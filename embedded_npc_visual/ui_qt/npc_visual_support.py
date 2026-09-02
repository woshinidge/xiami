from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from PySide2.QtCore import QSize
from PySide2.QtGui import QImage, QPixmap

try:
    from PIL import Image
    PIL_IMPORT_ERROR: BaseException | None = None
except BaseException as exc:
    Image = None
    PIL_IMPORT_ERROR = exc

try:
    from embedded_npc_visual.core.local_store import connect_local_store
    LOCAL_STORE_IMPORT_ERROR: BaseException | None = None
except BaseException as exc:
    connect_local_store = None
    LOCAL_STORE_IMPORT_ERROR = exc

try:
    from embedded_npc_visual.core.npc_preview.pak_asset_browser import (
        asset_record_has_pending_metadata,
        image_for_record,
        persist_record_corrections,
        thumbnail_for,
    )
    PAK_IMPORT_ERROR: BaseException | None = None
except BaseException as exc:
    asset_record_has_pending_metadata = None
    image_for_record = None
    persist_record_corrections = None
    thumbnail_for = None
    PAK_IMPORT_ERROR = exc


AsyncRunner = Callable[
    [Callable[[], object], Callable[[object], None], Callable[[BaseException], None]],
    None,
]


def _empty_path() -> str:
    return ""


def _default_engine_family() -> str:
    return "lf"


def _empty_session() -> dict[str, Any] | None:
    return None


@dataclass(frozen=True)
class NpcToolContext:
    get_version_path: Callable[[], str]
    get_login_folder: Callable[[], str]
    choose_version: Callable[[], None]
    load_npcs: Callable[[], list[Any]]
    read_text_file: Callable[[str], tuple[str, str]]
    run_async: AsyncRunner
    get_database_path: Callable[[], str] = _empty_path
    get_engine_family: Callable[[], str] = _default_engine_family
    get_patch_folder: Callable[[], str] = _empty_path
    get_client_folder: Callable[[], str] = _empty_path
    choose_patch_folder: Callable[[], None] = lambda: None
    get_session: Callable[[], dict[str, Any] | None] = _empty_session


def _error_text(exc: object) -> str:
    if isinstance(exc, BaseException):
        return str(exc) or exc.__class__.__name__
    return str(exc)


def _pil_to_pixmap(image: Any) -> QPixmap:
    if Image is None:
        raise RuntimeError(f"Pillow 未安装：{_error_text(PIL_IMPORT_ERROR)}")
    rgba = image.convert("RGBA")
    width, height = rgba.size
    data = rgba.tobytes("raw", "BGRA")
    qimage = QImage(data, width, height, width * 4, QImage.Format_ARGB32).copy()
    return QPixmap.fromImage(qimage)


def _load_record_image(record: Any) -> Any:
    if image_for_record is None:
        raise RuntimeError(_error_text(PAK_IMPORT_ERROR) or "image_for_record unavailable")
    image = image_for_record(record).convert("RGBA")
    image.load()
    return image.copy()


def _load_thumbnail_batch(records: list[tuple[int, Any]]) -> list[tuple[Any, ...]]:
    if thumbnail_for is None and image_for_record is None:
        message = _error_text(PAK_IMPORT_ERROR) or "asset image decoder unavailable"
        return [(index, None, message, None, None, None, False) for index, _record in records]

    results = []
    corrected_records = []
    for index, record in records:
        try:
            kind = str(getattr(record, "kind", "") or "").casefold()
            if kind in {"empty", "blank"} and thumbnail_for is not None:
                thumbnail = thumbnail_for(record)
            else:
                thumbnail = _load_record_image(record)
            thumbnail.load()
            if (
                asset_record_has_pending_metadata is not None
                and asset_record_has_pending_metadata(record)
            ):
                corrected_records.append((index, record))
            results.append(
                (
                    index,
                    thumbnail.copy(),
                    None,
                    int(getattr(record, "width", 0) or 0),
                    int(getattr(record, "height", 0) or 0),
                    str(getattr(record, "summary", "") or ""),
                    False,
                )
            )
        except BaseException as exc:
            results.append((index, None, _error_text(exc), None, None, None, False))

    persisted_indexes = set()
    if persist_record_corrections is not None:
        for index, record in corrected_records:
            try:
                if persist_record_corrections(record):
                    persisted_indexes.add(int(index))
            except BaseException:
                continue
    if persisted_indexes:
        results = [
            (*result[:6], int(result[0]) in persisted_indexes or bool(result[6]))
            for result in results
        ]
    return results


__all__ = [
    "LOCAL_STORE_IMPORT_ERROR",
    "NpcToolContext",
    "_error_text",
    "_load_record_image",
    "_load_thumbnail_batch",
    "_pil_to_pixmap",
    "connect_local_store",
]
