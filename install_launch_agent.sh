#!/bin/zsh
set -euo pipefail

LABEL="com.mostafa.mahsang.bridge"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-/usr/local/bin/python3}"
BIND="${BIND:-127.0.0.1:18080}"
SOURCE="${SOURCE:-all}"
CARRIER="${CARRIER:-all}"
CACHE_SECONDS="${CACHE_SECONDS:-300}"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$PROJECT_DIR/logs"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python not found/executable at: $PYTHON_BIN" >&2
  echo "Set PYTHON_BIN=/path/to/python3 and retry." >&2
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
try:
    import cryptography
except Exception:
    raise SystemExit("Missing dependency: cryptography. Run: python3 -m pip install cryptography")
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
  </dict>
</dict>
</plist>
PLIST

UID_NUM="$(id -u)"
launchctl bootout "gui/$UID_NUM" "$PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"
launchctl kickstart -k "gui/$UID_NUM/$LABEL"

echo "Installed and started $LABEL"
echo "Subscription: http://$BIND/sub"
echo "Plain links:   http://$BIND/links"
echo "Health:        http://$BIND/health"
echo "Plist:         $PLIST"
echo "Logs:          $LOG_DIR"
