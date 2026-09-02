# -*- coding: utf-8 -*-
"""Best-effort client security telemetry.

Wire contract: POST /api/security/events with a bearer token.
The module never blocks application startup, never retries in a loop, and only
reports signals that can be observed directly by the running client.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import secrets
import sys
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping, Optional

from toolbox_backend_tls import (
    BackendTransportPolicyError,
    backend_urlopen,
    normalize_backend_base_url,
)


SECURITY_EVENT_PATH = "/api/security/events"
_EVENT_SOURCES = {
    "binary_hash_mismatch": "client_integrity",
    "integrity_failed": "client_integrity",
    "debugger_signal": "client_runtime",
    "module_injection": "client_runtime",
    "hook_detected": "client_runtime",
    "token_replay": "client_rpc",
    "rpc_abuse": "client_rpc",
    "invalid_signature": "client_update",
}
_ALLOWED_EVENT_TYPES = frozenset(_EVENT_SOURCES)
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_STATE_LOCK = threading.Lock()
_MEMORY_ATTEMPTS: dict[str, float] = {}
_MEMORY_SUCCESSES: dict[str, float] = {}


def _is_truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_text(value: object, limit: int) -> str:
    text = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    return text[: max(0, int(limit))]


def _valid_sha256(value: object) -> str:
    text = _safe_text(value, 64).lower()
    return text if _SHA256_RE.fullmatch(text) else ""


def _default_state_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "XiamiToolbox" / "security_event_state.json"


def _sanitize_details(details: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    if not isinstance(details, Mapping):
        return clean
    for raw_key in sorted(details, key=lambda item: str(item))[:16]:
        key = _safe_text(raw_key, 48)
        if not key or key.lower() in {"token", "authorization", "password", "cookie"}:
            continue
        value = details.get(raw_key)
        if isinstance(value, bool) or value is None:
            clean[key] = value
        elif isinstance(value, int):
            clean[key] = int(value)
        elif isinstance(value, float):
            clean[key] = round(float(value), 6)
        elif isinstance(value, (list, tuple)):
            clean[key] = [_safe_text(item, 96) for item in value[:8]]
        else:
            clean[key] = _safe_text(value, 256)
    return clean


def _serialize_details(details: Optional[Mapping[str, Any]], limit: int = 1024) -> str:
    clean = _sanitize_details(details)
    bounded: dict[str, Any] = {}
    for key, value in clean.items():
        candidate = dict(bounded)
        candidate[key] = value
        encoded = json.dumps(candidate, ensure_ascii=True, separators=(",", ":"))
        if len(encoded) > limit:
            break
        bounded = candidate
    if len(bounded) < len(clean):
        candidate = dict(bounded)
        candidate["_truncated"] = True
        encoded = json.dumps(candidate, ensure_ascii=True, separators=(",", ":"))
        if len(encoded) <= limit:
            bounded = candidate
    return json.dumps(bounded, ensure_ascii=True, separators=(",", ":"))


def _expected_binary_sha256(session: Mapping[str, Any]) -> str:
    for key in ("expected_binary_sha256", "toolbox_binary_sha256"):
        digest = _valid_sha256(session.get(key))
        if digest:
            return digest
    for parent_key in ("security", "security_policy", "client_security"):
        nested = session.get(parent_key)
        if not isinstance(nested, Mapping):
            continue
        for key in ("expected_binary_sha256", "toolbox_binary_sha256", "binary_sha256"):
            digest = _valid_sha256(nested.get(key))
            if digest:
                return digest
    return ""


def apply_login_security_metadata(session: dict[str, Any], login_response: Mapping[str, Any]) -> None:
    """Copy only validated security metadata from an authenticated login response."""
    if not isinstance(session, dict) or not isinstance(login_response, Mapping):
        return
    expected = _expected_binary_sha256(login_response)
    if expected:
        session["expected_binary_sha256"] = expected


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _windows_debugger_methods() -> list[str]:
    if os.name != "nt":
        return []
    methods: list[str] = []
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.IsDebuggerPresent.restype = ctypes.c_bool
        if bool(kernel32.IsDebuggerPresent()):
            methods.append("win32_is_debugger_present")

        present = ctypes.c_bool(False)
        kernel32.GetCurrentProcess.restype = ctypes.c_void_p
        handle = kernel32.GetCurrentProcess()
        kernel32.CheckRemoteDebuggerPresent.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_bool)]
        kernel32.CheckRemoteDebuggerPresent.restype = ctypes.c_bool
        if bool(kernel32.CheckRemoteDebuggerPresent(handle, ctypes.byref(present))) and bool(present.value):
            methods.append("win32_remote_debugger_present")
    except Exception:
        return methods
    return methods


def collect_reliable_signals(
    session: Mapping[str, Any],
    *,
    executable_path: Optional[os.PathLike[str] | str] = None,
    require_frozen: bool = True,
    trace_getter: Optional[Callable[[], object]] = None,
    windows_debugger_probe: Optional[Callable[[], list[str]]] = None,
) -> list[tuple[str, dict[str, Any]]]:
    """Collect direct observations only; absence of a signal proves nothing."""
    if require_frozen and not bool(getattr(sys, "frozen", False)):
        return []

    signals: list[tuple[str, dict[str, Any]]] = []
    methods: list[str] = []
    getter = trace_getter if trace_getter is not None else getattr(sys, "gettrace", None)
    try:
        if callable(getter) and getter() is not None:
            methods.append("python_trace_hook")
    except Exception:
        pass
    probe = windows_debugger_probe if windows_debugger_probe is not None else _windows_debugger_methods
    try:
        methods.extend(str(item) for item in probe() if item)
    except Exception:
        pass
    methods = sorted(set(methods))
    if methods:
        confidence = "high" if any(item.startswith("win32_") for item in methods) else "medium"
        signals.append(("debugger_signal", {"methods": methods, "confidence": confidence}))

    expected = _expected_binary_sha256(session)
    if expected:
        raw_path = executable_path if executable_path is not None else getattr(sys, "executable", "")
        try:
            path = Path(raw_path).resolve()
            if path.is_file():
                actual = _file_sha256(path)
                if actual != expected:
                    signals.append(
                        (
                            "binary_hash_mismatch",
                            {
                                "expected_sha256": expected,
                                "actual_sha256": actual,
                                "binary_size": int(path.stat().st_size),
                                "confidence": "high",
                            },
                        )
                    )
        except Exception:
            # A read failure is not evidence of tampering and must not be reported.
            pass
    return signals


def _load_state(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, dict) and isinstance(obj.get("events"), dict):
            return obj
    except Exception:
        pass
    return {"version": 1, "events": {}}


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text(json.dumps(state, ensure_ascii=True, separators=(",", ":")), encoding="utf-8")
        os.replace(str(temp_path), str(path))
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)  # type: ignore[name-defined,call-arg]
        except Exception:
            pass


class SecurityEventReporter:
    def __init__(
        self,
        session: Mapping[str, Any],
        *,
        app_name: str,
        app_version: str,
        state_path: Optional[os.PathLike[str] | str] = None,
        attempt_interval_seconds: int = 300,
        success_interval_seconds: int = 3600,
        timeout_seconds: float = 3.0,
    ) -> None:
        self._session = dict(session or {})
        self._app_name = _safe_text(app_name, 48) or "toolbox"
        self._app_version = _safe_text(app_version, 32) or "0"
        self._state_path = Path(state_path) if state_path is not None else _default_state_path()
        self._attempt_interval = max(60, int(attempt_interval_seconds))
        self._success_interval = max(self._attempt_interval, int(success_interval_seconds))
        self._timeout = max(0.5, min(10.0, float(timeout_seconds)))

    def _identity(self) -> tuple[str, str, str]:
        token = _safe_text(self._session.get("token"), 4096)
        device_id = _safe_text(self._session.get("device_id"), 256)
        try:
            server = normalize_backend_base_url(
                _safe_text(self._session.get("server"), 512),
                allow_local_http=True,
            )
        except BackendTransportPolicyError:
            server = ""
        return server, token, device_id

    def _fingerprint(self, event_type: str, device_id: str) -> str:
        material = f"{self._app_name}\n{event_type}\n{device_id}".encode("utf-8", "ignore")
        return hashlib.sha256(material).hexdigest()

    def _reserve(self, fingerprint: str) -> bool:
        now = time.time()
        with _STATE_LOCK:
            last_attempt = float(_MEMORY_ATTEMPTS.get(fingerprint, 0.0) or 0.0)
            last_success = float(_MEMORY_SUCCESSES.get(fingerprint, 0.0) or 0.0)
            state = _load_state(self._state_path)
            events = state.setdefault("events", {})
            record = events.get(fingerprint, {}) if isinstance(events, dict) else {}
            if isinstance(record, dict):
                last_attempt = max(last_attempt, float(record.get("last_attempt", 0.0) or 0.0))
                last_success = max(last_success, float(record.get("last_success", 0.0) or 0.0))
            if now - last_attempt < self._attempt_interval or now - last_success < self._success_interval:
                return False

            _MEMORY_ATTEMPTS[fingerprint] = now
            if not isinstance(events, dict):
                events = {}
                state["events"] = events
            events[fingerprint] = {"last_attempt": now, "last_success": last_success}
            if len(events) > 128:
                ordered = sorted(
                    events.items(),
                    key=lambda item: float(item[1].get("last_attempt", 0.0)) if isinstance(item[1], dict) else 0.0,
                    reverse=True,
                )
                state["events"] = dict(ordered[:128])
            _write_state(self._state_path, state)
            return True

    def _mark_success(self, fingerprint: str) -> None:
        now = time.time()
        with _STATE_LOCK:
            _MEMORY_SUCCESSES[fingerprint] = now
            state = _load_state(self._state_path)
            events = state.setdefault("events", {})
            if not isinstance(events, dict):
                events = {}
                state["events"] = events
            record = events.get(fingerprint, {})
            if not isinstance(record, dict):
                record = {}
            record["last_attempt"] = float(record.get("last_attempt", now) or now)
            record["last_success"] = now
            events[fingerprint] = record
            _write_state(self._state_path, state)

    def report(self, event_type: str, details: Optional[Mapping[str, Any]] = None) -> bool:
        event_type = _safe_text(event_type, 64)
        if event_type not in _ALLOWED_EVENT_TYPES:
            return False
        server, token, device_id = self._identity()
        if not server or not token or not device_id:
            return False
        fingerprint = self._fingerprint(event_type, device_id)
        if not self._reserve(fingerprint):
            return False

        nonce = secrets.token_hex(16)
        payload = {
            "nonce": nonce,
            "event_type": event_type,
            "severity": "high" if event_type != "debugger_signal" else "medium",
            "source": _EVENT_SOURCES[event_type],
            "app": self._app_name,
            "app_version": self._app_version,
            "detail": _serialize_details(details),
        }
        data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        request = urllib.request.Request(
            server + SECURITY_EVENT_PATH,
            data=data,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json; charset=utf-8",
                "X-Device-Id": device_id,
                "X-Event-Nonce": nonce,
            },
        )
        try:
            with backend_urlopen(request, timeout=self._timeout, allow_local_http=True) as response:
                status = int(getattr(response, "status", 200) or 200)
                response.read(1024)
            if 200 <= status < 300:
                self._mark_success(fingerprint)
                return True
        except Exception:
            pass
        return False


def schedule_startup_security_checks(
    session: Mapping[str, Any],
    *,
    app_name: str,
    app_version: str,
    state_path: Optional[os.PathLike[str] | str] = None,
) -> bool:
    """Run collection and reporting on a daemon thread; all failures stay silent."""
    if _is_truthy(os.environ.get("XIAMI_SECURITY_EVENTS_DISABLED")):
        return False
    if not isinstance(session, Mapping):
        return False
    snapshot = dict(session)
    if not _safe_text(snapshot.get("token"), 4096) or not _safe_text(snapshot.get("device_id"), 256):
        return False

    def worker() -> None:
        try:
            signals = collect_reliable_signals(snapshot, require_frozen=True)
            if not signals:
                return
            reporter = SecurityEventReporter(
                snapshot,
                app_name=app_name,
                app_version=app_version,
                state_path=state_path,
            )
            for event_type, details in signals:
                reporter.report(event_type, details)
        except Exception:
            return

    try:
        thread = threading.Thread(target=worker, name="xiami-security-event", daemon=True)
        thread.start()
        return True
    except Exception:
        return False


__all__ = [
    "SECURITY_EVENT_PATH",
    "SecurityEventReporter",
    "apply_login_security_metadata",
    "collect_reliable_signals",
    "schedule_startup_security_checks",
]
