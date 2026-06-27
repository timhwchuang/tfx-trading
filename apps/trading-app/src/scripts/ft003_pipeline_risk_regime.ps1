# Resume FT-003 from agent-risk-exit (execution already done).
$ErrorActionPreference = "Stop"
$Root = "C:\Users\Tim\Desktop\tfx-trading"
$Src = "$Root\apps\trading-app\src"
$Py = "$Root\.venv\Scripts\python.exe"
$Log = "$Root\workspaces\ft003_pipeline.log"

function Log($msg) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg"
    Add-Content -Path $Log -Value $line -Encoding utf8
    Write-Host $line
}

function Run-Baseline($agent) {
    Log "baseline $agent"
    . C:\Users\Tim\Desktop\sinotrade\uat-env.ps1
    $env:LOG_LEVEL = "INFO"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONPATH = $Src
    $env:CONFIG_PATH = "$Root\workspaces\$agent\config\config.yaml"
    $logDir = "$Root\workspaces\$agent\logs"
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    $logFile = "$logDir\baseline_valid.log"
    Set-Location $Src
    & $Py -m backtest --dates-from-cache --cache-dir "$Root\tick_cache" `
        --from-date 2026-04-01 --to-date 2026-04-30 --report --log-file $logFile
    if ($LASTEXITCODE -ne 0) { throw "baseline failed $agent exit=$LASTEXITCODE" }
    $reportSrc = "$Root\reports\baseline_valid.json"
    $reportDst = "$Root\workspaces\$agent\reports\baseline_valid.json"
    if (-not (Test-Path $reportSrc)) { throw "missing report $reportSrc" }
    New-Item -ItemType Directory -Force -Path (Split-Path $reportDst) | Out-Null
    Copy-Item -Force $reportSrc $reportDst
    & $Py scripts\ft003_fill_analysis.py $agent --sections baseline
}

function Run-Sweep($agent) {
    Log "sweep $agent"
    . C:\Users\Tim\Desktop\sinotrade\uat-env.ps1
    $env:LOG_LEVEL = "ERROR"
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONPATH = $Src
    $env:CONFIG_PATH = "$Root\workspaces\$agent\config\config.yaml"
    Set-Location $Src
    & $Py scripts\ft003_run_sweep.py $agent
    if ($LASTEXITCODE -ne 0) { throw "sweep failed $agent exit=$LASTEXITCODE" }
    & $Py scripts\ft003_fill_analysis.py $agent --sections sweep
}

Log "resume risk-exit + regime"
Set-Location $Src
Run-Baseline "agent-risk-exit"
Run-Sweep "agent-risk-exit"
Log "agent-risk-exit done — starting agent-regime next"
Run-Baseline "agent-regime"
Run-Sweep "agent-regime"
Log "agent-regime done — pipeline complete"
Log "pipeline complete"
