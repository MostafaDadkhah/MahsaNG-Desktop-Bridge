#!/usr/bin/env python3
"""Regression checks for Android parity around free config rotation.

`MahsaNG` Android parser (`q/g`) shuffles free configs, keeps at most 10
per fetch, and gives imported free configs per-refresh identity. The desktop
bridge mirrors the rotation and varies only display remarks so Shadowrocket sees
a fresh subscription without breaking proxy credentials.
"""

from __future__ import annotations

import json
import random
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mahsa_bridge  # noqa: E402


def without_fragment(link: str) -> str:
    return link.split("#", 1)[0]


def remark(link: str) -> str:
    return urllib.parse.unquote(link.split("#", 1)[1])


def test_decode_free_limits_rotates_and_refreshes_identity() -> None:
    payload = {
        "mtn": [{"config": f"vless://mtn-{i}.example:443?encryption=none#MTN {i}"} for i in range(12)],
        "mci": [{"config": f"vless://mci-{i}.example:443?encryption=none#MCI {i}"} for i in range(12)],
    }

    plain = json.dumps(payload)

    original_fetch_text = mahsa_bridge.fetch_text
    original_decrypt = mahsa_bridge.aes_cbc_decrypt_base64

    try:
        mahsa_bridge.fetch_text = lambda *_a, **_k: plain
        mahsa_bridge.aes_cbc_decrypt_base64 = lambda *args: plain

        random.seed(20260627)
        first = mahsa_bridge.decode_free("all", timeout=3)
        random.seed(20260627)
        second = mahsa_bridge.decode_free("all", timeout=3)

        all_links = [entry["config"] for entry in payload["mtn"] + payload["mci"]]
        assert len(first) == 10
        assert [without_fragment(link) for link in first] == [without_fragment(link) for link in second]
        assert {without_fragment(link) for link in first}.issubset({without_fragment(link) for link in all_links})
        assert first != second
        assert all("mahsa-" in remark(link) for link in first)
        assert len(set(first)) == 10
    finally:
        mahsa_bridge.fetch_text = original_fetch_text
        mahsa_bridge.aes_cbc_decrypt_base64 = original_decrypt


if __name__ == "__main__":
    test_decode_free_limits_rotates_and_refreshes_identity()
    print("android_rotation_ok")
