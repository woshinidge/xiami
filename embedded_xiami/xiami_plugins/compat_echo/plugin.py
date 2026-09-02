from __future__ import annotations

from xiami_core.plugins.compat import on_command, on_keyword


PLUGIN_ID = "compat_echo"
PLUGIN_NAME = "Compat Echo"
PLUGIN_VERSION = "0.2.0"
PLUGIN_DESCRIPTION = "用于验证命令、关键词、权限、配置和事件处理链路。"
PLUGIN_CONFIG = {"prefix": "[compat]", "owners": [], "admins": []}

MATCHERS = []


def on_load(ctx) -> None:
    marker = ctx.data_dir() / "loaded.txt"
    marker.write_text("loaded", encoding="utf-8")
    ctx.log("Compat Echo 插件已加载")


def on_event(event, ctx) -> None:
    if event.type == "notice":
        ctx.log(f"Compat Echo 收到通知事件：{event.raw.get('notice_type', 'unknown')}")


@on_command("/cecho", aliases=("/兼容回声",), description="回显命令参数")
def compat_echo(event, ctx, session) -> None:
    prefix = ctx.get_config("prefix", "")
    ctx.reply(event, f"{prefix} {session.argument}".strip())


@on_command("/cgroup", only_group=True, admin_only=True, description="群管理员测试命令")
def group_admin_echo(event, ctx, session) -> None:
    ctx.reply(event, f"群管理员命令：{session.group_id} {session.argument}".strip())


@on_command("/ccount", description="插件持久计数")
def count_echo(event, ctx, _session) -> None:
    count = int(ctx.get_state("count", 0)) + 1
    ctx.set_state("count", count)
    ctx.reply(event, f"兼容计数：{count}")


@on_keyword("兼容测试", description="关键词测试")
def keyword_echo(event, ctx, _session) -> None:
    ctx.reply(event, "兼容层收到关键词")


MATCHERS.extend([compat_echo, group_admin_echo, count_echo, keyword_echo])
