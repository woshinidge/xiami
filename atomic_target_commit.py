from __future__ import annotations

import contextlib
import os
import stat
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Tuple


TargetIdentity = Tuple[int, int, int, int]


class TargetChangedError(RuntimeError):
    pass


def _mtime_ns(value: os.stat_result) -> int:
    return int(getattr(value, "st_mtime_ns", int(value.st_mtime * 1000000000)))


def identity_from_stat(value: os.stat_result) -> TargetIdentity:
    return (
        int(getattr(value, "st_dev", 0)),
        int(getattr(value, "st_ino", 0)),
        int(getattr(value, "st_size", 0)),
        _mtime_ns(value),
    )


def target_identity(path: str | Path) -> TargetIdentity:
    return identity_from_stat(os.stat(str(path), follow_symlinks=False))


def _assert_regular(value: os.stat_result, path: Path) -> None:
    if not stat.S_ISREG(value.st_mode):
        raise TargetChangedError(f"目标不是普通文件：{path}")


def _open_windows_read_guard(path: Path) -> BinaryIO:
    import ctypes
    import msvcrt
    from ctypes import wintypes

    generic_read = 0x80000000
    file_share_read = 0x00000001
    file_share_delete = 0x00000004
    open_existing = 3
    file_attribute_normal = 0x00000080
    file_flag_open_reparse_point = 0x00200000
    invalid_handle_value = ctypes.c_void_p(-1).value

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
    close_handle = kernel32.CloseHandle
    close_handle.argtypes = (wintypes.HANDLE,)
    close_handle.restype = wintypes.BOOL

    handle = create_file(
        str(path),
        generic_read,
        file_share_read | file_share_delete,
        None,
        open_existing,
        file_attribute_normal | file_flag_open_reparse_point,
        None,
    )
    if handle == invalid_handle_value:
        error = ctypes.get_last_error()
        raise OSError(error, os.strerror(error), str(path))
    binary = int(getattr(os, "O_BINARY", 0))
    try:
        descriptor = msvcrt.open_osfhandle(int(handle), os.O_RDONLY | binary)
    except Exception:
        close_handle(handle)
        raise
    return os.fdopen(descriptor, "rb", closefd=True)


def _open_read_guard(path: Path) -> BinaryIO:
    if os.name == "nt":
        return _open_windows_read_guard(path)
    return open(str(path), "rb")


class TargetGuard:
    def __init__(
        self,
        path: Path,
        *,
        expected_exists: bool,
        expected_raw: Optional[bytes],
        expected_identity: Optional[TargetIdentity],
        stream: Optional[BinaryIO],
    ) -> None:
        self.path = Path(path)
        self.expected_exists = bool(expected_exists)
        self.expected_raw = None if expected_raw is None else bytes(expected_raw)
        self._stream = stream
        self._handle_identity: Optional[TargetIdentity] = None
        if stream is not None:
            current = os.fstat(stream.fileno())
            _assert_regular(current, self.path)
            self._handle_identity = identity_from_stat(current)
        self.expected_identity = expected_identity or self._handle_identity

    def _handle_raw(self) -> bytes:
        if self._stream is None:
            raise TargetChangedError(f"目标保护句柄不存在：{self.path}")
        self._stream.seek(0)
        raw = self._stream.read()
        self._stream.seek(0)
        return raw

    def assert_at_path(self, path: str | Path | None = None) -> bytes:
        target = self.path if path is None else Path(path)
        if not self.expected_exists:
            if os.path.lexists(str(target)):
                raise TargetChangedError(f"目标在提交前被外部创建：{target}")
            return b""
        if self._stream is None or self._handle_identity is None:
            raise TargetChangedError(f"目标保护句柄已失效：{target}")
        handle_stat = os.fstat(self._stream.fileno())
        _assert_regular(handle_stat, target)
        handle_identity = identity_from_stat(handle_stat)
        if self.expected_identity is not None and handle_identity != self.expected_identity:
            raise TargetChangedError(f"目标保护句柄身份变化：{target}")
        raw = self._handle_raw()
        if self.expected_raw is not None and raw != self.expected_raw:
            raise TargetChangedError(f"目标内容在提交窗口内变化：{target}")
        try:
            path_stat = os.stat(str(target), follow_symlinks=False)
        except FileNotFoundError as exc:
            raise TargetChangedError(f"目标在提交窗口内消失：{target}") from exc
        _assert_regular(path_stat, target)
        if os.path.islink(str(target)) or identity_from_stat(path_stat) != handle_identity:
            raise TargetChangedError(f"目标路径身份在提交窗口内变化：{target}")
        return raw

    def assert_current(self) -> bytes:
        return self.assert_at_path(self.path)

    def replace_from(self, stage_path: str | Path, expected_stage_raw: bytes) -> None:
        stage = Path(stage_path)
        self.assert_current()
        try:
            stage_stat = os.stat(str(stage), follow_symlinks=False)
        except FileNotFoundError as exc:
            raise TargetChangedError(f"暂存文件在提交前消失：{stage}") from exc
        _assert_regular(stage_stat, stage)
        if os.path.islink(str(stage)) or stage.read_bytes() != bytes(expected_stage_raw):
            raise TargetChangedError(f"暂存文件在提交前变化：{stage}")
        if self.expected_exists:
            _replace_existing(stage, self.path)
        elif os.name == "nt":
            # Windows os.rename is atomic and fails if a competing creator won.
            os.rename(str(stage), str(self.path))
        else:
            # POSIX rename replaces an existing target. Link is the atomic no-clobber primitive.
            os.link(str(stage), str(self.path))
            os.unlink(str(stage))

    def unlink(self) -> None:
        self.assert_current()
        os.unlink(str(self.path))

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.close()


@contextlib.contextmanager
def protected_target(
    path: str | Path,
    *,
    expected_exists: bool,
    expected_raw: Optional[bytes] = None,
    expected_identity: Optional[TargetIdentity] = None,
) -> Iterator[TargetGuard]:
    target = Path(path)
    stream: Optional[BinaryIO] = None
    if expected_exists:
        if not os.path.isfile(str(target)) or os.path.islink(str(target)):
            raise TargetChangedError(f"目标已不存在或不再是普通文件：{target}")
        stream = _open_read_guard(target)
    guard = TargetGuard(
        target,
        expected_exists=expected_exists,
        expected_raw=expected_raw,
        expected_identity=expected_identity,
        stream=stream,
    )
    try:
        guard.assert_current()
        yield guard
    finally:
        guard.close()


def write_exclusive(path: str | Path, payload: bytes, mode: int = 0o600) -> None:
    target = Path(path)
    binary = int(getattr(os, "O_BINARY", 0))
    descriptor = os.open(
        str(target),
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | binary,
        mode,
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _replace_existing(stage: Path, target: Path) -> None:
    if os.name != "nt":
        os.replace(str(stage), str(target))
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    replace_file = kernel32.ReplaceFileW
    replace_file.argtypes = (
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    )
    replace_file.restype = wintypes.BOOL
    if not replace_file(str(target), str(stage), None, 0, None, None):
        error = ctypes.get_last_error()
        # ReplaceFileW can fail on Windows Server 2012/2008 or network shares
        # (ERROR_UNABLE_TO_MOVE_REPLACEMENT=1176, ERROR_UNABLE_TO_MOVE_REPLACEMENT_2=1177,
        # or ERROR_ACCESS_DENIED=5 in some configurations). Fall back to os.replace
        # which is atomic on NTFS via MoveFileExW and safe for local paths.
        REPLACE_FALLBACK_ERRORS = {1176, 1177, 5, 32, 87}
        if error in REPLACE_FALLBACK_ERRORS:
            try:
                os.replace(str(stage), str(target))
                return
            except OSError:
                pass
        raise OSError(error, os.strerror(error), f"{stage} -> {target}")


def atomic_restore_bytes(
    path: str | Path,
    payload: bytes,
    *,
    expected_exists: bool,
    expected_raw: Optional[bytes],
    prefix: str,
    expected_identity: Optional[TargetIdentity] = None,
    mode: Optional[int] = None,
    atime_ns: Optional[int] = None,
    mtime_ns: Optional[int] = None,
) -> TargetIdentity:
    target = Path(path)
    token = os.urandom(8).hex()
    stage = target.with_name(f".{target.name}.{prefix}-{token}.tmp")
    write_exclusive(stage, bytes(payload))
    try:
        with protected_target(
            target,
            expected_exists=expected_exists,
            expected_raw=expected_raw,
            expected_identity=expected_identity,
        ) as target_guard:
            target_guard.replace_from(stage, payload)
        with protected_target(target, expected_exists=True, expected_raw=payload) as committed_guard:
            committed_guard.assert_current()
            if mode is not None:
                os.chmod(str(target), int(mode))
            if atime_ns is not None and mtime_ns is not None:
                try:
                    os.utime(str(target), ns=(int(atime_ns), int(mtime_ns)))
                except (AttributeError, OSError):
                    pass
            refreshed_identity = identity_from_stat(os.fstat(committed_guard._stream.fileno()))
            committed_guard._handle_identity = refreshed_identity
            committed_guard.expected_identity = refreshed_identity
            committed_guard.assert_current()
            return target_identity(target)
    finally:
        with contextlib.suppress(OSError):
            if os.path.exists(str(stage)):
                os.unlink(str(stage))


def atomic_unlink(
    path: str | Path,
    *,
    expected_raw: bytes,
    expected_identity: Optional[TargetIdentity] = None,
) -> None:
    with protected_target(
        path,
        expected_exists=True,
        expected_raw=expected_raw,
        expected_identity=expected_identity,
    ) as guard:
        guard.unlink()


__all__ = [
    "TargetChangedError",
    "TargetGuard",
    "TargetIdentity",
    "atomic_restore_bytes",
    "atomic_unlink",
    "identity_from_stat",
    "protected_target",
    "target_identity",
    "write_exclusive",
]
