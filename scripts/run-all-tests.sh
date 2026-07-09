#!/usr/bin/env bash
# Run unit tests for the trading-app product (host + storage + strategy).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

bash "$ROOT/scripts/setup-dev.sh"

if [[ -z "${VIRTUAL_ENV:-}" && -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi
PY=python

echo "=== apps/trading-app ==="
(cd "$ROOT/apps/trading-app" && "$PY" run_tests.py)

echo "All tests passed."
