from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SectionKind(str, Enum):
    IF = "if"
    ACT = "act"
    SAY = "say"


class ActKind(str, Enum):
    MOV = "mov"
    GOTO = "goto"
    DELAYGOTO = "delaygoto"
    CALL = "call"
    OPENMERCHANT = "openmerchant"
    BREAK = "break"
    OTHER = "other"


@dataclass
class SourceSpan:
    line_start: int = 0
    line_end: int = 0


@dataclass
class MovStmt:
    name: str
    value: str
    raw: str
    span: SourceSpan = field(default_factory=SourceSpan)


@dataclass
class GotoStmt:
    label: str
    raw: str
    span: SourceSpan = field(default_factory=SourceSpan)


@dataclass
class DelayGotoStmt:
    seconds: str
    label: str
    raw: str
    span: SourceSpan = field(default_factory=SourceSpan)


@dataclass
class CallStmt:
    """#CALL [路径] @标签 — 引入外部脚本片段（公共片段）。"""

    file_path: str
    label: str
    raw: str
    span: SourceSpan = field(default_factory=SourceSpan)


@dataclass
class ActStatement:
    kind: ActKind
    raw: str
    mov: MovStmt | None = None
    goto: GotoStmt | None = None
    delay_goto: DelayGotoStmt | None = None
    call: CallStmt | None = None
    span: SourceSpan = field(default_factory=SourceSpan)


@dataclass
class ScriptSection:
    """
    方法体内一段 #IF → #ACT → #SAY 逻辑（任一可省略）。
    预览渲染主要消费 say_text；if_lines / act 供轻量模拟使用。
    """

    if_lines: list[str] = field(default_factory=list)
    if_mode: str = "if"
    if_param: str = ""
    is_else: bool = False
    act: list[ActStatement] = field(default_factory=list)
    say_lines: list[str] = field(default_factory=list)
    say_line_spans: list[SourceSpan] = field(default_factory=list)
    span: SourceSpan = field(default_factory=SourceSpan)

    @property
    def say_text(self) -> str:
        return "".join(self.say_lines)

    @property
    def has_say(self) -> bool:
        return bool(self.say_text.strip())


@dataclass
class MethodBlock:
    """[@关键字] 方法体，可嵌套在父方法的 { } 内。"""

    label: str
    sections: list[ScriptSection] = field(default_factory=list)
    preamble_lines: list[str] = field(default_factory=list)
    preamble_line_spans: list[SourceSpan] = field(default_factory=list)
    children: list["MethodBlock"] = field(default_factory=list)
    parent_label: str | None = None
    wrapped_in_braces: bool = False
    span: SourceSpan = field(default_factory=SourceSpan)

    def all_calls(self) -> list[CallStmt]:
        calls: list[CallStmt] = []
        for section in self.sections:
            for stmt in section.act:
                if stmt.call is not None:
                    calls.append(stmt.call)
        for child in self.children:
            calls.extend(child.all_calls())
        return calls

    def iter_methods_depth_first(self) -> list["MethodBlock"]:
        out = [self]
        for child in self.children:
            out.extend(child.iter_methods_depth_first())
        return out

    def preamble_text(self) -> str:
        return "".join(self.preamble_lines)


@dataclass
class NpcScript:
    """完整 NPC 脚本 AST。"""

    source: str
    source_path: str | None = None
    methods: list[MethodBlock] = field(default_factory=list)
    orphan_lines: list[str] = field(default_factory=list)

    @property
    def method_index(self) -> dict[str, MethodBlock]:
        index: dict[str, MethodBlock] = {}
        for method in self.methods:
            for block in method.iter_methods_depth_first():
                index.setdefault(block.label, block)
        return index

    def all_calls(self) -> list[CallStmt]:
        calls: list[CallStmt] = []
        for method in self.methods:
            calls.extend(method.all_calls())
        return calls

    def labels(self) -> list[str]:
        return list(self.method_index.keys())
