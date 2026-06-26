#!/usr/bin/env bash
# Migrate deprecated monorepo kbar_cache/*_kbars_* into tick_cache/ (tick_cache SSOT).
# Usage: MONOREPO_ROOT=~/tfx-trading bash scripts/linux/migrate-legacy-kbar-cache.sh [--dry-run]
set -euo pipefail

MONOREPO_ROOT="${MONOREPO_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
APP_SRC="$MONOREPO_ROOT/apps/trading-app/src"
PYTHON="${VENV_PYTHON:-$MONOREPO_ROOT/.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

export PYTHONPATH="${PYTHONPATH:-$APP_SRC}"
cd "$APP_SRC"
exec "$PYTHON" -m storage.legacy_cache_migrate "$@"
