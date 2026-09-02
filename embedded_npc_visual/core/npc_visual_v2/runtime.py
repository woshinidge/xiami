from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

_LABEL_RE = re.compile(r"^\s*\[(?P<label>@[^\]]+)\]\s*$", re.IGNORECASE)
_DIRECTIVE_RE = re.compile(r"^\s*#(?P<name>[A-Z0-9_()]+)\b", re.IGNORECASE)
_MOV_RE = re.compile(r"^\s*mov\s+(?P<name>\S+)(?:\s+(?P<value>.*?))?\s*$", re.IGNORECASE)
_GOTO_RE = re.compile(r"^\s*goto\s+(?P<label>@?\S+)", re.IGNORECASE)
_CALL_RE = re.compile(r"^\s*#CALL\s+\[(?P<path>[^\]]+)\]\s+(?P<label>@\S+)", re.IGNORECASE)
_OPENMERCHANT_RE = re.compile(
    r"^\s*(?:OPENMERCHANTBIGDLG|OPENBIGDIALOGBOX)\b", re.IGNORECASE
)
_STR_RE = re.compile(r"<\$\s*STR\((?P<name>[^)]+)\)\s*>", re.IGNORECASE)
_STR_TOKEN_RE = re.compile(r"^<\$\s*STR\((?P<name>[^)]+)\)\s*>$", re.IGNORECASE)
_GET_LIST_STRING_RE = re.compile(r"^\s*GetListString\s+(?P<path>\S+)\s+(?P<index>\S+)\s+(?P<string_var>\S+)(?:\s+(?P<number_var>\S+))?", re.IGNORECASE)
_READ_CONFIG_RE = re.compile(r"^\s*ReadConfigFileItem\s+(?P<path>\S+)\s+(?P<section>\S+)\s+(?P<item>\S+)\s+(?P<target>\S+)", re.IGNORECASE)
_SET_STRING_BLANK_RE = re.compile(r"^\s*SetStringBlank\s+(?P<target>\S+)\s+(?P<width>-?\d+)(?:\s+(?P<mode>\S+))?", re.IGNORECASE)
_TEXTSPLIT_RE = re.compile(r"^\s*Textsplit\s+(?P<delimiter>\S+)\s+(?P<source>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_TEXTREPLACE_RE = re.compile(r"^\s*TextReplace\s+(?P<source>\S+)\s+(?P<old>\S+)\s+(?P<new>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_TEXTLENGTH_RE = re.compile(r"^\s*Textlength\s+(?P<source>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_GET_DB_ITEM_FIELD_RE = re.compile(r"^\s*GetDBitemFieldValue\s+(?P<name>\S+)\s+(?P<field>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_GET_DB_MONSTER_FIELD_RE = re.compile(r"^\s*GetDBMonsterFieldValue\s+(?P<name>\S+)\s+(?P<field>\S+)\s+(?P<target>\S+)\s*$", re.IGNORECASE)
_EXTRACT_STRING_RE = re.compile(r"^\s*ExtractString\s+(?P<delimiter>\S+)\s+(?P<source>\S+)\s+(?P<targets>.+?)\s*$", re.IGNORECASE)
_GET_STRING_POS_EX_RE = re.compile(r"^\s*GetstringPoseX\s+(?P<path>\S+)\s+(?P<needle>\S+)\s+(?P<number_var>\S+)\s+(?P<string_var>\S+)(?:\s+\S+)?\s*$", re.IGNORECASE)
_ARITH_RE = re.compile(r"^\s*(?P<op>INC|DEC|MUL|DIV)\s+(?P<name>\S+)(?:\s+(?P<value>.*?))?\s*$", re.IGNORECASE)

_USERNAME_TEXT = "畅玩可视化"
_UNDEFINED_STR_TAG = "__NPCV2_UNDEFINED_STR__"


@dataclass
class RuntimeMethod:
    label: str
    lines: list[str] = field(default_factory=list)


@dataclass
class RuntimeSnapshot:
    label: str
    variables: dict[str, str]
    act_lines: list[str]
    say_lines: list[str]
    trace: list[str] = field(default_factory=list)

    def source(self) -> str:
        parts = [f"[{self.label}]\n"]
        if self.act_lines:
            parts.append("#ACT\n")
            parts.extend(line if line.endswith("\n") else line + "\n" for line in self.act_lines)
        parts.append("#SAY\n")
        parts.extend(line if line.endswith("\n") else line + "\n" for line in self.say_lines)
        return "".join(parts)


class NpcVisualRuntimeV2:
    def __init__(
        self,
        *,
        text_loader: Callable[[str], str | None] | None = None,
        item_field_loader: Callable[[str, str, str | None], str | None] | None = None,
        monster_field_loader: Callable[[str, str, str | None], str | None] | None = None,
        max_hops: int = 128,
    ) -> None:
        self.text_loader = text_loader
        self.item_field_loader = item_field_loader
        self.monster_field_loader = monster_field_loader
        self.max_hops = max_hops
        self.methods = {}
        self.variables = {}
        self.act_lines = []
        self.say_lines = []
        self.trace = []
        self._call_stack = []
        self._hops = 0

    def simulate(self, source: str, *, entry_label: str, requested_label: str = "") -> RuntimeSnapshot | None:
        self.methods = self._parse_methods(source)
        self.variables = {}
        self.act_lines = []
        self.say_lines = []
        self.trace = []
        self._call_stack = []
        self._hops = 0
        entry = self._normalize_label(requested_label or entry_label)
        if not self._has_method(entry):
            entry = self._normalize_label(entry_label)
        if not self._has_method(entry):
            return None
        final_label = self._run_method(entry) or entry
        if not self.say_lines and not self.act_lines:
            return None
        return RuntimeSnapshot(
            label=final_label,
            variables=dict(self.variables),
            act_lines=list(self.act_lines),
            say_lines=list(self.say_lines),
            trace=list(self.trace),
        )

    def _parse_methods(self, source: str) -> dict[str, RuntimeMethod]:
        methods: dict[str, RuntimeMethod] = {}
        current = None
        for raw in source.splitlines(True):
            match = _LABEL_RE.match(raw.strip())
            if match:
                label = self._normalize_label(match.group("label"))
                current = RuntimeMethod(label=label)
                methods.setdefault(label.casefold(), current)
                methods[label] = current
            elif current is not None:
                current.lines.append(raw)
        return methods

    def _run_method(self, label: str) -> str | None:
        label = self._normalize_label(label)
        key = label.casefold()
        method = self.methods.get(key) or self.methods.get(label)
        if method is None:
            self.trace.append(f"missing label: {label}")
            return None
        if key in self._call_stack:
            self.trace.append(f"circular skipped: {label}")
            return None
        self._call_stack.append(key)
        self._hops += 1
        if self._hops > self.max_hops:
            self.trace.append("max hops reached")
            self._call_stack.pop()
            return None
        try:
            return self._run_lines(method)
        finally:
            self._call_stack.pop()

    def _has_method(self, label: str) -> bool:
        label = self._normalize_label(label)
        return label in self.methods or label.casefold() in self.methods

    def _run_lines(self, method: RuntimeMethod) -> str | None:
        mode = ""
        condition_lines: list[str] = []
        condition_operator = "and"
        pending_condition = True
        current_active = True
        say_buffer: list[str] = []

        def flush_say() -> str | None:
            if not say_buffer:
                return None
            self.say_lines.extend(self._resolve_text(line) for line in say_buffer)
            self.trace.append(f"{method.label}: #SAY {len(say_buffer)} lines")
            return method.label

        for raw in method.lines:
            stripped = raw.strip()
            if not stripped or stripped in {"{", "}"} or stripped.startswith(";"):
                continue
            directive = _DIRECTIVE_RE.match(stripped)
            if directive:
                name = directive.group("name").upper()
                if name == "IF" or name.startswith("IF(") or name == "OR":
                    if mode == "say":
                        result = flush_say()
                        if result:
                            return result
                    condition_lines = []
                    condition_operator = "or" if name == "OR" else "and"
                    inline = self._inline_condition(stripped, name)
                    if inline:
                        condition_lines.append(inline)
                    mode = "cond"
                    current_active = True
                    continue
                if name == "ACT":
                    pending_condition = self._evaluate_conditions(condition_lines, mode=condition_operator)
                    current_active = bool(pending_condition)
                    mode = "act"
                    continue
                if name == "ELSEACT":
                    current_active = not bool(pending_condition)
                    mode = "act"
                    continue
                if name in {'SAY', 'ELSESAY'}:
                    if mode == "say":
                        result = flush_say()
                        if result:
                            return result
                    current_active = current_active if name == "SAY" else not bool(pending_condition)
                    say_buffer = []
                    mode = "say"
                    continue
                if name == "CALL":
                    mode = "act"
            if mode == "cond":
                condition_lines.append(stripped)
                continue
            if mode == "say":
                if current_active:
                    say_buffer.append(raw)
                continue
            if not current_active:
                continue
            result = self._handle_act(stripped, method)
            if result:
                return result
        if mode == "say":
            result = flush_say()
            if result:
                return result
        return None

    def _handle_act(self, raw: str, method: RuntimeMethod) -> str | None:
        if raw.upper() == "BREAK":
            self.trace.append(f"{method.label}: break")
            if self.say_lines:
                return method.label
            return None
        match = _CALL_RE.match(raw)
        if match:
            call_label = self._normalize_label(match.group("label"))
            self.trace.append(f"{method.label}: #CALL {call_label}")
            return self._run_method(call_label)
        match = _GOTO_RE.match(raw)
        if match:
            target = self._normalize_label(match.group("label"))
            self.trace.append(f"{method.label}: GOTO {target}")
            result = self._run_method(target)
            if self.say_lines:
                return result
            return None
        if _OPENMERCHANT_RE.match(raw):
            self.act_lines.append(raw)
            return None
        match = _MOV_RE.match(raw)
        if match:
            self._set_var(match.group("name"), self._resolve_text(match.group("value") or ""))
            return None
        match = _ARITH_RE.match(raw)
        if match:
            self._apply_arith(match.group("op").upper(), match.group("name"), match.group("value") or "1")
            return None
        if self._handle_get_list_string(raw):
            return None
        if self._handle_read_config(raw):
            return None
        if self._handle_set_string_blank(raw):
            return None
        if self._handle_textsplit(raw):
            return None
        if self._handle_textreplace(raw):
            return None
        if self._handle_textlength(raw):
            return None
        if self._handle_extract_string(raw):
            return None
        if self._handle_get_db_item_field(raw):
            return None
        if self._handle_get_db_monster_field(raw):
            return None
        return None

    def _handle_get_list_string(self, raw: str) -> bool:
        match = _GET_LIST_STRING_RE.match(raw)
        if not match:
            return False
        index = self._number_value(match.group("index"))
        text = self._load_text(match.group("path")) or ""
        lines = text.splitlines()
        line = lines[index] if 0 <= index < len(lines) else ""
        string_var = self._variable_name(match.group("string_var"))
        number_var = self._variable_name(match.group("number_var"))
        if number_var:
            left, right = self._split_list_line(line)
            self._set_var(string_var, left)
            self._set_var(number_var, right)
        else:
            self._set_var(string_var, line.strip())
        self.trace.append(f"GetListString {match.group('path')}[{index}]")
        return True

    def _handle_read_config(self, raw: str) -> bool:
        match = _READ_CONFIG_RE.match(raw)
        if not match:
            return False
        text = self._load_text(match.group("path")) or ""
        section = self._token_text(match.group("section")).strip()
        item = self._token_text(match.group("item")).strip()
        value = self._config_value(text, section, item)
        self._set_var(self._variable_name(match.group("target")), value)
        self.trace.append(f"ReadConfigFileItem {section}.{item}={value!r}")
        return True

    def _handle_set_string_blank(self, raw: str) -> bool:
        match = _SET_STRING_BLANK_RE.match(raw)
        if not match:
            return False
        name = self._variable_name(match.group("target"))
        if not name:
            return True
        width = self._number_value(match.group("width"))
        current = self.variables.get(name, "")
        missing = max(0, width - self._display_width(current))
        if (match.group("mode") or "").strip() == "0":
            current = " " * missing + current
        else:
            current = current + " " * missing
        self._set_var(name, current)
        return True

    def _handle_textsplit(self, raw: str) -> bool:
        match = _TEXTSPLIT_RE.match(raw)
        if not match:
            return False
        delimiter = self._token_text(match.group("delimiter"))
        source = self._token_text(match.group("source"))
        target = self._variable_name(match.group("target"))
        if not target:
            return True
        parts = source.split(delimiter) if delimiter else [source]
        for offset, part in enumerate(parts):
            self._set_var(self._sequential_variable_name(target, offset), part)
        self.trace.append(f"Textsplit {delimiter!r} -> {target}[{len(parts)}]")
        return True

    def _handle_textreplace(self, raw: str) -> bool:
        match = _TEXTREPLACE_RE.match(raw)
        if not match:
            return False
        target = self._variable_name(match.group("target"))
        if target:
            self._set_var(
                target,
                self._token_text(match.group("source")).replace(
                    self._token_text(match.group("old")),
                    self._token_text(match.group("new")),
                ),
            )
        return True

    def _handle_textlength(self, raw: str) -> bool:
        match = _TEXTLENGTH_RE.match(raw)
        if not match:
            return False
        target = self._variable_name(match.group("target"))
        if target:
            self._set_var(
                target,
                str(self._display_width(self._token_text(match.group("source")))),
            )
        return True

    def _handle_extract_string(self, raw: str) -> bool:
        match = _EXTRACT_STRING_RE.match(raw)
        if not match:
            return False
        delimiter = self._token_text(match.group("delimiter"))
        source = self._token_text(match.group("source"))
        parts = source.split(delimiter) if delimiter else [source]
        targets = [self._variable_name(part) for part in match.group("targets").split()]
        for index, target in enumerate(targets):
            if target:
                self._set_var(target, parts[index].strip() if index < len(parts) else "")
        self.trace.append(f"ExtractString {delimiter!r} -> {len(targets)} targets")
        return True

    def _handle_get_db_item_field(self, raw: str) -> bool:
        match = _GET_DB_ITEM_FIELD_RE.match(raw)
        if not match:
            return False
        target = self._variable_name(match.group("target"))
        if target:
            value = self._item_field_value(
                self._token_text(match.group("name")),
                match.group("field"),
                target,
            )
            self._set_var(target, value)
            self.trace.append(
                f"GetDBitemFieldValue {match.group('field')} -> {target}={value!r}"
            )
        return True

    def _handle_get_db_monster_field(self, raw: str) -> bool:
        match = _GET_DB_MONSTER_FIELD_RE.match(raw)
        if not match:
            return False
        target = self._variable_name(match.group("target"))
        if target:
            value = self._monster_field_value(
                self._token_text(match.group("name")),
                match.group("field"),
                target,
            )
            self._set_var(target, value)
            self.trace.append(
                f"GetDBMonsterFieldValue {match.group('field')} -> {target}={value!r}"
            )
        return True

    def _apply_arith(self, op: str, name: str, value: str) -> None:
        current = self._number_value(f"<$STR({name})>")
        amount = self._number_value(value)
        if op == "INC":
            current += amount
        elif op == "DEC":
            current -= amount
        elif op == "MUL":
            current *= amount
        elif op == "DIV":
            current = int(current / amount) if amount else 0
        self._set_var(name, str(current))

    def _evaluate_conditions(self, lines: list[str], *, mode: str = "and") -> bool:
        values = [self._evaluate_condition(line) for line in lines if line.strip()]
        if not values:
            return True
        if mode == "or":
            return any(values)
        return all(values)

    def _evaluate_condition(self, line: str) -> bool:
        text = line.strip()
        upper = text.upper()
        if upper.startswith("IF(") and upper.endswith(")"):
            inner = upper[3:-1].strip()
            return inner not in {'0', 'FALSE'}
        negated = False
        while text.upper().startswith("NOT "):
            negated = not negated
            text = text[4:].strip()
        parts = text.split()
        if not parts:
            result = True
        else:
            op = parts[0].upper()
            left = self._condition_token(parts[1]) if len(parts) >= 2 else ""
            right = self._condition_token(" ".join(parts[2:])) if len(parts) >= 3 else ""
            if op == "EQUAL":
                result = left == right
            elif op in {'LARGE', 'LARGER'}:
                result = self._to_int(left) > self._to_int(right)
            elif op in {'SMALL', 'LESS'}:
                result = self._to_int(left) < self._to_int(right)
            elif op == "CHECK":
                result = self._check_flag_value(left, right)
            elif op == "CHECKTEXTLIST":
                result = self._check_text_list(left, right)
            elif op in {'CHECKITEM', 'CHECKITEMW', 'CHECKITEMEX'}:
                result = False
            else:
                pos_match = _GET_STRING_POS_EX_RE.match(text)
                result = self._handle_get_string_pos_ex(pos_match) if pos_match else False
        return not result if negated else result

    def _handle_get_string_pos_ex(self, match) -> bool:
        if not match:
            return False
        number_var = self._variable_name(match.group("number_var"))
        string_var = self._variable_name(match.group("string_var"))
        if not number_var or not string_var:
            return False
        text = self._load_text(match.group("path")) or ""
        wanted = self._token_text(match.group("needle")).strip()
        if not text or not wanted:
            return False
        for index, raw_line in enumerate(text.splitlines()):
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            key = line.split(":", 1)[0].strip()
            if key == wanted:
                self._set_var(number_var, str(index))
                self._set_var(string_var, line)
                return True
        return False

    def _check_flag_value(self, left: str, right: str) -> bool:
        match = re.search(r"\[(?P<flag>-?\d+)\]", left)
        if not match:
            return False
        expected = self._to_int(right)
        current = self._to_int(self.variables.get("__CHECK_" + match.group("flag"), "0"))
        return current == expected

    def _inline_condition(self, line: str, keyword: str) -> str:
        if keyword.startswith("IF("):
            return keyword
        parts = line.split(maxsplit=1)
        if len(parts) > 1:
            return parts[1].strip()
        return ""

    def _resolve_text(self, value: str) -> str:
        result = value
        result = re.sub(r"<\$\s*USERNAME\s*>", _USERNAME_TEXT, result, flags=re.IGNORECASE)
        result = re.sub(r"\$USERNAME\b", _USERNAME_TEXT, result, flags=re.IGNORECASE)
        for _ in range(12):
            updated = _STR_RE.sub(lambda m: self._display_var(m.group("name")), result)
            if updated == result:
                break
            result = updated
        return result

    def _token_text(self, token: str) -> str:
        return self._resolve_text(token.strip())

    def _condition_token(self, token: str) -> str:
        token = self._resolve_text(token.strip())
        key = self._lookup_key(token)
        if key is not None:
            return self.variables.get(key, "")
        if re.fullmatch(r"[A-Z]\d+", token, re.IGNORECASE):
            if token.upper().startswith("T"):
                return self.variables.get(token, "")
            return self.variables.get(token, "0")
        return token

    def _display_var(self, name: str) -> str:
        key = self._lookup_key(name)
        if key is not None:
            return self.variables.get(key, "")
        name = name.strip()
        if re.match(r"^S\$", name, re.IGNORECASE):
            return f"<{_UNDEFINED_STR_TAG}:{name}>"
        if re.match(r"^(N|U)\$", name, re.IGNORECASE) or re.match(r"^[A-Z]+\d+$", name, re.IGNORECASE):
            return "0"
        return f"<$STR({name})>"

    def _lookup_key(self, name: str) -> str | None:
        needle = name.strip().casefold()
        for key in self.variables:
            if key.casefold() == needle:
                return key
        return None

    def _set_var(self, name: str, value: str) -> None:
        if not name:
            return None
        self.variables[name.strip()] = value

    def _variable_name(self, token: str | None) -> str:
        if token is None:
            return None
        token = token.strip()
        match = _STR_TOKEN_RE.match(token)
        if match:
            return match.group("name").strip()
        return token or None

    def _number_value(self, token: str) -> int:
        if token is None:
            return 0
        text = self._token_text(token)
        if text in self.variables:
            text = self.variables.get(text, "0")
        match = re.search(r"-?\d+", str(text))
        if match:
            return int(match.group(0))
        return 0

    def _to_int(self, value: str) -> int:
        match = re.search(r"-?\d+", value)
        if match:
            return int(match.group(0))
        return 0

    def _load_text(self, path: str) -> str | None:
        if self.text_loader is None:
            return None
        return self.text_loader(self._resolve_text(path))

    def _split_list_line(self, line: str) -> tuple[str, str]:
        for marker in (":", "|", ",", "\t"):
            if marker in line:
                left, right = line.split(marker, 1)
                return left.strip(), right.strip()
        return line.strip(), ""

    def _check_text_list(self, path: str, needle: str) -> bool:
        text = self._load_text(path) or ""
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

    def _item_field_value(self, item_name: str, field_name: str, target_name: str | None = None) -> str:
        if self.item_field_loader is not None:
            try:
                value = self.item_field_loader(item_name, field_name, target_name)
            except Exception:
                value = None
            if value is not None:
                return str(value).strip()
        if field_name.strip().casefold() != "name":
            return "0"
        return ""

    def _monster_field_value(self, monster_name: str, field_name: str, target_name: str | None = None) -> str:
        if self.monster_field_loader is not None:
            try:
                value = self.monster_field_loader(monster_name, field_name, target_name)
            except Exception:
                value = None
            if value is not None:
                return str(value).strip()
        if field_name.strip().casefold() != "name":
            return "0"
        return ""

    def _sequential_variable_name(self, base_name: str, offset: int) -> str:
        match = re.match(r"^(?P<prefix>.*?)(?P<number>\d+)$", base_name)
        if not match:
            if offset == 0:
                return base_name
            return f"{base_name}{offset + 1}"
        number = match.group("number")
        return f"{match.group('prefix')}{int(number) + offset:0{len(number)}d}"

    def _config_value(self, text: str, section: str, item: str) -> str:
        current = ""
        section_key = section.casefold()
        item_key = item.casefold()
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(";") or line.startswith("#"):
                continue
            if line.startswith("[") and "]" in line:
                current = line[1:line.find("]")].strip().casefold()
                continue
            if current != section_key or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip().casefold() == item_key:
                return value.strip()
        return ""

    def _display_width(self, text: str) -> int:
        width = 0
        for char in text:
            width += 2 if unicodedata.east_asian_width(char) in {'W', 'F'} else 1
        return width

    def _normalize_label(self, label: str | None) -> str:
        label = (label or "").strip()
        if not label:
            return "@main"
        if label.startswith("@"):
            return label
        return f"@{label}"


def read_text_guess(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    for encoding in ("utf-8-sig", "gb18030", "cp936"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")

