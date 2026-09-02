from __future__ import annotations

import re

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.permissions import PluginPermissionService, parse_user_ids


PLUGIN_ID = "moderation"
PLUGIN_NAME = "群管"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "提供禁言、踢人、全员禁言、群名片、群管理员和撤回等群管理命令。"
PLUGIN_CONFIG = {"owners": [], "admins": []}
PLUGIN_ADMIN_SCHEMA = [
    {
        "id": "moderation_commands",
        "label": "群管命令",
        "type": "runtime",
        "runtime_key": "commands",
        "commands": [
            "禁言 <QQ> <时长>",
            "解禁 <QQ>",
            "踢 <QQ>",
            "踢黑 <QQ>",
            "改名片 <QQ> <名片>",
            "改头衔 <QQ> <头衔>",
            "清头衔 <QQ>",
            "设管理员 <QQ>",
            "取消管理员 <QQ>",
            "改群名 <新群名>",
            "发公告 <内容>",
            "撤回消息 <message_id>",
        ],
    }
]
PLUGIN_ADMIN_HANDLERS = {"commands": lambda ctx: _help_text()}

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("群管插件已加载")


@on_command("群管帮助", aliases=("群管菜单", "群管命令"), only_group=True, description="查看群管命令")
def moderation_help(event, ctx, session) -> None:
    ctx.reply(event, _help_text())


@on_command("禁言", only_group=True, description="禁言 <QQ> <时长>")
def ban_member(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    duration = _parse_duration(session.argument, user_ids[0])
    if duration <= 0:
        duration = 600
    duration = min(duration, 30 * 24 * 60 * 60)
    response = ctx.set_group_ban(session.group_id, user_ids[0], duration)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已禁言 {user_ids[0]} {duration} 秒。")
    else:
        ctx.reply(event, f"禁言失败：{getattr(response, 'message', response)}")


@on_command("解禁", aliases=("解除禁言",), only_group=True, description="解禁 <QQ>")
def unban_member(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    response = ctx.set_group_ban(session.group_id, user_ids[0], 0)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已解除 {user_ids[0]} 的禁言。")
    else:
        ctx.reply(event, f"解禁失败：{getattr(response, 'message', response)}")


@on_command("踢", only_group=True, description="踢 <QQ>")
def kick_member(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    response = ctx.set_group_kick(session.group_id, user_ids[0], reject_add_request=False)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已踢出 {user_ids[0]}。")
    else:
        ctx.reply(event, f"踢人失败：{getattr(response, 'message', response)}")


@on_command("踢黑", aliases=("踢并拒绝", "踢出并拒绝", "拒绝踢"), only_group=True, description="踢黑 <QQ>，踢出并拒绝再次入群")
def kick_member_reject(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    response = ctx.set_group_kick(session.group_id, user_ids[0], reject_add_request=True)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已踢出并拒绝 {user_ids[0]} 再次申请。")
    else:
        ctx.reply(event, f"踢黑失败：{getattr(response, 'message', response)}")


@on_command("全员禁言", aliases=("开启全员禁言", "开启全体禁言", "全体禁言"), only_group=True, description="开启全员禁言")
def enable_whole_ban(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    response = ctx.set_group_whole_ban(session.group_id, True)
    if getattr(response, "ok", False):
        ctx.reply(event, "已开启全员禁言。")
    else:
        ctx.reply(event, f"开启全员禁言失败：{getattr(response, 'message', response)}")


@on_command("解除全员禁言", aliases=("关闭全员禁言", "关闭全体禁言", "全员解禁", "全体解禁"), only_group=True, description="关闭全员禁言")
def disable_whole_ban(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    response = ctx.set_group_whole_ban(session.group_id, False)
    if getattr(response, "ok", False):
        ctx.reply(event, "已关闭全员禁言。")
    else:
        ctx.reply(event, f"关闭全员禁言失败：{getattr(response, 'message', response)}")


@on_command("改名片", aliases=("设置名片", "群名片"), only_group=True, description="改名片 <QQ> <名片>")
def set_member_card(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    card = _tail_after_first_id(session.argument, user_ids[0])
    if not card:
        ctx.reply(event, "格式：改名片 <QQ> <名片>")
        return
    response = ctx.set_group_card(session.group_id, user_ids[0], card)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已设置 {user_ids[0]} 的群名片：{card}")
    else:
        ctx.reply(event, f"设置群名片失败：{getattr(response, 'message', response)}")


@on_command("改头衔", aliases=("设置头衔", "专属头衔"), only_group=True, description="改头衔 <QQ> <头衔>")
def set_member_special_title(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    title = _tail_after_first_id(session.argument, user_ids[0])
    if not title:
        ctx.reply(event, "格式：改头衔 <QQ> <头衔>")
        return
    response = ctx.set_group_special_title(session.group_id, user_ids[0], title, -1)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已设置 {user_ids[0]} 的专属头衔：{title}")
    else:
        ctx.reply(event, f"设置专属头衔失败：{getattr(response, 'message', response)}")


@on_command("清头衔", aliases=("清除头衔", "取消头衔"), only_group=True, description="清头衔 <QQ>")
def clear_member_special_title(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    response = ctx.set_group_special_title(session.group_id, user_ids[0], "", -1)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已清除 {user_ids[0]} 的专属头衔。")
    else:
        ctx.reply(event, f"清除专属头衔失败：{getattr(response, 'message', response)}")


@on_command("设管理员", aliases=("设置管理员", "加群管", "设群管"), only_group=True, description="设管理员 <QQ>")
def set_group_admin(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    response = ctx.set_group_admin(session.group_id, user_ids[0], True)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已设置 {user_ids[0]} 为群管理员。")
    else:
        ctx.reply(event, f"设置管理员失败：{getattr(response, 'message', response)}")


@on_command("取消管理员", aliases=("删群管", "删除管理员", "取消群管"), only_group=True, description="取消管理员 <QQ>")
def unset_group_admin(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    response = ctx.set_group_admin(session.group_id, user_ids[0], False)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已取消 {user_ids[0]} 的群管理员。")
    else:
        ctx.reply(event, f"取消管理员失败：{getattr(response, 'message', response)}")


@on_command("改群名", aliases=("设置群名",), only_group=True, description="改群名 <新群名>")
def set_group_name(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    group_name = session.argument.strip()
    if not group_name:
        ctx.reply(event, "格式：改群名 <新群名>")
        return
    response = ctx.set_group_name(session.group_id, group_name)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已设置群名：{group_name}")
    else:
        ctx.reply(event, f"设置群名失败：{getattr(response, 'message', response)}")


@on_command("发公告", aliases=("设置公告", "群公告"), only_group=True, description="发公告 <内容>")
def set_group_notice(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    content = session.argument.strip()
    if not content:
        ctx.reply(event, "格式：发公告 <内容>")
        return
    response = ctx.set_group_notice(session.group_id, content)
    if getattr(response, "ok", False):
        ctx.reply(event, "群公告已发送。")
    else:
        ctx.reply(event, f"发送群公告失败：{getattr(response, 'message', response)}")


@on_command("撤回消息", aliases=("撤回",), only_group=True, description="撤回消息 <message_id>")
def recall_message(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    match = re.search(r"\d+", session.argument)
    if not match:
        ctx.reply(event, "格式：撤回消息 <message_id>")
        return
    message_id = match.group(0)
    response = ctx.delete_msg(message_id)
    if getattr(response, "ok", False):
        ctx.reply(event, f"已撤回消息：{message_id}")
    else:
        ctx.reply(event, f"撤回消息失败：{getattr(response, 'message', response)}")


def _require_admin(event, ctx, session) -> bool:
    service = PluginPermissionService(ctx)
    ok, reason = service.require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


def _parse_duration(argument: str, user_id: str) -> int:
    tail = argument.replace(user_id, "", 1).strip()
    match = re.search(r"(\d+)\s*(天|日|小时|时|分钟|分|秒|d|h|m|min|s)?", tail, re.IGNORECASE)
    if match:
        value = int(match.group(1))
        unit = str(match.group(2) or "秒").lower()
        if unit in {"天", "日", "d"}:
            return value * 24 * 60 * 60
        if unit in {"小时", "时", "h"}:
            return value * 60 * 60
        if unit in {"分钟", "分", "m", "min"}:
            return value * 60
        return value
    return 600


def _tail_after_first_id(argument: str, user_id: str) -> str:
    return re.sub(rf"(^|\s){re.escape(str(user_id))}(\s|$)", " ", str(argument or ""), count=1).strip()


def _help_text() -> str:
    return "\n".join(
        [
            "群管命令：",
            "禁言 <QQ> <时长>（示例：10分钟/1小时/1天）",
            "解禁 <QQ>",
            "踢 <QQ> / 踢黑 <QQ>",
            "改名片 <QQ> <名片>",
            "改头衔 <QQ> <头衔> / 清头衔 <QQ>",
            "设管理员 <QQ> / 取消管理员 <QQ>",
            "改群名 <新群名>",
            "发公告 <内容>",
            "撤回消息 <message_id>",
        ]
    )


MATCHERS.extend(
    [
        moderation_help,
        ban_member,
        unban_member,
        kick_member,
        kick_member_reject,
        enable_whole_ban,
        disable_whole_ban,
        set_member_card,
        set_member_special_title,
        clear_member_special_title,
        set_group_admin,
        unset_group_admin,
        set_group_name,
        set_group_notice,
        recall_message,
    ]
)
