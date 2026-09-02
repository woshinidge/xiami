from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from xiami_core.storage.paths import PROJECT_ROOT


@dataclass(frozen=True)
class NativeRewriteItem:
    plugin_id: str
    path: str
    status: str
    reasons: tuple[str, ...] = ()
    uses_xiami_compat_helpers: bool = False
    commands: tuple[str, ...] = ()


@dataclass(frozen=True)
class NativeRewriteAudit:
    total: int
    native: int
    native_with_helpers: int
    legacy_or_compat: int
    items: tuple[NativeRewriteItem, ...] = field(default_factory=tuple)

    @property
    def native_percent(self) -> int:
        if self.total <= 0:
            return 100
        return round(self.native / self.total * 100)


def audit_native_rewrite(plugin_root: Path | None = None) -> NativeRewriteAudit:
    root = plugin_root or PROJECT_ROOT / "xiami_plugins"
    items: list[NativeRewriteItem] = []
    if not root.exists():
        return NativeRewriteAudit(0, 0, 0, 0, ())
    for path in sorted(root.iterdir(), key=lambda item: item.name.lower()):
        if path.name.startswith("__"):
            continue
        if path.is_dir():
            plugin_file = path / "plugin.py"
            if plugin_file.exists():
                items.append(_audit_plugin_file(path.name, plugin_file, directory_plugin=True))
            continue
        if path.suffix == ".py":
            items.append(_legacy_file_item(path))
    native = sum(1 for item in items if item.status == "native")
    native_with_helpers = sum(1 for item in items if item.uses_xiami_compat_helpers)
    legacy_or_compat = len(items) - native
    return NativeRewriteAudit(
        total=len(items),
        native=native,
        native_with_helpers=native_with_helpers,
        legacy_or_compat=legacy_or_compat,
        items=tuple(items),
    )


def format_native_rewrite_audit(audit: NativeRewriteAudit) -> str:
    lines = [
        "# Xiami native rewrite audit",
        "",
        f"Plugins: {audit.total}",
        f"Xiami native: {audit.native}/{audit.total} ({audit.native_percent}%)",
        f"Native using Xiami compat helpers: {audit.native_with_helpers}",
        f"Legacy/compat samples still present: {audit.legacy_or_compat}",
        "",
        "## Non-native items",
    ]
    non_native = [item for item in audit.items if item.status != "native"]
    if not non_native:
        lines.append("- none")
    for item in non_native:
        reason = "; ".join(item.reasons) if item.reasons else item.status
        lines.append(f"- {item.plugin_id}: {item.status}; {reason}; {item.path}")
    lines.extend(["", "## Native items"])
    for item in [item for item in audit.items if item.status == "native"]:
        helper = " + compat_helpers" if item.uses_xiami_compat_helpers else ""
        command_text = f" commands={','.join(item.commands[:5])}" if item.commands else ""
        lines.append(f"- {item.plugin_id}: native{helper}{command_text}")
    return "\n".join(lines)


def native_rewrite_audit_to_dict(audit: NativeRewriteAudit) -> dict[str, Any]:
    return {
        "total": audit.total,
        "native": audit.native,
        "native_percent": audit.native_percent,
        "native_with_helpers": audit.native_with_helpers,
        "legacy_or_compat": audit.legacy_or_compat,
        "items": [asdict(item) for item in audit.items],
    }


def _audit_plugin_file(plugin_id: str, plugin_file: Path, *, directory_plugin: bool) -> NativeRewriteItem:
    text = plugin_file.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return NativeRewriteItem(plugin_id, str(plugin_file), "invalid", (f"syntax error: {exc}",))
    assigned = _assigned_constants(tree)
    mode = str(assigned.get("PLUGIN_MODE") or "").lower()
    capabilities = _string_list(assigned.get("PLUGIN_CAPABILITIES"))
    commands = tuple(sorted(_decorated_commands(tree)))
    uses_helpers = "xiami_core.plugins.compat" in text
    reasons: list[str] = []
    status = "native"
    if not directory_plugin:
        status = "legacy_file"
        reasons.append("root-level .py plugin, not xiami_plugins/<plugin_id>/plugin.py")
    if mode == "legacy":
        status = "legacy_bridge"
        reasons.append("PLUGIN_MODE='legacy'")
    if any(item.startswith("legacy:") for item in capabilities):
        status = "legacy_bridge"
        reasons.append("legacy capability marker")
    if _has_legacy_handler_signature(tree):
        status = "legacy_bridge"
        reasons.append("legacy bot/event handler signature")
    if status == "native" and "PLUGIN_ID" not in assigned:
        reasons.append("missing PLUGIN_ID")
    return NativeRewriteItem(
        plugin_id=str(assigned.get("PLUGIN_ID") or plugin_id),
        path=str(plugin_file),
        status=status,
        reasons=tuple(reasons),
        uses_xiami_compat_helpers=uses_helpers,
        commands=commands,
    )


def _legacy_file_item(plugin_file: Path) -> NativeRewriteItem:
    return _audit_plugin_file(plugin_file.stem, plugin_file, directory_plugin=False)


def _assigned_constants(tree: ast.Module) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.startswith("PLUGIN_"):
                values[target.id] = _literal_value(node.value)
    return values


def _literal_value(node: ast.AST) -> Any:
    try:
        return ast.literal_eval(node)
    except Exception:
        return None


def _string_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, (list, tuple, set)):
        return tuple(str(item) for item in value)
    return ()


def _decorated_commands(tree: ast.Module) -> set[str]:
    commands: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            name = _call_name(decorator.func)
            if name not in {"on_command", "on_keyword", "on_regex", "on_command_hook"}:
                continue
            if decorator.args:
                value = _literal_value(decorator.args[0])
                if isinstance(value, str):
                    commands.add(value)
            for keyword in decorator.keywords:
                if keyword.arg == "aliases":
                    commands.update(_string_list(_literal_value(keyword.value)))
    return {command for command in commands if command}


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _has_legacy_handler_signature(tree: ast.Module) -> bool:
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        args = [arg.arg for arg in node.args.args]
        if node.name in {"handle_message", "on_message", "on_event"} and args[:2] == ["bot", "event"]:
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit whether Xiami plugins are native rewrites.")
    parser.add_argument("--plugin-root", type=Path, default=PROJECT_ROOT / "xiami_plugins")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()
    audit = audit_native_rewrite(args.plugin_root)
    if args.format == "json":
        print(json.dumps(native_rewrite_audit_to_dict(audit), ensure_ascii=False, indent=2))
    else:
        print(format_native_rewrite_audit(audit))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
