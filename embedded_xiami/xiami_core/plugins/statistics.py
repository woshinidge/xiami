from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any


def build_plugin_statistics(source: Any, top_limit: int = 10) -> dict[str, Any]:
    diagnostics = _diagnostics(source)
    plugins = [_plugin_row(item) for item in diagnostics]
    hot_matchers = _hot_matchers(plugins, top_limit=top_limit)
    hot_plugins = sorted(
        plugins,
        key=lambda item: (item["handled_total"], item["dispatch_total"], item["id"]),
        reverse=True,
    )[:top_limit]
    error_plugins = sorted(
        (item for item in plugins if item["error_count"] or item["error"]),
        key=lambda item: (item["error_count"], item["id"]),
        reverse=True,
    )
    command_surface = [
        {
            "plugin_id": item["id"],
            "plugin_name": item["name"],
            "commands": list(item["commands"]),
        }
        for item in plugins
        if item["commands"]
    ]

    return {
        "summary": {
            "plugin_count": len(plugins),
            "enabled_count": sum(1 for item in plugins if item["enabled"]),
            "error_count": sum(1 for item in plugins if item["error_count"] or item["error"]),
            "message_count": sum(item["message_count"] for item in plugins),
            "event_count": sum(item["event_count"] for item in plugins),
            "handled_total": sum(item["handled_total"] for item in plugins),
            "unhandled_total": sum(item["unhandled_total"] for item in plugins),
        },
        "plugins": plugins,
        "hot_plugins": hot_plugins,
        "hot_matchers": hot_matchers,
        "error_plugins": error_plugins,
        "command_surface": command_surface,
    }


def plugin_statistics_json(source: Any, top_limit: int = 10) -> str:
    return json.dumps(build_plugin_statistics(source, top_limit=top_limit), ensure_ascii=False, indent=2)


def format_plugin_statistics(source: Any, top_limit: int = 10) -> str:
    stats = build_plugin_statistics(source, top_limit=top_limit)
    summary = stats["summary"]
    lines = [
        f"插件：{summary['plugin_count']} 个，启用：{summary['enabled_count']} 个，异常：{summary['error_count']} 个",
        f"分发：消息 {summary['message_count']}，事件 {summary['event_count']}，命中 {summary['handled_total']}，未命中 {summary['unhandled_total']}",
    ]
    if stats["hot_plugins"]:
        lines.append("插件热度：")
        for item in stats["hot_plugins"][:top_limit]:
            lines.append(
                f"- {item['name']} ({item['id']}): 命中 {item['handled_total']} / 分发 {item['dispatch_total']}"
            )
    if stats["hot_matchers"]:
        lines.append("命令/规则热度：")
        for item in stats["hot_matchers"][:top_limit]:
            lines.append(f"- {item['label']} [{item['plugin_id']}]: {item['count']}")
    if stats["error_plugins"]:
        lines.append("异常插件：")
        for item in stats["error_plugins"][:top_limit]:
            lines.append(f"- {item['name']} ({item['id']}): {item['error_count']} {item['last_error']}")
    return "\n".join(lines)


def _diagnostics(source: Any) -> list[dict[str, Any]]:
    if callable(getattr(source, "diagnostics", None)):
        value = source.diagnostics()
    else:
        value = source
    if isinstance(value, dict):
        value = [value]
    if not isinstance(value, Iterable):
        return []
    return [item for item in value if isinstance(item, dict)]


def _plugin_row(item: dict[str, Any]) -> dict[str, Any]:
    message_count = _int(item.get("message_count"))
    event_count = _int(item.get("event_count"))
    message_handled = _int(item.get("message_handled_count"))
    message_unhandled = _int(item.get("message_unhandled_count"))
    event_handled = _int(item.get("event_handled_count"))
    event_unhandled = _int(item.get("event_unhandled_count"))
    matcher_hits = _matcher_hits(item.get("matcher_hit_count"))
    return {
        "id": str(item.get("id") or ""),
        "name": str(item.get("name") or item.get("id") or ""),
        "enabled": bool(item.get("enabled")),
        "error": str(item.get("error") or ""),
        "last_error": str(item.get("last_error") or item.get("error") or ""),
        "error_count": _int(item.get("error_count")),
        "message_count": message_count,
        "event_count": event_count,
        "message_handled_count": message_handled,
        "message_unhandled_count": message_unhandled,
        "event_handled_count": event_handled,
        "event_unhandled_count": event_unhandled,
        "dispatch_total": message_count + event_count,
        "handled_total": message_handled + event_handled,
        "unhandled_total": message_unhandled + event_unhandled,
        "commands": _string_list(item.get("commands")),
        "capabilities": _string_list(item.get("capabilities")),
        "matcher_hit_count": matcher_hits,
        "migration_status": str(item.get("migration_status") or ""),
    }


def _hot_matchers(plugins: list[dict[str, Any]], top_limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plugin in plugins:
        for label, count in plugin["matcher_hit_count"].items():
            rows.append(
                {
                    "plugin_id": plugin["id"],
                    "plugin_name": plugin["name"],
                    "label": label,
                    "count": count,
                }
            )
    return sorted(rows, key=lambda item: (item["count"], item["plugin_id"], item["label"]), reverse=True)[:top_limit]


def _matcher_hits(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        label = str(key or "").strip()
        if label:
            result[label] = _int(count)
    return result


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
