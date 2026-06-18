#!/usr/bin/env bash
# Pull tick_cache, reports, snapshots, logs from GCE live host to on-prem research machine.
# Usage: GCE_HOST=user@1.2.3.4 MONOREPO_ROOT=~/tfx-trading ./scripts/linux/sync-from-gce.sh
set -euo pipefail

MONOREPO_ROOT="${MONOREPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
GCE_HOST="${GCE_HOST:?set GCE_HOST=user@static-ip}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/tfx-trading}"

rsync -avz --progress \
  "$GCE_HOST:$REMOTE_ROOT/tick_cache/" \
  "$MONOREPO_ROOT/tick_cache/"

rsync -avz --progress \
  "$GCE_HOST:$REMOTE_ROOT/reports/" \
  "$MONOREPO_ROOT/reports/"

rsync -avz --progress \
  "$GCE_HOST:$REMOTE_ROOT/snapshots/" \
  "$MONOREPO_ROOT/snapshots/"

# Optional: pull rotated logs for calibration_cli / episode replay
if [[ -n "${SYNC_LOGS:-}" ]]; then
  rsync -avz --progress \
    "$GCE_HOST:/var/log/tfx-trading/" \
    "$MONOREPO_ROOT/logs-from-gce/"
fi

echo "Sync complete → $MONOREPO_ROOT (tick_cache, reports, snapshots)"