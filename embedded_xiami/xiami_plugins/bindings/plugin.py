from __future__ import annotations

import re

from xiami_core.plugins.bindings import BindingService
from xiami_core.plugins.compat import on_command, on_regex
from xiami_core.plugins.group_settings import GroupSettingService


PLUGIN_ID = "bindings"
PLUGIN_NAME = "账号绑定"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "维护群内 QQ 与游戏区服账号绑定关系。"
PLUGIN_CONFIG = {
    "binding_root": "",
}

PLUGIN_CONFIG_SCHEMA = [
    {"key": "binding_root", "label": "绑定信息存放目录", "type": "string"},
]
PLUGIN_ADMIN_SCHEMA = [
    {
        "id": "bindings",
        "label": "账号绑定",
        "type": "state",
        "state_key": "bindings",
        "commands": [
            "绑定 <区服> <账号>",
            "绑定+<区服>+<账号>",
            "解绑 [区服]",
            "我的绑定",
            "区服列表",
            "绑定记录 [关键词]",
            "导出绑定 [关键词]",
            "导入绑定 <区服|QQ|账号>",
            "删除绑定 <区服> <QQ>",
        ],
    },
    {"id": "binding_root", "label": "绑定信息存放目录", "type": "config", "config_key": "binding_root"},
]

MATCHERS = []
USAGE_TEXT = "绑定失败，用法：绑定 <区服> <账号>；也支持：绑定+<区服>+<账号>"


def on_load(ctx) -> None:
    ctx.log("账号绑定插件已加载")


@on_regex(r"^绑定\+([^+\s]{1,32})\+(.{2,32})$", only_group=True, description="绑定+<区服>+<账号>")
def bind_account(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    server_name = str(session.match.group(1) or "").strip()
    account = str(session.match.group(2) or "").strip()
    _bind_to_account(event, ctx, session.group_id, session.user_id, server_name, account)


@on_regex(r"^绑定\s+([^\s+]{1,32})\s+([^\s]{2,32})$", only_group=True, description="绑定 <区服> <账号>")
def bind_account_spaced(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    server_name = str(session.match.group(1) or "").strip()
    account = str(session.match.group(2) or "").strip()
    _bind_to_account(event, ctx, session.group_id, session.user_id, server_name, account)


def _bind_to_account(event, ctx, group_id: str, user_id: str, server_name: str, account: str) -> None:
    if not _valid_server_name(server_name):
        ctx.reply(event, "绑定失败，区服名只能包含中文、字母、数字、下划线和短横线，长度 1-32。")
        return
    service = BindingService(ctx)
    scope = _binding_scope(group_id, server_name)
    result = service.bind(scope, user_id, account)
    if result.message.startswith("绑定成功"):
        ctx.reply(event, f"绑定成功：{server_name}+{account} = {user_id}")
    else:
        ctx.reply(event, result.message)


@on_command("绑定", only_group=True, description="绑定 <区服> <账号>")
def bind_usage(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    if re.fullmatch(r"([^\s+]{1,32})\s+([^\s]{2,32})", session.argument):
        return
    ctx.reply(event, USAGE_TEXT)


@on_regex(r"^绑定\+.*$", only_group=True, description="绑定格式提示")
def bind_malformed(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    if re.fullmatch(r"^绑定\+([^+\s]{1,32})\+(.{2,32})$", session.text):
        return
    ctx.reply(event, USAGE_TEXT)


@on_command("解绑", only_group=True, description="解绑当前账号")
def unbind_account(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    service = BindingService(ctx)
    server_name = str(session.argument or "").strip()
    if server_name:
        if not _valid_server_name(server_name):
            ctx.reply(event, "解绑失败，区服名只能包含中文、字母、数字、下划线和短横线。")
            return
        scope = _binding_scope(session.group_id, server_name)
        result = service.unbind(scope, session.user_id)
        ctx.reply(event, f"{server_name} {result.message}")
        return
    removed = 0
    for scope in _group_scopes(service, session.group_id):
        result = service.unbind(scope, session.user_id)
        if "成功" in result.message:
            removed += 1
    ctx.reply(event, f"解绑成功：{removed} 个区服。" if removed else "当前没有绑定账号。")


@on_command("我的绑定", aliases=("查询绑定", "绑定查询"), only_group=True, description="查询当前绑定账号")
def query_binding(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    service = BindingService(ctx)
    labels = service.group_labels()
    rows = []
    for scope in _group_scopes(service, session.group_id):
        account = service.account_for_user(scope, session.user_id)
        if not account:
            continue
        server_name = _scope_server(scope, labels)
        rows.append(f"{server_name or session.group_id}+{account}")
    ctx.reply(event, "当前绑定账号：" + "；".join(rows) if rows else "当前没有绑定账号。")


@on_command("区服列表", aliases=("绑定区服", "账号区服"), only_group=True, description="查看本群已创建区服")
def list_servers(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    service = BindingService(ctx)
    rows = service.server_list(session.group_id)
    if not rows:
        ctx.reply(event, "本群还没有创建区服，请先在账号绑定后台创建区服。")
        return
    names = [str(row.get("server_name") or row.get("scope") or "") for row in rows]
    ctx.reply(event, "本群可绑定区服：" + "、".join(name for name in names if name))


@on_command("绑定记录", aliases=("查询绑定记录",), only_group=True, admin_only=True, description="管理员查询绑定记录")
def list_records(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    service = BindingService(ctx)
    rows = service.records(session.group_id, session.argument)
    if not rows:
        ctx.reply(event, "没有匹配的绑定记录。")
        return
    lines = _format_record_lines(rows, limit=12)
    more = "" if len(rows) <= 12 else f"\n……还有 {len(rows) - 12} 条，请到账号绑定后台查看。"
    ctx.reply(event, "绑定记录：\n" + "\n".join(lines) + more)


@on_command("导出绑定", only_group=True, admin_only=True, description="管理员导出绑定记录")
def export_records(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    service = BindingService(ctx)
    text = service.export_records(session.group_id, session.argument)
    ctx.reply(event, "绑定导出：\n" + text if text else "没有可导出的绑定记录。")


@on_command("导入绑定", only_group=True, admin_only=True, description="管理员批量导入绑定记录")
def import_records(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    payload = str(session.argument or "").strip()
    if not payload:
        ctx.reply(event, "导入失败，用法：导入绑定 区服|QQ|账号，每行一条；区服必须先在后台创建。")
        return
    service = BindingService(ctx)
    result = service.import_records(session.group_id, payload)
    ctx.reply(event, result.message)


@on_regex(r"^删除绑定\s+([^\s+]{1,32})\s+(\d{5,})$", only_group=True, admin_only=True, description="删除绑定 <区服> <QQ>")
def delete_record(event, ctx, session) -> None:
    if not _binding_enabled(ctx, session.group_id):
        return
    server_name = str(session.match.group(1) or "").strip()
    user_id = str(session.match.group(2) or "").strip()
    if not _valid_server_name(server_name):
        ctx.reply(event, "删除失败，区服名只能包含中文、字母、数字、下划线和短横线。")
        return
    service = BindingService(ctx)
    scope = _binding_scope(session.group_id, server_name)
    result = service.delete_binding(scope, user_id)
    ctx.reply(event, f"{server_name}/{user_id}：{result.message}")


def _binding_enabled(ctx, group_id: str) -> bool:
    return GroupSettingService(ctx).enabled(group_id, "bindings_enabled")


def _binding_scope(group_id: str, server_name: str) -> str:
    return f"{str(group_id).strip()}::{str(server_name).strip()}"


def _scope_server(scope: str, labels: dict[str, str]) -> str:
    text = str(scope or "").strip()
    if "::" in text:
        return text.split("::", 1)[1].strip()
    return str(labels.get(text, "") or "").strip()


def _group_scopes(service: BindingService, group_id: str) -> list[str]:
    prefix = f"{str(group_id).strip()}::"
    scopes = [str(scope) for scope in service.groups() if str(scope) == str(group_id).strip() or str(scope).startswith(prefix)]
    return scopes or [str(group_id).strip()]


def _valid_server_name(value: str) -> bool:
    return bool(re.fullmatch(r"[\w\u4e00-\u9fff-]{1,32}", str(value or "").strip()))


def _format_record_lines(rows: list[dict[str, str]], limit: int = 12) -> list[str]:
    result: list[str] = []
    for row in rows[: max(1, int(limit))]:
        server = str(row.get("server_name") or row.get("scope") or "").strip()
        user_id = str(row.get("user_id") or "").strip()
        account = str(row.get("account") or "").strip()
        if not user_id and not account:
            result.append(f"{server}：暂无绑定")
        else:
            result.append(f"{server}：{user_id} -> {account}")
    return result


MATCHERS.extend(
    [
        bind_account,
        bind_account_spaced,
        bind_usage,
        bind_malformed,
        unbind_account,
        query_binding,
        list_servers,
        list_records,
        export_records,
        import_records,
        delete_record,
    ]
)
