from __future__ import annotations

import hashlib
import hmac
import http.client
import json
import math
import re
import secrets
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Optional, Sequence

from toolbox_backend_tls import (
    BackendTransportPolicyError,
    build_backend_opener,
    normalize_backend_base_url,
)
from toolbox_capabilities import (
    CapabilityAuthorizationError,
    CapabilityConfigurationError,
    CapabilityError,
    CapabilityTransportError,
    VerifiedCapability,
    compute_device_hash,
    request_rpc_capability,
)


MICRO_PAK_FEATURE = "micro.pak.encrypt"
MICRO_PAK_RPC_PATH = "/api/v2/rpc/micro-pak/encrypt"
STORE_SETTINGS_FEATURE = "store.settings"
STORE_RENDER_RPC_PATH = "/api/v2/rpc/store/render-bundle"
STORE_BUNDLE_ROLES = (
    "feature.filter_main",
    "feature.create_file",
    "feature.interface_config",
    "feature.variable_init",
    "owned.qmanage_login",
    "owned.qmanage_timer",
    "owned.qfunction_main",
)
SPAWN_VISUAL_FEATURE = "spawn.visual.edit"
SPAWN_PARSE_RPC_PATH = "/api/v2/rpc/spawn/parse-document"
NPC_VISUAL_FEATURE = "npc.visual.parse"
NPC_PARSE_RPC_PATH = "/api/v2/rpc/npc/parse-document"
RPC_REQUEST_SCHEMA_VERSION = 1

DEFAULT_RPC_TIMEOUT_SECONDS = 15.0
MAX_RPC_TIMEOUT_SECONDS = 30.0
MAX_PASSWORD_COUNT = 256
MAX_PASSWORD_CHARS = 512
MAX_PASSWORD_GBK_BYTES = 1024
MAX_CANONICAL_REQUEST_BYTES = 128 * 1024
MAX_RPC_WRAPPER_BYTES = 160 * 1024
MAX_RPC_RESPONSE_BYTES = 512 * 1024
MAX_STORE_VALUE_CHARS = 256
MAX_STORE_REQUEST_BYTES = 4 * 1024
MAX_SPAWN_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_NPC_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_RPC_WRAPPER_BYTES = 5 * 1024 * 1024
MAX_DOCUMENT_RPC_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_SPAWN_RECORDS = 250000

_OPERATION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,128}$")
_SERVER_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,63}$")
_LOWER_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UPPER_HEX_RE = re.compile(r"^[0-9A-F]+$")
_STORE_PATH_SEGMENT_RE = re.compile(r'^[^<>:"/\\|?*\x00-\x1f]{1,128}$')
_STORE_LABEL_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fff]{1,64}$")
_STORE_U_VAR_RE = re.compile(r"^U(?:0|[1-9][0-9]{0,3})$")


class CoreRpcError(Exception):
    """Base exception for protected toolbox core RPC failures."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "core_rpc_error",
        http_status: Optional[int] = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(str(message or "Core RPC failed"))
        self.code = str(code or "core_rpc_error")
        self.http_status = http_status
        self.retryable = bool(retryable)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "http_status": self.http_status,
            "retryable": self.retryable,
        }


class CoreRpcConfigurationError(CoreRpcError):
    pass


class CoreRpcTransportError(CoreRpcError):
    pass


class CoreRpcAuthorizationError(CoreRpcError):
    pass


class CoreRpcProtocolError(CoreRpcError):
    pass


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
        raise CoreRpcProtocolError(
            "Core RPC returned invalid JSON",
            code="invalid_json",
        ) from exc


def canonical_rpc_json(value: Mapping[str, Any]) -> bytes:
    try:
        text = json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except Exception as exc:
        raise CoreRpcConfigurationError(
            "Core RPC request cannot be canonicalized",
            code="invalid_canonical_request",
        ) from exc
    return text.encode("utf-8")


def compute_rpc_request_sha256(request_payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_rpc_json(request_payload)).hexdigest()


def _normalize_operation_id(operation_id: Optional[str]) -> str:
    value = secrets.token_urlsafe(24) if operation_id is None else operation_id
    if not isinstance(value, str):
        raise CoreRpcConfigurationError(
            "RPC operation identifier is invalid",
            code="invalid_operation_id",
        )
    normalized = value.strip()
    if normalized != value or not _OPERATION_ID_RE.fullmatch(normalized):
        raise CoreRpcConfigurationError(
            "RPC operation identifier is invalid",
            code="invalid_operation_id",
        )
    return normalized


def _normalize_passwords(passwords: Sequence[str]) -> List[str]:
    if isinstance(passwords, (str, bytes, bytearray)) or not isinstance(passwords, Sequence):
        raise CoreRpcConfigurationError(
            "Password batch must be a sequence",
            code="invalid_password_batch",
        )
    normalized = list(passwords)
    if not normalized or len(normalized) > MAX_PASSWORD_COUNT:
        raise CoreRpcConfigurationError(
            "Password batch size is outside the allowed range",
            code="invalid_password_count",
        )
    for value in normalized:
        if not isinstance(value, str):
            raise CoreRpcConfigurationError(
                "Password batch contains a non-text value",
                code="invalid_password",
            )
        if len(value) > MAX_PASSWORD_CHARS:
            raise CoreRpcConfigurationError(
                "Password exceeds the character limit",
                code="password_too_long",
            )
        if len(value.encode("gbk", errors="replace")) > MAX_PASSWORD_GBK_BYTES:
            raise CoreRpcConfigurationError(
                "Password exceeds the GBK byte limit",
                code="password_too_large",
            )
    return normalized


def build_micro_pak_encrypt_request(
    passwords: Sequence[str],
    *,
    operation_id: Optional[str] = None,
) -> Dict[str, Any]:
    request_payload = {
        "schema_version": RPC_REQUEST_SCHEMA_VERSION,
        "operation_id": _normalize_operation_id(operation_id),
        "passwords": _normalize_passwords(passwords),
    }
    raw = canonical_rpc_json(request_payload)
    if len(raw) > MAX_CANONICAL_REQUEST_BYTES:
        raise CoreRpcConfigurationError(
            "Canonical RPC request exceeds the size limit",
            code="request_too_large",
        )
    return request_payload


def _bounded_utf8_text(value: Any, field: str, maximum_bytes: int) -> str:
    if not isinstance(value, str):
        raise CoreRpcConfigurationError(
            "%s must be text" % field,
            code="invalid_%s" % field,
        )
    try:
        raw = value.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise CoreRpcConfigurationError(
            "%s contains invalid Unicode" % field,
            code="invalid_%s" % field,
        ) from exc
    if len(raw) > maximum_bytes:
        raise CoreRpcConfigurationError(
            "%s exceeds the size limit" % field,
            code="%s_too_large" % field,
        )
    return value


def _normalize_sha256_binding(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _LOWER_SHA256_RE.fullmatch(value):
        raise CoreRpcConfigurationError(
            "%s must be a lowercase SHA-256 digest" % field,
            code="invalid_%s" % field,
        )
    return value


def build_store_bundle_request(
    config: Mapping[str, Any],
    *,
    operation_id: Optional[str] = None,
) -> Dict[str, Any]:
    expected_names = {
        "feature_folder", "category_folder", "script_name", "method_name",
        "common_folder", "zone_name", "store_u_var", "teleport_condition",
        "timer_id", "qr_trigger", "resource_number", "qr_method",
        "filter_tip", "store_tip", "target_scope_sha256",
    }
    if not isinstance(config, Mapping) or set(config) != expected_names:
        raise CoreRpcConfigurationError(
            "Store bundle config is invalid",
            code="invalid_store_config",
        )
    normalized: Dict[str, Any] = {}
    for name in ("feature_folder", "category_folder", "script_name", "common_folder", "zone_name"):
        value = config.get(name)
        if (
            not isinstance(value, str) or value in (".", "..") or
            value != value.strip() or not _STORE_PATH_SEGMENT_RE.fullmatch(value)
        ):
            raise CoreRpcConfigurationError(
                "Store path config is invalid: %s" % name,
                code="invalid_store_config",
            )
        _bounded_utf8_text(value, name, MAX_STORE_VALUE_CHARS * 4)
        normalized[name] = value
    for name in ("method_name", "qr_method"):
        value = config.get(name)
        if not isinstance(value, str) or not _STORE_LABEL_RE.fullmatch(value):
            raise CoreRpcConfigurationError(
                "Store label config is invalid: %s" % name,
                code="invalid_store_config",
            )
        normalized[name] = value
    store_u_var = config.get("store_u_var")
    if not isinstance(store_u_var, str) or not _STORE_U_VAR_RE.fullmatch(store_u_var):
        raise CoreRpcConfigurationError("Store U variable is invalid", code="invalid_store_config")
    normalized["store_u_var"] = store_u_var
    target_scope_sha256 = config.get("target_scope_sha256")
    if not isinstance(target_scope_sha256, str) or not _LOWER_SHA256_RE.fullmatch(target_scope_sha256):
        raise CoreRpcConfigurationError(
            "Store target scope is invalid",
            code="invalid_store_config",
        )
    normalized["target_scope_sha256"] = target_scope_sha256
    for name, maximum in (("teleport_condition", 256), ("filter_tip", 128), ("store_tip", 128)):
        value = config.get(name)
        if (
            not isinstance(value, str) or not value or value != value.strip() or
            len(value) > maximum or any(ord(char) < 32 for char in value)
        ):
            raise CoreRpcConfigurationError(
                "Store text config is invalid: %s" % name,
                code="invalid_store_config",
            )
        _bounded_utf8_text(value, name, maximum * 4)
        normalized[name] = value
    for name, minimum, maximum in (
        ("timer_id", 1, 255),
        ("qr_trigger", 1, 999999),
        ("resource_number", 0, 999999),
    ):
        value = config.get(name)
        if type(value) is not int or value < minimum or value > maximum:
            raise CoreRpcConfigurationError(
                "Store numeric config is invalid: %s" % name,
                code="invalid_store_config",
            )
        normalized[name] = value
    request_payload = {
        "schema_version": RPC_REQUEST_SCHEMA_VERSION,
        "operation_id": _normalize_operation_id(operation_id),
        "config": normalized,
    }
    if len(canonical_rpc_json(request_payload)) > MAX_STORE_REQUEST_BYTES:
        raise CoreRpcConfigurationError("Store bundle request is too large", code="request_too_large")
    return request_payload


def build_spawn_parse_request(
    text: str,
    *,
    target_scope_sha256: str,
    expected_pre_sha256: str,
    operation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": RPC_REQUEST_SCHEMA_VERSION,
        "operation_id": _normalize_operation_id(operation_id),
        "target_scope_sha256": _normalize_sha256_binding(
            target_scope_sha256, "target_scope_sha256"
        ),
        "expected_pre_sha256": _normalize_sha256_binding(
            expected_pre_sha256, "expected_pre_sha256"
        ),
        "text": _bounded_utf8_text(text, "spawn_document", MAX_SPAWN_DOCUMENT_BYTES),
    }


def build_npc_parse_request(
    source_text: str,
    *,
    target_scope_sha256: str,
    expected_pre_sha256: str,
    operation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "schema_version": RPC_REQUEST_SCHEMA_VERSION,
        "operation_id": _normalize_operation_id(operation_id),
        "target_scope_sha256": _normalize_sha256_binding(
            target_scope_sha256, "target_scope_sha256"
        ),
        "expected_pre_sha256": _normalize_sha256_binding(
            expected_pre_sha256, "expected_pre_sha256"
        ),
        "source_text": _bounded_utf8_text(source_text, "npc_document", MAX_NPC_DOCUMENT_BYTES),
    }


def _normalize_server_base(
    server_base: str,
    *,
    allow_local_http: bool,
) -> str:
    raw = str(server_base or "").strip()
    if not raw:
        raise CoreRpcConfigurationError(
            "Core RPC server URL is empty",
            code="invalid_server_url",
        )
    try:
        return normalize_backend_base_url(raw, allow_local_http=allow_local_http)
    except BackendTransportPolicyError as exc:
        raise CoreRpcConfigurationError(
            str(exc),
            code="insecure_transport",
        ) from exc


def _build_rpc_endpoint(
    server_base: str,
    *,
    allow_local_http: bool,
    rpc_path: str = MICRO_PAK_RPC_PATH,
) -> str:
    base = _normalize_server_base(
        server_base,
        allow_local_http=allow_local_http,
    )
    if not isinstance(rpc_path, str) or not rpc_path.startswith("/api/v2/rpc/"):
        raise CoreRpcConfigurationError(
            "Core RPC path is invalid",
            code="invalid_rpc_path",
        )
    return base.rstrip("/") + rpc_path


def _validate_timeout(timeout_seconds: float) -> float:
    try:
        timeout = float(timeout_seconds)
    except Exception as exc:
        raise CoreRpcConfigurationError(
            "Core RPC timeout is invalid",
            code="invalid_timeout",
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0 or timeout > MAX_RPC_TIMEOUT_SECONDS:
        raise CoreRpcConfigurationError(
            "Core RPC timeout is outside the allowed range",
            code="invalid_timeout",
        )
    return timeout


def _normalize_device_id_header(device_id: Any) -> str:
    if not isinstance(device_id, str) or not device_id or len(device_id) > 1024:
        raise CoreRpcConfigurationError(
            "Toolbox session device identifier is missing or invalid",
            code="invalid_device_id",
        )
    if "\r" in device_id or "\n" in device_id or any(ord(char) < 32 for char in device_id):
        raise CoreRpcConfigurationError(
            "Toolbox session device identifier is missing or invalid",
            code="invalid_device_id",
        )
    try:
        device_id.encode("ascii", errors="strict")
    except UnicodeEncodeError as exc:
        raise CoreRpcConfigurationError(
            "Toolbox session device identifier must be ASCII",
            code="invalid_device_id",
        ) from exc
    return device_id


def _read_bounded_response(response, maximum: int) -> bytes:
    content_encoding = str(response.headers.get("Content-Encoding", "") or "").strip().lower()
    if content_encoding not in {"", "identity"}:
        raise CoreRpcProtocolError(
            "Compressed Core RPC responses are not accepted",
            code="unsupported_content_encoding",
        )
    content_type = str(response.headers.get("Content-Type", "") or "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        raise CoreRpcProtocolError(
            "Core RPC response Content-Type is invalid",
            code="invalid_content_type",
        )
    declared_length = str(response.headers.get("Content-Length", "") or "").strip()
    if declared_length:
        try:
            length = int(declared_length)
        except ValueError as exc:
            raise CoreRpcProtocolError(
                "Core RPC response Content-Length is invalid",
                code="invalid_content_length",
            ) from exc
        if length < 0 or length > maximum:
            raise CoreRpcProtocolError(
                "Core RPC response exceeds the size limit",
                code="response_too_large",
            )
    raw = response.read(maximum + 1)
    if len(raw) > maximum:
        raise CoreRpcProtocolError(
            "Core RPC response exceeds the size limit",
            code="response_too_large",
        )
    return raw


def _server_error_details(raw: bytes) -> tuple:
    try:
        payload = _strict_json_loads(raw)
    except CoreRpcError:
        return None, None
    if not isinstance(payload, dict):
        return None, None
    error = payload.get("error")
    if isinstance(error, dict):
        code = error.get("code")
        message = error.get("message")
    else:
        code = payload.get("code")
        message = error if isinstance(error, str) else payload.get("message")
    normalized_code = code if isinstance(code, str) and _SERVER_ERROR_CODE_RE.fullmatch(code) else None
    normalized_message = message if isinstance(message, str) and 0 < len(message) <= 256 else None
    return normalized_code, normalized_message


def _raise_http_error(status: int, raw: bytes) -> None:
    server_code, server_message = _server_error_details(raw)
    if status in {401, 403, 409}:
        raise CoreRpcAuthorizationError(
            server_message or "Core RPC authorization was denied",
            code=server_code or ("grant_conflict" if status == 409 else "authorization_denied"),
            http_status=status,
        )
    if status == 429 or status >= 500:
        raise CoreRpcTransportError(
            server_message or "Core RPC server is temporarily unavailable",
            code=server_code or "server_unavailable",
            http_status=status,
            retryable=True,
        )
    raise CoreRpcProtocolError(
        server_message or "Core RPC server rejected the request",
        code=server_code or "request_rejected",
        http_status=status,
    )


def _translate_capability_error(exc: CapabilityError) -> CoreRpcError:
    kwargs = {
        "code": exc.code,
        "http_status": exc.http_status,
        "retryable": exc.retryable,
    }
    if isinstance(exc, CapabilityAuthorizationError):
        return CoreRpcAuthorizationError(str(exc), **kwargs)
    if isinstance(exc, CapabilityConfigurationError):
        return CoreRpcConfigurationError(str(exc), **kwargs)
    if isinstance(exc, CapabilityTransportError):
        return CoreRpcTransportError(str(exc), **kwargs)
    return CoreRpcProtocolError(str(exc), **kwargs)


def _validate_rpc_result(
    payload: Any,
    *,
    operation_id: str,
    passwords: Sequence[str],
) -> List[str]:
    if not isinstance(payload, dict) or set(payload) != {"ok", "operation_id", "encoded"}:
        raise CoreRpcProtocolError(
            "Core RPC response envelope is invalid",
            code="invalid_response_envelope",
        )
    if payload.get("ok") is not True:
        raise CoreRpcProtocolError(
            "Core RPC response did not report success",
            code="operation_failed",
        )
    response_operation_id = payload.get("operation_id")
    if not isinstance(response_operation_id, str) or not hmac.compare_digest(
        response_operation_id.encode("utf-8"),
        operation_id.encode("utf-8"),
    ):
        raise CoreRpcProtocolError(
            "Core RPC operation identifier does not match",
            code="operation_id_mismatch",
        )
    encoded = payload.get("encoded")
    if not isinstance(encoded, list) or len(encoded) != len(passwords):
        raise CoreRpcProtocolError(
            "Core RPC result count does not match the request",
            code="result_count_mismatch",
        )
    result: List[str] = []
    for password, value in zip(passwords, encoded):
        if not isinstance(value, str):
            raise CoreRpcProtocolError(
                "Core RPC returned a non-text encoded value",
                code="invalid_encoded_value",
            )
        if password == "":
            if value != "":
                raise CoreRpcProtocolError(
                    "Core RPC returned an invalid empty-password result",
                    code="invalid_encoded_value",
                )
        else:
            expected_length = 2 * (len(password.encode("gbk", errors="replace")) + 1)
            if (
                len(value) != expected_length
                or not _UPPER_HEX_RE.fullmatch(value)
                or value[:2] == "00"
            ):
                raise CoreRpcProtocolError(
                    "Core RPC returned an invalid encoded value",
                    code="invalid_encoded_value",
                )
        result.append(value)
    return result


def _call_bound_rpc_payload(
    server_base: str,
    session_token: str,
    device_id: str,
    grant: VerifiedCapability,
    request_payload: Mapping[str, Any],
    *,
    rpc_path: str,
    timeout_seconds: float,
    allow_local_http: bool,
    max_wrapper_bytes: int,
    max_response_bytes: int,
) -> Any:
    timeout = _validate_timeout(timeout_seconds)
    normalized_device_id = _normalize_device_id_header(device_id)
    endpoint = _build_rpc_endpoint(
        server_base,
        allow_local_http=allow_local_http,
        rpc_path=rpc_path,
    )
    signed_capability = grant.envelope.get("capability")
    if not isinstance(signed_capability, dict):
        raise CoreRpcProtocolError(
            "Verified capability payload is missing",
            code="invalid_capability_envelope",
        )
    wrapper = {
        "capability": dict(signed_capability),
        "request": dict(request_payload),
    }
    body = canonical_rpc_json(wrapper)
    if len(body) > max_wrapper_bytes:
        raise CoreRpcConfigurationError(
            "Core RPC wrapper exceeds the size limit",
            code="wrapper_too_large",
        )
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + str(session_token),
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "XiamiToolbox-CoreRPC/1",
            "X-Device-Id": normalized_device_id,
        },
    )
    opener = build_backend_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            final_url = str(response.geturl() or endpoint)
            if not hmac.compare_digest(final_url.encode("utf-8"), endpoint.encode("utf-8")):
                raise CoreRpcTransportError(
                    "Core RPC response URL changed unexpectedly",
                    code="unsafe_final_url",
                )
            status = int(getattr(response, "status", response.getcode()) or 0)
            raw = _read_bounded_response(response, max_response_bytes)
            if status != 200:
                _raise_http_error(status, raw)
    except urllib.error.HTTPError as exc:
        status = int(getattr(exc, "code", 0) or 0)
        try:
            raw = exc.read(max_response_bytes + 1)
        except Exception:
            raw = b""
        if len(raw) > max_response_bytes:
            raw = b""
        _raise_http_error(status, raw)
    except CoreRpcError:
        raise
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError) as exc:
        raise CoreRpcTransportError(
            "Core RPC server could not be reached",
            code="network_error",
            retryable=True,
        ) from exc

    return _strict_json_loads(raw)


def _call_micro_pak_rpc(
    server_base: str,
    session_token: str,
    device_id: str,
    grant: VerifiedCapability,
    request_payload: Mapping[str, Any],
    *,
    timeout_seconds: float,
    allow_local_http: bool,
) -> List[str]:
    payload = _call_bound_rpc_payload(
        server_base,
        session_token,
        device_id,
        grant,
        request_payload,
        rpc_path=MICRO_PAK_RPC_PATH,
        timeout_seconds=timeout_seconds,
        allow_local_http=allow_local_http,
        max_wrapper_bytes=MAX_RPC_WRAPPER_BYTES,
        max_response_bytes=MAX_RPC_RESPONSE_BYTES,
    )
    return _validate_rpc_result(
        payload,
        operation_id=str(request_payload["operation_id"]),
        passwords=request_payload["passwords"],
    )


def encrypt_micro_pak_passwords(
    session: Mapping[str, Any],
    passwords: Sequence[str],
    client_version: str,
    *,
    operation_id: Optional[str] = None,
    timeout_seconds: float = DEFAULT_RPC_TIMEOUT_SECONDS,
    allow_local_http: bool = False,
    allow_dev_trust_keys: bool = False,
    now: Optional[int] = None,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
    _test_nonce: Optional[str] = None,
) -> List[str]:
    """Encode a password batch through the protected backend implementation."""
    if not isinstance(session, Mapping):
        raise CoreRpcConfigurationError(
            "Toolbox session is invalid",
            code="invalid_session",
        )
    server_base = str(session.get("server") or "").strip()
    session_token = session.get("token")
    expected_subject = session.get("username")
    device_id = session.get("device_id")
    if not isinstance(session_token, str) or not session_token.strip():
        raise CoreRpcConfigurationError(
            "Toolbox session token is missing",
            code="invalid_session_token",
        )
    if not isinstance(expected_subject, str) or not expected_subject.strip():
        raise CoreRpcConfigurationError(
            "Toolbox session username is missing",
            code="invalid_expected_subject",
        )
    normalized_device_id = _normalize_device_id_header(device_id)

    normalized_server_base = _normalize_server_base(
        server_base,
        allow_local_http=allow_local_http,
    )
    timeout = _validate_timeout(timeout_seconds)
    normalized_session_token = session_token.strip()
    request_payload = build_micro_pak_encrypt_request(
        passwords,
        operation_id=operation_id,
    )
    request_sha256 = compute_rpc_request_sha256(request_payload)
    try:
        grant = request_rpc_capability(
            normalized_server_base,
            normalized_session_token,
            MICRO_PAK_FEATURE,
            client_version,
            compute_device_hash(normalized_device_id),
            expected_subject=expected_subject,
            request_sha256=request_sha256,
            rpc_path=MICRO_PAK_RPC_PATH,
            _test_nonce=_test_nonce,
            timeout_seconds=timeout,
            allow_local_http=allow_local_http,
            allow_dev_trust_keys=allow_dev_trust_keys,
            now=now,
            public_keys=public_keys,
        )
    except CapabilityError as exc:
        raise _translate_capability_error(exc) from exc
    return _call_micro_pak_rpc(
        normalized_server_base,
        normalized_session_token,
        normalized_device_id,
        grant,
        request_payload,
        timeout_seconds=timeout,
        allow_local_http=allow_local_http,
    )


def _request_bound_core_rpc(
    session: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    feature: str,
    rpc_path: str,
    client_version: str,
    *,
    timeout_seconds: float,
    allow_local_http: bool,
    allow_dev_trust_keys: bool,
    now: Optional[int],
    public_keys: Optional[Mapping[str, Mapping[str, Any]]],
    test_nonce: Optional[str],
) -> Any:
    if not isinstance(session, Mapping):
        raise CoreRpcConfigurationError("Toolbox session is invalid", code="invalid_session")
    server_base = str(session.get("server") or "").strip()
    session_token = session.get("token")
    expected_subject = session.get("username")
    device_id = session.get("device_id")
    if not isinstance(session_token, str) or not session_token.strip():
        raise CoreRpcConfigurationError(
            "Toolbox session token is missing",
            code="invalid_session_token",
        )
    if not isinstance(expected_subject, str) or not expected_subject.strip():
        raise CoreRpcConfigurationError(
            "Toolbox session username is missing",
            code="invalid_expected_subject",
        )
    normalized_device_id = _normalize_device_id_header(device_id)
    normalized_server_base = _normalize_server_base(
        server_base,
        allow_local_http=allow_local_http,
    )
    timeout = _validate_timeout(timeout_seconds)
    normalized_session_token = session_token.strip()
    request_sha256 = compute_rpc_request_sha256(request_payload)
    try:
        grant = request_rpc_capability(
            normalized_server_base,
            normalized_session_token,
            feature,
            client_version,
            compute_device_hash(normalized_device_id),
            expected_subject=expected_subject,
            request_sha256=request_sha256,
            rpc_path=rpc_path,
            _test_nonce=test_nonce,
            timeout_seconds=timeout,
            allow_local_http=allow_local_http,
            allow_dev_trust_keys=allow_dev_trust_keys,
            now=now,
            public_keys=public_keys,
        )
    except CapabilityError as exc:
        raise _translate_capability_error(exc) from exc
    return _call_bound_rpc_payload(
        normalized_server_base,
        normalized_session_token,
        normalized_device_id,
        grant,
        request_payload,
        rpc_path=rpc_path,
        timeout_seconds=timeout,
        allow_local_http=allow_local_http,
        max_wrapper_bytes=MAX_DOCUMENT_RPC_WRAPPER_BYTES,
        max_response_bytes=MAX_DOCUMENT_RPC_RESPONSE_BYTES,
    )


def _validate_operation_envelope(
    payload: Any,
    operation_id: str,
    expected_keys: set,
) -> Dict[str, Any]:
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise CoreRpcProtocolError(
            "Core RPC response envelope is invalid",
            code="invalid_response_envelope",
        )
    if payload.get("ok") is not True or payload.get("schema_version") != RPC_REQUEST_SCHEMA_VERSION:
        raise CoreRpcProtocolError(
            "Core RPC response version is invalid",
            code="invalid_response_version",
        )
    response_operation_id = payload.get("operation_id")
    if not isinstance(response_operation_id, str) or not hmac.compare_digest(
        response_operation_id.encode("utf-8"), operation_id.encode("utf-8")
    ):
        raise CoreRpcProtocolError(
            "Core RPC operation identifier does not match",
            code="operation_id_mismatch",
        )
    core_version = payload.get("core_version")
    if not isinstance(core_version, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", core_version):
        raise CoreRpcProtocolError(
            "Core RPC implementation version is invalid",
            code="invalid_core_version",
        )
    return payload


def _rpc_options(
    session: Mapping[str, Any],
    request_payload: Mapping[str, Any],
    feature: str,
    rpc_path: str,
    client_version: str,
    timeout_seconds: float,
    allow_local_http: bool,
    allow_dev_trust_keys: bool,
    now: Optional[int],
    public_keys: Optional[Mapping[str, Mapping[str, Any]]],
    test_nonce: Optional[str],
) -> Any:
    return _request_bound_core_rpc(
        session,
        request_payload,
        feature,
        rpc_path,
        client_version,
        timeout_seconds=timeout_seconds,
        allow_local_http=allow_local_http,
        allow_dev_trust_keys=allow_dev_trust_keys,
        now=now,
        public_keys=public_keys,
        test_nonce=test_nonce,
    )


def _validate_document_identity(
    identity: Any,
    request_payload: Mapping[str, Any],
    source_text: str,
    *,
    error_code: str,
) -> None:
    if not isinstance(identity, dict) or set(identity) != {
        "target_scope_sha256", "expected_pre_sha256", "source_sha256"
    }:
        raise CoreRpcProtocolError(
            "Core RPC document identity is invalid",
            code=error_code,
        )
    expected_values = {
        "target_scope_sha256": request_payload["target_scope_sha256"],
        "expected_pre_sha256": request_payload["expected_pre_sha256"],
        "source_sha256": hashlib.sha256(source_text.encode("utf-8", errors="strict")).hexdigest(),
    }
    for name, expected in expected_values.items():
        actual = identity.get(name)
        if (
            not isinstance(actual, str) or
            not _LOWER_SHA256_RE.fullmatch(actual) or
            not hmac.compare_digest(actual.encode("ascii"), expected.encode("ascii"))
        ):
            raise CoreRpcProtocolError(
                "Core RPC document identity does not match",
                code=error_code,
            )


def render_store_bundle_rpc(
    session: Mapping[str, Any],
    config: Mapping[str, Any],
    client_version: str,
    *,
    operation_id: Optional[str] = None,
    timeout_seconds: float = DEFAULT_RPC_TIMEOUT_SECONDS,
    allow_local_http: bool = False,
    allow_dev_trust_keys: bool = False,
    now: Optional[int] = None,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
    _test_nonce: Optional[str] = None,
) -> Dict[str, Any]:
    request_payload = build_store_bundle_request(config, operation_id=operation_id)
    payload = _rpc_options(
        session, request_payload, STORE_SETTINGS_FEATURE, STORE_RENDER_RPC_PATH,
        client_version, timeout_seconds, allow_local_http, allow_dev_trust_keys,
        now, public_keys, _test_nonce,
    )
    validated = _validate_operation_envelope(
        payload,
        str(request_payload["operation_id"]),
        {"ok", "schema_version", "operation_id", "core_version", "artifacts", "identity"},
    )
    artifacts = validated.get("artifacts")
    identity = validated.get("identity")
    if not isinstance(artifacts, list) or len(artifacts) != len(STORE_BUNDLE_ROLES):
        raise CoreRpcProtocolError("Store bundle artifact count is invalid", code="invalid_store_response")
    if not isinstance(identity, dict) or set(identity) != {
        "config_sha256", "target_scope_sha256"
    }:
        raise CoreRpcProtocolError("Store Core RPC response is invalid", code="invalid_store_response")
    normalized_config = request_payload["config"]
    expected_names = {
        "feature.filter_main": str(normalized_config["script_name"]) + ".txt",
        "feature.create_file": "创建文件.txt",
        "feature.interface_config": "界面配置读取.txt",
        "feature.variable_init": "存销变量初始化.txt",
        "owned.qmanage_login": "QManage.txt",
        "owned.qmanage_timer": "QManage.txt",
        "owned.qfunction_main": "QFunction-0.txt",
    }
    by_role: Dict[str, Dict[str, str]] = {}
    total_bytes = 0
    for index, artifact in enumerate(artifacts):
        if not isinstance(artifact, dict) or set(artifact) != {
            "role", "name", "content", "content_sha256"
        }:
            raise CoreRpcProtocolError("Store bundle artifact is invalid", code="invalid_store_response")
        role = artifact.get("role")
        name = artifact.get("name")
        content = artifact.get("content")
        content_sha256 = artifact.get("content_sha256")
        if role != STORE_BUNDLE_ROLES[index] or role in by_role or name != expected_names.get(role):
            raise CoreRpcProtocolError("Store bundle artifact identity is invalid", code="invalid_store_response")
        if not isinstance(content, str) or not content:
            raise CoreRpcProtocolError("Store bundle artifact content is invalid", code="invalid_store_response")
        try:
            raw = content.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise CoreRpcProtocolError("Store bundle artifact Unicode is invalid", code="invalid_store_response") from exc
        total_bytes += len(raw)
        expected_sha256 = hashlib.sha256(raw).hexdigest()
        if (
            not isinstance(content_sha256, str) or
            not re.fullmatch(r"[0-9a-f]{64}", content_sha256) or
            not hmac.compare_digest(content_sha256, expected_sha256)
        ):
            raise CoreRpcProtocolError("Store bundle artifact hash is invalid", code="invalid_store_response")
        by_role[role] = {
            "name": name,
            "content": content,
            "content_sha256": content_sha256,
        }
    if total_bytes > MAX_DOCUMENT_RPC_RESPONSE_BYTES:
        raise CoreRpcProtocolError("Store bundle is too large", code="response_too_large")
    config_sha256 = identity.get("config_sha256")
    target_scope_sha256 = identity.get("target_scope_sha256")
    expected_config_sha256 = hashlib.sha256(canonical_rpc_json(normalized_config)).hexdigest()
    if (
        not isinstance(config_sha256, str) or
        not _LOWER_SHA256_RE.fullmatch(config_sha256) or
        not hmac.compare_digest(config_sha256.encode("ascii"), expected_config_sha256.encode("ascii"))
    ):
        raise CoreRpcProtocolError("Store bundle config identity is invalid", code="invalid_store_response")
    expected_target_scope_sha256 = str(normalized_config["target_scope_sha256"])
    if (
        not isinstance(target_scope_sha256, str) or
        not _LOWER_SHA256_RE.fullmatch(target_scope_sha256) or
        not hmac.compare_digest(
            target_scope_sha256.encode("ascii"),
            expected_target_scope_sha256.encode("ascii"),
        )
    ):
        raise CoreRpcProtocolError("Store bundle target identity is invalid", code="invalid_store_response")
    return {
        "artifacts": by_role,
        "config_sha256": config_sha256,
        "target_scope_sha256": target_scope_sha256,
    }


def parse_spawn_document_rpc(
    session: Mapping[str, Any],
    text: str,
    client_version: str = "toolbox-core-rpc-v1",
    *,
    target_scope_sha256: str,
    expected_pre_sha256: str,
    operation_id: Optional[str] = None,
    timeout_seconds: float = DEFAULT_RPC_TIMEOUT_SECONDS,
    allow_local_http: bool = False,
    allow_dev_trust_keys: bool = False,
    now: Optional[int] = None,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
    _test_nonce: Optional[str] = None,
) -> Dict[str, Any]:
    request_payload = build_spawn_parse_request(
        text,
        target_scope_sha256=target_scope_sha256,
        expected_pre_sha256=expected_pre_sha256,
        operation_id=operation_id,
    )
    payload = _rpc_options(
        session, request_payload, SPAWN_VISUAL_FEATURE, SPAWN_PARSE_RPC_PATH,
        client_version, timeout_seconds, allow_local_http, allow_dev_trust_keys,
        now, public_keys, _test_nonce,
    )
    validated = _validate_operation_envelope(
        payload,
        str(request_payload["operation_id"]),
        {
            "ok", "schema_version", "operation_id", "core_version", "accepted",
            "rejected", "records", "identity",
        },
    )
    _validate_document_identity(
        validated.get("identity"),
        request_payload,
        text,
        error_code="invalid_spawn_response",
    )
    accepted = validated.get("accepted")
    rejected = validated.get("rejected")
    records = validated.get("records")
    if type(accepted) is not int or type(rejected) is not int or accepted < 0 or rejected < 0:
        raise CoreRpcProtocolError("Spawn counts are invalid", code="invalid_spawn_response")
    if not isinstance(records, list) or accepted != len(records) or accepted > MAX_SPAWN_RECORDS:
        raise CoreRpcProtocolError("Spawn record count is invalid", code="invalid_spawn_response")
    lines = text.splitlines()
    normalized_records: List[Dict[str, Any]] = []
    seen_lines = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {"line_number", "fields", "token_spans"}:
            raise CoreRpcProtocolError("Spawn record is invalid", code="invalid_spawn_response")
        line_number = record.get("line_number")
        fields = record.get("fields")
        spans = record.get("token_spans")
        if type(line_number) is not int or line_number < 0 or line_number >= len(lines) or line_number in seen_lines:
            raise CoreRpcProtocolError("Spawn line number is invalid", code="invalid_spawn_response")
        if not isinstance(fields, list) or len(fields) not in (7, 8) or any(not isinstance(value, str) for value in fields):
            raise CoreRpcProtocolError("Spawn fields are invalid", code="invalid_spawn_response")
        if not isinstance(spans, list) or len(spans) != len(fields):
            raise CoreRpcProtocolError("Spawn token spans are invalid", code="invalid_spawn_response")
        normalized_spans: List[List[int]] = []
        cursor = 0
        for field, span in zip(fields, spans):
            if (
                not isinstance(span, list) or len(span) != 2 or
                type(span[0]) is not int or type(span[1]) is not int or
                span[0] < cursor or span[1] <= span[0] or span[1] > len(lines[line_number]) or
                lines[line_number][span[0]:span[1]] != field
            ):
                raise CoreRpcProtocolError("Spawn token span is invalid", code="invalid_spawn_response")
            normalized_spans.append([span[0], span[1]])
            cursor = span[1]
        seen_lines.add(line_number)
        normalized_records.append({
            "line_number": line_number,
            "fields": list(fields),
            "token_spans": normalized_spans,
        })
    return {"accepted": accepted, "rejected": rejected, "records": normalized_records}


def parse_npc_document_rpc(
    session: Mapping[str, Any],
    source_text: str,
    client_version: str = "toolbox-core-rpc-v1",
    *,
    target_scope_sha256: str,
    expected_pre_sha256: str,
    operation_id: Optional[str] = None,
    timeout_seconds: float = DEFAULT_RPC_TIMEOUT_SECONDS,
    allow_local_http: bool = False,
    allow_dev_trust_keys: bool = False,
    now: Optional[int] = None,
    public_keys: Optional[Mapping[str, Mapping[str, Any]]] = None,
    _test_nonce: Optional[str] = None,
) -> Dict[str, Any]:
    request_payload = build_npc_parse_request(
        source_text,
        target_scope_sha256=target_scope_sha256,
        expected_pre_sha256=expected_pre_sha256,
        operation_id=operation_id,
    )
    payload = _rpc_options(
        session, request_payload, NPC_VISUAL_FEATURE, NPC_PARSE_RPC_PATH,
        client_version, timeout_seconds, allow_local_http, allow_dev_trust_keys,
        now, public_keys, _test_nonce,
    )
    validated = _validate_operation_envelope(
        payload,
        str(request_payload["operation_id"]),
        {"ok", "schema_version", "operation_id", "core_version", "document", "identity"},
    )
    _validate_document_identity(
        validated.get("identity"),
        request_payload,
        source_text,
        error_code="invalid_npc_response",
    )
    document = validated.get("document")
    if not isinstance(document, dict) or set(document) != {"labels"} or not isinstance(document.get("labels"), list):
        raise CoreRpcProtocolError("NPC document response is invalid", code="invalid_npc_response")
    return document


__all__ = [
    "CoreRpcAuthorizationError",
    "CoreRpcConfigurationError",
    "CoreRpcError",
    "CoreRpcProtocolError",
    "CoreRpcTransportError",
    "MICRO_PAK_FEATURE",
    "MICRO_PAK_RPC_PATH",
    "NPC_PARSE_RPC_PATH",
    "NPC_VISUAL_FEATURE",
    "SPAWN_PARSE_RPC_PATH",
    "SPAWN_VISUAL_FEATURE",
    "STORE_BUNDLE_ROLES",
    "STORE_RENDER_RPC_PATH",
    "STORE_SETTINGS_FEATURE",
    "build_npc_parse_request",
    "build_micro_pak_encrypt_request",
    "build_spawn_parse_request",
    "build_store_bundle_request",
    "canonical_rpc_json",
    "compute_rpc_request_sha256",
    "encrypt_micro_pak_passwords",
    "parse_npc_document_rpc",
    "parse_spawn_document_rpc",
    "render_store_bundle_rpc",
]
