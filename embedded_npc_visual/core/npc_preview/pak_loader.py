from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from .pak_asset_browser import AssetRecord
from .recovered_asset_reader import default_password_for_magic, load_recovered_resource_records, read_magic


@dataclass
class PakLoadResult:
    path: "Path"
    password: "str"
    magic: "str"
    slot_count: "int"
    valid_count: "int"
    empty_count: "int"
    blank_count: "int"
    mode: "str"
    records: "list[AssetRecord]"

    @property
    def record_count(self) -> "int":
        return len(self.records)

    @property
    def detail(self) -> "str":
        return f"{self.magic} slots={self.slot_count} records={self.record_count} valid={self.valid_count} empty={self.empty_count} mode={self.mode}"


def asset_is_valid(asset: "AssetRecord") -> "bool":
    return asset.kind not in {"blank", "empty"}


def count_valid_assets(records: "list[AssetRecord]") -> "int":
    return sum(1 for record in records if asset_is_valid(record))


def count_kind(records: "list[AssetRecord]", kind: "str") -> "int":
    return sum(1 for record in records if record.kind == kind)


def load_pak_assets(
    pak_path,
    password="",
    *,
    transparent_zero=True,
    progress: "Callable[[str], None] | None" = None,
    decode_profile: "Mapping[str, Any] | None" = None,
):
    path = Path(pak_path)
    if progress:
        progress(f"读取素材文件头: {path.name}")
    magic = read_magic(path)
    if decode_profile is not None:
        if not isinstance(decode_profile, Mapping):
            raise ValueError("authorized asset decode profile is invalid")
        resolved_password = str(decode_profile.get("resolved_password") or "")
        if password and password != resolved_password:
            raise ValueError("authorized asset password does not match the loader request")
        password = resolved_password
    else:
        password = password or default_password_for_magic(magic)
    if progress:
        progress(f'识别格式 {magic or "unknown"}，使用 recovered 素材读取器')
    magic, slot_count, records, mode = load_recovered_resource_records(
        path,
        password,
        transparent_zero=transparent_zero,
        progress=progress,
        decode_profile=decode_profile,
    )
    if progress:
        progress(f"索引解析完成: 槽位 {slot_count}，记录 {len(records)}")
    return PakLoadResult(
        path=path,
        password=password,
        magic=magic,
        slot_count=slot_count,
        valid_count=count_valid_assets(records),
        empty_count=count_kind(records, "empty"),
        blank_count=count_kind(records, "blank"),
        mode=mode,
        records=records,
    )


__all__ = [
    "PakLoadResult",
    "asset_is_valid",
    "count_kind",
    "count_valid_assets",
    "default_password_for_magic",
    "load_pak_assets",
    "read_magic",
]
