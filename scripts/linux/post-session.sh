#!/usr/bin/env bash
# Post-session maintenance: compress tick_cache, daily JSON report, determinism hash.
# Run after market close. GCP 14:00 shutdown: root stop @13:50, then this @13:54 (see docs/ops/LinuxOps.md).
# 24/7 VMs: root stop @15:50, this @15:54.
set -euo pipefail

MONOREPO_ROOT="${MONOREPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
VENV_PYTHON="${VENV_PYTHON:-$MONOREPO_ROOT/.venv/bin/python}"
SRC_DIR="$MONOREPO_ROOT/apps/trading-app/src"

if [[ -f /etc/tfx-trading/env ]]; then
  set -a
  # shellcheck disable=SC1091
  source /etc/tfx-trading/env
  set +a
fi

export PYTHONPATH="${PYTHONPATH:-$SRC_DIR}"
for sibling in \
  "$MONOREPO_ROOT/packages/trading-engine/src" \
  "$MONOREPO_ROOT/packages/trading-backtest/src" \
  "$MONOREPO_ROOT/packages/strategies/vwap-momentum/src"; do
  if [[ -d "$sibling" ]]; then
    export PYTHONPATH="$sibling:$PYTHONPATH"
  fi
done

LOG_FILE="${LOG_FILE:-/var/log/tfx-trading/trading-app-uat.log}"
LOG_DIR="${LOG_DIR:-$(dirname "$LOG_FILE")}"
LOG_KEEP_DAYS="${LOG_KEEP_DAYS:-14}"
REPORTS_DIR="$MONOREPO_ROOT/reports"
SNAPSHOTS_DIR="$MONOREPO_ROOT/snapshots"
DATE_ISO="$(TZ=Asia/Taipei date +%Y-%m-%d)"
DAY="$(TZ=Asia/Taipei date +%Y%m%d)"

_rotate_tfx_logs() {
  [[ -d "$LOG_DIR" ]] || return 0

  shopt -s nullglob
  local f archive="$LOG_DIR/post-session.log.$DATE_ISO"
  for f in "$LOG_DIR"/*.log.[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]; do
    gzip -f "$f"
  done

  if [[ -f "$LOG_DIR/post-session.log" && -s "$LOG_DIR/post-session.log" \
    && ! -f "$archive" && ! -f "${archive}.gz" ]]; then
    cp "$LOG_DIR/post-session.log" "$archive"
    gzip -f "$archive"
    : > "$LOG_DIR/post-session.log"
  fi

  find "$LOG_DIR" -maxdepth 1 -type f \
    \( -name '*.log.[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].gz' \
    -o -name 'post-session.log.[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9].gz' \) \
    -mtime +"$LOG_KEEP_DAYS" -delete
}

mkdir -p "$REPORTS_DIR" "$SNAPSHOTS_DIR"

cd "$MONOREPO_ROOT"
"$VENV_PYTHON" -m storage

if [[ -f "$LOG_FILE" ]]; then
  "$VENV_PYTHON" -m reporting "$LOG_FILE" --json > "$REPORTS_DIR/day${DAY}.json"
  echo "Wrote reports/day${DAY}.json"
else
  echo "略過 reporting：找不到 LOG_FILE=$LOG_FILE" >&2
fi

"$VENV_PYTHON" -m sweep.determinism_check \
  --date "$DATE_ISO" \
  --mode hash \
  --output "$SNAPSHOTS_DIR/determinism_${DAY}.txt"
echo "Wrote snapshots/determinism_${DAY}.txt"

_rotate_tfx_logs
echo "Rotated logs under $LOG_DIR (keep ${LOG_KEEP_DAYS}d)"
echo "Post-session done."