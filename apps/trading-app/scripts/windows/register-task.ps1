param(
    [Parameter(Mandatory = $false)]
    [string]$MonorepoRoot = "C:\tfx-trading",
    [string]$TaskName = "tfx-trading-vwap"
)

$ErrorActionPreference = "Stop"
$startScript = Join-Path $MonorepoRoot "apps\trading-app\scripts\windows\start-trading-app.ps1"

if (-not (Test-Path $startScript)) {
    throw "找不到 start-trading-app.ps1: $startScript"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -MonorepoRoot `"$MonorepoRoot`""

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "已註冊工作排程器任務: $TaskName (MonorepoRoot=$MonorepoRoot)"