# Shared env for Linux live / post-session scripts. Source only — do not execute directly.
MONOREPO_ROOT="${MONOREPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
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
  "$MONOREPO_ROOT/packages/strategies/vwap-momentum/src" \
  "$MONOREPO_ROOT/packages/strategies/gudt-route-a/src"; do
  if [[ -d "$sibling" ]]; then
    export PYTHONPATH="$sibling:$PYTHONPATH"
  fi
done

# GUDT UAT / holdout replay on 2026-05 dates (determinism + backtest)
export FT003_HOLDOUT_UNSEAL="${FT003_HOLDOUT_UNSEAL:-1}"
