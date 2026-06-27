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
import hashlib
import json
import re
import random
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Literal, Protocol

try:
    from cryptography.hazmat.primitives import padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
except Exception as exc:
    raise SystemExit(
        "Missing Python dependency: cryptography\n"
        "Install it with:\n"
        "  python3 -m pip install cryptography"
    ) from exc

Source = Literal["all", "free", "ems"]
Carrier = Literal["all", "mtn", "mci"]
OutputFormat = Literal["base64", "plain", "json"]

FREE_URL = "https://raw.githubusercontent.com/mahsanet/MahsaFreeConfig/main/app/sub.txt"
EMS_URL = "https://raw.githubusercontent.com/GFW-knocker/MahsaNG/master/mahsa_EMS_accounts.json"

FREE_IV = "lvcas56410c97lpb"       # APK q/c
EMS_IV = "Xvc1wOrxs77Ilj0N"        # APK q/e
FREE_KEY_SEED = "mvcfhjju5632gfsseu95642yhfhnhjhty68532gfg"
EMS_KEY_SEED = "aassddy734321thjmvbxcdgtt67i7kmghddfhfdxb"

PROTOCOLS = ("vless://", "vmess://", "trojan://", "ss://")
ANDROID_FREE_ROTATION_LIMIT = 10
USER_AGENT = "MahsaNG-Desktop-Bridge/1.3"
DEFAULT_CACHE_SECONDS = 300
DEFAULT_TIMEOUT_SECONDS = 12


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
        except (TimeoutError, ssl.SSLError, urllib.error.URLError, OSError) as exc:
            errors.append(f"attempt {attempt + 1}: {type(exc).__name__}: {exc}")
            if attempt == 0:
                time.sleep(0.25)
                continue
            raise RuntimeError(f"fetch failed for {url}: {'; '.join(errors)}") from exc
    raise RuntimeError(f"fetch failed for {url}")


def aes_cbc_decrypt_base64(ciphertext_b64: str, key: str, iv: str) -> str:
    raw = base64.b64decode("".join(ciphertext_b64.split()))
    decryptor = Cipher(algorithms.AES(key.encode("utf-8")), modes.CBC(iv.encode("utf-8"))).decryptor()
    padded = decryptor.update(raw) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    plain = unpadder.update(padded) + unpadder.finalize()
    return plain.decode("utf-8")


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

    return apply_android_rotation(raw_links)


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


def collect_links(source: Source = "all", carrier: Carrier = "all", timeout: int = DEFAULT_TIMEOUT_SECONDS) -> list[str]:
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
        server_version = "MahsaNGDesktopBridge/1.3"

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
                            "note": "Payload changes only when the upstream GitHub feeds change; generated_at changes on each forced refresh.",
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
    parser.add_argument("--source", choices=("all", "free", "ems"), default="all")
    parser.add_argument("--carrier", choices=("all", "mtn", "mci"), default="all", help="Carrier filter for MahsaFreeConfig")
    parser.add_argument("--format", choices=("base64", "plain", "json"), default="base64")
    parser.add_argument("-o", "--output", help="Write subscription payload to a file")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--cache-seconds", type=int, default=DEFAULT_CACHE_SECONDS)
    parser.add_argument("--serve", nargs="?", const="127.0.0.1:18080", help="Serve a local subscription URL, optionally HOST:PORT")
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
