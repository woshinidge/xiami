from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory
import threading

from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.market import (
    PluginMarketItem,
    download_market_package,
    format_market_items,
    market_install_decision,
    scan_local_market,
)
from xiami_core.plugins.packages import export_plugin_package
from xiami_core.plugins.signing import RSA_SHA256_DIGEST_INFO_PREFIX, signature_payload
from xiami_core.plugins.state import PluginStateStore


class PackageHandler(BaseHTTPRequestHandler):
    package_bytes: bytes = b""

    def do_GET(self) -> None:
        if self.path != "/remote_only.xiami-plugin.zip":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Content-Length", str(len(self.package_bytes)))
        self.end_headers()
        self.wfile.write(self.package_bytes)

    def log_message(self, _format: str, *args) -> None:
        return


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        installed_root = root / "installed"
        market_root = root / "market"
        remote_root = root / "remote"
        installed_root.mkdir()
        market_root.mkdir()
        remote_root.mkdir()
        _write_plugin(installed_root / "same" / "plugin.py", "same", "Same Plugin", "1.0.0")
        _write_plugin(installed_root / "older" / "plugin.py", "older", "Older Plugin", "1.0.0")
        _write_plugin(installed_root / "newer" / "plugin.py", "newer", "Newer Plugin", "2.0.0")
        _write_plugin(root / "market_src" / "same" / "plugin.py", "same", "Same Plugin", "1.0.0")
        _write_plugin(root / "market_src" / "older" / "plugin.py", "older", "Older Plugin", "2.0.0")
        _write_plugin(root / "market_src" / "newer" / "plugin.py", "newer", "Newer Plugin", "1.0.0")
        _write_plugin(root / "market_src" / "fresh" / "plugin.py", "fresh", "Fresh Plugin", "0.1.0")
        _write_plugin(root / "market_src" / "manifested" / "plugin.py", "manifested", "Manifested Plugin", "1.2.0")
        _write_plugin(root / "market_src" / "bad_checksum" / "plugin.py", "bad_checksum", "Bad Checksum", "0.2.0")
        _write_plugin(root / "market_src" / "bad_signature" / "plugin.py", "bad_signature", "Bad Signature", "0.3.0")
        _write_plugin(root / "market_src" / "beta_channel" / "plugin.py", "beta_channel", "Beta Channel", "0.4.0")
        _write_plugin(root / "market_src" / "future_only" / "plugin.py", "future_only", "Future Only", "0.5.0")
        _write_plugin(root / "market_src" / "remote_only" / "plugin.py", "remote_only", "Remote Only", "9.9.9")

        for plugin_id in ("same", "older", "newer", "fresh", "manifested", "bad_checksum", "bad_signature", "beta_channel", "future_only"):
            result = export_plugin_package(root / "market_src", plugin_id, market_root)
            if not result.ok:
                raise RuntimeError(result)
        remote_package = export_plugin_package(root / "market_src", "remote_only", remote_root)
        if not remote_package.ok or not remote_package.path:
            raise RuntimeError(remote_package)

        PackageHandler.package_bytes = remote_package.path.read_bytes()
        server = HTTPServer(("127.0.0.1", 0), PackageHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            remote_url = f"http://127.0.0.1:{server.server_address[1]}/remote_only.xiami-plugin.zip"
            _write_manifest(market_root, remote_url, _sha256(remote_package.path))

            loader = PluginLoader(
                installed_root,
                PluginContext(send_fn=lambda _message: None),
                state_store=PluginStateStore(root / "enabled.json"),
            )
            loader.load_all()
            items = scan_local_market(market_root, loader)
            statuses = {item.plugin_id: item.status for item in items}
            expected = {
                "same": "installed",
                "older": "update_available",
                "newer": "downgrade",
                "fresh": "not_installed",
            "manifested": "not_installed",
            "bad_checksum": "not_installed",
            "bad_signature": "not_installed",
            "beta_channel": "not_installed",
            "future_only": "not_installed",
            "remote_only": "not_installed",
        }
            if statuses != expected:
                raise RuntimeError(f"market statuses failed: {statuses}")
            by_id = {item.plugin_id: item for item in items}
            if by_id["manifested"].source != "manifest" or by_id["manifested"].checksum_status != "ok":
                raise RuntimeError(f"manifest item failed: {by_id['manifested']!r}")
            if by_id["manifested"].signature_status != "ok" or by_id["manifested"].signer != "smoke":
                raise RuntimeError(f"signature verification failed: {by_id['manifested']!r}")
            if by_id["bad_checksum"].checksum_status != "mismatch":
                raise RuntimeError(f"checksum mismatch not detected: {by_id['bad_checksum']!r}")
            if by_id["bad_signature"].signature_status != "invalid":
                raise RuntimeError(f"bad signature not detected: {by_id['bad_signature']!r}")
            if by_id["beta_channel"].channel != "beta":
                raise RuntimeError(f"beta channel not detected: {by_id['beta_channel']!r}")
            if by_id["future_only"].compatibility_status != "incompatible":
                raise RuntimeError(f"future compatibility not detected: {by_id['future_only']!r}")
            if by_id["remote_only"].download_url != remote_url:
                raise RuntimeError(f"remote manifest url failed: {by_id['remote_only']!r}")
            decisions = {plugin_id: market_install_decision(item) for plugin_id, item in by_id.items()}
            if not decisions["fresh"].ok or decisions["fresh"].overwrite:
                raise RuntimeError(f"fresh install decision failed: {decisions['fresh']!r}")
            if not decisions["older"].ok or not decisions["older"].overwrite:
                raise RuntimeError(f"update decision failed: {decisions['older']!r}")
            if decisions["same"].ok or "当前版本" not in decisions["same"].message:
                raise RuntimeError(f"installed decision failed: {decisions['same']!r}")
            if decisions["newer"].ok or "阻止降级" not in decisions["newer"].message:
                raise RuntimeError(f"downgrade decision failed: {decisions['newer']!r}")
            if decisions["bad_signature"].ok or "签名" not in decisions["bad_signature"].message:
                raise RuntimeError(f"bad signature decision failed: {decisions['bad_signature']!r}")
            if decisions["beta_channel"].ok or "更新通道" not in decisions["beta_channel"].message:
                raise RuntimeError(f"beta channel decision failed: {decisions['beta_channel']!r}")
            if decisions["future_only"].ok or "不兼容" not in decisions["future_only"].message:
                raise RuntimeError(f"future compatibility decision failed: {decisions['future_only']!r}")
            unsafe_remote = PluginMarketItem(
                plugin_id="unsafe_remote",
                name="Unsafe Remote",
                version="1.0.0",
                description="",
                package_path=Path(),
                status="not_installed",
                download_url=remote_url,
            )
            if market_install_decision(unsafe_remote).ok:
                raise RuntimeError("remote install without sha256 should be blocked")
            downloaded = download_market_package(by_id["remote_only"], root / "cache", timeout=5)
            if not downloaded.ok or not downloaded.path.is_file() or _sha256(downloaded.path) != _sha256(remote_package.path):
                raise RuntimeError(f"remote download failed: {downloaded}")
            text = format_market_items(items)
            for expected_text in ("Xiami local plugin market", "update_available", "sha256=ok", "signature=ok", "channel=beta", "xiami=incompatible", remote_url):
                if expected_text not in text:
                    raise RuntimeError(f"market format failed: missing {expected_text!r}: {text}")
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()
    print("plugin market smoke ok")
    return 0


def _write_plugin(path: Path, plugin_id: str, name: str, version: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f'PLUGIN_ID = "{plugin_id}"',
                f'PLUGIN_NAME = "{name}"',
                f'PLUGIN_VERSION = "{version}"',
                'PLUGIN_DESCRIPTION = "market smoke plugin"',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_manifest(market_root: Path, remote_url: str, remote_sha256: str) -> None:
    manifested = market_root / "manifested.xiami-plugin.zip"
    manifested_sha256 = _sha256(manifested)
    bad_signature = market_root / "bad_signature.xiami-plugin.zip"
    bad_signature_sha256 = _sha256(bad_signature)
    rsa_key = _rsa_test_key()
    manifest = {
        "trusted_signers": {
            "smoke": {
                "algorithm": "rsa-sha256",
                "n": f"{rsa_key['n']:x}",
                "e": str(rsa_key["e"]),
            }
        },
        "plugins": [
            {
                "id": "manifested",
                "name": "Manifested Plugin",
                "version": "1.2.0",
                "description": "manifest metadata wins",
                "package": manifested.name,
                "sha256": manifested_sha256,
                "signature": {
                    "algorithm": "rsa-sha256",
                    "key_id": "smoke",
                    "value": _rsa_sign_sha256(rsa_key, signature_payload(manifested_sha256)),
                },
                "homepage": "https://example.invalid/manifested",
                "release_notes": "manifest smoke",
            },
            {
                "id": "bad_checksum",
                "name": "Bad Checksum",
                "version": "0.2.0",
                "package": "bad_checksum.xiami-plugin.zip",
                "sha256": "0" * 64,
            },
            {
                "id": "bad_signature",
                "name": "Bad Signature",
                "version": "0.3.0",
                "package": bad_signature.name,
                "sha256": bad_signature_sha256,
                "signature": {
                    "algorithm": "rsa-sha256",
                    "key_id": "smoke",
                    "value": "AA",
                },
            },
            {
                "id": "beta_channel",
                "name": "Beta Channel",
                "version": "0.4.0",
                "package": "beta_channel.xiami-plugin.zip",
                "sha256": _sha256(market_root / "beta_channel.xiami-plugin.zip"),
                "channel": "beta",
            },
            {
                "id": "future_only",
                "name": "Future Only",
                "version": "0.5.0",
                "package": "future_only.xiami-plugin.zip",
                "sha256": _sha256(market_root / "future_only.xiami-plugin.zip"),
                "min_xiami_version": "9.0.0",
            },
            {
                "id": "remote_only",
                "name": "Remote Only",
                "version": "9.9.9",
                "url": remote_url,
                "sha256": remote_sha256,
            },
        ]
    }
    (market_root / "xiami-market.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rsa_test_key() -> dict[str, int]:
    rng = random.Random(20260629)
    public_exponent = 65537
    while True:
        p = _random_prime(rng)
        q = _random_prime(rng)
        if p == q:
            continue
        phi = (p - 1) * (q - 1)
        if phi % public_exponent:
            return {
                "n": p * q,
                "e": public_exponent,
                "d": pow(public_exponent, -1, phi),
            }


def _rsa_sign_sha256(key: dict[str, int], payload: str) -> str:
    digest_info = RSA_SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload.encode("utf-8")).digest()
    key_size = (key["n"].bit_length() + 7) // 8
    padding_size = key_size - len(digest_info) - 3
    if padding_size < 8:
        raise RuntimeError("test RSA key is too small")
    encoded = b"\x00\x01" + b"\xff" * padding_size + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), key["d"], key["n"]).to_bytes(key_size, "big")
    return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


def _random_prime(rng: random.Random) -> int:
    while True:
        candidate = rng.getrandbits(256) | (1 << 255) | 1
        if _is_probable_prime(candidate):
            return candidate


def _is_probable_prime(value: int) -> bool:
    small_primes = (3, 5, 7, 11, 13, 17, 19, 23, 29, 31)
    if value < 2 or value % 2 == 0:
        return value == 2
    for prime in small_primes:
        if value == prime:
            return True
        if value % prime == 0:
            return False
    d = value - 1
    shifts = 0
    while d % 2 == 0:
        shifts += 1
        d //= 2
    for base in (2, 3, 5, 7, 11, 13, 17):
        if base >= value:
            continue
        x = pow(base, d, value)
        if x in {1, value - 1}:
            continue
        for _ in range(shifts - 1):
            x = pow(x, 2, value)
            if x == value - 1:
                break
        else:
            return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
