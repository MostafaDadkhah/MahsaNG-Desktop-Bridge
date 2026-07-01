#!/bin/zsh
set -euo pipefail

LABEL="com.mostafa.mahsang.bridge"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/local/bin/python3}"
# Bind to all interfaces by default so LAN clients such as Shadowrocket can
# update from http://<mac-lan-ip>:18080/sub. Override with
# BIND=127.0.0.1:18080 for local-only desktop clients.
BIND="${BIND:-0.0.0.0:18080}"
SOURCE="${SOURCE:-android}"
CARRIER="${CARRIER:-all}"
CACHE_SECONDS="${CACHE_SECONDS:-300}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$PROJECT_DIR/logs"

if [[ ! -x "$PYTHON_BIN" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="$(command -v python3)"
  else
    echo "Python not found. Install Python 3.10+ and retry." >&2
    exit 1
  fi
fi

"$PYTHON_BIN" - <<'PY'
try:
    import cryptography
except Exception:
    raise SystemExit("Missing dependency: cryptography. Run: python3 -m pip install -r requirements.txt")
PY

mkdir -p "$HOME/Library/LaunchAgents" "$LOG_DIR"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON_BIN</string>
    <string>$PROJECT_DIR/mahsa_bridge.py</string>
    <string>--serve</string>
    <string>$BIND</string>
    <string>--source</string>
    <string>$SOURCE</string>
    <string>--carrier</string>
    <string>$CARRIER</string>
    <string>--cache-seconds</string>
    <string>$CACHE_SECONDS</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$PROJECT_DIR</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/stdout.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/stderr.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
    <key>PYTHON_BIN</key>
    <string>$PYTHON_BIN</string>
    <key>BIND</key>
    <string>$BIND</string>
    <key>SOURCE</key>
    <string>$SOURCE</string>
    <key>CARRIER</key>
    <string>$CARRIER</string>
    <key>CACHE_SECONDS</key>
    <string>$CACHE_SECONDS</string>
  </dict>
</dict>
</plist>
PLIST

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"
launchctl kickstart -k "gui/$UID_NUM/$LABEL"

echo "Installed and started $LABEL for macOS"
echo "Subscription: http://$BIND/sub"
echo "Plain links:   http://$BIND/links"
echo "Health:        http://$BIND/health"
if [[ "$BIND" == 0.0.0.0:* ]]; then
  PORT="${BIND##*:}"
  echo "LAN URLs:"
  ifconfig | awk -v port="$PORT" '/^[a-z].*:/{iface=$1} /inet / && $2 !~ /^127\./ {printf "  http://%s:%s/sub  (%s)\n", $2, port, iface}'
fi
echo "Plist:         $PLIST"
echo "Logs:          $LOG_DIR"
