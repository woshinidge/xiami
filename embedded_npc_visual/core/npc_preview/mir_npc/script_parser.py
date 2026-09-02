from __future__ import annotations

import re

from .call_path import normalize_call_path
from .script_model import (
    ActKind,
    ActStatement,
    CallStmt,
    DelayGotoStmt,
    GotoStmt,
    MethodBlock,
    MovStmt,
    NpcScript,
    ScriptSection,
    SourceSpan,
)

_LABEL_LINE_RE = re.compile(r"^\s*\[@(?P<label>[^\]]+)\]\s*$")
_SECTION_RE = re.compile(
    r"^\s*#(?P<section>if|or)(?:\s*\((?P<param>[^)]*)\))?\s*$"
    r"|^\s*#(?P<plain_section>act|say|elseact|elsesay)\s*$",
    re.IGNORECASE,
)
_MOV_RE = re.compile(r"^\s*mov\s+(?P<name>\S+)(?:\s+(?P<value>.*?))?\s*$", re.IGNORECASE)
_GOTO_RE = re.compile(r"^\s*goto\s+(?P<label>@\S+)\s*$", re.IGNORECASE)
_DELAYGOTO_RE = re.compile(r"^\s*delay(?:goto|call)\s+(?P<seconds>\S+)\s+(?P<label>@\S+)\s*$", re.IGNORECASE)
_CALL_RE = re.compile(r"^\s*#CALL\s+\[(?P<path>[^\]]+)\]\s+(?P<label>@\S+)\s*$", re.IGNORECASE)
_OPENMERCHANT_RE = re.compile(r"^\s*OPENMERCHANTBIGDLG\b", re.IGNORECASE)
_BREAK_RE = re.compile(r"^\s*break\s*$", re.IGNORECASE)
_SCRIPT_HEADER_DECL_RE = re.compile(r"^\(\s*@+\S+(?:\s+@+\S+)*\s*\)$", re.IGNORECASE)
_SCRIPT_SYSTEM_FLAG_RE = re.compile(r"^[+\-%]\d+\s*$")
_BRACE_LINES = frozenset({"{", "}"})
_ACT_LIKE_KINDS = frozenset(
    {
        ActKind.MOV,
        ActKind.GOTO,
        ActKind.DELAYGOTO,
        ActKind.CALL,
        ActKind.OPENMERCHANT,
        ActKind.BREAK,
    }
)


def _strip_line(line: str) -> str:
    return line.rstrip("\r\n")


def _line_body(line: str) -> str:
    return _strip_line(line).strip()


def _is_comment(line: str) -> bool:
    body = _line_body(line)
    return (
        body.startswith(";")
        or _SCRIPT_HEADER_DECL_RE.match(body) is not None
        or _SCRIPT_SYSTEM_FLAG_RE.match(body) is not None
    )


def _is_blank(line: str) -> bool:
    return not _line_body(line)


def _normalize_label(label: str) -> str:
    label = label.strip()
    if label.startswith("@"):
        return label
    return f"@{label}"


def _parse_act_line(line: str, line_no: int) -> ActStatement:
    body = _strip_line(line)
    span = SourceSpan(line_start=line_no, line_end=line_no + 1)

    match = _MOV_RE.match(body)
    if match:
        mov = MovStmt(
            name=match.group("name").strip(),
            value=(match.group("value") or "").strip(),
            raw=body,
            span=span,
        )
        return ActStatement(kind=ActKind.MOV, raw=body, mov=mov, span=span)

    match = _DELAYGOTO_RE.match(body)
    if match:
        delay_goto = DelayGotoStmt(
            seconds=match.group("seconds").strip(),
            label=_normalize_label(match.group("label")),
            raw=body,
            span=span,
        )
        return ActStatement(kind=ActKind.DELAYGOTO, raw=body, delay_goto=delay_goto, span=span)

    match = _GOTO_RE.match(body)
    if match:
        goto = GotoStmt(label=_normalize_label(match.group("label")), raw=body, span=span)
        return ActStatement(kind=ActKind.GOTO, raw=body, goto=goto, span=span)

    match = _CALL_RE.match(body)
    if match:
        call = CallStmt(
            file_path=normalize_call_path(match.group("path")),
            label=_normalize_label(match.group("label")),
            raw=body,
            span=span,
        )
        return ActStatement(kind=ActKind.CALL, raw=body, call=call, span=span)

    if _BREAK_RE.match(body):
        return ActStatement(kind=ActKind.BREAK, raw=body, span=span)
    if _OPENMERCHANT_RE.match(body):
        return ActStatement(kind=ActKind.OPENMERCHANT, raw=body, span=span)
    return ActStatement(kind=ActKind.OTHER, raw=body, span=span)


def _parse_sections(lines: list[tuple[int, str]]) -> tuple[list[ScriptSection], list[str], list[SourceSpan]]:
    """将方法体行解析为 #IF/#ACT/#SAY 段列表及前导行。

    注意：模拟器按“IF-only section + 后续 ACT/SAY section”的形式消费
    条件状态，所以这里保留原始分段语义，不把 #IF/#ACT/#SAY 合并为同一
    ScriptSection。
    """
    sections: list[ScriptSection] = []
    preamble: list[str] = []
    preamble_spans: list[SourceSpan] = []
    state = "none"
    current: ScriptSection | None = None

    def flush() -> None:
        nonlocal current, state
        if current is not None and (current.if_lines or current.act or current.say_lines):
            sections.append(current)
        current = None
        state = "none"

    def maybe_implicit_act(line: str, line_no: int) -> bool:
        nonlocal current, state
        stmt = _parse_act_line(line, line_no)
        if stmt.kind not in _ACT_LIKE_KINDS:
            return False
        current = ScriptSection(act=[stmt], span=SourceSpan(line_start=line_no, line_end=line_no + 1))
        state = "implicit_act"
        return True

    for line_no, raw_line in lines:
        if _is_comment(raw_line):
            continue

        body = _line_body(raw_line)
        if body in _BRACE_LINES:
            continue

        section_match = _SECTION_RE.match(body)
        if section_match:
            flush()
            raw_state = (section_match.group("section") or section_match.group("plain_section") or "").lower()
            current = ScriptSection(
                is_else=raw_state in {"elsesay", "elseact"},
                span=SourceSpan(line_start=line_no, line_end=line_no + 1),
            )
            state = raw_state
            if section_match.group("param") is not None:
                current.if_param = section_match.group("param").strip()
            if state == "or":
                current.if_mode = "or"
                state = "if"
            elif state == "elseact":
                state = "act"
            elif state == "elsesay":
                state = "say"
            continue

        if state == "none":
            if _is_blank(raw_line):
                continue
            if maybe_implicit_act(raw_line, line_no):
                continue
            preamble.append(raw_line)
            preamble_spans.append(SourceSpan(line_start=line_no, line_end=line_no + 1))
            continue

        if state == "implicit_act":
            if _is_blank(raw_line):
                continue
            stmt = _parse_act_line(raw_line, line_no)
            if stmt.kind in _ACT_LIKE_KINDS:
                assert current is not None
                current.span.line_end = line_no + 1
                current.act.append(stmt)
                continue
            flush()
            preamble.append(raw_line)
            preamble_spans.append(SourceSpan(line_start=line_no, line_end=line_no + 1))
            continue

        assert current is not None
        current.span.line_end = line_no + 1
        if state == "if":
            current.if_lines.append(body)
        elif state == "act":
            current.act.append(_parse_act_line(raw_line, line_no))
        elif state == "say":
            current.say_lines.append(raw_line)
            current.say_line_spans.append(SourceSpan(line_start=line_no, line_end=line_no + 1))
        else:
            flush()
            return sections, preamble, preamble_spans

    flush()
    return sections, preamble, preamble_spans


def _peek_non_blank(lines: list[tuple[int, str]], start: int) -> int:
    index = start
    while index < len(lines) and _is_blank(lines[index][1]):
        index += 1
    return index


def _parse_method_at(
    lines: list[tuple[int, str]],
    start: int,
    *,
    stop_at_brace_close: bool,
) -> tuple[MethodBlock | None, int]:
    if start >= len(lines):
        return None, start

    line_no, raw_line = lines[start]
    match = _LABEL_LINE_RE.match(_strip_line(raw_line))
    if not match:
        return None, start

    label = _normalize_label(match.group("label"))
    index = _peek_non_blank(lines, start + 1)
    wrapped = index < len(lines) and _line_body(lines[index][1]) == "{"
    if wrapped:
        index += 1

    body_lines: list[tuple[int, str]] = []
    children: list[MethodBlock] = []
    brace_depth = 1 if wrapped else 0

    while index < len(lines):
        ln, raw = lines[index]
        body = _line_body(raw)

        if wrapped:
            if body == "{":
                brace_depth += 1
                index += 1
                continue
            if body == "}":
                brace_depth -= 1
                index += 1
                if brace_depth <= 0:
                    break
                continue
            if brace_depth == 1 and _LABEL_LINE_RE.match(_strip_line(raw)):
                child, index = _parse_method_at(lines, index, stop_at_brace_close=True)
                if child is not None:
                    child.parent_label = label
                    children.append(child)
                    continue
        else:
            if _LABEL_LINE_RE.match(_strip_line(raw)):
                break
            if stop_at_brace_close and body == "}":
                break

        body_lines.append((ln, raw))
        index += 1

    sections, preamble, preamble_spans = _parse_sections(body_lines)
    end_line = lines[index - 1][0] + 1 if index > start + 1 else line_no + 1
    block = MethodBlock(
        label=label,
        sections=sections,
        preamble_lines=preamble,
        preamble_line_spans=preamble_spans,
        children=children,
        wrapped_in_braces=wrapped,
        span=SourceSpan(line_start=line_no, line_end=end_line),
    )
    return block, index


def parse_npc_script(source: str, *, source_path: str | None = None) -> NpcScript:
    """
    将 NPC 脚本文本解析为 AST。

    结构规则（SCR 系列）：
    - [@关键字] 开启方法体；可选 { } 包裹，内部可嵌套 [@内部关键字]
    - 方法体内 #IF → #ACT → #SAY（可多次、可省略）
    - #ACT 支持 mov / goto / delaygoto / #CALL / break 等
    """
    indexed = list(enumerate(source.splitlines(keepends=True)))
    methods: list[MethodBlock] = []
    orphan: list[str] = []
    index = 0

    while index < len(indexed):
        line_no, raw_line = indexed[index]
        if _LABEL_LINE_RE.match(_strip_line(raw_line)):
            block, index = _parse_method_at(indexed, index, stop_at_brace_close=False)
            if block is not None:
                methods.append(block)
                continue
        elif not _is_blank(raw_line) and not _is_comment(raw_line):
            orphan.append(raw_line)
        index += 1

    return NpcScript(source=source, source_path=source_path, methods=methods, orphan_lines=orphan)
