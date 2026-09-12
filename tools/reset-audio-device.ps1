<#
.SYNOPSIS
  安全地重启/启用指定 USB 音频设备的功能节点(usbaudio)。
.DESCRIPTION
  安全保证:
    * 设备当前处于"已禁用"(ProblemCode 22)时,只做"启用",绝不再禁用;
    * 任何分支结束后都会再尝试一次 Enable,避免把设备留在禁用状态;
    * 默认目标为音频功能子设备(&MI_xx / Class=MEDIA),不是 USB 复合父节点
      (父节点不支持禁用,WMI 会报 0x80041001)。
.PARAMETER EnableOnly
  只启用,不重启(设备被误禁用时用这个)。
#>
[CmdletBinding()]
param(
    [string]$Match = 'VID_0CD4&PID_1004',
    [switch]$EnableOnly,
    [switch]$DryRun,
    [switch]$NoTest
)

$ErrorActionPreference = 'Stop'

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return ([Security.Principal.WindowsPrincipal]$id).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    if ($DryRun) {
        Write-Host "[dry-run] 当前不是管理员;真实运行会弹 UAC 提权。" -ForegroundColor Yellow
    } else {
        Write-Host "需要管理员权限,正在请求提权(会弹 UAC)..." -ForegroundColor Yellow
        $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-Match', $Match)
        if ($EnableOnly) { $a += '-EnableOnly' }
        if ($NoTest) { $a += '-NoTest' }
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $a -Wait
        exit 0
    }
}

function Get-ProblemCode([string]$InstanceId) {
    try { return (Get-PnpDeviceProperty -InstanceId $InstanceId -KeyName 'DEVPKEY_Device_ProblemCode' -ErrorAction Stop).Data } catch { return $null }
}

# 选目标:优先音频功能子设备(MEDIA),退回复合父节点
$cands = Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object { $_.InstanceId -like "*$Match*" }
if (-not $cands) { Write-Host "[X] 没找到匹配 '$Match' 的设备" -ForegroundColor Red; exit 1 }
$present = $cands | Where-Object { $_.Status -eq 'OK' }
$target = ($present | Where-Object { $_.Class -eq 'MEDIA' } | Select-Object -First 1)
if (-not $target) { $target = ($present | Sort-Object { $_.InstanceId.Length } | Select-Object -First 1) }
# 没有任何 OK 的设备 -> 用父设备(可能就是被禁用的那个)
if (-not $target) { $target = ($cands | Sort-Object { $_.InstanceId.Length } | Select-Object -First 1) }

$parent = $cands | Where-Object { $_.InstanceId -notmatch '&MI_' } | Select-Object -First 1
Write-Host "候选:" -ForegroundColor Cyan
$cands | ForEach-Object { Write-Host ("  [{0}] {1}  {2}" -f $_.Status, $_.FriendlyName, $_.InstanceId) }
Write-Host "目标: $($target.FriendlyName) ($($target.InstanceId))" -ForegroundColor Green
$code = Get-ProblemCode $target.InstanceId
Write-Host "  当前 ProblemCode: $code   (22 = 已禁用,需要启用)" -ForegroundColor Yellow

if ($DryRun) {
    Write-Host "[dry-run] 计划: $(if ($EnableOnly -or $code -eq 22) { 'pnputil /enable-device' } else { 'pnputil /restart-device(失败则 Disable+Enable)' })" -ForegroundColor Yellow
    exit 0
}

function Invoke-Pnputil([string[]]$Args) {
    $out = & pnputil @Args 2>&1
    $text = ($out | Out-String)
    Write-Host $text.Trim()
    if ($text -match 'pending system reboot') { return 'pending' }
    if ($text -match 'Failed|denied|拒绝') { return 'fail' }
    return 'ok'
}

$disabled = ($EnableOnly -or $code -eq 22)
if ($disabled) {
    Write-Host "[1/2] 设备处于禁用状态 -> 只执行启用" -ForegroundColor Cyan
    $r = Invoke-Pnputil @('/enable-device', $target.InstanceId)
    if ($r -ne 'ok' -and $parent) { Invoke-Pnputil @('/enable-device', $parent.InstanceId) | Out-Null }
} else {
    Write-Host "[1/2] pnputil /restart-device ..." -ForegroundColor Cyan
    $r = Invoke-Pnputil @('/restart-device', $target.InstanceId)
    if ($r -eq 'pending') {
        Write-Host "`n[!] Windows 报告该设备 `"等待重启完成上一次操作`" -> 需要重启一次 Windows。" -ForegroundColor Red
    } elseif ($r -ne 'ok') {
        Write-Host "[2/2] 退化:Disable + Enable(并保证最后一定启用)" -ForegroundColor Cyan
        try { Disable-PnpDevice -InstanceId $target.InstanceId -Confirm:$false -ErrorAction Stop } catch { Write-Host "  Disable 失败(忽略): $_" -ForegroundColor Yellow }
        Start-Sleep -Seconds 3
    }
}

# ==== 安全兜底:不管上面怎么走,最后都保证设备是启用的 ====
Write-Host "[safety] 确保设备处于启用状态 ..." -ForegroundColor Cyan
foreach ($t in @($target.InstanceId) + @($parent.InstanceId | Where-Object { $_ })) {
    try {
        $c = Get-ProblemCode $t
        if ($c -eq 22) { Invoke-Pnputil @('/enable-device', $t) | Out-Null }
    } catch { }
}
try { Enable-PnpDevice -InstanceId $target.InstanceId -Confirm:$false -ErrorAction SilentlyContinue } catch { }
Start-Sleep -Seconds 3

$after = Get-PnpDevice -InstanceId $target.InstanceId -ErrorAction SilentlyContinue
$code2 = if ($after) { Get-ProblemCode $target.InstanceId } else { 'n/a' }
Write-Host "完成。状态=$($after.Status -join ',')  ProblemCode=$code2" -ForegroundColor Green

if (-not $NoTest) {
    Write-Host "`n现在对着它的麦克风说话,做 6 秒电平测试(峰值 > 30 才算有声音):" -ForegroundColor Cyan
    $repo = Split-Path -Parent $PSScriptRoot
    $py = Join-Path $repo '.venv\Scripts\python.exe'
    $tool = Join-Path $PSScriptRoot 'mic-level-test.py'
    if ((Test-Path $py) -and (Test-Path $tool)) { & $py $tool --device "A1" --seconds 6 }
    else { Write-Host "(手动跑 mic-level-test.cmd)" -ForegroundColor Yellow }
}
