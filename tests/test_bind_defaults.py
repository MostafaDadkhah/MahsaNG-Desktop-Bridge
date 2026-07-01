#!/usr/bin/env python3
"""Regression checks for LAN-accessible bridge defaults.

Shadowrocket updates run from another device, so the default service bind must be
reachable on the Mac LAN address. Binding only 127.0.0.1 lets local curl work
while phone clients hit a different wildcard listener or fail entirely.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mahsa_bridge  # noqa: E402


def test_default_bind_is_lan_reachable() -> None:
    assert mahsa_bridge.DEFAULT_BIND == "0.0.0.0:18080"
    assert mahsa_bridge.parse_bind(mahsa_bridge.DEFAULT_BIND) == ("0.0.0.0", 18080)


def test_unix_service_wrapper_defaults_to_lan_bind() -> None:
    script = (Path(__file__).resolve().parents[1] / "run_bridge_unix.sh").read_text(encoding="utf-8")
    assert 'BIND="${BIND:-0.0.0.0:18080}"' in script
    assert 'SOURCE="${SOURCE:-android}"' in script


def test_macos_launch_agent_invokes_python_directly() -> None:
    script = (Path(__file__).resolve().parents[1] / "install_macos_launch_agent.sh").read_text(encoding="utf-8")
    assert "run_bridge_unix.sh</string>" not in script
    assert "<string>$PYTHON_BIN</string>" in script
    assert "<string>$PROJECT_DIR/mahsa_bridge.py</string>" in script
    assert 'SOURCE="${SOURCE:-android}"' in script


def test_linux_installer_defaults_to_lan_bind_and_android_source() -> None:
    script = (Path(__file__).resolve().parents[1] / "install_linux_systemd_user.sh").read_text(encoding="utf-8")
    assert 'BIND="${BIND:-0.0.0.0:18080}"' in script
    assert 'SOURCE="${SOURCE:-android}"' in script


def test_windows_helpers_default_to_android_source() -> None:
    root = Path(__file__).resolve().parents[1]
    installer = (root / "install_windows_scheduled_task.ps1").read_text(encoding="utf-8")
    runner = (root / "run_bridge_windows.ps1").read_text(encoding="utf-8")
    assert '[string]$Source = "android"' in installer
    assert '$Source = "android"' in runner


if __name__ == "__main__":
    test_default_bind_is_lan_reachable()
    test_unix_service_wrapper_defaults_to_lan_bind()
    test_macos_launch_agent_invokes_python_directly()
    test_linux_installer_defaults_to_lan_bind_and_android_source()
    test_windows_helpers_default_to_android_source()
    print("bind_defaults_ok")
