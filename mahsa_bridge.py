#!/usr/bin/env python3
"""
MahsaNG macOS Bridge

Local subscription bridge for MahsaNG/MahsaFreeConfig encrypted feeds.
It fetches live encrypted feeds, decrypts them using the same AES-CBC schemes
found in the official MahsaNG Android APK, and serves standard V2Ray-style
subscriptions for macOS clients.

Routes when serving:
  /sub    -> base64 newline-separated subscription payload
  /links  -> plain newline-separated links
  /json   -> JSON array of links
  /health -> JSON status
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Iterable, Literal

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
USER_AGENT = "MahsaNG-macOS-Bridge/1.0"
DEFAULT_CACHE_SECONDS = 300


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


def md5_hex(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest().zfill(32)


def free_key() -> str:
    digest = md5_hex(FREE_KEY_SEED)
    return digest[0:7] + digest[10:19]


def ems_key() -> str:
    digest = md5_hex(EMS_KEY_SEED)
    return digest[8:14] + digest[20:30]


def fetch_text(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except (ssl.SSLError, urllib.error.URLError) as exc:
        # Some macOS Python builds do not have a usable cert bundle. Retry without
        # TLS verification so the bridge still works. This is a public feed; the
        # decoded links are not credentials owned by this machine.
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc) and not isinstance(exc, ssl.SSLError):
            raise
        print(f"warning: TLS verification failed for {url}; retrying without verification", file=sys.stderr)
        ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.read().decode("utf-8")


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


def decode_free(carrier: Carrier = "all", timeout: int = 30) -> list[str]:
    encrypted = fetch_text(FREE_URL, timeout=timeout).strip()
    plain = aes_cbc_decrypt_base64(encrypted, free_key(), FREE_IV)
    data = json.loads(plain)
    if not isinstance(data, dict):
        raise ValueError("MahsaFreeConfig payload is not a JSON object")

    carriers = ["mtn", "mci"] if carrier == "all" else [carrier]
    links: list[str] = []
    for name in carriers:
        entries = data.get(name, [])
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and valid_link(entry.get("config")):
                links.append(entry["config"].strip())
    return links


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


def collect_links(source: Source = "all", carrier: Carrier = "all", timeout: int = 30) -> list[str]:
    links: list[str] = []
    if source in ("all", "free"):
        links.extend(decode_free(carrier=carrier, timeout=timeout))
    if source in ("all", "ems"):
        links.extend(decode_ems(timeout=timeout))
    return dedupe_keep_order(links)


def render_payload(links: list[str], output_format: OutputFormat) -> str:
    plain = "\n".join(links) + ("\n" if links else "")
    if output_format == "plain":
        return plain
    if output_format == "base64":
        return base64.b64encode(plain.encode("utf-8")).decode("ascii") + "\n"
    if output_format == "json":
        return json.dumps(links, ensure_ascii=False, indent=2) + "\n"
    raise ValueError(f"Unsupported output format: {output_format}")


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


def serve(bind: str, source: Source, carrier: Carrier, timeout: int, cache_seconds: int) -> None:
    host, port = parse_bind(bind)
    cache = BridgeCache(source=source, carrier=carrier, timeout=timeout, cache_seconds=cache_seconds)

    class Handler(BaseHTTPRequestHandler):
        server_version = "MahsaNGMacBridge/1.0"

        def _send_text(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8", extra: dict[str, str] | None = None) -> None:
            data = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
            path = self.path.split("?", 1)[0]
            try:
                if path == "/health":
                    result = cache.get(force=False)
                    body = json.dumps(
                        {
                            "ok": True,
                            "links": len(result.links),
                            "protocol_counts": result.protocol_counts,
                            "source": result.source,
                            "carrier": result.carrier,
                            "generated_at": result.generated_at,
                            "stale": result.stale,
                            "error": result.error,
                        },
                        ensure_ascii=False,
                        indent=2,
                    ) + "\n"
                    self._send_text(200, body, "application/json; charset=utf-8")
                    return

                if path not in ("/", "/sub", "/links", "/json"):
                    self._send_text(404, "Use /sub, /links, /json, or /health\n")
                    return

                result = cache.get(force=False)
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
                    },
                )
            except Exception as exc:
                self._send_text(500, f"error: {exc}\n")

        def log_message(self, format: str, *args: Any) -> None:
            print(f"[{self.log_date_time_string()}] {format % args}", file=sys.stderr)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"MahsaNG macOS Bridge listening on http://{host}:{port}/sub", file=sys.stderr)
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
    parser = argparse.ArgumentParser(description="MahsaNG encrypted feed decoder and local macOS subscription bridge")
    parser.add_argument("--source", choices=("all", "free", "ems"), default="all")
    parser.add_argument("--carrier", choices=("all", "mtn", "mci"), default="all", help="Carrier filter for MahsaFreeConfig")
    parser.add_argument("--format", choices=("base64", "plain", "json"), default="base64")
    parser.add_argument("-o", "--output", help="Write subscription payload to a file")
    parser.add_argument("--timeout", type=int, default=30)
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
