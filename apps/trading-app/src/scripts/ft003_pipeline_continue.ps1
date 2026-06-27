# FT-003: continue expansion agents after MVP sweeps.
# Usage (from apps/trading-app/src):
#   powershell -File scripts\ft003_pipeline_continue.ps1

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

function Wait-SweepDone($agent) {
    $lock = "$Root\workspaces\$agent\logs\sweep.lock"
    $progress = "$Root\workspaces\$agent\logs\sweep_progress.log"
    Log "waiting for $agent sweep..."
    while ($true) {
        if (Test-Path $lock) {
            $pidText = (Get-Content $lock -Raw).Trim().Split()[0]
            $proc = Get-Process -Id ([int]$pidText) -ErrorAction SilentlyContinue
            if ($proc) {
                Start-Sleep -Seconds 30
                continue
            }
        }
        if (Test-Path $progress) {
            $last = Get-Content $progress -Encoding utf8 | Select-Object -Last 1
            if ($last -match '"event"\s*:\s*"sweep_done"') {
                Log "$agent sweep_done"
                return
            }
            if ($last -match '"event"\s*:\s*"sweep_failed"') {
                throw "$agent sweep_failed: $last"
            }
        }
        if (-not (Test-Path $lock)) {
            $result = "$Root\workspaces\$agent\sweep_result.jsonl"
            if ((Test-Path $result) -and ((Get-Content $result).Count -gt 0)) {
                Log "$agent result present, lock gone"
                return
            }
        }
        Start-Sleep -Seconds 30
    }
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

Log "pipeline start"
Set-Location $Src

# 1) finish agent-execution if still running
Wait-SweepDone "agent-execution"
& $Py scripts\ft003_fill_analysis.py agent-execution --sections sweep
Log "agent-execution analysis §3 done"

# 2) agent-risk-exit (27 combos)
Run-Baseline "agent-risk-exit"
Run-Sweep "agent-risk-exit"
Log "agent-risk-exit done"

# 3) agent-regime (6 combos)
Run-Baseline "agent-regime"
Run-Sweep "agent-regime"
Log "agent-regime done"

Log "pipeline complete"
