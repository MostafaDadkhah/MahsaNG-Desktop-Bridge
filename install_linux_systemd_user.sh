#!/usr/bin/env bash
set -euo pipefail

LABEL="com.mostafa.mahsang.bridge"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BIND="${BIND:-127.0.0.1:18080}"
SOURCE="${SOURCE:-all}"
CARRIER="${CARRIER:-all}"
CACHE_SECONDS="${CACHE_SECONDS:-300}"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_FILE="$UNIT_DIR/$LABEL.service"
LOG_DIR="$PROJECT_DIR/logs"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "systemctl not found. Use manual mode instead: python3 mahsa_bridge.py --serve 127.0.0.1:18080" >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON_BIN. Install Python 3.10+ or set PYTHON_BIN=/path/to/python3." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
try:
    import cryptography
except Exception:
    raise SystemExit("Missing dependency: cryptography. Run: python3 -m pip install -r requirements.txt")
PY

mkdir -p "$UNIT_DIR" "$LOG_DIR"

cat > "$UNIT_FILE" <<UNIT
[Unit]
Description=MahsaNG Desktop Bridge local subscription server
After=network-online.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
Environment=PYTHONUNBUFFERED=1
Environment=PYTHON_BIN=$PYTHON_BIN
Environment=BIND=$BIND
Environment=SOURCE=$SOURCE
Environment=CARRIER=$CARRIER
Environment=CACHE_SECONDS=$CACHE_SECONDS
ExecStart=/usr/bin/env bash -lc 'exec "$PROJECT_DIR/run_bridge_unix.sh"'
Restart=always
RestartSec=5
StandardOutput=append:$LOG_DIR/stdout.log
StandardError=append:$LOG_DIR/stderr.log

[Install]
WantedBy=default.target
UNIT

systemctl --user daemon-reload
systemctl --user enable --now "$LABEL.service"

echo "Installed and started $LABEL for Linux/systemd user session"
echo "Subscription: http://$BIND/sub"
echo "Plain links:   http://$BIND/links"
echo "Health:        http://$BIND/health"
echo "Unit:          $UNIT_FILE"
echo "Logs:          $LOG_DIR"
