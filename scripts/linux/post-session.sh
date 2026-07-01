#!/usr/bin/env bash
# Post-session maintenance: compress tick_cache, daily JSON report, determinism hash.
# Run after market close. GCP 14:00 shutdown: root stop @13:50, then this @13:54 (see docs/ops/LinuxOps.md).
# 24/7 VMs: root stop @15:50, this @15:54.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common-env.sh"

LOG_FILE="${LOG_FILE:-/var/log/tfx-trading/trading-app-uat.log}"
LOG_DIR="${LOG_DIR:-$(dirname "$LOG_FILE")}"
LOG_KEEP_DAYS="${LOG_KEEP_DAYS:-14}"
REPORTS_DIR="$MONOREPO_ROOT/reports"
SNAPSHOTS_DIR="$MONOREPO_ROOT/snapshots"
DATE_ISO="$(TZ=Asia/Taipei date +%Y-%m-%d)"
DAY="$(TZ=Asia/Taipei date +%Y%m%d)"
CONFIG_PATH="${CONFIG_PATH:-$MONOREPO_ROOT/apps/trading-app/config/config.yaml}"

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

_gudt_session_summary() {
  [[ -f "$LOG_FILE" ]] || return 0
  if ! grep -qE 'gudt_live state=|gudt_skip|GudtRouteA' "$LOG_FILE" 2>/dev/null; then
    return 0
  fi
  echo "--- GUDT session summary ($DATE_ISO) ---"
  grep -E 'gudt_live state=|gudt_skip' "$LOG_FILE" | tail -20 || true
  grep 'DAILY_SUMMARY ' "$LOG_FILE" | tail -1 || true
  echo "--- end GUDT summary ---"
}

mkdir -p "$REPORTS_DIR" "$SNAPSHOTS_DIR"

cd "$MONOREPO_ROOT"
"$VENV_PYTHON" -m storage

if [[ -f "$LOG_FILE" ]]; then
  "$VENV_PYTHON" -m reporting "$LOG_FILE" --json > "$REPORTS_DIR/day${DAY}.json"
  echo "Wrote reports/day${DAY}.json"
  _gudt_session_summary
else
  echo "略過 reporting：找不到 LOG_FILE=$LOG_FILE" >&2
fi

export CONFIG_PATH
"$VENV_PYTHON" -m sweep.determinism_check \
  --date "$DATE_ISO" \
  --mode hash \
  --output "$SNAPSHOTS_DIR/determinism_${DAY}.txt"
echo "Wrote snapshots/determinism_${DAY}.txt (CONFIG_PATH=$CONFIG_PATH)"

_rotate_tfx_logs
echo "Rotated logs under $LOG_DIR (keep ${LOG_KEEP_DAYS}d)"
echo "Post-session done."
