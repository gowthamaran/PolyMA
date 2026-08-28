#!/usr/bin/env bash
set -euo pipefail

POLYMA_DIR="$(pwd -P)"
POLYMA_USER="${SUDO_USER:-$(id -un)}"

if [[ ! -f "$POLYMA_DIR/main.py" || ! -f "$POLYMA_DIR/requirements.txt" ]]; then
  echo "Run this script from the PolyMA repository root." >&2
  exit 1
fi

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
python3 -m venv "$POLYMA_DIR/.venv"
"$POLYMA_DIR/.venv/bin/python" -m pip install --upgrade pip
"$POLYMA_DIR/.venv/bin/python" -m pip install -r "$POLYMA_DIR/requirements.txt"

if [[ ! -f "$POLYMA_DIR/.env" ]]; then
  cp "$POLYMA_DIR/.env.example" "$POLYMA_DIR/.env"
  chmod 600 "$POLYMA_DIR/.env"
  echo "Created .env. Edit it before enabling Telegram or exposing the dashboard."
fi

mkdir -p "$POLYMA_DIR/data" "$POLYMA_DIR/logs" "$POLYMA_DIR/exports"
"$POLYMA_DIR/.venv/bin/python" "$POLYMA_DIR/main.py" stats >/dev/null

for service in polyma-scanner polyma-dashboard; do
  sed -e "s|__POLYMA_DIR__|$POLYMA_DIR|g" -e "s|__POLYMA_USER__|$POLYMA_USER|g" \
    "$POLYMA_DIR/systemd/$service.service" | sudo tee "/etc/systemd/system/$service.service" >/dev/null
done

sudo systemctl daemon-reload
sudo systemctl enable --now polyma-scanner.service polyma-dashboard.service

echo "PolyMA Lab installed."
echo "Scanner:   sudo systemctl status polyma-scanner"
echo "Dashboard: sudo systemctl status polyma-dashboard"
echo "Logs:      journalctl -u polyma-scanner -f"

