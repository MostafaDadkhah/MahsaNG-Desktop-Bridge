#!/usr/bin/env python3
"""
MahsaNG Desktop Bridge

Cross-platform local subscription bridge for MahsaNG/MahsaFreeConfig encrypted feeds.
It fetches live encrypted feeds, decrypts them using the same AES-CBC schemes
found in the official MahsaNG Android APK, and serves standard V2Ray-style
subscriptions for desktop clients on macOS, Linux, and Windows.

Routes when serving:
  /sub    -> base64 newline-separated subscription payload
  /links  -> plain newline-separated links
  /json   -> JSON array of links
  /health -> JSON status
  /debug  -> JSON refresh diagnostics for humans
"""

from __future__ import annotations

import argparse
import base64
import concurrent.futures
import gzip
import hashlib
import http.client
import json
import os
import re
import random
import ssl
import subprocess
import sys
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None  # type: ignore[assignment]

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception as exc:
    raise SystemExit(
        "Missing Python dependency: cryptography\n"
        "Install it with:\n"
        "  python3 -m pip install cryptography"
    ) from exc

Source = Literal["android", "dynamic", "all", "free", "ems"]
Carrier = Literal["all", "mtn", "mci"]
OutputFormat = Literal["base64", "plain", "json"]

FREE_URL = "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/main/app/sub.txt"
EMS_URL = "https://raw.githubusercontent.com/GFW-knocker/MahsaNG/master/mahsa_EMS_accounts.json"
REMOTE_UPDATE_URL = "https://raw.githubusercontent.com/GFW-knocker/MahsaNG/master/remote_config_update_v14.json"

FREE_IV = "lvcas56410c97lpb"       # APK q/c
EMS_IV = "Xvc1wOrxs77Ilj0N"        # APK q/e
ANDROID_API_IV = "lvcas56410c97lpb" # APK j/j
FREE_KEY_SEED = "mvcfhjju5632gfsseu95642yhfhnhjhty68532gfg"
EMS_KEY_SEED = "aassddy734321thjmvbxcdgtt67i7kmghddfhfdxb"
ANDROID_PACKAGE = "com.MahsaNet.MahsaNG"
# MD5 of the DER signing certificate from META-INF/BNDLTOOL.RSA, matching APK Lj/h.e().
ANDROID_SIGNATURE_MD5 = "d63b2eabf70b5fefc6ac38be9923bd1b"
ANDROID_CLIENT_VERSION = "14"
ANDROID_CLIENT_SOURCE = "g"
ANDROID_TIMEZONE = os.environ.get("MAHSA_ANDROID_TIMEZONE", "Asia/Tehran")
ANDROID_DYNAMIC_ENDPOINTS = (
    "https://www.mahsaserver.com",
    "https://r1.mahsaserver.com",
)

PROTOCOLS = ("vless://", "vmess://", "trojan://", "ss://")
ANDROID_FREE_ROTATION_LIMIT = 10
USER_AGENT = "MahsaNG-Desktop-Bridge/1.4"
DEFAULT_CACHE_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 12
DEFAULT_BIND = "0.0.0.0:18080"


@dataclass
class FetchResult:
    links: list[str]
    generated_at: float
    source: Source
    carrier: Carrier
    stale: bool = False
    error: str | None = None

    @property
    def protocol_counts(self) -> dict[str, int]:
        return {proto: sum(link.startswith(proto) for link in self.links) for proto in PROTOCOLS}

    @property
    def payload_hash(self) -> str:
        return hashlib.sha256("\n".join(self.links).encode("utf-8")).hexdigest()


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().zfill(32)


def free_key() -> str:
    digest = md5_hex(FREE_KEY_SEED)
    return digest[0:7] + digest[10:19]


def ems_key() -> str:
    digest = md5_hex(EMS_KEY_SEED)
    return digest[8:14] + digest[20:30]


def seeded_substring(seed: str, start: int, end: int) -> str:
    return md5_hex(seed)[start:end]


def remote_update_key() -> str:
    seed = "fsq7ncdlh1iu85642gnnvderhjkl77igfdgnfd"
    return seeded_substring(seed, 10, 17) + seeded_substring(seed, 20, 29)


def android_dynamic_request_key() -> str:
    seed = "tzqkkkad476mvcnneeq19087hnmggbalmnytcx55"
    return seeded_substring(seed, 10, 17) + seeded_substring(seed, 20, 29)


def android_dynamic_response_key() -> str:
    seed = "cnfhjkreewbnkis43hza65r4354756hgbfvdrsgfk"
    return seeded_substring(seed, 0, 7) + seeded_substring(seed, 10, 19)


def android_dynamic_token_salt() -> str:
    return seeded_substring("jfdvgjk5643790jgvdhnmddhssnyyy9521gfnbvfty", 4, 23)


def android_provider_salt() -> str:
    return seeded_substring("lmvbfgi5i94234ybssdul89853gjmnvreey9863bf", 5, 28)


def fetch_text(url: str, timeout: int = DEFAULT_TIMEOUT_SECONDS) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    # Framework Python on macOS commonly lacks a working CA bundle in fresh user
    # installs. Going through the failing verified handshake first made client
    # subscription updates slow enough for Shadowrocket to keep old configs. The
    # upstream feeds are public GitHub raw files, so use an unverified context for
    # these fetches and retry once for transient GitHub/proxy TLS EOFs.
    errors: list[str] = []
    for attempt in range(2):
        try:
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                return resp.read().decode("utf-8")
        except (TimeoutError, ssl.SSLError, urllib.error.URLError, http.client.IncompleteRead, OSError) as exc:
            errors.append(f"attempt {attempt + 1}: {type(exc).__name__}: {exc}")
            if attempt == 0:
                time.sleep(0.25)
                continue
            try:
                return curl_fetch_bytes(url, timeout=timeout).decode("utf-8")
            except Exception as curl_exc:
                errors.append(f"curl fallback: {type(curl_exc).__name__}: {curl_exc}")
                raise RuntimeError(f"fetch failed for {url}: {'; '.join(errors)}") from exc
    raise RuntimeError(f"fetch failed for {url}")


def curl_fetch_bytes(
    url: str,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
) -> bytes:
    """Fetch through curl as a runtime-network fallback.

    macOS Python `urllib` can hang on local system proxies that curl handles
    correctly. Curl uses the active system route/proxy without the bridge
    hardwiring any VPN-specific port.
    """
    cmd = [
        "curl",
        "-fsSL",
        "--compressed",
        "--connect-timeout",
        str(max(1, min(timeout, 8))),
        "--max-time",
        str(max(2, timeout + 5)),
        "-k",
    ]
    effective_headers = dict(headers or {})
    if "User-Agent" not in effective_headers:
        effective_headers["User-Agent"] = USER_AGENT
    for key, value in effective_headers.items():
        cmd.extend(["-H", f"{key}: {value}"])
    if method.upper() != "GET":
        cmd.extend(["-X", method.upper()])
    if data is not None:
        cmd.extend(["--data-binary", "@-"])
    cmd.append(url)
    result = subprocess.run(cmd, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout + 8)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"curl exited {result.returncode}: {stderr[:300]}")
    return result.stdout


def aes_cbc_encrypt_base64(plain: str, key: str, iv: str) -> str:
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plain.encode("utf-8")) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8"))).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(ciphertext).decode("ascii")


def aes_cbc_decrypt_base64(ciphertext_b64: str, key: str, iv: str) -> str:
    raw = base64.b64decode("".join(ciphertext_b64.split()))
    decryptor = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8"))).decryptor()
    padded = decryptor.update(raw) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return plain.decode("utf-8")


class DynamicCaptchaRequired(RuntimeError):
    def __init__(self, captcha_id: str, captcha_img: str) -> None:
        super().__init__(f"Mahsa dynamic API requires captcha_id={captcha_id}")
        self.captcha_id = captcha_id
        self.captcha_img = captcha_img


def android_h_b(request_time: str) -> str:
    return md5_hex(md5_hex(ANDROID_PACKAGE) + ANDROID_SIGNATURE_MD5[4:12] + request_time)


def android_h1(client_ip: str, request_time: str) -> str:
    material = (
        client_ip
        + md5_hex(ANDROID_PACKAGE)[10:18]
        + ANDROID_SIGNATURE_MD5[18:29]
        + request_time
        + android_h_b(request_time)
    )
    return md5_hex(material)[10:20]


def android_h_d(part_16: str, secret: str, salt: str, short_head: str, short_tail: str) -> str:
    material = md5_hex(part_16)[2:27] + secret + short_head + md5_hex(salt)[3:25] + secret + short_tail
    return md5_hex(material)[:20]


def generate_android_token(part_16: str | None = None, short_code: str | None = None) -> str:
    """Reproduce APK `Lj/k.a(..., ..., q())` token construction."""
    part_16 = part_16 or md5_hex(str(uuid.uuid4()))[:16]
    short_code = short_code or md5_hex(str(uuid.uuid4()))[:8]
    nonce_hash = md5_hex(str(uuid.uuid4()))
    nonce_a = nonce_hash[:7]
    nonce_b = nonce_hash[7:17]
    nonce_c = nonce_hash[17:24]
    nonce_joined = nonce_a + nonce_b + nonce_c
    secret = nonce_joined[5:9] + nonce_joined[14:18] + nonce_joined[20:22]
    code_head = short_code[:3]
    code_tail = short_code[3:]
    signed = android_h_d(part_16, secret, android_dynamic_token_salt(), code_head, code_tail)
    return (
        nonce_a
        + part_16[:5]
        + signed[:12]
        + code_tail
        + nonce_b
        + signed[12:20]
        + code_head
        + part_16[5:]
        + nonce_c
    )


def generate_provider_code(part_16: str | None = None) -> str:
    part_16 = part_16 or md5_hex(str(uuid.uuid4()))[:16]
    return md5_hex(part_16 + android_provider_salt())[:8]


def android_local_time() -> str:
    if ZoneInfo is not None:
        try:
            return datetime.now(ZoneInfo(ANDROID_TIMEZONE)).strftime("%Y%m%d_%H%M%S")
        except Exception:
            pass
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def fetch_public_ip(timeout: int = 5) -> str:
    configured = os.environ.get("MAHSA_CLIENT_IP", "").strip()
    if configured:
        return configured
    public_ip_urls = (
        "https://checkip.amazonaws.com/",
        "https://api.ipify.org/",
        "https://icanhazip.com/",
    )
    for url in public_ip_urls:
        try:
            candidate = curl_fetch_bytes(url, timeout=max(2, min(timeout, 4))).decode("utf-8").strip()
            if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", candidate):
                return candidate
        except Exception:
            continue
    return ""


def build_android_dynamic_request(
    hashes: list[str] | None = None,
    provider_code: str | None = None,
    captcha_id: str = "",
    captcha_input: str = "",
    client_ip: str | None = None,
    connected: bool = True,
) -> tuple[str, str, dict[str, Any]]:
    request_timestamp = int(time.time())
    signed_request_time = str(request_timestamp)
    request_time = signed_request_time
    local_time = android_local_time()
    if connected:
        request_time += " UTC"
        local_time += " UTC"
    client_ip = client_ip if client_ip is not None else fetch_public_ip()
    body: dict[str, Any] = {
        "hashes": hashes if hashes is not None else ["aaa", "bbb"],
        "h1": android_h1(client_ip, signed_request_time),
        "provider_code": provider_code if provider_code is not None else "",
        "timezone": ANDROID_TIMEZONE,
        "request_time": request_time,
        "request_timestamp": request_timestamp,
        "local_time": local_time,
        "client_ip": client_ip,
        "client_version": ANDROID_CLIENT_VERSION,
        "client_source": ANDROID_CLIENT_SOURCE,
        "captcha_id": captcha_id,
        "captcha_input": captcha_input,
    }
    body_json = json.dumps(body, separators=(",", ":"), ensure_ascii=False)
    ciphertext = aes_cbc_encrypt_base64(body_json, android_dynamic_request_key(), ANDROID_API_IV)
    return generate_android_token(), ciphertext, body


def post_android_dynamic_ciphertext(url: str, request_ciphertext: str, timeout: int) -> str:
    # The custom Android lib posts a JSON string whose value is the encrypted
    # payload. Posting the raw ciphertext gets HTTP 415/403 from the backend.
    data = json.dumps(request_ciphertext).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "*/*",
        "User-Agent": "MahsaNG/14",
    }
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers=headers,
    )
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            raw = resp.read()
            encoding = resp.headers.get("Content-Encoding", "")
            if encoding.lower() == "gzip" or raw[:2] == b"\x1f\x8b":
                raw = gzip.decompress(raw)
            return raw.decode("ascii")
    except (TimeoutError, ssl.SSLError, urllib.error.URLError, http.client.IncompleteRead, OSError):
        raw = curl_fetch_bytes(url, timeout=timeout, method="POST", data=data, headers=headers)
        if raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
        return raw.decode("ascii")


def decrypt_android_dynamic_response(response_ciphertext: str) -> dict[str, Any]:
    plain = aes_cbc_decrypt_base64(response_ciphertext, android_dynamic_response_key(), ANDROID_API_IV)
    data = json.loads(plain)
    if not isinstance(data, dict):
        raise ValueError("Mahsa dynamic response is not a JSON object")
    return data


def decode_remote_update(timeout: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    encrypted = fetch_text(REMOTE_UPDATE_URL, timeout=timeout).strip()
    plain = aes_cbc_decrypt_base64(encrypted, remote_update_key(), EMS_IV)
    data = json.loads(plain)
    if not isinstance(data, dict):
        raise ValueError("Mahsa remote update payload is not a JSON object")
    return data


def android_dynamic_endpoint_bases(timeout: int = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    configured = os.environ.get("MAHSA_DYNAMIC_ENDPOINTS")
    bases = [item.strip().rstrip("/") for item in configured.split(",")] if configured else []
    bases.extend(ANDROID_DYNAMIC_ENDPOINTS)
    # `remote_config_update_v14.json` currently exposes `mahsa_endpoints` as
    # bare IPs used by Android's network helpers, not as TLS backend hostnames.
    # Treating them as `https://<ip>/backend/...` makes unattended refreshes wait
    # through avoidable TLS/SNI timeouts. Keep them opt-in for diagnostics only.
    if os.environ.get("MAHSA_USE_REMOTE_UPDATE_ENDPOINTS") == "1":
        try:
            remote = decode_remote_update(timeout=timeout)
            update = remote.get("update_setting", {})
            endpoints = update.get("mahsa_endpoints", []) if isinstance(update, dict) else []
            if isinstance(endpoints, list):
                for endpoint in endpoints:
                    if isinstance(endpoint, str) and endpoint.strip():
                        value = endpoint.strip().rstrip("/")
                        if not value.startswith(("http://", "https://")):
                            value = "https://" + value
                        bases.append(value)
        except Exception:
            pass
    return dedupe_keep_order(bases)


def fetch_android_dynamic(
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    captcha_id: str = "",
    captcha_input: str = "",
) -> list[str]:
    token, request_ciphertext, _body = build_android_dynamic_request(
        captcha_id=captcha_id,
        captcha_input=captcha_input,
    )
    path = "/backend/app_api/v7/config_fetch/?token=" + urllib.parse.quote(token, safe="")
    errors: list[str] = []
    for base in android_dynamic_endpoint_bases(timeout=timeout):
        url = base.rstrip("/") + path
        try:
            response_ciphertext = post_android_dynamic_ciphertext(url, request_ciphertext, timeout=timeout)
            data = decrypt_android_dynamic_response(response_ciphertext)
            if data.get("is_captcha") is True:
                raise DynamicCaptchaRequired(str(data.get("captcha_id") or ""), str(data.get("captcha_img") or ""))
            configs = data.get("configs", [])
            if not isinstance(configs, list):
                raise ValueError("Mahsa dynamic response 'configs' is not a list")
            links: list[str] = []
            for entry in configs:
                if isinstance(entry, dict) and valid_link(entry.get("url")):
                    links.append(str(entry["url"]).strip())
            return dedupe_keep_order(links)
        except DynamicCaptchaRequired:
            raise
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Mahsa dynamic fetch failed: " + "; ".join(errors))


def valid_link(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(PROTOCOLS)


def dedupe_keep_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        item = item.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def normalize_android_free_link(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"\\u.{4}", "", raw)
    raw = raw.replace("\\", "")
    return raw.replace("&amp;", "&")


def apply_android_rotation(entries: list[str], limit: int = ANDROID_FREE_ROTATION_LIMIT) -> list[str]:
    if not entries:
        return []

    order = list(range(len(entries)))
    random.shuffle(order)

    selected: list[str] = []
    for idx in order:
        if len(selected) >= limit:
            break
        candidate = entries[idx].strip()
        if candidate:
            selected.append(candidate)

    return selected


def append_refresh_marker(title: str) -> str:
    marker = uuid.uuid4().hex[:8]
    return f"{title} · mahsa-{marker}" if title else f"mahsa-{marker}"


def add_android_style_refresh_identity(link: str) -> str:
    """Make each free-feed import visibly fresh without changing credentials.

    The Android app wraps each selected free config with a per-import random
    fake UUID/address mapping before import. Desktop clients do not have that
    MahsaNG-native mapping layer, so changing host or credential UUID would
    break otherwise valid proxy links. Instead, vary only the display name
    fragment/remark; Shadowrocket treats the fetched subscription as fresh, but
    the proxy endpoint and credentials stay intact.
    """
    if link.startswith("vmess://"):
        try:
            encoded = link.removeprefix("vmess://")
            encoded += "=" * ((4 - len(encoded) % 4) % 4)
            config = json.loads(base64.b64decode(encoded).decode("utf-8"))
            if isinstance(config, dict):
                config["ps"] = append_refresh_marker(str(config.get("ps") or ""))
                refreshed = base64.b64encode(
                    json.dumps(config, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                ).decode("ascii")
                return "vmess://" + refreshed
        except Exception:
            return link

    if link.startswith(("vless://", "trojan://", "ss://")):
        base_part, sep, fragment = link.partition("#")
        title = urllib.parse.unquote(fragment) if sep else ""
        return base_part + "#" + urllib.parse.quote(append_refresh_marker(title), safe="")

    return link


def decode_free(carrier: Carrier = "all", timeout: int = 30) -> list[str]:
    encrypted = fetch_text(FREE_URL, timeout=timeout).strip()
    plain = aes_cbc_decrypt_base64(encrypted, free_key(), FREE_IV)
    data = json.loads(plain)
    if not isinstance(data, dict):
        raise ValueError("MahsaFreeConfig payload is not a JSON object")

    carriers = ["mtn", "mci"] if carrier == "all" else [carrier]
    raw_links: list[str] = []
    for name in carriers:
        entries = data.get(name, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                candidate = entry.get("config")
                if isinstance(candidate, str):
                    normalized = normalize_android_free_link(candidate)
                    if normalized:
                        raw_links.append(normalized)

    return [add_android_style_refresh_identity(link) for link in apply_android_rotation(raw_links)]


def decode_ems(timeout: int = 30) -> list[str]:
    encrypted = fetch_text(EMS_URL, timeout=timeout).strip()
    plain = aes_cbc_decrypt_base64(encrypted, ems_key(), EMS_IV)
    data = json.loads(plain)
    if not isinstance(data, list):
        raise ValueError("MahsaNG EMS payload is not a JSON array")

    links: list[str] = []
    for entry in data:
        if isinstance(entry, dict) and valid_link(entry.get("url")):
            links.append(entry["url"].strip())
    return links


def collect_links(source: Source = "android", carrier: Carrier = "all", timeout: int = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
    if source == "dynamic":
        return fetch_android_dynamic(timeout=timeout)
    if source == "android":
        try:
            dynamic_links = fetch_android_dynamic(timeout=timeout)
            if dynamic_links:
                return dynamic_links
        except DynamicCaptchaRequired:
            # Android itself falls back to MAHSA_SUB when the dynamic m1() path
            # asks for a captcha. Preserve that behavior so unattended desktop
            # clients keep receiving usable configs without mixing in EMS.
            pass
        except Exception:
            # Keep the desktop bridge self-healing: dynamic API failures should
            # not strand Shadowrocket when the Android MAHSA_SUB backup is alive.
            pass
        return decode_free(carrier=carrier, timeout=timeout)

    if source == "free":
        return decode_free(carrier=carrier, timeout=timeout)
    if source == "ems":
        return dedupe_keep_order(decode_ems(timeout=timeout))

    # Fetch free + EMS in parallel. Subscription clients such as Shadowrocket
    # often have short update timeouts; sequential upstream fetches can make the
    # client abandon the update and keep the previous imported configs.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        free_future = executor.submit(decode_free, carrier=carrier, timeout=timeout)
        ems_future = executor.submit(decode_ems, timeout=timeout)
        free_links = free_future.result()
        ems_links = ems_future.result()
    return [*free_links, *ems_links]


def render_payload(links: list[str], output_format: OutputFormat) -> str:
    plain = "\n".join(links) + ("\n" if links else "")
    if output_format == "plain":
        return plain
    if output_format == "base64":
        return base64.b64encode(plain.encode("utf-8")).decode("ascii") + "\n"
    if output_format == "json":
        return json.dumps(links, ensure_ascii=False, indent=2) + "\n"
    raise ValueError(f"Unsupported output format: {output_format}")


class SubscriptionCache(Protocol):
    def get(self, force: bool = False) -> FetchResult:
        ...


class BridgeCache:
    def __init__(self, source: Source, carrier: Carrier, timeout: int, cache_seconds: int) -> None:
        self.source = source
        self.carrier = carrier
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self._last: FetchResult | None = None

    def get(self, force: bool = False) -> FetchResult:
        now = time.time()
        if (
            not force
            and self._last is not None
            and now - self._last.generated_at < self.cache_seconds
            and not self._last.stale
        ):
            return self._last

        try:
            links = collect_links(source=self.source, carrier=self.carrier, timeout=self.timeout)
            self._last = FetchResult(
                links=links,
                generated_at=time.time(),
                source=self.source,
                carrier=self.carrier,
            )
            return self._last
        except Exception as exc:
            if self._last is not None and self._last.links:
                return FetchResult(
                    links=self._last.links,
                    generated_at=self._last.generated_at,
                    source=self.source,
                    carrier=self.carrier,
                    stale=True,
                    error=str(exc),
                )
            raise


def parse_bind(bind: str) -> tuple[str, int]:
    host, sep, port_text = bind.rpartition(":")
    if not sep:
        return "127.0.0.1", int(bind)
    return host or "127.0.0.1", int(port_text)


def make_handler(cache: SubscriptionCache) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "MahsaNGDesktopBridge/1.4"

        def _send_text(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8", extra: dict[str, str] | None = None) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.send_header("Content-Length", str(len(data)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            path = self.path.split("?", 1)[0]
            try:
                if path in ("/health", "/debug"):
                    force_refresh = path == "/debug"
                    result = cache.get(force=force_refresh)
                    body = json.dumps(
                        {
                            "ok": True,
                            "endpoint": path,
                            "refreshed_now": force_refresh,
                            "links": len(result.links),
                            "payload_hash": result.payload_hash,
                            "payload_hash_short": result.payload_hash[:16],
                            "protocol_counts": result.protocol_counts,
                            "source": result.source,
                            "carrier": result.carrier,
                            "generated_at": result.generated_at,
                            "stale": result.stale,
                            "error": result.error,
                            "note": "source=android tries the live Mahsa dynamic API first, then falls back to Android MAHSA_SUB rotation if the API requires captcha or fails.",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ) + "\n"
                    self._send_text(200, body, "application/json; charset=utf-8")
                    return

                if path not in ("/", "/sub", "/links", "/json"):
                    self._send_text(404, "Use /sub, /links, /json, /health, or /debug\n")
                    return

                # Client subscription update requests must observe the freshest
                # upstream feeds. Cache is only a last-good fallback if refresh
                # fails, not the normal response path for /sub, /links, or /json.
                result = cache.get(force=True)
                output_format: OutputFormat = "base64"
                content_type = "text/plain; charset=utf-8"
                if path == "/links":
                    output_format = "plain"
                elif path == "/json":
                    output_format = "json"
                    content_type = "application/json; charset=utf-8"

                payload = render_payload(result.links, output_format)
                self._send_text(
                    200,
                    payload,
                    content_type,
                    {
                        "X-Mahsa-Link-Count": str(len(result.links)),
                        "X-Mahsa-Stale": "1" if result.stale else "0",
                        "X-Mahsa-Generated-At": str(result.generated_at),
                    },
                )
            except Exception as exc:
                self._send_text(500, f"error: {exc}\n")

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[{self.log_date_time_string()}] {format % args}", file=sys.stderr)

    return Handler


def serve(bind: str, source: Source, carrier: Carrier, timeout: int, cache_seconds: int) -> None:
    host, port = parse_bind(bind)
    cache = BridgeCache(source=source, carrier=carrier, timeout=timeout, cache_seconds=cache_seconds)
    httpd = ThreadingHTTPServer((host, port), make_handler(cache))
    print(f"MahsaNG Desktop Bridge listening on http://{host}:{port}/sub", file=sys.stderr)
    print(f"Plain links: http://{host}:{port}/links", file=sys.stderr)
    print(f"Health:      http://{host}:{port}/health", file=sys.stderr)
    httpd.serve_forever()


def write_or_print(payload: str, output_path: str | None) -> None:
    if output_path:
        path = Path(output_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload, encoding="utf-8")
    else:
        sys.stdout.write(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MahsaNG encrypted feed decoder and local desktop subscription bridge")
    parser.add_argument(
        "--source",
        choices=("android", "dynamic", "all", "free", "ems"),
        default="android",
        help="android=dynamic Mahsa API first, then Android MAHSA_SUB rotation; dynamic=only live backend",
    )
    parser.add_argument("--carrier", choices=("all", "mtn", "mci"), default="all", help="Carrier filter for MahsaFreeConfig")
    parser.add_argument("--format", choices=("base64", "plain", "json"), default="base64")
    parser.add_argument("-o", "--output", help="Write subscription payload to a file")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--cache-seconds", type=int, default=DEFAULT_CACHE_SECONDS)
    parser.add_argument("--serve", nargs="?", const=DEFAULT_BIND, help="Serve a local/LAN subscription URL, optionally HOST:PORT")
    args = parser.parse_args(argv)

    if args.serve:
        serve(
            bind=args.serve,
            source=args.source,  # type: ignore[arg-type]
            carrier=args.carrier,  # type: ignore[arg-type]
            timeout=args.timeout,
            cache_seconds=args.cache_seconds,
        )
        return 0

    links = collect_links(source=args.source, carrier=args.carrier, timeout=args.timeout)  # type: ignore[arg-type]
    payload = render_payload(links, args.format)  # type: ignore[arg-type]
    write_or_print(payload, args.output)
    print(f"decoded {len(links)} unique links", file=sys.stderr)
    print(json.dumps({"protocol_counts": {proto: sum(link.startswith(proto) for link in links) for proto in PROTOCOLS}}, indent=2), file=sys.stderr)
    if args.output:
        print(f"wrote {args.format} payload to {Path(args.output).expanduser()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
