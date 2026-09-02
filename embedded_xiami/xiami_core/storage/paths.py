from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
XIAMI_HOME = Path(os.environ.get("XIAMI_HOME", PROJECT_ROOT / "runtime" / "xiami_v1"))
KERNEL_HOME = XIAMI_HOME / "kernels"
CONFIG_FILE = XIAMI_HOME / "config.json"
LOG_HOME = XIAMI_HOME / "logs"


def ensure_runtime_dirs() -> None:
    XIAMI_HOME.mkdir(parents=True, exist_ok=True)
    KERNEL_HOME.mkdir(parents=True, exist_ok=True)
    LOG_HOME.mkdir(parents=True, exist_ok=True)


def _fsync_directory(directory: Path) -> None:
    if os.name == "nt":
        return
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    """Commit bytes with a same-directory stage and byte-exact rollback."""

    target = Path(path)
    parent = target.parent
    parent_existed = parent.exists()
    parent.mkdir(parents=True, exist_ok=True)
    stage_fd, stage_name = tempfile.mkstemp(prefix=f".{target.name}.xiami-stage-", dir=str(parent))
    stage = Path(stage_name)
    rollback: Path | None = None
    replaced = False
    try:
        with os.fdopen(stage_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if target.exists():
            rollback_fd, rollback_name = tempfile.mkstemp(
                prefix=f".{target.name}.xiami-rollback-", dir=str(parent)
            )
            rollback = Path(rollback_name)
            with os.fdopen(rollback_fd, "wb") as handle:
                handle.write(target.read_bytes())
                handle.flush()
                os.fsync(handle.fileno())
        os.replace(str(stage), str(target))
        replaced = True
        _fsync_directory(parent)
    except BaseException:
        if replaced:
            if rollback is not None and rollback.exists():
                os.replace(str(rollback), str(target))
            else:
                with suppress(OSError):
                    target.unlink()
            with suppress(OSError):
                _fsync_directory(parent)
        raise
    finally:
        with suppress(OSError):
            stage.unlink()
        if rollback is not None:
            with suppress(OSError):
                rollback.unlink()
        if not parent_existed:
            with suppress(OSError):
                parent.rmdir()


def json_bytes_preserving_source(payload: object, source: bytes | None = None) -> bytes:
    import json

    raw = source or b""
    bom = raw.startswith(b"\xef\xbb\xbf")
    body = raw[3:] if bom else raw
    newline = "\r\n" if b"\r\n" in body else "\n"
    trailing = body.endswith((b"\n", b"\r"))
    text = json.dumps(payload, ensure_ascii=False, indent=2).replace("\n", newline)
    if trailing:
        text += newline
    encoded = text.encode("utf-8")
    return (b"\xef\xbb\xbf" + encoded) if bom else encoded


def atomic_write_json(path: Path, payload: object) -> None:
    target = Path(path)
    source = target.read_bytes() if target.is_file() else None
    atomic_write_bytes(target, json_bytes_preserving_source(payload, source))
