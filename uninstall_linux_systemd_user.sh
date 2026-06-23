#!/usr/bin/env bash
set -euo pipefail

LABEL="com.mostafa.mahsang.bridge"
UNIT_FILE="$HOME/.config/systemd/user/$LABEL.service"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user disable --now "$LABEL.service" >/dev/null 2>&1 || true
  systemctl --user daemon-reload >/dev/null 2>&1 || true
fi
rm -f "$UNIT_FILE"

echo "Stopped and removed $LABEL from Linux/systemd user services"
