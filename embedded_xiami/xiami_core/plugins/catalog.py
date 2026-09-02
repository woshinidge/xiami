from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from xiami_core.plugins.loader import LoadedPlugin, PluginLoader


@dataclass(frozen=True)
class PluginCatalogItem:
    plugin_id: str
    name: str
    version: str
    description: str
    enabled: bool
    healthy: bool
    category: str
    command_count: int
    capability_count: int
    admin_items: int
    package_path: str


def build_plugin_catalog(loader: PluginLoader) -> list[PluginCatalogItem]:
    return [catalog_item(plugin) for plugin in sorted(loader.plugins, key=lambda item: item.id)]


def catalog_item(plugin: LoadedPlugin) -> PluginCatalogItem:
    return PluginCatalogItem(
        plugin_id=plugin.id,
        name=plugin.name,
        version=plugin.version,
        description=plugin.description,
        enabled=plugin.enabled,
        healthy=not bool(plugin.error),
        category=_category(plugin),
        command_count=len(plugin.commands),
        capability_count=len(plugin.capabilities),
        admin_items=len(plugin.admin_schema),
        package_path=str(_plugin_package_path(plugin.path)),
    )


def format_plugin_catalog(items: list[PluginCatalogItem]) -> str:
    lines = ["# Xiami plugin catalog", ""]
    if not items:
        lines.append("- no plugins loaded")
        return "\n".join(lines)
    for item in items:
        state = "enabled" if item.enabled else "disabled"
        health = "healthy" if item.healthy else "error"
        version = f" v{item.version}" if item.version else ""
        lines.append(
            f"- {item.plugin_id}: {item.name}{version} [{item.category}] "
            f"{state}/{health}, commands={item.command_count}, admin={item.admin_items}"
        )
    return "\n".join(lines)


def _category(plugin: LoadedPlugin) -> str:
    tokens = {item.lower() for item in plugin.capabilities}
    commands = set(plugin.commands)
    if any(item.startswith("ai:") for item in tokens):
        return "AI"
    if any("knowledge" in item for item in tokens) or {"查知识", "添加知识"} & commands:
        return "Knowledge"
    if "onebot" in plugin.id.lower() or any("onebot" in item for item in tokens) or {"OneBot状态", "列群"} & commands:
        return "OneBot"
    if {"禁言", "解禁", "踢"} & commands:
        return "Moderation"
    if plugin.admin_schema:
        return "Admin"
    if plugin.commands:
        return "Command"
    return "Utility"


def _plugin_package_path(path: Path) -> Path:
    if path.is_file():
        return path
    return path / "plugin.py"
