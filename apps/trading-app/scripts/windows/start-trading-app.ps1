param(
    [Parameter(Mandatory = $false)]
    [string]$MonorepoRoot = "C:\tfx-trading"
)

$ErrorActionPreference = "Stop"
$venvPython = Join-Path $MonorepoRoot ".venv\Scripts\python.exe"
$srcDir = Join-Path $MonorepoRoot "apps\trading-app\src"

if (-not (Test-Path $venvPython)) {
    throw "找不到 venv Python: $venvPython （請在 monorepo 根目錄執行 scripts/setup-dev 或建立 .venv）"
}
if (-not (Test-Path $srcDir)) {
    throw "找不到 app src 目錄: $srcDir"
}

Set-Location $srcDir
& $venvPython -m live