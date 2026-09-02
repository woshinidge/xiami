from __future__ import annotations

from typing import Any

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.notification_templates import (
    DEFAULT_NOTICE_SWITCHES,
    DEFAULT_NOTICE_TEMPLATES,
    refresh_notice_template_state,
)
from xiami_core.plugins.permissions import PluginPermissionService


PLUGIN_ID = "help_menu"
PLUGIN_NAME = "菜单帮助"
PLUGIN_VERSION = "0.2.0"
PLUGIN_DESCRIPTION = "提供群菜单和帮助命令，支持后台编辑菜单和通知模板。"

DEFAULT_MENU_LINES = [
    "虾米机器人命令：",
    "积分 / 积分排行",
    "邀请排行 / 邀请排行榜",
    "兑换 <卡密>",
    "绑定 区服名 游戏账户 / 绑定+区服名+游戏账户 / 解绑 / 我的绑定",
    "出题 / 答题 <答案>",
    "知识搜索 <关键词> / 知识统计",
    "问 <问题> / AI状态",
]

DEFAULT_ADMIN_MENU_LINES = [
    "管理员命令：",
    "加管理员/删管理员 <QQ...> / 管理员列表",
    "禁言 <QQ> <秒> / 解禁 <QQ> / 踢 <QQ>",
    "加黑名单/删黑名单 <QQ...>",
    "加白名单/删白名单 <QQ...>",
    "加违禁词/删违禁词 <词...>",
    "插件列表 / 插件搜索 <关键词> / 插件详情 <插件ID> / 插件命令 <插件ID>",
    "插件状态 [插件ID] / 插件异常",
    "开启插件 <插件ID> / 关闭插件 <插件ID>",
    "复制群配置 <来源群号> [目标群号] / 清空群配置 [群号]",
    "知识导入 <文件或目录路径> / 知识清空",
    "违禁词、黑名单和撤回规则：在账号页权限管理与名单与违禁词页面维护",
]

PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
    "menu_lines": DEFAULT_MENU_LINES,
    "admin_menu_lines": DEFAULT_ADMIN_MENU_LINES,
    "notice_templates": DEFAULT_NOTICE_TEMPLATES,
    "notice_switches": DEFAULT_NOTICE_SWITCHES,
}

PLUGIN_CONFIG_SCHEMA = [
    {
        "key": "menu_lines",
        "label": "普通菜单",
        "type": "list",
        "description": "菜单/帮助命令对普通用户展示的行文本。",
    },
    {
        "key": "admin_menu_lines",
        "label": "管理员菜单",
        "type": "list",
        "description": "管理员触发菜单/帮助命令时追加展示的行文本。",
    },
    {
        "key": "notice_templates",
        "label": "通知模板",
        "type": "dict",
        "description": "旧后台通知模板占位符配置，桌面后台按模板分类编辑。",
    },
    {
        "key": "notice_switches",
        "label": "通知开关",
        "type": "dict",
        "description": "旧后台开/关事件、好友、入群、退群、邀请和审核提示。",
    },
]

PLUGIN_ADMIN_SCHEMA = [
    {"id": "menu_lines", "label": "普通菜单", "type": "config", "config_key": "menu_lines", "commands": ["菜单", "设置菜单", "重置菜单"]},
    {
        "id": "admin_menu_lines",
        "label": "管理员菜单",
        "type": "config",
        "config_key": "admin_menu_lines",
        "commands": ["管理员菜单", "设置管理菜单", "重置菜单"],
    },
    {
        "id": "notice_templates",
        "label": "通知模板",
        "type": "config",
        "config_key": "notice_templates",
        "commands": ["通知模板", "设置通知模板", "重置通知模板"],
    },
    {
        "id": "notice_switches",
        "label": "通知开关",
        "type": "config",
        "config_key": "notice_switches",
        "commands": ["通知设置", "设置通知"],
    },
]

MATCHERS = []
HELP_MENU_STATE_KEY = "help_menu_settings"
NOTICE_LABELS = {
    "event": "普通事件",
    "friend": "好友申请",
    "join": "入群通知",
    "leave": "退群通知",
    "invite": "邀请积分",
    "review": "审核通知",
}


def on_load(ctx) -> None:
    refresh_notice_template_state(ctx)
    ctx.log("菜单帮助插件已加载")


@on_command("菜单", aliases=("帮助", "命令", "功能", "机器人菜单"), description="查看机器人命令菜单")
def menu(event, ctx, session) -> None:
    lines = _config_lines(ctx, "menu_lines", DEFAULT_MENU_LINES)
    if PluginPermissionService(ctx).is_admin(session.user_id, session.group_id):
        admin_lines = _config_lines(ctx, "admin_menu_lines", DEFAULT_ADMIN_MENU_LINES)
        if admin_lines:
            if lines and lines[-1]:
                lines.append("")
            lines.extend(admin_lines)
    ctx.reply(event, "\n".join(lines))


@on_command("管理员菜单", aliases=("管理菜单", "后台菜单"), only_group=True, description="查看管理员菜单")
def admin_menu(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    lines = _config_lines(ctx, "admin_menu_lines", DEFAULT_ADMIN_MENU_LINES)
    ctx.reply(event, "\n".join(lines))


@on_command("设置菜单", aliases=("修改菜单",), only_group=True, description="设置菜单 <每行菜单；也支持用 | 分隔>")
def set_menu(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    lines = _parse_lines_argument(session.argument)
    if not lines:
        ctx.reply(event, "格式：设置菜单 第一行|第二行")
        return
    settings = _state_settings(ctx)
    settings["menu_lines"] = lines
    ctx.set_state(HELP_MENU_STATE_KEY, settings)
    ctx.reply(event, f"普通菜单已保存：{len(lines)} 行。")


@on_command("设置管理菜单", aliases=("设置管理员菜单", "修改管理菜单"), only_group=True, description="设置管理菜单 <每行菜单；也支持用 | 分隔>")
def set_admin_menu(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    lines = _parse_lines_argument(session.argument)
    if not lines:
        ctx.reply(event, "格式：设置管理菜单 第一行|第二行")
        return
    settings = _state_settings(ctx)
    settings["admin_menu_lines"] = lines
    ctx.set_state(HELP_MENU_STATE_KEY, settings)
    ctx.reply(event, f"管理员菜单已保存：{len(lines)} 行。")


@on_command("重置菜单", aliases=("恢复菜单",), only_group=True, description="重置菜单 [普通/管理/全部]")
def reset_menu(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    target = session.argument.strip()
    settings = _state_settings(ctx)
    if target in {"管理", "管理员", "admin"}:
        settings.pop("admin_menu_lines", None)
        message = "管理员菜单已恢复默认。"
    elif target in {"普通", "用户", "menu"}:
        settings.pop("menu_lines", None)
        message = "普通菜单已恢复默认。"
    else:
        settings.pop("menu_lines", None)
        settings.pop("admin_menu_lines", None)
        message = "普通菜单和管理员菜单已恢复默认。"
    ctx.set_state(HELP_MENU_STATE_KEY, settings)
    ctx.reply(event, message)


@on_command("通知设置", aliases=("通知开关",), only_group=True, description="查看通知开关")
def notice_settings(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    switches = _notice_switches(ctx)
    lines = ["通知开关："]
    for key in ("event", "friend", "join", "leave", "invite", "review"):
        lines.append(f"{NOTICE_LABELS.get(key, key)}({key})：{'开启' if switches.get(key, True) else '关闭'}")
    ctx.reply(event, "\n".join(lines))


@on_command("设置通知", aliases=("设置通知开关",), only_group=True, description="设置通知 <类型> <开/关>")
def set_notice_switch(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    key, value_text = _split_two_args(session.argument)
    key = _normalize_notice_key(key)
    enabled = _parse_bool(value_text)
    if not key or enabled is None:
        ctx.reply(event, "格式：设置通知 <event/friend/join/leave/invite/review> <开/关>")
        return
    switches = _notice_switches(ctx)
    switches[key] = bool(enabled)
    ctx.set_state("notice_switches", switches)
    ctx.reply(event, f"{NOTICE_LABELS.get(key, key)}通知已{'开启' if enabled else '关闭'}。")


@on_command("通知模板", aliases=("查看通知模板",), only_group=True, description="通知模板 [类型]")
def notice_template(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    key = _normalize_notice_key(session.argument.strip())
    templates = _notice_templates(ctx)
    if key:
        ctx.reply(event, f"{NOTICE_LABELS.get(key, key)}({key})：\n{templates.get(key, '')}")
        return
    lines = ["通知模板类型："]
    for item_key in ("event", "friend", "join", "leave", "invite", "review"):
        lines.append(f"{NOTICE_LABELS.get(item_key, item_key)}({item_key})")
    ctx.reply(event, "\n".join(lines))


@on_command("设置通知模板", aliases=("修改通知模板",), only_group=True, description="设置通知模板 <类型> <模板内容>")
def set_notice_template(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    key, template = _split_two_args(session.argument)
    key = _normalize_notice_key(key)
    template = template.strip()
    if not key or not template:
        ctx.reply(event, "格式：设置通知模板 <event/friend/join/leave/invite/review> <模板内容>")
        return
    templates = _notice_templates(ctx)
    templates[key] = template
    ctx.set_state("notice_templates", templates)
    ctx.reply(event, f"{NOTICE_LABELS.get(key, key)}通知模板已保存。")


@on_command("重置通知模板", aliases=("恢复通知模板",), only_group=True, description="重置通知模板 [类型/全部]")
def reset_notice_template(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    key = _normalize_notice_key(session.argument.strip())
    templates = _notice_templates(ctx)
    if key:
        templates[key] = DEFAULT_NOTICE_TEMPLATES.get(key, "")
        ctx.set_state("notice_templates", templates)
        ctx.reply(event, f"{NOTICE_LABELS.get(key, key)}通知模板已恢复默认。")
        return
    ctx.set_state("notice_templates", dict(DEFAULT_NOTICE_TEMPLATES))
    ctx.reply(event, "全部通知模板已恢复默认。")


def _config_lines(ctx: Any, key: str, default: list[str]) -> list[str]:
    settings = _state_settings(ctx)
    value = settings.get(key, ctx.get_config(key, default))
    if isinstance(value, str):
        lines = value.splitlines()
    elif isinstance(value, (list, tuple)):
        lines = [str(item) for item in value]
    else:
        lines = list(default)
    cleaned = [line.rstrip() for line in lines]
    return cleaned or list(default)


def _state_settings(ctx: Any) -> dict[str, Any]:
    value = ctx.get_state(HELP_MENU_STATE_KEY, {})
    return dict(value) if isinstance(value, dict) else {}


def _parse_lines_argument(text: str) -> list[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    rows = raw.splitlines()
    if len(rows) == 1 and "|" in raw:
        rows = raw.split("|")
    return [line.strip() for line in rows if line.strip()]


def _notice_switches(ctx: Any) -> dict[str, bool]:
    value = ctx.get_state("notice_switches", None)
    if not isinstance(value, dict):
        value = ctx.get_config("notice_switches", {})
    switches = dict(DEFAULT_NOTICE_SWITCHES)
    if isinstance(value, dict):
        for key, raw in value.items():
            parsed = _parse_bool(raw)
            switches[str(key)] = bool(parsed) if parsed is not None else bool(raw)
    return switches


def _notice_templates(ctx: Any) -> dict[str, str]:
    value = ctx.get_state("notice_templates", None)
    if not isinstance(value, dict):
        value = ctx.get_config("notice_templates", {})
    templates = dict(DEFAULT_NOTICE_TEMPLATES)
    if isinstance(value, dict):
        for key, raw in value.items():
            templates[str(key)] = str(raw)
    return templates


def _normalize_notice_key(text: str) -> str:
    raw = str(text or "").strip().lower()
    aliases = {
        "普通事件": "event",
        "事件": "event",
        "event": "event",
        "好友": "friend",
        "好友申请": "friend",
        "friend": "friend",
        "入群": "join",
        "入群通知": "join",
        "join": "join",
        "退群": "leave",
        "退群通知": "leave",
        "leave": "leave",
        "邀请": "invite",
        "邀请积分": "invite",
        "invite": "invite",
        "审核": "review",
        "审核通知": "review",
        "review": "review",
    }
    return aliases.get(raw, "")


def _parse_bool(value: Any):
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    if text in {"1", "true", "yes", "on", "enable", "enabled", "开", "开启", "启用"}:
        return True
    if text in {"0", "false", "no", "off", "disable", "disabled", "关", "关闭", "禁用"}:
        return False
    return None


def _split_two_args(text: str) -> tuple[str, str]:
    parts = str(text or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1]


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


MATCHERS.extend([
    menu,
    admin_menu,
    set_menu,
    set_admin_menu,
    reset_menu,
    notice_settings,
    set_notice_switch,
    notice_template,
    set_notice_template,
    reset_notice_template,
])
