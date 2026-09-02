from __future__ import annotations

import base64
import math
import os
import random
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import toolbox_update as update


def _is_probable_prime(value: int) -> bool:
    if value < 2:
        return False
    for prime in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
        if value == prime:
            return True
        if value % prime == 0:
            return False
    d = value - 1
    shifts = 0
    while d % 2 == 0:
        shifts += 1
        d //= 2
    for base in (2, 3, 5, 7, 11, 13, 17, 19):
        x = pow(base, d, value)
        if x in (1, value - 1):
            continue
        for _ in range(shifts - 1):
            x = pow(x, 2, value)
            if x == value - 1:
                break
        else:
            return False
    return True


def _prime(rng: random.Random, bits: int, exponent: int) -> int:
    while True:
        value = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if math.gcd(value - 1, exponent) == 1 and _is_probable_prime(value):
            return value


def _probe_keypair():
    rng = random.Random(0x5849414D49)
    exponent = 65537
    p = _prime(rng, 384, exponent)
    q = _prime(rng, 384, exponent)
    while q == p:
        q = _prime(rng, 384, exponent)
    modulus = p * q
    private_exponent = pow(exponent, -1, (p - 1) * (q - 1))
    return modulus, exponent, private_exponent


def _sign(payload: bytes, modulus: int, private_exponent: int) -> str:
    width = (modulus.bit_length() + 7) // 8
    digest_info = update._RSA_SHA256_DIGEST_INFO_PREFIX + update.hashlib.sha256(payload).digest()
    padding_len = width - len(digest_info) - 3
    if padding_len < 8:
        raise AssertionError("probe RSA modulus is too small")
    encoded = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
    signature = pow(int.from_bytes(encoded, "big"), private_exponent, modulus).to_bytes(width, "big")
    return base64.b64encode(signature).decode("ascii")


def _base_manifest() -> dict:
    return {
        "ok": True,
        "schema_version": 1,
        "app": "toolbox",
        "channel": "stable",
        "latest_version": "1.3.8",
        "min_supported_version": "1.3.7",
        "download_url": "https://updates.example.invalid/toolbox-1.3.8.zip",
        "sha256": "ab" * 32,
        "size": 123456,
        "release_notes": "trust probe",
        "published_at": "2026-07-22T00:00:00Z",
        "expires_at": "2099-08-22T00:00:00Z",
    }


def _attach_signature(manifest: dict, modulus: int, private_exponent: int) -> dict:
    result = dict(manifest)
    payload = update.canonical_update_manifest(result, app="toolbox", channel="stable")
    result["manifest_signature"] = {
        "alg": "RS256",
        "key_id": "probe-2026",
        "value": _sign(payload, modulus, private_exponent),
    }
    return result


def main() -> int:
    modulus, exponent, private_exponent = _probe_keypair()
    public_keys = {"probe-2026": {"n": "0x" + format(modulus, "x"), "e": exponent}}

    signed = _attach_signature(_base_manifest(), modulus, private_exponent)
    trusted, status, error = update.validate_update_manifest_trust(
        signed,
        app="toolbox",
        channel="stable",
        public_keys=public_keys,
        require_signature=True,
    )
    assert trusted and status == "verified" and not error, (trusted, status, error)

    tampered = dict(signed)
    tampered["download_url"] = "https://attacker.invalid/replacement.zip"
    trusted, status, _ = update.validate_update_manifest_trust(
        tampered,
        app="toolbox",
        channel="stable",
        public_keys=public_keys,
        require_signature=True,
    )
    assert not trusted and status == "invalid"

    expired_source = _base_manifest()
    expired_source["expires_at"] = "2026-07-21T23:59:59Z"
    expired = _attach_signature(expired_source, modulus, private_exponent)
    trusted, status, replay_error = update.validate_update_manifest_trust(
        expired,
        app="toolbox",
        public_keys=public_keys,
        require_signature=False,
        now_utc=datetime(2026, 7, 22, tzinfo=timezone.utc),
    )
    assert not trusted and status == "expired" and "重放" in replay_error

    no_expiry_source = _base_manifest()
    no_expiry_source.pop("expires_at")
    no_expiry = _attach_signature(no_expiry_source, modulus, private_exponent)
    trusted, status, warning = update.validate_update_manifest_trust(
        no_expiry,
        app="toolbox",
        public_keys=public_keys,
        require_signature=False,
    )
    assert trusted and status == "verified_legacy_expiry" and warning
    trusted, status, _ = update.validate_update_manifest_trust(
        no_expiry,
        app="toolbox",
        public_keys=public_keys,
        require_signature=True,
    )
    assert not trusted and status == "invalid_expiry"

    invalid_expiry_source = _base_manifest()
    invalid_expiry_source["expires_at"] = "2099-08-22T08:00:00+08:00"
    invalid_expiry = _attach_signature(invalid_expiry_source, modulus, private_exponent)
    trusted, status, _ = update.validate_update_manifest_trust(
        invalid_expiry,
        app="toolbox",
        public_keys=public_keys,
        require_signature=False,
    )
    assert trusted and status == "verified_legacy_expiry"
    trusted, status, _ = update.validate_update_manifest_trust(
        invalid_expiry,
        app="toolbox",
        public_keys=public_keys,
        require_signature=True,
    )
    assert not trusted and status == "invalid_expiry"

    utc_offset_source = _base_manifest()
    utc_offset_source["expires_at"] = "2099-08-22T00:00:00+00:00"
    utc_offset_signed = _attach_signature(utc_offset_source, modulus, private_exponent)
    trusted, status, _ = update.validate_update_manifest_trust(
        utc_offset_signed,
        app="toolbox",
        public_keys=public_keys,
        require_signature=True,
    )
    assert trusted and status == "verified"

    zero_size_source = _base_manifest()
    zero_size_source["size"] = 0
    zero_size = _attach_signature(zero_size_source, modulus, private_exponent)
    trusted, status, _ = update.validate_update_manifest_trust(
        zero_size,
        app="toolbox",
        public_keys=public_keys,
        require_signature=False,
    )
    assert not trusted and status == "invalid_size"

    ok, _ = update.validate_update_download_size(100, 100, final=True)
    assert ok
    ok, _ = update.validate_update_download_size(100, 101, final=False)
    assert not ok
    ok, _ = update.validate_update_download_size(100, 99, final=True)
    assert not ok
    ok, _ = update.validate_update_download_size(
        0,
        update.MAX_UPDATE_DOWNLOAD_BYTES + 1,
        final=False,
    )
    assert not ok

    version_manifest = _base_manifest()
    version_manifest["latest_version"] = "2.0.0"
    version_manifest["min_supported_version"] = "1.5.0"
    version_ok, below_minimum, _ = update.validate_min_supported_version(version_manifest, "1.4.9")
    assert version_ok and below_minimum
    version_ok, below_minimum, _ = update.validate_min_supported_version(version_manifest, "1.5.0")
    assert version_ok and not below_minimum
    version_manifest["min_supported_version"] = "2.1.0"
    version_ok, _, _ = update.validate_min_supported_version(version_manifest, "1.5.0")
    assert not version_ok

    unsigned = _base_manifest()
    trusted, status, warning = update.validate_update_manifest_trust(
        unsigned,
        app="toolbox",
        require_signature=False,
    )
    assert trusted and status == "unsigned_legacy" and warning
    trusted, status, _ = update.validate_update_manifest_trust(
        unsigned,
        app="toolbox",
        require_signature=True,
    )
    assert not trusted and status == "unsigned"
    assert update.UPDATE_MANIFEST_PUBLIC_KEYS
    os.environ.pop("XIAMI_UPDATE_ALLOW_DEV_TRUST_KEYS", None)
    os.environ["XIAMI_UPDATE_MANIFEST_SIGNATURE_MODE"] = "compat"
    try:
        assert update._manifest_signature_required("toolbox")
    finally:
        os.environ.pop("XIAMI_UPDATE_MANIFEST_SIGNATURE_MODE", None)

    ok, _ = update.validate_update_transport_url(
        "http://updates.example.invalid/toolbox.zip",
        allow_local_http=False,
        allow_file=False,
    )
    assert not ok
    ok, _ = update.validate_update_transport_url(
        "http://127.0.0.1:18080/toolbox.zip",
        allow_local_http=True,
        allow_file=False,
    )
    assert ok
    ok, _ = update.validate_update_transport_url(
        "file:///C:/temp/toolbox.zip",
        allow_local_http=False,
        allow_file=False,
    )
    assert not ok
    ok, _ = update.validate_update_transport_url(
        "file:///C:/temp/toolbox.zip",
        allow_local_http=False,
        allow_file=True,
    )
    assert ok

    keep_files, keep_dirs = update.update_keep_paths("toolbox")
    forbidden_files = {
        "工具箱_qt.py",
        "toolbox_update.py",
        "工具箱_qt.bootstrap_backup.py",
    }
    forbidden_dirs = {"Website", "resources", "tools", "source_backups"}
    assert forbidden_files.isdisjoint(set(keep_files))
    assert forbidden_dirs.isdisjoint(set(keep_dirs))
    pre_keep, post_keep = update.build_keep_commands(keep_files, keep_dirs)
    keep_commands = "\n".join(pre_keep + post_keep)
    for forbidden in sorted(forbidden_files | forbidden_dirs):
        assert forbidden not in keep_commands, forbidden
    for required in (
        "toolbox_login.json",
        "toolbox_size_preferences.json",
        "micro_client_configs.json",
        "微端配置目录",
        "存销系统配置.json",
    ):
        assert required in keep_commands, required

    print("PASS valid_signature")
    print("PASS tampered_manifest_rejected")
    print("PASS expired_signed_manifest_replay_rejected")
    print("PASS expiry_compat_and_required_modes")
    print("PASS declared_size_stream_and_completion_limits")
    print("PASS minimum_supported_version_policy")
    print("PASS unsigned_compat_and_required_modes")
    print("PASS production_trust_root_cannot_be_downgraded_by_policy")
    print("PASS remote_http_rejected")
    print("PASS explicit_localhost_and_file_dev_exceptions")
    print("PASS update_keep_rules_preserve_data_not_code")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
