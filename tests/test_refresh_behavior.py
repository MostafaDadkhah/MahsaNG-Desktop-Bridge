#!/usr/bin/env python3
"""Regression tests for server refresh behavior.

The desktop bridge must refresh upstream feeds on every client subscription
update request. Cache is allowed only as a last-good fallback when refresh fails,
not as the normal response for /sub, /links, or /json.
"""

from __future__ import annotations

import base64
import json
import sys
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mahsa_bridge import FetchResult, make_handler  # noqa: E402


class CountingCache:
    def __init__(self) -> None:
        self.calls: list[bool] = []
        self.counter = 0

    def get(self, force: bool = False) -> FetchResult:
        self.calls.append(force)
        self.counter += 1
        return FetchResult(
            links=[f"vless://00000000-0000-4000-8000-{self.counter:012d}@example.com:443?type=tcp"],
            generated_at=time.time(),
            source="all",
            carrier="all",
        )


def fetch(base: str, path: str) -> tuple[str, dict[str, str]]:
    with urllib.request.urlopen(base + path, timeout=10) as response:
        return response.read().decode("utf-8"), dict(response.headers.items())


def main() -> int:
    cache = CountingCache()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cache))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        health_body, _ = fetch(base, "/health")
        health = json.loads(health_body)
        assert health["links"] == 1
        assert cache.calls == [False], cache.calls

        sub_1, headers_1 = fetch(base, "/sub")
        sub_2, headers_2 = fetch(base, "/sub")
        decoded_1 = base64.b64decode(sub_1.strip()).decode("utf-8")
        decoded_2 = base64.b64decode(sub_2.strip()).decode("utf-8")

        assert cache.calls == [False, True, True], cache.calls
        assert decoded_1 != decoded_2, (decoded_1, decoded_2)
        assert headers_1.get("X-Mahsa-Stale") == "0"
        assert headers_2.get("X-Mahsa-Stale") == "0"
        assert "no-cache" in headers_1.get("Cache-Control", "")
        print("ok: /sub refreshes on every request; /health may use cached status")
        return 0
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
