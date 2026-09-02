from __future__ import annotations

from dataclasses import dataclass, field

from .call_path import normalize_call_key, normalize_call_path
from .script_model import MethodBlock, NpcScript
from .script_parser import parse_npc_script
from .script_render import FileLoader

MAIN_KEY = "__editor__"


def _normalize_path(path: "str") -> "str":
    return normalize_call_key(path)


def _normalize_label(label: "str") -> "str":
    label = label.strip()
    if label.startswith("@"):
        return label
    return f"@{label}"


@dataclass(frozen=True)
class MethodRef:
    """内存中对某一脚本文件内方法体的引用（非合并文本）。"""

    source_path: "str"
    label: "str"
    block: "MethodBlock"


@dataclass
class ScriptWorkspace:
    """
    多文件脚本工作区：各文件独立保留 AST，#CALL 仅在内存中解析引用。

    原则（SCR-050）：绝不拼接、改写、落盘合并脚本文本。
    """

    scripts: "dict[str, NpcScript]" = field(default_factory=dict)
    main_key: "str" = MAIN_KEY

    @classmethod
    def from_editor(cls, source: "str") -> "ScriptWorkspace":
        ws = cls()
        ws.scripts[MAIN_KEY] = parse_npc_script(source, source_path=None)
        return ws

    def register_path(self, path: "str", source: "str") -> "NpcScript":
        normalized_path = normalize_call_path(path)
        key = _normalize_path(normalized_path)
        script = parse_npc_script(source, source_path=normalized_path)
        self.scripts[key] = script
        return script

    def get(self, path: "str | None" = None) -> "NpcScript | None":
        if path is None:
            return self.scripts.get(self.main_key)
        return self.scripts.get(_normalize_path(path))

    def resolve_label(self, label: "str", *, context_path: "str | None") -> "MethodRef | None":
        label = _normalize_label(label)
        keys: list[str] = []
        if context_path is not None:
            keys.append(_normalize_path(context_path))
        if self.main_key not in keys:
            keys.append(self.main_key)
        searched: set[str] = set()

        def find_in_key(key: str) -> MethodRef | None:
            searched.add(key)
            script = self.scripts.get(key)
            if script is None:
                return None
            block = script.method_index.get(label)
            if block is None:
                lower_label = label.lower()
                for method_label, candidate in script.method_index.items():
                    if method_label.lower() == lower_label:
                        block = candidate
                        break
            if block is None:
                return None
            return MethodRef(key, block.label, block)

        for key in keys:
            ref = find_in_key(key)
            if ref is not None:
                return ref
        for key in self.scripts:
            if key in searched:
                continue
            ref = find_in_key(key)
            if ref is not None:
                return ref
        return None

    def resolve_call(self, file_path: "str", label: "str") -> "MethodRef | None":
        key = _normalize_path(file_path)
        script = self.scripts.get(key)
        if script is None:
            return None
        normalized_label = _normalize_label(label)
        block = script.method_index.get(normalized_label)
        if block is None:
            lower_label = normalized_label.lower()
            for method_label, candidate in script.method_index.items():
                if method_label.lower() == lower_label:
                    block = candidate
                    break
        if block is None:
            lower_label = normalized_label.lower()
            matches = [
                (method_label, candidate)
                for method_label, candidate in script.method_index.items()
                if lower_label.startswith(method_label.lower())
            ]
            if matches:
                _method_label, block = max(matches, key=lambda item: len(item[0]))
        if block is None:
            return None
        return MethodRef(key, block.label, block)

    def load_call_dependencies(self, loader: "FileLoader", *, max_rounds: "int" = 16) -> "list[str]":
        """
        按 #CALL 引用从 loader 读取外部文件，解析后登记到工作区（只读内存）。
        不修改任何已登记脚本的 source 字段。
        """
        loaded: list[str] = []
        for _ in range(max_rounds):
            pending: list[tuple[str, str]] = []
            for script in self.scripts.values():
                for call in script.all_calls():
                    key = _normalize_path(call.file_path)
                    if key not in self.scripts:
                        pending.append((call.file_path, key))
            if not pending:
                break
            for original_path, key in pending:
                if key in self.scripts:
                    continue
                text = loader(original_path)
                if text is None:
                    continue
                self.register_path(original_path, text)
                loaded.append(original_path)
        return loaded

    def all_source_paths(self) -> "list[str]":
        return [path for path in self.scripts if path != MAIN_KEY]
