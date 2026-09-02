from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


TRUSTED_SIGNER_FILES = ("xiami-trusted-signers.json", "trusted-signers.json")
SIGNATURE_PAYLOAD_PREFIX = "xiami-plugin-package-sha256:"
RSA_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")


@dataclass(frozen=True)
class SignatureCheck:
    status: str
    key_id: str = ""
    algorithm: str = ""
    signature: str = ""
    required: bool = False
    message: str = ""


def signature_payload(package_sha256: str) -> str:
    return f"{SIGNATURE_PAYLOAD_PREFIX}{package_sha256.strip().lower()}"


def manifest_signature_required(manifest: dict[str, Any]) -> bool:
    policy = manifest.get("signature_policy")
    if isinstance(policy, dict):
        return bool(policy.get("require_signature") or policy.get("required"))
    return bool(manifest.get("require_signature"))


def load_trusted_signers(package_dir: Path, manifest: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    signers: dict[str, dict[str, str]] = {}
    for name in TRUSTED_SIGNER_FILES:
        path = package_dir / name
        if path.is_file():
            signers.update(_parse_signers(_read_json(path)))
    if manifest:
        # Local/offline markets may keep their trust anchor beside package metadata.
        # A separate trusted-signers file is preferred for real distribution.
        signers.update(_parse_signers(manifest.get("trusted_signers")))
    return signers


def check_package_signature(
    entry: dict[str, Any],
    *,
    package_path: Path,
    expected_sha256: str,
    trusted_signers: dict[str, dict[str, str]],
    required: bool,
) -> SignatureCheck:
    algorithm, key_id, signature = _signature_parts(entry)
    if not signature:
        status = "missing" if required else "unsigned"
        return SignatureCheck(status=status, required=required, message="插件包未签名。")
    algorithm = (algorithm or "rsa-sha256").lower()
    if algorithm != "rsa-sha256":
        return SignatureCheck("unsupported", key_id, algorithm, signature, required, "不支持的签名算法。")
    if not key_id:
        return SignatureCheck("untrusted", key_id, algorithm, signature, required, "签名缺少 key_id。")
    public_key = trusted_signers.get(key_id)
    if not public_key:
        return SignatureCheck("untrusted", key_id, algorithm, signature, required, "签名者不在信任列表。")
    package_sha256 = expected_sha256.strip().lower()
    if not package_sha256 and package_path.is_file():
        package_sha256 = _sha256_file(package_path)
    if not package_sha256:
        return SignatureCheck("pending", key_id, algorithm, signature, required, "缺少包 sha256，暂不能验签。")
    payload = signature_payload(package_sha256)
    if _verify_rsa_sha256(public_key, payload, signature):
        return SignatureCheck("ok", key_id, algorithm, signature, required, "插件包签名有效。")
    return SignatureCheck("invalid", key_id, algorithm, signature, required, "插件包签名无效。")


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return {}


def _parse_signers(raw: Any) -> dict[str, dict[str, str]]:
    if isinstance(raw, dict) and "signers" in raw:
        raw = raw.get("signers")
    result: dict[str, dict[str, str]] = {}
    if isinstance(raw, dict):
        for key_id, signer in raw.items():
            if isinstance(signer, dict):
                normalized = _normalize_signer(str(key_id), signer)
                if normalized:
                    result[normalized["key_id"]] = normalized
    elif isinstance(raw, list):
        for signer in raw:
            if isinstance(signer, dict):
                normalized = _normalize_signer("", signer)
                if normalized:
                    result[normalized["key_id"]] = normalized
    return result


def _normalize_signer(default_key_id: str, raw: dict[str, Any]) -> dict[str, str]:
    key_id = str(raw.get("key_id") or raw.get("id") or raw.get("name") or default_key_id).strip()
    algorithm = str(raw.get("algorithm") or raw.get("alg") or "rsa-sha256").strip().lower()
    modulus = str(raw.get("n") or raw.get("modulus") or raw.get("n_hex") or "").strip()
    exponent = str(raw.get("e") or raw.get("exponent") or "65537").strip()
    if not key_id or algorithm != "rsa-sha256" or not modulus:
        return {}
    return {"key_id": key_id, "algorithm": algorithm, "n": modulus, "e": exponent}


def _signature_parts(entry: dict[str, Any]) -> tuple[str, str, str]:
    value = entry.get("signature") or entry.get("sig")
    if isinstance(value, dict):
        algorithm = str(value.get("algorithm") or value.get("alg") or "rsa-sha256").strip()
        key_id = str(value.get("key_id") or value.get("signer") or value.get("signer_id") or "").strip()
        signature = str(value.get("value") or value.get("signature") or value.get("sig") or "").strip()
        return algorithm, key_id, signature
    if value is None:
        return "", "", ""
    text = str(value).strip()
    parts = text.split(":", 2)
    if len(parts) == 3:
        return parts[0].strip(), parts[1].strip(), parts[2].strip()
    key_id = str(entry.get("key_id") or entry.get("signer") or entry.get("signer_id") or "").strip()
    algorithm = str(entry.get("signature_algorithm") or entry.get("alg") or "rsa-sha256").strip()
    return algorithm, key_id, text


def _verify_rsa_sha256(public_key: dict[str, str], payload: str, signature: str) -> bool:
    try:
        modulus = _modulus_from_text(public_key["n"])
        exponent = int(str(public_key.get("e") or "65537"), 0)
        signature_bytes = _decode_base64(signature)
    except (KeyError, ValueError, TypeError):
        return False
    if modulus <= 0 or exponent <= 1 or not signature_bytes:
        return False
    key_size = (modulus.bit_length() + 7) // 8
    signature_int = int.from_bytes(signature_bytes, "big")
    if signature_int >= modulus:
        return False
    encoded = pow(signature_int, exponent, modulus).to_bytes(key_size, "big")
    digest_info = RSA_SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload.encode("utf-8")).digest()
    if len(encoded) < len(digest_info) + 11 or not encoded.startswith(b"\x00\x01"):
        return False
    try:
        separator = encoded.index(b"\x00", 2)
    except ValueError:
        return False
    padding = encoded[2:separator]
    return len(padding) >= 8 and all(byte == 0xFF for byte in padding) and encoded[separator + 1 :] == digest_info


def _modulus_from_text(value: str) -> int:
    text = value.strip()
    if text.startswith("0x"):
        return int(text, 16)
    if all(ch in "0123456789abcdefABCDEF:" for ch in text):
        return int(text.replace(":", ""), 16)
    return int.from_bytes(_decode_base64(text), "big")


def _decode_base64(value: str) -> bytes:
    text = value.strip()
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode((text + padding).encode("ascii"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
