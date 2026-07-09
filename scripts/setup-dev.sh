#!/usr/bin/env bash
# Editable install trading-app (includes in-tree trading_engine).
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
"$PY" -m pip install -q -e "$ROOT/apps/trading-app"
"$PY" -m pip install -q shioaji "PyYAML>=6.0"
