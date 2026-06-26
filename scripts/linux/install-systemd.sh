#!/usr/bin/env bash
# Install systemd unit for live trading on Linux/GCE. Requires root.
set -euo pipefail

MONOREPO_ROOT="${MONOREPO_ROOT:-/opt/tfx-trading}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "請以 root 執行（sudo bash scripts/linux/install-systemd.sh）" >&2
  exit 1
fi

if [[ ! -d "$MONOREPO_ROOT/.git" ]]; then
  echo "警告: $MONOREPO_ROOT 尚未 clone — 請先 git clone 再執行本腳本" >&2
fi

id -u tfx &>/dev/null || useradd --system --home "$MONOREPO_ROOT" --shell /usr/sbin/nologin tfx
mkdir -p /etc/tfx-trading /var/log/tfx-trading
mkdir -p "$MONOREPO_ROOT"/{tick_cache,reports,snapshots}
chown -R tfx:tfx /var/log/tfx-trading
if [[ -d "$MONOREPO_ROOT" ]]; then
  chown -R tfx:tfx "$MONOREPO_ROOT"
fi

if [[ ! -f /etc/tfx-trading/env ]]; then
  cat > /etc/tfx-trading/env <<'EOF'
SJ_API_KEY=
SJ_SEC_KEY=
LOG_FILE=/var/log/tfx-trading/trading-app-uat.log
CONFIG_PATH=/opt/tfx-trading/apps/trading-app/config/config.yaml
TICK_ARCHIVE=1
KBARS_ARCHIVE=1
EOF
  echo "已建立 /etc/tfx-trading/env — 請填入 API 金鑰後 systemctl start tfx-trading"
fi
chown root:tfx /etc/tfx-trading/env
chmod 640 /etc/tfx-trading/env

sed "s|/opt/tfx-trading|$MONOREPO_ROOT|g" "$SCRIPT_DIR/tfx-trading.service" \
  > /etc/systemd/system/tfx-trading.service

systemctl daemon-reload
systemctl enable tfx-trading
echo "已安裝 tfx-trading.service（enable）。編輯 /etc/tfx-trading/env 後：systemctl start tfx-trading"
echo "git pull 請用: sudo -u tfx git -C $MONOREPO_ROOT pull（repo 已 chown tfx）"