from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from toolbox_backend_tls import (
    BackendTransportPolicyError,
    backend_base_from_login_url,
    backend_urlopen,
    build_backend_opener,
    normalize_backend_base_url,
)


# 更新进度条分段：下载结束后还有校验/解压/写脚本三段耗时工作，
# 若下载独占 0-100，后续阶段就只能停在 100 不动（或倒退回 0），
# 表现为“很快到 9x% 然后卡住很久”。这里给每段留出可见区间。
_DOWNLOAD_PCT = 70
_VERIFY_PCT = 80
_EXTRACT_PCT = 94
_FINALIZE_PCT = 97

# Only public verification material belongs in the client. The matching private
# key stays on the update server and is excluded from Git and release packages.
UPDATE_MANIFEST_PUBLIC_KEYS = {
    "fca6f5048ef42ee7": {
        "n": "0xb2c8179300657512d192d0e2d976cf391c0c90f04b748f987f8b2dbc3a9851e896c5e74b33989c946551090263882ff707c6206da1c26b7801eaae59121e6da37b0d4297cfeadaa258eb218c5dc05c5df00a59ebfe200952495f0512353ef950d1b83939142ac63fbee65a80174df54d88b14f5644d0efdf653f991024c6a0d56592843a4af4fb6589a4955d88e551e3bf8ec8c3587fd3511caf97d544b5c3202c95fbf151c010ff36d5dbea00bddbb38dcfefc53fa0a47e0a9d91c8c34690889c7fa79d3454b26997824c71c38ddeca9627bccf6e8c3aee4994e812b6d580052a4b41e8b702aaefe1fd785fe067e3aecb714dc710660ac9f7c15a1ba82f95c097313f7bb0c084b801ea11f36932fddad53f88cbeaf36865d83930c8845c9f20f656d220d8d120a761051882b24006ed93d2c98c472d2a2eba27e8e56ccc9d52b478e8ed41cd11182de1be60c0955355da56d437705ff23daf16f12caf7db696ea62dba554bab07cdb25b380c947c1d977f225fe1f3c8f54aa971b6863d18f1b",
        "e": 65537,
    },
}

# A corrupt or malicious server must not be able to fill the system drive even
# when it omits Content-Length. Signed manifests can declare a smaller limit.
MAX_UPDATE_DOWNLOAD_BYTES = 2 * 1024 * 1024 * 1024
MAX_UPDATE_ZIP_ENTRIES = 20_000
MAX_UPDATE_ZIP_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_UPDATE_ZIP_ENTRY_BYTES = 512 * 1024 * 1024
MAX_UPDATE_ZIP_COMPRESSION_RATIO = 250
_UPDATE_ZIP_RATIO_MIN_BYTES = 1024 * 1024

_SIGNED_MANIFEST_FIELDS = (
    "schema_version",
    "app",
    "channel",
    "latest_version",
    "min_supported_version",
    "download_url",
    "sha256",
    "size",
    "release_notes",
    "published_at",
    "expires_at",
    "same_version_update",
    "force_same_version_update",
    "allow_same_version_update",
    "hot_update",
    "force_hot_update",
)

_SIGNED_MANIFEST_BOOL_FIELDS = {
    "same_version_update",
    "force_same_version_update",
    "allow_same_version_update",
    "hot_update",
    "force_hot_update",
}

_SIGNED_MANIFEST_INT_FIELDS = {"schema_version", "size"}

_RSA_SHA256_DIGEST_INFO_PREFIX = bytes.fromhex("3031300d060960864801650304020105000420")

_QT_AVAILABLE = True
_QT_IMPORT_ERROR_MESSAGE = ""
_QT_BINDING = ""

try:
    from PySide2 import QtCore
    from PySide2 import QtWidgets
    _QT_BINDING = "PySide2"
except Exception as _e_pyside2:
    try:
        from PySide6 import QtCore
        from PySide6 import QtWidgets
        _QT_BINDING = "PySide6"
    except Exception as _e_pyside6:
        _QT_AVAILABLE = False
        _QT_BINDING = ""

        class _SignalStub:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def connect(self, *_args, **_kwargs) -> None:
                return None

            def emit(self, *_args, **_kwargs) -> None:
                return None

        def _signal_stub(*_args, **_kwargs):
            return _SignalStub()

        def _slot_stub(*_args, **_kwargs):
            def deco(fn):
                return fn
            return deco

        class _QtEnumStub:
            def __getattr__(self, _name: str) -> int:
                return 0

        class _QtModuleStub:
            Qt = _QtEnumStub()
            Signal = staticmethod(_signal_stub)
            Slot = staticmethod(_slot_stub)

            def __getattr__(self, name: str):
                if name in ("Qt", "Signal", "Slot"):
                    return getattr(self, name)
                if name == "qInstallMessageHandler":
                    return lambda *_args, **_kwargs: None
                return type(name, (), {})

        _QT_IMPORT_ERROR_MESSAGE = (
            f"导入错误：PySide2={type(_e_pyside2).__name__}: {_e_pyside2}\n"
            f"导入错误：PySide6={type(_e_pyside6).__name__}: {_e_pyside6}\n"
        )
        QtCore = _QtModuleStub()
        QtWidgets = _QtModuleStub()


def server_base_from_login_url(login_url: str) -> str:
    raw = str(login_url or "").strip()
    if not raw:
        return ""
    try:
        return backend_base_from_login_url(raw, allow_local_http=True)
    except BackendTransportPolicyError:
        return ""


def compare_versions(v1, v2) -> int:
    def normalize(v):
        return [int(x) for x in str(v).split(".") if str(x).strip() != ""]

    try:
        p1 = normalize(v1)
        p2 = normalize(v2)
        return (p1 > p2) - (p1 < p2)
    except Exception:
        v1s = str(v1)
        v2s = str(v2)
        return (v1s > v2s) - (v1s < v2s)


def make_absolute_url(base_url: str, u: str) -> str:
    try:
        u = str(u or "").strip()
        if not u:
            return ""
        if urllib.parse.urlsplit(u).scheme:
            return u
        base_url = str(base_url or "").strip().rstrip("/")
        if not base_url:
            return u
        if u.startswith("/"):
            return base_url + u
        return base_url + "/" + u
    except Exception:
        try:
            return str(u or "")
        except Exception:
            return ""


def normalize_http_url(u: str) -> str:
    try:
        u = str(u or "").strip()
        if not u:
            return ""
        p = urllib.parse.urlsplit(u)
        path = urllib.parse.quote(p.path, safe="/%")
        return urllib.parse.urlunsplit((p.scheme, p.netloc, path, p.query, p.fragment))
    except Exception:
        try:
            return str(u or "")
        except Exception:
            return ""


def _http_origin(url: str):
    try:
        parsed = urllib.parse.urlsplit(str(url or "").strip())
        scheme = str(parsed.scheme or "").lower()
        host = str(parsed.hostname or "").lower()
        if scheme not in {"http", "https"} or not host:
            return None
        port = parsed.port
        if port is None:
            port = 443 if scheme == "https" else 80
        return scheme, host, int(port)
    except Exception:
        return None


def _same_http_origin(left: str, right: str) -> bool:
    left_origin = _http_origin(left)
    return bool(left_origin and left_origin == _http_origin(right))


def _download_uses_backend_transport(base_url: str, download_url: str) -> bool:
    try:
        normalized_base = normalize_backend_base_url(base_url, allow_local_http=True)
    except BackendTransportPolicyError:
        return False
    return _same_http_origin(normalized_base, download_url)


def _open_update_download(request, *, timeout: float, use_backend_transport: bool):
    if use_backend_transport:
        return build_backend_opener().open(request, timeout=float(timeout))
    return urllib.request.urlopen(request, timeout=float(timeout))


def _manifest_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    try:
        text = str(value or "").strip().lower()
    except Exception:
        text = ""
    return text in {"1", "true", "yes", "y", "on", "enable", "enabled", "是", "启用", "开启"}


def _update_policy_value(app: str, key: str, env_name: str, default=""):
    env_value = os.environ.get(str(env_name or ""), "")
    if str(env_value or "").strip():
        return env_value
    try:
        bootstrap = load_bootstrap(app) or {}
        if key in bootstrap:
            return bootstrap.get(key)
    except Exception:
        pass
    return default


def _update_policy_bool(app: str, key: str, env_name: str, default: bool = False) -> bool:
    value = _update_policy_value(app, key, env_name, default)
    if value is default:
        return bool(default)
    return _manifest_bool(value)


def _manifest_signature_required(app: str) -> bool:
    # A writable bootstrap file must never be able to downgrade a production
    # trust root. Unsigned compatibility is available only behind two explicit
    # development switches used for local migration probes.
    if UPDATE_MANIFEST_PUBLIC_KEYS and not (
        _manifest_bool(os.environ.get("XIAMI_UPDATE_ALLOW_DEV_TRUST_KEYS", ""))
        and _manifest_bool(os.environ.get("XIAMI_UPDATE_ALLOW_UNSIGNED_MANIFESTS", ""))
    ):
        return True
    mode = str(
        _update_policy_value(
            app,
            "manifest_signature_mode",
            "XIAMI_UPDATE_MANIFEST_SIGNATURE_MODE",
            "required",
        )
        or "required"
    ).strip().lower()
    return mode in {"required", "require", "strict", "enforce", "fail-closed", "fail_closed"}


def _is_loopback_host(host: str) -> bool:
    host = str(host or "").strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return bool(ipaddress.ip_address(host).is_loopback)
    except Exception:
        return False


def validate_update_transport_url(
    url: str,
    app: str = "toolbox",
    allow_local_http=None,
    allow_file=None,
) -> tuple[bool, str]:
    """Validate an update manifest/download URL without opening it."""
    try:
        parsed = urllib.parse.urlsplit(str(url or "").strip())
    except Exception:
        return False, "更新地址格式无效"
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme == "https":
        return True, ""
    if allow_local_http is None:
        allow_local_http = _update_policy_bool(
            app,
            "allow_local_http_update",
            "XIAMI_UPDATE_ALLOW_LOCAL_HTTP",
            False,
        )
    if scheme == "http":
        if bool(allow_local_http) and _is_loopback_host(parsed.hostname or ""):
            return True, ""
        return False, "远程更新禁止使用 HTTP 明文地址，请配置 HTTPS"
    if allow_file is None:
        allow_file = _update_policy_bool(
            app,
            "allow_file_update",
            "XIAMI_UPDATE_ALLOW_FILE_UPDATE",
            False,
        )
    if scheme == "file":
        if bool(allow_file):
            return True, ""
        return False, "file:// 更新仅允许在显式启用的开发模式中使用"
    return False, "更新地址仅支持 HTTPS；localhost HTTP/file 需要显式开发开关"


def canonical_update_manifest(manifest: dict, app: str = "toolbox", channel: str = "stable") -> bytes:
    """Return the exact bytes signed by the update server."""
    source = manifest if isinstance(manifest, dict) else {}
    requested_app = str(app or "toolbox").strip().lower()
    if requested_app not in ("toolbox", "editor"):
        requested_app = "toolbox"
    requested_channel = str(channel or "stable").strip().lower() or "stable"
    normalized = {}
    for key in _SIGNED_MANIFEST_FIELDS:
        if key == "app":
            value = source.get(key) or requested_app
            normalized[key] = str(value or "").strip().lower()
        elif key == "channel":
            value = source.get(key) or requested_channel
            normalized[key] = str(value or "").strip().lower()
        elif key in _SIGNED_MANIFEST_BOOL_FIELDS:
            normalized[key] = _manifest_bool(source.get(key))
        elif key in _SIGNED_MANIFEST_INT_FIELDS:
            try:
                default = 1 if key == "schema_version" else 0
                normalized[key] = int(source.get(key, default) or default)
            except Exception:
                normalized[key] = 1 if key == "schema_version" else 0
        elif key == "sha256":
            normalized[key] = str(source.get(key) or "").strip().lower()
        else:
            normalized[key] = str(source.get(key) or "")
    return json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _parse_explicit_utc_timestamp(value):
    text = str(value or "").strip()
    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)",
        text,
    ):
        return None
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
            return None
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def validate_manifest_declared_size(manifest: dict, required: bool = False) -> tuple[bool, int, str]:
    source = manifest if isinstance(manifest, dict) else {}
    raw = source.get("size")
    if raw in (None, ""):
        if required:
            return False, 0, "签名更新清单缺少有效的安装包 size"
        return True, 0, ""
    if isinstance(raw, bool):
        return False, 0, "更新清单 size 必须是正整数"
    try:
        if isinstance(raw, int):
            size = int(raw)
        else:
            text = str(raw or "").strip()
            if not re.fullmatch(r"\d+", text):
                raise ValueError("invalid size")
            size = int(text)
    except Exception:
        return False, 0, "更新清单 size 必须是正整数"
    if size <= 0:
        if required:
            return False, 0, "签名更新清单 size 必须大于 0"
        return True, 0, ""
    if size > MAX_UPDATE_DOWNLOAD_BYTES:
        return False, size, "更新包声明尺寸超过客户端允许的绝对上限"
    return True, size, ""


def validate_update_download_size(declared_size: int, received_size: int, final: bool = False) -> tuple[bool, str]:
    try:
        declared = int(declared_size or 0)
        received = int(received_size or 0)
    except Exception:
        return False, "更新包尺寸状态无效"
    if received < 0:
        return False, "更新包尺寸状态无效"
    if received > MAX_UPDATE_DOWNLOAD_BYTES:
        return False, "更新包超过客户端允许的绝对上限，已终止下载"
    if declared > 0 and received > declared:
        return False, "更新包已超过清单声明尺寸，已终止下载"
    if final and declared > 0 and received != declared:
        return False, f"更新包尺寸不符：声明 {declared} 字节，实际 {received} 字节"
    return True, ""


def _strict_version_parts(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"\d+(?:\.\d+)*", text):
        return None
    try:
        return tuple(int(part) for part in text.split("."))
    except Exception:
        return None


def _compare_numeric_versions(left, right) -> int:
    left_parts = list(left or ())
    right_parts = list(right or ())
    width = max(len(left_parts), len(right_parts))
    left_parts.extend([0] * (width - len(left_parts)))
    right_parts.extend([0] * (width - len(right_parts)))
    return (left_parts > right_parts) - (left_parts < right_parts)


def validate_min_supported_version(manifest: dict, current_version: str) -> tuple[bool, bool, str]:
    source = manifest if isinstance(manifest, dict) else {}
    minimum_text = str(source.get("min_supported_version") or "").strip()
    if not minimum_text:
        return True, False, ""
    latest_text = str(source.get("latest_version") or "").strip()
    minimum = _strict_version_parts(minimum_text)
    latest = _strict_version_parts(latest_text)
    current = _strict_version_parts(current_version)
    if minimum is None or latest is None:
        return False, False, "更新清单的版本门槛格式无效"
    if current is None:
        return False, False, "当前客户端版本格式无效，无法校验最低支持版本"
    if _compare_numeric_versions(minimum, latest) > 0:
        return False, False, "更新清单的最低支持版本高于最新版本"
    below = _compare_numeric_versions(current, minimum) < 0
    return True, below, ""


def _parse_rsa_public_number(value):
    if isinstance(value, int):
        return int(value)
    text = str(value or "").strip().lower()
    if not text:
        raise ValueError("empty RSA public number")
    if text.startswith("0x"):
        return int(text, 16)
    if any(c in "abcdef" for c in text):
        return int(text, 16)
    return int(text, 10)


def _load_update_manifest_public_keys() -> dict:
    keys = dict(UPDATE_MANIFEST_PUBLIC_KEYS or {})
    # External trust keys are deliberately development-only. Production keys
    # belong in UPDATE_MANIFEST_PUBLIC_KEYS so a writable config cannot replace
    # the trust root.
    if not _manifest_bool(os.environ.get("XIAMI_UPDATE_ALLOW_DEV_TRUST_KEYS", "")):
        return keys
    raw = str(os.environ.get("XIAMI_UPDATE_DEV_PUBLIC_KEYS_JSON", "") or "").strip()
    if not raw:
        return keys
    try:
        extra = json.loads(raw)
        if isinstance(extra, dict):
            keys.update(extra)
    except Exception:
        pass
    return keys


def _verify_rs256_signature(payload: bytes, signature_b64: str, public_key: dict) -> bool:
    try:
        n = _parse_rsa_public_number(public_key.get("n"))
        e = _parse_rsa_public_number(public_key.get("e", 65537))
        if n <= 0 or e <= 1:
            return False
        signature = base64.b64decode(str(signature_b64 or "").encode("ascii"), validate=True)
        width = (n.bit_length() + 7) // 8
        if len(signature) != width:
            return False
        encoded = pow(int.from_bytes(signature, "big"), e, n).to_bytes(width, "big")
        digest_info = _RSA_SHA256_DIGEST_INFO_PREFIX + hashlib.sha256(payload).digest()
        padding_len = width - len(digest_info) - 3
        if padding_len < 8:
            return False
        expected = b"\x00\x01" + (b"\xff" * padding_len) + b"\x00" + digest_info
        return hmac.compare_digest(encoded, expected)
    except Exception:
        return False


def validate_update_manifest_trust(
    manifest: dict,
    app: str = "toolbox",
    channel: str = "stable",
    public_keys=None,
    require_signature=None,
    now_utc=None,
) -> tuple[bool, str, str]:
    """Return (trusted, status, error_or_warning)."""
    if not isinstance(manifest, dict):
        return False, "invalid", "更新清单格式无效"
    requested_app = str(app or "toolbox").strip().lower()
    requested_channel = str(channel or "stable").strip().lower() or "stable"
    required = _manifest_signature_required(requested_app) if require_signature is None else bool(require_signature)
    signature = manifest.get("manifest_signature")
    if signature in (None, "", {}):
        if required:
            return False, "unsigned", "更新清单缺少数字签名，强制模式已拒绝"
        return True, "unsigned_legacy", "当前后台仍使用未签名更新清单，仅按兼容模式检查"
    if not isinstance(signature, dict):
        return False, "invalid", "更新清单签名格式无效"
    alg = str(signature.get("alg") or "").strip().upper()
    key_id = str(signature.get("key_id") or "").strip()
    value = str(signature.get("value") or "").strip()
    if alg != "RS256" or not key_id or not value:
        return False, "invalid", "更新清单签名参数无效"
    actual_app = str(manifest.get("app") or requested_app).strip().lower()
    actual_channel = str(manifest.get("channel") or requested_channel).strip().lower()
    if actual_app != requested_app or actual_channel != requested_channel:
        return False, "invalid", "更新清单的应用或发布通道不匹配"
    key_map = public_keys if isinstance(public_keys, dict) else _load_update_manifest_public_keys()
    public_key = key_map.get(key_id) if isinstance(key_map, dict) else None
    if not isinstance(public_key, dict):
        return False, "unknown_key", f"更新清单使用未知签名密钥：{key_id}"
    payload = canonical_update_manifest(manifest, app=requested_app, channel=requested_channel)
    if not _verify_rs256_signature(payload, value, public_key):
        return False, "invalid", "更新清单数字签名验证失败，已拒绝更新"
    size_ok, _, size_err = validate_manifest_declared_size(manifest, required=True)
    if not size_ok:
        return False, "invalid_size", size_err or "签名更新清单 size 无效"
    expires_text = str(manifest.get("expires_at") or "").strip()
    expires_at = _parse_explicit_utc_timestamp(expires_text)
    if expires_at is None:
        if required:
            detail = "缺少" if not expires_text else "格式无效"
            return False, "invalid_expiry", f"签名更新清单 expires_at {detail}，强制模式已拒绝"
        detail = "缺少" if not expires_text else "格式无效"
        return True, "verified_legacy_expiry", f"签名已验证，但 expires_at {detail}；当前仅按兼容模式接受"
    if now_utc is None:
        current_time = datetime.now(timezone.utc)
    else:
        current_time = now_utc
        if getattr(current_time, "tzinfo", None) is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        current_time = current_time.astimezone(timezone.utc)
    if expires_at <= current_time:
        return False, "expired", "签名更新清单已过期，疑似重放，已拒绝更新"
    return True, "verified", ""


def _manifest_requests_same_version_update(manifest: dict) -> bool:
    if not isinstance(manifest, dict):
        return False
    for key in (
        "same_version_update",
        "force_same_version_update",
        "allow_same_version_update",
        "hot_update",
        "force_hot_update",
    ):
        if _manifest_bool(manifest.get(key)):
            return True
    return False


def fetch_update_manifest(base_url: str, app: str = "toolbox") -> tuple[dict | None, str]:
    try:
        raw_base_url = str(base_url or "").strip()
        if not raw_base_url:
            return None, "未配置服务器地址"
        try:
            base_url = normalize_backend_base_url(raw_base_url, allow_local_http=True)
        except BackendTransportPolicyError as exc:
            return None, "更新服务器地址不安全：{}".format(exc)
        app = str(app or "toolbox").strip().lower()
        if app not in ("toolbox", "editor"):
            app = "toolbox"
        channel = "stable"
        manifest_url = base_url + f"/api/update/latest?app={app}&channel={channel}"
        with build_backend_opener().open(manifest_url, timeout=10) as resp:
            final_manifest_url = str(resp.geturl() or manifest_url)
            final_ok, final_err = validate_update_transport_url(
                final_manifest_url,
                app=app,
                allow_local_http=True,
            )
            if not final_ok:
                return None, final_err or "更新清单发生不安全的地址跳转"
            if not _same_http_origin(base_url, final_manifest_url):
                return None, "更新清单发生跨源地址跳转，已拒绝"
            raw = resp.read().decode("utf-8")
            obj = json.loads(raw)
        if not isinstance(obj, dict) or not obj.get("ok"):
            err = ""
            try:
                err = str(obj.get("error") or "").strip()
            except Exception:
                err = ""
            return None, ("检查更新失败" + (f"：{err}" if err else ""))
        trusted, trust_status, trust_message = validate_update_manifest_trust(
            obj,
            app=app,
            channel=channel,
        )
        if not trusted:
            return None, trust_message or "更新清单未通过信任校验"
        size_ok, declared_size, size_err = validate_manifest_declared_size(
            obj,
            required=isinstance(obj.get("manifest_signature"), dict),
        )
        if not size_ok:
            return None, size_err or "更新清单 size 无效"
        latest = str(obj.get("latest_version") or "").strip()
        min_supported = str(obj.get("min_supported_version") or "").strip()
        download_url = str(obj.get("download_url") or "").strip()
        sha256 = str(obj.get("sha256") or "").strip()
        notes = str(obj.get("release_notes") or "")
        if not latest:
            return None, "未配置在线更新版本信息"
        version_ok, _, version_err = validate_min_supported_version(obj, latest)
        if not version_ok:
            return None, version_err or "更新清单的最低支持版本无效"
        if download_url:
            absolute_download_url = make_absolute_url(base_url, download_url)
            use_backend_transport = _download_uses_backend_transport(
                base_url,
                absolute_download_url,
            )
            download_ok, download_err = validate_update_transport_url(
                absolute_download_url,
                app=app,
                allow_local_http=True if use_backend_transport else None,
            )
            if not download_ok:
                return None, download_err
        manifest = {
            "schema_version": int(obj.get("schema_version") or 1),
            "app": app,
            "channel": channel,
            "latest_version": latest,
            "min_supported_version": min_supported,
            "download_url": download_url,
            "sha256": sha256,
            "size": declared_size,
            "release_notes": notes,
            "published_at": str(obj.get("published_at") or ""),
            "expires_at": str(obj.get("expires_at") or ""),
            "base_url": base_url,
            "_signature_status": trust_status,
            "_signature_warning": trust_message or "",
        }
        if isinstance(obj.get("manifest_signature"), dict):
            manifest["manifest_signature"] = dict(obj.get("manifest_signature") or {})
        for key in (
            "same_version_update",
            "force_same_version_update",
            "allow_same_version_update",
            "hot_update",
            "force_hot_update",
        ):
            if key in obj:
                manifest[key] = obj.get(key)
        return (manifest, "")
    except Exception as e:
        return None, f"检查更新失败：{e}"


class UpdateCheckWorker(QtCore.QObject):
    finished = QtCore.Signal(object, str)

    def __init__(self, base_url: str, current_version: str, app: str = "toolbox") -> None:
        super().__init__()
        self._base_url = str(base_url or "").strip()
        self._current_version = str(current_version or "").strip() or "0.0"
        self._app = str(app or "toolbox").strip().lower()
        if self._app not in ("toolbox", "editor"):
            self._app = "toolbox"

    @QtCore.Slot()
    def run(self) -> None:
        manifest, err = fetch_update_manifest(self._base_url, app=self._app)
        if err or not manifest:
            self.finished.emit(None, err or "检查更新失败")
            return
        latest = str(manifest.get("latest_version") or "0.0").strip()
        if not latest or latest == "0.0":
            self.finished.emit(None, "未配置在线更新版本信息")
            return
        version_ok, below_minimum, version_err = validate_min_supported_version(
            manifest,
            self._current_version,
        )
        if not version_ok:
            self.finished.emit(None, version_err or "最低支持版本校验失败")
            return
        if below_minimum:
            manifest["_mandatory_update"] = True
            manifest["_minimum_supported_version"] = str(
                manifest.get("min_supported_version") or ""
            ).strip()
            self.finished.emit(
                {"state": "update_available", "current": self._current_version, "manifest": manifest},
                "",
            )
            return
        cmp = compare_versions(latest, self._current_version)
        if cmp <= 0:
            sha256 = str(manifest.get("sha256") or "").strip()
            if cmp == 0 and sha256:
                bootstrap = load_bootstrap(self._app) or {}
                preferred_sha256 = str(bootstrap.get("preferred_sha256") or "").strip()
                install_dir = _current_install_dir()
                local_state = load_local_update_state(install_dir)
                local_sha256 = str(local_state.get("preferred_sha256") or "").strip()
                matched = False
                if preferred_sha256.lower() == sha256.lower():
                    matched = True
                elif local_sha256.lower() == sha256.lower():
                    matched = True
                    merged = dict(bootstrap)
                    merged["preferred_sha256"] = sha256
                    merged["preferred_version"] = latest
                    merged["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    save_bootstrap(self._app, merged)
                if (not matched) and _manifest_requests_same_version_update(manifest):
                    try:
                        manifest["_same_version_update"] = True
                    except Exception:
                        pass
                    self.finished.emit({"state": "update_available", "current": self._current_version, "manifest": manifest}, "")
                    return
            self.finished.emit({"state": "up_to_date", "current": self._current_version, "latest": latest}, "")
            return
        self.finished.emit({"state": "update_available", "current": self._current_version, "manifest": manifest}, "")


class HeartbeatWorker(QtCore.QObject):
    finished = QtCore.Signal(str, object)

    def __init__(self, base_url: str, token: str, device_id: str) -> None:
        super().__init__()
        self._base_url = str(base_url or "").strip().rstrip("/")
        self._token = str(token or "").strip()
        self._device_id = str(device_id or "").strip()

    @QtCore.Slot()
    def run(self) -> None:
        status = "offline"
        http_code = None
        try:
            if not self._base_url or not self._token:
                self.finished.emit("no_session", None)
                return
            url = self._base_url + "/api/heartbeat"
            headers = {"Authorization": "Bearer " + self._token}
            if self._device_id:
                headers["X-Device-Id"] = self._device_id
            req = urllib.request.Request(url, headers=headers)
            backend_urlopen(req, timeout=5, allow_local_http=True).read()
            status = "ok"
        except urllib.error.HTTPError as e:
            http_code = getattr(e, "code", None)
            status = "http_error"
        except Exception:
            status = "offline"
        self.finished.emit(status, http_code)


class ClientConfigWorker(QtCore.QObject):
    finished = QtCore.Signal(object)

    def __init__(self, base_url: str, token: str) -> None:
        super().__init__()
        self._base_url = str(base_url or "").strip().rstrip("/")
        self._token = str(token or "").strip()

    @QtCore.Slot()
    def run(self) -> None:
        if not self._base_url:
            self.finished.emit({"ok": False, "error": "服务器地址为空"})
            return
        url = self._base_url + "/api/client_config"
        headers = {}
        if self._token:
            headers["Authorization"] = "Bearer " + self._token
        req = urllib.request.Request(url, headers=headers)
        try:
            raw = backend_urlopen(
                req,
                timeout=5,
                allow_local_http=True,
            ).read().decode("utf-8", "ignore")
            obj = json.loads(raw) if raw else {}
            if isinstance(obj, dict):
                self.finished.emit(obj)
                return
            self.finished.emit({"ok": False, "error": "返回数据格式错误"})
            return
        except urllib.error.HTTPError as e:
            code = getattr(e, "code", None)
            msg = f"HTTP {code}" if code else "HTTP错误"
            self.finished.emit({"ok": False, "error": msg, "http_code": code})
            return
        except Exception as e:
            msg = str(e or "").strip()
            self.finished.emit({"ok": False, "error": msg or "无法连接服务器"})
            return


def toolbox_update_base_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "XiamiToolbox")


def editor_update_base_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "XiamiAIEditor")


def update_base_dir(app: str) -> str:
    a = str(app or "toolbox").strip().lower()
    if a == "editor":
        return editor_update_base_dir()
    return toolbox_update_base_dir()


def _bootstrap_file_path(app: str) -> str:
    return os.path.join(update_base_dir(app), "bootstrap.json")


def load_bootstrap(app: str) -> dict:
    try:
        p = _bootstrap_file_path(app)
        if not os.path.exists(p):
            return {}
        # PowerShell Set-Content may write UTF-8 with BOM on some systems.
        # Accept both BOM and plain UTF-8 so a successful update is recognized after restart.
        with open(p, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_bootstrap(app: str, d: dict) -> bool:
    try:
        base = update_base_dir(app)
        os.makedirs(base, exist_ok=True)
        p = _bootstrap_file_path(app)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d or {}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False



def _toolbox_bootstrap_file_path() -> str:
    return os.path.join(toolbox_update_base_dir(), "bootstrap.json")


def load_toolbox_bootstrap() -> dict:
    return load_bootstrap("toolbox")


def save_toolbox_bootstrap(d: dict) -> bool:
    return save_bootstrap("toolbox", d or {})


def _update_state_file_path(install_dir: str) -> str:
    return os.path.join(str(install_dir or ""), "update_state.json")


def load_local_update_state(install_dir: str) -> dict:
    try:
        p = _update_state_file_path(install_dir)
        if not os.path.exists(p):
            return {}
        with open(p, "r", encoding="utf-8-sig") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_local_update_state(install_dir: str, d: dict) -> bool:
    try:
        p = _update_state_file_path(install_dir)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d or {}, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def _current_install_dir() -> str:
    try:
        if getattr(sys, "frozen", False):
            return os.path.abspath(os.path.dirname(sys.executable))
    except Exception:
        pass
    try:
        return os.path.abspath(os.getcwd())
    except Exception:
        return ""


def find_exe_in_dir(root_dir: str, preferred_names: list[str] | None = None) -> str:
    try:
        root_dir = os.path.abspath(str(root_dir or ""))
    except Exception:
        return ""
    if not root_dir or (not os.path.isdir(root_dir)):
        return ""
    preferred: list[str] = []
    seen = set()
    for value in preferred_names or []:
        name = os.path.basename(str(value or "").strip())
        key = name.casefold()
        if not name or not name.lower().endswith(".exe") or key in seen:
            continue
        seen.add(key)
        preferred.append(name)
    if not preferred:
        return ""
    try:
        direct_files = {
            entry.name.casefold(): entry.path
            for entry in os.scandir(root_dir)
            if entry.is_file(follow_symlinks=False)
        }
    except OSError:
        return ""
    for name in preferred:
        candidate = direct_files.get(name.casefold())
        if candidate:
            return os.path.abspath(candidate)
    return ""


_WINDOWS_RESERVED_PATH_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def _validate_zip_member_name(name_norm: str) -> None:
    if "\x00" in name_norm:
        raise RuntimeError("更新包包含异常路径，已终止解压")
    parts = name_norm.split("/")
    for index, part in enumerate(parts):
        if not part:
            if index == len(parts) - 1 and name_norm.endswith("/"):
                continue
            raise RuntimeError("更新包包含异常路径，已终止解压")
        if part in {".", ".."} or ":" in part or part.endswith((" ", ".")):
            raise RuntimeError("更新包包含 Windows 特殊路径，已终止解压")
        stem = part.split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED_PATH_NAMES:
            raise RuntimeError("更新包包含 Windows 保留路径，已终止解压")


def _validate_zip_archive(z, dest_dir: str) -> None:
    base_abs = os.path.abspath(dest_dir)
    base_abs_norm = os.path.normcase(base_abs.rstrip("\\/") + os.sep)
    entries = z.infolist()
    if len(entries) > MAX_UPDATE_ZIP_ENTRIES:
        raise RuntimeError("更新包文件数量超出限制")
    expanded_total = 0
    destinations = set()
    for info in entries:
        name = str(getattr(info, "filename", "") or "")
        if not name:
            continue
        name_norm = name.replace("\\", "/")
        if name_norm.startswith("/") or name_norm.startswith("../") or "/../" in name_norm:
            raise RuntimeError("更新包包含异常路径，已终止解压")
        if re.match(r"^[a-zA-Z]:", name_norm):
            raise RuntimeError("更新包包含异常路径，已终止解压")
        _validate_zip_member_name(name_norm)
        dest_path = os.path.abspath(os.path.join(dest_dir, name_norm))
        dest_norm = os.path.normcase(dest_path)
        if not (dest_norm == os.path.normcase(base_abs) or dest_norm.startswith(base_abs_norm)):
            raise RuntimeError("更新包包含异常路径，已终止解压")
        destination_key = dest_norm.rstrip("\\/")
        if destination_key in destinations:
            raise RuntimeError("更新包包含重复路径，已终止解压")
        destinations.add(destination_key)
        if int(getattr(info, "flag_bits", 0) or 0) & 0x1:
            raise RuntimeError("更新包包含加密文件，已终止解压")
        unix_mode = (int(getattr(info, "external_attr", 0) or 0) >> 16) & 0xFFFF
        file_type = unix_mode & 0o170000
        if file_type not in {0, 0o040000, 0o100000}:
            raise RuntimeError("更新包包含不支持的特殊文件，已终止解压")
        if getattr(info, "is_dir", None) and info.is_dir():
            continue
        file_size = int(getattr(info, "file_size", -1))
        compressed_size = int(getattr(info, "compress_size", -1))
        if file_size < 0 or compressed_size < 0:
            raise RuntimeError("更新包文件尺寸无效")
        if file_size > MAX_UPDATE_ZIP_ENTRY_BYTES:
            raise RuntimeError("更新包包含超大单文件，已终止解压")
        expanded_total += file_size
        if expanded_total > MAX_UPDATE_ZIP_EXPANDED_BYTES:
            raise RuntimeError("更新包展开总量超出限制")
        if file_size > 0 and compressed_size == 0:
            raise RuntimeError("更新包文件压缩尺寸无效")
        if (
            file_size >= _UPDATE_ZIP_RATIO_MIN_BYTES
            and file_size > compressed_size * MAX_UPDATE_ZIP_COMPRESSION_RATIO
        ):
            raise RuntimeError("更新包文件压缩比异常，已终止解压")


def _windows_expand_archive(zip_path: str, dest_dir: str) -> None:
    cmd = "Expand-Archive -LiteralPath '{}' -DestinationPath '{}' -Force".format(
        str(zip_path or "").replace("'", "''"),
        str(dest_dir or "").replace("'", "''"),
    )
    kwargs: dict = {
        "check": True,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "ignore",
    }
    if os.name == "nt":
        try:
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        except Exception:
            pass
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", cmd],
        **kwargs,
    )


def safe_extract_zip(z, dest_dir: str) -> None:
    _validate_zip_archive(z, dest_dir)
    expanded_total = 0
    extracted_files = 0
    for info in z.infolist():
        name = str(getattr(info, "filename", "") or "")
        if not name:
            continue
        name_norm = name.replace("\\", "/")
        dest_path = os.path.abspath(os.path.join(dest_dir, name_norm))
        if getattr(info, "is_dir", None) and info.is_dir():
            os.makedirs(dest_path, exist_ok=True)
            continue
        extracted_files += 1
        if extracted_files > MAX_UPDATE_ZIP_ENTRIES:
            raise RuntimeError("更新包文件数量超出限制")
        parent_dir = os.path.dirname(dest_path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with z.open(info, "r") as src, open(dest_path, "wb") as out:
            entry_total = 0
            while True:
                chunk = src.read(1024 * 1024)
                if not chunk:
                    break
                entry_total += len(chunk)
                expanded_total += len(chunk)
                if entry_total > MAX_UPDATE_ZIP_ENTRY_BYTES:
                    raise RuntimeError("更新包单文件实际展开量超出限制")
                if expanded_total > MAX_UPDATE_ZIP_EXPANDED_BYTES:
                    raise RuntimeError("更新包实际展开总量超出限制")
                if entry_total > int(getattr(info, "file_size", 0)):
                    raise RuntimeError("更新包实际展开尺寸与目录记录不一致")
                out.write(chunk)
            if entry_total != int(getattr(info, "file_size", 0)):
                raise RuntimeError("更新包文件展开不完整")


def _choose_update_work_base_dir(app: str, install_dir: str) -> str:
    try:
        install_dir = os.path.abspath(str(install_dir or ""))
    except Exception:
        install_dir = ""

    def is_inside_install(candidate: str) -> bool:
        if not install_dir:
            return False
        try:
            return os.path.commonpath([install_dir, candidate]) == install_dir
        except (OSError, ValueError):
            return True

    candidates = [update_base_dir(app)]
    if install_dir:
        install_parent = os.path.dirname(install_dir)
        install_name = os.path.basename(install_dir.rstrip("\\/")) or str(app or "toolbox")
        candidates.append(os.path.join(install_parent, f".{install_name}.xiami-update"))
    candidates.append(os.path.join(tempfile.gettempdir(), "XiamiUpdate", str(app or "toolbox")))

    seen = set()
    for candidate in candidates:
        try:
            candidate = os.path.abspath(str(candidate or ""))
        except Exception:
            continue
        key = os.path.normcase(candidate)
        if not candidate or key in seen or is_inside_install(candidate):
            continue
        seen.add(key)
        try:
            os.makedirs(candidate, exist_ok=True)
            test = os.path.join(candidate, f".w_{uuid.uuid4().hex}")
            with open(test, "wb") as f:
                f.write(b"1")
            os.remove(test)
            return candidate
        except Exception:
            continue
    raise RuntimeError("找不到位于工具安装目录外的可写更新工作目录")


def _sidecar_pkg_name(exe_name: str) -> str:
    base = os.path.splitext(os.path.basename(str(exe_name or "").strip()))[0]
    if not base:
        return ""
    return base + ".pkg"


def _validate_payload_runtime(payload_exe_path: str, install_dir: str) -> tuple[bool, str]:
    try:
        payload_exe_path = os.path.abspath(str(payload_exe_path or ""))
        install_dir = os.path.abspath(str(install_dir or ""))
    except Exception:
        return False, "更新包路径无效"
    if not payload_exe_path or not os.path.isfile(payload_exe_path):
        return False, "未在更新包中找到可执行文件"
    exe_name = os.path.basename(payload_exe_path)
    pkg_name = _sidecar_pkg_name(exe_name)
    if not pkg_name:
        return True, ""
    payload_pkg = os.path.join(os.path.dirname(payload_exe_path), pkg_name)
    install_pkg = os.path.join(install_dir, pkg_name)
    payload_has_pkg = os.path.isfile(payload_pkg)
    install_has_pkg = os.path.isfile(install_pkg)
    if install_has_pkg and (not payload_has_pkg):
        return False, f"更新包缺少关键运行文件：{pkg_name}"
    if payload_has_pkg:
        try:
            if os.path.getsize(payload_pkg) <= 0:
                return False, f"更新包关键运行文件损坏：{pkg_name}"
        except Exception:
            return False, f"更新包关键运行文件不可读：{pkg_name}"
    return True, ""


def update_keep_paths(app: str) -> tuple[list[str], list[str]]:
    app = str(app or "toolbox").strip().lower()
    if app == "editor":
        return (
            [
                "ai_config.json",
                "editor_config.json",
                "toolbox_login.json",
                "toolbox_size_preferences.json",
                "user_commands.json",
                "Config.ini",
            ],
            [],
        )
    return (
        [
            "toolbox_login.json",
            "toolbox_size_preferences.json",
            "auth_settings.json",
            "auth_users.json",
            "script_templates_store.json",
            "data\\script_templates_store.json",
            "item_templates_store.json",
            "data\\item_templates_store.json",
            "recycle_settings.json",
            "micro_client_configs.json",
            "data\\micro_client_configs.json",
            "Config.ini",
            "存销系统配置.json",
            "源码修改备份规则.txt",
        ],
        [
            "微端配置目录",
            "微端配置",
            "micro_configs",
            "micro_client_configs",
            "embedded_xiami\\runtime\\xiami_v1",
            "_internal\\embedded_xiami\\runtime\\xiami_v1",
            "runtime\\xiami_v1",
            "_internal\\微端配置目录",
            "_internal\\微端配置",
            "_internal\\micro_configs",
            "_internal\\micro_client_configs",
        ],
    )


def discover_update_plugin_config_paths(install_dir: str) -> list[str]:
    try:
        base = os.path.abspath(str(install_dir or ""))
    except Exception:
        return []
    if not base or not os.path.isdir(base):
        return []
    result: list[str] = []
    for rel_root in (
        "embedded_xiami\\xiami_plugins",
        "_internal\\embedded_xiami\\xiami_plugins",
    ):
        plugin_root = os.path.join(base, rel_root)
        if not os.path.isdir(plugin_root) or os.path.islink(plugin_root):
            continue
        try:
            children = list(os.scandir(plugin_root))
        except OSError:
            continue
        for child in children:
            try:
                if not child.is_dir(follow_symlinks=False):
                    continue
                config_path = os.path.join(child.path, "plugin_config.json")
                if not os.path.isfile(config_path) or os.path.islink(config_path):
                    continue
                relative = os.path.relpath(config_path, base).replace("/", "\\")
            except (OSError, ValueError):
                continue
            if relative.startswith("..\\") or os.path.isabs(relative):
                continue
            result.append(relative)
    return sorted(set(result), key=str.casefold)


def build_keep_commands(
    keep_files: list[str],
    keep_dirs: list[str] | None = None,
    *,
    restore_root_var: str = "DST",
) -> tuple[list[str], list[str]]:
    pre_keep: list[str] = []
    post_keep: list[str] = []
    restore_var = str(restore_root_var or "").strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,31}", restore_var):
        raise ValueError("invalid update restore root variable")
    restore_root = f"%{restore_var}%"

    for fn in keep_files or []:
        try:
            rel = str(fn or "").replace("/", "\\").strip("\\")
        except Exception:
            rel = ""
        if not rel:
            continue
        try:
            d = os.path.dirname(rel).strip("\\")
        except Exception:
            d = ""
        if d:
            pre_keep.append(f"if not exist \"%KEEP%\\{d}\" mkdir \"%KEEP%\\{d}\" >nul 2>nul")
        pre_keep.append(f"if exist \"%DST%\\{rel}\" copy /y \"%DST%\\{rel}\" \"%KEEP%\\{rel}\" >nul 2>nul")
        pre_keep.append(f"if exist \"%DST%\\{rel}\" if errorlevel 1 goto prepare_failed")
        if d:
            post_keep.append(f"if not exist \"{restore_root}\\{d}\" mkdir \"{restore_root}\\{d}\" >nul 2>nul")
        post_keep.append(f"if exist \"%KEEP%\\{rel}\" copy /y \"%KEEP%\\{rel}\" \"{restore_root}\\{rel}\" >nul 2>nul")
        post_keep.append(f"if exist \"%KEEP%\\{rel}\" if errorlevel 1 goto prepare_failed")

    for dn in keep_dirs or []:
        try:
            rel = str(dn or "").replace("/", "\\").strip("\\")
        except Exception:
            rel = ""
        if not rel:
            continue
        pre_keep.append(
            f"if exist \"%DST%\\{rel}\" robocopy \"%DST%\\{rel}\" \"%KEEP%\\{rel}\" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul"
        )
        pre_keep.append(f"if exist \"%DST%\\{rel}\" if errorlevel 8 goto prepare_failed")
        post_keep.append(
            f"if exist \"%KEEP%\\{rel}\" robocopy \"%KEEP%\\{rel}\" \"{restore_root}\\{rel}\" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul"
        )
        post_keep.append(f"if exist \"%KEEP%\\{rel}\" if errorlevel 8 goto prepare_failed")

    return pre_keep, post_keep


def update_retired_paths(app: str) -> tuple[str, ...]:
    if str(app or "toolbox").strip().lower() == "editor":
        return ()
    return ("resources\\free_micro_client\\PasswordWorker.ps1",)


def _build_atomic_install_commands(
    pre_keep: list[str],
    post_keep: list[str],
    retired_paths: tuple[str, ...],
    *,
    full_payload: bool,
    success_commands: list[str],
) -> list[str]:
    commands = [
        "set \"NEW=%DST%.xiami-new-%PID%\"",
        "set \"OLD=%DST%.xiami-old-%PID%\"",
        "set \"KEEP=%TMP%.keep\"",
        "if exist \"%NEW%\" rmdir /s /q \"%NEW%\" >nul 2>nul",
        "if exist \"%OLD%\" rmdir /s /q \"%OLD%\" >nul 2>nul",
        "if exist \"%KEEP%\" rmdir /s /q \"%KEEP%\" >nul 2>nul",
        "if exist \"%NEW%\" exit /b 20",
        "if exist \"%OLD%\" exit /b 20",
        "if exist \"%KEEP%\" exit /b 20",
        "mkdir \"%KEEP%\" >nul 2>nul",
        "if errorlevel 1 exit /b 20",
        *pre_keep,
    ]
    if full_payload:
        commands.extend(
            [
                "robocopy \"%SRC%\" \"%NEW%\" /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul",
                "if errorlevel 8 goto prepare_failed",
            ]
        )
    else:
        commands.extend(
            [
                "robocopy \"%DST%\" \"%NEW%\" /MIR /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul",
                "if errorlevel 8 goto prepare_failed",
                "robocopy \"%SRC%\" \"%NEW%\" /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NJH /NJS /NP >nul",
                "if errorlevel 8 goto prepare_failed",
            ]
        )
    commands.extend(post_keep)
    for value in retired_paths:
        rel = str(value or "").replace("/", "\\").strip("\\")
        if not rel or os.path.isabs(rel) or rel.startswith("..") or "\\..\\" in f"\\{rel}\\":
            raise ValueError("invalid retired update path")
        commands.extend(
            [
                f"if exist \"%NEW%\\{rel}\" del /f /q \"%NEW%\\{rel}\" >nul 2>nul",
                f"if exist \"%NEW%\\{rel}\" goto invalid_payload",
            ]
        )
    commands.extend(
        [
            "if not exist \"%NEW%\\%EXE%\" goto invalid_payload",
            "cd /d \"%DST%\\..\"",
            "if errorlevel 1 goto swap_source_failed",
            "move \"%DST%\" \"%OLD%\" >nul 2>nul",
            "if errorlevel 1 goto swap_source_failed",
            "move \"%NEW%\" \"%DST%\" >nul 2>nul",
            "if errorlevel 1 goto swap_target_failed",
            *success_commands,
            "if exist \"%OLD%\" rmdir /s /q \"%OLD%\" >nul 2>nul",
            "if exist \"%KEEP%\" rmdir /s /q \"%KEEP%\" >nul 2>nul",
            "if exist \"%PKG%\" del /f /q \"%PKG%\" >nul 2>nul",
            "if exist \"%TMP%\" rmdir /s /q \"%TMP%\" >nul 2>nul",
            "if exist \"%DST%\\%EXE%\" start \"\" \"%DST%\\%EXE%\"",
            "start \"\" /b cmd.exe /c del /f /q \"%~f0\" >nul 2>nul",
            "exit /b 0",
            ":invalid_payload",
            "set RC=21",
            "goto prepare_cleanup",
            ":prepare_failed",
            "set RC=%ERRORLEVEL%",
            ":prepare_cleanup",
            "if exist \"%NEW%\" rmdir /s /q \"%NEW%\" >nul 2>nul",
            "if exist \"%KEEP%\" rmdir /s /q \"%KEEP%\" >nul 2>nul",
            "exit /b %RC%",
            ":swap_source_failed",
            "if exist \"%NEW%\" rmdir /s /q \"%NEW%\" >nul 2>nul",
            "if exist \"%KEEP%\" rmdir /s /q \"%KEEP%\" >nul 2>nul",
            "exit /b 30",
            ":swap_target_failed",
            "move \"%OLD%\" \"%DST%\" >nul 2>nul",
            "if errorlevel 1 exit /b 32",
            "if exist \"%NEW%\" rmdir /s /q \"%NEW%\" >nul 2>nul",
            "if exist \"%KEEP%\" rmdir /s /q \"%KEEP%\" >nul 2>nul",
            "exit /b 31",
        ]
    )
    return commands


def _is_supported_download_url(url: str, app: str = "toolbox") -> bool:
    ok, _ = validate_update_transport_url(url, app=app)
    return bool(ok)


def _ps_single_quote(s: str) -> str:
    try:
        return str(s or "").replace("'", "''")
    except Exception:
        return ""


def _to_b64_utf8(s: str) -> str:
    try:
        return __import__("base64").b64encode(str(s or "").encode("utf-8")).decode("ascii")
    except Exception:
        return ""


def _to_b64_utf16le(s: str) -> str:
    try:
        return __import__("base64").b64encode(str(s or "").encode("utf-16le")).decode("ascii")
    except Exception:
        return ""


class UpdateDownloadWorker(QtCore.QObject):
    progress = QtCore.Signal(int, str)
    finished = QtCore.Signal(object, str)

    def __init__(self, manifest: dict, cancel_flag: dict, current_version: str) -> None:
        super().__init__()
        self._manifest = dict(manifest or {})
        self._cancel_flag = cancel_flag
        self._current_version = str(current_version or "").strip()

    @QtCore.Slot()
    def run(self) -> None:
        try:
            app = str(self._manifest.get("app") or self._manifest.get("_update_app") or "toolbox").strip().lower()
            if app not in ("toolbox", "editor"):
                app = "toolbox"
            channel = str(self._manifest.get("channel") or "stable").strip().lower() or "stable"
            trusted, _, trust_err = validate_update_manifest_trust(
                self._manifest,
                app=app,
                channel=channel,
            )
            if not trusted:
                self.finished.emit(None, trust_err or "更新清单未通过信任校验")
                return
            size_ok, declared_size, size_err = validate_manifest_declared_size(
                self._manifest,
                required=isinstance(self._manifest.get("manifest_signature"), dict),
            )
            if not size_ok:
                self.finished.emit(None, size_err or "更新清单 size 无效")
                return
            latest = str(self._manifest.get("latest_version") or "").strip()
            version_ok, _, version_err = validate_min_supported_version(
                self._manifest,
                self._current_version,
            )
            if not version_ok:
                self.finished.emit(None, version_err or "最低支持版本校验失败")
                return
            dl = str(self._manifest.get("download_url") or "").strip()
            sha256_expected = str(self._manifest.get("sha256") or "").strip()
            base_url = str(self._manifest.get("base_url") or "").strip()
            download_base_url = base_url
            if download_base_url:
                try:
                    download_base_url = normalize_backend_base_url(
                        download_base_url,
                        allow_local_http=True,
                    )
                except BackendTransportPolicyError:
                    pass
            dl = make_absolute_url(download_base_url, dl)
            dl = normalize_http_url(dl)
            if not getattr(sys, "frozen", False):
                self.finished.emit(None, "当前是源码运行模式，已禁用覆盖式自动更新。请使用打包版工具箱执行在线更新。")
                return
            use_backend_transport = _download_uses_backend_transport(
                download_base_url,
                dl,
            )
            if dl:
                transport_ok, transport_err = validate_update_transport_url(
                    dl,
                    app=app,
                    allow_local_http=True if use_backend_transport else None,
                )
            else:
                transport_ok, transport_err = False, "未配置下载地址（download_url）"
            if dl and (not transport_ok):
                self.finished.emit(None, transport_err or "更新下载地址未通过安全校验")
                return
            if dl and (not str(sha256_expected or "").strip()):
                self.finished.emit(None, "更新清单缺少 SHA256 校验值，已阻止自动更新。")
                return
            if not dl:
                self.finished.emit(None, "未配置下载地址（download_url）")
                return

            ua = "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36"
            headers = {"User-Agent": ua, "Accept": "*/*", "Connection": "close"}

            is_exe = dl.lower().endswith(".exe")
            self.progress.emit(0, "准备更新...")

            cur_exe = ""
            install_dir = ""
            exe_name = ""
            try:
                cur_exe = os.path.abspath(sys.executable)
                install_dir = os.path.abspath(os.path.dirname(cur_exe))
                exe_name = os.path.basename(cur_exe)

                base_dir = os.path.normcase(os.path.abspath(update_base_dir(app)).rstrip("\\/") + os.sep)
                cur_norm = os.path.normcase(os.path.abspath(cur_exe))
                if cur_norm.startswith(base_dir):
                    bootstrap = load_bootstrap(app) or {}
                    preferred_exe = str(bootstrap.get("preferred_exe") or "").strip()
                    if preferred_exe:
                        preferred_dir = os.path.abspath(os.path.dirname(preferred_exe))
                        if os.path.isdir(preferred_dir):
                            install_dir = preferred_dir
                            exe_name = os.path.basename(preferred_exe) or exe_name
            except Exception:
                cur_exe = ""
                install_dir = os.path.abspath(os.getcwd())
                exe_name = "XiamiToolbox.exe"

            try:
                test_file = os.path.join(install_dir, f".update_write_test_{uuid.uuid4().hex}.tmp")
                with open(test_file, "w", encoding="utf-8") as tf:
                    tf.write("ok")
                os.remove(test_file)
            except Exception:
                self.finished.emit(None, "当前工具目录无写入权限，无法覆盖安装。\n请以管理员运行，或将工具放到可写目录（如 D 盘）后再更新。")
                return

            work_base = _choose_update_work_base_dir(app, install_dir)
            downloads = os.path.join(work_base, "downloads")
            staging = os.path.join(work_base, "staging")
            os.makedirs(downloads, exist_ok=True)
            os.makedirs(staging, exist_ok=True)

            download_path = os.path.join(downloads, f"{app}_{latest or 'latest'}" + (".exe" if is_exe else ".zip"))
            self.progress.emit(0, "下载更新包...")

            def remove_partial_download() -> None:
                try:
                    if os.path.exists(download_path):
                        os.remove(download_path)
                except Exception:
                    pass

            remove_partial_download()

            req = urllib.request.Request(dl, headers=headers)
            download_size_error = ""
            got = 0
            response = _open_update_download(
                req,
                timeout=15,
                use_backend_transport=use_backend_transport,
            )
            with response as resp:
                final_download_url = str(resp.geturl() or dl)
                final_ok, final_err = validate_update_transport_url(
                    final_download_url,
                    app=app,
                    allow_local_http=True if use_backend_transport else None,
                )
                if not final_ok:
                    self.finished.emit(None, final_err or "更新下载发生不安全的地址跳转")
                    return
                if use_backend_transport and not _same_http_origin(
                    download_base_url,
                    final_download_url,
                ):
                    self.finished.emit(None, "后端更新下载发生跨源地址跳转，已拒绝")
                    return
                try:
                    total = int(resp.headers.get("Content-Length") or 0)
                except Exception:
                    total = 0
                if total > 0:
                    announced_ok, announced_err = validate_update_download_size(
                        declared_size,
                        total,
                        final=True,
                    )
                    if not announced_ok:
                        self.finished.emit(None, announced_err or "更新包响应尺寸无效")
                        return
                last_ui = 0.0
                with open(download_path, "wb") as f:
                    while True:
                        if self._cancel_flag.get("v"):
                            break
                        chunk = resp.read(1024 * 64)
                        if not chunk:
                            break
                        next_size = got + len(chunk)
                        stream_ok, stream_err = validate_update_download_size(
                            declared_size,
                            next_size,
                            final=False,
                        )
                        if not stream_ok:
                            download_size_error = stream_err or "更新包下载尺寸超限"
                            break
                        f.write(chunk)
                        got = next_size
                        now = time.time()
                        if now - last_ui >= 0.2:
                            last_ui = now
                            if total > 0:
                                # 下载占进度条 0-DOWNLOAD_PCT，其余留给校验/解压，
                                # 避免下载一结束就顶到 100 之后长时间不动。
                                pct = int(max(0.0, min(1.0, got / total)) * _DOWNLOAD_PCT)
                                shown = int(max(0.0, min(100.0, got * 100.0 / total)))
                                self.progress.emit(pct, f"下载中...{shown}%")
                            else:
                                mb = round(got / 1024 / 1024, 2)
                                self.progress.emit(0, f"下载中...{mb} MB")
                # 循环按 0.2s 节流发进度，最后一个分块往往赶不上一次发送，
                # 这里补一次，否则进度条会停在最后一次采样值（常见 9x%）不动。
                if not self._cancel_flag.get("v") and not download_size_error:
                    self.progress.emit(_DOWNLOAD_PCT, "下载完成")

            if download_size_error:
                remove_partial_download()
                self.finished.emit(None, download_size_error)
                return

            if self._cancel_flag.get("v"):
                remove_partial_download()
                self.finished.emit(None, "已取消下载")
                return

            complete_ok, complete_err = validate_update_download_size(
                declared_size,
                got,
                final=True,
            )
            if not complete_ok:
                remove_partial_download()
                self.finished.emit(None, complete_err or "更新包最终尺寸校验失败")
                return

            if sha256_expected:
                self.progress.emit(_DOWNLOAD_PCT, "校验文件...")
                try:
                    h = hashlib.sha256()
                    verified = 0
                    verify_total = 0
                    try:
                        verify_total = os.path.getsize(download_path)
                    except Exception:
                        verify_total = 0
                    last_verify_ui = 0.0
                    with open(download_path, "rb") as f:
                        for chunk in iter(lambda: f.read(1024 * 1024), b""):
                            h.update(chunk)
                            verified += len(chunk)
                            now = time.time()
                            if verify_total > 0 and now - last_verify_ui >= 0.2:
                                last_verify_ui = now
                                span = _VERIFY_PCT - _DOWNLOAD_PCT
                                self.progress.emit(
                                    _DOWNLOAD_PCT + int(min(1.0, verified / verify_total) * span),
                                    "校验文件...",
                                )
                    sha256_actual = h.hexdigest()
                except Exception:
                    sha256_actual = ""
                self.progress.emit(_VERIFY_PCT, "校验完成")
                if sha256_actual.lower() != sha256_expected.lower():
                    self.finished.emit(
                        None,
                        f"更新包校验失败\n期望 SHA256：{sha256_expected}\n实际 SHA256：{sha256_actual}",
                    )
                    return

            tmp_dir = os.path.join(staging, f"{app}_{latest or 'latest'}_tmp")
            try:
                if os.path.exists(tmp_dir):
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass
            os.makedirs(tmp_dir, exist_ok=True)

            payload_dir = tmp_dir
            exe_path = os.path.join(install_dir, exe_name)
            payload_exe_path = os.path.join(payload_dir, exe_name)

            if is_exe:
                self.progress.emit(_VERIFY_PCT, "写入更新文件...")
                try:
                    shutil.copy2(download_path, os.path.join(tmp_dir, exe_name))
                except Exception as e:
                    self.finished.emit(None, f"写入更新文件失败：{e}")
                    return
                payload_exe_path = os.path.join(tmp_dir, exe_name)
                self.progress.emit(_EXTRACT_PCT, "写入完成")
            else:
                import zipfile as _zf

                if not _zf.is_zipfile(download_path):
                    head = b""
                    try:
                        with open(download_path, "rb") as hf:
                            head = hf.read(64)
                    except Exception:
                        head = b""
                    self.finished.emit(None, f"更新包格式无效（不是 zip）\n文件头：{head.hex()}")
                    return
                self.progress.emit(_VERIFY_PCT, "解压安装包...（大包较慢，请勿关闭）")
                with _zf.ZipFile(download_path, "r") as z:
                    safe_extract_zip(z, tmp_dir)
                self.progress.emit(_EXTRACT_PCT, "解压完成")

                payload_dir = tmp_dir
                try:
                    candidates = ["虾米工具箱"] if app != "editor" else ["虾米AI编辑器", "XiamiAIEditor", "AIEditor"]
                    for c in candidates:
                        sub = os.path.join(tmp_dir, c)
                        if os.path.isdir(sub):
                            payload_dir = sub
                            break
                except Exception:
                    payload_dir = tmp_dir

                preferred_names: list[str] = []
                try:
                    if getattr(sys, "frozen", False):
                        preferred_names.append(os.path.basename(sys.executable))
                except Exception:
                    pass
                if app == "editor":
                    preferred_names.extend([exe_name, "虾米AI编辑器.exe", "AIEditor.exe", "XiamiAIEditor.exe"])
                else:
                    preferred_names.extend([exe_name, "XiamiToolbox.exe", "虾米工具箱.exe"])
                found = find_exe_in_dir(payload_dir, preferred_names=preferred_names)
                if not found:
                    self.finished.emit(None, "未在更新包中找到可执行文件")
                    return
                try:
                    found_dir = os.path.abspath(os.path.dirname(found))
                    if found_dir and os.path.isdir(found_dir):
                        payload_dir = found_dir
                    exe_name = os.path.basename(found) or exe_name
                    exe_path = os.path.join(install_dir, exe_name)
                    payload_exe_path = found
                except Exception:
                    pass

            self.progress.emit(_EXTRACT_PCT, "校验运行文件...")
            ok_runtime, runtime_err = _validate_payload_runtime(payload_exe_path, install_dir)
            if not ok_runtime:
                self.finished.emit(None, runtime_err or "更新包缺少关键运行文件")
                return

            bat_path = os.path.join(downloads, f"apply_update_{app}_{latest or 'latest'}.cmd")
            keep_files, keep_dirs = update_keep_paths(app)
            if app != "editor":
                keep_files.extend(discover_update_plugin_config_paths(install_dir))
            pre_keep, post_keep = build_keep_commands(
                keep_files,
                keep_dirs,
                restore_root_var="NEW",
            )
            sidecar_pkg_name = _sidecar_pkg_name(exe_name)
            payload_exe_dir = os.path.dirname(payload_exe_path)
            payload_sidepkg_path = os.path.join(payload_exe_dir, sidecar_pkg_name) if sidecar_pkg_name else ""
            bootstrap_path = _bootstrap_file_path(app)
            local_state_path = _update_state_file_path(install_dir)
            applied_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            bootstrap_payload = {
                "preferred_exe": exe_path,
                "preferred_version": latest,
                "preferred_sha256": sha256_expected,
                "updated_at": applied_at,
            }
            try:
                current_bootstrap = load_bootstrap(app) or {}
                for policy_key in (
                    "manifest_signature_mode",
                    "allow_local_http_update",
                    "allow_file_update",
                ):
                    if policy_key in current_bootstrap:
                        bootstrap_payload[policy_key] = current_bootstrap.get(policy_key)
            except Exception:
                pass
            bootstrap_payload_b64 = _to_b64_utf8(
                json.dumps(
                    bootstrap_payload,
                    ensure_ascii=False,
                    indent=2,
                )
            )
            local_state_payload_b64 = _to_b64_utf8(
                json.dumps(
                    {
                        "app": app,
                        "preferred_exe": exe_path,
                        "preferred_version": latest,
                        "preferred_sha256": sha256_expected,
                        "updated_at": applied_at,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            bootstrap_cmd = (
                "$dir=Split-Path -Parent '%s'; "
                "if($dir){ New-Item -ItemType Directory -Force -Path $dir | Out-Null }; "
                "$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s')); "
                "Set-Content -LiteralPath '%s' -Value $raw -Encoding UTF8"
            ) % (
                _ps_single_quote(bootstrap_path),
                bootstrap_payload_b64,
                _ps_single_quote(bootstrap_path),
            )
            local_state_cmd = (
                "$dir=Split-Path -Parent '%s'; "
                "if($dir){ New-Item -ItemType Directory -Force -Path $dir | Out-Null }; "
                "$raw=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('%s')); "
                "Set-Content -LiteralPath '%s' -Value $raw -Encoding UTF8"
            ) % (
                _ps_single_quote(local_state_path),
                local_state_payload_b64,
                _ps_single_quote(local_state_path),
            )
            bootstrap_ps = (
                "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand %s >nul 2>nul"
                % _to_b64_utf16le(bootstrap_cmd)
            )
            local_state_ps = (
                "powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand %s >nul 2>nul"
                % _to_b64_utf16le(local_state_cmd)
            )
            install_commands = _build_atomic_install_commands(
                pre_keep,
                post_keep,
                update_retired_paths(app),
                full_payload=not is_exe,
                success_commands=[bootstrap_ps, local_state_ps],
            )
            bat = "\r\n".join(
                [
                    "@echo off",
                    "chcp 65001>nul",
                    "setlocal",
                    f"set PID={os.getpid()}",
                    f"set \"SRC={payload_dir}\"",
                    f"set \"TMP={tmp_dir}\"",
                    f"set \"PKG={download_path}\"",
                    f"set \"DST={install_dir}\"",
                    f"set \"EXE={exe_name}\"",
                    f"set \"SIDEPKG={sidecar_pkg_name}\"",
                    f"set \"PAYLOAD_EXE={payload_exe_path}\"",
                    f"set \"PAYLOAD_SIDEPKG={payload_sidepkg_path}\"",
                    "set WAITCOUNT=0",
                    ":wait",
                    "tasklist /FI \"PID eq %PID%\" /FO CSV /NH 2>nul | find \"\\\"%PID%\\\"\" >nul",
                    "if %errorlevel%==0 (",
                    "  set /a WAITCOUNT+=1",
                    "  if %WAITCOUNT% GEQ 20 taskkill /PID %PID% /F >nul 2>nul",
                    "  timeout /t 1 /nobreak >nul",
                    "  goto wait",
                    ")",
                    *install_commands,
                    "",
                ]
            )
            self.progress.emit(_FINALIZE_PCT, "写入更新脚本...")
            with open(bat_path, "w", encoding="utf-8-sig", newline="") as bf:
                bf.write(bat)


            self.progress.emit(100, "更新包已准备就绪")
            self.finished.emit(
                {"latest": latest, "current": self._current_version, "exe_path": exe_path, "restart_cmd": bat_path},
                "",
            )
        except urllib.error.HTTPError as he:
            code = getattr(he, "code", None)
            url = ""
            try:
                url = he.geturl() or ""
            except Exception:
                url = ""
            msg = f"下载失败（HTTP {code}）" if code else "下载失败（HTTP错误）"
            if url:
                pass
            self.finished.emit(None, msg)
        except Exception as e:
            self.finished.emit(None, str(e) or "更新失败")


def _qt_dialog_exec(dlg: QtWidgets.QDialog) -> int:
    try:
        return int(dlg.exec())
    except Exception:
        try:
            return int(dlg.exec_())
        except Exception:
            return 0


def prompt_update(window, manifest: dict, current_version: str) -> None:
    latest = str(manifest.get("latest_version") or "").strip()
    notes = str(manifest.get("release_notes") or "")
    dl = str(manifest.get("download_url") or "").strip()
    dl_norm = normalize_http_url(make_absolute_url(str(manifest.get("base_url") or "").strip(), dl))
    is_same_version_update = bool(manifest.get("_same_version_update"))
    is_mandatory_update = bool(manifest.get("_mandatory_update"))
    minimum_supported = str(manifest.get("_minimum_supported_version") or "").strip()
    signature_warning = str(manifest.get("_signature_warning") or "").strip()
    if signature_warning:
        notes = (str(notes or "").strip() + "\n\n安全提示：" + signature_warning).strip()
    if dl_norm.lower().startswith("http://"):
        notes = (
            str(notes or "").strip()
            + "\n\n开发提示：当前仅因 localhost HTTP 开关显式启用才允许明文更新。"
        ).strip()
    if is_same_version_update:
        msg = f"发现热更新：{current_version or '当前'}（版本号不变）"
    else:
        msg = f"发现新版本：{current_version or '当前'} -> {latest or '未知'}"
    if is_mandatory_update:
        msg += f"\n\n当前版本低于最低支持版本 {minimum_supported or '未知'}，必须更新后才能继续获得支持。"
    if notes.strip():
        msg += "\n\n更新说明：\n" + notes.strip()
    if not dl:
        msg += "\n\n未配置下载地址（download_url），无法自动更新。"
    r = QtWidgets.QMessageBox.question(window, "在线更新", msg, QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No)
    if r != QtWidgets.QMessageBox.Yes:
        try:
            window._update_in_progress = False
        except Exception:
            pass
        return
    if not dl:
        try:
            window._update_in_progress = False
        except Exception:
            pass
        return
    start_update_download(window, manifest, current_version)


def start_update_download(window, manifest: dict, current_version: str) -> None:
    dlg = QtWidgets.QDialog(window)
    dlg.setWindowTitle("在线更新")
    dlg.setModal(True)
    dlg.setMinimumWidth(540)
    lay = QtWidgets.QVBoxLayout(dlg)
    lay.setContentsMargins(16, 16, 16, 16)
    lay.setSpacing(10)

    status = QtWidgets.QLabel("准备下载...")
    status.setWordWrap(True)
    lay.addWidget(status, 0)

    bar = QtWidgets.QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(0)
    lay.addWidget(bar, 0)

    btn_row = QtWidgets.QHBoxLayout()
    restart_btn = QtWidgets.QPushButton("更新重启")
    restart_btn.setEnabled(False)
    btn_row.addWidget(restart_btn, 0)
    cancel_btn = QtWidgets.QPushButton("取消下载")
    btn_row.addWidget(cancel_btn, 0)
    close_btn = QtWidgets.QPushButton("关闭")
    close_btn.setEnabled(False)
    btn_row.addWidget(close_btn, 0)
    btn_row.addStretch(1)
    lay.addLayout(btn_row)

    cancel_flag = {"v": False}
    state: dict = {"exe_path": "", "restart_cmd": "", "latest": "", "current": current_version}

    def on_progress(p: int, text: str) -> None:
        try:
            if 0 <= int(p) <= 100:
                bar.setValue(int(p))
        except Exception:
            pass
        status.setText(str(text or ""))

    def on_finished(result: dict | None, err: str) -> None:
        nonlocal state
        if err:
            try:
                window._update_in_progress = False
            except Exception:
                pass
            try:
                restart_btn.setEnabled(False)
                close_btn.setEnabled(True)
                cancel_btn.setEnabled(True)
            except Exception:
                pass
            QtWidgets.QMessageBox.critical(dlg, "更新失败", err)
            return
        if not isinstance(result, dict):
            try:
                window._update_in_progress = False
            except Exception:
                pass
            QtWidgets.QMessageBox.critical(dlg, "更新失败", "更新结果无效")
            try:
                close_btn.setEnabled(True)
            except Exception:
                pass
            return
        state.update(result)
        try:
            restart_btn.setEnabled(True)
            close_btn.setEnabled(True)
            cancel_btn.setEnabled(False)
        except Exception:
            pass
        cur = str(state.get("current") or "").strip()
        latest = str(state.get("latest") or "").strip()
        status.setText(f"更新包已准备就绪：{cur or '当前'} -> {latest}，点击“更新重启”完成覆盖安装并自动重启。")

    def do_cancel() -> None:
        cancel_flag["v"] = True
        try:
            cancel_btn.setEnabled(False)
            close_btn.setEnabled(True)
        except Exception:
            pass

    def do_close() -> None:
        try:
            window._update_in_progress = False
        except Exception:
            pass
        dlg.close()

    def do_restart_now() -> None:
        restart_cmd = str(state.get("restart_cmd") or "").strip()
        if not restart_cmd:
            QtWidgets.QMessageBox.critical(dlg, "更新失败", "缺少更新脚本，无法应用更新")
            return
        try:
            create_no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            subprocess.Popen(
                ["cmd.exe", "/c", restart_cmd],
                cwd=os.path.dirname(restart_cmd) or None,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=create_no_window,
            )
        except Exception:
            QtWidgets.QMessageBox.critical(dlg, "更新失败", "启动更新程序失败")
            return
        try:
            window._closing_to_exit = True
        except Exception:
            pass
        try:
            restart_btn.setEnabled(False)
            cancel_btn.setEnabled(False)
            close_btn.setEnabled(False)
        except Exception:
            pass
        try:
            dlg.accept()
        except Exception:
            pass
        try:
            window.close()
        except Exception:
            pass
        try:
            QtWidgets.QApplication.processEvents()
        except Exception:
            pass
        QtCore.QTimer.singleShot(0, QtWidgets.QApplication.quit)
        return

    cancel_btn.clicked.connect(do_cancel)
    close_btn.clicked.connect(do_close)
    restart_btn.clicked.connect(do_restart_now)
    dlg.rejected.connect(do_close)

    worker = UpdateDownloadWorker(manifest, cancel_flag, current_version)
    thread = QtCore.QThread(dlg)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(on_progress)
    worker.finished.connect(on_finished)
    worker.finished.connect(thread.quit)
    worker.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()

    _qt_dialog_exec(dlg)
