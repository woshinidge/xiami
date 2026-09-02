from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.permissions import PluginPermissionService, parse_user_ids


PLUGIN_ID = "onebot_tools"
PLUGIN_NAME = "OneBot 查询工具"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "提供群资料、成员资料和常用 OneBot 管理工具。"
PLUGIN_CONFIG = {"owners": [], "admins": []}

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("OneBot 查询工具插件已加载")


@on_command("机器人信息", aliases=("登录信息", "OneBot状态"), description="查询机器人登录和 OneBot 状态")
def bot_info(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    login = ctx.get_login_info()
    status = ctx.get_status()
    version = ctx.get_version()
    if not ctx.onebot_ok(login):
        ctx.reply(event, f"读取登录信息失败：{ctx.onebot_message(login)}")
        return
    login_data = ctx.onebot_data(login)
    if not isinstance(login_data, dict):
        ctx.reply(event, "读取登录信息失败：OneBot 返回格式不正确。")
        return
    nickname = login_data.get("nickname") or login_data.get("name") or "未知"
    user_id = login_data.get("user_id") or login_data.get("uin") or "未知"
    online = "正常" if ctx.onebot_ok(status) else f"异常：{ctx.onebot_message(status)}"
    version_data = ctx.onebot_data(version) if ctx.onebot_ok(version) else {}
    impl = version_data.get("app_name") or version_data.get("impl") or version_data.get("protocol_name") if isinstance(version_data, dict) else ""
    ctx.reply(event, f"机器人信息：{nickname}({user_id})\nOneBot：{online}\n实现：{impl or '未知'}")


@on_command("好友列表", aliases=("列好友",), description="列出好友摘要")
def friend_list(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    response = ctx.get_friend_list()
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取好友列表失败：{ctx.onebot_message(response)}")
        return
    data = ctx.onebot_data(response)
    if not isinstance(data, list):
        ctx.reply(event, "读取好友列表失败：OneBot 返回格式不正确。")
        return
    limit = _limit_from_session(session, default=8)
    lines = [f"好友列表：共 {len(data)} 个"]
    for item in data[:limit]:
        if not isinstance(item, dict):
            continue
        user_id = item.get("user_id") or item.get("uin") or "未知"
        nickname = item.get("nickname") or item.get("remark") or item.get("name") or "未知"
        lines.append(f"- {nickname}({user_id})")
    ctx.reply(event, "\n".join(lines))


@on_command("群列表", aliases=("列群",), description="列出群摘要")
def group_list(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    response = ctx.get_group_list()
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取群列表失败：{ctx.onebot_message(response)}")
        return
    data = ctx.onebot_data(response)
    if not isinstance(data, list):
        ctx.reply(event, "读取群列表失败：OneBot 返回格式不正确。")
        return
    limit = _limit_from_session(session, default=8)
    lines = [f"群列表：共 {len(data)} 个"]
    for item in data[:limit]:
        if not isinstance(item, dict):
            continue
        group_id = item.get("group_id") or item.get("gid") or "未知"
        name = item.get("group_name") or item.get("name") or "未知"
        member_count = item.get("member_count", "未知")
        lines.append(f"- {name}({group_id}) 成员:{member_count}")
    ctx.reply(event, "\n".join(lines))


@on_command("群信息", aliases=("查询群信息",), only_group=True, description="群信息 [群号]")
def group_info(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    group_id = session.argv[0] if session.argv else session.group_id
    response = ctx.get_group_info(group_id)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取群信息失败：{ctx.onebot_message(response)}")
        return
    data = ctx.onebot_data(response)
    if not isinstance(data, dict):
        ctx.reply(event, "读取群信息失败：OneBot 返回格式不正确。")
        return
    name = data.get("group_name") or data.get("name") or "未知"
    member_count = data.get("member_count", "未知")
    max_member_count = data.get("max_member_count", "未知")
    ctx.reply(event, f"群信息：{name}({data.get('group_id', group_id)})\n成员：{member_count}/{max_member_count}")


@on_command("查成员", aliases=("成员信息", "查询成员"), only_group=True, description="查成员 <QQ>")
def member_info(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "格式：查成员 <QQ>")
        return
    user_id = user_ids[0]
    response = ctx.get_group_member_info(session.group_id, user_id)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取成员信息失败：{ctx.onebot_message(response)}")
        return
    data = ctx.onebot_data(response)
    if not isinstance(data, dict):
        ctx.reply(event, "读取成员信息失败：OneBot 返回格式不正确。")
        return
    nickname = data.get("card") or data.get("nickname") or "未知"
    role = data.get("role") or "unknown"
    title = data.get("title") or data.get("special_title") or ""
    suffix = f"\n头衔：{title}" if title else ""
    ctx.reply(event, f"成员信息：{nickname}({data.get('user_id', user_id)})\n角色：{role}{suffix}")


@on_command("群成员列表", aliases=("成员列表", "群成员"), only_group=True, description="群成员列表 [数量]")
def group_member_list(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    response = ctx.get_group_member_list(session.group_id)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取群成员列表失败：{ctx.onebot_message(response)}")
        return
    data = ctx.onebot_data(response)
    if not isinstance(data, list):
        ctx.reply(event, "读取群成员列表失败：OneBot 返回格式不正确。")
        return
    limit = _limit_from_session(session, default=10, maximum=50)
    lines = [f"群成员列表：共 {len(data)} 人，显示前 {min(len(data), limit)} 人"]
    for item in data[:limit]:
        if not isinstance(item, dict):
            continue
        user_id = item.get("user_id") or item.get("uin") or "未知"
        nickname = item.get("card") or item.get("nickname") or item.get("name") or "未知"
        role = item.get("role") or "unknown"
    lines.append(f"- {nickname}({user_id}) {role}")
    ctx.reply(event, "\n".join(lines))


@on_command("设置群头衔", aliases=("设头衔", "设置头衔"), only_group=True, description="设置群头衔 <QQ> <头衔> [秒数]")
def set_member_title(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids or len(session.argv) < 2:
        ctx.reply(event, "格式：设置群头衔 <QQ> <头衔> [秒数]")
        return
    user_id = user_ids[0]
    title = session.argv[1]
    duration = -1
    if len(session.argv) >= 3:
        try:
            duration = int(session.argv[2])
        except ValueError:
            ctx.reply(event, "头衔有效期必须是秒数。")
            return
    response = ctx.set_group_special_title(session.group_id, user_id, title, duration=duration)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"设置群头衔失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, f"设置群头衔成功：{user_id} -> {title}")


@on_command("清除群头衔", aliases=("清头衔", "删除头衔"), only_group=True, description="清除群头衔 <QQ>")
def clear_member_title(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "格式：清除群头衔 <QQ>")
        return
    user_id = user_ids[0]
    response = ctx.set_group_special_title(session.group_id, user_id, "", duration=-1)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"清除群头衔失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, f"清除群头衔成功：{user_id}")


@on_command("QQ资料", aliases=("查QQ", "陌生人信息"), description="QQ资料 <QQ>")
def stranger_info(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "格式：QQ资料 <QQ>")
        return
    user_id = user_ids[0]
    response = ctx.get_stranger_info(user_id, no_cache=False)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取 QQ 资料失败：{ctx.onebot_message(response)}")
        return
    data = ctx.onebot_data(response)
    if not isinstance(data, dict):
        ctx.reply(event, "读取 QQ 资料失败：OneBot 返回格式不正确。")
        return
    nickname = data.get("nickname") or data.get("name") or "未知"
    sex = data.get("sex") or "unknown"
    age = data.get("age", "未知")
    ctx.reply(event, f"QQ资料：{nickname}({data.get('user_id', user_id)})\n性别：{sex}\n年龄：{age}")


@on_command("赞", aliases=("点赞",), description="赞 <QQ> [次数]")
def send_like(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "格式：赞 <QQ> [次数]")
        return
    times = 1
    if len(session.argv) >= 2:
        try:
            times = max(1, min(int(session.argv[1]), 10))
        except ValueError:
            times = 1
    response = ctx.send_like(user_ids[0], times=times)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"点赞失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, f"点赞成功：{user_ids[0]} x{times}")


@on_command("撤回消息", aliases=("撤回",), only_group=True, description="撤回消息 <message_id>")
def delete_message(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "格式：撤回消息 <message_id>")
        return
    response = ctx.delete_msg(session.argv[0])
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"撤回失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, f"撤回成功：{session.argv[0]}")


@on_command("戳一戳", aliases=("戳",), only_group=True, description="戳一戳 <QQ>")
def send_poke(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "格式：戳一戳 <QQ>")
        return
    response = ctx.send_poke(user_ids[0], group_id=session.group_id)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"戳一戳失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, f"戳一戳成功：{user_ids[0]}")


@on_command("设精华", aliases=("设置精华",), only_group=True, description="设精华 <message_id>")
def set_essence(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "格式：设精华 <message_id>")
        return
    response = ctx.set_essence_msg(session.argv[0])
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"设置精华失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, f"设置精华成功：{session.argv[0]}")


@on_command("删精华", aliases=("删除精华",), only_group=True, description="删精华 <message_id>")
def delete_essence(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "格式：删精华 <message_id>")
        return
    response = ctx.delete_essence_msg(session.argv[0])
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"删除精华失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, f"删除精华成功：{session.argv[0]}")


@on_command("群公告", aliases=("发群公告",), only_group=True, description="群公告 <内容>")
def set_group_notice(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    content = session.argument.strip()
    if not content:
        ctx.reply(event, "格式：群公告 <内容>")
        return
    if content in {"列表", "记录", "查询"}:
        _reply_group_notice_list(event, ctx, session.group_id)
        return
    response = ctx.set_group_notice(session.group_id, content)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"发送群公告失败：{ctx.onebot_message(response)}")
        return
    ctx.reply(event, "群公告已发送。")


@on_command("群公告列表", aliases=("查群公告", "群公告记录"), only_group=True, description="群公告列表")
def group_notice_list(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    _reply_group_notice_list(event, ctx, session.group_id)


def _reply_group_notice_list(event, ctx, group_id: str) -> None:
    response = ctx.get_group_notice(group_id)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取群公告失败：{ctx.onebot_message(response)}")
        return
    notices = ctx.onebot_data(response)
    if not isinstance(notices, list):
        ctx.reply(event, "读取群公告失败：OneBot 返回格式不正确。")
        return
    if not notices:
        ctx.reply(event, "暂无群公告。")
        return
    lines = ["群公告列表："]
    for index, notice in enumerate(notices[:5], start=1):
        if not isinstance(notice, dict):
            continue
        title = str(notice.get("title") or notice.get("content") or notice.get("text") or "无标题")
        sender = notice.get("sender_id") or notice.get("user_id") or notice.get("sender") or "未知"
        if len(title) > 40:
            title = title[:37] + "..."
        lines.append(f"{index}. {title} / 发布者：{sender}")
    ctx.reply(event, "\n".join(lines))


@on_command("群荣誉", aliases=("群荣耀",), only_group=True, description="群荣誉 [类型]")
def group_honor(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    honor_type = session.argv[0] if session.argv else "all"
    response = ctx.get_group_honor_info(session.group_id, honor_type=honor_type)
    if not ctx.onebot_ok(response):
        ctx.reply(event, f"读取群荣誉失败：{ctx.onebot_message(response)}")
        return
    data = ctx.onebot_data(response)
    if not isinstance(data, dict):
        ctx.reply(event, "读取群荣誉失败：OneBot 返回格式不正确。")
        return
    current_talkative = data.get("current_talkative")
    talkative = "无"
    if isinstance(current_talkative, dict):
        talkative = f"{current_talkative.get('nickname') or '未知'}({current_talkative.get('user_id') or '未知'})"
    active_count = len(data.get("talkative_list") or []) if isinstance(data.get("talkative_list"), list) else 0
    ctx.reply(event, f"群荣誉：当前龙王 {talkative}\n历史活跃：{active_count} 人")


def _limit_from_session(session, default: int = 8, maximum: int = 30) -> int:
    if not session.argv:
        return default
    try:
        value = int(session.argv[0])
    except ValueError:
        return default
    return max(1, min(value, maximum))


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


MATCHERS.extend(
    [
        bot_info,
        friend_list,
        group_list,
        group_info,
        member_info,
        group_member_list,
        set_member_title,
        clear_member_title,
        stranger_info,
        send_like,
        delete_message,
        send_poke,
        set_essence,
        delete_essence,
        set_group_notice,
        group_notice_list,
        group_honor,
    ]
)
