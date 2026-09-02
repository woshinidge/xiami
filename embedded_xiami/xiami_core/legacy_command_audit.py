from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from xiami_core.migration_inventory import inspect_plugins


@dataclass(frozen=True)
class LegacyCommandAudit:
    legacy_commands: tuple[str, ...]
    plugin_commands: tuple[str, ...]
    missing_commands: tuple[str, ...]

    @property
    def covered_commands(self) -> int:
        return len(self.legacy_commands) - len(self.missing_commands)


def audit_legacy_commands(project_root: Path | None = None) -> LegacyCommandAudit:
    root = project_root or Path.cwd()
    legacy_commands = extract_legacy_commands(root / "xiami_onebot" / "command_router.py")
    plugin_commands: set[str] = set()
    for item in inspect_plugins(root / "xiami_plugins"):
        plugin_commands.update(item.commands)
    missing = tuple(command for command in legacy_commands if command not in plugin_commands)
    return LegacyCommandAudit(
        legacy_commands=tuple(sorted(legacy_commands)),
        plugin_commands=tuple(sorted(plugin_commands)),
        missing_commands=tuple(sorted(missing)),
    )


def extract_legacy_commands(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return set()
    visitor = _LegacyCommandVisitor()
    visitor.visit(tree)
    return {command for command in visitor.commands if _looks_like_command(command)}


def format_legacy_command_audit(report: LegacyCommandAudit) -> str:
    lines = [
        "# Legacy command audit",
        "",
        f"Legacy commands: {len(report.legacy_commands)}",
        f"Covered by Xiami plugins: {report.covered_commands}/{len(report.legacy_commands)}",
        "",
        "## Missing legacy commands",
    ]
    if report.missing_commands:
        lines.extend(f"- {command}" for command in report.missing_commands)
    else:
        lines.append("- none")
    return "\n".join(lines)


class _LegacyCommandVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.commands: set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute) and node.func.attr == "startswith" and node.args:
            self.commands.update(_string_values(node.args[0]))
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        for value in [node.left, *node.comparators]:
            self.commands.update(_string_values(value))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        target_names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if "commands" in target_names:
            self.commands.update(_first_tuple_strings(node.value))
        self.generic_visit(node)


def _first_tuple_strings(node: ast.AST) -> set[str]:
    values: set[str] = set()
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for item in node.elts:
            if isinstance(item, (ast.List, ast.Tuple)) and item.elts:
                values.update(_string_values(item.elts[0]))
    return values


def _string_values(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        values: set[str] = set()
        for item in node.elts:
            values.update(_string_values(item))
        return values
    return set()


def _looks_like_command(value: str) -> bool:
    command = value.strip()
    if command != value or not command:
        return False
    if len(command) > 20:
        return False
    if any(char.isspace() for char in command):
        return False
    if any(separator in command for separator in ("：", ":", "/", "。", "，", ",")):
        return False
    if not any("\u4e00" <= char <= "\u9fff" for char in command):
        return False
    return True


def main() -> int:
    report = audit_legacy_commands(Path.cwd())
    print(format_legacy_command_audit(report))
    return 0 if not report.missing_commands else 1


if __name__ == "__main__":
    raise SystemExit(main())
