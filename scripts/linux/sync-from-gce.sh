#!/usr/bin/env bash
# Pull tick_cache, kbar_cache, reports, snapshots, logs from GCE live host to on-prem.
# Usage: GCE_HOST=<deploy-user>@1.2.3.4 MONOREPO_ROOT=~/tfx-trading ./scripts/linux/sync-from-gce.sh
# Example (see docs/ops/LinuxOps.md): GCE_HOST=you@static-ip bash scripts/linux/sync-from-gce.sh
set -euo pipefail

MONOREPO_ROOT="${MONOREPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
GCE_HOST="${GCE_HOST:?set GCE_HOST=deploy-user@static-ip (SSH user, not tfx)}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/tfx-trading}"

_sync_dir() {
  local name="$1"
  local local_dir="$MONOREPO_ROOT/$name"
  mkdir -p "$local_dir"

  # 使用 --ignore-missing-args 讓 rsync 在遠端目錄不存在時不會報錯
  rsync -avz --progress --ignore-missing-args \
    "$GCE_HOST:$REMOTE_ROOT/$name/" \
    "$local_dir/" || true
}

_sync_dir tick_cache
_sync_dir kbar_cache
_sync_dir reports
_sync_dir snapshots

if [[ -n "${SYNC_LOGS:-}" ]]; then
  mkdir -p "$MONOREPO_ROOT/logs-from-gce"
  if ssh -o BatchMode=yes -o ConnectTimeout=10 "$GCE_HOST" "test -d /var/log/tfx-trading" 2>/dev/null; then
    rsync -avz --progress \
      "$GCE_HOST:/var/log/tfx-trading/" \
      "$MONOREPO_ROOT/logs-from-gce/"
  else
    echo "略過 logs：遠端尚無 /var/log/tfx-trading/" >&2
  fi
fi

echo "Sync complete → $MONOREPO_ROOT (tick_cache, kbar_cache, reports, snapshots)"