from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.permissions import PluginPermissionService, parse_user_ids, sync_permission_config


PLUGIN_ID = "permissions"
PLUGIN_NAME = "权限管理"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "维护主人、全局管理员和本群管理员权限。"
PLUGIN_CONFIG = {"owners": [], "admins": []}

MATCHERS = []


def on_load(ctx) -> None:
    sync_permission_config(ctx)
    ctx.log("权限管理插件已加载")


@on_command("加管理员", only_group=True, description="添加本群管理员")
def add_group_admin(event, ctx, session) -> None:
    service = PluginPermissionService(ctx)
    ok, reason = service.require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    count = service.add_group_admins(session.group_id, user_ids)
    ctx.reply(event, f"已添加本群管理员：{count} 个。")


@on_command("删管理员", only_group=True, description="删除本群管理员")
def remove_group_admin(event, ctx, session) -> None:
    service = PluginPermissionService(ctx)
    ok, reason = service.require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    count = service.remove_group_admins(session.group_id, user_ids)
    ctx.reply(event, f"已删除本群管理员：{count} 个。")


@on_command("加全局管理员", description="添加全局管理员")
def add_global_admin(event, ctx, session) -> None:
    service = PluginPermissionService(ctx)
    if not service.is_owner(session.user_id):
        ctx.reply(event, "权限不足，需要主人。")
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    count = service.add_global_admins(user_ids)
    ctx.reply(event, f"已添加全局管理员：{count} 个。")


@on_command("删全局管理员", description="删除全局管理员")
def remove_global_admin(event, ctx, session) -> None:
    service = PluginPermissionService(ctx)
    if not service.is_owner(session.user_id):
        ctx.reply(event, "权限不足，需要主人。")
        return
    user_ids = parse_user_ids(session.argument)
    if not user_ids:
        ctx.reply(event, "没有识别到有效QQ号。")
        return
    count = service.remove_global_admins(user_ids)
    ctx.reply(event, f"已删除全局管理员：{count} 个。")


@on_command("管理员列表", description="查看权限列表")
def list_admins(event, ctx, session) -> None:
    service = PluginPermissionService(ctx)
    ctx.reply(event, service.summary(session.group_id))


MATCHERS.extend([add_group_admin, remove_group_admin, add_global_admin, remove_global_admin, list_admins])
