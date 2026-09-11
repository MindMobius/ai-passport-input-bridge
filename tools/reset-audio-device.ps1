<#
.SYNOPSIS
  重新枚举指定 USB 音频设备(等价于拔插 USB),用于修"端点正常但采集全零"的卡死。
.NOTES
  - 需要管理员权限(UAC);脚本会自己请求提权。
  - 默认匹配 B&O Beoplay A1(VID_0CD4&PID_1004),可用 -Match 指定别的设备。
  - 会短暂中断该设备的音频(它如果是默认输出,声音会切走再切回)。
#>
[CmdletBinding()]
param(
    [string]$Match = 'VID_0CD4&PID_1004',
    [int]$WaitSeconds = 3,
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
        Write-Host "[dry-run] 当前不是管理员;真实运行到这里会弹 UAC 提权。" -ForegroundColor Yellow
    } else {
        Write-Host "需要管理员权限,正在请求提权(会弹 UAC)..." -ForegroundColor Yellow
        $a = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath,
               '-Match', $Match, '-WaitSeconds', $WaitSeconds)
        if ($NoTest) { $a += '-NoTest' }
        Start-Process -FilePath 'powershell.exe' -Verb RunAs -ArgumentList $a -Wait
        exit 0
    }
}

$dev = Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue |
       Where-Object { $_.InstanceId -like "*$Match*" } |
       Sort-Object { $_.InstanceId.Length } | Select-Object -First 1   # 取最上层的复合设备

if (-not $dev) {
    Write-Host "[X] 没找到匹配 '$Match' 的设备 —— 确认设备已插好" -ForegroundColor Red
    exit 1
}

Write-Host "目标设备: $($dev.FriendlyName)" -ForegroundColor Cyan
Write-Host "  InstanceId: $($dev.InstanceId)"
Write-Host "  当前状态  : $($dev.Status)"

if ($DryRun) {
    Write-Host "[dry-run] 将执行: Disable-PnpDevice -> 等待 $WaitSeconds s -> Enable-PnpDevice" -ForegroundColor Yellow
    exit 0
}

Write-Host "`n[1/3] 禁用设备(等价于拔掉)..." -ForegroundColor Cyan
Disable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false
Start-Sleep -Seconds $WaitSeconds

Write-Host "[2/3] 重新启用(等价于插回)..." -ForegroundColor Cyan
try {
    Enable-PnpDevice -InstanceId $dev.InstanceId -Confirm:$false
} catch {
    Write-Host "[!] 重新启用失败: $_" -ForegroundColor Red
    Write-Host "    请到 设备管理器 里手动启用该设备,或直接拔插一次 USB 线。" -ForegroundColor Yellow
    exit 2
}
Start-Sleep -Seconds 4

$after = Get-PnpDevice -InstanceId $dev.InstanceId -ErrorAction SilentlyContinue
Write-Host "[3/3] 完成。当前状态: $($after.Status)" -ForegroundColor Green

if (-not $NoTest) {
    Write-Host "`n现在对着它的麦克风说话,做 6 秒电平测试(峰值 > 30 才算有声音):" -ForegroundColor Cyan
    $repo = Split-Path -Parent $PSScriptRoot
    $py = Join-Path $repo '.venv\Scripts\python.exe'
    $tool = Join-Path $PSScriptRoot 'mic-level-test.py'
    if ((Test-Path $py) -and (Test-Path $tool)) {
        & $py $tool --device "A1" --seconds 6
    } else {
        Write-Host "(没找到 .venv/tools,手动跑: mic-level-test.cmd)" -ForegroundColor Yellow
    }
}
Write-Host "`n如果重新枚举后仍然全零:换 USB 口 / 换台电脑再测;都为零 = 设备硬件或固件问题。" -ForegroundColor Yellow
