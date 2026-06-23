# MahsaNG macOS Bridge

Local macOS subscription bridge for MahsaNG daily configs.

It fetches the encrypted feeds used by MahsaNG / MahsaFreeConfig, decrypts them locally, and exposes a standard V2Ray subscription URL for macOS clients.

## Local URLs

After installation:

- Base64 subscription: `http://127.0.0.1:18080/sub`
- Plain links: `http://127.0.0.1:18080/links`
- JSON links: `http://127.0.0.1:18080/json`
- Health/status: `http://127.0.0.1:18080/health`

Use `/sub` in clients that expect a normal V2Ray subscription URL.

## Install / start

```bash
cd ~/Documents/MahsaNG-macOS-Bridge
./install_launch_agent.sh
```

This installs a per-user LaunchAgent:

`~/Library/LaunchAgents/com.mostafa.mahsang.bridge.plist`

The service binds only to localhost (`127.0.0.1:18080`).

## Stop / uninstall

```bash
cd ~/Documents/MahsaNG-macOS-Bridge
./uninstall_launch_agent.sh
```

## Manual run

```bash
python3 mahsa_bridge.py --serve 127.0.0.1:18080
```

## Generate files without server

```bash
python3 mahsa_bridge.py --format base64 -o ~/Downloads/mahsa-sub.txt
python3 mahsa_bridge.py --format plain -o ~/Downloads/mahsa-links.txt
```

## Smoke test

```bash
python3 smoke_test.py
```

## Feeds currently decoded

- `https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/main/app/sub.txt`
- `https://raw.githubusercontent.com/GFW-knocker/MahsaNG/master/mahsa_EMS_accounts.json`

The bridge emits only standard links such as `vless://`, `vmess://`, `ss://`, and `trojan://`.

## Notes

- Link counts can change because the upstream feeds are live.
- If macOS Python has a broken/missing CA bundle, the script retries public GitHub feed requests without certificate verification and logs a warning.
- This bridge does not run a VPN itself. It only converts/serves subscriptions for another macOS client.
