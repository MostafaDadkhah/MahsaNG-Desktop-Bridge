#!/usr/bin/env python3
"""Regression checks for Android dynamic config source parity."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mahsa_bridge  # noqa: E402


def test_android_dynamic_crypto_round_trip() -> None:
    original_time = mahsa_bridge.time.time
    original_local_time = mahsa_bridge.android_local_time
    original_token = mahsa_bridge.generate_android_token
    try:
        mahsa_bridge.time.time = lambda: 1_700_000_000
        mahsa_bridge.android_local_time = lambda: "20231114_221320"
        mahsa_bridge.generate_android_token = lambda *_args, **_kwargs: "T" * 68

        token, ciphertext, body = mahsa_bridge.build_android_dynamic_request(
            hashes=["old-hash"],
            provider_code="provider",
            client_ip="1.2.3.4",
        )
        decoded = json.loads(
            mahsa_bridge.aes_cbc_decrypt_base64(
                ciphertext,
                mahsa_bridge.android_dynamic_request_key(),
                mahsa_bridge.ANDROID_API_IV,
            )
        )
        _, default_ciphertext, default_body = mahsa_bridge.build_android_dynamic_request(
            hashes=["old-hash"],
            client_ip="1.2.3.4",
        )
        default_decoded = json.loads(
            mahsa_bridge.aes_cbc_decrypt_base64(
                default_ciphertext,
                mahsa_bridge.android_dynamic_request_key(),
                mahsa_bridge.ANDROID_API_IV,
            )
        )
    finally:
        mahsa_bridge.time.time = original_time
        mahsa_bridge.android_local_time = original_local_time
        mahsa_bridge.generate_android_token = original_token

    assert token == "T" * 68
    assert body == decoded
    assert decoded["hashes"] == ["old-hash"]
    assert decoded["client_ip"] == "1.2.3.4"
    assert decoded["client_version"] == mahsa_bridge.ANDROID_CLIENT_VERSION
    assert decoded["client_source"] == mahsa_bridge.ANDROID_CLIENT_SOURCE
    assert decoded["h1"] == mahsa_bridge.android_h1("1.2.3.4", "1700000000")
    assert decoded["request_time"] == "1700000000 UTC"
    assert decoded["local_time"] == "20231114_221320 UTC"
    assert default_body == default_decoded
    assert default_decoded["provider_code"] == ""

    response_ciphertext = mahsa_bridge.aes_cbc_encrypt_base64(
        json.dumps(
            {
                "configs": [
                    {"url": "vless://dynamic.example:443?encryption=none"},
                    {"url": "not-a-proxy-link"},
                ],
                "is_captcha": False,
            },
            separators=(",", ":"),
        ),
        mahsa_bridge.android_dynamic_response_key(),
        mahsa_bridge.ANDROID_API_IV,
    )
    response = mahsa_bridge.decrypt_android_dynamic_response(response_ciphertext)
    assert response["configs"][0]["url"].startswith("vless://")


def test_collect_links_android_prefers_dynamic() -> None:
    calls: list[str] = []

    def fake_dynamic(timeout: int = 12, captcha_id: str = "", captcha_input: str = "") -> list[str]:
        calls.append(f"dynamic:{timeout}:{captcha_id}:{captcha_input}")
        return ["vless://dynamic.example:443?encryption=none"]

    def fail_free(*_args: Any, **_kwargs: Any) -> list[str]:
        raise AssertionError("backup free feed should not be used when dynamic has links")

    def fail_ems(*_args: Any, **_kwargs: Any) -> list[str]:
        raise AssertionError("backup EMS feed should not be used when dynamic has links")

    original_dynamic = mahsa_bridge.fetch_android_dynamic
    original_free = mahsa_bridge.decode_free
    original_ems = mahsa_bridge.decode_ems
    try:
        mahsa_bridge.fetch_android_dynamic = fake_dynamic
        mahsa_bridge.decode_free = fail_free
        mahsa_bridge.decode_ems = fail_ems
        links = mahsa_bridge.collect_links(source="android", carrier="all", timeout=4)
    finally:
        mahsa_bridge.fetch_android_dynamic = original_dynamic
        mahsa_bridge.decode_free = original_free
        mahsa_bridge.decode_ems = original_ems

    assert links == ["vless://dynamic.example:443?encryption=none"]
    assert calls == ["dynamic:4::"]


def test_collect_links_android_falls_back_on_captcha() -> None:
    calls: list[str] = []

    def fake_dynamic(timeout: int = 12, captcha_id: str = "", captcha_input: str = "") -> list[str]:
        calls.append("dynamic")
        raise mahsa_bridge.DynamicCaptchaRequired("captcha-id", "captcha-png")

    def fake_free(carrier: str = "all", timeout: int = 12) -> list[str]:
        calls.append(f"free:{carrier}:{timeout}")
        return ["vless://free.example:443?encryption=none"]

    def fail_ems(timeout: int = 12) -> list[str]:
        raise AssertionError("Android button fallback should use MAHSA_SUB before EMS")

    original_dynamic = mahsa_bridge.fetch_android_dynamic
    original_free = mahsa_bridge.decode_free
    original_ems = mahsa_bridge.decode_ems
    try:
        mahsa_bridge.fetch_android_dynamic = fake_dynamic
        mahsa_bridge.decode_free = fake_free
        mahsa_bridge.decode_ems = fail_ems
        links = mahsa_bridge.collect_links(source="android", carrier="mci", timeout=5)
        try:
            mahsa_bridge.collect_links(source="dynamic", carrier="mci", timeout=5)
        except mahsa_bridge.DynamicCaptchaRequired:
            dynamic_only_raised = True
        else:
            dynamic_only_raised = False
    finally:
        mahsa_bridge.fetch_android_dynamic = original_dynamic
        mahsa_bridge.decode_free = original_free
        mahsa_bridge.decode_ems = original_ems

    assert links == ["vless://free.example:443?encryption=none"]
    assert dynamic_only_raised
    assert calls[:2] == ["dynamic", "free:mci:5"]


if __name__ == "__main__":
    test_android_dynamic_crypto_round_trip()
    test_collect_links_android_prefers_dynamic()
    test_collect_links_android_falls_back_on_captcha()
    print("dynamic_source_ok")
