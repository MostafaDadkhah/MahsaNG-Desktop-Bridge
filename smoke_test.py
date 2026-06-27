#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import sys
import urllib.request

def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18080"

    health = urllib.request.urlopen(base + "/health", timeout=90).read().decode("utf-8")
    health_obj = json.loads(health)
    print("health", json.dumps(health_obj, ensure_ascii=False))

    sub = urllib.request.urlopen(base + "/sub", timeout=90).read().decode("utf-8").strip()
    plain = base64.b64decode(sub).decode("utf-8")
    links = [line for line in plain.splitlines() if line.strip()]
    print("decoded_links", len(links))
    print(
        "protocol_counts",
        {proto: sum(link.startswith(proto) for link in links) for proto in ["vless://", "vmess://", "trojan://", "ss://"]},
    )
    print("first", links[0][:220] if links else "")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
