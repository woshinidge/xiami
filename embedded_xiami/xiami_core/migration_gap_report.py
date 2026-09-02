from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ONEBOT_PREFIXES = (
    "send_",
    "get_",
    "set_",
    "delete_",
    "upload_",
    "download_",
    "create_",
    "mark_",
    "can_",
)

ACTION_ALIASES = {
    "get_version": "get_version_info",
    "set_group_notice": "_send_group_notice",
    "get_group_notice": "_get_group_notice",
}


@dataclass(frozen=True)
class Evidence:
    path: str
    line: int
    kind: str


@dataclass
class ApiInventory:
    public_methods: set[str] = field(default_factory=set)
    action_names: set[str] = field(default_factory=set)
    evidence: dict[str, list[Evidence]] = field(default_factory=lambda: defaultdict(list))

    @property
    def names(self) -> set[str]:
        return self.public_methods | self.action_names

    def add(self, name: str, evidence: Evidence, *, method: bool = False, action: bool = False) -> None:
        if method:
            self.public_methods.add(name)
        if action:
            self.action_names.add(name)
        self.evidence[name].append(evidence)


@dataclass(frozen=True)
class MigrationGapReport:
    old_count: int
    covered_count: int
    missing: tuple[str, ...]
    covered: tuple[str, ...]
    old_evidence: dict[str, tuple[Evidence, ...]]
    new_names: tuple[str, ...]


def build_report(project_root: Path | None = None) -> MigrationGapReport:
    root = project_root or Path.cwd()
    old_root = root / "xiami_onebot"
    new_roots = (root / "xiami_core", root / "xiami_plugins")
    old_inventory = _scan_old_inventory(old_root)
    new_inventory = _scan_new_inventory(new_roots)
    new_names = new_inventory.names
    covered: list[str] = []
    missing: list[str] = []
    for name in sorted(old_inventory.names):
        if _is_covered(name, new_names):
            covered.append(name)
        else:
            missing.append(name)
    evidence = {name: tuple(items[:5]) for name, items in old_inventory.evidence.items()}
    return MigrationGapReport(
        old_count=len(old_inventory.names),
        covered_count=len(covered),
        missing=tuple(missing),
        covered=tuple(covered),
        old_evidence=evidence,
        new_names=tuple(sorted(new_names)),
    )


def format_report(report: MigrationGapReport) -> str:
    lines = [
        "# Xiami migration gap report",
        "",
        f"Old OneBot-like APIs observed: {report.old_count}",
        f"Covered by Xiami v1 adapters/plugins: {report.covered_count}",
        f"Missing or not explicitly wrapped: {len(report.missing)}",
        "",
    ]
    if report.missing:
        lines.append("## Missing APIs")
        for name in report.missing:
            lines.append(f"- {name}")
            for evidence in report.old_evidence.get(name, ())[:3]:
                lines.append(f"  - {evidence.path}:{evidence.line} ({evidence.kind})")
        lines.append("")
    else:
        lines.append("## Missing APIs")
        lines.append("- none")
        lines.append("")
    lines.append("## Next acceleration path")
    if report.missing:
        lines.append("- Add the missing names to `OneBotHttpClient`, `PluginContext`, or `LegacyBot` in batches.")
        lines.append("- Then rerun `python -m xiami_core.migration_gap_report` and `python -m xiami_core.mvp_smoke`.")
    else:
        lines.append("- OneBot wrapper coverage is not the current bottleneck; move to plugin-specific behavior and UI verification.")
    return "\n".join(lines)


def main() -> int:
    report = build_report(Path.cwd())
    print(format_report(report))
    return 0


def _scan_old_inventory(old_root: Path) -> ApiInventory:
    inventory = ApiInventory()
    old_client = old_root / "onebot_client.py"
    wrapper_names = {(name, line) for name, line in _public_methods(old_client) if _looks_like_onebot_name(name)}
    wrapper_name_set = {name for name, _line in wrapper_names}
    for name, line in wrapper_names:
        if _looks_like_onebot_name(name):
            inventory.add(name, Evidence(_rel(old_client), line, "old-wrapper"), method=True)
    for path in _python_files(old_root):
        tree = _parse(path)
        if tree is None:
            continue
        for name, line, kind in _called_onebot_names(tree, wrapper_names=wrapper_name_set, strict_receiver=True):
            inventory.add(name, Evidence(_rel(path), line, kind), method=name in wrapper_name_set, action=True)
    return inventory


def _scan_new_inventory(roots: Iterable[Path]) -> ApiInventory:
    inventory = ApiInventory()
    for root in roots:
        for path in _python_files(root):
            tree = _parse(path)
            if tree is None:
                continue
            for name, line in _public_methods(path):
                if _looks_like_onebot_name(name):
                    inventory.add(name, Evidence(_rel(path), line, "new-wrapper"), method=True)
            for name, line, kind in _called_onebot_names(tree, wrapper_names=set(), strict_receiver=False):
                inventory.add(name, Evidence(_rel(path), line, kind), action=True)
    return inventory


def _public_methods(path: Path) -> set[tuple[str, int]]:
    tree = _parse(path)
    if tree is None:
        return set()
    result: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_"):
            result.add((node.name, node.lineno))
    return result


def _called_onebot_names(tree: ast.AST, wrapper_names: set[str], *, strict_receiver: bool) -> list[tuple[str, int, str]]:
    result: list[tuple[str, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
            if strict_receiver and not _is_onebot_receiver(func.value):
                continue
            if name in wrapper_names or (not strict_receiver and _looks_like_onebot_name(name)):
                result.append((name, node.lineno, "call"))
            if name in {"call", "call_api", "call_action", "call_onebot", "onebot_call"}:
                action = _first_string_arg(node)
                if action:
                    result.append((action, node.lineno, "action-string"))
        elif isinstance(func, ast.Name) and func.id in {"call_onebot", "onebot_call"}:
            action = _first_string_arg(node)
            if action:
                result.append((action, node.lineno, "action-string"))
    return result


def _is_onebot_receiver(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "onebot"
    if isinstance(node, ast.Attribute):
        return node.attr == "onebot" or _is_onebot_receiver(node.value)
    return False


def _first_string_arg(node: ast.Call) -> str:
    if not node.args:
        return ""
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value.strip()
    return ""


def _looks_like_onebot_name(name: str) -> bool:
    if name.startswith(ONEBOT_PREFIXES):
        return True
    return any(token in name for token in ("_msg", "_message", "_notice", "_request", "_group", "_friend", "_file"))


def _is_covered(name: str, new_names: set[str]) -> bool:
    if name in new_names:
        return True
    alias = ACTION_ALIASES.get(name)
    if alias and alias in new_names:
        return True
    reverse_alias = {value: key for key, value in ACTION_ALIASES.items()}
    alias = reverse_alias.get(name)
    return bool(alias and alias in new_names)


def _python_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and ".venv" not in path.parts and "node_modules" not in path.parts
    ]


def _parse(path: Path) -> ast.AST | None:
    if not path.exists():
        return None
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    except SyntaxError:
        return None


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
