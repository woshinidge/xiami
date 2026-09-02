from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..npc_dialog_core import NpcDialog, parse_npc_dialog_pages
from .profile import Engine, EngineProfile, get_profile

_LABEL_RE = re.compile("^@(?P<label>.+)$", re.IGNORECASE)
_EQUAL_RE = re.compile("^\\s*EQUAL\\s+(?P<name>\\S+)\\s+(?P<value>.+?)\\s*$", re.IGNORECASE)
_CHECKLEVEL_RE = re.compile("^\\s*CHECKLEVEL\\s+(?P<op>[<>=]+)\\s+(?P<value>\\d+)\\s*$", re.IGNORECASE)


@dataclass
class NpcRuntimeState:
    engine: "Engine" = Engine.GOM
    current_label: "str" = "主对话"
    variables: "dict[str, str]" = field(default_factory=dict)
    global_variables: "dict[str, str]" = field(default_factory=dict)
    npc_inputs: "dict[int, str]" = field(default_factory=dict)
    command_log: "list[str]" = field(default_factory=list)
    builtin: "dict[str, str]" = field(
        default_factory=lambda: {
            "USERNAME": "畅玩可视化",
            "LEVEL": "50",
            "GAMEGLORY": "1000",
        }
    )
    if_overrides: "dict[str, bool]" = field(default_factory=dict)


class NpcLightRuntime:
    """GOM / 翎风 NPC 脚本轻量模拟运行时（RT 系列）。"""

    def __init__(
        self,
        source: str = "",
        *,
        engine: Engine | str = Engine.GOM,
        profile: EngineProfile | None = None,
    ) -> None:
        self.source = source
        self.profile = profile or get_profile(engine)
        self.state = NpcRuntimeState(engine=self.profile.engine)
        self._pages: list[NpcDialog] = []
        self._page_index: dict[str, int] = {}
        if source:
            self.load(source)

    def load(self, source: str) -> None:
        self.source = source
        self._pages = parse_npc_dialog_pages(source)
        self._page_index = {page.label: index for index, page in enumerate(self._pages)}
        if self._pages and self.state.current_label not in self._page_index:
            self.state.current_label = self._pages[0].label

    @property
    def pages(self) -> list[NpcDialog]:
        return list(self._pages)

    def current_page(self) -> NpcDialog | None:
        index = self._page_index.get(self.state.current_label)
        if index is None:
            if self._pages:
                return self._pages[0]
            return None
        return self._pages[index]

    def set_variable(self, name: str, value: str, *, global_scope: bool = False) -> None:
        if global_scope:
            self.state.global_variables[name] = value
        else:
            self.state.variables[name] = value

    def get_variable(self, name: str) -> str | None:
        if name in self.state.variables:
            return self.state.variables[name]
        return self.state.global_variables.get(name)

    def resolve_builtin(self, token: str) -> str | None:
        """解析 <$USERNAME> 形式内置变量（不含 STR）。"""
        inner = token.strip()
        if inner.startswith("<$") and inner.endswith(">"):
            inner = inner[2:-1]
        key = inner.upper()
        if key in self.state.builtin:
            return self.state.builtin[key]
        if key.startswith("NPCINPUT(") and key.endswith(")"):
            try:
                index = int(key[len("NPCINPUT("):-1])
            except ValueError:
                return None
            return self.state.npc_inputs.get(index, "")
        return None

    def run_command(self, command: str, *, input_value: str = "") -> str | None:
        """
        处理点击触发的 @命令。返回跳转目标标签（若有），否则 None。
        RT-001 / RT-002
        """
        command = command.strip()
        if not command:
            return None
        line = command
        if input_value:
            line = f"{command} = {input_value}"
        self.state.command_log.append(line)
        if command.lower().startswith("@@inputstring"):
            match = re.search("(\\d+)\\s*$", command)
            if match and input_value:
                self.state.npc_inputs[int(match.group(1))] = input_value
            return None
        label = self._normalize_label(command)
        if label and label in self._page_index:
            self.state.current_label = label
            return label
        return None

    def evaluate_if_line(self, line: str) -> bool | None:
        """
        RT-010 桩：评估单行 #IF 条件。
        返回 None 表示无法识别，由 if_unknown_defaults_false 决定。
        """
        stripped = line.strip()
        if not stripped:
            return True
        if stripped in self.state.if_overrides:
            return self.state.if_overrides[stripped]
        match = _EQUAL_RE.match(stripped)
        if match:
            name = match.group("name")
            expected = match.group("value").strip()
            actual = self.get_variable(name)
            if actual is None:
                actual = self.state.global_variables.get(name)
            return (actual or "") == expected
        match = _CHECKLEVEL_RE.match(stripped)
        if match:
            try:
                level = int(self.state.builtin.get("LEVEL", "0"))
                threshold = int(match.group("value"))
            except ValueError:
                return False
            op = match.group("op")
            if op == ">":
                return level > threshold
            if op == "<":
                return level < threshold
            if op in {"=>", ">="}:
                return level >= threshold
            if op in {"<=", "=<"}:
                return level <= threshold
            if op == "=":
                return level == threshold
            return False
        return None

    def evaluate_if_block(self, lines: list[str], *, mode: str = "if") -> bool:
        """多行 #IF：全部可识别行 AND；含未知行时按引擎配置默认 false。"""
        if not lines:
            return True
        if mode.lower() == "or":
            unknown_defaults_true = not self.profile.if_unknown_defaults_false
            saw_unknown = False
            for line in lines:
                result = self.evaluate_if_line(line)
                if result is None:
                    saw_unknown = True
                elif result:
                    return True
            return saw_unknown and unknown_defaults_true
        for line in lines:
            result = self.evaluate_if_line(line)
            if result is None:
                return not self.profile.if_unknown_defaults_false
            if not result:
                return False
        return True

    @staticmethod
    def _normalize_label(command: str) -> str | None:
        command = command.strip()
        if not command.startswith("@"):
            return None
        match = _LABEL_RE.match(command)
        if not match:
            return None
        return f'@{match.group("label").strip()}'
