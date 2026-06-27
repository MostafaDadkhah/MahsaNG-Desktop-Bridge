#!/usr/bin/env python3
"""Regression checks for Android parity around free config rotation.

`MahsaNG` Android parser (`q/g`) shuffles free configs and keeps at most 10
per fetch. The desktop bridge should mirror this to keep response size and
rotation behavior aligned.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mahsa_bridge  # noqa: E402


def test_decode_free_limits_and_rotates_to_10() -> None:
    payload = {
        "mtn": [{"config": f"vless://mtn-{i}"} for i in range(12)],
        "mci": [{"config": f"vmess://mci-{i}"} for i in range(12)],
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
        assert first == second
        assert set(first).issubset(set(all_links))
        assert len(set(first)) == 10
    finally:
        mahsa_bridge.fetch_text = original_fetch_text
        mahsa_bridge.aes_cbc_decrypt_base64 = original_decrypt



if __name__ == "__main__":
    test_decode_free_limits_and_rotates_to_10()
    print("android_rotation_ok")
