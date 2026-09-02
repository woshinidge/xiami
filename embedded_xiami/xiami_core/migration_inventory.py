from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from xiami_core.plugins.legacy_file import looks_like_legacy_file_plugin


MVP_COMMANDS = [
    "菜单",
    "帮助",
    "命令",
    "功能",
    "机器人菜单",
    "加管理员",
    "删管理员",
    "加全局管理员",
    "删全局管理员",
    "管理员列表",
    "禁言",
    "解禁",
    "踢",
    "清理本群黑",
    "清理黑名单",
    "清本群黑",
    "加黑名单",
    "删黑名单",
    "加白名单",
    "删白名单",
    "加全局黑名单",
    "删全局黑名单",
    "加全局白名单",
    "删全局白名单",
    "加违禁词",
    "删违禁词",
    "加全局违禁词",
    "删全局违禁词",
    "出题",
    "答题",
    "答案",
    "兑换卡密",
    "绑定",
    "解绑",
    "我的绑定",
    "邀请排行",
    "加回答",
    "加精确回答",
    "删回答",
    "回答列表",
    "预览知识",
    "知识导入",
    "知识添加",
    "知识搜索",
    "知识统计",
    "问",
    "AI状态",
    "AI试连",
    "AI流式",
    "AI审计",
    "AI供应商",
]


@dataclass
class PluginInventory:
    plugin_id: str
    name: str
    path: str
    commands: set[str] = field(default_factory=set)
    capabilities: set[str] = field(default_factory=set)


def main() -> int:
    project_root = Path.cwd()
    inventories = inspect_plugins(project_root / "xiami_plugins")
    command_to_plugin: dict[str, str] = {}
    for item in inventories:
        for command in item.commands:
            command_to_plugin.setdefault(command, item.plugin_id)

    missing = [command for command in MVP_COMMANDS if command not in command_to_plugin]
    old_commands = inspect_old_command_router(project_root / "xiami_onebot" / "command_router.py")
    old_missing = sorted(command for command in old_commands if command not in command_to_plugin)

    print("# Xiami migration inventory")
    print(f"Plugins: {len(inventories)}")
    print(f"MVP commands: {len(MVP_COMMANDS)}")
    print(f"Covered: {len(MVP_COMMANDS) - len(missing)}")
    print(f"Missing: {len(missing)}")
    print()
    print("## Covered MVP commands")
    for command in MVP_COMMANDS:
        if command in command_to_plugin:
            print(f"- {command}: {command_to_plugin[command]}")
    if missing:
        print()
        print("## Missing MVP commands")
        for command in missing:
            print(f"- {command}")
    print()
    print("## Old command router audit")
    print(f"Old router commands detected: {len(old_commands)}")
    print(f"Missing old router commands: {len(old_missing)}")
    for command in old_missing[:80]:
        print(f"- {command}")
    if len(old_missing) > 80:
        print(f"- ... {len(old_missing) - 80} more")
    print()
    print("## Plugins")
    for item in sorted(inventories, key=lambda entry: entry.plugin_id):
        commands = ", ".join(sorted(item.commands)) or "-"
        capabilities = ", ".join(sorted(item.capabilities)) or "-"
        print(f"- {item.plugin_id}: commands=[{commands}] capabilities=[{capabilities}]")
    return 0 if not missing else 1


def inspect_plugins(plugin_root: Path) -> list[PluginInventory]:
    if not plugin_root.exists():
        return []
    result: list[PluginInventory] = []
    for plugin_dir in sorted(path for path in plugin_root.iterdir() if (path / "plugin.py").exists()):
        plugin_file = plugin_dir / "plugin.py"
        try:
            tree = ast.parse(plugin_file.read_text(encoding="utf-8"), filename=str(plugin_file))
        except (OSError, SyntaxError):
            continue
        result.append(_inspect_tree(plugin_dir, tree))
    for plugin_file in sorted(path for path in plugin_root.glob("*.py") if looks_like_legacy_file_plugin(path)):
        try:
            tree = ast.parse(plugin_file.read_text(encoding="utf-8"), filename=str(plugin_file))
        except (OSError, SyntaxError):
            continue
        result.append(_inspect_legacy_file(plugin_file, tree))
    return result


def inspect_old_command_router(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError):
        return set()
    commands: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "startswith":
            if node.args:
                commands.update(_command_strings(node.args[0]))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "commands":
                    commands.update(_first_string_from_tuples(node.value))
        elif isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id in {"text", "message"}:
            for comparator in node.comparators:
                commands.update(_command_strings(comparator))
    return {command for command in commands if _looks_like_command(command)}


def _inspect_tree(plugin_dir: Path, tree: ast.Module) -> PluginInventory:
    plugin_id = plugin_dir.name
    name = plugin_id
    commands: set[str] = set()
    capabilities: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            plugin_id = _read_assignment(node, "PLUGIN_ID") or plugin_id
            name = _read_assignment(node, "PLUGIN_NAME") or name
            if _assigns(node, {"PLUGIN_COMMANDS", "COMMANDS"}):
                commands.update(_command_strings(node.value))
            if _assigns(node, {"PLUGIN_CAPABILITIES", "CAPABILITIES"}):
                capabilities.update(_command_strings(node.value))
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                commands.update(_commands_from_decorator(decorator))
    return PluginInventory(plugin_id=plugin_id, name=name, path=str(plugin_dir), commands=commands, capabilities=capabilities)


def _inspect_legacy_file(plugin_file: Path, tree: ast.Module) -> PluginInventory:
    plugin_id = plugin_file.stem
    name = plugin_id
    hooks: set[str] = set()
    services: set[str] = set()
    admin_path = ""
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not _assigns(node, {"plugin_spec"}):
            continue
        try:
            spec = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
        if not isinstance(spec, dict):
            continue
        plugin_id = str(spec.get("key") or plugin_id)
        name = str(spec.get("name") or name)
        hooks.update(str(item) for item in spec.get("hooks", ()) if str(item).strip())
        services.update(str(item) for item in spec.get("services", ()) if str(item).strip())
        admin_path = str(spec.get("admin_path") or admin_path)
    capabilities = {"legacy-file-plugin"}
    if hooks:
        capabilities.add("legacy-file-hooks:" + ",".join(sorted(hooks)))
    if "admin" in hooks:
        capabilities.add("legacy-admin-hook")
    if admin_path:
        capabilities.add("legacy-admin-path:" + admin_path)
    for service in sorted(services):
        capabilities.add("legacy-service:" + service)
    return PluginInventory(plugin_id=plugin_id, name=name, path=str(plugin_file), capabilities=capabilities)


def _read_assignment(node: ast.Assign, name: str) -> str:
    if not _assigns(node, {name}):
        return ""
    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        return node.value.value
    return ""


def _assigns(node: ast.Assign, names: set[str]) -> bool:
    return any(isinstance(target, ast.Name) and target.id in names for target in node.targets)


def _commands_from_decorator(decorator: ast.AST) -> set[str]:
    if not isinstance(decorator, ast.Call):
        return set()
    func_name = ""
    if isinstance(decorator.func, ast.Name):
        func_name = decorator.func.id
    elif isinstance(decorator.func, ast.Attribute):
        func_name = decorator.func.attr
    if func_name != "on_command":
        return set()
    commands: set[str] = set()
    if decorator.args:
        commands.update(_command_strings(decorator.args[0]))
    for keyword in decorator.keywords:
        if keyword.arg == "aliases":
            commands.update(_command_strings(keyword.value))
    return commands


def _command_strings(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        values: set[str] = set()
        for element in node.elts:
            values.update(_command_strings(element))
        return values
    return set()


def _first_string_from_tuples(node: ast.AST) -> set[str]:
    if not isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return set()
    values: set[str] = set()
    for element in node.elts:
        if isinstance(element, (ast.Tuple, ast.List)) and element.elts:
            values.update(_command_strings(element.elts[0]))
    return values


def _looks_like_command(value: str) -> bool:
    command = value.strip()
    if not command:
        return False
    if len(command) > 32:
        return False
    if command.startswith(("http://", "https://", "{", "[")):
        return False
    return "\n" not in command and "\r" not in command


if __name__ == "__main__":
    raise SystemExit(main())
