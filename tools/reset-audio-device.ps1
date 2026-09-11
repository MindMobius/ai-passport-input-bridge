<#
.SYNOPSIS
  重启指定 USB 音频设备的功能节点(usbaudio),修"端点正常但采集全零"的卡死。
.DESCRIPTION
  要点:必须打**音频功能子设备**(InstanceId 里带 &MI_xx、Service=usbaudio),
  不是 USB 复合设备父节点 —— 父节点不支持禁用,WMI 会报 0x80041001 常规故障。
  依次尝试:pnputil /restart-device → Disable/Enable-PnpDevice。
.NOTES
  需要管理员(UAC 自动提权)。会短暂中断该设备音频(默认输出会切走再切回)。
#>
[CmdletBinding()]
param(
    [string]$Match = 'VID_0CD4&PID_1004',
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
        if ($NoTest) { $a += '-NoTest' }
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $a -Wait
        exit 0
    }
}

# 选目标:优先音频功能子设备(MEDIA / Service=usbaudio),否则退回复合设备
$cands = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
         Where-Object { $_.InstanceId -like "*$Match*" }
if (-not $cands) {
    Write-Host "[X] 没找到匹配 '$Match' 的设备 —— 确认已插好" -ForegroundColor Red
    exit 1
}
$audio = $cands | Where-Object { $_.Class -eq 'MEDIA' } | Select-Object -First 1
$dev = if ($audio) { $audio } else { $cands | Sort-Object { $_.InstanceId.Length } | Select-Object -First 1 }

Write-Host "候选设备:" -ForegroundColor Cyan
$cands | ForEach-Object { Write-Host ("  [{0}] {1}  {2}" -f $_.Class, $_.FriendlyName, $_.InstanceId) }
Write-Host "选中: $($dev.FriendlyName) ($($dev.Class))" -ForegroundColor Green
Write-Host "      $($dev.InstanceId)`n"

if ($DryRun) {
    Write-Host "[dry-run] 将执行: pnputil /restart-device `"$($dev.InstanceId)`"" -ForegroundColor Yellow
    Write-Host "[dry-run] 失败则退化为 Disable-PnpDevice + Enable-PnpDevice" -ForegroundColor Yellow
    exit 0
}

function Try-Restart {
    param([string]$InstanceId)
    $out = & pnputil /restart-device "$InstanceId" 2>&1
    $text = ($out | Out-String)
    Write-Host ($text.Trim())
    if ($text -match 'pending system reboot') { return 'pending' }
    if ($text -match 'Failed|拒绝|denied') { return 'fail' }
    return 'ok'
}

Write-Host "[1/2] pnputil /restart-device ..." -ForegroundColor Cyan
$result = Try-Restart -InstanceId $dev.InstanceId
if ($result -eq 'pending') {
    Write-Host "`n[!] Windows 报告:该设备处于 `"等待重启完成上一次操作`" 状态。" -ForegroundColor Red
    Write-Host "    软件侧已无解 —— **需要重启一次 Windows**,重启后再跑一次本脚本或拔插一次 USB 线。" -ForegroundColor Yellow
    if (-not $NoTest) { Write-Host "(跳过电平测试:设备未重新初始化)" -ForegroundColor Yellow }
    exit 3
}

if ($result -ne 'ok') {
    Write-Host "[2/2] pnputil 未成功,改用 Disable/Enable-PnpDevice ..." -ForegroundColor Cyan
    try {
        Disable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false
        Start-Sleep -Seconds 3
        Enable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false
        Write-Host "  Disable/Enable 完成" -ForegroundColor Green
    } catch {
        Write-Host "[X] 两种方式都失败: $_" -ForegroundColor Red
        Write-Host "    可靠兜底:把设备的 USB 线拔掉 10 秒再插回;若提示等待重启,就重启一次 Windows。" -ForegroundColor Yellow
        exit 2
    }
}
Start-Sleep -Seconds 4

$after = Get-PnpDevice -InstanceId $dev.InstanceId -ErrorAction SilentlyContinue
Write-Host "`n完成。设备当前状态: $($after.Status)" -ForegroundColor Green

if (-not $NoTest) {
    Write-Host "`n现在对着它的麦克风说话,做 6 秒电平测试(峰值 > 30 才算有声音):" -ForegroundColor Cyan
    $repo = Split-Path -Parent $PSScriptRoot
    $py = Join-Path $repo '.venv\Scripts\python.exe'
    $tool = Join-Path $PSScriptRoot 'mic-level-test.py'
    if ((Test-Path $py) -and (Test-Path $tool)) { & $py $tool --device "A1" --seconds 6 }
    else { Write-Host "(没找到 .venv/tools,手动跑 mic-level-test.cmd)" -ForegroundColor Yellow }
}
Write-Host "`n仍然全零的话:换 USB 口 / 换另一台电脑测同一台 A1;换机也全零 = 设备硬件或固件问题。" -ForegroundColor Yellow
