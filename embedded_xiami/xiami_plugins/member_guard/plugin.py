from __future__ import annotations

import re

from xiami_core.plugins.compat import on_command, on_notice
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.member_guard import MemberGuardService
from xiami_core.plugins.permissions import PluginPermissionService


PLUGIN_ID = "member_guard"
PLUGIN_NAME = "名单与违禁词"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "管理黑白名单、违禁词和消息自动撤回规则。"
PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
    "forbidden_ban_seconds": 600,
    "blacklist_kick": True,
    "forbidden_recall_enabled": True,
    "blacklist_recall_enabled": True,
    "blacklist_kick_notice_enabled": True,
    "group_number_recall_enabled": False,
    "auto_recall_enabled": False,
    "leave_recall_enabled": False,
    "leave_recall_limit": 20,
    "message_cache_limit_per_member": 50,
    "recall_message_types": [],
}
PLUGIN_ADMIN_SCHEMA = [
    {"id": "member_lists", "label": "黑白名单", "type": "state", "state_key": "member_lists", "commands": ["名单列表", "加黑名单", "删黑名单", "加白名单", "删白名单", "清空黑名单", "清空白名单"]},
    {"id": "forbidden_words", "label": "违禁词", "type": "state", "state_key": "forbidden_words", "commands": ["违禁词列表", "加违禁词", "删违禁词", "清空违禁词"]},
    {"id": "blacklist_kick", "label": "黑名单入群踢出", "type": "config", "config_key": "blacklist_kick"},
    {"id": "forbidden_recall_enabled", "label": "违禁词撤回", "type": "config", "config_key": "forbidden_recall_enabled"},
    {"id": "group_number_recall_enabled", "label": "群号撤回", "type": "config", "config_key": "group_number_recall_enabled"},
    {"id": "auto_recall_enabled", "label": "自动类型撤回", "type": "config", "config_key": "auto_recall_enabled", "commands": ["撤回设置", "设置撤回类型", "开启红包撤回", "关闭红包撤回"]},
    {"id": "leave_recall_enabled", "label": "退群撤回", "type": "config", "config_key": "leave_recall_enabled", "commands": ["开启退群撤回", "关闭退群撤回"]},
    {"id": "leave_recall_limit", "label": "退群撤回条数", "type": "config", "config_key": "leave_recall_limit", "commands": ["设置退群撤回条数"]},
    {"id": "bot_reply_recall_enabled", "label": "机器人全部回复撤回", "type": "config", "config_key": "bot_reply_recall_enabled", "commands": ["开启机器人回复撤回", "关闭机器人回复撤回", "设置机器人回复撤回秒数"]},
    {"id": "recall_message_types", "label": "撤回消息类型", "type": "config", "config_key": "recall_message_types", "commands": ["设置撤回类型", "撤回类型"]},
]

MATCHERS = []
EVENT_MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("名单与违禁词插件已加载")


def on_message(event, ctx) -> None:
    if event.message_type != "group":
        return
    if not _member_guard_enabled(ctx, event.target):
        return
    guard = MemberGuardService(ctx)
    decision = guard.decide(event.target, event.sender)
    if decision.action == "deny" and _guard_bool(ctx, event.target, "blacklist_kick_enabled"):
        response = ctx.set_group_kick(event.target, event.sender, reject_add_request=False)
        if getattr(response, "ok", False):
            ctx.reply(event, f"已踢出黑名单成员 {event.sender}（{decision.reason}）。")
        else:
            ctx.reply(event, f"黑名单处理失败：{getattr(response, 'message', response)}")
        return
    if decision.action == "allow":
        return
    hit = guard.match_forbidden(event.target, event.text)
    if hit:
        seconds = _guard_number(ctx, event.target, "forbidden_ban_seconds", default=600, maximum=86400)
        response = ctx.set_group_ban(event.target, event.sender, seconds)
        if getattr(response, "ok", False):
            ctx.reply(event, f"命中违禁词：{hit.word}，已禁言 {seconds} 秒。")
        else:
            ctx.reply(event, f"违禁词处理失败：{getattr(response, 'message', response)}")


def on_raw_message(event, ctx) -> None:
    if not event.message or event.message.message_type != "group":
        return
    if not _member_guard_enabled(ctx, event.message.target):
        return
    message_id = event.raw.get("message_id")
    if message_id is None:
        return

    if _recall_exempt(ctx, event.message.target, event.message.sender):
        return

    _remember_group_message(ctx, event.message.target, event.message.sender, message_id)

    guard = MemberGuardService(ctx)
    decision = guard.decide(event.message.target, event.message.sender)
    if decision.action == "deny" and _guard_bool(ctx, event.message.target, "blacklist_recall_enabled"):
        response = _delete_message(ctx, message_id, event.message.target, event.message.sender, "黑名单")
        if _response_ok(response) and _guard_bool(ctx, event.message.target, "blacklist_kick_notice_enabled"):
            ctx.send_group(event.message.target, f"黑名单成员 {event.message.sender} 的消息已撤回。")
        return
    if decision.action == "allow":
        return

    hit = guard.match_forbidden(event.message.target, event.message.text)
    if hit and _guard_bool(ctx, event.message.target, "forbidden_recall_enabled"):
        response = _delete_message(ctx, message_id, event.message.target, event.message.sender, "违禁词")
        if _response_ok(response):
            ctx.send_group(event.message.target, f"成员 {event.message.sender} 的消息包含违禁词，已撤回。")
        return

    if _matches_group_number_recall(event.message, ctx, event.message.target):
        _delete_message(ctx, message_id, event.message.target, event.message.sender, "群号")
        return

    detected_types = _detect_recall_types(event.message, event.raw)
    if _matches_auto_recall_type(event.message, ctx, event.message.target, detected_types=detected_types):
        detected = sorted(detected_types)
        _delete_message(ctx, message_id, event.message.target, event.message.sender, f"消息类型:{','.join(detected)}")


@on_notice("group_decrease", description="成员退群后撤回最近消息")
def recall_member_messages_on_leave(event, ctx, session) -> None:
    group_id = str(session.group_id or event.group_id or "")
    user_id = str(session.user_id or event.user_id or "")
    if not group_id or not user_id:
        return
    if not _member_guard_enabled(ctx, group_id):
        return
    if not _guard_bool(ctx, group_id, "leave_recall_enabled"):
        return
    if _recall_exempt(ctx, group_id, user_id):
        ctx.log(f"退群撤回跳过：群 {group_id} 成员 {user_id} 是管理人员。")
        return
    cache = _message_cache(ctx)
    key = _message_cache_key(group_id, user_id)
    message_ids = list(cache.get(key, []))
    if not message_ids:
        return
    limit = _guard_number(ctx, group_id, "leave_recall_limit", default=20, maximum=500)
    recalled = 0
    failed = 0
    for message_id in message_ids[-limit:]:
        response = ctx.delete_msg(message_id)
        if _response_ok(response):
            recalled += 1
        else:
            failed += 1
    cache.pop(key, None)
    ctx.set_state("recent_group_messages", cache)
    ctx.log(f"退群撤回：群 {group_id} 成员 {user_id}，成功 {recalled} 条，失败 {failed} 条。")


@on_command("加黑名单", only_group=True, description="加黑名单 <QQ...>")
def add_group_black(event, ctx, session) -> None:
    _member_command(event, ctx, session, "group", "black", "add", "本群黑名单")


@on_command("删黑名单", only_group=True, description="删黑名单 <QQ...>")
def remove_group_black(event, ctx, session) -> None:
    _member_command(event, ctx, session, "group", "black", "remove", "本群黑名单")


@on_command("加白名单", only_group=True, description="加白名单 <QQ...>")
def add_group_white(event, ctx, session) -> None:
    _member_command(event, ctx, session, "group", "white", "add", "本群白名单")


@on_command("删白名单", only_group=True, description="删白名单 <QQ...>")
def remove_group_white(event, ctx, session) -> None:
    _member_command(event, ctx, session, "group", "white", "remove", "本群白名单")


@on_command("加全局黑名单", description="加全局黑名单 <QQ...>")
def add_global_black(event, ctx, session) -> None:
    _member_command(event, ctx, session, "global", "black", "add", "全局黑名单")


@on_command("删全局黑名单", description="删全局黑名单 <QQ...>")
def remove_global_black(event, ctx, session) -> None:
    _member_command(event, ctx, session, "global", "black", "remove", "全局黑名单")


@on_command("加全局白名单", description="加全局白名单 <QQ...>")
def add_global_white(event, ctx, session) -> None:
    _member_command(event, ctx, session, "global", "white", "add", "全局白名单")


@on_command("删全局白名单", description="删全局白名单 <QQ...>")
def remove_global_white(event, ctx, session) -> None:
    _member_command(event, ctx, session, "global", "white", "remove", "全局白名单")


@on_command("加违禁词", only_group=True, description="加违禁词 <词...>")
def add_group_words(event, ctx, session) -> None:
    _word_command(event, ctx, session, "group", "add", "本群违禁词")


@on_command("删违禁词", only_group=True, description="删违禁词 <词...>")
def remove_group_words(event, ctx, session) -> None:
    _word_command(event, ctx, session, "group", "remove", "本群违禁词")


@on_command("加全局违禁词", description="加全局违禁词 <词...>")
def add_global_words(event, ctx, session) -> None:
    _word_command(event, ctx, session, "global", "add", "全局违禁词")


@on_command("删全局违禁词", description="删全局违禁词 <词...>")
def remove_global_words(event, ctx, session) -> None:
    _word_command(event, ctx, session, "global", "remove", "全局违禁词")


@on_command(
    "清理黑名单",
    aliases=("清理群黑名单", "黑名单清理", "清理本群黑", "清本群黑"),
    only_group=True,
    description="清理本群当前黑名单成员",
)
def sweep_blacklist(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    guard = MemberGuardService(ctx)
    response = ctx.get_group_member_list(session.group_id)
    if not _response_ok(response):
        ctx.reply(event, f"读取群成员列表失败：{getattr(response, 'message', response)}")
        return
    members = _response_data(response)
    if not isinstance(members, list):
        ctx.reply(event, "读取群成员列表失败：OneBot 返回格式不正确。")
        return

    matched = 0
    kicked = 0
    failed = 0
    for member in members:
        user_id = _member_user_id(member)
        if not user_id:
            continue
        decision = guard.decide(session.group_id, user_id)
        if decision.action != "deny":
            continue
        matched += 1
        kick_response = ctx.set_group_kick(session.group_id, user_id, reject_add_request=False)
        if _response_ok(kick_response):
            kicked += 1
        else:
            failed += 1

    if matched == 0:
        ctx.reply(event, "清理黑名单完成：当前群内未发现黑名单成员。")
        return
    ctx.reply(event, f"清理黑名单完成：命中 {matched} 人，成功移出 {kicked} 人，失败 {failed} 人。")


@on_command("名单列表", aliases=("名单状态", "风控名单"), only_group=True, description="查看本群和全局黑白名单")
def list_member_guard(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    ctx.reply(event, MemberGuardService(ctx).summary_text(session.group_id))


@on_command("违禁词列表", aliases=("违禁词列表", "违禁词状态"), only_group=True, description="查看本群和全局违禁词")
def list_forbidden_words(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    guard = MemberGuardService(ctx)
    ctx.reply(
        event,
        "\n".join(
            [
                "违禁词列表：",
                f"本群违禁词：{_format_values(guard.words('group', session.group_id))}",
                f"全局违禁词：{_format_values(guard.words('global', ''))}",
            ]
        ),
    )


@on_command("清空黑名单", aliases=("清空本群黑名单",), only_group=True, description="清空本群黑名单")
def clear_group_black(event, ctx, session) -> None:
    _clear_members_command(event, ctx, session, "group", "black", "本群黑名单")


@on_command("清空白名单", aliases=("清空本群白名单",), only_group=True, description="清空本群白名单")
def clear_group_white(event, ctx, session) -> None:
    _clear_members_command(event, ctx, session, "group", "white", "本群白名单")


@on_command("清空全局黑名单", description="清空全局黑名单")
def clear_global_black(event, ctx, session) -> None:
    _clear_members_command(event, ctx, session, "global", "black", "全局黑名单")


@on_command("清空全局白名单", description="清空全局白名单")
def clear_global_white(event, ctx, session) -> None:
    _clear_members_command(event, ctx, session, "global", "white", "全局白名单")


@on_command("清空违禁词", aliases=("清空本群违禁词",), only_group=True, description="清空本群违禁词")
def clear_group_words(event, ctx, session) -> None:
    _clear_words_command(event, ctx, session, "group", "本群违禁词")


@on_command("清空全局违禁词", description="清空全局违禁词")
def clear_global_words(event, ctx, session) -> None:
    _clear_words_command(event, ctx, session, "global", "全局违禁词")


@on_command("撤回设置", aliases=("风控设置", "名单设置"), only_group=True, description="查看本群撤回和风控设置")
def recall_settings(event, ctx, session) -> None:
    service = GroupSettingService(ctx)
    types = _recall_types(ctx, session.group_id)
    ctx.reply(
        event,
        "\n".join(
            [
                "撤回设置：",
                f"名单风控：{'开启' if service.enabled(session.group_id, 'member_guard_enabled') else '关闭'}",
                f"黑名单入群踢出：{'开启' if service.enabled(session.group_id, 'blacklist_kick_enabled') else '关闭'}",
                f"违禁词撤回：{'开启' if service.enabled(session.group_id, 'forbidden_recall_enabled') else '关闭'}",
                f"黑名单发言撤回：{'开启' if service.enabled(session.group_id, 'blacklist_recall_enabled') else '关闭'}",
                f"群号撤回：{'开启' if service.enabled(session.group_id, 'group_number_recall_enabled') else '关闭'}",
                f"自动类型撤回：{'开启' if service.enabled(session.group_id, 'auto_recall_enabled') else '关闭'}",
                f"退群撤回：{'开启' if service.enabled(session.group_id, 'leave_recall_enabled') else '关闭'}",
                f"机器人全部回复撤回：{'开启' if service.enabled(session.group_id, 'bot_reply_recall_enabled') else '关闭'}（{service.number(session.group_id, 'bot_reply_recall_seconds')}秒）",
                f"撤回类型：{_format_recall_types(types)}",
                f"违禁词禁言：{service.number(session.group_id, 'forbidden_ban_seconds')} 秒",
                f"退群撤回条数：{service.number(session.group_id, 'leave_recall_limit')}",
            ]
        ),
    )


@on_command("开启群号撤回", only_group=True, description="开启本群群号撤回")
def enable_group_number_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "group_number_recall_enabled", True, "群号撤回")


@on_command("关闭群号撤回", only_group=True, description="关闭本群群号撤回")
def disable_group_number_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "group_number_recall_enabled", False, "群号撤回")


@on_command("开启自动撤回", only_group=True, description="开启本群自动类型撤回")
def enable_auto_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "auto_recall_enabled", True, "自动类型撤回")


@on_command("关闭自动撤回", only_group=True, description="关闭本群自动类型撤回")
def disable_auto_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "auto_recall_enabled", False, "自动类型撤回")


@on_command("开启红包撤回", only_group=True, description="开启本群红包撤回")
def enable_redbag_recall(event, ctx, session) -> None:
    _toggle_recall_type_command(event, ctx, session, "redbag", True)


@on_command("关闭红包撤回", only_group=True, description="关闭本群红包撤回")
def disable_redbag_recall(event, ctx, session) -> None:
    _toggle_recall_type_command(event, ctx, session, "redbag", False)


@on_command("开启退群撤回", only_group=True, description="开启本群退群撤回")
def enable_leave_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "leave_recall_enabled", True, "退群撤回")


@on_command("关闭退群撤回", only_group=True, description="关闭本群退群撤回")
def disable_leave_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "leave_recall_enabled", False, "退群撤回")


@on_command("开启机器人回复撤回", aliases=("开启机器人全部回复撤回", "开启全部回复撤回"), only_group=True, description="开启本群机器人全部回复撤回")
def enable_bot_reply_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "bot_reply_recall_enabled", True, "机器人全部回复撤回")


@on_command("关闭机器人回复撤回", aliases=("关闭机器人全部回复撤回", "关闭全部回复撤回"), only_group=True, description="关闭本群机器人全部回复撤回")
def disable_bot_reply_recall(event, ctx, session) -> None:
    _set_guard_enabled_command(event, ctx, session, "bot_reply_recall_enabled", False, "机器人全部回复撤回")


@on_command("设置撤回类型", aliases=("撤回类型",), only_group=True, description="设置撤回类型 图片 红包 链接 ...；不填则查看")
def set_recall_types(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argument.strip():
        ctx.reply(event, f"当前撤回类型：{_format_recall_types(_recall_types(ctx, session.group_id))}")
        return
    parsed = _parse_recall_types(session.argument)
    if not parsed:
        ctx.reply(event, "没有识别到有效撤回类型。可用：图片、视频、链接、JSON、XML、卡片、红包、小程序、邮箱。")
        return
    _set_recall_types(ctx, session.group_id, parsed)
    GroupSettingService(ctx).set_enabled(session.group_id, "auto_recall_enabled", bool(parsed))
    ctx.reply(event, f"已设置本群撤回类型：{_format_recall_types(parsed)}。")


@on_command("设置违禁词禁言", aliases=("违禁词禁言",), only_group=True, description="设置违禁词禁言 <秒>")
def set_forbidden_ban_seconds(event, ctx, session) -> None:
    _set_guard_number_command(event, ctx, session, "forbidden_ban_seconds", "违禁词禁言秒数")


@on_command("设置退群撤回条数", aliases=("退群撤回条数",), only_group=True, description="设置退群撤回条数 <数量>")
def set_leave_recall_limit(event, ctx, session) -> None:
    _set_guard_number_command(event, ctx, session, "leave_recall_limit", "退群撤回条数")


@on_command("设置机器人回复撤回秒数", aliases=("设置机器人全部回复撤回秒数", "机器人回复撤回秒数", "全部回复撤回秒数"), only_group=True, description="设置机器人回复撤回秒数 <秒>")
def set_bot_reply_recall_seconds(event, ctx, session) -> None:
    _set_guard_number_command(event, ctx, session, "bot_reply_recall_seconds", "机器人全部回复撤回秒数")


def _member_command(event, ctx, session, scope: str, list_type: str, action: str, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    guard = MemberGuardService(ctx)
    user_ids = guard.parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    group_id = session.group_id if scope == "group" else ""
    if action == "add":
        count = guard.add_members(scope, group_id, list_type, user_ids)
        verb = "添加"
    else:
        count = guard.remove_members(scope, group_id, list_type, user_ids)
        verb = "删除"
    ctx.reply(event, f"已{verb}{label}：{count} 个。")


def _clear_members_command(event, ctx, session, scope: str, list_type: str, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    group_id = session.group_id if scope == "group" else ""
    count = MemberGuardService(ctx).clear_members(scope, group_id, list_type)
    ctx.reply(event, f"已清空{label}：{count} 个。")


def _word_command(event, ctx, session, scope: str, action: str, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    guard = MemberGuardService(ctx)
    words = guard.parse_words(session.argument)
    if not words:
        ctx.reply(event, "没有识别到有效词条。")
        return
    group_id = session.group_id if scope == "group" else ""
    if action == "add":
        count = guard.add_words(scope, group_id, words)
        verb = "添加"
    else:
        count = guard.remove_words(scope, group_id, words)
        verb = "删除"
    ctx.reply(event, f"已{verb}{label}：{count} 个。")


def _clear_words_command(event, ctx, session, scope: str, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    group_id = session.group_id if scope == "group" else ""
    count = MemberGuardService(ctx).clear_words(scope, group_id)
    ctx.reply(event, f"已清空{label}：{count} 个。")


def _set_guard_enabled_command(event, ctx, session, key: str, enabled: bool, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    GroupSettingService(ctx).set_enabled(session.group_id, key, enabled)
    ctx.reply(event, f"已{'开启' if enabled else '关闭'}本群{label}。")


def _set_guard_number_command(event, ctx, session, key: str, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    try:
        value = int(str(session.argument or "").strip())
    except (TypeError, ValueError):
        ctx.reply(event, f"格式：设置{label} <数字>")
        return
    if value <= 0:
        ctx.reply(event, f"{label}必须大于 0。")
        return
    GroupSettingService(ctx).set_number(session.group_id, key, value)
    ctx.reply(event, f"已设置本群{label}：{value}。")


def _toggle_recall_type_command(event, ctx, session, recall_type: str, enabled: bool) -> None:
    if not _require_admin(event, ctx, session):
        return
    types = set(_recall_types(ctx, session.group_id))
    if enabled:
        types.add(recall_type)
    else:
        types.discard(recall_type)
    selected = sorted(types, key=lambda item: _RECALL_TYPE_ORDER.index(item) if item in _RECALL_TYPE_ORDER else 999)
    _set_recall_types(ctx, session.group_id, selected)
    GroupSettingService(ctx).set_enabled(session.group_id, "auto_recall_enabled", bool(selected))
    ctx.reply(event, f"已{'开启' if enabled else '关闭'}本群{_RECALL_TYPE_LABELS.get(recall_type, recall_type)}撤回。")


_RECALL_TYPE_LABELS = {
    "image": "图片",
    "video": "视频",
    "url": "链接",
    "json": "JSON",
    "xml": "XML",
    "card": "卡片",
    "redbag": "红包",
    "miniapp": "小程序",
    "email": "邮箱",
}
_RECALL_TYPE_ORDER = tuple(_RECALL_TYPE_LABELS.keys())
_RECALL_TYPE_ALIASES = {
    "图片": "image",
    "image": "image",
    "img": "image",
    "视频": "video",
    "video": "video",
    "链接": "url",
    "网址": "url",
    "url": "url",
    "json": "json",
    "JSON": "json",
    "xml": "xml",
    "XML": "xml",
    "卡片": "card",
    "卡片消息": "card",
    "card": "card",
    "红包": "redbag",
    "redbag": "redbag",
    "redpacket": "redbag",
    "小程序": "miniapp",
    "miniapp": "miniapp",
    "邮箱": "email",
    "邮件": "email",
    "email": "email",
}


def _parse_recall_types(text: str) -> list[str]:
    result: list[str] = []
    for part in re.split(r"[,，、\s]+", str(text or "")):
        key = _RECALL_TYPE_ALIASES.get(part.strip(), _RECALL_TYPE_ALIASES.get(part.strip().lower(), ""))
        if key and key not in result:
            result.append(key)
    return result


def _recall_types(ctx, group_id: str) -> list[str]:
    values = GroupSettingService(ctx).group_value(group_id, PLUGIN_ID, "recall_message_types", "recall_message_types", [])
    selected = _string_set(values)
    return [key for key in _RECALL_TYPE_ORDER if key in selected]


def _set_recall_types(ctx, group_id: str, values: list[str]) -> None:
    GroupSettingService(ctx).set_group_value(group_id, PLUGIN_ID, "recall_message_types", list(values))


def _format_recall_types(values: list[str]) -> str:
    return "、".join(_RECALL_TYPE_LABELS.get(item, item) for item in values) if values else "无"


def _format_values(values: list[str]) -> str:
    return "、".join(str(item) for item in values) if values else "无"


def _matches_auto_recall_type(message, ctx, group_id: str, *, detected_types: set[str] | None = None) -> bool:
    if not _guard_bool(ctx, group_id, "auto_recall_enabled"):
        return False
    enabled_types = _string_set(
        GroupSettingService(ctx).group_value(group_id, PLUGIN_ID, "recall_message_types", "recall_message_types", [])
    )
    if not enabled_types:
        return False
    if detected_types is None:
        detected_types = _detect_recall_types(message)
    return bool(enabled_types.intersection(detected_types))


def _matches_group_number_recall(message, ctx, group_id: str) -> bool:
    if not _guard_bool(ctx, group_id, "group_number_recall_enabled"):
        return False
    if getattr(message, "message_type", "") != "group":
        return False
    text = _message_blob(message)
    if not text:
        return False
    lowered = _normalized_recall_text(text)
    normalized = _compact_group_number_text(lowered)
    if any(token in normalized for token in ("qun.qq.com", "jq.qq.com", "qm.qq.com", "groupwpa", "m.q.qq.com")):
        return True
    patterns = (
        r"(?:qq群|q群|群号|群聊|交流群|玩家群|福利群|加群|进群|入群|裙号|裙)\D{0,12}\d{5,12}",
        r"\d{5,12}\D{0,12}(?:qq群|q群|群号|群聊|交流群|玩家群|福利群|加群|进群|入群|裙号|裙)",
    )
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in patterns):
        return True
    return False


_GROUP_DIGIT_TRANS = str.maketrans(
    {
        "０": "0",
        "１": "1",
        "２": "2",
        "３": "3",
        "４": "4",
        "５": "5",
        "６": "6",
        "７": "7",
        "８": "8",
        "９": "9",
        "⓪": "0",
        "①": "1",
        "②": "2",
        "③": "3",
        "④": "4",
        "⑤": "5",
        "⑥": "6",
        "⑦": "7",
        "⑧": "8",
        "⑨": "9",
        "⓿": "0",
        "❶": "1",
        "❷": "2",
        "❸": "3",
        "❹": "4",
        "❺": "5",
        "❻": "6",
        "❼": "7",
        "❽": "8",
        "❾": "9",
        "➊": "1",
        "➋": "2",
        "➌": "3",
        "➍": "4",
        "➎": "5",
        "➏": "6",
        "➐": "7",
        "➑": "8",
        "➒": "9",
    }
)


def _compact_group_number_text(text: str) -> str:
    normalized = str(text or "").translate(_GROUP_DIGIT_TRANS)
    return re.sub(r"(?<=\d)[\s,，.。·、_\-]+(?=\d)", "", normalized)


def _message_blob(message) -> str:
    parts = [str(getattr(message, "raw_message", "") or ""), str(getattr(message, "text", "") or "")]
    for segment in getattr(message, "segments", ()) or ():
        segment_type = str(getattr(segment, "type", "") or "")
        data = getattr(segment, "data", {}) or {}
        if segment_type == "at":
            continue
        if isinstance(data, dict):
            parts.extend(str(value) for value in data.values() if value is not None)
        else:
            parts.append(str(data))
    return " ".join(part for part in parts if part)


def _detect_recall_types(message, raw_event=None) -> set[str]:
    result: set[str] = set()
    raw_text = f"{getattr(message, 'raw_message', '') or ''} {getattr(message, 'text', '') or ''}"
    lowered_text = _normalized_recall_text(raw_text)
    segments = tuple(getattr(message, "segments", ()) or ())
    visible_parts = [str(getattr(message, "text", "") or "")]
    for segment in segments:
        segment_type = _normalized_segment_type(getattr(segment, "type", ""))
        data = getattr(segment, "data", {}) or {}
        data_text = _normalized_recall_text(data)
        if segment_type == "text" and isinstance(data, dict):
            visible_parts.append(str(data.get("text") or ""))
        if segment_type in {"image", "mface", "marketface", "market_face", "flash_image"}:
            result.add("image")
        if segment_type in {"video", "shortvideo", "short_video"}:
            result.add("video")
        if segment_type in {"json", "lightapp", "light_app", "ark"}:
            result.add("json")
        if segment_type in {"xml", "rich"}:
            result.add("xml")
        if segment_type in {"json", "xml", "lightapp", "light_app", "ark", "rich"}:
            result.add("card")
        if segment_type in {"card", "forward", "node", "share", "music", "contact", "location", "markdown", "keyboard"} or (
            segment_type not in {"text", "at"} and "card" in data_text
        ):
            result.add("card")
        if _looks_like_redbag(segment_type, data_text, allow_plain_words=segment_type not in {"text"}):
            result.add("redbag")
        if segment_type in {"miniapp", "mini_program", "miniprogram", "mini_program_app"} or (
            segment_type not in {"text", "at"}
            and any(token in data_text for token in ("miniapp", "mini_program", "miniprogram", "小程序"))
        ):
            result.add("miniapp")
        if segment_type in {"share", "url", "link"} and _segment_url(data):
            result.add("url")
    visible_text = " ".join(part for part in visible_parts if part)
    lowered_visible_text = _normalized_recall_text(visible_text)
    if "http://" in lowered_visible_text or "https://" in lowered_visible_text:
        result.add("url")
    if _looks_like_redbag("", lowered_text, allow_plain_words=False):
        result.add("redbag")
    if _looks_like_napcat_wallet_payload(raw_event):
        result.add("redbag")
    if re.search(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", visible_text):
        result.add("email")
    return result


def _looks_like_napcat_wallet_payload(raw_event) -> bool:
    if not isinstance(raw_event, dict):
        return False
    if str(raw_event.get("post_type") or "") != "message":
        return False
    if str(raw_event.get("message_type") or raw_event.get("detail_type") or "") != "group":
        return False
    if "message" not in raw_event or "raw_message" not in raw_event:
        return False
    if raw_event.get("message") != [] or str(raw_event.get("raw_message") or ""):
        return False
    if str(raw_event.get("message_format") or "").lower() != "array":
        return False
    if str(raw_event.get("sub_type") or "normal").lower() not in {"", "normal"}:
        return False
    return raw_event.get("message_id") is not None


def _normalized_segment_type(value) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _segment_url(data) -> str:
    if not isinstance(data, dict):
        return ""
    for key in ("url", "jump_url", "jumpUrl", "jumpurl", "content_url", "contentUrl"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def _normalized_recall_text(value) -> str:
    text = str(value or "").lower()
    if not text:
        return ""
    try:
        decoded = bytes(text, "utf-8").decode("unicode_escape").lower()
    except Exception:
        decoded = ""
    return f"{text} {decoded}" if decoded and decoded != text else text


def _looks_like_redbag(segment_type: str, text: str, *, allow_plain_words: bool = False) -> bool:
    segment_type = str(segment_type or "").lower()
    blob = _normalized_recall_text(text)
    if segment_type in {"redbag", "red_packet", "redpacket", "hongbao", "qq_redbag", "qq_wallet"}:
        return True
    technical_keywords = (
        "redbag",
        "red_packet",
        "redpacket",
        "hongbao",
        "lucky_money",
        "luckymoney",
        "qqwallet",
        "qq_wallet",
        "qwallet",
        "tenpay",
        "qqpay",
        "wallet/red",
        "wallet?",
        "com.tencent.qqwallet",
        "com.tencent.mobileqq.qwallet",
        "com.tencent.redpacket",
    )
    if any(keyword in blob for keyword in technical_keywords):
        return True
    if allow_plain_words:
        return any(keyword in blob for keyword in ("红包", "口令红包", "拼手气"))
    return False


def _string_set(value) -> set[str]:
    if isinstance(value, (list, tuple, set)):
        return {str(item).strip() for item in value if str(item).strip()}
    if isinstance(value, str):
        return {item.strip() for item in re.split(r"[,，\s]+", value) if item.strip()}
    return set()


def _remember_group_message(ctx, group_id: str, user_id: str, message_id) -> None:
    group_id = str(group_id or "")
    user_id = str(user_id or "")
    if not group_id or not user_id:
        return
    cache = _message_cache(ctx)
    key = _message_cache_key(group_id, user_id)
    recent = [item for item in cache.get(key, []) if str(item) != str(message_id)]
    recent.append(_coerce_message_id(message_id))
    limit = _guard_number(ctx, group_id, "message_cache_limit_per_member", default=50, maximum=1000)
    cache[key] = recent[-limit:]
    ctx.set_state("recent_group_messages", cache)


def _message_cache(ctx) -> dict[str, list[object]]:
    value = ctx.get_state("recent_group_messages", {})
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[object]] = {}
    for key, items in value.items():
        if isinstance(items, list):
            result[str(key)] = list(items)
    return result


def _message_cache_key(group_id: str, user_id: str) -> str:
    return f"{group_id}:{user_id}"


def _coerce_message_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return str(value)


def _positive_int(value, *, default: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if number <= 0:
        return default
    return min(number, maximum)


def _response_ok(response) -> bool:
    if hasattr(response, "ok"):
        return bool(response.ok)
    if isinstance(response, dict):
        return bool(response.get("ok") or response.get("status") == "ok" or response.get("retcode") == 0)
    return bool(response)


def _response_data(response):
    if hasattr(response, "data"):
        return response.data
    if isinstance(response, dict):
        return response.get("data", response)
    return response


def _delete_message(ctx, message_id, group_id: str, user_id: str, reason: str):
    response = ctx.delete_msg(message_id)
    if not _response_ok(response):
        detail = getattr(response, "message", "") or _response_data(response) or response
        ctx.log(
            f"成员消息撤回失败：群 {group_id}，成员 {user_id}，消息 {message_id}，规则 {reason}，返回 {detail}",
            level="warning",
        )
    return response


def _member_user_id(member) -> str:
    if not isinstance(member, dict):
        return ""
    value = member.get("user_id") or member.get("uin") or member.get("qq")
    return str(value or "")


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


def _member_guard_enabled(ctx, group_id: str) -> bool:
    return GroupSettingService(ctx).enabled(group_id, "member_guard_enabled")


def _recall_exempt(ctx, group_id: str, user_id: str) -> bool:
    if not str(user_id or "").strip():
        return False
    try:
        return PluginPermissionService(ctx).is_admin(user_id, group_id)
    except Exception as exc:
        ctx.log(f"管理人员撤回豁免判断失败：{exc}", level="warning")
        return False


def _guard_bool(ctx, group_id: str, key: str) -> bool:
    return GroupSettingService(ctx).enabled(group_id, key)


def _guard_number(ctx, group_id: str, key: str, *, default: int, maximum: int) -> int:
    value = GroupSettingService(ctx).number(group_id, key)
    return _positive_int(value, default=default, maximum=maximum)


MATCHERS.extend(
    [
        add_group_black,
        remove_group_black,
        add_group_white,
        remove_group_white,
        add_global_black,
        remove_global_black,
        add_global_white,
        remove_global_white,
        add_group_words,
        remove_group_words,
        add_global_words,
        remove_global_words,
        sweep_blacklist,
        list_member_guard,
        list_forbidden_words,
        clear_group_black,
        clear_group_white,
        clear_global_black,
        clear_global_white,
        clear_group_words,
        clear_global_words,
        recall_settings,
        enable_group_number_recall,
        disable_group_number_recall,
        enable_auto_recall,
        disable_auto_recall,
        enable_redbag_recall,
        disable_redbag_recall,
        enable_leave_recall,
        disable_leave_recall,
        enable_bot_reply_recall,
        disable_bot_reply_recall,
        set_recall_types,
        set_forbidden_ban_seconds,
        set_leave_recall_limit,
        set_bot_reply_recall_seconds,
    ]
)
EVENT_MATCHERS.append(recall_member_messages_on_leave)
