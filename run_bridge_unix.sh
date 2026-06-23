#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
BIND="${BIND:-127.0.0.1:18080}"
SOURCE="${SOURCE:-all}"
CARRIER="${CARRIER:-all}"
CACHE_SECONDS="${CACHE_SECONDS:-300}"

exec "$PYTHON_BIN" "$PROJECT_DIR/mahsa_bridge.py" \
  --serve "$BIND" \
  --source "$SOURCE" \
  --carrier "$CARRIER" \
  --cache-seconds "$CACHE_SECONDS"
