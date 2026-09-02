from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xiami_core.plugins.loader import LoadedPlugin, PluginLoader


@dataclass(frozen=True)
class PluginAdminOperation:
    ok: bool
    message: str
    data: dict[str, Any] | None = None


class PluginAdminService:
    def __init__(self, loader: PluginLoader) -> None:
        self.loader = loader

    def snapshot(self, plugin_id: str, *, include_values: bool = False) -> dict[str, Any]:
        plugin = self._plugin(plugin_id)
        items = [self._item_snapshot(plugin, item, include_values=include_values) for item in plugin.admin_schema]
        return {
            "plugin_id": plugin.id,
            "plugin_name": plugin.name,
            "version": plugin.version,
            "enabled": plugin.enabled,
            "items": items,
        }

    def export_snapshot(self, plugin_id: str, path: Path, *, include_values: bool = True) -> PluginAdminOperation:
        snapshot = self.snapshot(plugin_id, include_values=include_values)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        return PluginAdminOperation(True, f"插件后台状态已导出：{path}", snapshot)

    def import_snapshot(self, plugin_id: str, path: Path, *, dry_run: bool = False) -> PluginAdminOperation:
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return PluginAdminOperation(False, f"插件后台状态导入失败：{exc}", {"path": str(path)})
        if not isinstance(snapshot, dict):
            return PluginAdminOperation(False, "插件后台状态导入失败：快照格式不是 JSON 对象", {"path": str(path)})
        snapshot_plugin_id = str(snapshot.get("plugin_id") or "").strip()
        if snapshot_plugin_id and snapshot_plugin_id != plugin_id:
            return PluginAdminOperation(
                False,
                f"插件后台状态导入失败：快照属于 {snapshot_plugin_id}，当前选择 {plugin_id}",
                {"plugin_id": plugin_id, "snapshot_plugin_id": snapshot_plugin_id},
            )
        raw_items = snapshot.get("items")
        if not isinstance(raw_items, list):
            return PluginAdminOperation(False, "插件后台状态导入失败：快照缺少 items 列表", {"path": str(path)})

        applied: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                skipped.append({"id": "", "reason": "管理项不是 JSON 对象"})
                continue
            item_id = self._snapshot_item_id(raw_item)
            if not item_id:
                skipped.append({"id": "", "reason": "管理项缺少 id/state_key/config_key"})
                continue
            if "value" not in raw_item:
                skipped.append({"id": item_id, "reason": "管理项不包含 value"})
                continue
            try:
                plugin, item = self._plugin_item(plugin_id, item_id)
            except KeyError:
                skipped.append({"id": item_id, "reason": "当前插件 schema 中不存在该管理项"})
                continue
            if dry_run:
                applied.append({"id": item_id, "label": str(item.get("label") or item_id), "dry_run": True})
                continue
            result = self.set_item(plugin_id, item_id, raw_item["value"])
            if result.ok:
                applied.append({"id": item_id, "label": str(item.get("label") or item_id)})
            else:
                skipped.append({"id": item_id, "reason": result.message})

        data = {
            "plugin_id": plugin_id,
            "path": str(path),
            "dry_run": dry_run,
            "applied": applied,
            "skipped": skipped,
        }
        if not applied:
            return PluginAdminOperation(False, "插件后台状态导入失败：没有可恢复的管理项", data)
        action = "导入预检通过" if dry_run else "已导入"
        message = f"插件后台状态{action}：{len(applied)} 项"
        if skipped:
            message += f"，跳过 {len(skipped)} 项"
        return PluginAdminOperation(True, message, data)

    def get_item(self, plugin_id: str, item_id: str) -> PluginAdminOperation:
        plugin, item = self._plugin_item(plugin_id, item_id)
        return PluginAdminOperation(True, "OK", self._item_snapshot(plugin, item, include_values=True))

    def set_item(self, plugin_id: str, item_id: str, value: Any) -> PluginAdminOperation:
        plugin, item = self._plugin_item(plugin_id, item_id)
        if plugin.context is None:
            return PluginAdminOperation(False, "插件上下文不可用")
        state_key = str(item.get("state_key") or "").strip()
        config_key = str(item.get("config_key") or "").strip()
        runtime_key = str(item.get("runtime_key") or "").strip()
        if runtime_key:
            return PluginAdminOperation(False, f"运行时管理项只读：{runtime_key}")
        if state_key:
            plugin.context.set_state(state_key, value)
            return PluginAdminOperation(True, f"状态已写入：{state_key}", self._item_snapshot(plugin, item, include_values=True))
        if config_key:
            config = dict(self.loader.user_config(plugin.id))
            config[config_key] = value
            self.loader.save_user_config(plugin.id, config)
            plugin.config[config_key] = value
            if plugin.context:
                plugin.context.config[config_key] = value
            return PluginAdminOperation(True, f"配置已写入：{config_key}", self._item_snapshot(plugin, item, include_values=True))
        return PluginAdminOperation(False, "管理项未绑定 state_key 或 config_key")

    def delete_item(self, plugin_id: str, item_id: str) -> PluginAdminOperation:
        plugin, item = self._plugin_item(plugin_id, item_id)
        if plugin.context is None:
            return PluginAdminOperation(False, "插件上下文不可用")
        state_key = str(item.get("state_key") or "").strip()
        config_key = str(item.get("config_key") or "").strip()
        runtime_key = str(item.get("runtime_key") or "").strip()
        if runtime_key:
            return PluginAdminOperation(False, f"运行时管理项只读：{runtime_key}")
        if state_key:
            plugin.context.delete_state(state_key)
            return PluginAdminOperation(True, f"状态已删除：{state_key}", self._item_snapshot(plugin, item, include_values=True))
        if config_key:
            config = dict(self.loader.user_config(plugin.id))
            config.pop(config_key, None)
            self.loader.save_user_config(plugin.id, config)
            plugin.config.pop(config_key, None)
            if plugin.context:
                plugin.context.config.pop(config_key, None)
            return PluginAdminOperation(True, f"配置覆盖已删除：{config_key}", self._item_snapshot(plugin, item, include_values=True))
        return PluginAdminOperation(False, "管理项未绑定 state_key 或 config_key")

    def _plugin_item(self, plugin_id: str, item_id: str) -> tuple[LoadedPlugin, dict[str, Any]]:
        plugin = self._plugin(plugin_id)
        for item in plugin.admin_schema:
            aliases = {
                str(item.get("id") or ""),
                str(item.get("state_key") or ""),
                str(item.get("config_key") or ""),
            }
            if item_id in aliases:
                return plugin, item
        raise KeyError(f"plugin admin item not found: {plugin_id}/{item_id}")

    def _snapshot_item_id(self, item: dict[str, Any]) -> str:
        for key in ("id", "state_key", "config_key"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
        return ""

    def _plugin(self, plugin_id: str) -> LoadedPlugin:
        for plugin in self.loader.plugins:
            if plugin.id == plugin_id or plugin.path.name == plugin_id:
                return plugin
        raise KeyError(f"plugin not loaded: {plugin_id}")

    def _item_snapshot(self, plugin: LoadedPlugin, item: dict[str, Any], *, include_values: bool) -> dict[str, Any]:
        state_key = str(item.get("state_key") or "").strip()
        config_key = str(item.get("config_key") or "").strip()
        runtime_key = str(item.get("runtime_key") or "").strip()
        value: Any = None
        if state_key and plugin.context is not None:
            value = plugin.context.get_state(state_key, None)
        elif config_key:
            value = plugin.config.get(config_key)
        elif runtime_key:
            value = _runtime_value(plugin, runtime_key)
        row = {
            "id": str(item.get("id") or state_key or config_key),
            "label": str(item.get("label") or state_key or config_key),
            "type": str(item.get("type") or "state"),
            "state_key": state_key,
            "config_key": config_key,
            "runtime_key": runtime_key,
            "description": str(item.get("description") or ""),
            "commands": list(item.get("commands") or []),
            "actions": list(item.get("actions") or []),
            **_value_summary(value),
        }
        if include_values:
            row["value"] = value
        return {key: value for key, value in row.items() if value not in ("", [])}


def _runtime_value(plugin: LoadedPlugin, runtime_key: str) -> Any:
    if plugin.context is None:
        return "插件上下文不可用"
    handlers = getattr(plugin.module, "PLUGIN_ADMIN_HANDLERS", None) if plugin.module else None
    handler = handlers.get(runtime_key) if isinstance(handlers, dict) else None
    if not callable(handler):
        return f"未找到运行时处理器：{runtime_key}"
    try:
        return handler(plugin.context)
    except Exception as exc:
        return f"运行时处理器失败：{exc}"


def _value_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {"value_type": "missing", "count": 0, "summary": "未写入"}
    if isinstance(value, dict):
        return {"value_type": "dict", "count": len(value), "summary": f"{len(value)} 项"}
    if isinstance(value, (list, tuple, set)):
        return {"value_type": "list", "count": len(value), "summary": f"{len(value)} 项"}
    if isinstance(value, bool):
        return {"value_type": "bool", "count": 1 if value else 0, "summary": "开启" if value else "关闭"}
    if isinstance(value, (int, float)):
        return {"value_type": "number", "count": 1, "summary": str(value)}
    text = str(value)
    return {"value_type": "text", "count": 1 if text else 0, "summary": f"文本 {len(text)} 字"}
