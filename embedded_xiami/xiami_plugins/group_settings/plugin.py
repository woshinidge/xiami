from __future__ import annotations

from typing import Any

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.group_settings import (
    BOOLEAN_SETTINGS,
    NUMBER_SETTINGS,
    GroupSettingService,
    number_key_from_label,
    setting_key_from_label,
)
from xiami_core.plugins.permissions import PluginPermissionService


PLUGIN_ID = "group_settings"
PLUGIN_NAME = "群配置"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "维护群功能开关、插件响应和奖励积分配置。"
PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
}
PLUGIN_ADMIN_SCHEMA = [
    {
        "id": "settings",
        "label": "群功能配置",
        "type": "state",
        "state_key": "settings",
        "commands": [
            "群配置",
            "开启邀请积分",
            "关闭邀请积分",
            "开启",
            "关闭",
            "设置积分",
            "设置参数",
            "插件列表",
            "插件搜索",
            "插件详情",
            "插件命令",
            "插件状态",
            "插件异常",
            "开启插件",
            "关闭插件",
            "开启全部插件",
            "关闭全部插件",
            "复制群配置",
            "清空群配置",
        ],
    },
]

MATCHERS = []
HIDDEN_PLUGIN_IDS = {
    "compat_echo",
    "echo",
    "error_history_case",
    "legacy_bridge",
    "onebot_tools",
    "permissions",
    "group_settings",
}


def on_load(ctx) -> None:
    ctx.log("群配置插件已加载")


@on_command("群配置", aliases=("本群配置", "群设置"), only_group=True, description="查看本群功能配置")
def show_settings(event, ctx, session) -> None:
    ctx.reply(event, GroupSettingService(ctx).summary(session.group_id))


@on_command("插件列表", aliases=("插件中心", "插件管理", "群插件"), only_group=True, description="查看当前群的插件响应状态")
def list_group_plugins(event, ctx, session) -> None:
    catalog = _plugin_catalog(ctx)
    if not catalog:
        ctx.reply(event, "暂无插件目录，请重载插件后再试。")
        return
    service = GroupSettingService(ctx)
    lines = [f"当前群插件（{session.group_id}）："]
    for item in catalog:
        plugin_id = _plugin_id(item)
        group_enabled = service.plugin_enabled(session.group_id, plugin_id, default=False)
        globally_ok = bool(item.get("enabled", True)) and not str(item.get("error") or "").strip()
        if group_enabled and globally_ok:
            state = "开启"
        elif not group_enabled:
            state = "群内关闭"
        else:
            state = "全局停用/异常"
        commands = item.get("commands")
        command_count = len(commands) if isinstance(commands, list) else 0
        lines.append(f"- {_plugin_name(item)}({plugin_id})：{state}｜命令 {command_count} 个")
    lines.append("用法：插件详情 <ID/名称>；开启插件/关闭插件 <ID/名称>。")
    ctx.reply(event, "\n".join(lines))


@on_command("插件搜索", aliases=("搜索插件", "找插件", "查插件"), only_group=True, description="按名称、ID、命令或说明检索插件")
def search_group_plugins(event, ctx, session) -> None:
    query = str(session.argument or "").strip()
    if not query:
        ctx.reply(event, "格式：插件搜索 <关键词>；可搜插件名称、ID、命令或说明。")
        return
    catalog = _plugin_catalog(ctx)
    if not catalog:
        ctx.reply(event, "暂无插件目录，请重载插件后再试。")
        return
    matches = _search_plugin_catalog(catalog, query)
    if not matches:
        ctx.reply(event, f"没有找到匹配“{query}”的插件。")
        return
    service = GroupSettingService(ctx)
    lines = [f"插件搜索“{query}”："]
    for item in matches[:12]:
        plugin_id = _plugin_id(item)
        state = "开启" if service.plugin_enabled(session.group_id, plugin_id, default=False) else "群内关闭"
        matched_commands = _matched_commands(item, query)
        command_hint = f"｜命令：{'、'.join(matched_commands[:3])}" if matched_commands else ""
        lines.append(f"- {_plugin_name(item)}({plugin_id})：{state}{command_hint}")
    if len(matches) > 12:
        lines.append(f"... 还有 {len(matches) - 12} 个结果，请换更精确关键词。")
    lines.append("用法：插件详情 <ID/名称>；插件命令 <ID/名称>。")
    ctx.reply(event, "\n".join(lines))


@on_command("插件详情", aliases=("插件信息", "查看插件"), only_group=True, description="查看插件说明、命令和当前群响应状态")
def group_plugin_detail(event, ctx, session) -> None:
    item, error = _resolve_plugin_arg(ctx, session.argument)
    if error:
        ctx.reply(event, error)
        return
    assert item is not None
    plugin_id = _plugin_id(item)
    service = GroupSettingService(ctx)
    group_enabled = service.plugin_enabled(session.group_id, plugin_id, default=False)
    global_enabled = bool(item.get("enabled", True))
    error_text = str(item.get("error") or "").strip()
    commands = _string_list(item.get("commands"))
    capabilities = _string_list(item.get("capabilities"))
    lines = [
        "插件详情：",
        f"名称：{_plugin_name(item)}",
        f"ID：{plugin_id}",
        f"当前群响应：{'开启' if group_enabled else '关闭'}",
        f"全局状态：{'已启用' if global_enabled and not error_text else '停用/异常'}",
    ]
    description = str(item.get("description") or "").strip()
    version = str(item.get("version") or "").strip()
    if version:
        lines.append(f"版本：{version}")
    if description:
        lines.append(f"说明：{description}")
    if commands:
        lines.append("命令：" + "、".join(commands[:18]) + (" ..." if len(commands) > 18 else ""))
    if capabilities:
        lines.append("能力：" + "、".join(capabilities[:12]) + (" ..." if len(capabilities) > 12 else ""))
    admin_items = _admin_item_labels(item)
    if admin_items:
        lines.append("可配置项：" + "、".join(admin_items[:10]) + (" ..." if len(admin_items) > 10 else ""))
    if error_text:
        lines.append(f"异常：{error_text}")
    ctx.reply(event, "\n".join(lines))


@on_command("插件命令", aliases=("插件帮助", "插件功能"), only_group=True, description="查看指定插件的全部命令")
def group_plugin_commands(event, ctx, session) -> None:
    item, error = _resolve_plugin_arg(ctx, session.argument)
    if error:
        ctx.reply(event, error)
        return
    assert item is not None
    commands = _string_list(item.get("commands"))
    if not commands:
        ctx.reply(event, f"{_plugin_name(item)}({_plugin_id(item)}) 暂无声明命令。")
        return
    lines = [f"{_plugin_name(item)}({_plugin_id(item)}) 命令："]
    for index, command in enumerate(commands[:40], start=1):
        lines.append(f"{index}. {command}")
    if len(commands) > 40:
        lines.append(f"... 还有 {len(commands) - 40} 条未显示。")
    ctx.reply(event, "\n".join(lines))


@on_command("插件状态", aliases=("插件诊断", "插件统计"), only_group=True, description="查看插件收发、处理和异常统计")
def group_plugin_status(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    query = str(session.argument or "").strip()
    if query:
        item, error = _resolve_plugin_arg(ctx, query)
        if error:
            ctx.reply(event, error)
            return
        assert item is not None
        ctx.reply(event, _plugin_status_detail(ctx, session.group_id, item))
        return
    catalog = _plugin_catalog(ctx)
    if not catalog:
        ctx.reply(event, "暂无插件目录，请重载插件后再试。")
        return
    service = GroupSettingService(ctx)
    total = len(catalog)
    global_ok = 0
    group_enabled = 0
    abnormal = 0
    total_messages = 0
    total_events = 0
    rows: list[str] = []
    for item in catalog:
        plugin_id = _plugin_id(item)
        globally_ok = bool(item.get("enabled", True)) and not _error_text(item)
        enabled_in_group = service.plugin_enabled(session.group_id, plugin_id, default=False)
        if globally_ok:
            global_ok += 1
        if enabled_in_group:
            group_enabled += 1
        if not globally_ok or _int_value(item.get("error_count")) > 0:
            abnormal += 1
        message_count = _int_value(item.get("message_count"))
        event_count = _int_value(item.get("event_count"))
        total_messages += message_count
        total_events += event_count
        if message_count or event_count or _int_value(item.get("error_count")) > 0:
            state = "开" if enabled_in_group and globally_ok else ("群关" if not enabled_in_group else "异常")
            rows.append(f"- {_plugin_name(item)}({plugin_id})：{state}｜消息 {message_count}｜事件 {event_count}｜异常 {_int_value(item.get('error_count'))}")
    lines = [
        "插件状态：",
        f"总数 {total}；全局可用 {global_ok}；本群开启 {group_enabled}；异常 {abnormal}；消息 {total_messages}；事件 {total_events}",
    ]
    if rows:
        lines.extend(rows[:12])
        if len(rows) > 12:
            lines.append(f"... 还有 {len(rows) - 12} 个有运行记录的插件。")
    else:
        lines.append("暂无运行记录。")
    lines.append("用法：插件状态 <ID/名称> 查看单插件详情。")
    ctx.reply(event, "\n".join(lines))


@on_command("插件异常", aliases=("插件错误", "异常插件"), only_group=True, description="查看加载失败或运行报错插件")
def group_plugin_errors(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    catalog = _plugin_catalog(ctx)
    if not catalog:
        ctx.reply(event, "暂无插件目录，请重载插件后再试。")
        return
    rows = []
    for item in catalog:
        error_count = _int_value(item.get("error_count"))
        error_text = _error_text(item)
        if not error_count and not error_text and bool(item.get("enabled", True)):
            continue
        plugin_id = _plugin_id(item)
        if error_text:
            rows.append(f"- {_plugin_name(item)}({plugin_id})：异常 {error_count} 次｜{_short_text(error_text, 80)}")
        elif not bool(item.get("enabled", True)):
            rows.append(f"- {_plugin_name(item)}({plugin_id})：全局停用")
    if not rows:
        ctx.reply(event, "当前没有插件异常。")
        return
    ctx.reply(event, "插件异常：\n" + "\n".join(rows[:20]))


@on_command("开启插件", aliases=("启用插件", "打开插件"), only_group=True, description="在当前群开启指定插件响应")
def enable_group_plugin(event, ctx, session) -> None:
    _set_group_plugin(event, ctx, session, True)


@on_command("关闭插件", aliases=("禁用插件", "停用插件"), only_group=True, description="在当前群关闭指定插件响应")
def disable_group_plugin(event, ctx, session) -> None:
    _set_group_plugin(event, ctx, session, False)


@on_command("开启全部插件", aliases=("启用全部插件", "打开全部插件"), only_group=True, description="在当前群开启所有公开插件响应")
def enable_all_group_plugins(event, ctx, session) -> None:
    _set_all_group_plugins(event, ctx, session, True)


@on_command("关闭全部插件", aliases=("禁用全部插件", "停用全部插件"), only_group=True, description="在当前群关闭所有公开插件响应")
def disable_all_group_plugins(event, ctx, session) -> None:
    _set_all_group_plugins(event, ctx, session, False)


@on_command("复制群配置", aliases=("复制插件配置", "复制本群配置"), only_group=True, description="复制群插件开关和功能配置")
def copy_group_config(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    parts = session.argv
    if not parts:
        ctx.reply(event, "格式：复制群配置 <来源群号> [目标群号]；只填来源时复制到当前群。")
        return
    if len(parts) == 1:
        if session.command in {"复制本群配置"}:
            source_group_id = session.group_id
            target_group_id = parts[0]
        else:
            source_group_id = parts[0]
            target_group_id = session.group_id
    else:
        source_group_id, target_group_id = parts[0], parts[1]
    if source_group_id == target_group_id:
        ctx.reply(event, "来源群和目标群不能相同。")
        return
    changed = GroupSettingService(ctx).copy_group_settings(source_group_id, target_group_id, _catalog_plugin_ids(ctx))
    if changed:
        ctx.reply(event, f"已复制群 {source_group_id} 的插件配置到群 {target_group_id}。")
    else:
        ctx.reply(event, f"未找到群 {source_group_id} 可复制的插件配置。")


@on_command("清空群配置", aliases=("重置群配置", "清除群配置"), only_group=True, description="清空指定群或当前群的插件单独配置")
def clear_group_config(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    group_id = session.argv[0] if session.argv else session.group_id
    changed = GroupSettingService(ctx).clear_group_settings(group_id, _catalog_plugin_ids(ctx))
    if changed:
        ctx.reply(event, f"已清空群 {group_id} 的插件单独配置，将恢复默认。")
    else:
        ctx.reply(event, f"群 {group_id} 没有单独配置，无需清空。")


@on_command("开启", only_group=True, description="开启 <功能名>，支持群配置中列出的所有功能项")
def enable_feature(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    _set_feature(event, ctx, session, True)


@on_command("关闭", only_group=True, description="关闭 <功能名>，支持群配置中列出的所有功能项")
def disable_feature(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    _set_feature(event, ctx, session, False)


@on_command("设置积分", aliases=("设置奖励", "设置参数", "设置数值"), only_group=True, description="设置参数 <参数名> <数值>")
def set_points(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    parts = session.argv
    if len(parts) < 2:
        ctx.reply(event, "格式：设置参数 <邀请奖励积分|答题奖励积分|机器人全部回复撤回秒数> <数值>")
        return
    key = number_key_from_label(parts[0])
    if key not in NUMBER_SETTINGS:
        ctx.reply(event, "未知数值参数，可用：邀请奖励积分、答题奖励积分、机器人全部回复撤回秒数。")
        return
    try:
        value = int(parts[1])
    except ValueError:
        ctx.reply(event, "积分数量必须是数字。")
        return
    GroupSettingService(ctx).set_number(session.group_id, key, value)
    ctx.reply(event, f"已设置{NUMBER_SETTINGS[key].label}：{max(1, value)}。")


@on_command("开启邀请积分", only_group=True, description="开启本群邀请积分")
def enable_invite_points(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    GroupSettingService(ctx).set_enabled(session.group_id, "invite_points_enabled", True)
    ctx.reply(event, "本群邀请积分已开启。")


@on_command("关闭邀请积分", only_group=True, description="关闭本群邀请积分")
def disable_invite_points(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    GroupSettingService(ctx).set_enabled(session.group_id, "invite_points_enabled", False)
    ctx.reply(event, "本群邀请积分已关闭。")


def _set_feature(event, ctx, session, enabled: bool) -> None:
    feature = session.argument.strip()
    key = setting_key_from_label(feature)
    if key not in BOOLEAN_SETTINGS:
        ctx.reply(event, f"未知功能，可用：{_available_features()}。")
        return
    GroupSettingService(ctx).set_enabled(session.group_id, key, enabled)
    state = "开启" if enabled else "关闭"
    ctx.reply(event, f"已{state}{BOOLEAN_SETTINGS[key].label}。")


def _available_features() -> str:
    return "、".join(spec.label for spec in BOOLEAN_SETTINGS.values())


def _set_group_plugin(event, ctx, session, enabled: bool) -> None:
    if not _require_admin(event, ctx, session):
        return
    item, error = _resolve_plugin_arg(ctx, session.argument)
    if error:
        ctx.reply(event, error)
        return
    assert item is not None
    plugin_id = _plugin_id(item)
    if plugin_id == PLUGIN_ID and not enabled:
        ctx.reply(event, "群配置插件是群内管理入口，不能在群内关闭。")
        return
    GroupSettingService(ctx).set_plugin_enabled(session.group_id, plugin_id, enabled)
    state = "开启" if enabled else "关闭"
    suffix = ""
    if enabled and (not bool(item.get("enabled", True)) or str(item.get("error") or "").strip()):
        suffix = "（注意：插件全局未启用或加载异常时仍不会响应）"
    ctx.reply(event, f"已在本群{state}插件：{_plugin_name(item)}({plugin_id})。{suffix}")


def _set_all_group_plugins(event, ctx, session, enabled: bool) -> None:
    if not _require_admin(event, ctx, session):
        return
    catalog = _plugin_catalog(ctx)
    if not catalog:
        ctx.reply(event, "暂无插件目录，请重载插件后再试。")
        return
    service = GroupSettingService(ctx)
    changed: list[str] = []
    unchanged = 0
    for item in catalog:
        plugin_id = _plugin_id(item)
        if not plugin_id or plugin_id == PLUGIN_ID:
            continue
        before = service.plugin_enabled(session.group_id, plugin_id, default=False)
        service.set_plugin_enabled(session.group_id, plugin_id, enabled)
        label = f"{_plugin_name(item)}({plugin_id})"
        if before == enabled:
            unchanged += 1
        else:
            changed.append(label)
    state = "开启" if enabled else "关闭"
    total = len(changed) + unchanged
    if total <= 0:
        ctx.reply(event, "没有可批量设置的公开插件。")
        return
    preview = "、".join(changed[:8])
    if len(changed) > 8:
        preview += f" 等 {len(changed)} 个"
    elif not changed:
        preview = "无需变更"
    suffix = f"；其中 {unchanged} 个原本已{state}" if unchanged else ""
    ctx.reply(event, f"已在本群{state}全部公开插件：{total} 个（{preview}）{suffix}。")


def _resolve_plugin_arg(ctx: Any, argument: str) -> tuple[dict[str, Any] | None, str]:
    query = str(argument or "").strip()
    catalog = _plugin_catalog(ctx)
    if not catalog:
        return None, "暂无插件目录，请重载插件后再试。"
    if not query:
        return None, "格式：插件详情/开启插件/关闭插件 <插件ID或名称>。"
    exact: list[dict[str, Any]] = []
    fuzzy: list[dict[str, Any]] = []
    needle = _normalize_plugin_ref(query)
    for item in catalog:
        plugin_id = _plugin_id(item)
        name = _plugin_name(item)
        aliases = [plugin_id, name]
        normalized_aliases = [_normalize_plugin_ref(value) for value in aliases if value]
        if needle in normalized_aliases:
            exact.append(item)
            continue
        haystack = " ".join(
            [
                plugin_id,
                name,
                str(item.get("description") or ""),
                " ".join(_string_list(item.get("commands"))),
            ]
        )
        if needle and needle in _normalize_plugin_ref(haystack):
            fuzzy.append(item)
    matches = exact or fuzzy
    if not matches:
        return None, f"未找到插件：{query}。可发送“插件列表”查看可用插件。"
    if len(matches) > 1:
        options = "、".join(f"{_plugin_name(item)}({_plugin_id(item)})" for item in matches[:8])
        return None, f"匹配到多个插件：{options}。请使用插件 ID。"
    return matches[0], ""


def _search_plugin_catalog(catalog: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    needle = _normalize_plugin_ref(query)
    if not needle:
        return []
    scored: list[tuple[int, str, dict[str, Any]]] = []
    for item in catalog:
        plugin_id = _plugin_id(item)
        name = _plugin_name(item)
        score = 0
        if needle == _normalize_plugin_ref(plugin_id) or needle == _normalize_plugin_ref(name):
            score += 100
        elif needle in _normalize_plugin_ref(plugin_id) or needle in _normalize_plugin_ref(name):
            score += 60
        command_matches = _matched_commands(item, query)
        if command_matches:
            score += 30 + min(10, len(command_matches))
        haystack = _normalize_plugin_ref(
            " ".join(
                [
                    str(item.get("description") or ""),
                    " ".join(_string_list(item.get("capabilities"))),
                    " ".join(_admin_item_labels(item)),
                ]
            )
        )
        if needle in haystack:
            score += 10
        if score > 0:
            scored.append((score, plugin_id, item))
    return [item for _score, _plugin_id, item in sorted(scored, key=lambda row: (-row[0], row[1]))]


def _matched_commands(item: dict[str, Any], query: str) -> list[str]:
    needle = _normalize_plugin_ref(query)
    if not needle:
        return []
    result: list[str] = []
    for command in _string_list(item.get("commands")):
        if needle in _normalize_plugin_ref(command):
            result.append(command)
    return result


def _admin_item_labels(item: dict[str, Any]) -> list[str]:
    raw = item.get("admin_schema")
    if not isinstance(raw, list):
        return []
    labels: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or entry.get("id") or "").strip()
        if label and label not in labels:
            labels.append(label)
    return labels


def _plugin_status_detail(ctx: Any, group_id: str, item: dict[str, Any]) -> str:
    service = GroupSettingService(ctx)
    plugin_id = _plugin_id(item)
    group_enabled = service.plugin_enabled(group_id, plugin_id, default=False)
    global_enabled = bool(item.get("enabled", True))
    error_text = _error_text(item)
    lines = [
        "插件状态详情：",
        f"名称：{_plugin_name(item)}",
        f"ID：{plugin_id}",
        f"当前群响应：{'开启' if group_enabled else '关闭'}",
        f"全局状态：{'已启用' if global_enabled and not error_text else '停用/异常'}",
        f"消息：收到 {_int_value(item.get('message_count'))}｜已处理 {_int_value(item.get('message_handled_count'))}｜未处理 {_int_value(item.get('message_unhandled_count'))}",
        f"事件：收到 {_int_value(item.get('event_count'))}｜已处理 {_int_value(item.get('event_handled_count'))}｜未处理 {_int_value(item.get('event_unhandled_count'))}",
        f"异常次数：{_int_value(item.get('error_count'))}",
    ]
    matcher_hits = item.get("matcher_hit_count")
    if isinstance(matcher_hits, dict) and matcher_hits:
        top_hits = sorted(((str(key), _int_value(value)) for key, value in matcher_hits.items()), key=lambda row: (-row[1], row[0]))
        lines.append("命中：" + "、".join(f"{label}×{count}" for label, count in top_hits[:8]))
    if error_text:
        lines.append(f"最近异常：{_short_text(error_text, 160)}")
    return "\n".join(lines)


def _error_text(item: dict[str, Any]) -> str:
    return str(item.get("last_error") or item.get("error") or "").strip()


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _short_text(value: Any, limit: int = 80) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)] + "…"


def _plugin_catalog(ctx: Any) -> list[dict[str, Any]]:
    registry = getattr(ctx, "runtime_registry", None)
    if not isinstance(registry, dict):
        return []
    raw = registry.get("plugin_catalog") or registry.get("plugins") or []
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw:
        plugin_id = _plugin_id(item) if isinstance(item, dict) else ""
        if plugin_id and plugin_id.lower() not in HIDDEN_PLUGIN_IDS:
            result.append(item)
    return sorted(result, key=lambda item: _plugin_id(item))


def _catalog_plugin_ids(ctx: Any) -> list[str]:
    return [_plugin_id(item) for item in _plugin_catalog(ctx)]


def _plugin_id(item: dict[str, Any]) -> str:
    return str(item.get("id") or "").strip()


def _plugin_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("id") or "").strip()


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_plugin_ref(value: str) -> str:
    return "".join(str(value or "").strip().lower().split())


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


MATCHERS.extend(
    [
        show_settings,
        list_group_plugins,
        search_group_plugins,
        group_plugin_detail,
        group_plugin_commands,
        group_plugin_status,
        group_plugin_errors,
        enable_group_plugin,
        disable_group_plugin,
        enable_all_group_plugins,
        disable_all_group_plugins,
        copy_group_config,
        clear_group_config,
        enable_invite_points,
        disable_invite_points,
        enable_feature,
        disable_feature,
        set_points,
    ]
)

