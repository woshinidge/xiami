from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.join_review import JoinReviewService, ReviewRules, parse_words
from xiami_core.plugins.notification_templates import notice_template_enabled, render_notice_template
from xiami_core.plugins.permissions import PluginPermissionService


PLUGIN_ID = "join_review"
PLUGIN_NAME = "入群审核"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "提供入群审核、入群通知和退群通知能力。"
PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
    "join_review_enabled": False,
    "join_notice_enabled": True,
    "leave_notice_enabled": True,
    "review_reject_reason": "本群已开启入群审核，请联系管理员。",
    "review_auto_approve_keywords": [],
    "review_blacklist_enabled": True,
    "review_gender_enabled": False,
    "review_allowed_gender": "any",
    "review_level_enabled": False,
    "review_min_level": 0,
    "review_qage_enabled": False,
    "review_min_qage": 0,
}

PLUGIN_ADMIN_SCHEMA = [
    {
        "id": "settings",
        "label": "入群审核群配置",
        "type": "state",
        "state_key": "settings",
        "commands": ["开启入群审核", "关闭入群审核", "入群审核状态", "重置入群审核"],
    },
    {
        "id": "records",
        "label": "入群审核记录",
        "type": "state",
        "state_key": "join_review_records",
        "commands": ["审核记录", "导出入群审核记录", "清空入群审核记录", "同意入群", "拒绝入群"],
    },
    {"id": "admins", "label": "入群审核管理员", "type": "config", "config_key": "admins"},
    {"id": "default_enabled", "label": "默认开启入群审核", "type": "config", "config_key": "join_review_enabled"},
    {"id": "rule_blacklist", "label": "黑白名单审核", "type": "state", "state_key": "settings"},
    {"id": "rule_profile", "label": "性别/等级/Q龄审核", "type": "state", "state_key": "settings"},
]

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("入群审核插件已加载")


def on_event(event, ctx) -> None:
    raw = event.raw
    post_type = str(raw.get("post_type") or event.type)
    if post_type == "request" and str(raw.get("request_type") or "") == "group":
        _handle_group_request(event, ctx)
        return
    if post_type == "notice":
        _handle_notice(event, ctx)


def _send_notice(ctx, group_id: str, key: str, fallback: str, **values) -> None:
    if not notice_template_enabled(ctx, key):
        return
    ctx.send_group(group_id, render_notice_template(ctx, key, fallback, **values))


@on_command("审核状态", aliases=("入群审核状态",), only_group=True, description="查看入群审核配置")
def review_status(event, ctx, session) -> None:
    ctx.reply(event, JoinReviewService(ctx).summary(session.group_id))


@on_command("开启入群审核", only_group=True, description="开启本群入群审核")
def enable_review(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    JoinReviewService(ctx).set_enabled(session.group_id, True)
    ctx.reply(event, "本群入群审核已开启。")


@on_command("关闭入群审核", only_group=True, description="关闭本群入群审核")
def disable_review(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    JoinReviewService(ctx).set_enabled(session.group_id, False)
    ctx.reply(event, "本群入群审核已关闭。")


@on_command("开启入群通知", only_group=True, description="开启入群通知")
def enable_join_notice(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    JoinReviewService(ctx).set_notice_enabled(session.group_id, "join_notice_enabled", True)
    ctx.reply(event, "本群入群通知已开启。")


@on_command("关闭入群通知", only_group=True, description="关闭入群通知")
def disable_join_notice(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    JoinReviewService(ctx).set_notice_enabled(session.group_id, "join_notice_enabled", False)
    ctx.reply(event, "本群入群通知已关闭。")


@on_command("开启退群通知", only_group=True, description="开启退群通知")
def enable_leave_notice(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    JoinReviewService(ctx).set_notice_enabled(session.group_id, "leave_notice_enabled", True)
    ctx.reply(event, "本群退群通知已开启。")


@on_command("关闭退群通知", only_group=True, description="关闭退群通知")
def disable_leave_notice(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    JoinReviewService(ctx).set_notice_enabled(session.group_id, "leave_notice_enabled", False)
    ctx.reply(event, "本群退群通知已关闭。")


@on_command("设置拒绝理由", only_group=True, description="设置拒绝理由 <文本>")
def set_reject_reason(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    JoinReviewService(ctx).set_reject_reason(session.group_id, session.argument)
    ctx.reply(event, "入群拒绝理由已更新。")


@on_command("设置审核关键词", only_group=True, description="设置审核关键词 <关键词...>")
def set_review_keywords(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    words = parse_words(session.argument)
    JoinReviewService(ctx).set_auto_approve_keywords(session.group_id, words)
    ctx.reply(event, f"已设置自动同意关键词：{', '.join(words) if words else '无'}。")


@on_command("设置审核性别", only_group=True, description="设置审核性别 <不限/男/女>")
def set_review_gender(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    value = str(session.argument or "").strip()
    mapping = {"不限": "any", "任意": "any", "男": "male", "女": "female", "male": "male", "female": "female", "any": "any"}
    if value.lower() not in mapping:
        ctx.reply(event, "用法：设置审核性别 不限/男/女")
        return
    service = JoinReviewService(ctx)
    rules = service.rules(session.group_id)
    gender = mapping[value.lower()]
    service.set_rules(
        session.group_id,
        ReviewRules(
            blacklist_enabled=rules.blacklist_enabled,
            gender_enabled=gender != "any",
            allowed_gender=gender,
            level_enabled=rules.level_enabled,
            min_level=rules.min_level,
            qage_enabled=rules.qage_enabled,
            min_qage=rules.min_qage,
        ),
    )
    label = {"any": "不限制", "male": "男", "female": "女"}[gender]
    ctx.reply(event, f"入群审核性别规则已设置：{label}。")


@on_command("设置审核等级", only_group=True, description="设置审核等级 <最低等级>；0 为关闭")
def set_review_level(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    value = _parse_non_negative_int(session.argument)
    if value is None:
        ctx.reply(event, "用法：设置审核等级 <最低等级>；0 为关闭")
        return
    service = JoinReviewService(ctx)
    rules = service.rules(session.group_id)
    service.set_rules(
        session.group_id,
        ReviewRules(
            blacklist_enabled=rules.blacklist_enabled,
            gender_enabled=rules.gender_enabled,
            allowed_gender=rules.allowed_gender,
            level_enabled=value > 0,
            min_level=value,
            qage_enabled=rules.qage_enabled,
            min_qage=rules.min_qage,
        ),
    )
    ctx.reply(event, f"入群审核等级规则已{'开启' if value > 0 else '关闭'}：最低 {value}。")


@on_command("设置审核Q龄", aliases=("设置审核q龄", "设置审核账号年龄"), only_group=True, description="设置审核Q龄 <最低Q龄>；0 为关闭")
def set_review_qage(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    value = _parse_non_negative_int(session.argument)
    if value is None:
        ctx.reply(event, "用法：设置审核Q龄 <最低Q龄>；0 为关闭")
        return
    service = JoinReviewService(ctx)
    rules = service.rules(session.group_id)
    service.set_rules(
        session.group_id,
        ReviewRules(
            blacklist_enabled=rules.blacklist_enabled,
            gender_enabled=rules.gender_enabled,
            allowed_gender=rules.allowed_gender,
            level_enabled=rules.level_enabled,
            min_level=rules.min_level,
            qage_enabled=value > 0,
            min_qage=value,
        ),
    )
    ctx.reply(event, f"入群审核Q龄规则已{'开启' if value > 0 else '关闭'}：最低 {value}。")


@on_command("开启黑白名单审核", only_group=True, description="开启入群黑白名单审核")
def enable_blacklist_rule(event, ctx, session) -> None:
    _set_blacklist_rule(event, ctx, session, True)


@on_command("关闭黑白名单审核", only_group=True, description="关闭入群黑白名单审核")
def disable_blacklist_rule(event, ctx, session) -> None:
    _set_blacklist_rule(event, ctx, session, False)


@on_command("重置入群审核", aliases=("恢复入群审核默认",), only_group=True, description="恢复本群入群审核默认设置")
def reset_join_review(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    removed = JoinReviewService(ctx).reset_group(session.group_id)
    ctx.reply(event, "本群入群审核设置已恢复默认。" if removed else "本群当前使用默认入群审核设置。")


@on_command("入群审核记录", aliases=("审核记录",), only_group=True, description="查看最近入群审核和通知记录")
def review_records(event, ctx, session) -> None:
    records = JoinReviewService(ctx).recent_records(session.group_id, limit=80, query=session.argument)[:8]
    if not records:
        ctx.reply(event, "暂无入群审核记录。")
        return
    suffix = f"（筛选：{session.argument}）" if str(session.argument or "").strip() else ""
    lines = [f"最近入群审核记录{suffix}："]
    for item in records:
        lines.append(
            f"- {item.get('time', '')} {item.get('action', '')} user={item.get('user_id', '')} "
            f"flag={item.get('flag', '')} reason={item.get('reason', '')}"
        )
    ctx.reply(event, "\n".join(lines))


@on_command("导出入群审核记录", aliases=("入群审核导出",), only_group=True, description="导出本群入群审核记录")
def export_review_records(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    text = JoinReviewService(ctx).export_records(session.group_id, session.argument, limit=200)
    ctx.reply(event, "入群审核记录导出：\n" + text)


@on_command("清空入群审核记录", aliases=("清空审核记录",), only_group=True, description="清空本群入群审核记录")
def clear_review_records(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    removed = JoinReviewService(ctx).clear_records(session.group_id)
    ctx.reply(event, f"入群审核记录已清空：{removed} 条。")


@on_command("同意入群", aliases=("通过入群", "同意进群"), only_group=True, description="手动同意入群申请：同意入群 <flag>")
def approve_join_request(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "用法：同意入群 <flag>")
        return
    flag = session.argv[0]
    response = ctx.set_group_add_request(flag, "add", True)
    _record(ctx, session.group_id, "manual_approve", user_id="", flag=flag, reason="手动同意")
    ctx.reply(event, f"已提交同意入群申请：{response}")


@on_command("拒绝入群", aliases=("驳回入群", "拒绝进群"), only_group=True, description="手动拒绝入群申请：拒绝入群 <flag> [理由]")
def reject_join_request(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "用法：拒绝入群 <flag> [理由]")
        return
    flag = session.argv[0]
    reason = " ".join(session.argv[1:]).strip() or JoinReviewService(ctx).reject_reason(session.group_id)
    response = ctx.set_group_add_request(flag, "add", False, reason)
    _record(ctx, session.group_id, "manual_reject", user_id="", flag=flag, reason=reason)
    ctx.reply(event, f"已提交拒绝入群申请：{response}")


def _handle_group_request(event, ctx) -> None:
    raw = event.raw
    group_id = str(raw.get("group_id") or "")
    user_id = str(raw.get("user_id") or "")
    flag = str(raw.get("flag") or "")
    sub_type = str(raw.get("sub_type") or "add")
    if not group_id or not user_id or not flag or sub_type != "add":
        return

    service = JoinReviewService(ctx)
    decision = service.decide(group_id, user_id, raw)
    if decision.action == "approve":
        response = ctx.set_group_add_request(flag, sub_type, True)
        ctx.log(f"入群审核同意：group={group_id} user={user_id} reason={decision.reason} result={response}")
        _record(ctx, group_id, "approve", user_id=user_id, flag=flag, comment=str(raw.get("comment") or ""), reason=decision.reason)
        _send_notice(
            ctx,
            group_id,
            "review",
            "已自动同意 {qq} 入群（{detail}）。",
            label="入群审核同意",
            group=group_id,
            qq=user_id,
            target=user_id,
            detail=decision.reason,
            flag=flag,
            comment=str(raw.get("comment") or ""),
        )
        return
    if decision.action == "reject":
        response = ctx.set_group_add_request(flag, sub_type, False, decision.reason)
        ctx.log(f"入群审核拒绝：group={group_id} user={user_id} reason={decision.reason} result={response}")
        _record(ctx, group_id, "reject", user_id=user_id, flag=flag, comment=str(raw.get("comment") or ""), reason=decision.reason)
        _send_notice(
            ctx,
            group_id,
            "review",
            "已自动拒绝 {qq} 入群（{detail}）。",
            label="入群审核拒绝",
            group=group_id,
            qq=user_id,
            target=user_id,
            detail=decision.reason,
            flag=flag,
            comment=str(raw.get("comment") or ""),
        )
        return
    if decision.action == "manual":
        comment = str(raw.get("comment") or "")
        _record(ctx, group_id, "manual", user_id=user_id, flag=flag, comment=comment, reason=decision.reason)
        _send_notice(
            ctx,
            group_id,
            "review",
            "入群申请待审核：{qq}\n验证信息：{detail}",
            label="入群申请待审核",
            group=group_id,
            qq=user_id,
            target=user_id,
            detail=comment or "无",
            flag=flag,
            comment=comment,
        )


def _handle_notice(event, ctx) -> None:
    raw = event.raw
    notice_type = str(raw.get("notice_type") or "")
    group_id = str(raw.get("group_id") or "")
    user_id = str(raw.get("user_id") or "")
    if not group_id or not user_id:
        return
    service = JoinReviewService(ctx)
    if notice_type == "group_increase" and service.notice_enabled(group_id, "join_notice_enabled", True):
        _record(ctx, group_id, "join_notice", user_id=user_id, flag="", reason="入群通知")
        _send_notice(
            ctx,
            group_id,
            "join",
            "欢迎 {qq} 加入本群。",
            label="入群通知",
            group=group_id,
            qq=user_id,
            target=user_id,
            detail="入群通知",
        )
        return
    if notice_type == "group_decrease" and service.notice_enabled(group_id, "leave_notice_enabled", True):
        _record(ctx, group_id, "leave_notice", user_id=user_id, flag="", reason="退群通知")
        _send_notice(
            ctx,
            group_id,
            "leave",
            "成员 {qq} 已离开本群。",
            label="退群通知",
            group=group_id,
            qq=user_id,
            target=user_id,
            detail="退群通知",
        )


def _record(ctx, group_id: str, action: str, *, user_id: str, flag: str, comment: str = "", reason: str = "") -> None:
    ctx.append_state_record(
        "join_review_records",
        limit=80,
        group_id=str(group_id),
        action=action,
        user_id=str(user_id),
        flag=str(flag),
        comment=str(comment),
        reason=str(reason),
    )


def _recent_records(ctx, group_id: str, limit: int = 10) -> list[dict]:
    return [
        item
        for item in ctx.recent_state_records("join_review_records", limit=80)
        if str(item.get("group_id") or "") == str(group_id)
    ][:limit]


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


def _parse_non_negative_int(text: str) -> int | None:
    try:
        value = int(str(text or "").strip())
    except (TypeError, ValueError):
        return None
    return max(0, value)


def _set_blacklist_rule(event, ctx, session, enabled: bool) -> None:
    if not _require_admin(event, ctx, session):
        return
    service = JoinReviewService(ctx)
    rules = service.rules(session.group_id)
    service.set_rules(
        session.group_id,
        ReviewRules(
            blacklist_enabled=bool(enabled),
            gender_enabled=rules.gender_enabled,
            allowed_gender=rules.allowed_gender,
            level_enabled=rules.level_enabled,
            min_level=rules.min_level,
            qage_enabled=rules.qage_enabled,
            min_qage=rules.min_qage,
        ),
    )
    ctx.reply(event, f"本群黑白名单审核已{'开启' if enabled else '关闭'}。")


MATCHERS.extend(
    [
        review_status,
        enable_review,
        disable_review,
        enable_join_notice,
        disable_join_notice,
        enable_leave_notice,
        disable_leave_notice,
        set_reject_reason,
        set_review_keywords,
        set_review_gender,
        set_review_level,
        set_review_qage,
        enable_blacklist_rule,
        disable_blacklist_rule,
        reset_join_review,
        review_records,
        export_review_records,
        clear_review_records,
        approve_join_request,
        reject_join_request,
    ]
)
