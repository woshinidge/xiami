"""PAK/WIL/WZL image providers used by the visual NPC client."""
from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath, WindowsPath
from types import MappingProxyType
from typing import Any, Callable, Mapping

from PIL import Image

from embedded_npc_visual.core.dbc_reader import DbcTable
from embedded_npc_visual.core.npc_preview.pak_asset_browser import (
    AssetRecord,
    default_password_for_magic,
    image_for_record,
    mark_records_native_authorized,
    read_magic,
)
from toolbox_native_core import NativeCoreError, authorize_npc_asset_read
from toolbox_native_asset_worker import (
    NativeAssetWorkerBroker,
    NativeAssetWorkerError,
)

load_pak_assets = None
if not bool(getattr(sys, "frozen", False)):
    from embedded_npc_visual.core.npc_preview.pak_loader import load_pak_assets


ITEMSHOW_BACKGROUND_INDEX = 47


class NativeAssetAuthorizationError(RuntimeError):
    pass


def _prefetch_native_records(
    broker: NativeAssetWorkerBroker,
    handle: str,
    generation: int,
    records: list[AssetRecord],
    index_handle: str | None = None,
) -> None:
    indexes = [int(record.uid) for record in records if getattr(record, "kind", "") != "empty"][:32]
    if not indexes:
        return

    def run() -> None:
        try:
            broker.prefetch_images(handle, generation, indexes, index_handle, timeout=20.0)
        except Exception:
            return

    threading.Thread(target=run, name="xiami-native-asset-prefetch", daemon=True).start()


def _sibling_asset_file(path: Path, suffixes: tuple[str, ...]) -> Path | None:
    for suffix in suffixes:
        candidate = path.with_suffix(suffix)
        if candidate.is_file():
            return candidate
    if path.parent.is_dir():
        stem = path.stem.casefold()
        wanted = {suffix.casefold() for suffix in suffixes}
        for child in path.parent.iterdir():
            if child.is_file() and child.stem.casefold() == stem and child.suffix.casefold() in wanted:
                return child
    return None


def _resolve_wil_asset_paths(path: Path) -> tuple[Path, Path, str, str]:
    suffix = path.suffix.lower()
    if suffix in {".wzl", ".wzx"}:
        data = _sibling_asset_file(path, (".wzl", ".WZL"))
        index = _sibling_asset_file(path, (".wzx", ".WZX"))
        magic, kind = "WZL", "recovered_wzl"
    elif suffix == ".wis":
        data = _sibling_asset_file(path, (".wis", ".WIS"))
        index = _sibling_asset_file(path, (".wix", ".WIX"))
        magic, kind = "WIS", "recovered_wis"
    elif suffix == ".wix" and _sibling_asset_file(path, (".wil", ".WIL")) is None:
        data = _sibling_asset_file(path, (".wis", ".WIS"))
        index = _sibling_asset_file(path, (".wix", ".WIX"))
        magic, kind = "WIS", "recovered_wis"
    elif suffix in {".wil", ".wix"}:
        data = _sibling_asset_file(path, (".wil", ".WIL"))
        index = _sibling_asset_file(path, (".wix", ".WIX"))
        magic, kind = "WIL", "recovered_wil"
    else:
        raise ValueError(f"unsupported image library: {path.name}")
    if data is None or index is None:
        raise FileNotFoundError(str(data or index or path))
    return data, index, magic, kind


def _is_unsupported_asset_candidate(error: NativeAssetAuthorizationError) -> bool:
    """A wrong same-stem candidate is a missing asset, not an auth failure."""
    cause = error.__cause__
    return str(getattr(cause, "code", "") or "") in {
        "asset_magic_unsupported",
        "asset_suffix_unsupported",
    }


@dataclass
class _AuthorizationFlight:
    event: threading.Event
    authorization: Mapping[str, Any] | None = None
    error: NativeAssetAuthorizationError | None = None


@dataclass
class _FileIdentityFlight:
    event: threading.Event
    signature: tuple[Any, ...] | None = None
    error: Exception | None = None


@dataclass
class _VerificationFlight:
    event: threading.Event
    error: NativeAssetAuthorizationError | None = None


@dataclass(frozen=True)
class AssetAuthorizationSnapshot:
    """Immutable identity for one observed login/authorization generation."""

    session: Mapping[str, Any]
    session_key: tuple[str, str, str, str, int]
    generation: int
    worker_generation: int = 0

    @property
    def cache_identity(self) -> tuple[Any, ...]:
        return (
            int(self.generation),
            int(self.worker_generation),
            self.session_key,
        )


class _BoundAuthorization(dict):
    """Mapping-compatible native authorization bound to its source snapshot."""

    def __init__(
        self,
        authorization: Mapping[str, Any],
        snapshot: AssetAuthorizationSnapshot,
        file_identity: tuple[Any, ...],
    ) -> None:
        super().__init__(authorization)
        self.snapshot = snapshot
        self.file_identity = file_identity


class AuthorizedAssetFiles(list):
    """List-compatible file/authorization pairs sharing one snapshot."""

    def __init__(
        self,
        values: Any = (),
        *,
        snapshot: AssetAuthorizationSnapshot,
    ) -> None:
        super().__init__(values)
        self.snapshot = snapshot


class NativeAssetReadGate:
    def __init__(
        self,
        session_provider: Callable[[], Mapping[str, Any] | None] | None = None,
        authorize_func: Callable[..., Mapping[str, Any]] = authorize_npc_asset_read,
        asset_broker: NativeAssetWorkerBroker | None = None,
    ) -> None:
        self.session_provider = session_provider
        self.authorize_func = authorize_func
        if asset_broker is None and bool(getattr(sys, "frozen", False)):
            asset_broker = NativeAssetWorkerBroker()
        self.asset_broker = asset_broker
        self._cache: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        self._inflight: dict[tuple[Any, ...], _AuthorizationFlight] = {}
        self._file_identity_cache: dict[
            str, tuple[tuple[int, ...], tuple[Any, ...]]
        ] = {}
        self._file_identity_inflight: dict[
            tuple[str, tuple[int, ...]], _FileIdentityFlight
        ] = {}
        self._verification_cache: dict[tuple[str, tuple[Any, ...], str], None] = {}
        self._verification_inflight: dict[
            tuple[str, tuple[Any, ...], str], _VerificationFlight
        ] = {}
        self._lock = threading.RLock()
        self._generation = 0
        self._active_session_key: tuple[str, str, str, str, int] | None = None
        self._active_worker_generation = 0
        self._native_handles: set[tuple[str, int]] = set()

    def clear(self) -> None:
        current_worker_generation = self._broker_generation(ensure_alive=False)
        with self._lock:
            handles = self._detach_authorization_state_locked()
            self._generation += 1
            self._active_session_key = None
            self._active_worker_generation = 0
            self._file_identity_cache.clear()
        self._close_current_worker_handles(handles, current_worker_generation)

    @staticmethod
    def _session_key(
        session: Mapping[str, Any],
    ) -> tuple[str, str, str, str, int]:
        token = str(session.get("token") or "")
        try:
            auth_epoch = int(session.get("_auth_epoch") or 0)
        except (TypeError, ValueError):
            auth_epoch = 0
        return (
            str(session.get("server") or "").strip().rstrip("/").casefold(),
            str(session.get("username") or session.get("account_id") or "").strip().casefold(),
            str(session.get("device_id") or "").strip(),
            hashlib.sha256(token.encode("utf-8", errors="strict")).hexdigest(),
            auth_epoch,
        )

    def _clear_authorization_caches_locked(self) -> None:
        self._cache.clear()
        self._verification_cache.clear()

    def _detach_authorization_state_locked(self) -> tuple[tuple[str, int], ...]:
        handles = tuple(self._native_handles)
        self._native_handles.clear()
        self._clear_authorization_caches_locked()
        return handles

    def _broker_generation(self, *, ensure_alive: bool) -> int:
        broker = self.asset_broker
        if broker is None:
            return 0
        try:
            if ensure_alive:
                starter = getattr(broker, "start", None)
                if callable(starter):
                    generation = int(starter())
                else:
                    generation = int(getattr(broker, "generation", 0) or 0)
            else:
                generation = int(getattr(broker, "generation", 0) or 0)
        except Exception as exc:
            raise NativeAssetAuthorizationError("NPC 原生素材工作进程不可用") from exc
        if ensure_alive and generation <= 0:
            raise NativeAssetAuthorizationError("NPC 原生素材工作进程代次无效")
        return max(0, generation)

    def _close_current_worker_handles(
        self,
        handles: tuple[tuple[str, int], ...],
        current_worker_generation: int,
    ) -> None:
        broker = self.asset_broker
        if broker is None or current_worker_generation <= 0:
            return
        for handle, generation in handles:
            if int(generation) != int(current_worker_generation):
                continue
            try:
                broker.close_asset(handle, generation)
            except Exception:
                pass

    def _invalidate_worker_state(
        self,
        current_worker_generation: int,
        *,
        cache_key: tuple[Any, ...] | None = None,
        expected_authorization: Mapping[str, Any] | None = None,
    ) -> None:
        with self._lock:
            if (
                cache_key is not None
                and expected_authorization is not None
                and self._cache.get(cache_key) is not expected_authorization
            ):
                return
            handles = self._detach_authorization_state_locked()
            self._generation += 1
            self._active_worker_generation = int(current_worker_generation)
        self._close_current_worker_handles(handles, current_worker_generation)

    def _authorization_matches_worker(
        self,
        authorization: Mapping[str, Any],
        worker_generation: int,
    ) -> bool:
        if self.asset_broker is None:
            return True
        try:
            authorization_generation = int(
                authorization.get("worker_generation") or 0
            )
        except (TypeError, ValueError):
            return False
        return (
            worker_generation > 0
            and authorization_generation == int(worker_generation)
        )

    def capture_snapshot(self) -> AssetAuthorizationSnapshot:
        """Capture the session and generation at one gate serialization point."""
        worker_generation = self._broker_generation(ensure_alive=True)
        handles: tuple[tuple[str, int], ...] = ()
        with self._lock:
            if not callable(self.session_provider):
                raise NativeAssetAuthorizationError("NPC 素材读取需要登录并取得服务器授权")
            try:
                current = self.session_provider()
                if not isinstance(current, Mapping):
                    raise TypeError("session provider returned no mapping")
                session = MappingProxyType(dict(current))
                session_key = self._session_key(session)
            except NativeAssetAuthorizationError:
                raise
            except Exception as exc:
                error = NativeAssetAuthorizationError(
                    "NPC 素材读取需要登录并取得服务器授权"
                )
                error.__cause__ = exc
                raise error

            session_changed = (
                self._active_session_key is not None
                and self._active_session_key != session_key
            )
            worker_changed = (
                self._active_worker_generation > 0
                and self._active_worker_generation != worker_generation
            )
            if session_changed or worker_changed:
                handles = self._detach_authorization_state_locked()
                self._generation += 1
            if self._active_session_key is None or session_changed:
                self._active_session_key = session_key
            self._active_worker_generation = worker_generation
            snapshot = AssetAuthorizationSnapshot(
                session,
                session_key,
                self._generation,
                worker_generation,
            )
        self._close_current_worker_handles(handles, worker_generation)
        return snapshot

    def _snapshot_matches_locked(self, snapshot: AssetAuthorizationSnapshot) -> bool:
        return (
            isinstance(snapshot, AssetAuthorizationSnapshot)
            and int(snapshot.generation) == self._generation
            and snapshot.session_key == self._active_session_key
            and int(snapshot.worker_generation) == self._active_worker_generation
        )

    def ensure_snapshot_current(self, snapshot: AssetAuthorizationSnapshot) -> None:
        """Reject work captured before clear() or an observed session change."""
        current = self.capture_snapshot()
        if (
            not isinstance(snapshot, AssetAuthorizationSnapshot)
            or snapshot.cache_identity != current.cache_identity
        ):
            raise NativeAssetAuthorizationError("NPC 素材授权会话已变化，已拒绝旧任务")

    @staticmethod
    def snapshot_for_authorization(
        authorization: Mapping[str, Any],
    ) -> AssetAuthorizationSnapshot:
        snapshot = getattr(authorization, "snapshot", None)
        if not isinstance(snapshot, AssetAuthorizationSnapshot):
            raise NativeAssetAuthorizationError("NPC 素材授权缺少会话快照")
        return snapshot

    @property
    def authorization_generation(self) -> int:
        with self._lock:
            return int(self._generation)

    @staticmethod
    def _snapshot_fingerprint(path: Path, file_size: int) -> str:
        sample_size = 64 * 1024
        offsets = sorted(
            {
                0,
                max(0, (int(file_size) - sample_size) // 2),
                max(0, int(file_size) - sample_size),
            }
        )
        digest = hashlib.sha256()
        digest.update(int(file_size).to_bytes(8, "little", signed=False))
        with Path(path).open("rb") as handle:
            for offset in offsets:
                handle.seek(offset)
                chunk = handle.read(sample_size)
                digest.update(int(offset).to_bytes(8, "little", signed=False))
                digest.update(len(chunk).to_bytes(4, "little", signed=False))
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _windows_change_time(path: Path) -> int:
        if os.name != "nt":
            return 0
        try:
            import ctypes
            from ctypes import wintypes

            class FileBasicInfo(ctypes.Structure):
                _fields_ = (
                    ("CreationTime", ctypes.c_longlong),
                    ("LastAccessTime", ctypes.c_longlong),
                    ("LastWriteTime", ctypes.c_longlong),
                    ("ChangeTime", ctypes.c_longlong),
                    ("FileAttributes", wintypes.DWORD),
                )

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            create_file = kernel32.CreateFileW
            create_file.argtypes = (
                wintypes.LPCWSTR,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.LPVOID,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.HANDLE,
            )
            create_file.restype = wintypes.HANDLE
            get_info = kernel32.GetFileInformationByHandleEx
            get_info.argtypes = (
                wintypes.HANDLE,
                ctypes.c_int,
                wintypes.LPVOID,
                wintypes.DWORD,
            )
            get_info.restype = wintypes.BOOL
            close_handle = kernel32.CloseHandle
            close_handle.argtypes = (wintypes.HANDLE,)
            close_handle.restype = wintypes.BOOL

            handle = create_file(
                str(path),
                0x0080,
                0x0001 | 0x0002 | 0x0004,
                None,
                3,
                0,
                None,
            )
            invalid_handle = ctypes.c_void_p(-1).value
            if handle in (None, 0, invalid_handle):
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                info = FileBasicInfo()
                if not get_info(handle, 0, ctypes.byref(info), ctypes.sizeof(info)):
                    raise ctypes.WinError(ctypes.get_last_error())
                return int(info.ChangeTime)
            finally:
                close_handle(handle)
        except Exception as exc:
            raise OSError("unable to query the Windows file change time") from exc

    @classmethod
    def _stat_identity(cls, path: Path, stat: Any) -> tuple[int, ...]:
        return (
            int(stat.st_size),
            int(stat.st_mtime_ns),
            int(getattr(stat, "st_ctime_ns", 0)),
            int(getattr(stat, "st_ino", 0)),
            cls._windows_change_time(path),
        )

    def _file_signature(self, path: Path) -> tuple[Path, tuple[Any, ...]]:
        target = Path(path).resolve(strict=True)
        path_key = str(target)
        for _attempt in range(2):
            stat = target.stat()
            stat_identity = self._stat_identity(target, stat)
            flight_key = (path_key, stat_identity)
            with self._lock:
                cached = self._file_identity_cache.get(path_key)
                if cached is not None and cached[0] == stat_identity:
                    return target, cached[1]
                flight = self._file_identity_inflight.get(flight_key)
                is_leader = False
                if flight is None:
                    flight = _FileIdentityFlight(threading.Event())
                    self._file_identity_inflight[flight_key] = flight
                    is_leader = True

            if not is_leader:
                if not flight.event.wait(30.0):
                    raise OSError("asset file identity sampling timed out")
                if flight.error is not None:
                    if _attempt == 0:
                        continue
                    raise flight.error
                if flight.signature is None:
                    raise OSError("asset file identity sampling returned no result")
                return target, flight.signature

            signature = None
            error = None
            try:
                fingerprint = self._snapshot_fingerprint(target, stat_identity[0])
                if self._stat_identity(target, target.stat()) != stat_identity:
                    raise OSError("asset file changed while its identity was sampled")
                signature = (path_key, *stat_identity, fingerprint)
            except Exception as exc:
                error = exc
            with self._lock:
                current_flight = self._file_identity_inflight.get(flight_key)
                if error is None and signature is not None:
                    cached = self._file_identity_cache.get(path_key)
                    if cached is not None and cached[0] == stat_identity:
                        signature = cached[1]
                    else:
                        self._file_identity_cache[path_key] = (stat_identity, signature)
                        if len(self._file_identity_cache) > 256:
                            self._file_identity_cache.pop(next(iter(self._file_identity_cache)))
                if current_flight is flight:
                    flight.signature = signature
                    flight.error = error
                    self._file_identity_inflight.pop(flight_key, None)
                    flight.event.set()
            if error is not None:
                if _attempt == 0:
                    continue
                raise error
            if signature is not None:
                return target, signature
        raise OSError("asset file changed while its identity was sampled")

    def file_identity(self, path: Path) -> tuple[Any, ...]:
        return self._file_signature(path)[1]

    def cache_context(self) -> tuple[Any, ...]:
        return self.capture_snapshot().cache_identity

    @staticmethod
    def _full_file_sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with Path(path).open("rb") as handle:
            while True:
                chunk = handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def authorize(
        self,
        path: Path,
        purpose: str,
        asset_index: int = -1,
        password: str = "",
        *,
        snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> Mapping[str, Any]:
        authorization_snapshot = snapshot or self.capture_snapshot()
        self.ensure_snapshot_current(authorization_snapshot)
        try:
            target, signature = self._file_signature(path)
        except Exception as exc:
            raise NativeAssetAuthorizationError("NPC 素材文件状态无效") from exc
        self.ensure_snapshot_current(authorization_snapshot)
        cache_key = (
            authorization_snapshot.cache_identity,
            signature,
            str(purpose),
            hashlib.sha256(str(password or "").encode("utf-8", errors="strict")).hexdigest(),
        )
        with self._lock:
            cached = self._cache.get(cache_key)
            flight = None
            is_leader = False
            if cached is None:
                flight = self._inflight.get(cache_key)
                if flight is None:
                    flight = _AuthorizationFlight(threading.Event())
                    self._inflight[cache_key] = flight
                    is_leader = True
        if cached is not None:
            current_worker_generation = self._broker_generation(ensure_alive=True)
            if not self._authorization_matches_worker(
                cached, current_worker_generation
            ):
                self._invalidate_worker_state(
                    current_worker_generation,
                    cache_key=cache_key,
                    expected_authorization=cached,
                )
                return self.authorize(
                    path,
                    purpose,
                    asset_index,
                    password,
                )
            self.ensure_snapshot_current(authorization_snapshot)
            return cached
        if not is_leader:
            if flight is None or not flight.event.wait(30.0):
                raise NativeAssetAuthorizationError("NPC 素材授权请求等待超时")
            if flight.error is not None:
                raise flight.error
            if not isinstance(flight.authorization, Mapping):
                raise NativeAssetAuthorizationError("NPC 素材并发授权结果无效")
            self.ensure_snapshot_current(authorization_snapshot)
            flight_snapshot = self.snapshot_for_authorization(flight.authorization)
            if flight_snapshot.cache_identity != authorization_snapshot.cache_identity:
                raise NativeAssetAuthorizationError("NPC 素材并发授权快照不一致")
            current_worker_generation = self._broker_generation(ensure_alive=True)
            if not self._authorization_matches_worker(
                flight.authorization, current_worker_generation
            ):
                self._invalidate_worker_state(current_worker_generation)
                return self.authorize(
                    path,
                    purpose,
                    asset_index,
                    password,
                )
            return flight.authorization
        authorization = None
        error = None
        try:
            self.ensure_snapshot_current(authorization_snapshot)
            authorization_args = (
                dict(authorization_snapshot.session), target, purpose, -1, str(password or "")
            )
            authorization_kwargs = {"allow_local_http": True}
            if self.asset_broker is not None:
                authorization_kwargs["asset_broker"] = self.asset_broker
            raw_authorization = self.authorize_func(*authorization_args, **authorization_kwargs)
            if not isinstance(raw_authorization, Mapping):
                raise NativeAssetAuthorizationError("NPC 素材授权结果无效")
            if not self._authorization_matches_worker(
                raw_authorization, authorization_snapshot.worker_generation
            ):
                raise NativeAssetAuthorizationError(
                    "NPC 素材授权返回了过期的原生工作进程代次"
                )
            self.ensure_snapshot_current(authorization_snapshot)
            _current_target, current_signature = self._file_signature(target)
            if current_signature != signature:
                raise NativeAssetAuthorizationError("NPC 素材在授权期间发生变化，已拒绝读取")
            authorization = _BoundAuthorization(
                raw_authorization,
                authorization_snapshot,
                signature,
            )
        except NativeCoreError as exc:
            error = NativeAssetAuthorizationError(f"NPC 素材服务器授权失败：{exc}")
            error.__cause__ = exc
        except NativeAssetAuthorizationError as exc:
            error = exc
        except Exception as exc:
            error = NativeAssetAuthorizationError("NPC 素材授权结果无效")
            error.__cause__ = exc
        with self._lock:
            current_flight = self._inflight.get(cache_key)
            if error is None and not self._snapshot_matches_locked(authorization_snapshot):
                error = NativeAssetAuthorizationError("NPC 素材授权会话已变化，已拒绝旧任务")
            if error is None and isinstance(authorization, Mapping):
                if self.asset_broker is not None:
                    handle = str(authorization.get("asset_handle") or "")
                    try:
                        generation = int(authorization.get("worker_generation") or 0)
                    except (TypeError, ValueError):
                        generation = 0
                    if handle and generation > 0:
                        self._native_handles.add((handle, generation))
                self._cache[cache_key] = authorization
                if len(self._cache) > 256:
                    self._cache.pop(next(iter(self._cache)))
            elif error is None:
                error = NativeAssetAuthorizationError("NPC 素材授权结果无效")
            if flight is not None:
                flight.authorization = authorization
                flight.error = error
                if current_flight is flight:
                    self._inflight.pop(cache_key, None)
                flight.event.set()
        if error is not None:
            raise error
        if not isinstance(authorization, Mapping):
            raise NativeAssetAuthorizationError("NPC 素材授权结果无效")
        self.ensure_snapshot_current(authorization_snapshot)
        return authorization

    def verify(
        self,
        path: Path,
        authorization: Mapping[str, Any],
        *,
        snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> None:
        bound_snapshot = self.snapshot_for_authorization(authorization)
        authorization_snapshot = snapshot or bound_snapshot
        if bound_snapshot.cache_identity != authorization_snapshot.cache_identity:
            raise NativeAssetAuthorizationError("NPC 素材授权与解码快照不一致")
        self.ensure_snapshot_current(authorization_snapshot)
        try:
            target, signature = self._file_signature(path)
            expected_path = Path(authorization.get("path") or "").resolve(strict=True)
            expected_size = int(authorization.get("file_size") or -1)
            expected_digest = str(authorization.get("file_sha256") or "")
            authorization_id = str(authorization.get("authorization_id") or "").strip()
        except Exception as exc:
            raise NativeAssetAuthorizationError("NPC 素材授权后复核失败") from exc
        bound_identity = getattr(authorization, "file_identity", None)
        if (
            target != expected_path
            or expected_size != int(signature[1])
            or not isinstance(bound_identity, tuple)
            or bound_identity != signature
        ):
            raise NativeAssetAuthorizationError("NPC 素材在授权后发生变化，已拒绝读取")

        verification_key = None
        verification_flight = None
        is_verification_leader = True
        if authorization_id:
            verification_key = (
                authorization_snapshot.cache_identity,
                authorization_id,
                signature,
                expected_digest,
            )
            with self._lock:
                if verification_key in self._verification_cache:
                    self.ensure_snapshot_current(authorization_snapshot)
                    return
                verification_flight = self._verification_inflight.get(verification_key)
                if verification_flight is None:
                    verification_flight = _VerificationFlight(threading.Event())
                    self._verification_inflight[verification_key] = verification_flight
                else:
                    is_verification_leader = False

        if not is_verification_leader:
            if verification_flight is None or not verification_flight.event.wait(30.0):
                raise NativeAssetAuthorizationError("NPC 素材授权复核等待超时")
            if verification_flight.error is not None:
                raise verification_flight.error
            with self._lock:
                if verification_key in self._verification_cache:
                    self.ensure_snapshot_current(authorization_snapshot)
                    return
            raise NativeAssetAuthorizationError("NPC 素材并发授权复核结果无效")

        verification_error = None
        try:
            actual_digest = self._full_file_sha256(target)
            _target, current_signature = self._file_signature(target)
            self.ensure_snapshot_current(authorization_snapshot)
        except Exception as exc:
            if isinstance(exc, NativeAssetAuthorizationError):
                verification_error = exc
            else:
                verification_error = NativeAssetAuthorizationError("NPC 素材授权后复核失败")
                verification_error.__cause__ = exc
        if verification_error is None:
            try:
                matches = current_signature == signature and hmac.compare_digest(
                    expected_digest.encode("ascii"),
                    actual_digest.encode("ascii"),
                )
            except Exception as exc:
                verification_error = NativeAssetAuthorizationError("NPC 素材授权后复核失败")
                verification_error.__cause__ = exc
            else:
                if not matches:
                    verification_error = NativeAssetAuthorizationError(
                        "NPC 素材在授权后发生变化，已拒绝读取"
                    )
        if verification_key is not None:
            with self._lock:
                current_flight = self._verification_inflight.get(verification_key)
                if (
                    verification_error is None
                    and not self._snapshot_matches_locked(authorization_snapshot)
                ):
                    verification_error = NativeAssetAuthorizationError(
                        "NPC 素材授权会话已变化，已拒绝旧任务"
                    )
                if verification_error is None:
                    self._verification_cache[verification_key] = None
                    if len(self._verification_cache) > 512:
                        self._verification_cache.pop(next(iter(self._verification_cache)))
                if verification_flight is not None:
                    verification_flight.error = verification_error
                    if current_flight is verification_flight:
                        self._verification_inflight.pop(verification_key, None)
                    verification_flight.event.set()
        if verification_error is not None:
            raise verification_error
        self.ensure_snapshot_current(authorization_snapshot)


def read_text_guess(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "cp936"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

@dataclass(frozen=True)
class PakResourceLoad:
    path: Path
    password: str
    display_name: str

@dataclass(frozen=True)
class RenderImageAsset:
    image: Image.Image
    origin_x: int = 0
    origin_y: int = 0
    file_name: str = ''

def prioritized_asset_candidate_names(file_name: str) -> list[str]:
    requested = PureWindowsPath(file_name).name
    if not requested:
        return []
    path = PureWindowsPath(requested)
    stem = path.stem
    suffix = path.suffix.lower()
    names: list[str] = []

    def add(name: str) -> None:
        if not name:
            return
        if name.casefold() not in {item.casefold() for item in names}:
            names.append(name)

    groups: dict[str, tuple[str, ...]] = {
        "pak": (".Pak", ".pak", ".PAK"),
        # WIL-family resources are paired data/index files.  Include the
        # index suffixes in normal candidate expansion so callers that ask for
        # Items1.wil / Items1.wzl can still discover versions where directory
        # scans or user selections surfaced Items1.wix / Items1.wzx first.
        "wzl": (".wzl", ".WZL", ".wzx", ".WZX"),
        "wil": (".wil", ".WIL", ".wix", ".WIX"),
        "wis": (".wis", ".WIS", ".wix", ".WIX"),
    }
    suffix_group = {
        ".pak": "pak",
        ".wzl": "wzl",
        ".wzx": "wzl",
        ".wil": "wil",
        ".wix": "wil",
        ".wis": "wis",
    }.get(suffix)
    if suffix_group is not None:
        add(requested)
        ordered_groups = [suffix_group]
        for name in ("pak", "wzl", "wil", "wis"):
            if name != suffix_group:
                ordered_groups.append(name)
    else:
        add(requested)
        ordered_groups = ["pak", "wzl", "wil", "wis"]
    for group in ordered_groups:
        for ext in groups[group]:
            add(f"{stem}{ext}")
    return names

def load_records_for_pak(
    path: Path,
    password: str,
    *,
    gate: NativeAssetReadGate,
    purpose: str,
    asset_index: int = -1,
    authorization: Mapping[str, Any] | None = None,
    authorized_files: AuthorizedAssetFiles | None = None,
) -> list[AssetRecord]:
    if not isinstance(gate, NativeAssetReadGate):
        raise NativeAssetAuthorizationError("NPC 素材读取缺少原生授权门")
    if authorized_files is None:
        if Path(path).suffix.lower() in {".wzl", ".wzx", ".wil", ".wix", ".wis"}:
            authorized_files = _authorize_wil_family(gate, path, purpose, asset_index)
        else:
            if authorization is None:
                snapshot = gate.capture_snapshot()
                current = gate.authorize(
                    path,
                    purpose,
                    asset_index,
                    password,
                    snapshot=snapshot,
                )
            else:
                current = authorization
                snapshot = gate.snapshot_for_authorization(current)
                gate.ensure_snapshot_current(snapshot)
            authorized_files = AuthorizedAssetFiles(
                [(Path(path).resolve(), current)],
                snapshot=snapshot,
            )
    _validate_authorized_file_set(path, authorized_files)
    _ensure_authorized_files_current(gate, authorized_files)
    native_authorization = authorized_files[0][1] if authorized_files else {}
    native_broker = getattr(gate, "asset_broker", None)
    native_handle = str(native_authorization.get("asset_handle") or "")
    wil_family = Path(path).suffix.lower() in {".wzl", ".wzx", ".wil", ".wix", ".wis"}
    native_index_handle = ""
    if native_broker is not None and wil_family:
        if len(authorized_files) < 2:
            raise NativeAssetAuthorizationError("原生 WIL/WZX 授权不完整，已禁止 Python 解码回退")
        index_authorization = authorized_files[1][1]
        native_index_handle = str(index_authorization.get("asset_handle") or "")
        if not native_index_handle:
            raise NativeAssetAuthorizationError("原生 WIL/WZX 授权未返回索引 handle，已禁止 Python 解码回退")
        if int(index_authorization.get("worker_generation") or 0) != int(
            native_authorization.get("worker_generation") or 0
        ):
            raise NativeAssetAuthorizationError("原生 WIL/WZX handle 不属于同一 worker generation")
    if native_broker is not None and not native_handle:
        raise NativeAssetAuthorizationError("原生素材 worker 授权未返回 asset handle，已禁止 Python 解码回退")
    if native_broker is not None and native_handle:
        payload = native_broker.list_records(
            native_handle,
            int(native_authorization.get("worker_generation") or 0),
            native_index_handle or None,
        )
        records = []
        for line in payload.decode("ascii", errors="strict").splitlines():
            if not line.startswith("record="):
                continue
            values = line[7:].split(",")
            if len(values) != 11:
                raise NativeAssetAuthorizationError("native PAK record metadata is invalid")
            index, offset, data_offset, data_length, width, height, origin_x, origin_y, image_type, alpha, packed = map(int, values)
            bits = 8 if image_type == 3 else 16 if image_type in (4, 5) else 24 if image_type == 6 else 32 if image_type in (7, 9) else 0
            if offset == 0:
                records.append(AssetRecord(index, f"{index:05d}", f"{index:05d}_empty.png", None, 0, 0, "empty", "", "empty", Path(path), source_magic=str(native_authorization.get("magic") or "")))
                continue
            if bits == 0:
                raise NativeAssetAuthorizationError("native PAK image type is unsupported")
            stride = (width * bits + 31 & -32) // 8
            alpha_stride = (width * 8 + 31 & -32) // 8 if alpha else 0
            record = AssetRecord(
                index, f"{index:05d}", f"{index:05d}_{width}x{height}_{bits}b_native_recovered_pak.png", None,
                width, height, f"{bits}b type={image_type}", "native", "recovered_pak", path,
                data_offset, data_length, stride * height + alpha_stride * height, None, bits, stride, alpha_stride,
                image_type, alpha, True, None, packed, origin_x, origin_y, None, "recovered_pak", index,
                str(native_authorization.get("magic") or ""),
            )
            record._native_asset_worker = native_broker
            record._native_asset_handle = native_handle
            record._native_asset_index_handle = native_index_handle
            record._native_worker_generation = int(native_authorization.get("worker_generation") or 0)
            records.append(record)
        _verify_authorized_files(gate, authorized_files)
        return mark_records_native_authorized(records, _authorization_marker(authorized_files))
    decode_profile = _decode_profile_for_authorized_files(authorized_files)
    resolved_password = str(decode_profile.get("resolved_password") or "")
    if load_pak_assets is not None:
        records = load_pak_assets(
            path,
            resolved_password,
            decode_profile=decode_profile,
        ).records
        _verify_authorized_files(gate, authorized_files)
        return mark_records_native_authorized(
            records,
            _authorization_marker(authorized_files),
        )
    if read_magic is None:
        raise RuntimeError("当前目录缺少 pak_asset_browser.py，不能加载 PAK 图片")
    raise RuntimeError("当前目录缺少 pak_loader.py，不能加载 PAK 图片")


def _authorize_wil_family(
    gate: NativeAssetReadGate,
    image_path: Path,
    purpose: str,
    asset_index: int,
    *,
    snapshot: AssetAuthorizationSnapshot | None = None,
) -> AuthorizedAssetFiles:
    data_path, index_path, _magic, _kind = _resolve_wil_asset_paths(Path(image_path))
    if not hasattr(gate, "_lock"):
        # Compatibility for deny-only test/subclass gates that intentionally do
        # not initialize NativeAssetReadGate. A successful unbound result is
        # still rejected and can never reach a decoder.
        gate.authorize(data_path.resolve(), purpose, asset_index, "")
        raise NativeAssetAuthorizationError("NPC 素材授权门缺少会话快照状态")
    authorization_snapshot = snapshot or gate.capture_snapshot()
    gate.ensure_snapshot_current(authorization_snapshot)
    authorized = AuthorizedAssetFiles(snapshot=authorization_snapshot)
    seen: set[Path] = set()
    for candidate in (data_path, index_path):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        authorized.append(
            (
                resolved,
                gate.authorize(
                    resolved,
                    purpose,
                    asset_index,
                    "",
                    snapshot=authorization_snapshot,
                ),
            )
        )
    gate.ensure_snapshot_current(authorization_snapshot)
    return authorized


def _authorize_asset_files(
    gate: NativeAssetReadGate,
    path: Path,
    purpose: str,
    asset_index: int,
    password: str,
    *,
    snapshot: AssetAuthorizationSnapshot | None = None,
) -> AuthorizedAssetFiles:
    resolved = Path(path).resolve()
    if resolved.suffix.lower() in {".wzl", ".wzx", ".wil", ".wix", ".wis"}:
        return _authorize_wil_family(
            gate,
            resolved,
            purpose,
            asset_index,
            snapshot=snapshot,
        )
    if not hasattr(gate, "_lock"):
        gate.authorize(resolved, purpose, asset_index, password)
        raise NativeAssetAuthorizationError("NPC 素材授权门缺少会话快照状态")
    authorization_snapshot = snapshot or gate.capture_snapshot()
    gate.ensure_snapshot_current(authorization_snapshot)
    authorization = gate.authorize(
        resolved,
        purpose,
        asset_index,
        password,
        snapshot=authorization_snapshot,
    )
    gate.ensure_snapshot_current(authorization_snapshot)
    return AuthorizedAssetFiles(
        [(resolved, authorization)],
        snapshot=authorization_snapshot,
    )


def _authorized_files_snapshot(
    authorized: list[tuple[Path, Mapping[str, Any]]],
) -> AssetAuthorizationSnapshot:
    snapshot = getattr(authorized, "snapshot", None)
    if not isinstance(authorized, AuthorizedAssetFiles) or not isinstance(
        snapshot, AssetAuthorizationSnapshot
    ):
        raise NativeAssetAuthorizationError("NPC 素材授权文件集合缺少会话快照")
    for entry in authorized:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise NativeAssetAuthorizationError("NPC 素材授权文件集合格式无效")
        _path, authorization = entry
        candidate = getattr(authorization, "snapshot", None)
        if (
            not isinstance(candidate, AssetAuthorizationSnapshot)
            or candidate.cache_identity != snapshot.cache_identity
        ):
            raise NativeAssetAuthorizationError("NPC 素材配对文件授权快照不一致")
    return snapshot


def _ensure_authorized_files_current(
    gate: NativeAssetReadGate,
    authorized: list[tuple[Path, Mapping[str, Any]]],
) -> AssetAuthorizationSnapshot:
    snapshot = _authorized_files_snapshot(authorized)
    gate.ensure_snapshot_current(snapshot)
    return snapshot


def _decode_profile_for_authorized_files(
    authorized: list[tuple[Path, Mapping[str, Any]]],
) -> Mapping[str, Any]:
    _authorized_files_snapshot(authorized)
    if not authorized:
        raise NativeAssetAuthorizationError("NPC 素材授权结果为空")
    profile = authorized[0][1]
    if not isinstance(profile, Mapping):
        raise NativeAssetAuthorizationError("NPC 素材授权格式配置无效")
    fields = (
        "resolved_password",
        "header_password",
        "prefix_size",
        "data_base",
        "allowed_index_modes",
        "format_version",
    )
    expected = tuple(str(profile.get(name) or "") for name in fields)
    for _path, candidate in authorized[1:]:
        if not isinstance(candidate, Mapping):
            raise NativeAssetAuthorizationError("NPC 素材配对文件授权格式无效")
        actual = tuple(str(candidate.get(name) or "") for name in fields)
        if actual != expected:
            raise NativeAssetAuthorizationError("NPC 素材配对文件授权格式不一致")
    return profile


def _validate_authorized_file_set(
    path: Path,
    authorized: list[tuple[Path, Mapping[str, Any]]],
) -> None:
    snapshot = None
    if isinstance(authorized, AuthorizedAssetFiles):
        snapshot = _authorized_files_snapshot(authorized)
    target = Path(path).resolve(strict=True)
    if target.suffix.lower() in {".wzl", ".wzx", ".wil", ".wix", ".wis"}:
        data_path, index_path, _magic, _kind = _resolve_wil_asset_paths(target)
        expected_paths = []
        for candidate in (data_path, index_path):
            resolved = candidate.resolve(strict=True)
            if resolved not in expected_paths:
                expected_paths.append(resolved)
    else:
        expected_paths = [target]
    actual_paths: list[Path] = []
    for entry in authorized:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise NativeAssetAuthorizationError("NPC 素材授权文件集合格式无效")
        candidate, authorization = entry
        if not isinstance(authorization, Mapping):
            raise NativeAssetAuthorizationError("NPC 素材授权对象无效")
        if snapshot is not None:
            bound_snapshot = getattr(authorization, "snapshot", None)
            if (
                not isinstance(bound_snapshot, AssetAuthorizationSnapshot)
                or bound_snapshot.cache_identity != snapshot.cache_identity
            ):
                raise NativeAssetAuthorizationError("NPC 素材授权文件快照不一致")
        resolved = Path(candidate).resolve(strict=True)
        bound_path = Path(authorization.get("path") or "").resolve(strict=True)
        if resolved != bound_path:
            raise NativeAssetAuthorizationError("NPC 素材授权路径绑定不一致")
        actual_paths.append(resolved)
    if actual_paths != expected_paths or len(set(actual_paths)) != len(actual_paths):
        raise NativeAssetAuthorizationError("NPC 素材授权文件集合与解码目标不一致")


def _authorization_marker(
    authorized: list[tuple[Path, Mapping[str, Any]]],
) -> str:
    _authorized_files_snapshot(authorized)
    values = [str(item.get("authorization_id") or "") for _path, item in authorized]
    if len(values) == 1:
        return values[0]
    return hashlib.sha256("|".join(values).encode("ascii", errors="strict")).hexdigest()


def _asset_cache_identity(
    gate: NativeAssetReadGate,
    paths: list[Path] | tuple[Path, ...],
    password: str = "",
    snapshot: AssetAuthorizationSnapshot | None = None,
) -> tuple[Any, ...]:
    authorization_snapshot = snapshot or gate.capture_snapshot()
    gate.ensure_snapshot_current(authorization_snapshot)
    identities = tuple(gate.file_identity(Path(path)) for path in paths)
    gate.ensure_snapshot_current(authorization_snapshot)
    return (
        authorization_snapshot.cache_identity,
        identities,
        hashlib.sha256(str(password or "").encode("utf-8", errors="strict")).hexdigest(),
    )


def _authorized_cache_identity(
    gate: NativeAssetReadGate,
    authorized: list[tuple[Path, Mapping[str, Any]]],
    password: str = "",
    snapshot: AssetAuthorizationSnapshot | None = None,
) -> tuple[Any, ...]:
    if not isinstance(gate, NativeAssetReadGate):
        raise NativeAssetAuthorizationError("NPC 素材读取缺少原生授权门")
    authorization_snapshot = _authorized_files_snapshot(authorized)
    if (
        snapshot is not None
        and snapshot.cache_identity != authorization_snapshot.cache_identity
    ):
        raise NativeAssetAuthorizationError("NPC 素材缓存身份快照不一致")
    identities = []
    for path, authorization in authorized:
        identity = getattr(authorization, "file_identity", None)
        if not isinstance(identity, tuple) or not identity:
            raise NativeAssetAuthorizationError("NPC 素材授权缺少文件身份")
        if Path(path).resolve() != Path(str(identity[0])):
            raise NativeAssetAuthorizationError("NPC 素材授权文件身份路径不一致")
        identities.append(identity)
    return (
        authorization_snapshot.cache_identity,
        tuple(identities),
        hashlib.sha256(str(password or "").encode("utf-8", errors="strict")).hexdigest(),
    )


def _verify_authorized_files(
    gate: NativeAssetReadGate,
    authorized: list[tuple[Path, Mapping[str, Any]]],
) -> None:
    snapshot = _ensure_authorized_files_current(gate, authorized)
    for path, authorization in authorized:
        gate.verify(path, authorization, snapshot=snapshot)
    gate.ensure_snapshot_current(snapshot)

class MerchantBackgroundProvider:

    def __init__(
        self,
        effect_list_path: Path = WindowsPath('E:/MirServer巅峰潜龙提取测试/Mir200/Envir/EffectImageList.txt'),
        pak_password_path: Path = WindowsPath('E:/MirServer巅峰潜龙提取测试/登录器/pak.txt'),
        data_dir: Path = WindowsPath('E:/MirServer巅峰潜龙提取测试/登录器/补丁文件夹/Data'),
        *,
        session_provider: Callable[[], Mapping[str, Any] | None] | None = None,
        asset_gate: NativeAssetReadGate | None = None,
    ) -> None:
        self.effect_list_path = effect_list_path
        self.pak_password_path = pak_password_path
        self.data_dir = data_dir
        self.data_dirs = (data_dir,)
        self.effect_files = None
        self.passwords = None
        self.data_file_candidates_cache = {}
        # Recursive directory scans are expensive; reuse them per directory.
        self.dir_scan_cache = {}
        self.records_cache = {}
        self.image_cache = {}
        self.wzl_cache = {}
        self.asset_gate = asset_gate or NativeAssetReadGate(session_provider)
        self.last_status = ""
        self.generation = 0

    def configure(self, effect_list_path: Path, pak_password_path: Path, data_dir: Path, data_dirs: tuple[Path, ...] | list[Path] | None = None) -> None:
        normalized_dirs = tuple(data_dirs or (data_dir,))
        changed = effect_list_path != self.effect_list_path or pak_password_path != self.pak_password_path or data_dir != self.data_dir or normalized_dirs != self.data_dirs
        self.effect_list_path = effect_list_path
        self.pak_password_path = pak_password_path
        self.data_dir = data_dir
        self.data_dirs = normalized_dirs
        if changed:
            self.clear()

    def clear(self) -> None:
        self.effect_files = None
        self.passwords = None
        self.data_file_candidates_cache.clear()
        self.dir_scan_cache.clear()
        self.records_cache.clear()
        self.image_cache.clear()
        self.wzl_cache.clear()
        self.last_status = ""
        self.generation += 1

    def get(self, spec: Any | None) -> Image.Image | None:
        self.last_status = ""
        if spec is None:
            return None
        try:
            image, file_name = self.image_for_wil(spec.wil_index, spec.image_index)
            self.last_status = f"背景 {file_name} #{spec.image_index}"
            return image
        except NativeAssetAuthorizationError:
            raise
        except Exception as exc:
            self.last_status = f"背景加载失败: {exc}"
            return None

    def image_for_wil(self, wil_index: int, image_index: int) -> tuple[Image.Image, str]:
        asset = self.image_asset_for_wil(wil_index, image_index)
        return (asset.image, asset.file_name)

    def image_for_dialog_resource(self, wil_index: int, image_index: int) -> tuple[Image.Image, str]:
        return self.image_for_wil(wil_index, image_index)

    def image_for_file_name(self, file_name: str, image_index: int) -> tuple[Image.Image, str]:
        asset = self.image_asset_for_file_name(file_name, image_index)
        return (asset.image, asset.file_name)

    def prewarm_file_names(self, file_names, max_workers: int = 6) -> int:
        """Authorize several asset files concurrently before the render loop.

        Each file still goes through the full lease / native-core / consume
        cycle; only the waiting overlaps. Authorizing serially costs one native
        round trip per file, which dominates the time to open an NPC.
        NativeAssetReadGate already holds a lock and de-duplicates in-flight
        requests, so concurrent callers for the same file collapse into one.
        """
        wanted: list[Path] = []
        seen: set[str] = set()
        for file_name in file_names or ():
            name = str(file_name or "").strip()
            if not name:
                continue
            try:
                candidates = self.data_file_candidates(name)
            except Exception:
                continue
            for asset_path in candidates:
                if asset_path.suffix.lower() in {".wzl", ".wzx", ".wis", ".wil", ".wix"}:
                    continue
                try:
                    resolved = asset_path.resolve()
                except OSError:
                    continue
                key = str(resolved).lower()
                if key in seen:
                    break
                seen.add(key)
                wanted.append(resolved)
                break

        def warm(path: Path) -> bool:
            try:
                self.records_for_file(path, self.password_for_file(path.name))
                return True
            except Exception:
                # Prewarming is best effort; the render path reports real errors.
                return False

        if len(wanted) < 2:
            return sum(1 for path in wanted if warm(path))
        workers = max(1, min(int(max_workers), len(wanted)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return sum(1 for ok in pool.map(warm, wanted) if ok)

    def pending_load_for_file_name(self, file_name: str) -> PakResourceLoad | None:
        for asset_path in self.data_file_candidates(file_name):
            if asset_path.suffix.lower() in {'.wzl', '.wzx', '.wis', '.wil', '.wix'}:
                continue
            password = self.password_for_file(asset_path.name)
            pak_path = asset_path.resolve()
            key = _asset_cache_identity(
                self.asset_gate, (pak_path,), password
            )
            if key not in self.records_cache:
                return PakResourceLoad(pak_path, password, asset_path.name)
        return None

    def file_name_for_index(self, index: int) -> str:
        files = self.load_effect_files()
        if index < 0 or index >= len(files):
            raise IndexError(f"EffectImageList 序号 {index} 超出范围，总数 {len(files)}")
        file_name = files[index].strip()
        if not file_name:
            raise ValueError(f"EffectImageList 序号 {index} 是空行")
        return file_name

    def load_effect_files(self) -> list[str]:
        if self.effect_files is None:
            if not self.effect_list_path.is_file():
                raise FileNotFoundError(str(self.effect_list_path))
            self.effect_files = read_text_guess(self.effect_list_path).splitlines()
        return self.effect_files

    def load_passwords(self) -> dict[str, str]:
        if self.passwords is not None:
            return self.passwords
        if not self.pak_password_path.is_file():
            raise FileNotFoundError(str(self.pak_password_path))
        passwords = {}
        for line in read_text_guess(self.pak_password_path).splitlines():
            line = line.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) < 2:
                continue
            raw_path = parts[0].strip()
            base_name = PureWindowsPath(raw_path).name.lower()
            if base_name:
                passwords[base_name] = parts[1].strip()
        self.passwords = passwords
        return passwords

    def password_for_file(self, file_name: str) -> str:
        base_name = PureWindowsPath(file_name).name.lower()
        passwords = {}
        try:
            passwords = self.load_passwords()
        except FileNotFoundError:
            # Some private patch folders ship PAK files without a pak.txt.  The
            # recovered asset reader can infer the common GeePak/WZL defaults
            # from the file magic, so keep rendering instead of failing early.
            passwords = {}
        password = passwords.get(base_name)
        if password is None:
            return ""
        return password

    def find_data_file(self, file_name: str) -> Path:
        candidates = self.data_file_candidates(file_name)
        if candidates:
            return candidates[0]
        requested = PureWindowsPath(file_name).name
        raise FileNotFoundError(str(self.data_dir / requested))

    def data_file_candidates(self, file_name: str) -> list[Path]:
        requested = PureWindowsPath(file_name).name
        cache_key = requested.casefold()
        cached = self.data_file_candidates_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        candidate_names = prioritized_asset_candidate_names(requested)
        search_dirs = []
        for directory in self.data_dirs or (self.data_dir,):
            if directory.is_dir() and directory not in search_dirs:
                search_dirs.append(directory)
        if not search_dirs:
            raise FileNotFoundError(str(self.data_dir))
        candidates = []

        seen_resolved: set[str] = set()

        def add_candidate(path: Path) -> None:
            # A set of resolved paths avoids re-resolving every earlier
            # candidate on each insert.
            try:
                key = str(path.resolve()).casefold()
            except OSError:
                return
            if key in seen_resolved:
                return
            seen_resolved.add(key)
            candidates.append(path)

        # Names first: prioritized_asset_candidate_names ranks the requested
        # extension ahead of the other container formats, so every directory
        # must be tried for it before a different format can win.
        for candidate_name in candidate_names:
            for directory in search_dirs:
                candidate = directory / candidate_name
                if candidate.is_file():
                    add_candidate(candidate)
        lower_names = {name.lower() for name in candidate_names}
        for directory in search_dirs:
            scan_key = str(directory).casefold()
            children = self.dir_scan_cache.get(scan_key)
            if children is None:
                try:
                    children = tuple(directory.rglob("*"))
                except OSError:
                    children = ()
                self.dir_scan_cache[scan_key] = children
            if not children:
                continue
            for child in children:
                # Compare the name before touching the filesystem: is_file()
                # is a syscall and these scans hold thousands of entries.
                if child.name.lower() not in lower_names:
                    continue
                if child.is_file():
                    add_candidate(child)
        self.data_file_candidates_cache[cache_key] = tuple(candidates)
        return candidates

    def records_for_file(
        self,
        pak_path: Path,
        password: str,
        *,
        asset_index: int = -1,
        purpose: str = "npc-background",
    ) -> list[AssetRecord]:
        pak_path = pak_path.resolve()
        authorized = _authorize_asset_files(
            self.asset_gate,
            pak_path,
            purpose,
            asset_index,
            password,
        )
        key = _authorized_cache_identity(
            self.asset_gate, authorized, password
        )
        if key not in self.records_cache:
            self.records_cache[key] = load_records_for_pak(
                pak_path,
                password,
                gate=self.asset_gate,
                purpose=purpose,
                asset_index=asset_index,
                authorized_files=authorized,
            )
        else:
            mark_records_native_authorized(
                self.records_cache[key],
                _authorization_marker(authorized),
            )
        _ensure_authorized_files_current(self.asset_gate, authorized)
        return self.records_cache[key]

    def put_records_for_file(self, pak_path: Path, password: str, records: list[AssetRecord]) -> None:
        pak_path = pak_path.resolve()
        authorized = _authorize_asset_files(
            self.asset_gate,
            pak_path,
            "npc-background",
            -1,
            password,
        )
        key = _authorized_cache_identity(
            self.asset_gate,
            authorized,
            password,
        )
        _verify_authorized_files(self.asset_gate, authorized)
        mark_records_native_authorized(records, _authorization_marker(authorized))
        self.records_cache[key] = records
        self.generation += 1

    def read_wil_or_wzl_image(self, image_path: Path, index: int) -> Image.Image:
        return self.read_wil_or_wzl_image_asset(image_path, index).image

    def image_asset_for_wil(self, wil_index: int, image_index: int) -> RenderImageAsset:
        file_name = self.file_name_for_index(wil_index)
        return self.image_asset_for_file_name(file_name, image_index)

    def image_asset_for_dialog_resource(self, wil_index: int, image_index: int) -> RenderImageAsset:
        return self.image_asset_for_wil(wil_index, image_index)

    def image_asset_for_file_name(self, file_name: str, image_index: int) -> RenderImageAsset:
        last_error = None
        unsupported_candidate = False
        for asset_path in self.data_file_candidates(file_name):
            try:
                return self.image_asset_for_path(asset_path, file_name, image_index)
            except NativeAssetAuthorizationError as exc:
                if _is_unsupported_asset_candidate(exc):
                    unsupported_candidate = True
                    continue
                raise
            except (IndexError, ValueError, RuntimeError, OSError) as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
        if unsupported_candidate:
            raise FileNotFoundError(f"{file_name} 没有可识别的素材候选")
        raise FileNotFoundError(str(self.data_dir / PureWindowsPath(file_name).name))

    def image_asset_for_path(self, asset_path: Path, file_name: str, image_index: int) -> RenderImageAsset:
        asset_path = asset_path.resolve()
        suffix = asset_path.suffix.lower()
        if suffix in {'.wzl', '.wzx', '.wis', '.wil', '.wix'}:
            return self.read_wil_or_wzl_image_asset(asset_path, image_index)
        password = self.password_for_file(asset_path.name)
        authorized = _authorize_asset_files(
            self.asset_gate,
            asset_path,
            "npc-background",
            image_index,
            password,
        )
        key = (
            _authorized_cache_identity(
                self.asset_gate, authorized, password
            ),
            image_index,
        )
        # Authorization is still checked on every cache access; the cached
        # payload is additionally bound to the current session and file identity.
        cached = self.image_cache.get(key)
        if isinstance(cached, RenderImageAsset):
            _ensure_authorized_files_current(self.asset_gate, authorized)
            return RenderImageAsset(cached.image.copy(), cached.origin_x, cached.origin_y, cached.file_name)
        if isinstance(cached, Image.Image):
            _ensure_authorized_files_current(self.asset_gate, authorized)
            return RenderImageAsset(cached.copy(), 0, 0, asset_path.name)
        records = self.records_for_file(asset_path, password, asset_index=image_index)
        _ensure_authorized_files_current(self.asset_gate, authorized)
        if image_index < 0 or image_index >= len(records):
            raise IndexError(f"{file_name} image index {image_index} out of range, total {len(records)}")
        record = records[image_index]
        image = image_for_record(record).convert("RGBA")
        image.load()
        _verify_authorized_files(self.asset_gate, authorized)
        asset = RenderImageAsset(image, getattr(record, "origin_x", 0), getattr(record, "origin_y", 0), asset_path.name)
        self.image_cache[key] = asset
        return RenderImageAsset(asset.image.copy(), asset.origin_x, asset.origin_y, asset.file_name)

    def read_wil_or_wzl_image_asset(self, image_path: Path, index: int) -> RenderImageAsset:
        image_path = image_path.resolve()
        authorized = _authorize_wil_family(self.asset_gate, image_path, "npc-background", index)
        key = (
            _authorized_cache_identity(self.asset_gate, authorized),
            index,
        )
        cached = self.wzl_cache.get(key)
        if isinstance(cached, RenderImageAsset):
            _ensure_authorized_files_current(self.asset_gate, authorized)
            return RenderImageAsset(cached.image.copy(), cached.origin_x, cached.origin_y, cached.file_name)
        if isinstance(cached, Image.Image):
            _ensure_authorized_files_current(self.asset_gate, authorized)
            return RenderImageAsset(cached.copy(), 0, 0, image_path.name)
        _ensure_authorized_files_current(self.asset_gate, authorized)
        asset = WzlImageProvider._read_image_asset_file_unchecked(
            image_path,
            index,
            decode_profile=_decode_profile_for_authorized_files(authorized),
        )
        _verify_authorized_files(self.asset_gate, authorized)
        self.wzl_cache[key] = asset
        return RenderImageAsset(asset.image.copy(), asset.origin_x, asset.origin_y, asset.file_name)

class WzlImageProvider:


    def __init__(
        self,
        data_dir: Path = WindowsPath('E:/MirServer巅峰潜龙提取测试/登录器/补丁文件夹/Data'),
        *,
        session_provider: Callable[[], Mapping[str, Any] | None] | None = None,
        asset_gate: NativeAssetReadGate | None = None,
    ) -> None:
        self.data_dir = data_dir
        self.data_dirs = (data_dir,)
        self.pak_txt_path = None
        self.stditems_db_path = None
        self.cache = {}
        self.item_records_cache = {}
        self.item_passwords = None
        self.background_cache = None
        self.background_cache_key = None
        self.item_looks_cache = None
        self.item_ids_by_name_cache = None
        self.item_fields_by_name_cache = {}
        self.item_looks_path = None
        self.item_file_candidates_cache = {}
        self.last_status = ""
        self.generation = 0
        self.asset_gate = asset_gate or NativeAssetReadGate(session_provider)

    def configure(
        self,
        data_dir: Path,
        stditems_db_path: Path | str | None = None,
        data_dirs: tuple[Path, ...] | list[Path] | None = None,
        pak_txt_path: Path | str | None = None,
    ) -> None:
        normalized_db_path = Path(stditems_db_path) if stditems_db_path else None
        normalized_dirs = tuple(data_dirs or (data_dir,))
        normalized_pak_txt_path = Path(pak_txt_path) if pak_txt_path else None
        data_changed = data_dir != self.data_dir or normalized_dirs != self.data_dirs
        db_changed = normalized_db_path != self.stditems_db_path
        pak_txt_changed = normalized_pak_txt_path != self.pak_txt_path
        if data_changed or db_changed or pak_txt_changed:
            self.data_dir = data_dir
            self.data_dirs = normalized_dirs
            self.stditems_db_path = normalized_db_path
            self.pak_txt_path = normalized_pak_txt_path
            self.item_looks_cache = None
            self.item_ids_by_name_cache = None
            self.item_fields_by_name_cache.clear()
            self.item_looks_path = None
            self.last_status = ""
        if data_changed or pak_txt_changed:
            self.cache.clear()
            self.item_records_cache.clear()
            self.item_passwords = None
            self.background_cache = None
            self.background_cache_key = None
            self.item_file_candidates_cache.clear()
        if data_changed or db_changed or pak_txt_changed:
            self.generation += 1

    def find_items_wzl(self) -> Path:
        candidates = (candidate for candidate in self.item_data_file_candidates("Items.wzl"))
        for candidate in candidates:
            if candidate.is_file():
                return candidate
        raise FileNotFoundError("Items.wzl not found")

    def get_item_background(self) -> Image.Image | None:
        try:
            asset_path = next(iter(self.item_data_file_candidates("NewopUI.pak")), None)
            if asset_path is None:
                raise FileNotFoundError("NewopUI.pak")
            password = self.password_for_item_file("NewopUI.pak", asset_path)
            authorized = _authorize_asset_files(
                self.asset_gate,
                asset_path,
                "npc-item",
                ITEMSHOW_BACKGROUND_INDEX,
                password,
            )
            background_cache_key = _authorized_cache_identity(
                self.asset_gate,
                authorized,
                password,
            )
            if (
                self.background_cache is not None
                and self.background_cache_key == background_cache_key
            ):
                _ensure_authorized_files_current(self.asset_gate, authorized)
                return self.background_cache.copy()
            records = self.records_for_item_file(
                asset_path,
                password,
                asset_index=ITEMSHOW_BACKGROUND_INDEX,
                authorized_files=authorized,
            )
            if ITEMSHOW_BACKGROUND_INDEX >= len(records):
                raise IndexError(f"NewopUI.pak index {ITEMSHOW_BACKGROUND_INDEX} out of range")
            _ensure_authorized_files_current(self.asset_gate, authorized)
            image = image_for_record(records[ITEMSHOW_BACKGROUND_INDEX]).convert("RGBA")
            image.load()
            _verify_authorized_files(self.asset_gate, authorized)
            self.background_cache = image
            self.background_cache_key = background_cache_key
            return image.copy()
        except NativeAssetAuthorizationError:
            raise
        except Exception as exc:
            self.last_status = f"ItemShow 背景加载失败: {exc}"
            return None

    @staticmethod
    def _sibling_with_suffix(path: Path, suffixes: tuple[str, ...]) -> Path | None:
        for suffix in suffixes:
            candidate = path.with_suffix(suffix)
            if candidate.is_file():
                return candidate
        if path.parent.is_dir():
            stem = path.stem.lower()
            wanted = {suffix.lower() for suffix in suffixes}
            for child in path.parent.iterdir():
                if child.is_file() and child.stem.lower() == stem and child.suffix.lower() in wanted:
                    return child

    @staticmethod
    def _read_image_asset_file_unchecked(
        image_path: Path,
        index: int,
        *,
        decode_profile: Mapping[str, Any] | None = None,
    ) -> RenderImageAsset:
        from embedded_npc_visual.core.npc_preview.recovered_asset_reader import load_recovered_wil_records, record_to_image
        _magic, _count, records, _mode = load_recovered_wil_records(
            image_path,
            decode_profile=decode_profile,
        )
        if index < 0 or index >= len(records):
            raise IndexError(f"{image_path.name} index {index} out of range, total {len(records)}")
        record = records[index]
        if getattr(record, "kind", "") == "empty":
            raise ValueError(f"{image_path.name} index {index} is empty")
        image = record_to_image(record).convert("RGBA")
        image.load()
        return RenderImageAsset(image, int(getattr(record, "origin_x", 0)), int(getattr(record, "origin_y", 0)), str(getattr(record, "file_name", image_path.name)))

    def read_image_asset_file(
        self,
        image_path: Path,
        index: int,
        *,
        _authorized_files: AuthorizedAssetFiles | None = None,
    ) -> RenderImageAsset:
        authorized = _authorized_files or _authorize_wil_family(
            self.asset_gate, image_path, "npc-item", index
        )
        _ensure_authorized_files_current(self.asset_gate, authorized)
        native_broker = getattr(self.asset_gate, "asset_broker", None)
        if native_broker is not None and len(authorized) < 2:
            raise NativeAssetAuthorizationError("原生 WIL/WZX 授权不完整，已禁止 Python 解码回退")
        if native_broker is not None and len(authorized) >= 2:
            data_authorization = authorized[0][1]
            index_authorization = authorized[1][1]
            data_handle = str(data_authorization.get("asset_handle") or "")
            index_handle = str(index_authorization.get("asset_handle") or "")
            if not data_handle or not index_handle:
                raise NativeAssetAuthorizationError("原生 WIL/WZX 授权未返回完整 handle，已禁止 Python 解码回退")
            if data_handle and index_handle:
                generation = int(data_authorization.get("worker_generation") or 0)
                payload = native_broker.list_records(data_handle, generation, index_handle)
                selected = None
                for line in payload.decode("ascii", errors="strict").splitlines():
                    if not line.startswith("record="):
                        continue
                    values = line[7:].split(",")
                    if len(values) != 11:
                        continue
                    parsed = tuple(map(int, values))
                    if parsed[0] == int(index):
                        selected = parsed
                        break
                if selected is None:
                    raise IndexError(f"{image_path.name} index {index} out of range")
                (_uid, offset, data_offset, data_length, width, height, origin_x, origin_y, image_type, alpha, packed) = selected
                if offset == 0:
                    raise ValueError(f"{image_path.name} index {index} is empty")
                bits = 8 if image_type == 3 else 16 if image_type in (4, 5) else 24 if image_type == 6 else 32 if image_type in (7, 9) else 0
                if bits == 0:
                    raise NativeAssetAuthorizationError("native WIL image type is unsupported")
                stride = (width * bits + 31 & -32) // 8
                record = AssetRecord(
                    index, f"{index:05d}", f"{index:05d}_{width}x{height}_{bits}b_native_wil.png", None,
                    width, height, f"{bits}b type={image_type}", "native", "recovered_wil", Path(image_path),
                    data_offset, data_length, stride * height, None, bits, stride, 0, image_type, alpha, True,
                    None, packed, origin_x, origin_y, None, "recovered_wil", index, str(data_authorization.get("magic") or ""),
                )
                record._native_asset_worker = native_broker
                record._native_asset_handle = data_handle
                record._native_asset_index_handle = index_handle
                record._native_worker_generation = generation
                mark_records_native_authorized([record], _authorization_marker(authorized))
                image = image_for_record(record).convert("RGBA")
                image.load()
                _verify_authorized_files(self.asset_gate, authorized)
                return RenderImageAsset(image, origin_x, origin_y, record.file_name)
        asset = self._read_image_asset_file_unchecked(
            image_path,
            index,
            decode_profile=_decode_profile_for_authorized_files(authorized),
        )
        _verify_authorized_files(self.asset_gate, authorized)
        return asset

    def read_image_file(self, image_path: Path, index: int) -> Image.Image:
        return self.read_image_asset_file(image_path, index).image

    def get_asset(
        self,
        index: int | None = None,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> RenderImageAsset | None:
        if index is None:
            self.last_status = "ItemShow image index missing"
            return None
        try:
            asset_path = self.find_items_wzl().resolve()
            asset = self._read_item_asset_path(
                asset_path,
                asset_path.name,
                index,
                _snapshot=_snapshot,
            )
            self.last_status = f"ItemShow {asset.file_name} #{index}"
            return RenderImageAsset(asset.image.copy(), asset.origin_x, asset.origin_y, asset.file_name)
        except (NativeAssetAuthorizationError, NativeAssetWorkerError):
            raise
        except Exception as exc:
            self.last_status = f"ItemShow load failed: {exc}"
            return None

    def get_item_asset(
        self,
        item_id: int,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> RenderImageAsset | None:
        looks = self.image_index_for_item_id(item_id)
        if looks is None:
            self.last_status = f"ItemShow item {item_id} has no StdItems.Looks mapping"
            return
        asset = self.get_asset_for_looks(looks, _snapshot=_snapshot)
        if asset is not None:
            image_index = self.item_image_index_for_looks(looks)
            self.last_status = f"ItemShow item {item_id} Looks {looks} -> {asset.file_name} #{image_index}"
        return asset

    def image_index_for_item_id(self, item_id: int) -> int | None:
        return self.item_looks().get(item_id)

    @staticmethod
    def item_image_index_for_looks(looks: int) -> int:
        if looks >= 10000:
            return looks % 10000
        return looks

    def get_asset_for_looks(
        self,
        looks: int,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> RenderImageAsset | None:
        image_index = self.item_image_index_for_looks(looks)
        if looks >= 10000:
            segment = looks // 10000
            return self._get_segmented_item_asset(
                segment,
                image_index,
                _snapshot=_snapshot,
            )
        return self.get_asset(image_index, _snapshot=_snapshot)

    def _get_segmented_item_asset(
        self,
        segment: int,
        image_index: int,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> RenderImageAsset | None:
        file_names = [
            f"Items{segment}.Pak", f"Items{segment}.pak", f"Items{segment}.wzl", f"Items{segment}.WZL",
            f"Items{segment}.wil", f"Items{segment}.WIL", f"Items{segment}.wis", f"Items{segment}.WIS",
        ]
        last_error = None
        seen = set()
        for file_name in file_names:
            for asset_path in self.item_data_file_candidates(file_name):
                resolved = asset_path.resolve()
                if resolved in seen:
                    continue
                seen.add(resolved)
                try:
                    return self._read_item_asset_path(
                        asset_path,
                        file_name,
                        image_index,
                        _snapshot=_snapshot,
                    )
                except NativeAssetAuthorizationError as exc:
                    if _is_unsupported_asset_candidate(exc):
                        continue
                    raise
                except NativeAssetWorkerError:
                    raise
                except (IndexError, ValueError, RuntimeError, OSError, KeyError) as exc:
                    last_error = exc
        if last_error is not None:
            self.last_status = f"ItemShow segmented item load failed: {last_error}"
        else:
            self.last_status = f"ItemShow segmented item file Items{segment} not found"
        return None

    def item_data_file_candidates(self, file_name: str) -> list[Path]:
        requested = PureWindowsPath(file_name).name
        cache_key = requested.casefold()
        cached = self.item_file_candidates_cache.get(cache_key)
        if cached is not None:
            return list(cached)
        candidate_names = prioritized_asset_candidate_names(requested)
        search_dirs = []
        for directory in self.data_dirs or (self.data_dir,):
            if directory.is_dir() and directory not in search_dirs:
                search_dirs.append(directory)
        candidates = []

        def add_candidate(path: Path) -> None:
            resolved = path.resolve()
            if all(candidate.resolve() != resolved for candidate in candidates):
                candidates.append(path)

        lower_names = {name.lower() for name in candidate_names}
        for directory in search_dirs:
            for candidate_name in candidate_names:
                candidate = directory / candidate_name
                if candidate.is_file():
                    add_candidate(candidate)
            try:
                children = tuple(directory.rglob("*"))
            except OSError:
                continue
            for child in children:
                # Compare the name before touching the filesystem: is_file()
                # is a syscall and these scans hold thousands of entries.
                if child.name.lower() not in lower_names:
                    continue
                if child.is_file():
                    add_candidate(child)
        self.item_file_candidates_cache[cache_key] = tuple(candidates)
        return candidates

    def _read_item_asset_path(
        self,
        asset_path: Path,
        file_name: str,
        image_index: int,
        *,
        _snapshot: AssetAuthorizationSnapshot | None = None,
    ) -> RenderImageAsset:
        asset_path = asset_path.resolve()
        suffix = asset_path.suffix.lower()
        authorized = None
        records = None
        if suffix in frozenset({".wzl", ".wzx", ".wis", ".wil", ".wix"}):
            authorized = _authorize_wil_family(
                self.asset_gate,
                asset_path,
                "npc-item",
                image_index,
                snapshot=_snapshot,
            )
            cache_identity = _authorized_cache_identity(
                self.asset_gate, authorized
            )
        else:
            password = self.password_for_item_file(file_name, asset_path)
            authorized = _authorize_asset_files(
                self.asset_gate,
                asset_path,
                "npc-item",
                image_index,
                password,
                snapshot=_snapshot,
            )
            records = self.records_for_item_file(
                asset_path,
                password,
                asset_index=image_index,
                authorized_files=authorized,
            )
            cache_identity = _authorized_cache_identity(
                self.asset_gate,
                authorized,
                password,
            )
        key = (cache_identity, image_index)
        cached = self.cache.get(key)
        if isinstance(cached, RenderImageAsset):
            _ensure_authorized_files_current(self.asset_gate, authorized)
            self.last_status = f"ItemShow {cached.file_name} #{image_index}"
            return RenderImageAsset(cached.image.copy(), cached.origin_x, cached.origin_y, cached.file_name)
        if suffix in frozenset({".wzl", ".wzx", ".wis", ".wil", ".wix"}):
            asset = self.read_image_asset_file(
                asset_path,
                image_index,
                _authorized_files=authorized,
            )
        else:
            if records is None:
                raise NativeAssetAuthorizationError("NPC 素材记录授权状态无效")
            if image_index < 0 or image_index >= len(records):
                raise IndexError(f"{asset_path.name} image index {image_index} out of range, total {len(records)}")
            record = records[image_index]
            _ensure_authorized_files_current(self.asset_gate, authorized)
            image = image_for_record(record).convert("RGBA")
            image.load()
            _verify_authorized_files(self.asset_gate, authorized)
            asset = RenderImageAsset(image, getattr(record, "origin_x", 0), getattr(record, "origin_y", 0), asset_path.name)
        self.cache[key] = asset
        self.last_status = f"ItemShow {asset.file_name} #{image_index}"
        return RenderImageAsset(asset.image.copy(), asset.origin_x, asset.origin_y, asset.file_name)

    def records_for_item_file(
        self,
        pak_path: Path,
        password: str,
        *,
        asset_index: int = -1,
        authorized_files: AuthorizedAssetFiles | None = None,
    ) -> list[AssetRecord]:
        pak_path = pak_path.resolve()
        authorized = authorized_files
        if authorized is None:
            authorized = _authorize_asset_files(
                self.asset_gate, pak_path, "npc-item", asset_index, password
            )
        _validate_authorized_file_set(pak_path, authorized)
        _ensure_authorized_files_current(self.asset_gate, authorized)
        key = _authorized_cache_identity(
            self.asset_gate, authorized, password
        )

        if key not in self.item_records_cache:
            self.item_records_cache[key] = load_records_for_pak(
                pak_path,
                password,
                gate=self.asset_gate,
                purpose="npc-item",
                asset_index=asset_index,
                authorized_files=authorized,
            )
        else:
            mark_records_native_authorized(
                self.item_records_cache[key],
                _authorization_marker(authorized),
            )
        _ensure_authorized_files_current(self.asset_gate, authorized)
        return self.item_records_cache[key]

    def password_for_item_file(self, file_name: str, asset_path: Path) -> str:
        base_name = PureWindowsPath(asset_path.name or file_name).name.lower()
        password = self.load_item_passwords().get(base_name)
        if password is not None:
            return password
        return ""

    def load_item_passwords(self) -> dict[str, str]:
        if self.item_passwords is not None:
            return self.item_passwords
        passwords = {}
        pak_txt = self.find_pak_txt()
        if pak_txt is not None:
            for line in read_text_guess(pak_txt).splitlines():
                line = line.strip()
                if not line or line.startswith(";") or line.startswith("#"):
                    continue
                parts = line.split("|")
                if len(parts) < 2:
                    continue
                base_name = PureWindowsPath(parts[0].strip()).name.lower()
                if base_name:
                    passwords[base_name] = parts[1]

        self.item_passwords = passwords
        return passwords

    def find_pak_txt(self) -> Path | None:
        if self.pak_txt_path is not None and self.pak_txt_path.is_file():
            return self.pak_txt_path
        search_dirs: list[Path] = []
        for base in (self.data_dirs or (self.data_dir,)):
            if base not in search_dirs:
                search_dirs.append(base)
            for parent in list(base.parents)[:4]:
                if parent not in search_dirs:
                    search_dirs.append(parent)
        seen: set[Path] = set()
        for directory in search_dirs:
            try:
                key = directory.resolve()
            except OSError:
                key = directory.absolute()
            if key in seen:
                continue
            seen.add(key)
            candidate = directory / "pak.txt"
            if candidate.is_file():
                return candidate
        return None

    def item_looks(self) -> dict[int, int]:
        if self.item_looks_cache is None:
            self.item_looks_cache = self._load_item_looks()
        return self.item_looks_cache

    def item_id_for_name(self, item_name: str) -> int | None:
        name = str(item_name or "").strip().casefold()
        if not name:
            return None
        if self.item_ids_by_name_cache is None:
            self.item_ids_by_name_cache = self._load_item_ids_by_name()
        return self.item_ids_by_name_cache.get(name)

    def item_field_for_name(self, item_name: str, field_name: str) -> object | None:
        name = str(item_name or "").strip().casefold()
        field = str(field_name or "").strip().casefold()
        if not name or not field:
            return None
        if field in {"idx", "index", "id"}:
            return self.item_id_for_name(item_name)
        mapping = self.item_fields_by_name_cache.get(field)
        if mapping is None:
            mapping = self._load_item_field_by_name(field)
            self.item_fields_by_name_cache[field] = mapping
        return mapping.get(name)

    def _load_item_field_by_name(self, field_name: str) -> dict[str, object]:
        db_path = self.find_stditems_db()
        if db_path is None:
            return {}
        try:
            if self._path_is_sqlite(db_path):
                conn = sqlite3.connect(str(db_path))
                try:
                    table_row = conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1",
                        ("StdItems",),
                    ).fetchone()
                    if table_row is None:
                        return {}
                    table_name = str(table_row[0])
                    columns = [
                        str(row[1])
                        for row in conn.execute(
                            f"PRAGMA table_info({self._quote_identifier(table_name)})"
                        )
                    ]
                    column_map = {column.casefold(): column for column in columns}
                    name_column = column_map.get("name")
                    value_column = column_map.get(field_name)
                    if not name_column or not value_column:
                        return {}
                    rows = conn.execute(
                        f"SELECT {self._quote_identifier(name_column)}, "
                        f"{self._quote_identifier(value_column)} "
                        f"FROM {self._quote_identifier(table_name)}"
                    )
                    return {
                        str(raw_name).strip().casefold(): raw_value
                        for raw_name, raw_value in rows
                        if raw_name is not None and str(raw_name).strip()
                    }
                finally:
                    conn.close()
            if DbcTable is None:
                return {}
            table = DbcTable(str(db_path))
            columns = {column.name.casefold(): index for index, column in enumerate(table.columns)}
            name_index = columns.get("name")
            value_index = columns.get(field_name)
            if name_index is None or value_index is None:
                return {}
            return {
                str(row[name_index]).strip().casefold(): row[value_index]
                for row in table.rows()
                if row[name_index] is not None and str(row[name_index]).strip()
            }
        except Exception as exc:
            self.last_status = f"StdItems field lookup failed: {exc}"
            return {}

    def _load_item_ids_by_name(self) -> dict[str, int]:
        db_path = self.find_stditems_db()
        if db_path is None:
            return {}
        try:
            if self._path_is_sqlite(db_path):
                conn = sqlite3.connect(str(db_path))
                try:
                    table_row = conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1",
                        ("StdItems",),
                    ).fetchone()
                    if table_row is None:
                        return {}
                    table_name = str(table_row[0])
                    columns = [
                        row[1]
                        for row in conn.execute(
                            f"PRAGMA table_info({self._quote_identifier(table_name)})"
                        )
                    ]
                    column_map = {str(column).casefold(): str(column) for column in columns}
                    name_column = column_map.get("name")
                    item_column = column_map.get("idx") or column_map.get("index") or column_map.get("id")
                    if not name_column or not item_column:
                        return {}
                    rows = conn.execute(
                        f"SELECT {self._quote_identifier(name_column)}, "
                        f"{self._quote_identifier(item_column)} "
                        f"FROM {self._quote_identifier(table_name)}"
                    )
                    return {
                        str(raw_name).strip().casefold(): item_id
                        for raw_name, raw_item_id in rows
                        if raw_name is not None
                        for item_id in (self._to_int(raw_item_id),)
                        if item_id is not None and str(raw_name).strip()
                    }
                finally:
                    conn.close()
            if DbcTable is None:
                return {}
            table = DbcTable(str(db_path))
            columns = {column.name.casefold(): index for index, column in enumerate(table.columns)}
            name_index = columns.get("name")
            item_index = columns.get("idx") if "idx" in columns else columns.get("index", columns.get("id"))
            if name_index is None or item_index is None:
                return {}
            mapping = {}
            for row in table.rows():
                item_id = self._to_int(row[item_index])
                item_name = str(row[name_index] or "").strip()
                if item_id is not None and item_name:
                    mapping[item_name.casefold()] = item_id
            return mapping
        except Exception as exc:
            self.last_status = f"StdItems item-name lookup failed: {exc}"
            return {}

    def _load_item_looks(self) -> dict[int, int]:
        db_path = self.find_stditems_db()
        self.item_looks_path = db_path
        if db_path is None:
            return {}
        try:
            if self._path_is_sqlite(db_path):
                return self._load_sqlite_item_looks(db_path)
            if DbcTable is None:
                return {}
            table = DbcTable(str(db_path))
            column_indexes = {column.name.casefold(): index for index, column in enumerate(table.columns)}
            looks_index = column_indexes.get("looks")
            if looks_index is None:
                return {}
            item_index = column_indexes.get("idx") if "idx" in column_indexes else (column_indexes.get("index") if "index" in column_indexes else column_indexes.get("id"))
            mapping = {}
            for row_number, row in enumerate(table.rows()):
                raw_item_id = row[item_index] if item_index is not None else row_number
                item_id = self._to_int(raw_item_id)
                looks = self._to_int(row[looks_index])
                if item_id is None or looks is None:
                    continue
                mapping[item_id] = looks
            return mapping
        except Exception as exc:
            self.last_status = f"StdItems.DB load failed: {exc}"
            return {}

    def find_stditems_db(self) -> Path | None:
        if self.stditems_db_path is not None:
            configured = self._stditems_source_from_configured_path(self.stditems_db_path)
            if configured is not None:
                return configured
        roots = [
         self.data_dir]
        roots.extend(list(self.data_dir.parents)[:4])
        version_root = self.data_dir.parents[2] if len(self.data_dir.parents) > 2 else None
        candidates = []
        for root in roots:
            candidates.append(root / "StdItems.DB")
        if version_root is not None:
            candidates.extend([
             version_root / "Mud2" / "DB" / "StdItems.DB",
             version_root / "Mir200" / "Envir" / "StdItems.DB",
             version_root / "Mir200" / "StdItems.DB",
             version_root / "StdItems.DB"])
        seen = set()
        for candidate in candidates:
            resolved_parent = candidate.parent.resolve() if candidate.parent.exists() else candidate.parent
            key = resolved_parent / candidate.name.lower()
            if key in seen:
                continue
            seen.add(key)
            found = self._case_insensitive_file(candidate)
            if found is not None:
                return found

        search_dirs = []
        if version_root is not None:
            search_dirs.extend([
             version_root / "Mud2" / "DB",
             version_root / "Mir200" / "Envir",
             version_root / "Mir200"])
        search_dirs.extend(roots)
        seen_dirs = set()
        for directory in search_dirs:
            if not directory.is_dir():
                continue
            key = directory.resolve()
            if key in seen_dirs:
                continue
            seen_dirs.add(key)
            found = self._sqlite_file_with_stditems_in_dir(directory)
            if found is not None:
                return found
        return None

    def _stditems_source_from_configured_path(self, path: Path) -> Path | None:
        if path.is_dir():
            # A version can retain an old DBC2000 StdItems.DB beside the current
            # SQLite aggregate (for example ApexM2.DB). Directory auto-detection
            # must prefer the live SQLite table or new item names resolve to 0.
            sqlite_source = self._sqlite_file_with_stditems_in_dir(path)
            if sqlite_source is not None:
                return sqlite_source
            stditems = self._case_insensitive_file(path / "StdItems.DB")
            if stditems is not None:
                return stditems
            return None
        if not path.is_file():
            return None
        if self._path_is_sqlite(path) and self._sqlite_has_table(path, "StdItems"):
            return path
        if path.name.casefold() == "stditems.db":
            return path
        # The shared database selector can point at an empty or unrelated
        # SQLite database. ItemShow still needs the StdItems database located
        # beside it (for example ApexM2.db next to an empty GEEM21.db).
        return self._sqlite_file_with_stditems_in_dir(path.parent)

    def _sqlite_file_with_stditems_in_dir(self, directory: Path) -> Path | None:
        candidates = []
        for child in directory.iterdir():
            if child.is_file() and child.suffix.lower() in {'.sqlite3', '.sqlite', '.db'}:
                candidates.append(child)
        candidates.sort(key=lambda item: (0 if item.stem.casefold() == "stditems" else 1, item.name.casefold()))
        for candidate in candidates:
            if self._path_is_sqlite(candidate) and self._sqlite_has_table(candidate, "StdItems"):
                return candidate
        return None

    @staticmethod
    def _sqlite_has_table(path: Path, table_name: str) -> bool:
        try:
            conn = sqlite3.connect(str(path))
            try:
                row = conn.execute("SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1", (table_name,)).fetchone()
                return row is not None
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    @staticmethod
    def _path_is_sqlite(path: Path) -> bool:
        if not path.is_file() or path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
            return False
        try:
            with path.open("rb") as handle:
                return handle.read(16) == b"SQLite format 3\x00"
        except OSError:
            return False

    def _load_sqlite_item_looks(self, path: Path) -> dict[int, int]:
        mapping = {}
        conn = sqlite3.connect(str(path))
        try:
            table_row = conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1", ("StdItems",)).fetchone()
            if table_row is None:
                return mapping
            table_name = str(table_row[0])
            columns = [row[1] for row in conn.execute(f"PRAGMA table_info({self._quote_identifier(table_name)})")]
            column_map = {str(name).casefold(): str(name) for name in columns}
            looks_col = column_map.get("looks")
            if not looks_col:
                return mapping
            item_col = column_map.get("idx") or column_map.get("index") or column_map.get("id")
            table_sql = self._quote_identifier(table_name)
            looks_sql = self._quote_identifier(looks_col)
            if item_col:
                item_sql = self._quote_identifier(item_col)
                rows = conn.execute(f"SELECT {item_sql}, {looks_sql} FROM {table_sql}")
                for raw_item_id, raw_looks in rows:
                    item_id = self._to_int(raw_item_id)
                    looks = self._to_int(raw_looks)
                    if item_id is not None and looks is not None:
                        mapping[item_id] = looks
            else:
                rows = conn.execute(f"SELECT {looks_sql} FROM {table_sql}")
                for row_number, (raw_looks,) in enumerate(rows):
                    looks = self._to_int(raw_looks)
                    if looks is not None:
                        mapping[row_number] = looks
            return mapping
        finally:
            conn.close()

    @staticmethod
    def _quote_identifier(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    @staticmethod
    def _case_insensitive_file(path: Path) -> Path | None:
        if path.is_file():
            return path
        parent = path.parent
        if not parent.is_dir():
            return None
        target = path.name.casefold()
        for child in parent.iterdir():
            if child.is_file() and child.name.casefold() == target:
                return child
        return None

    @staticmethod
    def _to_int(value: object) -> int | None:
        try:
            text = "" if value is None else str(value).strip()
            if not text:
                return None
            return int(float(text))
        except (TypeError, ValueError):
            return None

    def get(self, index: int | None = None) -> Image.Image | None:
        asset = self.get_asset(index)
        if asset is None:
            return None
        return asset.image

    def _read_wzl_image_asset(self, wzl_path: Path, index: int) -> RenderImageAsset:
        return self.read_image_asset_file(wzl_path, index)

    def _read_wzl_image(self, wzl_path: Path, index: int) -> Image.Image:
        return self.read_image_file(wzl_path, index)
