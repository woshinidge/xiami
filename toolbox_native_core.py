from __future__ import annotations

"""Bounded client broker for the protected native toolbox core.

The Python process owns transport and UI integration, but never receives the
plaintext native lease key or decrypted rule material.  A device-bound native
worker unwraps the V2 lease, emits a challenge, and only runs after the server
has consumed the lease and returned two independently verified proofs.
"""

import base64
import hashlib
import hmac
import http.client
import json
import os
import queue
import re
import secrets
import struct
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path, PureWindowsPath
from typing import Any, Callable, Dict, Mapping, Optional, Set, Tuple

from toolbox_backend_tls import (
    BackendTransportPolicyError,
    build_backend_opener,
    normalize_backend_base_url,
)
from toolbox_capabilities import _verify_rs256_signature, load_capability_public_keys


NATIVE_LEASE_PATH = "/api/v2/native-leases"
NATIVE_LEASE_CONSUME_PATH = "/api/v2/native-leases/consume"
NATIVE_PROTOCOL_VERSION = "2"
DEFAULT_NATIVE_CLIENT_VERSION = "toolbox-native-v3"
DEFAULT_NATIVE_TIMEOUT_SECONDS = 20.0
MAX_NATIVE_TIMEOUT_SECONDS = 15.0 * 60.0
MAX_NATIVE_BODY_BYTES = 16 * 1024 * 1024
MAX_NATIVE_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_DEVICE_PUBLIC_KEY_BYTES = 2048
MAX_CHALLENGE_BLOCK_BYTES = 16 * 1024
NATIVE_LEASE_TTL_SECONDS = 120
NPC_ASSET_FEATURE = "npc.asset.decode"
NPC_ASSET_AUTHORIZE_OPERATION = "authorize-read"
NPC_ASSET_PURPOSES = frozenset(("npc-background", "npc-item", "npc-dialog", "npc-resource"))
NPC_ASSET_METADATA_FIELDS = frozenset(
    (
        "path_sha256",
        "file_name",
        "suffix",
        "file_sha256",
        "file_size",
        "magic",
        "purpose",
        "asset_index",
        "password_sha256",
    )
)
NPC_ASSET_SUFFIXES = frozenset((".pak", ".wil", ".wix", ".wzl", ".wzx", ".wis"))
NPC_ASSET_MAGICS = frozenset(
    ("WZL", "WIL", "WIS", "SWPAK", "GOMPACK", "GEEPAK3", "GEEPAK2", "GEEM2LP", "GAMEOFMIR2", "GAMEOFMIR", "D3DM2")
)
_NPC_ASSET_MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
NPC_TOOLTIP_FEATURE = "npc.tooltip.data"
NPC_TOOLTIP_AUTHORIZE_OPERATION = "authorize-files"
NPC_TOOLTIP_METADATA_FIELDS = frozenset(
    "%s_%s" % (prefix, field)
    for prefix in ("stditems", "top", "list")
    for field in ("path_sha256", "file_sha256", "file_size")
)
_NPC_TOOLTIP_SOURCE_FILE_NAMES = {
    "stditems": frozenset(("stditems.db", "apexm2.db")),
    "top": frozenset(("itemdesctoplist.txt",)),
    "list": frozenset(("itemdesclist.txt",)),
}
_NPC_TOOLTIP_MAX_SOURCE_BYTES = 128 * 1024 * 1024
_NPC_TOOLTIP_MAX_RESULT_BYTES = 512 * 1024
_NPC_TOOLTIP_HANDLE_RE = re.compile(r"^[0-9a-f]{32}$")
_NPC_TOOLTIP_SECTION_KINDS = ("summary", "attributes", "notes")

DEVICE_KEY_HEADER = "XIAMI-NATIVE-DEVICE-KEY-V1"
LEASE_HEADER = "XIAMI-NATIVE-LEASE-V2"
JOB_HEADER = "XIAMI-NATIVE-JOB-V2"
CHALLENGE_HEADER = "XIAMI-NATIVE-CHALLENGE-V1"
CONSUME_HEADER = "XIAMI-NATIVE-CONSUME-V1"
RESULT_HEADER = "XIAMI-NATIVE-RESULT-V2"

DEVICE_KEY_ALGORITHM = "RSA-OAEP-SHA256"
SERVER_SIGNATURE_ALGORITHM = "RS256"
SERVER_PROOF_CONTEXT = b"XIAMI-NATIVE-SERVER-PROOF-V1\0"
CONSUME_PROOF_CONTEXT = b"XIAMI-NATIVE-CONSUME-PROOF-V1\0"

_FIELD_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_HEX_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_LEASE_ID_RE = re.compile(r"^nl_[0-9a-f]{32}$")
_SERVER_CODE_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_SERVER_KEY_ID_RE = re.compile(r"^[0-9a-f]{16}$")
_UTC_DAY_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_BCRYPT_RSAPUBLIC_MAGIC = 0x31415352
_RSA_BITS = 3072
_RSA_MODULUS_BYTES = _RSA_BITS // 8
_RSA_PUBLIC_EXPONENT = 65537


class NativeCoreError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "native_core_error",
        http_status: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(str(message or "Native core failed"))
        self.code = str(code or "native_core_error")
        self.http_status = http_status
        self.retryable = bool(retryable)


class NativeCoreConfigurationError(NativeCoreError):
    pass


class NativeCoreAuthorizationError(NativeCoreError):
    pass


class NativeCoreTransportError(NativeCoreError):
    pass


class NativeCoreProtocolError(NativeCoreError):
    pass


def _wipe(value: Any) -> None:
    if isinstance(value, bytearray):
        for index in range(len(value)):
            value[index] = 0


def _as_bytes(value: Any, field: str) -> bytes:
    if isinstance(value, bytes):
        raw = value
    elif isinstance(value, bytearray):
        raw = bytes(value)
    elif isinstance(value, str):
        raw = value.encode("utf-8")
    else:
        raise NativeCoreConfigurationError(
            "native job field is not text or bytes",
            code="invalid_job_field",
        )
    if len(raw) > MAX_NATIVE_BODY_BYTES:
        raise NativeCoreConfigurationError("native job field is too large", code="job_too_large")
    return raw


def _encode_block_mutable(header: str, fields: Mapping[str, Any]) -> bytearray:
    if not isinstance(header, str) or not header or "\r" in header or "\n" in header:
        raise NativeCoreConfigurationError("native protocol header is invalid", code="invalid_protocol")
    if not isinstance(fields, Mapping):
        raise NativeCoreConfigurationError("native protocol fields are invalid", code="invalid_protocol")
    output = bytearray(header.encode("ascii"))
    output.extend(b"\r\n")
    for key in sorted(fields):
        if not isinstance(key, str) or not _FIELD_NAME_RE.fullmatch(key):
            _wipe(output)
            raise NativeCoreConfigurationError("native protocol field name is invalid", code="invalid_protocol")
        raw = _as_bytes(fields[key], key)
        encoded = base64.b64encode(raw)
        output.extend(key.encode("ascii"))
        output.extend(b"=")
        output.extend(encoded)
        output.extend(b"\r\n")
        if len(output) > MAX_NATIVE_BODY_BYTES:
            _wipe(output)
            raise NativeCoreConfigurationError("native protocol block is too large", code="job_too_large")
    output.extend(b"\r\n")
    return output


def _encode_block(header: str, fields: Mapping[str, Any]) -> bytes:
    mutable = _encode_block_mutable(header, fields)
    try:
        return bytes(mutable)
    finally:
        _wipe(mutable)


def _decode_block(raw: Any, expected_header: str, *, max_bytes: int = MAX_NATIVE_RESPONSE_BYTES) -> Dict[str, bytes]:
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > max_bytes:
        raise NativeCoreProtocolError("native protocol block is too large", code="result_too_large")
    data = bytes(raw)
    terminator = b"\r\n\r\n"
    position = data.find(terminator)
    if position < 0 or position + len(terminator) != len(data):
        raise NativeCoreProtocolError("native protocol block framing is invalid", code="invalid_result")
    parts = data[:position].split(b"\r\n")
    try:
        header = parts[0].decode("ascii", errors="strict") if parts else ""
    except Exception as exc:
        raise NativeCoreProtocolError("native protocol header is invalid", code="invalid_result") from exc
    if header != expected_header:
        raise NativeCoreProtocolError("native protocol header is invalid", code="invalid_result")
    fields: Dict[str, bytes] = {}
    for line in parts[1:]:
        if not line or b"=" not in line:
            raise NativeCoreProtocolError("native protocol field is invalid", code="invalid_result")
        raw_key, encoded = line.split(b"=", 1)
        try:
            key = raw_key.decode("ascii", errors="strict")
        except Exception as exc:
            raise NativeCoreProtocolError("native protocol field is invalid", code="invalid_result") from exc
        if not _FIELD_NAME_RE.fullmatch(key) or key in fields:
            raise NativeCoreProtocolError("native protocol field is invalid", code="invalid_result")
        try:
            fields[key] = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise NativeCoreProtocolError("native protocol field is invalid", code="invalid_result") from exc
    return fields


def _text(fields: Mapping[str, bytes], name: str, *, required: bool = True) -> str:
    value = fields.get(name)
    if value is None:
        if required:
            raise NativeCoreProtocolError("native protocol field is missing", code="invalid_result")
        return ""
    try:
        return bytes(value).decode("utf-8", errors="strict")
    except Exception as exc:
        raise NativeCoreProtocolError("native protocol text is invalid", code="invalid_result") from exc


def _require_fields(fields: Mapping[str, Any], required: Set[str], optional: Optional[Set[str]] = None) -> None:
    allowed = set(required) | set(optional or set())
    actual = set(fields)
    if not required.issubset(actual) or not actual.issubset(allowed):
        raise NativeCoreProtocolError("native protocol fields are invalid", code="invalid_result")


def _validate_timeout(timeout_seconds: float) -> float:
    try:
        value = float(timeout_seconds)
    except Exception as exc:
        raise NativeCoreConfigurationError("native timeout is invalid", code="invalid_timeout") from exc
    if value <= 0 or value > MAX_NATIVE_TIMEOUT_SECONDS:
        raise NativeCoreConfigurationError("native timeout is outside the allowed range", code="invalid_timeout")
    return value


def _remaining(deadline: float) -> float:
    value = float(deadline) - time.monotonic()
    if value <= 0:
        raise NativeCoreTransportError("native core timed out", code="native_timeout", retryable=True)
    return value


def _session_values(session: Mapping[str, Any]) -> Tuple[str, str, str]:
    if not isinstance(session, Mapping):
        raise NativeCoreConfigurationError("toolbox session is invalid", code="invalid_session")
    token = session.get("token")
    device_id = session.get("device_id")
    server = session.get("server")
    if not isinstance(token, str) or not token.strip():
        raise NativeCoreConfigurationError("toolbox session token is missing", code="invalid_session_token")
    if not isinstance(device_id, str) or not device_id.strip() or "\r" in device_id or "\n" in device_id:
        raise NativeCoreConfigurationError("toolbox device identifier is invalid", code="invalid_device_id")
    if not isinstance(server, str) or not server.strip():
        raise NativeCoreConfigurationError("toolbox backend URL is missing", code="invalid_server_url")
    return token.strip(), device_id.strip(), server.strip()


def _strict_json(raw: bytes) -> Any:
    def reject_duplicates(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    try:
        return json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
    except Exception as exc:
        raise NativeCoreProtocolError("native server JSON is invalid", code="invalid_json") from exc


def _normalize_npc_asset_metadata(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != NPC_ASSET_METADATA_FIELDS:
        raise NativeCoreConfigurationError(
            "NPC asset lease metadata fields are invalid", code="invalid_lease_context"
        )
    output: Dict[str, Any] = {}
    for name in ("path_sha256", "file_sha256", "password_sha256"):
        item = value.get(name)
        if not isinstance(item, str) or not _HEX_SHA256_RE.fullmatch(item):
            raise NativeCoreConfigurationError(
                "NPC asset digest metadata is invalid", code="invalid_lease_context"
            )
        output[name] = item
    file_name = value.get("file_name")
    suffix = value.get("suffix")
    magic = value.get("magic")
    purpose = value.get("purpose")
    if (
        not isinstance(file_name, str)
        or not file_name
        or len(file_name.encode("utf-8", errors="strict")) > 255
        or PureWindowsPath(file_name).name != file_name
        or not isinstance(suffix, str)
        or suffix not in NPC_ASSET_SUFFIXES
        or not isinstance(magic, str)
        or magic not in NPC_ASSET_MAGICS
        or not isinstance(purpose, str)
        or purpose not in NPC_ASSET_PURPOSES
    ):
        raise NativeCoreConfigurationError(
            "NPC asset identity metadata is invalid", code="invalid_lease_context"
        )
    output.update(file_name=file_name, suffix=suffix, magic=magic, purpose=purpose)
    file_size = value.get("file_size")
    asset_index = value.get("asset_index")
    if (
        isinstance(file_size, bool)
        or not isinstance(file_size, int)
        or file_size <= 0
        or file_size > _NPC_ASSET_MAX_FILE_BYTES
        or isinstance(asset_index, bool)
        or not isinstance(asset_index, int)
        or asset_index < -1
        or asset_index > 2147483647
    ):
        raise NativeCoreConfigurationError(
            "NPC asset numeric metadata is invalid", code="invalid_lease_context"
        )
    output["file_size"] = file_size
    output["asset_index"] = asset_index
    return output


def _normalize_npc_tooltip_metadata(value: Mapping[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != NPC_TOOLTIP_METADATA_FIELDS:
        raise NativeCoreConfigurationError(
            "NPC tooltip source metadata fields are invalid", code="invalid_tooltip_source"
        )
    output: Dict[str, Any] = {}
    for prefix in ("stditems", "top", "list"):
        path_sha256 = value.get(prefix + "_path_sha256")
        file_sha256 = value.get(prefix + "_file_sha256")
        file_size = value.get(prefix + "_file_size")
        optional = prefix != "stditems"
        omitted = path_sha256 == "" and file_sha256 == "" and file_size == 0
        if omitted and optional:
            output[prefix + "_path_sha256"] = ""
            output[prefix + "_file_sha256"] = ""
            output[prefix + "_file_size"] = 0
            continue
        if (
            not isinstance(path_sha256, str)
            or _HEX_SHA256_RE.fullmatch(path_sha256) is None
            or not isinstance(file_sha256, str)
            or _HEX_SHA256_RE.fullmatch(file_sha256) is None
            or isinstance(file_size, bool)
            or not isinstance(file_size, int)
            or file_size <= 0
            or file_size > _NPC_TOOLTIP_MAX_SOURCE_BYTES
        ):
            raise NativeCoreConfigurationError(
                "NPC tooltip source metadata is invalid", code="invalid_tooltip_source"
            )
        output[prefix + "_path_sha256"] = path_sha256
        output[prefix + "_file_sha256"] = file_sha256
        output[prefix + "_file_size"] = file_size
    return output


def _error_details(payload: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(payload, Mapping):
        return None, None
    error = payload.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        message = error.get("message")
    else:
        code = payload.get("code")
        message = error if isinstance(error, str) else payload.get("message")
    normalized_code = code if isinstance(code, str) and _SERVER_CODE_RE.fullmatch(code) else None
    normalized_message = message if isinstance(message, str) and 0 < len(message) <= 256 else None
    return normalized_code, normalized_message


def _read_response(response) -> bytes:
    content_type = str(response.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise NativeCoreProtocolError("native server Content-Type is invalid", code="invalid_content_type")
    content_encoding = str(response.headers.get("Content-Encoding", "") or "").strip().lower()
    if content_encoding not in {"", "identity"}:
        raise NativeCoreProtocolError("native server encoding is unsupported", code="invalid_content_encoding")
    declared = str(response.headers.get("Content-Length", "") or "").strip()
    if declared:
        try:
            length = int(declared)
        except ValueError as exc:
            raise NativeCoreProtocolError("native server response length is invalid", code="invalid_content_length") from exc
        if length < 0 or length > MAX_NATIVE_RESPONSE_BYTES:
            raise NativeCoreProtocolError("native server response is too large", code="result_too_large")
    raw = response.read(MAX_NATIVE_RESPONSE_BYTES + 1)
    if len(raw) > MAX_NATIVE_RESPONSE_BYTES:
        raise NativeCoreProtocolError("native server response is too large", code="result_too_large")
    return raw


def _request_json(
    session: Mapping[str, Any],
    path: str,
    request_payload: Mapping[str, Any],
    *,
    deadline: float,
    allow_local_http: bool,
) -> Dict[str, Any]:
    token, device_id, server = _session_values(session)
    try:
        base = normalize_backend_base_url(server, allow_local_http=allow_local_http)
    except BackendTransportPolicyError as exc:
        raise NativeCoreConfigurationError(str(exc), code="insecure_transport") from exc
    endpoint = base.rstrip("/") + path
    try:
        body = json.dumps(
            dict(request_payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except Exception as exc:
        raise NativeCoreConfigurationError("native request JSON is invalid", code="invalid_request") from exc
    if len(body) > MAX_NATIVE_BODY_BYTES:
        raise NativeCoreConfigurationError("native request is too large", code="job_too_large")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "XiamiToolbox-NativeCore/2",
            "X-Device-Id": device_id,
        },
    )
    try:
        with build_backend_opener().open(request, timeout=_remaining(deadline)) as response:
            final_url = str(response.geturl() or endpoint)
            if not hmac.compare_digest(final_url.encode("utf-8"), endpoint.encode("utf-8")):
                raise NativeCoreTransportError("native server response URL changed", code="unsafe_final_url")
            status = int(getattr(response, "status", response.getcode()) or 0)
            raw = _read_response(response)
            if status != 200:
                payload = _strict_json(raw)
                code, message = _error_details(payload)
                if status in {401, 403, 426}:
                    raise NativeCoreAuthorizationError(
                        message or "native core authorization was denied",
                        code=code or "authorization_denied",
                        http_status=status,
                    )
                raise NativeCoreTransportError(
                    message or "native server rejected the request",
                    code=code or "server_unavailable",
                    http_status=status,
                    retryable=status >= 500,
                )
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        try:
            raw = exc.read(MAX_NATIVE_RESPONSE_BYTES + 1)
            payload = _strict_json(raw) if raw and len(raw) <= MAX_NATIVE_RESPONSE_BYTES else {}
        except NativeCoreError:
            payload = {}
        code, message = _error_details(payload)
        if status in {401, 403, 426}:
            raise NativeCoreAuthorizationError(
                message or "native core authorization was denied",
                code=code or "authorization_denied",
                http_status=status,
            ) from exc
        raise NativeCoreTransportError(
            message or "native server could not complete the request",
            code=code or "server_unavailable",
            http_status=status,
            retryable=status >= 500,
        ) from exc
    except NativeCoreError:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        raise NativeCoreTransportError(
            "native server could not be reached", code="network_error", retryable=True
        ) from exc
    payload = _strict_json(raw)
    if not isinstance(payload, dict):
        raise NativeCoreProtocolError("native server envelope is invalid", code="invalid_server_envelope")
    return payload


def _request_lease(
    session: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    *,
    deadline: float,
    allow_local_http: bool,
) -> Dict[str, Any]:
    return _request_json(
        session,
        NATIVE_LEASE_PATH,
        request_payload,
        deadline=deadline,
        allow_local_http=allow_local_http,
    )


def _request_consume(
    session: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    *,
    deadline: float,
    allow_local_http: bool,
) -> Dict[str, Any]:
    try:
        return _request_json(
            session,
            NATIVE_LEASE_CONSUME_PATH,
            request_payload,
            deadline=deadline,
            allow_local_http=allow_local_http,
        )
    except NativeCoreTransportError as exc:
        # A lost consume response is ambiguous: the server may already have
        # committed the state transition, so callers must not replay the job.
        raise NativeCoreTransportError(
            str(exc), code=exc.code, http_status=exc.http_status, retryable=False
        ) from exc


def _notify_process(callback: Optional[Callable[[Optional[subprocess.Popen]], None]], process) -> None:
    if callback is None:
        return
    try:
        callback(process)
    except Exception:
        pass


def _close_process_pipes(process) -> None:
    if process is None:
        return
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(process, name, None)
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass
            try:
                setattr(process, name, None)
            except Exception:
                pass


def _kill_and_wait(process) -> None:
    if process is None:
        return
    try:
        if process.poll() is None:
            process.kill()
    except Exception:
        pass
    try:
        process.wait(timeout=1.0)
    except Exception:
        pass


def _native_core_path() -> str:
    configured = str(os.environ.get("XIAMI_NATIVE_CORE_PATH") or "").strip()
    candidates = []
    frozen = bool(getattr(sys, "frozen", False))
    if configured and not frozen:
        candidates.append(configured)
    if frozen:
        base = str(getattr(sys, "_MEIPASS", "") or os.path.dirname(sys.executable))
        candidates.append(os.path.join(base, "native", "xiami_native_core.exe"))
        candidates.append(os.path.join(base, "xiami_native_core.exe"))
    root = os.path.dirname(os.path.abspath(__file__))
    candidates.extend(
        (
            os.path.join(root, "native", "xiami_native_core.exe"),
            os.path.join(root, "build", "native_core", "xiami_native_core.exe"),
        )
    )
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    raise NativeCoreConfigurationError("native core executable is unavailable", code="native_core_missing")


def native_core_executable_path() -> str:
    try:
        return _native_core_path()
    except NativeCoreConfigurationError:
        return ""


def _validate_rsa_public_blob(blob: bytes) -> None:
    if not isinstance(blob, bytes) or len(blob) < 24 or len(blob) > MAX_DEVICE_PUBLIC_KEY_BYTES:
        raise NativeCoreProtocolError("native device public key is invalid", code="invalid_device_key")
    try:
        magic, bit_length, exponent_size, modulus_size, prime1_size, prime2_size = struct.unpack(
            "<6I", blob[:24]
        )
    except Exception as exc:
        raise NativeCoreProtocolError("native device public key is invalid", code="invalid_device_key") from exc
    if (
        magic != _BCRYPT_RSAPUBLIC_MAGIC
        or bit_length != _RSA_BITS
        or modulus_size != _RSA_MODULUS_BYTES
        or prime1_size != 0
        or prime2_size != 0
        or exponent_size <= 0
        or exponent_size > 8
        or len(blob) != 24 + exponent_size + modulus_size
    ):
        raise NativeCoreProtocolError("native device public key is invalid", code="invalid_device_key")
    exponent = int.from_bytes(blob[24 : 24 + exponent_size], "big")
    modulus = blob[24 + exponent_size :]
    if exponent != _RSA_PUBLIC_EXPONENT or not modulus or not (modulus[0] & 0x80):
        raise NativeCoreProtocolError("native device public key is invalid", code="invalid_device_key")


def _validate_device_key_block(fields: Mapping[str, bytes]) -> Dict[str, Any]:
    _require_fields(
        fields,
        {"schema_version", "algorithm", "key_id", "public_key"},
        {"provider", "rsa_bits"},
    )
    if _text(fields, "schema_version") != "1" or _text(fields, "algorithm") != DEVICE_KEY_ALGORITHM:
        raise NativeCoreProtocolError("native device key protocol is unsupported", code="invalid_device_key")
    key_id = _text(fields, "key_id")
    if not _HEX_SHA256_RE.fullmatch(key_id):
        raise NativeCoreProtocolError("native device key identifier is invalid", code="invalid_device_key")
    public_blob = bytes(fields["public_key"])
    _validate_rsa_public_blob(public_blob)
    if "rsa_bits" in fields and _text(fields, "rsa_bits") != str(_RSA_BITS):
        raise NativeCoreProtocolError("native device key size is invalid", code="invalid_device_key")
    actual_key_id = hashlib.sha256(public_blob).hexdigest()
    if not hmac.compare_digest(key_id.encode("ascii"), actual_key_id.encode("ascii")):
        raise NativeCoreProtocolError("native device key identifier does not match", code="invalid_device_key")
    return {
        "key_id": key_id,
        "public_key": public_blob,
        "public_key_b64": base64.b64encode(public_blob).decode("ascii"),
    }


_DEVICE_KEY_CACHE: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
_DEVICE_KEY_CACHE_LOCK = threading.Lock()


def _device_key_cache_key(executable: str) -> Optional[Tuple[Any, ...]]:
    """Identify the native core binary so a replaced one is re-queried."""
    try:
        stat = os.stat(executable)
    except OSError:
        return None
    return (
        os.path.normcase(os.path.abspath(executable)),
        int(stat.st_size),
        int(getattr(stat, "st_mtime_ns", 0)),
    )


def clear_native_device_key_cache() -> None:
    with _DEVICE_KEY_CACHE_LOCK:
        _DEVICE_KEY_CACHE.clear()


def _query_native_device_key(
    executable: str,
    deadline: float,
    process_callback: Optional[Callable[[Optional[subprocess.Popen]], None]],
) -> Dict[str, Any]:
    # The device key is machine-bound and constant for a given binary, but every
    # asset authorization used to spawn a process just to read it again. Cache it
    # per binary identity; the block is still fully validated before it is stored.
    cache_key = _device_key_cache_key(executable)
    if cache_key is not None:
        with _DEVICE_KEY_CACHE_LOCK:
            cached = _DEVICE_KEY_CACHE.get(cache_key)
        if cached is not None:
            return dict(cached)
    process = None
    stdout = bytearray()
    stderr = bytearray()
    try:
        process = subprocess.Popen(
            [executable, "--device-key-info", "--output", "-"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
        )
        _notify_process(process_callback, process)
        raw_stdout, raw_stderr = process.communicate(timeout=_remaining(deadline))
        stdout.extend(raw_stdout)
        stderr.extend(raw_stderr)
        if process.returncode != 0:
            raise NativeCoreProtocolError("native device key query failed", code="device_key_query_failed")
        fields = _decode_block(stdout, DEVICE_KEY_HEADER, max_bytes=MAX_CHALLENGE_BLOCK_BYTES)
        device_key = _validate_device_key_block(fields)
        if cache_key is not None:
            with _DEVICE_KEY_CACHE_LOCK:
                _DEVICE_KEY_CACHE[cache_key] = dict(device_key)
        return device_key
    except subprocess.TimeoutExpired as exc:
        _kill_and_wait(process)
        raise NativeCoreTransportError("native core timed out", code="native_timeout", retryable=True) from exc
    except OSError as exc:
        raise NativeCoreTransportError("native core could not be started", code="native_start_failed") from exc
    finally:
        _kill_and_wait(process)
        _close_process_pipes(process)
        _notify_process(process_callback, None)
        _wipe(stdout)
        _wipe(stderr)


def _decode_b64_field(source: Mapping[str, Any], name: str, *, expected_size: Optional[int] = None) -> bytearray:
    value = source.get(name)
    if not isinstance(value, str) or not value or len(value) > MAX_NATIVE_RESPONSE_BYTES:
        raise NativeCoreProtocolError("native lease binary field is invalid", code="invalid_lease")
    try:
        decoded = bytearray(base64.b64decode(value.encode("ascii"), validate=True))
    except Exception as exc:
        raise NativeCoreProtocolError("native lease binary field is invalid", code="invalid_lease") from exc
    if expected_size is not None and len(decoded) != expected_size:
        _wipe(decoded)
        raise NativeCoreProtocolError("native lease binary field is invalid", code="invalid_lease")
    return decoded


def _validate_lease(
    payload: Mapping[str, Any],
    feature: str,
    operation: str,
    operation_id: str,
    scope_sha256: str,
    key_id: str,
) -> Dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != {"ok", "lease", "usage"} or payload.get("ok") is not True:
        raise NativeCoreProtocolError("native lease response envelope is invalid", code="invalid_lease_envelope")
    lease = payload.get("lease")
    expected = {
        "schema_version", "lease_id", "feature", "operation", "operation_id", "scope_sha256",
        "expires_at", "key_id", "key_wrap_alg", "wrapped_key", "nonce", "ciphertext", "tag", "aad",
    }
    if isinstance(lease, Mapping) and "key" in lease:
        raise NativeCoreProtocolError("native lease contains a forbidden raw key", code="raw_key_forbidden")
    if not isinstance(lease, Mapping) or set(lease) != expected:
        raise NativeCoreProtocolError("native lease fields are invalid", code="invalid_lease")
    if lease.get("schema_version") != 2 or lease.get("key_wrap_alg") != DEVICE_KEY_ALGORITHM:
        raise NativeCoreProtocolError("native lease schema is unsupported", code="invalid_lease")
    lease_id = lease.get("lease_id")
    if not isinstance(lease_id, str) or not _LEASE_ID_RE.fullmatch(lease_id):
        raise NativeCoreProtocolError("native lease identifier is invalid", code="invalid_lease")
    bindings = (
        (lease.get("feature"), feature),
        (lease.get("operation"), operation),
        (lease.get("operation_id"), operation_id),
        (lease.get("scope_sha256"), scope_sha256),
        (lease.get("key_id"), key_id),
    )
    for actual, expected_value in bindings:
        if not isinstance(actual, str) or not hmac.compare_digest(
            actual.encode("utf-8"), expected_value.encode("utf-8")
        ):
            raise NativeCoreProtocolError("native lease scope does not match", code="lease_scope_mismatch")
    try:
        expires_at = int(lease.get("expires_at"))
    except Exception as exc:
        raise NativeCoreProtocolError("native lease expiry is invalid", code="invalid_lease") from exc
    now = int(time.time())
    if expires_at <= now or expires_at > now + NATIVE_LEASE_TTL_SECONDS + 30:
        raise NativeCoreProtocolError("native lease is expired", code="lease_expired")
    decoded: Dict[str, Any] = dict(lease)
    try:
        decoded["wrapped_key"] = _decode_b64_field(lease, "wrapped_key", expected_size=_RSA_MODULUS_BYTES)
        decoded["nonce"] = _decode_b64_field(lease, "nonce", expected_size=12)
        decoded["ciphertext"] = _decode_b64_field(lease, "ciphertext")
        decoded["tag"] = _decode_b64_field(lease, "tag", expected_size=16)
        decoded["aad"] = _decode_b64_field(lease, "aad")
        if not decoded["ciphertext"] or not decoded["aad"]:
            raise NativeCoreProtocolError(
                "native lease cryptographic fields are invalid", code="invalid_lease"
            )
    except Exception:
        for name in ("wrapped_key", "nonce", "ciphertext", "tag", "aad"):
            _wipe(decoded.get(name))
        raise
    return decoded


def _validate_usage(payload: Mapping[str, Any]) -> Dict[str, Any]:
    usage = payload.get("usage") if isinstance(payload, Mapping) else None
    if not isinstance(usage, Mapping) or set(usage) != {"day_utc", "used", "limit"}:
        raise NativeCoreProtocolError("native lease usage is missing", code="invalid_usage")
    day = usage.get("day_utc")
    used = usage.get("used")
    limit = usage.get("limit")
    if not isinstance(day, str) or not _UTC_DAY_RE.fullmatch(day):
        raise NativeCoreProtocolError("native lease usage day is invalid", code="invalid_usage")
    if isinstance(used, bool) or not isinstance(used, int):
        raise NativeCoreProtocolError("native lease usage count is invalid", code="invalid_usage")
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise NativeCoreProtocolError("native lease usage limit is invalid", code="invalid_usage")
    if used < 0 or limit < 0 or limit > 100000 or (limit > 0 and used > limit):
        raise NativeCoreProtocolError("native lease usage bounds are invalid", code="invalid_usage")
    return {"day_utc": day, "used": used, "limit": limit}


def _write_pipe_with_deadline(stream, payload: bytearray, deadline: float, threads: list) -> None:
    result_queue = queue.Queue(maxsize=1)

    def writer() -> None:
        try:
            view = memoryview(payload)
            offset = 0
            while offset < len(view):
                written = stream.write(view[offset:])
                if not isinstance(written, int) or written <= 0:
                    raise OSError("pipe write failed")
                offset += written
            stream.flush()
            result_queue.put((True, None))
        except Exception as exc:
            result_queue.put((False, exc))

    thread = threading.Thread(target=writer, name="xiami-native-pipe-writer", daemon=True)
    threads.append(thread)
    thread.start()
    try:
        ok, error = result_queue.get(timeout=_remaining(deadline))
    except queue.Empty as exc:
        raise NativeCoreTransportError("native core timed out", code="native_timeout", retryable=True) from exc
    if not ok:
        raise NativeCoreTransportError("native core pipe write failed", code="native_pipe_failed") from error


def _read_pipe_block_with_deadline(stream, deadline: float, max_bytes: int, threads: list) -> bytearray:
    result_queue = queue.Queue(maxsize=1)

    def reader() -> None:
        buffer = bytearray()
        try:
            while True:
                chunk = stream.read(4096)
                if not chunk:
                    raise EOFError("pipe closed before protocol block")
                buffer.extend(chunk)
                if len(buffer) > max_bytes:
                    raise ValueError("protocol block too large")
                position = buffer.find(b"\r\n\r\n")
                if position >= 0:
                    end = position + 4
                    if end != len(buffer):
                        raise ValueError("unexpected data after protocol block")
                    result_queue.put((True, buffer))
                    return
        except Exception as exc:
            _wipe(buffer)
            result_queue.put((False, exc))

    thread = threading.Thread(target=reader, name="xiami-native-challenge-reader", daemon=True)
    threads.append(thread)
    thread.start()
    try:
        ok, value = result_queue.get(timeout=_remaining(deadline))
    except queue.Empty as exc:
        raise NativeCoreTransportError("native core timed out", code="native_timeout", retryable=True) from exc
    if not ok:
        raise NativeCoreProtocolError("native challenge could not be read", code="invalid_challenge") from value
    return value


def _validate_challenge(fields: Mapping[str, bytes], lease: Mapping[str, Any]) -> bytearray:
    _require_fields(fields, {"schema_version", "lease_id", "key_id", "challenge"})
    if _text(fields, "schema_version") != "1":
        raise NativeCoreProtocolError("native challenge schema is unsupported", code="invalid_challenge")
    for name in ("lease_id", "key_id"):
        actual = _text(fields, name)
        expected = str(lease[name])
        if not hmac.compare_digest(actual.encode("ascii"), expected.encode("ascii")):
            raise NativeCoreProtocolError("native challenge binding does not match", code="challenge_scope_mismatch")
    challenge = bytearray(fields["challenge"])
    if len(challenge) != 32:
        _wipe(challenge)
        raise NativeCoreProtocolError("native challenge is invalid", code="invalid_challenge")
    return challenge


def _consume_canonical(lease: Mapping[str, Any], challenge: bytearray) -> bytearray:
    values = (
        str(lease["lease_id"]),
        str(lease["operation_id"]),
        str(lease["feature"]),
        str(lease["operation"]),
        str(lease["scope_sha256"]),
        str(lease["key_id"]),
    )
    output = bytearray(CONSUME_PROOF_CONTEXT)
    output.extend(b"\0".join(value.encode("utf-8") for value in values))
    output.extend(b"\0")
    output.extend(challenge)
    return output


def _validate_consume_response(
    payload: Mapping[str, Any],
    lease: Mapping[str, Any],
    challenge: bytearray,
) -> Dict[str, Any]:
    if not isinstance(payload, Mapping) or set(payload) != {"ok", "consume"} or payload.get("ok") is not True:
        raise NativeCoreProtocolError("native consume envelope is invalid", code="invalid_consume")
    consume = payload.get("consume")
    expected = {
        "schema_version", "lease_id", "challenge", "proof", "proof_alg", "state", "consumed_at",
        "server_signature",
    }
    if not isinstance(consume, Mapping) or set(consume) != expected:
        raise NativeCoreProtocolError("native consume fields are invalid", code="invalid_consume")
    if consume.get("schema_version") != 1 or consume.get("proof_alg") != "HMAC-SHA256" or consume.get("state") != "consumed":
        raise NativeCoreProtocolError("native consume protocol is invalid", code="invalid_consume")
    lease_id = consume.get("lease_id")
    if not isinstance(lease_id, str) or not hmac.compare_digest(
        lease_id.encode("ascii"), str(lease["lease_id"]).encode("ascii")
    ):
        raise NativeCoreProtocolError("native consume lease does not match", code="consume_scope_mismatch")
    returned_challenge = bytearray()
    proof = bytearray()
    signature_raw = bytearray()
    keep_output = False
    try:
        challenge_text = consume.get("challenge")
        proof_text = consume.get("proof")
        if not isinstance(challenge_text, str) or not isinstance(proof_text, str):
            raise NativeCoreProtocolError("native consume proof is invalid", code="invalid_consume")
        returned_challenge.extend(base64.b64decode(challenge_text.encode("ascii"), validate=True))
        proof.extend(base64.b64decode(proof_text.encode("ascii"), validate=True))
        if len(returned_challenge) != 32 or len(proof) != 32 or not hmac.compare_digest(
            returned_challenge, challenge
        ):
            raise NativeCoreProtocolError("native consume proof is invalid", code="invalid_consume")

        consumed_at = consume.get("consumed_at")
        if isinstance(consumed_at, bool) or not isinstance(consumed_at, int) or consumed_at <= 0:
            raise NativeCoreProtocolError("native consume timestamp is invalid", code="invalid_consume")
        signature = consume.get("server_signature")
        if not isinstance(signature, Mapping) or set(signature) != {"alg", "key_id", "value"}:
            raise NativeCoreProtocolError("native server signature is invalid", code="invalid_server_signature")
        algorithm = signature.get("alg")
        signature_key_id = signature.get("key_id")
        signature_text = signature.get("value")
        if (
            algorithm != SERVER_SIGNATURE_ALGORITHM
            or not isinstance(signature_key_id, str)
            or not _SERVER_KEY_ID_RE.fullmatch(signature_key_id)
            or not isinstance(signature_text, str)
            or not signature_text
        ):
            raise NativeCoreProtocolError("native server signature is invalid", code="invalid_server_signature")
        try:
            public_key = load_capability_public_keys().get(signature_key_id)
        except Exception as exc:
            raise NativeCoreProtocolError(
                "native server trust root is unavailable", code="invalid_server_signature"
            ) from exc
        if public_key is None:
            raise NativeCoreProtocolError("native server signature key is unknown", code="invalid_server_signature")
        signature_raw.extend(base64.b64decode(signature_text.encode("ascii"), validate=True))
        signature_size = (int(public_key["n"]).bit_length() + 7) // 8
        if len(signature_raw) != signature_size:
            raise NativeCoreProtocolError("native server signature is invalid", code="invalid_server_signature")

        canonical = _consume_canonical(lease, challenge)
        signed_payload = bytearray(SERVER_PROOF_CONTEXT)
        signed_payload.extend(canonical)
        signed_payload.extend(b"\0")
        signed_payload.extend(proof)
        try:
            verified = _verify_rs256_signature(bytes(signed_payload), signature_text, public_key)
        finally:
            _wipe(canonical)
            _wipe(signed_payload)
        if not verified:
            raise NativeCoreProtocolError(
                "native server signature verification failed", code="invalid_server_signature"
            )
        keep_output = True
        return {
            "proof": proof,
            "server_signature_alg": algorithm,
            "server_signature_key_id": signature_key_id,
            "server_signature": signature_raw,
        }
    except NativeCoreError:
        raise
    except Exception as exc:
        raise NativeCoreProtocolError("native consume proof is invalid", code="invalid_consume") from exc
    finally:
        _wipe(returned_challenge)
        if not keep_output:
            _wipe(proof)
            _wipe(signature_raw)


def _validate_native_result(
    raw: Any,
    feature: str,
    operation: str,
    lease: Mapping[str, Any],
) -> Dict[str, bytes]:
    fields = _decode_block(raw, RESULT_HEADER)
    required = {"ok", "schema_version", "feature", "operation", "lease_id", "operation_id", "scope_sha256", "key_id"}
    if not required.issubset(set(fields)):
        raise NativeCoreProtocolError("native result fields are incomplete", code="invalid_result")
    if _text(fields, "ok") != "1" or _text(fields, "schema_version") != "2":
        raise NativeCoreProtocolError("native core did not report success", code="operation_failed")
    expected = {
        "feature": feature,
        "operation": operation,
        "lease_id": str(lease["lease_id"]),
        "operation_id": str(lease["operation_id"]),
        "scope_sha256": str(lease["scope_sha256"]),
        "key_id": str(lease["key_id"]),
    }
    for name, expected_value in expected.items():
        actual = _text(fields, name)
        if not hmac.compare_digest(actual.encode("utf-8"), expected_value.encode("utf-8")):
            raise NativeCoreProtocolError("native result scope does not match", code="result_scope_mismatch")
    return fields


def _worker_error_text(stderr: bytearray) -> str:
    try:
        decoded = bytes(stderr).decode("ascii", errors="strict").strip()
    except Exception:
        return ""
    prefix = "XIAMI_NATIVE_ERROR: "
    if not decoded.startswith(prefix):
        return ""
    value = decoded[len(prefix) :]
    return value if re.fullmatch(r"[A-Za-z0-9 .:=_-]{1,320}", value) else ""


def run_native_core(
    session: Mapping[str, Any],
    feature: str,
    operation: str,
    job_fields: Mapping[str, Any],
    client_version: str = DEFAULT_NATIVE_CLIENT_VERSION,
    *,
    operation_id: Optional[str] = None,
    timeout_seconds: float = DEFAULT_NATIVE_TIMEOUT_SECONDS,
    allow_local_http: bool = False,
    lease_context: Optional[Mapping[str, Any]] = None,
    process_callback: Optional[Callable[[Optional[subprocess.Popen]], None]] = None,
    usage_callback: Optional[Callable[[Mapping[str, Any]], None]] = None,
    asset_broker: Optional[Any] = None,
) -> Dict[str, bytes]:
    timeout = _validate_timeout(timeout_seconds)
    deadline = time.monotonic() + timeout
    if not isinstance(feature, str) or not feature or not isinstance(operation, str) or not operation:
        raise NativeCoreConfigurationError("native feature or operation is invalid", code="invalid_operation")
    if not isinstance(client_version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+\-]{0,63}", client_version):
        raise NativeCoreConfigurationError("native client version is invalid", code="invalid_client_version")
    operation_id = secrets.token_urlsafe(24) if operation_id is None else operation_id
    if not isinstance(operation_id, str) or not _TOKEN_RE.fullmatch(operation_id):
        raise NativeCoreConfigurationError("native operation identifier is invalid", code="invalid_operation_id")
    process = None
    io_threads = []
    lease: Dict[str, Any] = {}
    usage: Dict[str, Any] = {}
    consume_result: Dict[str, Any] = {}
    job_block = bytearray()
    initial_payload = bytearray()
    challenge = bytearray()
    challenge_block = bytearray()
    consume_block = bytearray()
    stdout = bytearray()
    stderr = bytearray()
    try:
        executable = _native_core_path()
        device_key = _query_native_device_key(executable, deadline, process_callback)
        job_block = _encode_block_mutable(JOB_HEADER, job_fields)
        scope_sha256 = hashlib.sha256(job_block).hexdigest()
        request_payload = {
            "schema_version": 2,
            "feature": feature,
            "operation": operation,
            "operation_id": operation_id,
            "client_version": client_version,
            "scope_sha256": scope_sha256,
            "nonce": secrets.token_urlsafe(24),
            "device_key_id": device_key["key_id"],
            "device_public_key": device_key["public_key_b64"],
        }
        if lease_context is not None:
            if feature == NPC_ASSET_FEATURE and operation == NPC_ASSET_AUTHORIZE_OPERATION:
                request_payload["job"] = _normalize_npc_asset_metadata(lease_context)
            elif feature == NPC_TOOLTIP_FEATURE and operation == NPC_TOOLTIP_AUTHORIZE_OPERATION:
                request_payload["job"] = _normalize_npc_tooltip_metadata(lease_context)
            else:
                raise NativeCoreConfigurationError(
                    "native lease metadata is not supported for this operation",
                    code="invalid_lease_context",
                )
        lease_payload = _request_lease(
            session,
            request_payload,
            deadline=deadline,
            allow_local_http=allow_local_http,
        )
        lease = _validate_lease(
            lease_payload,
            feature,
            operation,
            operation_id,
            scope_sha256,
            device_key["key_id"],
        )
        usage = _validate_usage(lease_payload)
        if usage_callback is not None:
            try:
                usage_callback(dict(usage))
            except Exception:
                pass

        lease_fields = {
            "schema_version": "2",
            "lease_id": lease["lease_id"],
            "operation_id": lease["operation_id"],
            "feature": lease["feature"],
            "operation": lease["operation"],
            "scope_sha256": lease["scope_sha256"],
            "expires_at": str(lease["expires_at"]),
            "key_id": lease["key_id"],
            "wrapped_key": lease["wrapped_key"],
            "nonce": lease["nonce"],
            "ciphertext": lease["ciphertext"],
            "tag": lease["tag"],
            "aad": lease["aad"],
        }
        initial_payload = _encode_block_mutable(LEASE_HEADER, lease_fields)
        initial_payload.extend(job_block)
        _wipe(job_block)

        if asset_broker is not None:
            persistent_operation = (
                (feature == NPC_ASSET_FEATURE and operation == NPC_ASSET_AUTHORIZE_OPERATION)
                or (feature == NPC_TOOLTIP_FEATURE and operation == NPC_TOOLTIP_AUTHORIZE_OPERATION)
            )
            if not persistent_operation:
                raise NativeCoreConfigurationError(
                    "persistent native worker does not support this authorization operation",
                    code="invalid_persistent_operation",
                )
            from toolbox_native_asset_worker import (
                AUTHORIZE_COMMIT,
                AUTHORIZE_OPEN,
                CHALLENGE,
                OPEN_RESULT,
            )

            with asset_broker.authorization_transaction():
                response_type, raw_challenge = asset_broker.request(
                    AUTHORIZE_OPEN, bytes(initial_payload), timeout=_remaining(deadline)
                )
                _wipe(initial_payload)
                if response_type != CHALLENGE:
                    raise NativeCoreProtocolError(
                        "native asset worker did not return a challenge", code="invalid_challenge"
                    )
                challenge_block.extend(raw_challenge)
                challenge_fields = _decode_block(
                    challenge_block, CHALLENGE_HEADER, max_bytes=MAX_CHALLENGE_BLOCK_BYTES
                )
                challenge = _validate_challenge(challenge_fields, lease)
                consume_request = {
                    "schema_version": 1,
                    "lease_id": lease["lease_id"],
                    "operation_id": lease["operation_id"],
                    "feature": lease["feature"],
                    "operation": lease["operation"],
                    "scope_sha256": lease["scope_sha256"],
                    "key_id": lease["key_id"],
                    "challenge": base64.b64encode(challenge).decode("ascii"),
                }
                consume_payload = _request_consume(
                    session,
                    consume_request,
                    deadline=deadline,
                    allow_local_http=allow_local_http,
                )
                consume_result = _validate_consume_response(consume_payload, lease, challenge)
                consume_block = _encode_block_mutable(
                    CONSUME_HEADER,
                    {
                        "schema_version": "1",
                        "lease_id": lease["lease_id"],
                        "challenge": challenge,
                        "proof": consume_result["proof"],
                        "server_signature_alg": consume_result["server_signature_alg"],
                        "server_signature_key_id": consume_result["server_signature_key_id"],
                        "server_signature": consume_result["server_signature"],
                    },
                )
                response_type, raw_result = asset_broker.request(
                    AUTHORIZE_COMMIT, bytes(consume_block), timeout=_remaining(deadline)
                )
                _wipe(consume_block)
                if response_type != OPEN_RESULT:
                    raise NativeCoreProtocolError(
                        "native asset worker did not open the asset", code="invalid_open_result"
                    )
                stdout.extend(raw_result)
                result = _validate_native_result(stdout, feature, operation, lease)
                result["worker_generation"] = str(int(asset_broker.generation)).encode("ascii")
                result["usage.day_utc"] = usage["day_utc"].encode("ascii")
                result["usage.used"] = str(usage["used"]).encode("ascii")
                result["usage.limit"] = str(usage["limit"]).encode("ascii")
                return result

        process = subprocess.Popen(
            [executable, "--feature", feature, "--operation", operation, "--input", "-", "--output", "-"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            close_fds=True,
            bufsize=0,
        )
        _notify_process(process_callback, process)
        _write_pipe_with_deadline(process.stdin, initial_payload, deadline, io_threads)
        _wipe(initial_payload)

        challenge_block = _read_pipe_block_with_deadline(
            process.stdout, deadline, MAX_CHALLENGE_BLOCK_BYTES, io_threads
        )
        challenge_fields = _decode_block(
            challenge_block, CHALLENGE_HEADER, max_bytes=MAX_CHALLENGE_BLOCK_BYTES
        )
        challenge = _validate_challenge(challenge_fields, lease)
        consume_request = {
            "schema_version": 1,
            "lease_id": lease["lease_id"],
            "operation_id": lease["operation_id"],
            "feature": lease["feature"],
            "operation": lease["operation"],
            "scope_sha256": lease["scope_sha256"],
            "key_id": lease["key_id"],
            "challenge": base64.b64encode(challenge).decode("ascii"),
        }
        consume_payload = _request_consume(
            session,
            consume_request,
            deadline=deadline,
            allow_local_http=allow_local_http,
        )
        consume_result = _validate_consume_response(consume_payload, lease, challenge)
        consume_block = _encode_block_mutable(
            CONSUME_HEADER,
            {
                "schema_version": "1",
                "lease_id": lease["lease_id"],
                "challenge": challenge,
                "proof": consume_result["proof"],
                "server_signature_alg": consume_result["server_signature_alg"],
                "server_signature_key_id": consume_result["server_signature_key_id"],
                "server_signature": consume_result["server_signature"],
            },
        )
        _write_pipe_with_deadline(process.stdin, consume_block, deadline, io_threads)
        _wipe(consume_block)
        process.stdin.close()
        process.stdin = None

        raw_stdout, raw_stderr = process.communicate(timeout=_remaining(deadline))
        stdout.extend(raw_stdout)
        stderr.extend(raw_stderr)
        if process.returncode != 0:
            message = "native core rejected the lease or job"
            worker_error = _worker_error_text(stderr)
            if worker_error:
                message += ": " + worker_error
            raise NativeCoreProtocolError(message, code="native_core_failed")
        result = _validate_native_result(stdout, feature, operation, lease)
        result["usage.day_utc"] = usage["day_utc"].encode("ascii")
        result["usage.used"] = str(usage["used"]).encode("ascii")
        result["usage.limit"] = str(usage["limit"]).encode("ascii")
        return result
    except subprocess.TimeoutExpired as exc:
        _kill_and_wait(process)
        raise NativeCoreTransportError("native core timed out", code="native_timeout", retryable=True) from exc
    except OSError as exc:
        raise NativeCoreTransportError("native core pipe operation failed", code="native_pipe_failed") from exc
    finally:
        _kill_and_wait(process)
        _close_process_pipes(process)
        _notify_process(process_callback, None)
        for thread in io_threads:
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass
        for buffer in (job_block, initial_payload, challenge, challenge_block, consume_block, stdout, stderr):
            _wipe(buffer)
        for name in ("wrapped_key", "nonce", "ciphertext", "tag", "aad"):
            _wipe(lease.get(name))
        for name in ("proof", "server_signature"):
            _wipe(consume_result.get(name))


def parse_free_micro_text(
    session: Mapping[str, Any], text: str, client_version: str = DEFAULT_NATIVE_CLIENT_VERSION, **kwargs
) -> Dict[str, bytes]:
    return run_native_core(session, "free.micro.parse", "parse-text", {"text": text}, client_version, **kwargs)


def monitor_free_micro_password(
    session: Mapping[str, Any],
    root_pid: int,
    executable_path: str,
    client_version: str = DEFAULT_NATIVE_CLIENT_VERSION,
    **kwargs
) -> Dict[str, bytes]:
    return run_native_core(
        session,
        "free.micro.parse",
        "monitor-password",
        {"root_pid": str(int(root_pid)), "exe_path": str(executable_path or "")},
        client_version,
        **kwargs
    )


def _npc_asset_magic(path: Path, suffix: str) -> str:
    if suffix in {".wzl", ".wzx"}:
        return "WZL"
    if suffix in {".wil", ".wix"}:
        return "WIL"
    if suffix == ".wis":
        return "WIS"
    try:
        with path.open("rb") as handle:
            data = handle.read(32)
    except OSError as exc:
        raise NativeCoreConfigurationError(
            "NPC asset file could not be read", code="asset_file_unreadable"
        ) from exc
    if data.startswith(b"SWPAK01\x00"):
        return "SWPAK"
    if data.startswith(b"PACK"):
        return "GOMPACK"
    if data.startswith(b"\x07GEEPAK3"):
        return "GEEPAK3"
    if data.startswith(b"\x07GEEPAK2"):
        return "GEEPAK2"
    if data.startswith(b"\x05GEEM2"):
        return "GEEM2LP"
    if data.startswith(b"\nGAMEOFMIR2") or data.startswith(b"GAMEOFMIR2"):
        return "GAMEOFMIR2"
    if data.startswith(b"\tGAMEOFMIR") or data.startswith(b"GAMEOFMIR"):
        return "GAMEOFMIR"
    if data.startswith((b"D3DM2", b"MIRYQ", b"GEEM2")):
        return "D3DM2"
    raise NativeCoreConfigurationError(
        "NPC asset format is not authorized", code="asset_magic_unsupported"
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
    except OSError as exc:
        raise NativeCoreConfigurationError(
            "NPC asset file could not be hashed", code="asset_file_unreadable"
        ) from exc
    return digest.hexdigest()


def _prepare_npc_tooltip_source(
    value: Any,
    prefix: str,
    *,
    required: bool,
) -> Tuple[Optional[Path], Dict[str, Any], Dict[str, str]]:
    metadata: Dict[str, Any] = {
        prefix + "_path_sha256": "",
        prefix + "_file_sha256": "",
        prefix + "_file_size": 0,
    }
    job = {
        prefix + "_path": "",
        prefix + "_path_sha256": "",
        prefix + "_file_sha256": "",
        prefix + "_file_size": "0",
    }
    if value is None or value == "":
        if required:
            raise NativeCoreConfigurationError(
                "NPC tooltip StdItems source is missing", code="tooltip_source_missing"
            )
        return None, metadata, job
    try:
        candidate = Path(value).expanduser()
        if candidate.is_symlink():
            raise OSError("symbolic links are not accepted")
        path = candidate.resolve(strict=True)
        stat = path.stat()
    except (OSError, TypeError, ValueError) as exc:
        raise NativeCoreConfigurationError(
            "NPC tooltip source path is invalid", code="invalid_tooltip_source"
        ) from exc
    allowed_names = _NPC_TOOLTIP_SOURCE_FILE_NAMES.get(prefix)
    if (
        allowed_names is None
        or not path.is_file()
        or path.is_symlink()
        or path.name.casefold() not in allowed_names
        or stat.st_size <= 0
        or stat.st_size > _NPC_TOOLTIP_MAX_SOURCE_BYTES
    ):
        raise NativeCoreConfigurationError(
            "NPC tooltip source is not an authorized data file", code="invalid_tooltip_source"
        )
    path_text = str(path)
    try:
        path_raw = path_text.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise NativeCoreConfigurationError(
            "NPC tooltip source path is not valid UTF-8", code="invalid_tooltip_source"
        ) from exc
    if not path_raw or len(path_raw) > 32768 or "\x00" in path_text:
        raise NativeCoreConfigurationError(
            "NPC tooltip source path is invalid", code="invalid_tooltip_source"
        )
    path_sha256 = hashlib.sha256(path_raw).hexdigest()
    file_sha256 = _sha256_file(path)
    metadata.update(
        {
            prefix + "_path_sha256": path_sha256,
            prefix + "_file_sha256": file_sha256,
            prefix + "_file_size": int(stat.st_size),
        }
    )
    job.update(
        {
            prefix + "_path": path_text,
            prefix + "_path_sha256": path_sha256,
            prefix + "_file_sha256": file_sha256,
            prefix + "_file_size": str(int(stat.st_size)),
        }
    )
    return path, metadata, job


def authorize_npc_asset_read(
    session: Mapping[str, Any],
    asset_path: Any,
    purpose: str,
    asset_index: int = -1,
    password: str = "",
    client_version: str = DEFAULT_NATIVE_CLIENT_VERSION,
    asset_broker: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    if not isinstance(purpose, str) or purpose not in NPC_ASSET_PURPOSES:
        raise NativeCoreConfigurationError(
            "NPC asset purpose is invalid", code="invalid_asset_purpose"
        )
    if isinstance(asset_index, bool) or not isinstance(asset_index, int) or not -1 <= asset_index <= 2147483647:
        raise NativeCoreConfigurationError(
            "NPC asset index is invalid", code="invalid_asset_index"
        )
    if not isinstance(password, str) or len(password.encode("utf-8", errors="strict")) > 512:
        raise NativeCoreConfigurationError(
            "NPC asset password is invalid", code="invalid_asset_password"
        )
    try:
        path = Path(asset_path).expanduser().resolve(strict=True)
        stat = path.stat()
    except (OSError, TypeError, ValueError) as exc:
        raise NativeCoreConfigurationError(
            "NPC asset path is invalid", code="invalid_asset_path"
        ) from exc
    if not path.is_file() or path.is_symlink():
        raise NativeCoreConfigurationError(
            "NPC asset path must be a regular file", code="invalid_asset_path"
        )
    path_text = str(path)
    try:
        path_raw = path_text.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise NativeCoreConfigurationError(
            "NPC asset path is not valid UTF-8", code="invalid_asset_path"
        ) from exc
    if not path_raw or len(path_raw) > 32768 or "\x00" in path_text:
        raise NativeCoreConfigurationError(
            "NPC asset path is invalid", code="invalid_asset_path"
        )
    suffix = path.suffix.lower()
    if suffix not in NPC_ASSET_SUFFIXES:
        raise NativeCoreConfigurationError(
            "NPC asset suffix is not authorized", code="asset_suffix_unsupported"
        )
    if stat.st_size <= 0 or stat.st_size > _NPC_ASSET_MAX_FILE_BYTES:
        raise NativeCoreConfigurationError(
            "NPC asset file size is outside the authorized range", code="asset_file_size_invalid"
        )
    magic = _npc_asset_magic(path, suffix)
    file_sha256 = _sha256_file(path)
    password_sha256 = hashlib.sha256(password.encode("utf-8", errors="strict")).hexdigest()
    metadata = {
        "path_sha256": hashlib.sha256(path_raw).hexdigest(),
        "file_name": path.name,
        "suffix": suffix,
        "file_sha256": file_sha256,
        "file_size": int(stat.st_size),
        "magic": magic,
        "purpose": purpose,
        "asset_index": asset_index,
        "password_sha256": password_sha256,
    }
    native_job = dict(metadata, path=path_text, password=password)
    native_job["file_size"] = str(metadata["file_size"])
    native_job["asset_index"] = str(metadata["asset_index"])
    result = run_native_core(
        session,
        NPC_ASSET_FEATURE,
        NPC_ASSET_AUTHORIZE_OPERATION,
        native_job,
        client_version,
        lease_context=metadata,
        asset_broker=asset_broker,
        **kwargs
    )
    required = {
        "authorized",
        "path_sha256",
        "file_sha256",
        "file_size",
        "magic",
        "purpose",
        "asset_index",
        "prefix_size",
        "data_base",
        "allowed_index_modes",
        "format_version",
        "authorization_id",
    }
    if asset_broker is None:
        required.update(("resolved_password", "header_password"))
    else:
        required.update(("asset_handle", "worker_generation"))
    if not required.issubset(result):
        raise NativeCoreProtocolError(
            "NPC asset authorization result is incomplete", code="invalid_asset_authorization"
        )
    expected = {
        "authorized": "1",
        "path_sha256": metadata["path_sha256"],
        "file_sha256": file_sha256,
        "file_size": str(stat.st_size),
        "magic": magic,
        "purpose": purpose,
        "asset_index": str(asset_index),
    }
    for name, expected_value in expected.items():
        actual = _text(result, name)
        if not hmac.compare_digest(actual.encode("utf-8"), str(expected_value).encode("utf-8")):
            raise NativeCoreProtocolError(
                "NPC asset authorization binding does not match", code="asset_authorization_mismatch"
            )
    resolved_password = _text(result, "resolved_password", required=False)
    if asset_broker is None and password and not hmac.compare_digest(
        resolved_password.encode("utf-8"), password.encode("utf-8")
    ):
        raise NativeCoreProtocolError(
            "NPC asset password authorization does not match", code="asset_password_mismatch"
        )
    authorization_id = _text(result, "authorization_id")
    if not _HEX_SHA256_RE.fullmatch(authorization_id):
        raise NativeCoreProtocolError(
            "NPC asset authorization identifier is invalid", code="invalid_asset_authorization"
        )
    response = {
        "path": path,
        "path_sha256": metadata["path_sha256"],
        "file_sha256": file_sha256,
        "file_size": int(stat.st_size),
        "magic": magic,
        "purpose": purpose,
        "asset_index": asset_index,
        "resolved_password": resolved_password,
        "header_password": _text(result, "header_password", required=False),
        "prefix_size": _text(result, "prefix_size"),
        "data_base": int(_text(result, "data_base")),
        "allowed_index_modes": _text(result, "allowed_index_modes"),
        "format_version": _text(result, "format_version"),
        "authorization_id": authorization_id,
        "usage": {
            "day_utc": _text(result, "usage.day_utc"),
            "used": int(_text(result, "usage.used")),
            "limit": int(_text(result, "usage.limit")),
        },
    }
    if asset_broker is not None:
        response.pop("resolved_password", None)
        response.pop("header_password", None)
        response["asset_handle"] = _text(result, "asset_handle")
        response["worker_generation"] = int(_text(result, "worker_generation"))
    return response


def open_local_npc_tooltip_data(
    stditems_path: Any,
    item_desc_top_path: Any = None,
    item_desc_list_path: Any = None,
    asset_broker: Optional[Any] = None,
    timeout_seconds: float = DEFAULT_NATIVE_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Open fixed tooltip sources locally; no server lease is requested."""
    if asset_broker is None:
        raise NativeCoreConfigurationError(
            "NPC tooltip data requires the persistent native worker",
            code="tooltip_worker_required",
        )
    local_open = getattr(asset_broker, "open_local_tooltip_data", None)
    if not callable(local_open):
        raise NativeCoreConfigurationError(
            "NPC tooltip worker does not support local datasets",
            code="tooltip_worker_required",
        )
    timeout = _validate_timeout(timeout_seconds)
    metadata: Dict[str, Any] = {}
    native_job: Dict[str, str] = {}
    for value, prefix, required in (
        (stditems_path, "stditems", True),
        (item_desc_top_path, "top", False),
        (item_desc_list_path, "list", False),
    ):
        _path, source_metadata, source_job = _prepare_npc_tooltip_source(
            value, prefix, required=required
        )
        metadata.update(source_metadata)
        native_job.update(source_job)
    metadata = _normalize_npc_tooltip_metadata(metadata)
    request_payload = _encode_block(JOB_HEADER, native_job)
    raw_result = local_open(request_payload, timeout=timeout)
    result = _decode_block(raw_result, RESULT_HEADER)
    required_fields = {
        "authorized",
        "tooltip_handle",
        "tooltip_source_revision",
        "worker_generation",
    }
    _require_fields(result, required_fields, {"ok"})
    if _text(result, "authorized") != "1":
        raise NativeCoreProtocolError(
            "NPC tooltip data was not authorized", code="tooltip_authorization_failed"
        )
    tooltip_handle = _text(result, "tooltip_handle")
    source_revision = _text(result, "tooltip_source_revision")
    if _NPC_TOOLTIP_HANDLE_RE.fullmatch(tooltip_handle) is None:
        raise NativeCoreProtocolError(
            "NPC tooltip handle is invalid", code="invalid_tooltip_authorization"
        )
    revision_input = bytearray()
    try:
        for prefix in ("stditems", "top", "list"):
            revision_input.extend(str(metadata[prefix + "_file_sha256"]).encode("ascii"))
            revision_input.append(0)
        expected_revision = hashlib.sha256(revision_input).hexdigest()
    finally:
        _wipe(revision_input)
    if (
        _HEX_SHA256_RE.fullmatch(source_revision) is None
        or not hmac.compare_digest(source_revision.encode("ascii"), expected_revision.encode("ascii"))
    ):
        raise NativeCoreProtocolError(
            "NPC tooltip source revision does not match",
            code="tooltip_authorization_mismatch",
        )
    try:
        worker_generation = int(_text(result, "worker_generation"))
        current_generation = int(asset_broker.generation)
    except (AttributeError, TypeError, ValueError) as exc:
        raise NativeCoreProtocolError(
            "NPC tooltip worker generation is invalid",
            code="invalid_tooltip_authorization",
        ) from exc
    if worker_generation <= 0 or worker_generation != current_generation:
        raise NativeCoreProtocolError(
            "NPC tooltip authorization belongs to an expired worker generation",
            code="stale_tooltip_authorization",
        )
    return {
        "tooltip_handle": tooltip_handle,
        "worker_generation": worker_generation,
        "source_revision": source_revision,
    }


def authorize_npc_tooltip_data(
    session: Mapping[str, Any],
    stditems_path: Any,
    item_desc_top_path: Any = None,
    item_desc_list_path: Any = None,
    client_version: str = DEFAULT_NATIVE_CLIENT_VERSION,
    asset_broker: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """Compatibility wrapper for callers built before local tooltip datasets."""
    del session, client_version
    return open_local_npc_tooltip_data(
        stditems_path,
        item_desc_top_path,
        item_desc_list_path,
        asset_broker=asset_broker,
        timeout_seconds=kwargs.pop("timeout_seconds", DEFAULT_NATIVE_TIMEOUT_SECONDS),
    )


def _tooltip_utf8_size(value: Any) -> int:
    if not isinstance(value, str):
        return -1
    try:
        return len(value.encode("utf-8", errors="strict"))
    except UnicodeError:
        return -1


def _validate_npc_item_tooltip_dto(
    raw: Any,
    *,
    item_id: int,
    source_revision: str,
) -> Dict[str, Any]:
    if not isinstance(raw, (bytes, bytearray)) or not 0 < len(raw) <= _NPC_TOOLTIP_MAX_RESULT_BYTES:
        raise NativeCoreProtocolError(
            "native tooltip result size is invalid", code="invalid_tooltip_result"
        )
    payload = _strict_json(bytes(raw))
    root_fields = {
        "schema_version", "found", "item_id", "title", "title_color", "sections", "source_revision"
    }
    if not isinstance(payload, dict) or set(payload) != root_fields:
        raise NativeCoreProtocolError(
            "native tooltip result fields are invalid", code="invalid_tooltip_result"
        )
    returned_id = payload.get("item_id")
    found = payload.get("found")
    title = payload.get("title")
    title_color = payload.get("title_color")
    returned_revision = payload.get("source_revision")
    if (
        payload.get("schema_version") != 1
        or isinstance(payload.get("schema_version"), bool)
        or not isinstance(found, bool)
        or isinstance(returned_id, bool)
        or not isinstance(returned_id, int)
        or returned_id != item_id
        or not isinstance(title, str)
        or not 0 <= _tooltip_utf8_size(title) <= 512
        or "\x00" in title
        or isinstance(title_color, bool)
        or not isinstance(title_color, int)
        or not 1 <= title_color <= 255
        or not isinstance(returned_revision, str)
        or _HEX_SHA256_RE.fullmatch(returned_revision) is None
        or not hmac.compare_digest(returned_revision.encode("ascii"), source_revision.encode("ascii"))
    ):
        raise NativeCoreProtocolError(
            "native tooltip result binding is invalid", code="invalid_tooltip_result"
        )
    sections = payload.get("sections")
    if not isinstance(sections, list) or len(sections) > len(_NPC_TOOLTIP_SECTION_KINDS):
        raise NativeCoreProtocolError(
            "native tooltip sections are invalid", code="invalid_tooltip_result"
        )
    normalized_sections = []
    previous_kind_index = -1
    total_lines = 0
    for section in sections:
        if not isinstance(section, dict) or set(section) != {"kind", "lines"}:
            raise NativeCoreProtocolError(
                "native tooltip section fields are invalid", code="invalid_tooltip_result"
            )
        kind = section.get("kind")
        lines = section.get("lines")
        if not isinstance(kind, str) or kind not in _NPC_TOOLTIP_SECTION_KINDS:
            raise NativeCoreProtocolError(
                "native tooltip section kind is invalid", code="invalid_tooltip_result"
            )
        kind_index = _NPC_TOOLTIP_SECTION_KINDS.index(kind)
        if kind_index <= previous_kind_index or not isinstance(lines, list) or not 0 < len(lines) <= 256:
            raise NativeCoreProtocolError(
                "native tooltip section ordering or lines are invalid", code="invalid_tooltip_result"
            )
        previous_kind_index = kind_index
        normalized_lines = []
        for line in lines:
            if not isinstance(line, dict) or set(line) != {"color", "text"}:
                raise NativeCoreProtocolError(
                    "native tooltip line fields are invalid", code="invalid_tooltip_result"
                )
            color = line.get("color")
            text_value = line.get("text")
            if (
                isinstance(color, bool)
                or not isinstance(color, int)
                or not 0 <= color <= 999
                or not isinstance(text_value, str)
                or not text_value
                or "\x00" in text_value
                or not 0 < _tooltip_utf8_size(text_value) <= 8192
            ):
                raise NativeCoreProtocolError(
                    "native tooltip line value is invalid", code="invalid_tooltip_result"
                )
            normalized_lines.append({"color": color, "text": text_value})
        total_lines += len(normalized_lines)
        if total_lines > 512:
            raise NativeCoreProtocolError(
                "native tooltip result has too many lines", code="invalid_tooltip_result"
            )
        normalized_sections.append({"kind": kind, "lines": normalized_lines})
    if (found and not title) or (not found and (title != "" or sections)):
        raise NativeCoreProtocolError(
            "native tooltip found state is inconsistent", code="invalid_tooltip_result"
        )
    return {
        "schema_version": 1,
        "found": found,
        "item_id": item_id,
        "title": title,
        "title_color": title_color,
        "sections": normalized_sections,
        "source_revision": returned_revision,
    }


def build_npc_item_tooltip(
    asset_broker: Any,
    tooltip_handle: str,
    worker_generation: int,
    item_id: int,
    source_revision: str,
    timeout_seconds: float = DEFAULT_NATIVE_TIMEOUT_SECONDS,
) -> Dict[str, Any]:
    """Return a schema-checked native tooltip DTO; no source parsing occurs here."""
    if asset_broker is None or not callable(getattr(asset_broker, "build_item_tooltip", None)):
        raise NativeCoreConfigurationError(
            "NPC tooltip worker is invalid", code="tooltip_worker_required"
        )
    if not isinstance(tooltip_handle, str) or _NPC_TOOLTIP_HANDLE_RE.fullmatch(tooltip_handle) is None:
        raise NativeCoreConfigurationError(
            "NPC tooltip handle is invalid", code="invalid_tooltip_handle"
        )
    if isinstance(worker_generation, bool) or not isinstance(worker_generation, int) or worker_generation <= 0:
        raise NativeCoreConfigurationError(
            "NPC tooltip worker generation is invalid", code="invalid_tooltip_generation"
        )
    if isinstance(item_id, bool) or not isinstance(item_id, int) or not 0 <= item_id <= 2147483647:
        raise NativeCoreConfigurationError(
            "NPC tooltip item identifier is invalid", code="invalid_tooltip_item_id"
        )
    if not isinstance(source_revision, str) or _HEX_SHA256_RE.fullmatch(source_revision) is None:
        raise NativeCoreConfigurationError(
            "NPC tooltip source revision is invalid", code="invalid_tooltip_revision"
        )
    timeout = _validate_timeout(timeout_seconds)
    raw = asset_broker.build_item_tooltip(
        tooltip_handle,
        worker_generation,
        item_id,
        timeout=timeout,
    )
    return _validate_npc_item_tooltip_dto(
        raw,
        item_id=item_id,
        source_revision=source_revision,
    )


__all__ = [
    "NativeCoreAuthorizationError",
    "NativeCoreConfigurationError",
    "NativeCoreError",
    "NativeCoreProtocolError",
    "NativeCoreTransportError",
    "NATIVE_LEASE_PATH",
    "NATIVE_LEASE_CONSUME_PATH",
    "NPC_ASSET_AUTHORIZE_OPERATION",
    "NPC_ASSET_FEATURE",
    "NPC_TOOLTIP_AUTHORIZE_OPERATION",
    "NPC_TOOLTIP_FEATURE",
    "authorize_npc_asset_read",
    "authorize_npc_tooltip_data",
    "build_npc_item_tooltip",
    "open_local_npc_tooltip_data",
    "monitor_free_micro_password",
    "clear_native_device_key_cache",
    "native_core_executable_path",
    "parse_free_micro_text",
    "run_native_core",
]
