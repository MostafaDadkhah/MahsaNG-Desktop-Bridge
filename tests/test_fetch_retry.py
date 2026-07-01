#!/usr/bin/env python3
"""Regression checks for transient upstream fetch failures."""

from __future__ import annotations

import http.client
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mahsa_bridge  # noqa: E402


class FakeResponse:
    def __init__(self, body: bytes | None = None, exc: Exception | None = None) -> None:
        self.body = body
        self.exc = exc

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def read(self) -> bytes:
        if self.exc:
            raise self.exc
        assert self.body is not None
        return self.body


def test_fetch_text_retries_incomplete_read() -> None:
    calls = 0

    def fake_urlopen(*_args: Any, **_kwargs: Any) -> FakeResponse:
        nonlocal calls
        calls += 1
        if calls == 1:
            return FakeResponse(exc=http.client.IncompleteRead(b"partial", 5))
        return FakeResponse(body=b"ok")

    original_urlopen = mahsa_bridge.urllib.request.urlopen
    original_sleep = mahsa_bridge.time.sleep
    try:
        mahsa_bridge.urllib.request.urlopen = fake_urlopen
        mahsa_bridge.time.sleep = lambda *_args, **_kwargs: None
        assert mahsa_bridge.fetch_text("https://example.test/feed", timeout=1) == "ok"
    finally:
        mahsa_bridge.urllib.request.urlopen = original_urlopen
        mahsa_bridge.time.sleep = original_sleep

    assert calls == 2


def test_fetch_text_uses_curl_fallback_after_urllib_failures() -> None:
    urlopen_calls = 0

    def fake_urlopen(*_args: Any, **_kwargs: Any) -> FakeResponse:
        nonlocal urlopen_calls
        urlopen_calls += 1
        raise TimeoutError("urllib stuck")

    def fake_run(*args: Any, **kwargs: Any) -> subprocess.CompletedProcess[bytes]:
        assert "curl" in args[0][0]
        assert kwargs["stdout"] == subprocess.PIPE
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout=b"curl-ok", stderr=b"")

    original_urlopen = mahsa_bridge.urllib.request.urlopen
    original_sleep = mahsa_bridge.time.sleep
    original_run = mahsa_bridge.subprocess.run
    try:
        mahsa_bridge.urllib.request.urlopen = fake_urlopen
        mahsa_bridge.time.sleep = lambda *_args, **_kwargs: None
        mahsa_bridge.subprocess.run = fake_run
        assert mahsa_bridge.fetch_text("https://example.test/feed", timeout=1) == "curl-ok"
    finally:
        mahsa_bridge.urllib.request.urlopen = original_urlopen
        mahsa_bridge.time.sleep = original_sleep
        mahsa_bridge.subprocess.run = original_run

    assert urlopen_calls == 2


if __name__ == "__main__":
    test_fetch_text_retries_incomplete_read()
    test_fetch_text_uses_curl_fallback_after_urllib_failures()
    print("fetch_retry_ok")
