#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
# Bind to all interfaces by default so LAN clients such as Shadowrocket can
# update the subscription from the Mac. Override with BIND=127.0.0.1:18080 for
# local-only desktop clients.
BIND="${BIND:-0.0.0.0:18080}"
SOURCE="${SOURCE:-android}"
CARRIER="${CARRIER:-all}"
CACHE_SECONDS="${CACHE_SECONDS:-300}"

exec "$PYTHON_BIN" "$PROJECT_DIR/mahsa_bridge.py" \
  --serve "$BIND" \
  --source "$SOURCE" \
  --carrier "$CARRIER" \
  --cache-seconds "$CACHE_SECONDS"
