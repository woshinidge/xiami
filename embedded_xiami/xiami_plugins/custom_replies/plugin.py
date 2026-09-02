from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.custom_replies import CustomReplyService, match_type_label
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.permissions import PluginPermissionService


PLUGIN_ID = "custom_replies"
PLUGIN_NAME = "自定义回复"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "提供包含、精确、正则、前缀和后缀自定义回复。"
PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
}
PLUGIN_ADMIN_SCHEMA = [
    {
        "id": "custom_replies",
        "label": "自定义回复表",
        "type": "state",
        "state_key": "custom_replies",
        "commands": ["加回答", "加精确回答", "加正则回答", "加前缀回答", "加后缀回答", "批量加回答", "开启回答", "关闭回答", "删回答", "导出回答", "清空回答", "回答列表"],
    },
    {"id": "admins", "label": "自定义回复管理员", "type": "config", "config_key": "admins"},
]

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("自定义回复插件已加载")


def on_message(event, ctx) -> None:
    if event.message_type != "group":
        return
    if not GroupSettingService(ctx).enabled(event.target, "custom_replies_enabled"):
        return
    text = event.text.strip()
    if _is_management_command(text):
        return
    reply = CustomReplyService(ctx).match(event.target, text, event.sender)
    if reply:
        ctx.reply(event, reply)


@on_command("加回答", only_group=True, description="加回答 关键词=回复内容")
def add_reply(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    keyword, response = CustomReplyService(ctx).parse_pair(session.argument)
    if not keyword or not response:
        ctx.reply(event, "格式：加回答 关键词=回复内容")
        return
    CustomReplyService(ctx).set(session.group_id, keyword, response, "contains")
    ctx.reply(event, "已添加自定义回答。")


@on_command("加精确回答", only_group=True, description="加精确回答 关键词=回复内容")
def add_exact_reply(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    keyword, response = CustomReplyService(ctx).parse_pair(session.argument)
    if not keyword or not response:
        ctx.reply(event, "格式：加精确回答 关键词=回复内容")
        return
    CustomReplyService(ctx).set(session.group_id, keyword, response, "exact")
    ctx.reply(event, "已添加精确自定义回答。")


@on_command("加正则回答", only_group=True, description="加正则回答 正则=回复内容，可用 {1} 引用捕获组")
def add_regex_reply(event, ctx, session) -> None:
    _add_reply_by_type(event, ctx, session, "regex", "正则")


@on_command("加前缀回答", only_group=True, description="加前缀回答 前缀=回复内容")
def add_prefix_reply(event, ctx, session) -> None:
    _add_reply_by_type(event, ctx, session, "prefix", "前缀")


@on_command("加后缀回答", only_group=True, description="加后缀回答 后缀=回复内容")
def add_suffix_reply(event, ctx, session) -> None:
    _add_reply_by_type(event, ctx, session, "suffix", "后缀")


def _add_reply_by_type(event, ctx, session, match_type: str, label: str) -> None:
    if not _require_admin(event, ctx, session):
        return
    keyword, response = CustomReplyService(ctx).parse_pair(session.argument)
    if not keyword or not response:
        ctx.reply(event, f"格式：加{label}回答 关键词=回复内容")
        return
    CustomReplyService(ctx).set(session.group_id, keyword, response, match_type)
    ctx.reply(event, f"已添加{label}自定义回答。")


@on_command("删回答", only_group=True, description="删回答 关键词")
def remove_reply(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    keyword = session.argument.strip()
    if not keyword:
        ctx.reply(event, "格式：删回答 关键词")
        return
    count = CustomReplyService(ctx).delete(session.group_id, keyword)
    ctx.reply(event, f"已删除自定义回答：{count} 条。")


@on_command("开启回答", aliases=("启用回答",), only_group=True, description="开启回答 <关键词>")
def enable_reply(event, ctx, session) -> None:
    _set_reply_enabled(event, ctx, session, True)


@on_command("关闭回答", aliases=("停用回答",), only_group=True, description="关闭回答 <关键词>")
def disable_reply(event, ctx, session) -> None:
    _set_reply_enabled(event, ctx, session, False)


def _set_reply_enabled(event, ctx, session, enabled: bool) -> None:
    if not _require_admin(event, ctx, session):
        return
    keyword = session.argument.strip()
    if not keyword:
        ctx.reply(event, f"格式：{'开启' if enabled else '关闭'}回答 <关键词>")
        return
    count = CustomReplyService(ctx).set_enabled(session.group_id, keyword, enabled)
    ctx.reply(event, f"已{'启用' if enabled else '停用'}自定义回答：{count} 条。")


@on_command("回答列表", aliases=("自定义回答列表",), only_group=True, description="查看本群自定义回答")
def list_replies(event, ctx, session) -> None:
    rows = CustomReplyService(ctx).list(session.group_id, session.argument)
    if not rows:
        ctx.reply(event, "本群暂无自定义回答。")
        return
    suffix = f"（筛选：{session.argument.strip()}）" if session.argument.strip() else ""
    lines = [f"本群自定义回答{suffix}："]
    for item in rows[:20]:
        status = "" if item.enabled else "停用/"
        lines.append(f"- [{status}{match_type_label(item.match_type)}] {item.keyword} => {item.response}")
    ctx.reply(event, "\n".join(lines))


@on_command("批量加回答", aliases=("导入回答", "批量导入回答"), only_group=True, description="批量导入回答，每行：关键词=回复；可加前缀 精确:")
def import_replies(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    count = CustomReplyService(ctx).import_lines(session.group_id, session.argument)
    ctx.reply(event, f"已导入自定义回答：{count} 条。")


@on_command("导出回答", aliases=("导出自定义回答",), only_group=True, description="导出回答 [关键词]")
def export_replies(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    rows = CustomReplyService(ctx).export_lines(session.group_id, session.argument)
    if not rows:
        ctx.reply(event, "本群暂无可导出的自定义回答。")
        return
    ctx.reply(event, "自定义回答导出：\n" + "\n".join(rows[:50]))


@on_command("清空回答", aliases=("清空自定义回答",), only_group=True, description="清空本群自定义回答")
def clear_replies(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    removed = CustomReplyService(ctx).clear_group(session.group_id)
    ctx.reply(event, f"已清空本群自定义回答：{removed} 条。")


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


def _is_management_command(text: str) -> bool:
    return text.startswith(
        (
            "加回答",
            "加精确回答",
            "加正则回答",
            "加前缀回答",
            "加后缀回答",
            "批量加回答",
            "导入回答",
            "批量导入回答",
            "开启回答",
            "启用回答",
            "关闭回答",
            "停用回答",
            "删回答",
            "导出回答",
            "导出自定义回答",
            "清空回答",
            "清空自定义回答",
            "回答列表",
            "自定义回答列表",
        )
    )


MATCHERS.extend([
    add_exact_reply,
    add_reply,
    add_regex_reply,
    add_prefix_reply,
    add_suffix_reply,
    import_replies,
    remove_reply,
    enable_reply,
    disable_reply,
    export_replies,
    clear_replies,
    list_replies,
])
