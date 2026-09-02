from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.invites import InviteService
from xiami_core.plugins.points import format_ranked_name, resolve_display_names
from xiami_core.plugins.notification_templates import notice_template_enabled, render_notice_template
from xiami_core.plugins.permissions import PluginPermissionService


PLUGIN_ID = "invites"
PLUGIN_NAME = "邀请积分"
PLUGIN_VERSION = "0.2.0"
PLUGIN_DESCRIPTION = "提供邀请入群积分奖励、个人统计和邀请记录管理。"
PLUGIN_CONFIG = {
    "invite_points_enabled": True,
    "invite_reward_points": 1,
    "invite_retention_days": 0,
    "owners": [],
    "admins": [],
}
PLUGIN_ADMIN_SCHEMA = [
    {"id": "settings", "label": "邀请积分设置", "type": "state", "state_key": "settings", "commands": ["邀请设置", "开启邀请积分", "关闭邀请积分", "设置邀请奖励"]},
    {"id": "records", "label": "邀请记录", "type": "state", "state_key": "invite_records", "commands": ["邀请记录", "补邀请", "导入邀请记录", "导出邀请记录", "删除邀请记录", "清空邀请记录"]},
    {"id": "ranks", "label": "邀请排行数据", "type": "state", "state_key": "invite_ranks", "commands": ["邀请排行", "我的邀请", "重算邀请排行"]},
    {"id": "reward_points", "label": "默认邀请奖励积分", "type": "config", "config_key": "invite_reward_points"},
    {"id": "retention_days", "label": "默认入群保留天数", "type": "config", "config_key": "invite_retention_days"},
]

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("邀请积分插件已加载")


def on_event(event, ctx) -> None:
    if event.type != "notice":
        return
    raw = event.raw
    notice_type = str(raw.get("notice_type") or "")
    group_id = str(raw.get("group_id") or event.group_id or "")
    user_id = str(raw.get("user_id") or event.user_id or "")
    if notice_type == "group_decrease":
        result = InviteService(ctx).record_leave(
            group_id,
            user_id,
            sub_type=str(raw.get("sub_type") or ""),
        )
        if result.deducted and result.message and notice_template_enabled(ctx, "invite"):
            ctx.send_group(group_id, result.message)
        return
    if notice_type != "group_increase":
        return
    # group_increase 有两种子类型：
    #   invite  —— operator_id 是邀请人，该给分
    #   approve —— operator_id 是批准入群申请的管理员，不是邀请人，不能给分
    # 所以 operator_id 只在 sub_type=invite（或未提供 sub_type）时才作为邀请人兜底。
    sub_type = str(raw.get("sub_type") or "").strip().lower()
    inviter_id = str(raw.get("inviter_id") or "")
    if not inviter_id and sub_type in {"", "invite"}:
        inviter_id = str(raw.get("operator_id") or "")
    result = InviteService(ctx).record_join(group_id, user_id, inviter_id)
    if result.rewarded and result.message and notice_template_enabled(ctx, "invite"):
        ctx.send_group(
            group_id,
            render_notice_template(
                ctx,
                "invite",
                result.message,
                label="邀请积分",
                group=group_id,
                qq=user_id,
                target=user_id,
                inviter=inviter_id,
                reward=result.points,
                total=result.total,
                detail=result.message,
            ),
        )


@on_command("邀请排行", aliases=("邀请排行榜",), only_group=True, description="查看邀请排行")
def invite_rank(event, ctx, session) -> None:
    rows = InviteService(ctx).ranking(session.group_id, 10)
    if not rows:
        ctx.reply(event, "暂无邀请记录。")
        return
    names = resolve_display_names(ctx, session.group_id, [r.get("inviter_id") for r in rows])
    lines = ["邀请排行（前 10 名）："]
    for index, row in enumerate(rows, start=1):
        who = format_ranked_name(str(row.get("inviter_id") or ""), names)
        lines.append(f"{index}. {who} 邀请 {int(row.get('invite_count') or 0)} 人，奖励 {int(row.get('points') or 0)} 积分")
    ctx.reply(event, "\n".join(lines))


@on_command("我的邀请", aliases=("邀请统计",), only_group=True, description="查看自己的邀请人数和奖励积分")
def my_invites(event, ctx, session) -> None:
    data = InviteService(ctx).user_rank(session.group_id, session.user_id)
    rank_text = f"第 {data['rank']} 名" if int(data.get("rank") or 0) else "暂无排名"
    ctx.reply(
        event,
        f"我的邀请：邀请 {int(data.get('invite_count') or 0)} 人，奖励 {int(data.get('points') or 0)} 积分，{rank_text}。",
    )


@on_command("邀请记录", only_group=True, description="查看邀请记录，可追加 QQ 号筛选")
def invite_records(event, ctx, session) -> None:
    if session.argument.strip() and not _require_admin(event, ctx, session):
        return
    query = session.argument.strip()
    if not query:
        query = session.user_id
    ctx.reply(event, InviteService(ctx).records_text(session.group_id, query=query))


@on_command("邀请设置", aliases=("邀请积分设置",), only_group=True, description="查看本群邀请积分设置")
def invite_settings(event, ctx, session) -> None:
    service = InviteService(ctx)
    rows = service.records(session.group_id)
    ranks = service.ranking(session.group_id, 0)
    ctx.reply(
        event,
        "\n".join(
            [
                "邀请积分设置：",
                f"状态：{'已开启' if service.enabled(session.group_id) else '已关闭'}",
                f"每次邀请奖励：{service.reward_points(session.group_id)} 积分",
                f"入群保留期：{service.retention_days(session.group_id)} 天（0 为不限制）",
                f"邀请记录：{len(rows)} 条",
                f"邀请人：{len(ranks)} 个",
            ]
        ),
    )


@on_command("开启邀请积分", only_group=True, description="开启本群邀请积分")
def enable_invites(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    InviteService(ctx).set_enabled(session.group_id, True)
    ctx.reply(event, "已开启本群邀请积分。")


@on_command("关闭邀请积分", only_group=True, description="关闭本群邀请积分")
def disable_invites(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    InviteService(ctx).set_enabled(session.group_id, False)
    ctx.reply(event, "已关闭本群邀请积分。")


@on_command("设置邀请奖励", aliases=("邀请奖励", "设置邀请积分"), only_group=True, description="设置邀请奖励 <积分>")
def set_invite_reward(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    raw = session.argument.strip()
    try:
        points = max(1, int(raw))
    except (TypeError, ValueError):
        ctx.reply(event, "格式：设置邀请奖励 <积分>")
        return
    InviteService(ctx).set_reward_points(session.group_id, points)
    ctx.reply(event, f"已设置本群邀请奖励：{points} 积分。")


@on_command("设置邀请天数", aliases=("邀请保留天数", "设置入群天数"), only_group=True, description="设置邀请成员至少留群天数 <天数>，0 为不限制")
def set_invite_retention_days(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    raw = session.argument.strip()
    try:
        days = max(0, int(raw))
    except (TypeError, ValueError):
        ctx.reply(event, "格式：设置邀请天数 <天数>（0 为不限制）")
        return
    InviteService(ctx).set_retention_days(session.group_id, days)
    ctx.reply(event, f"已设置邀请成员入群保留期：{days} 天。")


@on_command("补邀请", aliases=("补录邀请", "添加邀请记录"), only_group=True, description="补邀请 <入群QQ> <邀请人QQ> [积分]")
def add_invite_record(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    user_id, inviter_id, points = InviteService(ctx).parse_record_line(session.argument)
    if not user_id or not inviter_id:
        ctx.reply(event, "格式：补邀请 <入群QQ> <邀请人QQ> [积分]")
        return
    result = InviteService(ctx).add_record(session.group_id, user_id, inviter_id, points, award_points=True)
    if not result.rewarded:
        ctx.reply(event, "补录失败：记录已存在、邀请人无效或 QQ 号格式不正确。")
        return
    ctx.reply(event, f"已补录邀请记录：{user_id} <- {inviter_id}，奖励 {result.points} 积分。")


@on_command("导入邀请记录", aliases=("批量导入邀请",), only_group=True, description="导入邀请记录，每行 入群QQ=邀请人QQ,积分")
def import_invite_records(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    text = session.argument.strip()
    if not text:
        ctx.reply(event, "格式：导入邀请记录 10002=10001,5（可换行多条）")
        return
    count = InviteService(ctx).import_records(session.group_id, text, award_points=True)
    ctx.reply(event, f"已导入邀请记录：{count} 条。")


@on_command("导出邀请记录", aliases=("导出邀请",), only_group=True, description="导出邀请记录 [QQ关键词]")
def export_invite_records(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    ctx.reply(event, InviteService(ctx).export_records(session.group_id, session.argument.strip()))


@on_command("重算邀请排行", aliases=("重建邀请排行",), only_group=True, description="根据邀请记录重算本群邀请排行")
def rebuild_invite_rank(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    count = InviteService(ctx).rebuild_ranking(session.group_id)
    ctx.reply(event, f"已根据 {count} 条邀请记录重算排行。")


@on_command("删除邀请记录", aliases=("删邀请记录",), only_group=True, description="删除邀请记录 <入群QQ>")
def delete_invite_record(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    value = session.argument.strip()
    if not value:
        ctx.reply(event, "格式：删除邀请记录 <入群QQ>")
        return
    removed = InviteService(ctx).delete_record(session.group_id, value)
    if not removed:
        ctx.reply(event, "未找到可删除的邀请记录。")
        return
    ctx.reply(event, f"已删除邀请记录：{removed.get('user_id')}。")


@on_command("清空邀请记录", aliases=("清空邀请排行",), only_group=True, description="清空本群邀请记录")
def clear_invite_records(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    removed = InviteService(ctx).clear_group(session.group_id)
    ctx.reply(event, f"已清空本群邀请记录：{removed} 条。")


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


MATCHERS.extend([
    invite_rank,
    my_invites,
    invite_records,
    invite_settings,
    enable_invites,
    disable_invites,
    set_invite_reward,
    set_invite_retention_days,
    add_invite_record,
    import_invite_records,
    export_invite_records,
    rebuild_invite_rank,
    delete_invite_record,
    clear_invite_records,
])
