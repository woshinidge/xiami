from __future__ import annotations

import base64
import hashlib
import hmac
import http.client
import ipaddress
import json
import math
import os
import re
import secrets
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from toolbox_backend_tls import (
    BackendTransportPolicyError,
    build_backend_opener,
    normalize_backend_url,
)


CAPABILITY_FORMAT = 1
CAPABILITY_ENDPOINT_PATH = "/api/v2/capabilities"
CAPABILITY_ISSUER = "xiami-auth-backend"
CAPABILITY_AUDIENCE = "xiami-toolbox-core"
CAPABILITY_APP = "toolbox"
CAPABILITY_CLAIMS_SCHEMA_VERSION = 1
CAPABILITY_SIGNATURE_CONTEXT = b"XIAMI-CAPABILITY-V1\x00"
RPC_CAPABILITY_FORMAT = 2
RPC_CAPABILITY_CLAIMS_SCHEMA_VERSION = 2
RPC_CAPABILITY_PURPOSE = "rpc"
RPC_CAPABILITY_SIGNATURE_CONTEXT = b"XIAMI-CAPABILITY-V2-RPC\x00"
CAPABILITY_SESSION_CONTEXT = b"XIAMI-CAP-SESSION-V1\x00"
CAPABILITY_DEVICE_CONTEXT = b"XIAMI-CAP-DEVICE-V1\x00"

DEFAULT_REQUEST_TIMEOUT_SECONDS = 8.0
MAX_REQUEST_TIMEOUT_SECONDS = 30.0
MAX_CAPABILITY_RESPONSE_BYTES = 16 * 1024
MAX_CAPABILITY_PAYLOAD_BYTES = 8 * 1024
DEFAULT_CLOCK_SKEW_SECONDS = 30
MAX_CLOCK_SKEW_SECONDS = 120
MAX_CAPABILITY_TTL_SECONDS = 900

KNOWN_CAPABILITY_FEATURES = frozenset(
    {
        "micro.pak.encrypt",
        "cdk.generate",
        "drop.optimize",
        "npc.visual.parse",
        "spawn.visual.edit",
        "store.settings",
        "script.inject",
        "item.inject",
        "recycle.generate",
    }
)

# This trust root is deliberately independent from UPDATE_MANIFEST_PUBLIC_KEYS.
# A writable bootstrap/config file must never be able to replace it in normal
# production mode. Development keys require both an explicit API switch and a
# separate environment opt-in.
CAPABILITY_PUBLIC_KEYS: Dict[str, Dict[str, Any]] = {
    "1cd8407399b1c949": {
        "n": (
            "0xab4dfc61d603567a195947b69e92ded937bd02774c15f3dd9065275ebffca099"
            "af1a5682de498271d84748636471fd1e5e8fb9651e0556b25aaf3ef1fe75fb0a"
            "4b93329972fd6bcad6c514b4162c801964ff58aabe046bcc73d940c1f9096cac"
            "97b9cc5df5f2b2c31509a65eb783584605552d541750a05a6c7e16e6f2c71e"
            "fed1bf91efcede502f140c10b179527fa8c7859a7602f4040baedeec0f451bdb"
            "e625ba8a241ec6f2c066f88b152298d7a2362e18aa7842467b4a45bde78f209"
            "ca02a6f036556803e15534fe75655f65e7ddbf2ba605010717cad025ea18560d"
            "53d4d5ca6a22e6b0be1faf65ab7e1550376173b4ce776b1cc121db6131bba18"
            "e950c0a42aa09fddb0ecf156912e6e0569f82d667b0dcfbe1b3eba4c85347ea"
            "41db3eaeeaf179dabe5f0d02b8b12c935e3074d5c1b50d420356176b67a3232"
            "867ee6a7d92ab724160bde16376604fa0c262456ef580c82810cbfae72d1cc24"
            "041b460715e69c9654aa13203fe98972a08d8f98b7bbe7a9fc0f0eaebb62aa75"
            "412a0d"
        ),
        "e": 65537,
    }
}

_FEATURE_RE = re.compile(r"^[a-z][a-z0-9.]{2,63}$")
_VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+\-]{0,63}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._-]{4,64}$")
_DEVICE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_RPC_PATH_RE = re.compile(r"^/api/v2/rpc/[a-z0-9][a-z0-9./-]{2,127}$")
_RSA_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")
_SIGNED_CLAIM_KEYS = frozenset(
    {
        "iss",
        "aud",
        "schema_version",
        "sub",
        "app",
        "feature",
        "client_version",
        "device_hash",
        "nonce",
        "iat",
        "nbf",
        "exp",
        "jti",
        "auth_version",
        "session_hash",
    }
)
_RPC_SIGNED_CLAIM_KEYS = frozenset(
    set(_SIGNED_CLAIM_KEYS)
    | {
        "purpose",
        "request_sha256",
        "rpc_path",
    }
)


class CapabilityError(Exception):
    """Base exception with a stable machine-readable failure code."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "capability_error",
        http_status: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(str(message or "Capability request failed"))
        self.code = str(code or "capability_error")
        self.http_status = http_status
        self.retryable = bool(retryable)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "http_status": self.http_status,
            "retryable": self.retryable,
        }


class CapabilityConfigurationError(CapabilityError):
    pass


class CapabilityTransportError(CapabilityError):
    pass


class CapabilityAuthorizationError(CapabilityError):
    pass


class CapabilityProtocolError(CapabilityError):
    pass


class CapabilityTrustError(CapabilityError):
    pass


class CapabilityClaimError(CapabilityError):
    pass


@dataclass(frozen=True)
class VerifiedCapability:
    envelope: Dict[str, Any]
    claims: Dict[str, Any]
    key_id: str
    canonical_payload: bytes

    @property
    def expires_at(self) -> int:
        return int(self.claims["exp"])

    def to_json(self) -> str:
        return json.dumps(
            self.envelope,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.environ.get(name, "") or "").strip().lower()
    if not value:
        return bool(default)
    return value in {"1", "true", "yes", "on", "enable", "enabled"}


def _is_loopback_host(host: str) -> bool:
    value = str(host or "").strip().strip("[]").lower()
    if value == "localhost":
        return True
    try:
        return bool(ipaddress.ip_address(value).is_loopback)
    except Exception:
        return False


def validate_capability_transport_url(
    url: str,
    *,
    allow_local_http: bool = False,
) -> Tuple[bool, str]:
    try:
        parsed = urllib.parse.urlsplit(str(url or "").strip())
    except Exception:
        return False, "Capability endpoint URL is invalid"
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        return False, "Capability endpoint must have a host and no URL credentials"
    if parsed.query or parsed.fragment:
        return False, "Capability endpoint must not contain a query or fragment"
    scheme = str(parsed.scheme or "").lower()
    if scheme == "https":
        return True, ""
    if scheme == "http" and bool(allow_local_http) and _is_loopback_host(parsed.hostname):
        return True, ""
    if scheme == "http":
        return False, "Remote capability requests require HTTPS"
    return False, "Capability endpoint only supports HTTPS; loopback HTTP needs explicit development opt-in"


def build_capability_endpoint(
    server_base: str,
    *,
    allow_local_http: bool = False,
) -> str:
    raw = str(server_base or "").strip()
    if not raw:
        raise CapabilityConfigurationError(
            "Capability server URL is empty",
            code="invalid_server_url",
        )
    try:
        raw = normalize_backend_url(raw, allow_local_http=allow_local_http)
    except BackendTransportPolicyError as exc:
        raise CapabilityConfigurationError(str(exc), code="insecure_transport") from exc
    parsed = urllib.parse.urlsplit(raw)
    if parsed.query or parsed.fragment:
        raise CapabilityConfigurationError(
            "Capability server URL must not contain a query or fragment",
            code="invalid_server_url",
        )
    path = str(parsed.path or "").rstrip("/")
    if path != CAPABILITY_ENDPOINT_PATH and not path.endswith(CAPABILITY_ENDPOINT_PATH):
        path = path + CAPABILITY_ENDPOINT_PATH
    endpoint = urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, path, "", "")
    )
    ok, error = validate_capability_transport_url(
        endpoint,
        allow_local_http=allow_local_http,
    )
    if not ok:
        raise CapabilityConfigurationError(error, code="insecure_transport")
    return endpoint


def compute_device_hash(device_id: str) -> str:
    value = str(device_id or "")
    if not value or len(value) > 1024 or any(ord(ch) < 32 for ch in value):
        raise CapabilityConfigurationError(
            "Device identifier is empty or invalid",
            code="invalid_device_id",
        )
    return hashlib.sha256(CAPABILITY_DEVICE_CONTEXT + value.encode("utf-8")).hexdigest()


def _normalize_session_token(session_token: str) -> str:
    if not isinstance(session_token, str):
        raise CapabilityConfigurationError(
            "Session token is empty or invalid",
            code="invalid_session_token",
        )
    token = session_token.strip()
    if not token or len(token) > 4096 or "\r" in token or "\n" in token:
        raise CapabilityConfigurationError(
            "Session token is empty or invalid",
            code="invalid_session_token",
        )
    try:
        token.encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise CapabilityConfigurationError(
            "Session token must be ASCII",
            code="invalid_session_token",
        ) from exc
    return token


def compute_session_hash(session_token: str) -> str:
    token = _normalize_session_token(session_token)
    return hashlib.sha256(CAPABILITY_SESSION_CONTEXT + token.encode("ascii")).hexdigest()


def generate_capability_nonce() -> str:
    return secrets.token_urlsafe(24)


def canonical_capability_payload(claims: Mapping[str, Any]) -> bytes:
    try:
        text = json.dumps(
            dict(claims),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except Exception as exc:
        raise CapabilityProtocolError(
            "Capability claims cannot be canonicalized",
            code="invalid_canonical_payload",
        ) from exc
    return text.encode("utf-8")


def _decode_capability_payload(value: Any) -> bytes:
    if not isinstance(value, str) or not value or len(value) > (MAX_CAPABILITY_PAYLOAD_BYTES * 2):
        raise CapabilityProtocolError(
            "Capability payload encoding is invalid",
            code="invalid_payload_encoding",
        )
    if value != value.strip() or not re.fullmatch(r"[A-Za-z0-9_-]+", value) or len(value) % 4 == 1:
        raise CapabilityProtocolError(
            "Capability payload is not strict unpadded base64url",
            code="invalid_payload_encoding",
        )
    padded = value + ("=" * ((4 - (len(value) % 4)) % 4))
    try:
        decoded = base64.b64decode(padded.encode("ascii"), altchars=b"-_", validate=True)
    except Exception as exc:
        raise CapabilityProtocolError(
            "Capability payload encoding is invalid",
            code="invalid_payload_encoding",
        ) from exc
    if len(decoded) > MAX_CAPABILITY_PAYLOAD_BYTES:
        raise CapabilityProtocolError(
            "Capability payload exceeds the size limit",
            code="payload_too_large",
        )
    normalized = base64.urlsafe_b64encode(decoded).rstrip(b"=").decode("ascii")
    if not hmac.compare_digest(normalized, value):
        raise CapabilityProtocolError(
            "Capability payload encoding is not canonical",
            code="invalid_payload_encoding",
        )
    return decoded


def _parse_rsa_public_number(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("boolean is not an RSA public number")
    if isinstance(value, int):
        return int(value)
    text = str(value or "").strip().lower()
    if not text:
        raise ValueError("empty RSA public number")
    if text.startswith("0x"):
        return int(text, 16)
    if any(char in "abcdef" for char in text):
        return int(text, 16)
    return int(text, 10)


def _verify_rs256_signature(payload: bytes, signature_b64: str, public_key: Mapping[str, Any]) -> bool:
    try:
        modulus = _parse_rsa_public_number(public_key.get("n"))
        exponent = _parse_rsa_public_number(public_key.get("e", 65537))
        if modulus.bit_length() < 2048 or exponent < 3 or exponent % 2 == 0:
            return False
        signature = base64.b64decode(str(signature_b64 or "").encode("ascii"), validate=True)
        width = (modulus.bit_length() + 7) // 8
        if len(signature) != width:
            return False
        encoded = pow(int.from_bytes(signature, "big"), exponent, modulus).to_bytes(width, "big")
        digest_info = _RSA_SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload).digest()
        padding_len = width - len(digest_info) - 3
        if padding_len < 8:
            return False
        expected = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
        return hmac.compare_digest(encoded, expected)
    except Exception:
        return False


def _validate_public_key_map(source: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(source, dict):
        raise CapabilityConfigurationError(
            "Capability public key map is invalid",
            code="invalid_public_keys",
        )
    result: Dict[str, Dict[str, Any]] = {}
    for key_id, public_key in source.items():
        normalized_id = str(key_id or "").strip()
        if not _KEY_ID_RE.fullmatch(normalized_id) or not isinstance(public_key, dict):
            raise CapabilityConfigurationError(
                "Capability public key entry is invalid",
                code="invalid_public_keys",
            )
        try:
            modulus = _parse_rsa_public_number(public_key.get("n"))
            exponent = _parse_rsa_public_number(public_key.get("e", 65537))
        except Exception as exc:
            raise CapabilityConfigurationError(
                "Capability public key entry is invalid",
                code="invalid_public_keys",
            ) from exc
        if modulus.bit_length() < 2048 or exponent < 3 or exponent % 2 == 0:
            raise CapabilityConfigurationError(
                "Capability public key does not meet the minimum strength",
                code="weak_public_key",
            )
        result[normalized_id] = {"n": modulus, "e": exponent}
    return result


def load_capability_public_keys(*, allow_dev_trust_keys: bool = False) -> Dict[str, Dict[str, Any]]:
    keys = _validate_public_key_map(dict(CAPABILITY_PUBLIC_KEYS))
    if not allow_dev_trust_keys:
        return keys
    if not _env_bool("XIAMI_CAPABILITY_ALLOW_DEV_TRUST_KEYS", False):
        raise CapabilityConfigurationError(
            "Development capability trust keys were not explicitly enabled",
            code="dev_trust_disabled",
        )
    raw = str(os.environ.get("XIAMI_CAPABILITY_DEV_PUBLIC_KEYS_JSON", "") or "").strip()
    if not raw:
        raise CapabilityConfigurationError(
            "Development capability trust key map is empty",
            code="dev_trust_empty",
        )
    try:
        dev_keys = _validate_public_key_map(json.loads(raw))
    except CapabilityError:
        raise
    except Exception as exc:
        raise CapabilityConfigurationError(
            "Development capability trust key map is invalid",
            code="invalid_dev_public_keys",
        ) from exc
    collision = set(keys).intersection(dev_keys)
    if collision:
        raise CapabilityConfigurationError(
            "Development keys cannot replace a production capability key",
            code="production_key_override",
        )
    keys.update(dev_keys)
    return keys


def _strict_json_loads(raw: bytes) -> Any:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(value):
        raise ValueError("non-finite JSON number")

    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=reject_constant,
        )
    except Exception as exc:
        raise CapabilityProtocolError(
            "Capability server returned invalid JSON",
            code="invalid_json",
        ) from exc


def _validate_request_texts(
    feature: str,
    client_version: str,
    device_hash: str,
    nonce: str,
) -> Tuple[str, str, str, str]:
    normalized_feature = str(feature or "").strip()
    normalized_version = str(client_version or "").strip()
    normalized_device = str(device_hash or "").strip().lower()
    normalized_nonce = str(nonce or "").strip()
    if not _FEATURE_RE.fullmatch(normalized_feature) or normalized_feature not in KNOWN_CAPABILITY_FEATURES:
        raise CapabilityConfigurationError(
            "Unknown or invalid capability feature",
            code="invalid_feature",
        )
    if not _VERSION_RE.fullmatch(normalized_version):
        raise CapabilityConfigurationError(
            "Client version is invalid",
            code="invalid_client_version",
        )
    if not _DEVICE_HASH_RE.fullmatch(normalized_device):
        raise CapabilityConfigurationError(
            "Device hash must be a SHA-256 hexadecimal value",
            code="invalid_device_hash",
        )
    if not _TOKEN_RE.fullmatch(normalized_nonce):
        raise CapabilityConfigurationError(
            "Capability nonce is invalid",
            code="invalid_nonce",
        )
    return normalized_feature, normalized_version, normalized_device, normalized_nonce


def _claim_text(claims: Mapping[str, Any], key: str, *, maximum: int = 128) -> str:
    value = claims.get(key)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise CapabilityClaimError(
            "Capability claim '{}' is invalid".format(key),
            code="invalid_claim",
        )
    if value != value.strip() or any(unicodedata.category(ch).startswith("C") for ch in value):
        raise CapabilityClaimError(
            "Capability claim '{}' is invalid".format(key),
            code="invalid_claim",
        )
    return value


def _validate_expected_subject(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise CapabilityConfigurationError(
            "Expected capability subject is empty or invalid",
            code="invalid_expected_subject",
        )
    if value != value.strip() or any(unicodedata.category(ch).startswith("C") for ch in value):
        raise CapabilityConfigurationError(
            "Expected capability subject is empty or invalid",
            code="invalid_expected_subject",
        )
    return value


def _claim_integer(claims: Mapping[str, Any], key: str) -> int:
    value = claims.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CapabilityClaimError(
            "Capability claim '{}' must be an integer".format(key),
            code="invalid_claim",
        )
    return int(value)


def _verify_signed_capability_claims(
    envelope: Mapping[str, Any],
    *,
    expected_format: int,
    signature_context: bytes,
    signed_claim_keys,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
    allow_dev_trust_keys: bool = False,
) -> Tuple[Dict[str, Any], Dict[str, Any], str, bytes]:
    if not isinstance(envelope, dict) or set(envelope) != {"ok", "capability"}:
        raise CapabilityProtocolError(
            "Capability response envelope is invalid",
            code="invalid_envelope",
        )
    if envelope.get("ok") is not True:
        raise CapabilityAuthorizationError(
            "Capability request was not authorized",
            code="capability_denied",
        )
    capability = envelope.get("capability")
    if not isinstance(capability, dict) or set(capability) != {"format", "payload", "signature"}:
        raise CapabilityProtocolError(
            "Capability object is invalid",
            code="invalid_capability",
        )
    format_version = capability.get("format")
    if type(format_version) is not int or format_version != expected_format:
        raise CapabilityProtocolError(
            "Unsupported capability format",
            code="unsupported_format",
        )
    payload_text = capability.get("payload")
    signature = capability.get("signature")
    if not isinstance(signature, dict) or set(signature) != {"alg", "key_id", "value"}:
        raise CapabilityProtocolError(
            "Capability signature object is invalid",
            code="invalid_signature_object",
        )
    algorithm = signature.get("alg")
    key_id = signature.get("key_id")
    signature_value = signature.get("value")
    if not isinstance(algorithm, str) or not isinstance(key_id, str) or not isinstance(signature_value, str):
        raise CapabilityTrustError(
            "Capability signature parameters are invalid",
            code="invalid_signature",
        )
    if algorithm != "RS256" or not _KEY_ID_RE.fullmatch(key_id) or not signature_value:
        raise CapabilityTrustError(
            "Capability signature parameters are invalid",
            code="invalid_signature",
        )
    key_map = (
        _validate_public_key_map(dict(public_keys))
        if public_keys is not None
        else load_capability_public_keys(allow_dev_trust_keys=allow_dev_trust_keys)
    )
    public_key = key_map.get(key_id)
    if public_key is None:
        raise CapabilityTrustError(
            "Capability was signed by an unknown key",
            code="unknown_key",
        )
    if not isinstance(payload_text, str) or not payload_text or len(payload_text) > (MAX_CAPABILITY_PAYLOAD_BYTES * 2):
        raise CapabilityProtocolError(
            "Capability payload encoding is invalid",
            code="invalid_payload_encoding",
        )
    try:
        payload_ascii = payload_text.encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise CapabilityProtocolError(
            "Capability payload must be ASCII",
            code="invalid_payload_encoding",
        ) from exc
    signed_bytes = signature_context + payload_ascii
    if not _verify_rs256_signature(signed_bytes, signature_value, public_key):
        raise CapabilityTrustError(
            "Capability signature verification failed",
            code="invalid_signature",
        )
    signed_payload = _decode_capability_payload(payload_text)
    claims = _strict_json_loads(signed_payload)
    if not isinstance(claims, dict) or set(claims) != set(signed_claim_keys):
        raise CapabilityProtocolError(
            "Capability claim set is invalid",
            code="invalid_claim_set",
        )
    canonical = canonical_capability_payload(claims)
    if not hmac.compare_digest(canonical, signed_payload):
        raise CapabilityProtocolError(
            "Capability claims payload is not canonical JSON",
            code="noncanonical_payload",
        )
    verified_envelope = {
        "ok": True,
        "capability": {
            "format": format_version,
            "payload": payload_text,
            "signature": dict(signature),
        },
    }
    return verified_envelope, dict(claims), key_id, signed_payload


def _validate_common_bound_claims(
    claims: Mapping[str, Any],
    *,
    expected_schema_version: int,
    expected_feature: str,
    expected_client_version: str,
    expected_device_hash: str,
    expected_nonce: str,
    expected_subject: str,
    session_token: str,
    now: Optional[int],
    clock_skew_seconds: int,
) -> None:
    expected_session_hash = compute_session_hash(session_token)
    issuer = _claim_text(claims, "iss")
    audience = _claim_text(claims, "aud")
    schema_version = _claim_integer(claims, "schema_version")
    subject = _claim_text(claims, "sub")
    app = _claim_text(claims, "app")
    actual_feature = _claim_text(claims, "feature")
    actual_version = _claim_text(claims, "client_version")
    actual_device_raw = _claim_text(claims, "device_hash")
    actual_device = actual_device_raw.lower()
    actual_nonce = _claim_text(claims, "nonce")
    jti = _claim_text(claims, "jti")
    actual_session_hash_raw = _claim_text(claims, "session_hash")
    actual_session_hash = actual_session_hash_raw.lower()
    if (
        issuer != CAPABILITY_ISSUER
        or audience != CAPABILITY_AUDIENCE
        or schema_version != expected_schema_version
    ):
        raise CapabilityClaimError(
            "Capability issuer or audience does not match",
            code="claim_scope_mismatch",
        )
    if app != CAPABILITY_APP:
        raise CapabilityClaimError(
            "Capability application does not match",
            code="claim_scope_mismatch",
        )
    if not hmac.compare_digest(subject.encode("utf-8"), expected_subject.encode("utf-8")):
        raise CapabilityClaimError(
            "Capability subject does not match",
            code="subject_mismatch",
        )
    if actual_feature != expected_feature or actual_feature not in KNOWN_CAPABILITY_FEATURES:
        raise CapabilityClaimError(
            "Capability feature does not match the request",
            code="feature_mismatch",
        )
    if actual_version != expected_client_version:
        raise CapabilityClaimError(
            "Capability client version does not match the request",
            code="version_mismatch",
        )
    if (
        actual_device_raw != actual_device
        or not _DEVICE_HASH_RE.fullmatch(actual_device)
        or not hmac.compare_digest(actual_device, expected_device_hash)
    ):
        raise CapabilityClaimError(
            "Capability device binding does not match",
            code="device_mismatch",
        )
    if not _TOKEN_RE.fullmatch(actual_nonce) or not hmac.compare_digest(actual_nonce, expected_nonce):
        raise CapabilityClaimError(
            "Capability nonce does not match",
            code="nonce_mismatch",
        )
    if not _TOKEN_RE.fullmatch(jti):
        raise CapabilityClaimError(
            "Capability identifier is invalid",
            code="invalid_jti",
        )
    if (
        actual_session_hash_raw != actual_session_hash
        or not _DEVICE_HASH_RE.fullmatch(actual_session_hash)
        or not hmac.compare_digest(actual_session_hash, expected_session_hash)
    ):
        raise CapabilityClaimError(
            "Capability session binding does not match",
            code="session_mismatch",
        )

    issued_at = _claim_integer(claims, "iat")
    not_before = _claim_integer(claims, "nbf")
    expires_at = _claim_integer(claims, "exp")
    auth_version = _claim_integer(claims, "auth_version")
    if auth_version < 0:
        raise CapabilityClaimError(
            "Capability authorization version is invalid",
            code="invalid_auth_version",
        )
    if isinstance(clock_skew_seconds, bool):
        raise CapabilityConfigurationError(
            "Clock skew setting is invalid",
            code="invalid_clock_skew",
        )
    skew = int(clock_skew_seconds)
    if skew < 0 or skew > MAX_CLOCK_SKEW_SECONDS:
        raise CapabilityConfigurationError(
            "Clock skew setting is outside the allowed range",
            code="invalid_clock_skew",
        )
    current_time = int(time.time() if now is None else now)
    if not (not_before <= issued_at < expires_at):
        raise CapabilityClaimError(
            "Capability time claims are inconsistent",
            code="invalid_time_claims",
        )
    if expires_at - issued_at > MAX_CAPABILITY_TTL_SECONDS:
        raise CapabilityClaimError(
            "Capability lifetime exceeds the allowed maximum",
            code="ttl_exceeded",
        )
    if issued_at > current_time + skew or not_before > current_time + skew:
        raise CapabilityClaimError(
            "Capability is not active yet",
            code="not_yet_valid",
        )
    if expires_at <= current_time - skew:
        raise CapabilityClaimError(
            "Capability has expired",
            code="expired",
        )
    if issued_at < current_time - MAX_CAPABILITY_TTL_SECONDS - skew:
        raise CapabilityClaimError(
            "Capability issuance time is too old",
            code="stale",
        )


def verify_capability_envelope(
    envelope: Mapping[str, Any],
    *,
    expected_feature: str,
    expected_client_version: str,
    expected_device_hash: str,
    expected_nonce: str,
    expected_subject: str,
    session_token: str,
    now: Optional[int] = None,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
    allow_dev_trust_keys: bool = False,
) -> VerifiedCapability:
    feature, version, device_hash, nonce = _validate_request_texts(
        expected_feature,
        expected_client_version,
        expected_device_hash,
        expected_nonce,
    )
    expected_subject_value = _validate_expected_subject(expected_subject)

    verified_envelope, claims, key_id, signed_payload = _verify_signed_capability_claims(
        envelope,
        expected_format=CAPABILITY_FORMAT,
        signature_context=CAPABILITY_SIGNATURE_CONTEXT,
        signed_claim_keys=_SIGNED_CLAIM_KEYS,
        public_keys=public_keys,
        allow_dev_trust_keys=allow_dev_trust_keys,
    )
    _validate_common_bound_claims(
        claims,
        expected_schema_version=CAPABILITY_CLAIMS_SCHEMA_VERSION,
        expected_feature=feature,
        expected_client_version=version,
        expected_device_hash=device_hash,
        expected_nonce=nonce,
        expected_subject=expected_subject_value,
        session_token=session_token,
        now=now,
        clock_skew_seconds=clock_skew_seconds,
    )
    return VerifiedCapability(
        envelope=verified_envelope,
        claims=claims,
        key_id=key_id,
        canonical_payload=signed_payload,
    )


def verify_rpc_capability_envelope(
    envelope: Mapping[str, Any],
    *,
    expected_feature: str,
    expected_client_version: str,
    expected_device_hash: str,
    expected_nonce: str,
    expected_subject: str,
    session_token: str,
    expected_request_sha256: str,
    expected_rpc_path: str,
    now: Optional[int] = None,
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
    allow_dev_trust_keys: bool = False,
) -> VerifiedCapability:
    feature, version, device_hash, nonce = _validate_request_texts(
        expected_feature,
        expected_client_version,
        expected_device_hash,
        expected_nonce,
    )
    subject = _validate_expected_subject(expected_subject)
    token = _normalize_session_token(session_token)
    if not isinstance(expected_request_sha256, str):
        raise CapabilityConfigurationError(
            "RPC request hash is invalid",
            code="invalid_request_sha256",
        )
    request_sha256 = expected_request_sha256.strip()
    if request_sha256 != expected_request_sha256 or not _REQUEST_SHA256_RE.fullmatch(request_sha256):
        raise CapabilityConfigurationError(
            "RPC request hash must be lowercase SHA-256 hexadecimal",
            code="invalid_request_sha256",
        )
    if not isinstance(expected_rpc_path, str):
        raise CapabilityConfigurationError(
            "RPC path is invalid",
            code="invalid_rpc_path",
        )
    rpc_path = expected_rpc_path.strip()
    if rpc_path != expected_rpc_path or not _RPC_PATH_RE.fullmatch(rpc_path):
        raise CapabilityConfigurationError(
            "RPC path is invalid",
            code="invalid_rpc_path",
        )

    verified_envelope, claims, key_id, signed_payload = _verify_signed_capability_claims(
        envelope,
        expected_format=RPC_CAPABILITY_FORMAT,
        signature_context=RPC_CAPABILITY_SIGNATURE_CONTEXT,
        signed_claim_keys=_RPC_SIGNED_CLAIM_KEYS,
        public_keys=public_keys,
        allow_dev_trust_keys=allow_dev_trust_keys,
    )
    _validate_common_bound_claims(
        claims,
        expected_schema_version=RPC_CAPABILITY_CLAIMS_SCHEMA_VERSION,
        expected_feature=feature,
        expected_client_version=version,
        expected_device_hash=device_hash,
        expected_nonce=nonce,
        expected_subject=subject,
        session_token=token,
        now=now,
        clock_skew_seconds=clock_skew_seconds,
    )

    purpose = _claim_text(claims, "purpose", maximum=16)
    actual_request_hash_raw = _claim_text(claims, "request_sha256", maximum=64)
    actual_request_hash = actual_request_hash_raw.lower()
    actual_rpc_path = _claim_text(claims, "rpc_path", maximum=128)
    if purpose != RPC_CAPABILITY_PURPOSE:
        raise CapabilityClaimError(
            "Capability purpose does not allow RPC use",
            code="purpose_mismatch",
        )
    if (
        actual_request_hash_raw != actual_request_hash
        or not _REQUEST_SHA256_RE.fullmatch(actual_request_hash)
        or not hmac.compare_digest(actual_request_hash, request_sha256)
    ):
        raise CapabilityClaimError(
            "Capability request hash does not match",
            code="request_sha256_mismatch",
        )
    if (
        not _RPC_PATH_RE.fullmatch(actual_rpc_path)
        or not hmac.compare_digest(actual_rpc_path.encode("ascii"), rpc_path.encode("ascii"))
    ):
        raise CapabilityClaimError(
            "Capability RPC path does not match",
            code="rpc_path_mismatch",
        )
    return VerifiedCapability(
        envelope=verified_envelope,
        claims=claims,
        key_id=key_id,
        canonical_payload=signed_payload,
    )


def _read_bounded_response(response, maximum: int) -> bytes:
    content_encoding = str(response.headers.get("Content-Encoding", "") or "").strip().lower()
    if content_encoding not in {"", "identity"}:
        raise CapabilityProtocolError(
            "Compressed capability responses are not accepted",
            code="unsupported_content_encoding",
        )
    declared_length = str(response.headers.get("Content-Length", "") or "").strip()
    if declared_length:
        try:
            if int(declared_length) < 0 or int(declared_length) > maximum:
                raise CapabilityProtocolError(
                    "Capability response exceeds the size limit",
                    code="response_too_large",
                )
        except ValueError as exc:
            raise CapabilityProtocolError(
                "Capability response Content-Length is invalid",
                code="invalid_content_length",
            ) from exc
    raw = response.read(maximum + 1)
    if len(raw) > maximum:
        raise CapabilityProtocolError(
            "Capability response exceeds the size limit",
            code="response_too_large",
        )
    return raw


def _http_error_message(status: int) -> str:
    if status in {401, 403}:
        return "Capability authorization was denied"
    if status == 429:
        return "Capability request was rate limited"
    if status >= 500:
        return "Capability server is temporarily unavailable"
    return "Capability server rejected the request"


def request_capability(
    server_base: str,
    session_token: str,
    feature: str,
    client_version: str,
    device_hash: str,
    *,
    expected_subject: str,
    _test_nonce: Optional[str] = None,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    max_response_bytes: int = MAX_CAPABILITY_RESPONSE_BYTES,
    allow_local_http: bool = False,
    allow_dev_trust_keys: bool = False,
    now: Optional[int] = None,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> VerifiedCapability:
    """Request and verify one short-lived capability grant.

    ``public_keys`` exists for deterministic probes. Production callers should
    leave it unset so the immutable ``CAPABILITY_PUBLIC_KEYS`` trust root is
    used. Environment development keys require a loopback endpoint plus both
    ``allow_dev_trust_keys=True`` and XIAMI_CAPABILITY_ALLOW_DEV_TRUST_KEYS.
    """
    token = _normalize_session_token(session_token)
    expected_subject_value = _validate_expected_subject(expected_subject)
    actual_nonce = str(_test_nonce or generate_capability_nonce()).strip()
    normalized = _validate_request_texts(feature, client_version, device_hash, actual_nonce)
    feature, client_version, device_hash, actual_nonce = normalized
    try:
        timeout = float(timeout_seconds)
    except Exception as exc:
        raise CapabilityConfigurationError(
            "Capability timeout is invalid",
            code="invalid_timeout",
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_REQUEST_TIMEOUT_SECONDS:
        raise CapabilityConfigurationError(
            "Capability timeout is outside the allowed range",
            code="invalid_timeout",
        )
    if isinstance(max_response_bytes, bool):
        raise CapabilityConfigurationError(
            "Capability response size limit is invalid",
            code="invalid_response_limit",
        )
    response_limit = int(max_response_bytes)
    if response_limit <= 0 or response_limit > MAX_CAPABILITY_RESPONSE_BYTES:
        raise CapabilityConfigurationError(
            "Capability response size limit is outside the allowed range",
            code="invalid_response_limit",
        )
    endpoint = build_capability_endpoint(server_base, allow_local_http=allow_local_http)
    parsed_endpoint = urllib.parse.urlsplit(endpoint)
    if public_keys is not None and not _is_loopback_host(parsed_endpoint.hostname or ""):
        raise CapabilityConfigurationError(
            "Injected capability trust keys are restricted to loopback probes",
            code="test_trust_remote_forbidden",
        )
    if allow_dev_trust_keys and not _is_loopback_host(parsed_endpoint.hostname or ""):
        raise CapabilityConfigurationError(
            "Development capability trust keys are restricted to loopback endpoints",
            code="dev_trust_remote_forbidden",
        )
    body = json.dumps(
        {
            "feature": feature,
            "client_version": client_version,
            "device_hash": device_hash,
            "nonce": actual_nonce,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "XiamiToolbox-Capability/1",
        },
    )
    opener = build_backend_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = str(response.geturl() or endpoint)
            ok, error = validate_capability_transport_url(
                final_url,
                allow_local_http=allow_local_http,
            )
            if not ok:
                raise CapabilityTransportError(error, code="unsafe_final_url")
            status = int(getattr(response, "status", response.getcode()) or 0)
            if status != 200:
                raise CapabilityTransportError(
                    "Capability server returned HTTP {}".format(status),
                    code="unexpected_http_status",
                    http_status=status,
                    retryable=status >= 500,
                )
            raw = _read_bounded_response(response, response_limit)
    except urllib.error.HTTPError as exc:
        try:
            exc.read(min(response_limit, 32 * 1024) + 1)
        except Exception:
            pass
        status = int(getattr(exc, "code", 0) or 0)
        message = _http_error_message(status)
        error_type = CapabilityAuthorizationError if status in {401, 403} else CapabilityTransportError
        raise error_type(
            message,
            code="capability_denied" if status in {401, 403} else "http_error",
            http_status=status,
            retryable=status == 429 or status >= 500,
        ) from exc
    except CapabilityError:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        raise CapabilityTransportError(
            "Capability server could not be reached",
            code="network_error",
            retryable=True,
        ) from exc

    payload = _strict_json_loads(raw)
    return verify_capability_envelope(
        payload,
        expected_feature=feature,
        expected_client_version=client_version,
        expected_device_hash=device_hash,
        expected_nonce=actual_nonce,
        expected_subject=expected_subject_value,
        session_token=token,
        now=now,
        public_keys=public_keys,
        allow_dev_trust_keys=allow_dev_trust_keys,
    )


def request_rpc_capability(
    server_base: str,
    session_token: str,
    feature: str,
    client_version: str,
    device_hash: str,
    *,
    expected_subject: str,
    request_sha256: str,
    rpc_path: str,
    _test_nonce: Optional[str] = None,
    timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    max_response_bytes: int = MAX_CAPABILITY_RESPONSE_BYTES,
    allow_local_http: bool = False,
    allow_dev_trust_keys: bool = False,
    now: Optional[int] = None,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> VerifiedCapability:
    """Request and verify one body-bound, single-use RPC capability."""
    token = _normalize_session_token(session_token)
    expected_subject_value = _validate_expected_subject(expected_subject)
    actual_nonce = str(_test_nonce or generate_capability_nonce()).strip()
    feature, client_version, device_hash, actual_nonce = _validate_request_texts(
        feature,
        client_version,
        device_hash,
        actual_nonce,
    )
    if not isinstance(request_sha256, str):
        raise CapabilityConfigurationError(
            "RPC request hash is invalid",
            code="invalid_request_sha256",
        )
    normalized_request_sha256 = request_sha256.strip()
    if normalized_request_sha256 != request_sha256 or not _REQUEST_SHA256_RE.fullmatch(normalized_request_sha256):
        raise CapabilityConfigurationError(
            "RPC request hash must be lowercase SHA-256 hexadecimal",
            code="invalid_request_sha256",
        )
    if not isinstance(rpc_path, str):
        raise CapabilityConfigurationError(
            "RPC path is invalid",
            code="invalid_rpc_path",
        )
    normalized_rpc_path = rpc_path.strip()
    if normalized_rpc_path != rpc_path or not _RPC_PATH_RE.fullmatch(normalized_rpc_path):
        raise CapabilityConfigurationError(
            "RPC path is invalid",
            code="invalid_rpc_path",
        )
    try:
        timeout = float(timeout_seconds)
    except Exception as exc:
        raise CapabilityConfigurationError(
            "Capability timeout is invalid",
            code="invalid_timeout",
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_REQUEST_TIMEOUT_SECONDS:
        raise CapabilityConfigurationError(
            "Capability timeout is outside the allowed range",
            code="invalid_timeout",
        )
    if isinstance(max_response_bytes, bool):
        raise CapabilityConfigurationError(
            "Capability response size limit is invalid",
            code="invalid_response_limit",
        )
    response_limit = int(max_response_bytes)
    if response_limit <= 0 or response_limit > MAX_CAPABILITY_RESPONSE_BYTES:
        raise CapabilityConfigurationError(
            "Capability response size limit is outside the allowed range",
            code="invalid_response_limit",
        )
    endpoint = build_capability_endpoint(server_base, allow_local_http=allow_local_http)
    parsed_endpoint = urllib.parse.urlsplit(endpoint)
    if public_keys is not None and not _is_loopback_host(parsed_endpoint.hostname or ""):
        raise CapabilityConfigurationError(
            "Injected capability trust keys are restricted to loopback probes",
            code="test_trust_remote_forbidden",
        )
    if allow_dev_trust_keys and not _is_loopback_host(parsed_endpoint.hostname or ""):
        raise CapabilityConfigurationError(
            "Development capability trust keys are restricted to loopback endpoints",
            code="dev_trust_remote_forbidden",
        )
    body = json.dumps(
        {
            "feature": feature,
            "client_version": client_version,
            "device_hash": device_hash,
            "nonce": actual_nonce,
            "purpose": RPC_CAPABILITY_PURPOSE,
            "request_sha256": normalized_request_sha256,
            "rpc_path": normalized_rpc_path,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "XiamiToolbox-Capability/2",
        },
    )
    opener = build_backend_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = str(response.geturl() or endpoint)
            ok, error = validate_capability_transport_url(
                final_url,
                allow_local_http=allow_local_http,
            )
            if not ok:
                raise CapabilityTransportError(error, code="unsafe_final_url")
            status = int(getattr(response, "status", response.getcode()) or 0)
            if status != 200:
                raise CapabilityTransportError(
                    "Capability server returned HTTP {}".format(status),
                    code="unexpected_http_status",
                    http_status=status,
                    retryable=status >= 500,
                )
            raw = _read_bounded_response(response, response_limit)
    except urllib.error.HTTPError as exc:
        try:
            exc.read(min(response_limit, 32 * 1024) + 1)
        except Exception:
            pass
        status = int(getattr(exc, "code", 0) or 0)
        message = _http_error_message(status)
        error_type = CapabilityAuthorizationError if status in {401, 403} else CapabilityTransportError
        raise error_type(
            message,
            code="capability_denied" if status in {401, 403} else "http_error",
            http_status=status,
            retryable=status == 429 or status >= 500,
        ) from exc
    except CapabilityError:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        raise CapabilityTransportError(
            "Capability server could not be reached",
            code="network_error",
            retryable=True,
        ) from exc

    payload = _strict_json_loads(raw)
    return verify_rpc_capability_envelope(
        payload,
        expected_feature=feature,
        expected_client_version=client_version,
        expected_device_hash=device_hash,
        expected_nonce=actual_nonce,
        expected_subject=expected_subject_value,
        session_token=token,
        expected_request_sha256=normalized_request_sha256,
        expected_rpc_path=normalized_rpc_path,
        now=now,
        public_keys=public_keys,
        allow_dev_trust_keys=allow_dev_trust_keys,
    )


__all__ = [
    "CAPABILITY_APP",
    "CAPABILITY_AUDIENCE",
    "CAPABILITY_CLAIMS_SCHEMA_VERSION",
    "CAPABILITY_DEVICE_CONTEXT",
    "CAPABILITY_ENDPOINT_PATH",
    "CAPABILITY_FORMAT",
    "CAPABILITY_ISSUER",
    "CAPABILITY_SESSION_CONTEXT",
    "CAPABILITY_SIGNATURE_CONTEXT",
    "CAPABILITY_PUBLIC_KEYS",
    "KNOWN_CAPABILITY_FEATURES",
    "RPC_CAPABILITY_CLAIMS_SCHEMA_VERSION",
    "RPC_CAPABILITY_FORMAT",
    "RPC_CAPABILITY_PURPOSE",
    "RPC_CAPABILITY_SIGNATURE_CONTEXT",
    "CapabilityAuthorizationError",
    "CapabilityClaimError",
    "CapabilityConfigurationError",
    "CapabilityError",
    "CapabilityProtocolError",
    "CapabilityTransportError",
    "CapabilityTrustError",
    "VerifiedCapability",
    "build_capability_endpoint",
    "canonical_capability_payload",
    "compute_device_hash",
    "compute_session_hash",
    "generate_capability_nonce",
    "load_capability_public_keys",
    "request_capability",
    "request_rpc_capability",
    "validate_capability_transport_url",
    "verify_capability_envelope",
    "verify_rpc_capability_envelope",
]
