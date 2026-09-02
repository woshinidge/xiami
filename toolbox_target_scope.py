from __future__ import annotations

import hashlib
import json
import os
import stat
import unicodedata
from pathlib import Path
from typing import Iterable, Union


PathValue = Union[str, os.PathLike]


def _canonical_path(path: PathValue) -> str:
    raw = os.fspath(path)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("target path is empty")
    absolute = os.path.abspath(os.path.normpath(raw))
    normalized = os.path.normcase(absolute).replace("\\", "/")
    return unicodedata.normalize("NFC", normalized)


def _target_record(path: PathValue) -> dict:
    target = Path(path)
    info = os.stat(str(target), follow_symlinks=False)
    if stat.S_ISLNK(info.st_mode):
        raise ValueError("target path cannot be a symbolic link")
    if stat.S_ISREG(info.st_mode):
        kind = "file"
    elif stat.S_ISDIR(info.st_mode):
        kind = "directory"
    else:
        raise ValueError("target path must be a regular file or directory")
    return {
        "device": int(getattr(info, "st_dev", 0)),
        "file_id": int(getattr(info, "st_ino", 0)),
        "kind": kind,
        "path": _canonical_path(target),
    }


def compute_target_scope_sha256(feature: str, targets: Iterable[PathValue]) -> str:
    normalized_feature = str(feature or "").strip()
    if not normalized_feature or len(normalized_feature) > 128:
        raise ValueError("target scope feature is invalid")
    records = [_target_record(path) for path in targets]
    if not records:
        raise ValueError("target scope requires at least one path")
    records.sort(key=lambda item: (item["path"], item["kind"]))
    if len({item["path"] for item in records}) != len(records):
        raise ValueError("target scope contains duplicate paths")
    payload = {
        "feature": normalized_feature,
        "schema_version": 1,
        "targets": records,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8", errors="strict")
    return hashlib.sha256(canonical).hexdigest()


__all__ = ["compute_target_scope_sha256"]
