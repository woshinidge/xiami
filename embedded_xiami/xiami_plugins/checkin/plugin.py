from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.permissions import PluginPermissionService
from xiami_core.plugins.points import PointsService, format_ranked_name, resolve_display_names


PLUGIN_ID = "checkin"
PLUGIN_NAME = "签到积分"
PLUGIN_VERSION = "0.2.0"
PLUGIN_DESCRIPTION = "提供每日签到、积分查询和积分排行功能。"
PLUGIN_CONFIG = {"checkin_enabled": True, "checkin_points": 1, "owners": [], "admins": []}
PLUGIN_CONFIG_SCHEMA = [
    {"key": "checkin_enabled", "label": "默认开启签到", "type": "bool", "description": "未单独设置时是否允许签到。"},
    {"key": "checkin_points", "label": "默认签到积分", "type": "int", "description": "每次签到增加的积分。"},
    {"key": "owners", "label": "主人 QQ", "type": "list", "description": "拥有最高权限的 QQ 列表。"},
    {"key": "admins", "label": "管理员 QQ", "type": "list", "description": "允许修改签到设置的 QQ 列表。"},
]
PLUGIN_ADMIN_SCHEMA = [
    {"id": "points", "label": "积分数据", "type": "state", "state_key": "points", "commands": ["积分", "积分排行"]},
    {"id": "checkins", "label": "签到记录", "type": "state", "state_key": "checkins", "commands": ["签到"]},
    {"id": "settings", "label": "签到设置", "type": "state", "state_key": "settings", "commands": ["签到设置", "开启签到", "关闭签到", "设置签到积分"]},
    {"id": "default_points", "label": "默认签到积分", "type": "config", "config_key": "checkin_points"},
]
MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("签到积分插件已加载")


@on_command("签到", only_group=True, description="每日签到获得积分")
def checkin(event, ctx, session) -> None:
    result = PointsService(ctx).checkin(session.group_id, session.user_id)
    ctx.reply(event, result.message)


@on_command("积分", only_group=True, description="查询当前积分")
def points(event, ctx, session) -> None:
    total = PointsService(ctx).points(session.group_id, session.user_id)
    ctx.reply(event, f"当前积分：{total}。")


@on_command("积分排行", aliases=("积分排行榜",), only_group=True, description="查看本群积分排行")
def ranking(event, ctx, session) -> None:
    rows = PointsService(ctx).ranking(session.group_id, limit=10)
    if not rows:
        ctx.reply(event, "暂无积分排行。")
        return
    names = resolve_display_names(ctx, session.group_id, [user_id for user_id, _value in rows])
    lines = ["积分排行："]
    lines.extend(
        f"{index}. {format_ranked_name(user_id, names)}: {value}"
        for index, (user_id, value) in enumerate(rows, start=1)
    )
    ctx.reply(event, "\n".join(lines))


@on_command("签到设置", aliases=("签到状态",), only_group=True, description="查看本群签到设置")
def checkin_settings(event, ctx, session) -> None:
    service = PointsService(ctx)
    ctx.reply(
        event,
        "\n".join(
            [
                "签到设置：",
                f"状态：{'已开启' if service.enabled(session.group_id) else '已关闭'}",
                f"每次签到积分：{service.checkin_points(session.group_id)}",
                f"今日已签到：{len(service.today_checkin_users(session.group_id))} 人",
            ]
        ),
    )


@on_command("开启签到", only_group=True, description="开启本群签到")
def enable_checkin(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    PointsService(ctx).set_enabled(session.group_id, True)
    ctx.reply(event, "已开启本群签到。")


@on_command("关闭签到", only_group=True, description="关闭本群签到")
def disable_checkin(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    PointsService(ctx).set_enabled(session.group_id, False)
    ctx.reply(event, "已关闭本群签到。")


@on_command("设置签到积分", aliases=("签到积分", "设置签到奖励"), only_group=True, description="设置签到积分 <积分>")
def set_checkin_points(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    try:
        value = int(str(session.argument or "").strip())
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        ctx.reply(event, "格式：设置签到积分 <积分>")
        return
    PointsService(ctx).set_checkin_points(session.group_id, value)
    ctx.reply(event, f"已设置本群签到积分：{value}。")


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


MATCHERS.extend(
    [checkin, points, ranking, checkin_settings, enable_checkin, disable_checkin, set_checkin_points]
)
