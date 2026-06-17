#!/usr/bin/env bash
# Editable install all monorepo packages (dev / CI).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${PYTHON:-python3}"

if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  if [[ ! -d "$ROOT/.venv" ]]; then
    "$PY" -m venv "$ROOT/.venv"
  fi
  # shellcheck disable=SC1091
  source "$ROOT/.venv/bin/activate"
  PY=python
fi

"$PY" -m pip install -q -U pip
"$PY" -m pip install -q -e "$ROOT/packages/trading-engine"
"$PY" -m pip install -q -e "$ROOT/packages/trading-backtest"
"$PY" -m pip install -q -e "$ROOT/packages/strategies/vwap-momentum"
"$PY" -m pip install -q shioaji "PyYAML>=6.0"