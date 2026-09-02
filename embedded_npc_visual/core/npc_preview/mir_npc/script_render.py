from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from ..npc_dialog_core import NpcDialog, _parse_npc_dialog_parts, parse_mov_assignments
from .call_path import normalize_call_path
from .script_model import ActKind, MethodBlock, NpcScript, ScriptSection
from .script_parser import parse_npc_script

FileLoader = Callable[[str], Optional[str]]


def default_file_loader(base_dir: Path | None) -> FileLoader:
    """从 Envir 根目录加载 #CALL 引用文件。"""

    def load(relative_path: str) -> str | None:
        if base_dir is None:
            return None
        normalized = normalize_call_path(relative_path)
        candidate = base_dir / normalized
        if candidate.is_file():
            return candidate.read_text(encoding="gb18030", errors="replace")
        return None

    return load


def _section_source(section: ScriptSection, method: MethodBlock) -> str:
    parts: list[str] = []
    if section.if_lines:
        marker = "#OR" if section.if_mode == "or" else "#IF"
        if section.if_param:
            marker = f"{marker}({section.if_param})"
        parts.append(marker + "\n")
        parts.extend(line + "\n" for line in section.if_lines)

    if section.act:
        parts.append("#ACT\n")
        parts.extend(stmt.raw + "\n" for stmt in section.act)

    if section.say_lines:
        parts.append("#SAY\n")
        parts.extend(section.say_lines)
    elif section.say_text:
        parts.append("#SAY\n")
        parts.append(section.say_text)

    if parts:
        return "".join(parts)
    return method.preamble_text()


def _method_render_parts(method: MethodBlock) -> list[tuple[str, ScriptSection | None, str]]:
    """返回 (page_label, section, source) 列表，供渲染 #SAY。"""
    parts: list[tuple[str, ScriptSection | None, str]] = []
    say_sections = [section for section in method.sections if section.has_say]

    if not say_sections:
        if method.preamble_lines:
            parts.append((method.label, None, "#SAY\n" + "".join(method.preamble_lines)))
        return parts

    for index, section in enumerate(say_sections, start=1):
        label = method.label if index == 1 else f"{method.label}{index}"
        parts.append((label, section, _section_source(section, method)))
    return parts


def script_to_dialog_pages(
    script: NpcScript,
    *,
    global_mov: dict[str, str] | None = None,
) -> list[NpcDialog]:
    """从脚本 AST 生成可渲染的 NpcDialog 页列表（仅含 #SAY 可视内容）。"""
    global_mov = global_mov or parse_mov_assignments(script.source)
    pages: list[NpcDialog] = []
    used_labels: set[str] = set()

    for method in script.methods:
        for block in method.iter_methods_depth_first():
            block_mov = parse_mov_assignments(
                "\n".join(
                    stmt.raw
                    for section in block.sections
                    for stmt in section.act
                    if stmt.kind == ActKind.MOV
                )
            )
            if block.preamble_lines:
                block_mov.update(parse_mov_assignments("\n".join(block.preamble_lines)))
            for label, section, source in _method_render_parts(block):
                unique = label
                if unique in used_labels:
                    suffix = 2
                    while f"{label}{suffix}" in used_labels:
                        suffix += 1
                    unique = f"{label}{suffix}"
                used_labels.add(unique)

                span = section.span if section else block.span
                dialog = _parse_npc_dialog_parts(
                    source,
                    unique,
                    span.line_start,
                    span.line_end,
                    local_mov_values=block_mov,
                    global_mov_values=global_mov,
                )
                pages.append(dialog)

    return pages


def resolve_call_graph(script: NpcScript, loader: FileLoader, *, _visited: set[tuple[str, str]] | None = None) -> dict[str, NpcScript]:
    """
    展开 #CALL 依赖，返回 {文件路径: NpcScript}。
    同一文件可被多个方法 #CALL，类似公共接口。
    """
    visited = _visited or set()
    out: dict[str, NpcScript] = {}

    for call in script.all_calls():
        key = (call.file_path, call.label)
        if key in visited:
            continue
        visited.add(key)

        text = loader(call.file_path)
        if text is None:
            continue

        called = parse_npc_script(text, source_path=call.file_path)
        out[call.file_path] = called
        out.update(resolve_call_graph(called, loader, _visited=visited))

    return out


def find_call_target(script: NpcScript, file_path: str, label: str) -> MethodBlock | None:
    """在已解析脚本中查找 #CALL 目标方法。"""
    label = label if label.startswith("@") else f"@{label}"
    return script.method_index.get(label)
