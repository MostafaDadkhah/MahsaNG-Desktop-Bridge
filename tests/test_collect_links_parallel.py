#!/usr/bin/env python3
"""Regression test for fast subscription refresh.

Shadowrocket can abandon subscription updates if the local bridge spends too
long fetching free and EMS feeds sequentially. source=all must fetch both feeds
concurrently so one slow upstream does not double the client wait time.
"""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path
from typing import Any, cast

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = PROJECT_ROOT / "mahsa_bridge.py"
spec = importlib.util.spec_from_file_location("mahsa_bridge", MODULE_PATH)
assert spec and spec.loader
mahsa_bridge = cast(Any, importlib.util.module_from_spec(spec))
sys.modules["mahsa_bridge"] = mahsa_bridge
spec.loader.exec_module(mahsa_bridge)


def test_collect_links_all_fetches_feeds_in_parallel() -> None:
    calls: list[str] = []

    def fake_free(carrier: str = "all", timeout: int = 12) -> list[str]:
        calls.append(f"free:{carrier}:{timeout}")
        time.sleep(0.35)
        return ["vless://free"]

    def fake_ems(timeout: int = 12) -> list[str]:
        calls.append(f"ems:{timeout}")
        time.sleep(0.35)
        return ["vmess://ems"]

    old_free = mahsa_bridge.decode_free
    old_ems = mahsa_bridge.decode_ems
    mahsa_bridge.decode_free = fake_free
    mahsa_bridge.decode_ems = fake_ems
    try:
        started = time.monotonic()
        links = mahsa_bridge.collect_links(source="all", carrier="mtn", timeout=7)
        elapsed = time.monotonic() - started
    finally:
        mahsa_bridge.decode_free = old_free
        mahsa_bridge.decode_ems = old_ems

    assert links == ["vless://free", "vmess://ems"]
    assert set(calls) == {"free:mtn:7", "ems:7"}
    assert elapsed < 0.6, f"source=all appears sequential; elapsed={elapsed:.3f}s"


if __name__ == "__main__":
    test_collect_links_all_fetches_feeds_in_parallel()
    print("collect_links_parallel_ok")
