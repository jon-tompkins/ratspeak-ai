#!/usr/bin/env bash
# One-shot installer for a fresh Debian/Ubuntu box.
set -euo pipefail

INSTALL_DIR="/opt/ratspeak-ai"
ETC_DIR="/etc/ratspeak-ai"
SERVICE_USER="ratspeak"

if [[ $EUID -ne 0 ]]; then
  echo "Run as root (sudo)."
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv python3-pip git

id -u "$SERVICE_USER" &>/dev/null || useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"

mkdir -p "$INSTALL_DIR" "$ETC_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

# Source (assumes script is run from a checkout of this repo).
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
rsync -a --delete --exclude state --exclude .git "$SRC_DIR/" "$INSTALL_DIR/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

sudo -u "$SERVICE_USER" python3 -m venv "$INSTALL_DIR/.venv"
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR"

if [[ ! -f "$ETC_DIR/config.toml" ]]; then
  cp "$INSTALL_DIR/config.example.toml" "$ETC_DIR/config.toml"
  echo "Wrote default config to $ETC_DIR/config.toml — edit before starting."
fi

if [[ ! -f "$ETC_DIR/env" ]]; then
  cat > "$ETC_DIR/env" <<EOF
VENICE_API_KEY=
EOF
  chmod 600 "$ETC_DIR/env"
  echo "Created $ETC_DIR/env — set VENICE_API_KEY before starting."
fi

install -m 644 "$INSTALL_DIR/systemd/ratspeak-ai-bot.service" /etc/systemd/system/
systemctl daemon-reload
echo
echo "Install done. Next:"
echo "  1. edit $ETC_DIR/env  (VENICE_API_KEY)"
echo "  2. edit $ETC_DIR/config.toml"
echo "  3. systemctl enable --now ratspeak-ai-bot"
echo "  4. journalctl -u ratspeak-ai-bot -f"
