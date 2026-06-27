# MahsaNG Desktop Bridge

Cross-platform local subscription bridge for MahsaNG daily configs on **macOS, Linux, and Windows**.

[MahsaNG](https://github.com/GFW-knocker/MahsaNG) is great on Android. This project is the small missing bridge for desktop users: it fetches the encrypted feeds used by MahsaNG / MahsaFreeConfig, decrypts them locally, and exposes a standard V2Ray-style subscription URL that desktop proxy clients can import.

It does **not** run a VPN by itself and it is **not** a replacement for the Android app. It is a companion tool that turns the daily MahsaNG ecosystem configs into a desktop-friendly local subscription.

## Local URLs

After running the bridge:

- Base64 subscription: `http://127.0.0.1:18080/sub`
- Plain links: `http://127.0.0.1:18080/links`
- JSON links: `http://127.0.0.1:18080/json`
- Health/status: `http://127.0.0.1:18080/health`

Use `/sub` in clients that expect a normal V2Ray subscription URL.

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
python3 mahsa_bridge.py --serve 127.0.0.1:18080
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

- Bind address: default `127.0.0.1:18080`
- Source: `all`, `free`, or `ems`
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

## Feeds currently decoded

- `https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/main/app/sub.txt`
- `https://raw.githubusercontent.com/GFW-knocker/MahsaNG/master/mahsa_EMS_accounts.json`

The bridge emits only standard links such as `vless://`, `vmess://`, `ss://`, and `trojan://`.

## Notes

- Link counts can change because the upstream feeds are live.
- If local Python has a broken/missing CA bundle, the script retries public GitHub feed requests without certificate verification and logs a warning.
- This bridge only converts/serves subscriptions for another desktop client. It does not route traffic by itself.
