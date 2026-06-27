#!/usr/bin/env bash
# Run unit tests for all packages in the tfx-trading monorepo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

bash "$ROOT/scripts/setup-dev.sh"

if [[ -z "${VIRTUAL_ENV:-}" && -f "$ROOT/.venv/bin/activate" ]]; then
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
fi
PY=python

run() {
  echo "=== $1 ==="
  (cd "$ROOT/$1" && "$PY" run_tests.py)
}

run packages/trading-engine
run packages/trading-backtest
run packages/strategies/vwap-momentum
run packages/strategies/momentum-continuation
run apps/trading-app

echo "All package test suites passed."