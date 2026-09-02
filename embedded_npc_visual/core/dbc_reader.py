"""Pure Python reader/writer for DBC2000 / Paradox ``.DB`` table files.

The project needs installation-free DBC browsing plus small table edits for
common Mir server DB files such as Magic.DB, Monster.DB, and StdItems.DB.
"""

from __future__ import annotations

import math
import os
import struct
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

_HEADER_SIZE = 120
_FIELD_TYPE_NAMES = {
    1: "Alpha", 2: "Date", 3: "Short", 4: "Long", 5: "Currency", 6: "Number",
    7: "Logical", 8: "Memo", 9: "Blob", 12: "Time", 13: "AutoInc", 14: "BCD",
    15: "Bytes", 20: "Timestamp",
}
_CODEPAGE_ENCODINGS = {437: "cp437", 932: "cp932", 936: "gbk", 949: "cp949", 950: "big5"}
DBC_SYSTEM_TABLES = {"pdoxusrs", "pdoxusrs.net", "pdoxusrs.lck"}


@dataclass
class DbcColumn:
    name: str
    type_code: int
    length: int
    offset: int

    @property
    def type_name(self) -> str:
        base = _FIELD_TYPE_NAMES.get(self.type_code, f"Type{self.type_code}")
        if self.type_code == 1:
            return f"{base}({self.length})"
        return base


class DbcDatabase:
    """Read-only view over a folder containing Paradox ``.DB`` tables."""

    def __init__(self, folder: str) -> None:
        self.folder = os.path.abspath(folder)
        if not os.path.isdir(self.folder):
            raise RuntimeError(f"DBC 数据库目录不存在:\n{folder}")
        if not self.list_tables():
            raise RuntimeError(f"DBC 数据库目录下没有找到 .DB 表文件:\n{self.folder}")

    def close(self) -> None:
        self._table.cache_clear()

    def list_tables(self) -> list[str]:
        tables = []
        for name in os.listdir(self.folder):
            stem, ext = os.path.splitext(name)
            if ext.lower() == ".db" and stem.lower() not in DBC_SYSTEM_TABLES:
                tables.append(stem)
        return sorted(set(tables), key=str.lower)

    def table_filename(self, table: str) -> str:
        wanted = table.lower()
        for name in os.listdir(self.folder):
            stem, ext = os.path.splitext(name)
            if ext.lower() == ".db" and stem.lower() == wanted:
                return name
        return f"{table}.DB"

    def get_columns(self, table: str) -> list[DbcColumn]:
        return self._table(table).columns

    def count_rows(self, table: str, keyword: str = "", columns: Iterable[str] = ()) -> int:
        return self._table(table).count(keyword, columns)

    def fetch_rows(self, table: str, *, keyword: str = "", columns: Iterable[str] = (), offset: int = 0, limit: int | None = None) -> list[tuple[Any, ...]]:
        return self._table(table).fetch(keyword=keyword, columns=columns, offset=offset, limit=limit)

    def all_rows(self, table: str) -> list[tuple[Any, ...]]:
        return self._table(table).rows()

    def update_column(self, table: str, column: str, value: Any, *, condition_column: str = "", condition_operator: str = "", condition_value: Any = None, only_rows: list[tuple[Any, ...]] | None = None) -> int:
        changed = self._table(table).update_column(column, value, condition_column=condition_column, condition_operator=condition_operator, condition_value=condition_value, only_rows=only_rows)
        self._table.cache_clear()
        return changed

    def append_rows(self, table: str, rows: Iterable[Iterable[Any]]) -> int:
        table_reader = self._table(table)
        changed = table_reader.append_rows(rows)
        self._table.cache_clear()
        return changed

    def update_cell(self, table: str, original_row: Iterable[Any], column: str, value: Any) -> int:
        changed = self._table(table).update_cell(original_row, column, value)
        self._table.cache_clear()
        return changed

    def delete_rows(self, table: str, rows: Iterable[Iterable[Any]]) -> int:
        changed = self._table(table).delete_rows(rows)
        self._table.cache_clear()
        return changed

    @lru_cache(maxsize=32)
    def _table(self, table: str) -> 'DbcTable':
        filename = self.table_filename(table)
        path = os.path.join(self.folder, filename)
        if not os.path.isfile(path):
            raise RuntimeError(f"DBC 表文件不存在:\n{path}")
        return DbcTable(path)


class DbcTable:
    def __init__(self, path: str) -> None:
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self._data = self._read_file(path)
        self.record_size = self._u16(0)
        self.header_size = self._u16(2)
        self.record_count = self._u32(6)
        self.file_blocks = self._u16(12)
        self.first_block = self._u16(14)
        self.field_count = self._u16(33)
        self.codepage = self._u16(106)
        self.encoding = _CODEPAGE_ENCODINGS.get(self.codepage, "gbk")
        self.columns = self._parse_columns()
        self._rows = None
        self._validate()

    @staticmethod
    def _read_file(path: str) -> bytes:
        with open(path, "rb") as handle:
            return handle.read()

    def _u16(self, offset: int) -> int:
        return struct.unpack_from("<H", self._data, offset)[0]

    def _u32(self, offset: int) -> int:
        return struct.unpack_from("<I", self._data, offset)[0]

    def _validate(self) -> None:
        if self.record_size <= 0:
            raise RuntimeError(f"DBC 表记录长度无效: {self.path}")
        if self.header_size <= _HEADER_SIZE or self.header_size >= len(self._data):
            raise RuntimeError(f"DBC 表头长度无效: {self.path}")
        if self.field_count <= 0:
            raise RuntimeError(f"DBC 表字段数量无效: {self.path}")
        total_length = sum(column.length for column in self.columns)
        if total_length != self.record_size:
            raise RuntimeError(f"DBC 表字段长度与记录长度不一致: {self.path}\n字段合计 {total_length}, 记录长度 {self.record_size}")

    def _parse_columns(self) -> list[DbcColumn]:
        if len(self._data) < _HEADER_SIZE + self.field_count * 2:
            raise RuntimeError(f"DBC 表头不完整: {self.path}")
        field_specs = []
        offset = _HEADER_SIZE
        for index in range(self.field_count):
            type_code = self._data[offset + index * 2]
            length = self._data[offset + index * 2 + 1]
            field_specs.append((type_code, length))
        names = self._parse_field_names()
        columns = []
        record_offset = 0
        for index, (type_code, length) in enumerate(field_specs):
            name = names[index] if index < len(names) and names[index] else f"Field{index + 1}"
            columns.append(DbcColumn(name=name, type_code=type_code, length=length, offset=record_offset))
            record_offset += length
        return columns

    def _parse_field_names(self) -> list[str]:
        names_start = _HEADER_SIZE + self.field_count * 2 + self.field_count * 4
        header = self._data[:self.header_size]
        pos = names_start
        table_name_end = header.lower().find(b".db\0", pos)
        if table_name_end >= 0:
            pos = table_name_end + 4
        while pos < len(header) and header[pos] == 0:
            pos += 1
        names = []
        for _ in range(self.field_count):
            end = header.find(b"\0", pos)
            if end < 0:
                break
            raw = header[pos:end]
            if not raw:
                break
            names.append(self._decode_text(raw))
            pos = end + 1
        return names

    def rows(self) -> list[tuple[Any, ...]]:
        if self._rows is None:
            self._rows = list(self._iter_rows())[:self.record_count]
        return self._rows

    def count(self, keyword: str = "", columns: Iterable[str] = ()) -> int:
        if not keyword:
            return len(self.rows())
        return sum(1 for row in self.rows() if self._matches(row, keyword, columns))

    def fetch(self, *, keyword: str = "", columns: Iterable[str] = (), offset: int = 0, limit: int | None = None) -> list[tuple[Any, ...]]:
        matched = []
        start = max(0, offset)
        end = None if limit is None else start + max(0, limit)
        matched_index = 0
        for row in self.rows():
            if keyword and not self._matches(row, keyword, columns):
                continue
            if matched_index >= start and (end is None or matched_index < end):
                matched.append(row)
            elif end is not None and matched_index >= end:
                break
            matched_index += 1
        if limit is None:
            return matched
        return matched

    def _matches(self, row: tuple[Any, ...], keyword: str, columns: Iterable[str]) -> bool:
        needle = keyword.casefold()
        column_set = {name for name in columns}
        for index, value in enumerate(row):
            if column_set and self.columns[index].name not in column_set:
                continue
            if needle in ("" if value is None else str(value)).casefold():
                return True
        return False

    def _iter_rows(self) -> Iterable[tuple[Any, ...]]:
        if self.record_count == 0 or self.file_blocks == 0:
            return
        block_size = self._block_size()
        block_number = self.first_block or 1
        seen = set()
        yielded = 0
        while block_number and block_number not in seen and 1 <= block_number <= self.file_blocks:
            seen.add(block_number)
            for row in self._iter_block_rows(block_number, block_size):
                yield row
                yielded += 1
                if yielded >= self.record_count:
                    return
            block_number = self._next_block(block_number, block_size)
        for block_number in range(1, self.file_blocks + 1):
            if block_number in seen:
                continue
            for row in self._iter_block_rows(block_number, block_size):
                yield row
                yielded += 1
                if yielded >= self.record_count:
                    return

    def _block_size(self) -> int:
        data_size = len(self._data) - self.header_size
        if self.file_blocks > 0 and data_size > 0 and data_size % self.file_blocks == 0:
            return data_size // self.file_blocks
        return 2048

    def _block_offset(self, block_number: int, block_size: int) -> int:
        return self.header_size + (block_number - 1) * block_size

    def _next_block(self, block_number: int, block_size: int) -> int:
        offset = self._block_offset(block_number, block_size)
        if offset + 2 > len(self._data):
            return 0
        return struct.unpack_from("<H", self._data, offset)[0]

    def _iter_block_rows(self, block_number: int, block_size: int) -> Iterable[tuple[Any, ...]]:
        offset = self._block_offset(block_number, block_size)
        if offset + 6 > len(self._data):
            return
        last_record_offset = struct.unpack_from("<H", self._data, offset + 4)[0]
        count = last_record_offset // self.record_size + 1
        max_count = max(0, (block_size - 6) // self.record_size)
        count = min(count, max_count)
        record_offset = offset + 6
        for _ in range(count):
            end = record_offset + self.record_size
            if end > len(self._data):
                return
            raw_record = self._data[record_offset:end]
            yield self._decode_record(raw_record)
            record_offset = end

    def _iter_record_offsets(self) -> Iterable[int]:
        if self.record_count == 0 or self.file_blocks == 0:
            return
        block_size = self._block_size()
        block_number = self.first_block or 1
        seen = set()
        yielded = 0
        while block_number and block_number not in seen and 1 <= block_number <= self.file_blocks:
            seen.add(block_number)
            for record_offset in self._iter_block_record_offsets(block_number, block_size):
                yield record_offset
                yielded += 1
                if yielded >= self.record_count:
                    return
            block_number = self._next_block(block_number, block_size)
        for block_number in range(1, self.file_blocks + 1):
            if block_number in seen:
                continue
            for record_offset in self._iter_block_record_offsets(block_number, block_size):
                yield record_offset
                yielded += 1
                if yielded >= self.record_count:
                    return

    def _iter_block_record_offsets(self, block_number: int, block_size: int) -> Iterable[int]:
        offset = self._block_offset(block_number, block_size)
        if offset + 6 > len(self._data):
            return
        last_record_offset = struct.unpack_from("<H", self._data, offset + 4)[0]
        count = last_record_offset // self.record_size + 1
        max_count = max(0, (block_size - 6) // self.record_size)
        count = min(count, max_count)
        record_offset = offset + 6
        for _ in range(count):
            end = record_offset + self.record_size
            if end > len(self._data):
                return
            yield record_offset
            record_offset = end

    def update_column(self, column: str, value: Any, *, condition_column: str = "", condition_operator: str = "", condition_value: Any = None, only_rows: list[tuple[Any, ...]] | None = None) -> int:
        column_index = self._column_index(column)
        target_column = self.columns[column_index]
        condition_index = self._column_index(condition_column) if condition_column else -1
        allowed_rows = {tuple(row) for row in only_rows} if only_rows is not None else None
        data = bytearray(self._data)
        updated = 0
        for record_offset in self._iter_record_offsets():
            raw_record = bytes(data[record_offset:record_offset + self.record_size])
            row = self._decode_record(raw_record)
            if allowed_rows is not None and row not in allowed_rows:
                continue
            if condition_index >= 0 and not self._condition_matches(row[condition_index], condition_operator, condition_value):
                continue
            next_value = value(row[column_index]) if callable(value) else value
            raw_value = self._encode_value(next_value, target_column)
            start = record_offset + target_column.offset
            data[start:start + target_column.length] = raw_value
            updated += 1
        if updated:
            with open(self.path, "wb") as handle:
                handle.write(data)
            self._data = bytes(data)
            self._rows = None
        return updated

    def update_cell(self, original_row: Iterable[Any], column: str, value: Any) -> int:
        column_index = self._column_index(column)
        target_column = self.columns[column_index]
        wanted = self._row_match_key(original_row)
        data = bytearray(self._data)
        for record_offset in self._iter_record_offsets():
            raw_record = bytes(data[record_offset:record_offset + self.record_size])
            row = self._decode_record(raw_record)
            if self._row_match_key(row) != wanted:
                continue
            raw_value = self._encode_value(value, target_column)
            start = record_offset + target_column.offset
            data[start:start + target_column.length] = raw_value
            with open(self.path, "wb") as handle:
                handle.write(data)
            self._data = bytes(data)
            self._rows = None
            return 1
        return 0

    def delete_rows(self, rows: Iterable[Iterable[Any]]) -> int:
        targets: dict[tuple[str, ...], int] = {}
        for row in rows:
            key = self._row_match_key(row)
            targets[key] = targets.get(key, 0) + 1
        if not targets:
            return 0
        kept = []
        deleted = 0
        for row in self.rows():
            key = self._row_match_key(row)
            if targets.get(key, 0) > 0:
                targets[key] -= 1
                deleted += 1
            else:
                kept.append(row)
        if deleted:
            self._rewrite_rows(kept)
        return deleted

    def append_rows(self, rows: Iterable[Iterable[Any]]) -> int:
        normalized_rows = [list(row) for row in rows]
        if not normalized_rows:
            return 0
        for index, row in enumerate(normalized_rows, start=1):
            if len(row) != len(self.columns):
                raise RuntimeError(f"第 {index} 行字段数量不一致，应为 {len(self.columns)} 个，实际 {len(row)} 个")

        block_size = self._block_size()
        max_records_per_block = max(1, (block_size - 6) // self.record_size)
        data = bytearray(self._data)
        inserted = 0

        for row in normalized_rows:
            block_number, count = self._append_target_block(data, block_size, max_records_per_block)
            if count >= max_records_per_block:
                block_number = self._append_new_block(data, block_size)
                count = 0

            block_offset = self._block_offset(block_number, block_size)
            record_offset = block_offset + 6 + count * self.record_size
            data[record_offset:record_offset + self.record_size] = self._encode_record(row)
            struct.pack_into("<H", data, block_offset + 4, count * self.record_size)

            inserted += 1
            self.record_count += 1

        struct.pack_into("<I", data, 6, self.record_count)
        with open(self.path, "wb") as handle:
            handle.write(data)
        self._data = bytes(data)
        self._rows = None
        self.file_blocks = self._u16(12)
        return inserted

    def _rewrite_rows(self, rows: list[tuple[Any, ...]]) -> None:
        if self.file_blocks <= 0:
            raise RuntimeError(f"DBC 表块数量无效，无法删除记录: {self.path}")
        block_size = self._block_size()
        max_records_per_block = max(1, (block_size - 6) // self.record_size)
        if len(rows) > self.file_blocks * max_records_per_block:
            raise RuntimeError("DBC 表剩余记录超过当前文件容量，无法重写。")

        data = bytearray(self._data)
        expected_size = self.header_size + self.file_blocks * block_size
        if len(data) < expected_size:
            data.extend(b"\0" * (expected_size - len(data)))

        order = self._block_order(block_size)
        used_blocks = max(1, math.ceil(len(rows) / max_records_per_block)) if rows else 1
        row_index = 0

        for order_index, block_number in enumerate(order):
            offset = self._block_offset(block_number, block_size)
            data[offset:offset + block_size] = b"\0" * block_size
            if order_index >= used_blocks:
                continue

            next_block = order[order_index + 1] if order_index + 1 < used_blocks else 0
            previous_block = order[order_index - 1] if order_index > 0 else 0
            remaining = len(rows) - row_index
            count = min(max_records_per_block, max(0, remaining))

            struct.pack_into("<H", data, offset, next_block)
            struct.pack_into("<H", data, offset + 2, previous_block)
            struct.pack_into("<H", data, offset + 4, (count - 1) * self.record_size if count else 0)

            record_offset = offset + 6
            for row in rows[row_index:row_index + count]:
                data[record_offset:record_offset + self.record_size] = self._encode_record(row)
                record_offset += self.record_size
            row_index += count

        self.record_count = len(rows)
        self.first_block = order[0]
        struct.pack_into("<I", data, 6, self.record_count)
        struct.pack_into("<H", data, 14, self.first_block)
        with open(self.path, "wb") as handle:
            handle.write(data)
        self._data = bytes(data)
        self._rows = None

    def _block_order(self, block_size: int) -> list[int]:
        order = []
        block_number = self.first_block or 1
        visited = set()
        while block_number and block_number not in visited and 1 <= block_number <= self.file_blocks:
            visited.add(block_number)
            order.append(block_number)
            block_number = self._next_block(block_number, block_size)
        for block_number in range(1, self.file_blocks + 1):
            if block_number not in visited:
                order.append(block_number)
        return order or list(range(1, self.file_blocks + 1))

    @staticmethod
    def _row_match_key(row: Iterable[Any]) -> tuple[str, ...]:
        return tuple("" if value is None else str(value) for value in row)

    def _append_target_block(self, data: bytearray, block_size: int, max_records_per_block: int) -> tuple[int, int]:
        if self.file_blocks <= 0:
            raise RuntimeError(f"DBC 表块数量无效，无法追加记录: {self.path}")
        block_number = self.first_block or 1
        visited = set()
        last_valid = block_number
        while block_number and block_number not in visited and 1 <= block_number <= self.file_blocks:
            visited.add(block_number)
            last_valid = block_number
            next_block = self._next_block_from_data(data, block_number, block_size)
            if not next_block:
                break
            block_number = next_block
        count = self._block_record_count_from_data(data, last_valid, block_size, max_records_per_block)
        return last_valid, count

    def _append_new_block(self, data: bytearray, block_size: int) -> int:
        previous_block = self._append_target_block(data, block_size, max(1, (block_size - 6) // self.record_size))[0]
        new_block_number = self.file_blocks + 1
        previous_offset = self._block_offset(previous_block, block_size)
        struct.pack_into("<H", data, previous_offset, new_block_number)
        block = bytearray(block_size)
        struct.pack_into("<H", block, 0, 0)
        struct.pack_into("<H", block, 2, previous_block)
        struct.pack_into("<H", block, 4, 0)
        data.extend(block)
        self.file_blocks = new_block_number
        struct.pack_into("<H", data, 12, self.file_blocks)
        return new_block_number

    def _next_block_from_data(self, data: bytearray, block_number: int, block_size: int) -> int:
        offset = self._block_offset(block_number, block_size)
        if offset + 2 > len(data):
            return 0
        return struct.unpack_from("<H", data, offset)[0]

    def _block_record_count_from_data(self, data: bytearray, block_number: int, block_size: int, max_records_per_block: int) -> int:
        offset = self._block_offset(block_number, block_size)
        if offset + 6 > len(data):
            return 0
        last_record_offset = struct.unpack_from("<H", data, offset + 4)[0]
        if self.record_count <= 0 and last_record_offset == 0:
            return 0
        return min(last_record_offset // self.record_size + 1, max_records_per_block)

    def _column_index(self, column: str) -> int:
        wanted = column.casefold()
        for index, item in enumerate(self.columns):
            if item.name.casefold() == wanted:
                return index
        raise RuntimeError(f"DBC 字段不存在: {column}")

    def _condition_matches(self, value: Any, operator: str, expected: Any) -> bool:
        op = operator or "eq"
        left_num = self._to_number(value)
        right_num = self._to_number(expected)
        if op in {"gt", "lt", "gte", "lte"} and left_num is not None and right_num is not None:
            if op == "gt": return left_num > right_num
            if op == "lt": return left_num < right_num
            if op == "gte": return left_num >= right_num
            return left_num <= right_num
        left = "" if value is None else str(value)
        right = "" if expected is None else str(expected)
        if op == "gt": return left > right
        if op == "lt": return left < right
        if op == "gte": return left >= right
        if op == "lte": return left <= right
        return left == right

    @staticmethod
    def _to_number(value: Any) -> float | None:
        try:
            text = "" if value is None else str(value).strip()
            if not text:
                return None
            return float(text)
        except ValueError:
            return None

    def _decode_record(self, raw_record: bytes) -> tuple[Any, ...]:
        row = []
        for column in self.columns:
            raw = raw_record[column.offset:column.offset + column.length]
            row.append(self._decode_value(raw, column))
        return tuple(row)

    def _encode_record(self, row: Iterable[Any]) -> bytes:
        encoded = bytearray(self.record_size)
        for column, value in zip(self.columns, row):
            raw = self._encode_value(value, column)
            encoded[column.offset:column.offset + column.length] = raw
        return bytes(encoded)

    def _encode_value(self, value: Any, column: DbcColumn) -> bytes:
        if column.type_code == 1:
            return self._encode_text(value, column.length)
        if column.type_code in {2, 3, 4, 5, 13}:
            return self._encode_int(value, column.length)
        if column.type_code == 6:
            return self._encode_number(value, column.length)
        if column.type_code == 7:
            return bytes([1 if self._boolish(value) else 0]).ljust(column.length, b"\0")
        if column.type_code in frozenset({8, 9, 12, 14, 15, 20}):
            return self._encode_raw_bytes(value, column.length)
        raise RuntimeError(f"暂不支持写入 DBC 字段类型: {column.name} ({column.type_name})")

    def _decode_value(self, raw: bytes, column: DbcColumn) -> Any:
        if column.type_code == 1:
            return self._decode_text(raw)
        if column.type_code in frozenset({2, 3, 4, 5, 13}):
            return self._decode_int(raw)
        if column.type_code == 6:
            return self._decode_number(raw)
        if column.type_code == 7:
            if not raw:
                return None
            return bool(raw[0])
        if not raw or all(byte == 0 for byte in raw):
            return None
        return raw.hex(" ").upper()

    def _decode_text(self, raw: bytes) -> str:
        text = raw.split(b"\0", 1)[0].rstrip(b" \0")
        if not text:
            return ""
        encodings = ["gbk", "cp936", self.encoding, "big5", "cp949", "utf-8", "latin1"]
        seen = set()
        for encoding in encodings:
            if encoding in seen:
                continue
            seen.add(encoding)
            try:
                return text.decode(encoding)
            except UnicodeDecodeError:
                continue
        return text.decode("latin1", errors="replace")

    def _encode_text(self, value: Any, length: int) -> bytes:
        text = "" if value is None else str(value)
        encodings = [self.encoding, "gbk", "cp936", "big5", "utf-8"]
        last = text.encode("gbk", errors="replace")
        for encoding in encodings:
            try:
                encoded = text.encode(encoding)
                break
            except UnicodeEncodeError:
                continue
        else:
            encoded = last
        if len(encoded) > length:
            encoded = encoded[:length]
        return encoded.ljust(length, b"\0")

    @staticmethod
    def _encode_raw_bytes(value: Any, length: int) -> bytes:
        if value is None or str(value).strip() == "":
            return b"\0" * length
        if isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
        else:
            text = str(value).strip()
            if text.lower().startswith("0x"):
                text = text[2:]
            compact = "".join(ch for ch in text if ch not in " \t\r\n,;:-_")
            if len(compact) % 2:
                raise ValueError("DBC 原始字节字段需要偶数位十六进制文本。")
            try:
                raw = bytes.fromhex(compact)
            except ValueError as exc:
                raise ValueError("DBC 原始字节字段只能写入十六进制文本，例如：01 02 FF。") from exc
        if len(raw) > length:
            raw = raw[:length]
        return raw.ljust(length, b"\0")

    @staticmethod
    def _decode_int(raw: bytes) -> int | None:
        if not raw or all(byte == 0 for byte in raw):
            return None
        data = bytearray(raw)
        data[0] ^= 128
        return int.from_bytes(data, "big", signed=True)

    @staticmethod
    def _encode_int(value: Any, length: int) -> bytes:
        if value is None or str(value).strip() == "":
            return b"\0" * length
        number = int(float(str(value).strip()))
        data = bytearray(number.to_bytes(length, "big", signed=True))
        data[0] ^= 128
        return bytes(data)

    @staticmethod
    def _decode_number(raw: bytes) -> float | int | None:
        if not raw or all(byte == 0 for byte in raw):
            return None
        data = bytearray(raw)
        if data[0] & 128:
            data[0] ^= 128
        else:
            data = bytearray(byte ^ 255 for byte in data)
        if len(data) == 8:
            value = struct.unpack(">d", bytes(data))[0]
            if math.isfinite(value) and value.is_integer():
                return int(value)
            return value
        return int.from_bytes(data, "big", signed=True)

    @staticmethod
    def _encode_number(value: Any, length: int) -> bytes:
        if value is None or str(value).strip() == "":
            return b"\0" * length
        if length == 8:
            number = float(str(value).strip())
            data = bytearray(struct.pack(">d", number))
        else:
            number = int(float(str(value).strip()))
            data = bytearray(number.to_bytes(length, "big", signed=True))
            if all(byte == 255 for byte in data):
                raise ValueError("DBC 短 Number 字段无法无损写入 -1：其编码与空值冲突。")
        if data[0] & 128:
            data = bytearray(byte ^ 255 for byte in data)
        else:
            data[0] ^= 128
        return bytes(data)

    @staticmethod
    def _boolish(value: Any) -> bool:
        text = "" if value is None else str(value).strip().lower()
        return text in {"1", "true", "yes", "y", "是", "开"}
