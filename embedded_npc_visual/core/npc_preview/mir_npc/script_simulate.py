from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

try:
    from embedded_npc_visual.core.dbc_reader import DbcTable
except Exception:
    DbcTable = None

from embedded_npc_visual.core.npc_preview.mir_npc.script_model import ActKind, NpcScript, ScriptSection
from embedded_npc_visual.core.npc_preview.mir_npc.call_path import normalize_call_path
from embedded_npc_visual.core.npc_preview.mir_npc.script_workspace import (
    MAIN_KEY,
    MethodRef,
    ScriptWorkspace,
    _normalize_label,
)
from embedded_npc_visual.core.npc_preview.npc_dialog_core import (
    NpcDialog,
    SourceMapEntry,
    SourceRef,
    _parse_npc_dialog_parts,
    replace_str_variables,
)

_GET_LIST_STRING_RE = re.compile(r"^\s*GetListString\s+(?P<path>\S+)\s+(?P<index>\S+)\s+(?P<string_var>\S+)(?:\s+(?P<number_var>\S+))?", re.IGNORECASE)
_READ_CONFIG_FILE_ITEM_RE = re.compile(r"^\s*ReadConfigFileItem\s+(?P<path>\S+)\s+(?P<section>\S+)\s+(?P<item>\S+)\s+(?P<target>\S+)", re.IGNORECASE)
_SET_STRING_BLANK_RE = re.compile(r"^\s*SetStringBlank\s+(?P<target>\S+)\s+(?P<width>-?\d+)(?:\s+(?P<mode>\S+))?", re.IGNORECASE)
_TEXTSPLIT_RE = re.compile(r"^\s*Textsplit\s+(?P<delimiter>\S+)\s+(?P<source>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_TEXTREPLACE_RE = re.compile(r"^\s*TextReplace\s+(?P<source>\S+)\s+(?P<old>\S+)\s+(?P<new>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_TEXTLENGTH_RE = re.compile(r"^\s*Textlength\s+(?P<source>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_GET_DB_ITEM_FIELD_RE = re.compile(r"^\s*GetDBitemFieldValue\s+(?P<name>\S+)\s+(?P<field>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_GET_DB_MONSTER_FIELD_RE = re.compile(r"^\s*GetDBMonsterFieldValue\s+(?P<name>\S+)\s+(?P<field>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_EXTRACT_STRING_RE = re.compile(r"^\s*ExtractString\s+(?P<delimiter>\S+)\s+(?P<source>\S+)\s+(?P<targets>.+?)\s*$", re.IGNORECASE)
_GET_STRING_POS_EX_RE = re.compile(r"^\s*GetstringPoseX\s+(?P<path>\S+)\s+(?P<needle>\S+)\s+(?P<number_var>\S+)\s+(?P<string_var>\S+)(?:\s+\S+)?\s*$", re.IGNORECASE)
_ARITH_RE = re.compile(r"^\s*(?P<op>MUL|DIV|INC|DEC)\s+(?P<name>\S+)(?:\s+(?P<value>.*?))?\s*$", re.IGNORECASE)
_MOVR_RE = re.compile(r"^\s*MOVR\s+(?P<name>\S+)\s+(?P<min>\S+)(?:\s+(?P<max>.*?))?\s*$", re.IGNORECASE)
_STR_TOKEN_RE = re.compile(r"^<\s*\$STR\((?P<name>[^)]+)\)\s*>$", re.IGNORECASE)


@dataclass
class SimulateOptions:
    """从指定 [@入口] 模拟 ACT 链，生成可渲染快照（内存）。"""

    entry_label: str = "@shoubao1"
    entry_path: str | None = None
    skip_goto_labels: frozenset[str] = frozenset()
    mock_variables: dict[str, str] = field(default_factory=dict)
    max_goto_hops: int = 48
    follow_call: bool = True
    call_loader: Callable[[str], str | None] | None = None
    on_call_loaded: Callable[[str], None] | None = None
    say_page_index: int = 1
    merge_adjacent_text: bool = True
    monster_field_loader: Callable[[str, str, str | None], str | None] | None = None

    def __post_init__(self) -> None:
        if not self.entry_label.startswith("@"):
            self.entry_label = f"@{self.entry_label}"
        if not self.mock_variables:
            self.mock_variables = {
                f"S$显示{i}": f"<text:预览物品{i}:187:0{{FCOLOR=249}}><text:999元宝:165:0{{FCOLOR=249}}>"
                for i in range(10)
            }


@dataclass
class PreviewBundle:
    """
    预览快照：变量状态 + 用于绘制的临时片段。

    say_lines / act_lines 是解释器输出的渲染输入，不是合并后的脚本文件。
    """

    entry_label: str
    entry_path: str | None
    final_label: str
    final_path: str | None
    variables: dict[str, str]
    act_lines: list[str]
    say_lines: list[str]
    act_source_refs: list[SourceRef | None] = field(default_factory=list)
    say_source_refs: list[SourceRef | None] = field(default_factory=list)
    merge_adjacent_text: bool = True
    trace: list[str] = field(default_factory=list)

    @property
    def say_source(self) -> str:
        return "".join(self.say_lines)

    def render_snapshot(self) -> str:
        """仅供 npc_dialog_core 解析绘制的 ephemeral 文本，不写回编辑器。"""
        parts = []
        if self.act_lines:
            parts.append("#ACT\n")
            parts.extend((line if line.endswith("\n") else line + "\n" for line in self.act_lines))
        parts.append("#SAY\n")
        parts.extend(self.say_lines)
        return "".join(parts)

    def say_source_map(self) -> list[SourceMapEntry]:
        entries = []
        offset = 0
        for line, ref in zip(self.say_lines, self.say_source_refs):
            line_end = offset + len(line)
            if ref is not None:
                entries.append(SourceMapEntry(offset, line_end, ref))
            offset = line_end
        return entries

    def to_dialog(self, *, global_mov: dict[str, str] | None = None) -> NpcDialog:
        return _parse_npc_dialog_parts(
            self.render_snapshot(),
            self.entry_label,
            local_mov_values=dict(self.variables),
            global_mov_values=global_mov or {},
            merge_adjacent_text=self.merge_adjacent_text,
            source_map=self.say_source_map(),
        )


def simulate_preview(script_or_workspace: NpcScript | ScriptWorkspace, options: SimulateOptions | None = None) -> PreviewBundle:
    """
    轻量模拟：沿 AST 执行 mov / OPENMERCHANT / GOTO / #CALL。
    各文件 source 保持独立，仅在内存中跳转与累积变量。
    """
    options = options or SimulateOptions()
    if isinstance(script_or_workspace, ScriptWorkspace):
        workspace = script_or_workspace
        context_path = options.entry_path or workspace.main_key
        ref = workspace.resolve_label(options.entry_label, context_path=context_path)
        if ref is None:
            raise KeyError(f"入口标签不存在: {options.entry_label}")
    else:
        workspace = None
        script = script_or_workspace
        block = script.method_index.get(options.entry_label)
        if block is None:
            raise KeyError(f"入口标签不存在: {options.entry_label}")
        ref = MethodRef(script.source_path or MAIN_KEY, options.entry_label, block)

    scripts_by_key = workspace.scripts if workspace is not None else {ref.source_path: script}
    variables = dict(options.mock_variables)
    act_lines: list[str] = []
    say_lines: list[str] = []
    act_source_refs: list[SourceRef | None] = []
    say_source_refs: list[SourceRef | None] = []
    trace: list[str] = []
    hops = 0
    current = ref
    final_ref = ref
    call_stack: list[tuple[str, str]] = []
    say_page_seen = 0
    break_signal = object()
    stop_signal = object()
    stditems_cache: dict[str, dict[str, object]] | None = None
    line_offsets_cache: dict[str, list[tuple[int, int, int]]] = {}

    def source_line_offsets(source_path: str) -> list[tuple[int, int, int]]:
        cached = line_offsets_cache.get(source_path)
        if cached is not None:
            return cached
        script_obj = scripts_by_key.get(source_path)
        source_text = script_obj.source if script_obj is not None else ""
        offsets = []
        start = 0
        for line in source_text.splitlines(keepends=True):
            end = start + len(line)
            content_end = end
            if line.endswith("\r\n"):
                content_end -= 2
            elif line.endswith("\n") or line.endswith("\r"):
                content_end -= 1
            offsets.append((start, content_end, end))
            start = end
        line_offsets_cache[source_path] = offsets
        return offsets

    def source_ref_for_line(method: MethodRef, line_no: int, fallback_raw: str) -> SourceRef | None:
        offsets = source_line_offsets(method.source_path)
        if line_no < 0 or line_no >= len(offsets):
            return None
        start, _content_end, end = offsets[line_no]
        script_obj = scripts_by_key.get(method.source_path)
        raw = script_obj.source[start:end] if script_obj is not None else fallback_raw
        return SourceRef(method.source_path, start, end, line_no + 1, 0, raw, True)

    def apply_mov(name: str, value: str) -> None:
        variables[name] = value
        trace.append(f"mov {name} = {value[:60]}{'...' if len(value) > 60 else ''}")

    def variable_value(name: str) -> str | None:
        if name in variables:
            return variables[name]
        folded = name.casefold()
        for key, value in variables.items():
            if key.casefold() == folded:
                return value
        return None

    def resolve_text(value: str) -> str:
        resolved = replace_str_variables(value, variables, {})
        return re.sub("<\\s*\\$USERNAME\\s*>", "畅玩可视化", resolved, flags=re.IGNORECASE)

    def resolve_number(value: str | None) -> int:
        if value is None:
            return 0
        resolved = resolve_text(value).strip()
        if variable_value(resolved) is not None:
            resolved = resolve_text(f"<$STR({resolved})>").strip()
        try:
            return int(float(resolved.replace(",", "")))
        except ValueError:
            return 0

    def token_value(token: str | None) -> str:
        if token is None:
            return ""
        text = token.strip()
        if variable_value(text) is not None:
            return resolve_text(f"<$STR({text})>")
        return resolve_text(text)

    def looks_like_variable_name(token: str) -> bool:
        text = token.strip()
        if not text:
            return False
        if _STR_TOKEN_RE.match(text):
            return True
        return bool(re.match(r"^[A-Za-z](?:\$[\w\u4e00-\u9fff]+|\d+)$", text))

    def condition_token_value(token: str | None, *, numeric: bool = False) -> str:
        if token is None:
            return ""
        text = token.strip()
        if variable_value(text) is not None:
            return resolve_text(f"<$STR({text})>")
        resolved = resolve_text(text)
        if resolved == text and looks_like_variable_name(text):
            if numeric and not text.casefold().startswith("s$"):
                return "0"
            return ""
        return resolved

    def condition_token_is_unknown(token: str | None, *, numeric: bool = False) -> bool:
        if token is None:
            return False
        text = token.strip()
        if not text or variable_value(text) is not None:
            return False
        if resolve_text(text) != text:
            return False
        if numeric:
            return False
        return looks_like_variable_name(text)

    def condition_number(value: str) -> int:
        return resolve_number(condition_token_value(value, numeric=True))

    def display_width(text: str) -> int:
        width = 0
        for char in text:
            width += 2 if unicodedata.east_asian_width(char) in {"F", "W"} else 1
        return width

    def pad_to_display_width(text: str, width: int, mode: str | None) -> str:
        missing = max(0, width - display_width(text))
        if (mode or "").strip() == "0":
            return " " * missing + text
        return text + " " * missing

    def variable_name_from_token(token: str | None) -> str | None:
        if token is None:
            return None
        match = _STR_TOKEN_RE.match(token.strip())
        if match:
            return match.group("name").strip()
        return token.strip() or None

    def sequential_variable_name(base_name: str, offset: int) -> str:
        match = re.match(r"^(?P<prefix>.*?)(?P<number>\d+)$", base_name)
        if not match:
            if offset == 0:
                return base_name
            return f"{base_name}{offset + 1}"
        number = match.group("number")
        return f'{match.group("prefix")}{int(number) + offset:0{len(number)}d}'

    def load_quest_text(file_path: str) -> str | None:
        if options.call_loader is None:
            return None
        normalized = normalize_call_path(resolve_text(file_path))
        candidates = [normalized]
        lowered = normalized.casefold()
        for prefix in ("../questdiary/", "..//questdiary/", "questdiary/", "/questdiary/"):
            if lowered.startswith(prefix):
                candidates.append(normalized[len(prefix):])
        marker = "/questdiary/"
        if marker in lowered:
            pos = lowered.rfind(marker)
            candidates.append(normalized[pos + len(marker):])
        seen = set()
        for candidate in candidates:
            candidate = normalize_call_path(candidate)
            folded = candidate.casefold()
            if not candidate or folded in seen:
                continue
            seen.add(folded)
            text = options.call_loader(candidate)
            if text is not None:
                return text
        return None

    def split_list_line(line: str) -> tuple[str, str]:
        for marker in (":", "|", ",", "\t"):
            if marker in line:
                left, right = line.split(marker, 1)
                return (left.strip(), right.strip())
        return (line.strip(), "")

    def check_text_list(path: str, needle: str) -> bool:
        text = load_quest_text(path) or ""
        wanted = needle.strip()
        if not text or not wanted:
            return False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            if line == wanted or wanted in line:
                return True
        return False

    def get_string_pos_ex(path: str, needle: str, number_var: str, string_var: str) -> bool:
        text = load_quest_text(path) or ""
        wanted = needle.strip()
        if not text or not wanted:
            return False
        for index, raw_line in enumerate(text.splitlines()):
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            key = line.split(":", 1)[0].strip()
            if key == wanted:
                apply_mov(number_var, str(index))
                apply_mov(string_var, line)
                trace.append(f"GetstringPoseX {path} {wanted!r} -> {string_var}")
                return True
        return False

    def config_item_value(text: str, section: str, item: str) -> str:
        current_section = ""
        wanted_section = section.strip().casefold()
        wanted_item = item.strip().casefold()
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line:
                if line.startswith(";") or line.startswith("#"):
                    continue
                if line.startswith("[") and "]" in line:
                    current_section = line[1:line.find("]")].strip().casefold()
                    continue
                if current_section != wanted_section or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip().casefold() == wanted_item:
                    return value.strip()
        return ""

    def find_stditems_db() -> Path | None:
        if not options.entry_path:
            return None
        try:
            entry = Path(options.entry_path)
        except (TypeError, ValueError):
            return None
        roots = [entry.parent, *entry.parents]
        candidates = []
        for root in roots[:8]:
            candidates.append(root / "StdItems.DB")
            candidates.append(root / "ApexM2.DB")
            candidates.append(root / "Envir" / "StdItems.DB")
            candidates.append(root / "Mir200" / "Envir" / "StdItems.DB")
            candidates.append(root / "Mir200" / "StdItems.DB")
            candidates.append(root / "Mud2" / "DB" / "StdItems.DB")
            candidates.append(root / "Mud2" / "DB" / "ApexM2.DB")
        seen = set()
        for candidate in candidates:
            key = str(candidate).casefold()
            if key in seen:
                continue
            seen.add(key)
            if candidate.is_file():
                if candidate.name.casefold() == "stditems.db" or sqlite_has_stditems(candidate):
                    return candidate
            parent = candidate.parent
            if parent.is_dir():
                target = candidate.name.casefold()
                for child in parent.iterdir():
                    if child.is_file() and child.name.casefold() == target and (
                        child.name.casefold() == "stditems.db" or sqlite_has_stditems(child)
                    ):
                        return child
        for directory in [root / "Mud2" / "DB" for root in roots[:6]]:
            if not directory.is_dir():
                continue
            for child in sorted(directory.iterdir(), key=lambda item: item.name.casefold()):
                if child.is_file() and child.suffix.casefold() in {".db", ".sqlite", ".sqlite3"} and sqlite_has_stditems(child):
                    return child
        return None

    def is_sqlite(path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                return handle.read(16) == b"SQLite format 3\x00"
        except OSError:
            return False

    def sqlite_has_stditems(path: Path) -> bool:
        if not is_sqlite(path):
            return False
        try:
            conn = sqlite3.connect(str(path))
            try:
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1",
                    ("StdItems",),
                ).fetchone()
                return row is not None
            finally:
                conn.close()
        except sqlite3.Error:
            return False

    def load_stditems() -> dict[str, dict[str, object]]:
        nonlocal stditems_cache
        if stditems_cache is not None:
            return stditems_cache
        stditems_cache = {}
        db_path = find_stditems_db()
        if db_path is None:
            return stditems_cache
        try:
            if sqlite_has_stditems(db_path):
                conn = sqlite3.connect(str(db_path))
                try:
                    table_row = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1",
                        ("StdItems",),
                    ).fetchone()
                    if table_row is None:
                        return stditems_cache
                    table_name = str(table_row[0])
                    columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')]
                    name_index = next((i for i, name in enumerate(columns) if str(name).casefold() in {"name", "stdname"}), None)
                    if name_index is None:
                        return stditems_cache
                    rows = conn.execute(f'SELECT * FROM "{table_name}"')
                    for row in rows:
                        name = str(row[name_index]).strip()
                        if not name:
                            continue
                        stditems_cache[name.casefold()] = {
                            str(columns[index]).casefold(): row[index]
                            for index in range(min(len(columns), len(row)))
                        }
                    return stditems_cache
                finally:
                    conn.close()
            if DbcTable is None:
                return stditems_cache
            table = DbcTable(str(db_path))
            column_indexes = {column.name.casefold(): index for index, column in enumerate(table.columns)}
            name_index = column_indexes.get("name")
            if name_index is None:
                name_index = column_indexes.get("stdname")
            if name_index is None:
                return stditems_cache
            for row in table.rows():
                raw_name = row[name_index]
                name = str(raw_name).strip()
                if not name:
                    continue
                stditems_cache[name.casefold()] = {
                    column.name.casefold(): row[index]
                    for index, column in enumerate(table.columns)
                    if index < len(row)
                }
        except Exception as exc:
            trace.append(f"StdItems.DB load failed: {exc}")
        return stditems_cache

    def item_field_value(item_name: str, field_name: str, target_name: str | None) -> str:
        row = load_stditems().get(item_name.strip().casefold())
        field = field_name.strip().casefold()
        if row is not None and field in row:
            value = row[field]
            if value is None:
                return ""
            return str(value).strip()
        if field == "stdmode" and target_name:
            suffix_match = re.search(r"(\d{2})", target_name)
            category = ""
            if suffix_match:
                category = variable_value(f"s$物品类别{suffix_match.group(1)}") or ""
            category_map = {
                "武器": "5", "衣服": "10", "头盔": "15", "项链": "19", "手镯": "24",
                "戒指": "22", "腰带": "54", "靴子": "52", "药品": "0", "材料": "41", "其他": "41",
            }
            return category_map.get(category.strip(), "0")
        if field not in {"name"}:
            return "0"
        return ""

    def monster_field_value(monster_name: str, field_name: str, target_name: str | None) -> str:
        if options.monster_field_loader is not None:
            try:
                value = options.monster_field_loader(monster_name, field_name, target_name)
            except Exception:
                value = None
            if value is not None:
                return str(value).strip()
        if field_name.strip().casefold() != "name":
            return "0"
        return ""

    def load_bootstrap_variables() -> None:
        text = (
            load_quest_text("../MapQuest_def/QManage.TXT")
            or load_quest_text("MapQuest_def/QManage.TXT")
            or load_quest_text("../QManage.TXT")
            or load_quest_text("QManage.TXT")
        )
        if not text:
            return None
        lines = text.splitlines()
        start = next((index + 1 for index, line in enumerate(lines) if line.strip().casefold() == "[@startup]"), 0)
        if start:
            end = next((index for index in range(start, len(lines)) if lines[index].strip().startswith("[@")), len(lines))
            lines = lines[start:end]
        for line in lines:
            stripped = line.strip()
            match = re.match(r"^\s*mov\s+(?P<name>\S+)\s+(?P<value>.*?)\s*$", stripped, re.IGNORECASE)
            if not match:
                continue
            name = match.group("name").strip()
            if variable_value(name) is None:
                variables[name] = match.group("value").strip()
        trace.append("loaded bootstrap variables: QManage.TXT")
        return None

    def handle_other_act(raw: str) -> bool:
        match = _GET_LIST_STRING_RE.match(raw)
        if match:
            index = resolve_number(match.group("index"))
            path = resolve_text(match.group("path"))
            text = load_quest_text(path) or ""
            lines = text.splitlines()
            line = lines[index] if 0 <= index < len(lines) else ""
            raw_number_var = match.group("number_var")
            if raw_number_var:
                string_value, number_value = split_list_line(line)
            else:
                string_value, number_value = line.strip(), ""
            string_var = variable_name_from_token(match.group("string_var"))
            if string_var:
                apply_mov(string_var, string_value)
            number_var = variable_name_from_token(raw_number_var)
            if number_var:
                apply_mov(number_var, number_value)
            trace.append(
                f"GetListString {path}[{index}] -> {string_var or match.group('string_var')}={string_value!r}"
                + (f", {number_var}={number_value!r}" if number_var else "")
            )
            return True
        match = _TEXTSPLIT_RE.match(raw)
        if match:
            delimiter = token_value(match.group("delimiter"))
            source = token_value(match.group("source"))
            target_name = variable_name_from_token(match.group("target"))
            if target_name:
                parts = source.split(delimiter) if delimiter else [source]
                for offset, part in enumerate(parts):
                    apply_mov(sequential_variable_name(target_name, offset), part)
                trace.append(f"Textsplit {delimiter!r} -> {target_name}[{len(parts)}]")
            return True
        match = _TEXTREPLACE_RE.match(raw)
        if match:
            source = token_value(match.group("source"))
            old = token_value(match.group("old"))
            new = token_value(match.group("new"))
            target_name = variable_name_from_token(match.group("target"))
            if target_name:
                apply_mov(target_name, source.replace(old, new))
                trace.append(f"TextReplace -> {target_name}")
            return True
        match = _TEXTLENGTH_RE.match(raw)
        if match:
            target_name = variable_name_from_token(match.group("target"))
            if target_name:
                apply_mov(target_name, str(display_width(token_value(match.group("source")))))
                trace.append(f"Textlength -> {target_name}")
            return True
        match = _GET_DB_ITEM_FIELD_RE.match(raw)
        if match:
            target_name = variable_name_from_token(match.group("target"))
            if target_name:
                value = item_field_value(token_value(match.group("name")), match.group("field"), target_name)
                apply_mov(target_name, value)
                trace.append(f"GetDBitemFieldValue {match.group('field')} -> {target_name}={value!r}")
            return True
        match = _GET_DB_MONSTER_FIELD_RE.match(raw)
        if match:
            target_name = variable_name_from_token(match.group("target"))
            if target_name:
                value = monster_field_value(token_value(match.group("name")), match.group("field"), target_name)
                apply_mov(target_name, value)
                trace.append(f"GetDBMonsterFieldValue {match.group('field')} -> {target_name}={value!r}")
            return True
        match = _EXTRACT_STRING_RE.match(raw)
        if match:
            delimiter = token_value(match.group("delimiter"))
            source = token_value(match.group("source"))
            target_names = [variable_name_from_token(part) for part in match.group("targets").split()]
            parts = source.split(delimiter) if delimiter else [source]
            for index, target_name in enumerate(target_names):
                if target_name:
                    apply_mov(target_name, parts[index].strip() if index < len(parts) else "")
            trace.append(f"ExtractString {delimiter!r} -> {len(target_names)} targets")
            return True
        match = _READ_CONFIG_FILE_ITEM_RE.match(raw)
        if match:
            path = resolve_text(match.group("path"))
            section = token_value(match.group("section"))
            item = token_value(match.group("item"))
            target_name = variable_name_from_token(match.group("target"))
            value = config_item_value(load_quest_text(path) or "", section, item)
            if target_name:
                apply_mov(target_name, value)
                trace.append(f"ReadConfigFileItem {path}[{section}] {item} -> {target_name}={value!r}")
            return True
        match = _SET_STRING_BLANK_RE.match(raw)
        if match:
            target_name = variable_name_from_token(match.group("target"))
            if target_name:
                width = resolve_number(match.group("width"))
                current_value = variable_value(target_name)
                if current_value is None:
                    current_value = ""
                padded = pad_to_display_width(current_value, width, match.group("mode"))
                apply_mov(target_name, padded)
                trace.append(f"SetStringBlank {target_name} width={width}")
            return True
        match = _ARITH_RE.match(raw)
        if match:
            name = match.group("name").strip()
            current_value = resolve_number(f"<$STR({name})>")
            value = resolve_number(match.group("value") or "1")
            op = match.group("op").upper()
            if op == "MUL":
                current_value *= value
            elif op == "DIV":
                current_value = int(current_value / value) if value else 0
            elif op == "INC":
                current_value += value
            elif op == "DEC":
                current_value -= value
            apply_mov(name, str(current_value))
            trace.append(f"{op} {name} {value} -> {current_value}")
            return True
        return False

    def evaluate_condition_line(line: str) -> bool | None:
        parts = line.split()
        if not parts:
            return True
        op = parts[0].lower()
        if op == "not" and len(parts) >= 2:
            nested = evaluate_condition_line(" ".join(parts[1:]))
            if nested is None:
                return None
            return not nested
        if op == "equal" and len(parts) >= 2:
            raw_right = " ".join(parts[2:]) if len(parts) > 2 else ""
            numeric_compare = bool(raw_right and re.fullmatch(r"-?\d+(?:\.\d+)?", raw_right.strip()))
            if condition_token_is_unknown(parts[1], numeric=numeric_compare) or condition_token_is_unknown(raw_right, numeric=numeric_compare):
                return None
            left = condition_token_value(parts[1], numeric=numeric_compare)
            right = condition_token_value(raw_right, numeric=numeric_compare) if len(parts) > 2 else ""
            return left == right
        if op in {"larger", "large"} and len(parts) >= 3:
            return condition_number(parts[1]) > condition_number(" ".join(parts[2:]))
        if op in {"small", "less"} and len(parts) >= 3:
            return condition_number(parts[1]) < condition_number(" ".join(parts[2:]))
        if op == "checktextlist" and len(parts) >= 3:
            return check_text_list(resolve_text(parts[1]), condition_token_value(" ".join(parts[2:])))
        match = _GET_STRING_POS_EX_RE.match(line)
        if match:
            number_var = variable_name_from_token(match.group("number_var"))
            string_var = variable_name_from_token(match.group("string_var"))
            if number_var is None or string_var is None:
                return False
            return get_string_pos_ex(resolve_text(match.group("path")), condition_token_value(match.group("needle")), number_var, string_var)
        return None

    def evaluate_section_condition(section: ScriptSection) -> bool | None:
        checks = [evaluate_condition_line(line) for line in section.if_lines if line.strip()]
        if not checks:
            return True
        if section.if_mode == "or":
            if any(check is True for check in checks):
                return True
            if any(check is None for check in checks):
                return None
            return False
        if any(check is False for check in checks):
            return False
        if any(check is None for check in checks):
            return None
        return True

    load_bootstrap_variables()

    def resolve_goto(label: str, context_path: str) -> MethodRef | None:
        if workspace is not None:
            return workspace.resolve_label(label, context_path=context_path)
        assert isinstance(script_or_workspace, NpcScript)
        block = script_or_workspace.method_index.get(_normalize_label(label))
        if block is None:
            return None
        return MethodRef(script_or_workspace.source_path or MAIN_KEY, block.label, block)

    def resolve_call(file_path: str, label: str) -> MethodRef | None:
        if workspace is None:
            return None
        target = workspace.resolve_call(file_path, label)
        if target is not None or options.call_loader is None:
            return target
        text = options.call_loader(file_path)
        if text is None:
            return None
        workspace.register_path(file_path, text)
        if options.on_call_loaded is not None:
            options.on_call_loaded(file_path)
        return workspace.resolve_call(file_path, label)

    def run_section(section: ScriptSection, method: MethodRef) -> MethodRef | str | None:
        nonlocal final_ref, say_page_seen
        target_page = max(1, options.say_page_index)
        for stmt in section.act:
            if stmt.kind == ActKind.MOV and stmt.mov is not None:
                apply_mov(stmt.mov.name, resolve_text(stmt.mov.value))
                continue
            movr_match = _MOVR_RE.match(stmt.raw)
            if movr_match:
                apply_mov(movr_match.group("name").strip(), str(resolve_number(movr_match.group("min"))))
                continue
            if stmt.kind == ActKind.OPENMERCHANT:
                act_lines.append(stmt.raw)
                act_source_refs.append(source_ref_for_line(method, stmt.span.line_start, stmt.raw))
                trace.append(f"{method.label}@{method.source_path}: {stmt.raw.strip()}")
                continue
            if stmt.kind == ActKind.CALL and stmt.call is not None:
                call = stmt.call
                trace.append(f"{method.label}: #CALL [{call.file_path}] {call.label}")
                if not options.follow_call:
                    continue
                target = resolve_call(call.file_path, call.label)
                if target is not None:
                    trace.append(f"  -> enter {target.label} ({target.source_path})")
                    say_count_before = len(say_lines)
                    result = run_method(target)
                    if len(say_lines) > say_count_before:
                        return stop_signal
                    if result is not None:
                        return result
                else:
                    trace.append("  -> call target not loaded")
                continue
            if stmt.kind == ActKind.GOTO and stmt.goto is not None:
                target_label = stmt.goto.label
                if target_label in options.skip_goto_labels:
                    trace.append(f"{method.label}: skip GOTO {target_label}")
                    continue
                trace.append(f"{method.label}: GOTO {target_label}")
                target = resolve_goto(target_label, method.source_path)
                if target is None:
                    return target_label
                say_count_before = len(say_lines)
                result = run_method(target)
                if len(say_lines) > say_count_before:
                    return stop_signal
                if result is not None:
                    return result
                continue
            if stmt.kind == ActKind.DELAYGOTO and stmt.delay_goto is not None:
                target_label = stmt.delay_goto.label
                if target_label in options.skip_goto_labels:
                    trace.append(f"{method.label}: skip DELAYGOTO {target_label}")
                    continue
                trace.append(f"{method.label}: DELAYGOTO {stmt.delay_goto.seconds}s -> {target_label}")
                target = resolve_goto(target_label, method.source_path)
                if target is None:
                    return target_label
                say_count_before = len(say_lines)
                result = run_method(target)
                if len(say_lines) > say_count_before:
                    return stop_signal
                if result is not None:
                    return result
                continue
            if stmt.kind == ActKind.BREAK:
                if target_page > 1 and say_page_seen < target_page and not section.say_lines:
                    trace.append(f"{method.label}: break skipped before target #SAY {target_page}")
                    continue
                trace.append(f"{method.label}: break")
                return break_signal
            if handle_other_act(stmt.raw):
                continue
            if stmt.raw.strip():
                trace.append(f"{method.label}: {stmt.raw.strip()}")
        if section.say_lines:
            say_page_seen += 1
            if say_page_seen == target_page:
                resolved_say_lines = [resolve_text(line) for line in section.say_lines]
                say_lines.extend(resolved_say_lines)
                for raw_line, span in zip(section.say_lines, section.say_line_spans):
                    say_source_refs.append(source_ref_for_line(method, span.line_start, raw_line))
                if len(section.say_line_spans) < len(section.say_lines):
                    say_source_refs.extend([None] * (len(section.say_lines) - len(section.say_line_spans)))
                final_ref = method
                trace.append(f"{method.label}: #SAY ({len(section.say_lines)} lines)")
            if target_page > 1 and say_page_seen >= target_page:
                return stop_signal
        return None

    def is_unknown_condition_guard(section: ScriptSection) -> bool:
        """Skip preview-only guard branches that would hide the real dialog."""
        if section.say_lines or not section.act:
            return False
        has_terminal = False
        for stmt in section.act:
            if stmt.kind in {ActKind.MOV, ActKind.OPENMERCHANT, ActKind.GOTO, ActKind.DELAYGOTO, ActKind.CALL}:
                return False
            if stmt.kind == ActKind.BREAK:
                has_terminal = True
                continue
            else:
                raw = stmt.raw.strip()
                if not raw:
                    continue
                command = raw.split(None, 1)[0].casefold()
                if command in {"close", "messagebox"}:
                    continue
                return False
        return has_terminal

    def run_method(method: MethodRef) -> MethodRef | str | None:
        nonlocal final_ref, say_lines, say_source_refs, say_page_seen
        key = (method.source_path, method.label)
        if key in call_stack:
            trace.append(f"{method.label}: circular #CALL skipped")
            return None
        call_stack.append(key)
        try:
            if not any(section.has_say for section in method.block.sections) and method.block.preamble_lines:
                say_page_seen += 1
                if say_page_seen >= max(1, options.say_page_index):
                    say_lines = list(method.block.preamble_lines)
                    say_source_refs = [
                        source_ref_for_line(method, span.line_start, raw_line)
                        for raw_line, span in zip(method.block.preamble_lines, method.block.preamble_line_spans)
                    ]
                    if len(method.block.preamble_line_spans) < len(method.block.preamble_lines):
                        say_source_refs.extend([None] * (len(method.block.preamble_lines) - len(method.block.preamble_line_spans)))
                    final_ref = method
                    trace.append(f"{method.label}: implicit #SAY ({len(say_lines)} lines)")
                    return None
            no_condition = object()
            pending_condition = no_condition
            for section_index, section in enumerate(method.block.sections):
                if section.if_lines:
                    pending_condition = evaluate_section_condition(section)
                    state = "UNKNOWN" if pending_condition is None else ("PASS" if pending_condition else "SKIP")
                    trace.append(
                        f"{method.label}: condition {state} ("
                        + ((" OR " if section.if_mode == "or" else " AND ").join(section.if_lines))
                        + ")"
                    )
                    if not section.act and not section.say_lines:
                        continue
                should_run = True
                condition_for_section = no_condition
                if section.is_else:
                    condition_for_section = pending_condition
                    should_run = (pending_condition is no_condition) or (pending_condition is None) or (pending_condition is False)
                    pending_condition = no_condition
                elif pending_condition is not no_condition and not section.if_lines:
                    condition_for_section = pending_condition
                    should_run = True if pending_condition is None else bool(pending_condition)
                    next_is_else = (
                        section_index + 1 < len(method.block.sections)
                        and method.block.sections[section_index + 1].is_else
                    )
                    if not next_is_else:
                        pending_condition = no_condition
                if not should_run:
                    trace.append(f"{method.label}: section skipped")
                    continue
                if condition_for_section is None and is_unknown_condition_guard(section):
                    trace.append(f"{method.label}: unknown guard skipped")
                    continue
                result = run_section(section, method)
                if result is stop_signal:
                    return None
                if result is break_signal:
                    return None
                if result is not None:
                    return result
            return None
        finally:
            call_stack.pop()

    while hops < options.max_goto_hops:
        hops += 1
        outcome = run_method(current)
        if say_lines:
            break
        if outcome is None:
            break
        if isinstance(outcome, MethodRef):
            current = outcome
            continue
        next_ref = resolve_goto(outcome, current.source_path)
        if next_ref is None:
            trace.append(f"missing label: {outcome}")
            break
        current = next_ref

    return PreviewBundle(
        entry_label=options.entry_label,
        entry_path=ref.source_path if ref.source_path != MAIN_KEY else None,
        final_label=final_ref.label,
        final_path=final_ref.source_path if final_ref.source_path != MAIN_KEY else None,
        variables=variables,
        act_lines=act_lines,
        say_lines=say_lines,
        act_source_refs=act_source_refs,
        say_source_refs=say_source_refs,
        merge_adjacent_text=options.merge_adjacent_text,
        trace=trace,
    )


def simulate_method_ref(workspace: ScriptWorkspace, method_ref: MethodRef, options: SimulateOptions | None = None) -> PreviewBundle:
    """从已解析的 MethodRef 开始模拟（不合并脚本）。"""
    options = options or SimulateOptions(entry_label=method_ref.label, entry_path=method_ref.source_path)
    return simulate_preview(workspace, options)
