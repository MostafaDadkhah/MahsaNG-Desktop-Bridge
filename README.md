# MahsaNG Desktop Bridge

Cross-platform local subscription bridge for MahsaNG daily configs on **macOS, Linux, and Windows**.

[MahsaNG](https://github.com/GFW-knocker/MahsaNG) is great on Android. This project is the small missing bridge for desktop users: it tries the same live Android config backend first, falls back to Android's `MAHSA_SUB` backup path when the backend requires captcha or fails, decrypts everything locally, and exposes a standard V2Ray-style subscription URL that desktop proxy clients can import.

It does **not** run a VPN by itself and it is **not** a replacement for the Android app. It is a companion tool that turns the daily MahsaNG ecosystem configs into a desktop-friendly local subscription.

## Local URLs

Use the local URL in desktop clients:

- Subscription URL: `http://127.0.0.1:18080/sub`
- Plain links for inspection: `http://127.0.0.1:18080/links`
- JSON links: `http://127.0.0.1:18080/json`
- Health/status: `http://127.0.0.1:18080/health`
- Human refresh diagnostics: `http://127.0.0.1:18080/debug`

`/sub`, `/links`, `/json`, and `/debug` force a fresh upstream fetch on every request. The default `android` source first calls the live Mahsa Android backend (`/backend/app_api/v7/config_fetch/`) with the APK-compatible encrypted request shape (`provider_code=""`, Android timestamps, and JSON-string ciphertext body). If that backend asks for captcha, the bridge falls back to the same Android button backup path (`MAHSA_SUB`, rotating up to 10 configs) so unattended clients still receive usable configs.

Use `/sub` in clients that expect a normal V2Ray subscription URL.

For Shadowrocket or another client on your phone, use the Mac LAN address instead:

- `http://<mac-lan-ip>:18080/sub`

The macOS installer binds the service to `0.0.0.0:18080` by default so LAN clients can reach the bridge. If you only use local desktop clients, install with `BIND=127.0.0.1:18080`.

## Requirements

- Python 3.10+
- `cryptography`

Install dependencies:

macOS / Linux:

```bash
python3 -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -3 -m pip install -r requirements.txt
```

## Install as a background service

### macOS LaunchAgent

```bash
cd ~/Documents/MahsaNG-Desktop-Bridge
./install_macos_launch_agent.sh
```

Backward-compatible alias:

```bash
./install_launch_agent.sh
```

Uninstall:

```bash
./uninstall_macos_launch_agent.sh
```

### Linux systemd user service

```bash
git clone https://github.com/MostafaDadkhah/MahsaNG-Desktop-Bridge.git
cd MahsaNG-Desktop-Bridge
python3 -m pip install -r requirements.txt
./install_linux_systemd_user.sh
```

Uninstall:

```bash
./uninstall_linux_systemd_user.sh
```

If your distro does not use systemd user services, use manual mode below.

### Windows Scheduled Task

PowerShell:

```powershell
git clone https://github.com/MostafaDadkhah/MahsaNG-Desktop-Bridge.git
cd MahsaNG-Desktop-Bridge
py -3 -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\install_windows_scheduled_task.ps1
```

Uninstall:

```powershell
powershell -ExecutionPolicy Bypass -File .\uninstall_windows_scheduled_task.ps1
```

## Manual run

macOS / Linux:

```bash
python3 mahsa_bridge.py --serve 0.0.0.0:18080
```

Windows PowerShell:

```powershell
py -3 .\mahsa_bridge.py --serve 127.0.0.1:18080
```

## Generate files without a server

macOS / Linux:

```bash
python3 mahsa_bridge.py --format base64 -o ~/Downloads/mahsa-sub.txt
python3 mahsa_bridge.py --format plain -o ~/Downloads/mahsa-links.txt
```

Windows PowerShell:

```powershell
py -3 .\mahsa_bridge.py --format base64 -o "$env:USERPROFILE\Downloads\mahsa-sub.txt"
py -3 .\mahsa_bridge.py --format plain -o "$env:USERPROFILE\Downloads\mahsa-links.txt"
```

## Smoke test

With the bridge running:

macOS / Linux:

```bash
python3 smoke_test.py
```

Windows PowerShell:

```powershell
py -3 .\smoke_test.py
```

## Configuration

The service installers accept environment variables or parameters:

- Bind address: default `0.0.0.0:18080` on macOS/Linux helpers so LAN clients such as Shadowrocket can update from `http://<mac-lan-ip>:18080/sub`. Use `127.0.0.1:18080` for local-only.
- Source: default `android` = live Android backend first, then Android `MAHSA_SUB` backup rotation. Other values: `dynamic` (live backend only), `all` (backup free + EMS), `free`, or `ems`.
- Carrier for MahsaFreeConfig: `all`, `mtn`, or `mci`
- Cache seconds: default `300` for `/health` status reuse; subscription endpoints always refresh upstream on each request and only use the last good snapshot as a fallback if refresh fails.

Examples:

macOS / Linux:

```bash
BIND=127.0.0.1:19090 SOURCE=free ./install_linux_systemd_user.sh
```

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\install_windows_scheduled_task.ps1 -Bind "127.0.0.1:19090" -Source free
```

## Config sources

- Live Android backend: `https://www.mahsaserver.com/backend/app_api/v7/config_fetch/`
- Remote Android update metadata: `https://raw.githubusercontent.com/GFW-knocker/MahsaNG/master/remote_config_update_v14.json`
- `https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/main/app/sub.txt`
- `https://raw.githubusercontent.com/GFW-knocker/MahsaNG/master/mahsa_EMS_accounts.json`

The bridge emits only standard links such as `vless://`, `vmess://`, `ss://`, and `trojan://`.

## Notes

- Link counts can change because the upstream feeds are live.
- If Python networking hangs on a local/system proxy that `curl` can use correctly, the script falls back to `curl` for that request without hardwiring any VPN-specific proxy port.
- If `http://127.0.0.1:18080/sub` updates but `http://<mac-lan-ip>:18080/sub` shows old configs, another process is probably listening on the LAN wildcard address. Check with `lsof -nP -iTCP:18080 -sTCP:LISTEN`, stop the stale process, then reinstall/restart the LaunchAgent.
- This bridge only converts/serves subscriptions for another desktop client. It does not route traffic by itself.
