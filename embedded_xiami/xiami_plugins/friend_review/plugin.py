from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.friend_review import FriendReviewService, parse_mode, parse_words
from xiami_core.plugins.permissions import PluginPermissionService, parse_user_ids


PLUGIN_ID = "friend_review"
PLUGIN_NAME = "好友审核"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "提供好友申请审核，支持自动同意、拒绝、人工通知和手动处理。"
PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
    "friend_review_enabled": False,
    "friend_review_mode": "manual",
    "friend_auto_approve_keywords": [],
    "friend_auto_reject_keywords": [],
    "friend_auto_approve_users": [],
    "friend_auto_reject_users": [],
    "friend_notify_users": [],
    "friend_reject_reason": "不接受陌生好友申请。",
    "friend_approve_remark": "",
}

PLUGIN_ADMIN_SCHEMA = [
    {"id": "enabled", "label": "好友审核开关", "type": "state", "state_key": "friend_review_enabled", "commands": ["开启好友审核", "关闭好友审核"]},
    {"id": "mode", "label": "好友审核模式", "type": "state", "state_key": "friend_review_mode", "commands": ["好友审核模式"]},
    {"id": "approve_keywords", "label": "好友自动同意关键词", "type": "state", "state_key": "friend_auto_approve_keywords", "commands": ["好友同意关键词"]},
    {"id": "reject_keywords", "label": "好友自动拒绝关键词", "type": "state", "state_key": "friend_auto_reject_keywords", "commands": ["好友拒绝关键词"]},
    {"id": "approve_users", "label": "好友自动同意 QQ", "type": "state", "state_key": "friend_auto_approve_users", "commands": ["好友同意QQ"]},
    {"id": "reject_users", "label": "好友自动拒绝 QQ", "type": "state", "state_key": "friend_auto_reject_users", "commands": ["好友拒绝QQ"]},
    {"id": "notify_users", "label": "好友审核通知 QQ", "type": "state", "state_key": "friend_notify_users", "commands": ["好友审核通知"]},
    {"id": "reject_reason", "label": "好友拒绝理由", "type": "state", "state_key": "friend_reject_reason", "commands": ["设置好友拒绝理由"]},
    {"id": "approve_remark", "label": "好友同意备注", "type": "state", "state_key": "friend_approve_remark", "commands": ["设置好友同意备注"]},
    {"id": "records", "label": "好友审核记录", "type": "state", "state_key": "friend_review_records", "commands": ["好友审核记录", "导出好友审核记录", "清空好友审核记录"]},
    {"id": "admins", "label": "好友审核管理员", "type": "config", "config_key": "admins"},
]

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("好友审核插件已加载")


def on_event(event, ctx) -> None:
    raw = event.raw
    if str(raw.get("post_type") or event.type) == "request" and str(raw.get("request_type") or "") == "friend":
        _handle_friend_request(event, ctx)


@on_command("好友审核状态", aliases=("好友申请状态",), description="查看好友审核配置")
def friend_review_status(event, ctx, session) -> None:
    ctx.reply(event, FriendReviewService(ctx).summary())


@on_command("开启好友审核", description="开启好友申请审核")
def enable_friend_review(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    FriendReviewService(ctx).set_enabled(True)
    ctx.reply(event, "已开启好友审核。")


@on_command("关闭好友审核", description="关闭好友申请审核")
def disable_friend_review(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    FriendReviewService(ctx).set_enabled(False)
    ctx.reply(event, "已关闭好友审核。")


@on_command("好友审核模式", description="设置好友审核模式：人工/同意/拒绝")
def set_friend_review_mode(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    mode = parse_mode(session.argument)
    FriendReviewService(ctx).set_mode(mode)
    labels = {"manual": "人工审核", "approve": "自动同意", "reject": "自动拒绝"}
    ctx.reply(event, f"好友审核模式已设置为：{labels.get(mode, '人工审核')}。")


@on_command("好友同意词", aliases=("设置好友同意词",), description="设置好友申请自动同意关键词")
def set_approve_words(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    words = parse_words(session.argument)
    FriendReviewService(ctx).set_approve_keywords(words)
    ctx.reply(event, f"已设置好友自动同意词：{', '.join(words) if words else '无'}。")


@on_command("好友拒绝词", aliases=("设置好友拒绝词",), description="设置好友申请自动拒绝关键词")
def set_reject_words(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    words = parse_words(session.argument)
    FriendReviewService(ctx).set_reject_keywords(words)
    ctx.reply(event, f"已设置好友自动拒绝词：{', '.join(words) if words else '无'}。")


@on_command("好友同意QQ", aliases=("设置好友同意QQ", "好友同意名单"), description="设置好友申请自动同意 QQ")
def set_approve_users(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    users = parse_user_ids(session.argument)
    FriendReviewService(ctx).set_approve_users(users)
    ctx.reply(event, f"已设置好友自动同意QQ：{'、'.join(users) if users else '无'}。")


@on_command("好友拒绝QQ", aliases=("设置好友拒绝QQ", "好友拒绝名单"), description="设置好友申请自动拒绝 QQ")
def set_reject_users(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    users = parse_user_ids(session.argument)
    FriendReviewService(ctx).set_reject_users(users)
    ctx.reply(event, f"已设置好友自动拒绝QQ：{'、'.join(users) if users else '无'}。")


@on_command("好友审核通知", aliases=("设置好友审核通知",), description="设置好友申请人工审核通知 QQ")
def set_notify_users(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    users = parse_user_ids(session.argument)
    FriendReviewService(ctx).set_notify_users(users)
    ctx.reply(event, f"已设置好友审核通知账号：{'、'.join(users) if users else '无'}。")


@on_command("设置好友拒绝理由", aliases=("好友拒绝理由",), description="设置好友申请默认拒绝理由")
def set_reject_reason(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    reason = str(session.argument or "").strip()
    if not reason:
        ctx.reply(event, "用法：设置好友拒绝理由 <理由>")
        return
    FriendReviewService(ctx).set_reject_reason(reason)
    ctx.reply(event, f"好友默认拒绝理由已设置：{reason}")


@on_command("设置好友同意备注", aliases=("好友同意备注",), description="设置好友申请默认同意备注")
def set_approve_remark(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    remark = str(session.argument or "").strip()
    FriendReviewService(ctx).set_approve_remark(remark)
    ctx.reply(event, f"好友默认同意备注已设置：{remark or '空'}")


@on_command("重置好友审核", aliases=("恢复好友审核默认",), description="恢复好友审核默认设置")
def reset_friend_review(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    FriendReviewService(ctx).reset()
    ctx.reply(event, "好友审核设置已恢复默认。")


@on_command("同意好友", description="手动同意好友申请：同意好友 <flag> [备注]")
def approve_friend(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "用法：同意好友 <flag> [备注]")
        return
    flag = session.argv[0]
    remark = " ".join(session.argv[1:]) or FriendReviewService(ctx).approve_remark()
    response = ctx.set_friend_add_request(flag, True, remark)
    _record(ctx, "manual_approve", user_id="", flag=flag, reason=remark)
    ctx.reply(event, f"已提交同意好友申请：{response}")


@on_command("拒绝好友", description="手动拒绝好友申请：拒绝好友 <flag> [理由]")
def reject_friend(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "用法：拒绝好友 <flag> [理由]")
        return
    flag = session.argv[0]
    reason = " ".join(session.argv[1:]) or FriendReviewService(ctx).reject_reason()
    response = ctx.set_friend_add_request(flag, False, reason)
    _record(ctx, "manual_reject", user_id="", flag=flag, reason=reason)
    ctx.reply(event, f"已提交拒绝好友申请：{response}")


@on_command("好友审核记录", aliases=("好友申请记录",), description="查看最近好友审核记录")
def friend_review_records(event, ctx, session) -> None:
    records = FriendReviewService(ctx).recent_records(limit=20, query=session.argument)[:8]
    if not records:
        ctx.reply(event, "暂无好友审核记录。")
        return
    suffix = f"（筛选：{session.argument}）" if str(session.argument or "").strip() else ""
    lines = [f"最近好友审核记录{suffix}："]
    for item in records:
        lines.append(
            f"- {item.get('time', '')} {item.get('action', '')} user={item.get('user_id', '')} "
            f"flag={item.get('flag', '')} reason={item.get('reason', '')}"
        )
    ctx.reply(event, "\n".join(lines))


@on_command("导出好友审核记录", aliases=("好友审核导出",), description="导出最近好友审核记录")
def export_friend_review_records(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    text = FriendReviewService(ctx).export_records(session.argument, limit=200)
    ctx.reply(event, "好友审核记录导出：\n" + text)


@on_command("清空好友审核记录", aliases=("清空好友申请记录",), description="清空好友审核记录")
def clear_friend_review_records(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    FriendReviewService(ctx).clear_records()
    ctx.reply(event, "好友审核记录已清空。")


def _handle_friend_request(event, ctx) -> None:
    raw = event.raw
    flag = str(raw.get("flag") or "")
    user_id = str(raw.get("user_id") or "")
    comment = str(raw.get("comment") or "")
    if not flag or not user_id:
        return

    service = FriendReviewService(ctx)
    decision = service.decide(user_id, comment)
    if decision.action == "ignore":
        return
    if decision.action == "approve":
        response = ctx.set_friend_add_request(flag, True, decision.remark)
        ctx.log(f"好友审核同意：user={user_id} reason={decision.reason} result={response}")
        _record(ctx, "approve", user_id=user_id, flag=flag, comment=comment, reason=decision.reason)
        _notify(ctx, service, f"好友申请已自动同意：{user_id}\n原因：{decision.reason}")
        return
    if decision.action == "reject":
        response = ctx.set_friend_add_request(flag, False, decision.reason)
        ctx.log(f"好友审核拒绝：user={user_id} reason={decision.reason} result={response}")
        _record(ctx, "reject", user_id=user_id, flag=flag, comment=comment, reason=decision.reason)
        _notify(ctx, service, f"好友申请已自动拒绝：{user_id}\n原因：{decision.reason}")
        return

    _record(ctx, "manual", user_id=user_id, flag=flag, comment=comment, reason=decision.reason)
    _notify(
        ctx,
        service,
        "\n".join(
            [
                f"好友申请待审核：{user_id}",
                f"验证信息：{comment or '无'}",
                f"flag：{flag}",
                f"同意命令：同意好友 {flag}",
                f"拒绝命令：拒绝好友 {flag} 理由",
            ]
        ),
    )


def _notify(ctx, service: FriendReviewService, text: str) -> None:
    targets = service.notify_users()
    for user_id in targets:
        ctx.send_private(user_id, text)


def _record(ctx, action: str, *, user_id: str, flag: str, comment: str = "", reason: str = "") -> None:
    ctx.append_state_record(
        "friend_review_records",
        limit=50,
        action=action,
        user_id=str(user_id),
        flag=str(flag),
        comment=str(comment),
        reason=str(reason),
    )


def _recent_records(ctx, limit: int = 10) -> list[dict]:
    return ctx.recent_state_records("friend_review_records", limit=limit)


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


MATCHERS.extend(
    [
        friend_review_status,
        enable_friend_review,
        disable_friend_review,
        set_friend_review_mode,
        set_approve_words,
        set_reject_words,
        set_approve_users,
        set_reject_users,
        set_notify_users,
        set_reject_reason,
        set_approve_remark,
        reset_friend_review,
        approve_friend,
        reject_friend,
        friend_review_records,
        export_friend_review_records,
        clear_friend_review_records,
    ]
)
