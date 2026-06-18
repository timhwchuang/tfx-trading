#!/usr/bin/env bash
# Post-session maintenance: compress tick_cache + daily JSON report.
# Run after market close (default 15:30 cron). See docs/ops/LinuxOps.md
set -euo pipefail

MONOREPO_ROOT="${MONOREPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
VENV_PYTHON="${VENV_PYTHON:-$MONOREPO_ROOT/.venv/bin/python}"
export PYTHONPATH="${PYTHONPATH:-$MONOREPO_ROOT/apps/trading-app/src}"
LOG_FILE="${LOG_FILE:-/var/log/tfx-trading/trading-app-uat.log}"
REPORTS_DIR="$MONOREPO_ROOT/reports"
DAY="$(TZ=Asia/Taipei date +%Y%m%d)"

mkdir -p "$REPORTS_DIR"

cd "$MONOREPO_ROOT"
"$VENV_PYTHON" -m storage
"$VENV_PYTHON" -m reporting "$LOG_FILE" --json > "$REPORTS_DIR/day${DAY}.json"
echo "Post-session done: reports/day${DAY}.json"