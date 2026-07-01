#!/usr/bin/env bash
# Start live/simulation session (Linux / GCE). See docs/ops/LinuxOps.md
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/common-env.sh"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "找不到 venv Python: $VENV_PYTHON （請在 monorepo 根執行 bash scripts/setup-dev.sh）" >&2
  exit 1
fi
if [[ ! -d "$SRC_DIR" ]]; then
  echo "找不到 app src: $SRC_DIR" >&2
  exit 1
fi

cd "$SRC_DIR"
exec "$VENV_PYTHON" -m live
