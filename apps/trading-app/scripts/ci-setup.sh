#!/usr/bin/env bash
# CI / dev install — delegates to monorepo setup-dev.sh
set -euo pipefail
APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MONOREPO="$(cd "$APP_ROOT/../.." && pwd)"
bash "$MONOREPO/scripts/setup-dev.sh"