from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []
    onebot_calls: list[tuple[str, dict[str, Any]]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, message_id="legacy-hook")

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        onebot_calls.append((action, params))
        return {"status": "ok", "retcode": 0, "data": {}}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "legacy_hooks_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.legacy import legacy_bot",
                    "PLUGIN_ID = 'legacy_hooks_case'",
                    "PLUGIN_NAME = '旧 Hook 兼容样例'",
                    "PLUGIN_CAPABILITIES = ['legacy:hooks']",
                    "def at_bot(context, ctx):",
                    "    ctx.reply(context.event, 'at:' + context.message)",
                    "def group_increase(bot, context):",
                    "    bot.send_group_msg(context.group_id, 'welcome:' + context.user_id)",
                    "def group_add(context, ctx):",
                    "    legacy_bot(ctx).set_group_add_request(context.event['flag'], context.event.get('sub_type', 'add'), True, 'ok')",
                    "def friend(context):",
                    "    return {'handled': True}",
                    "LEGACY_HOOK_HANDLERS = {",
                    "    'message.at_bot': [at_bot],",
                    "    'notice.group_increase': [group_increase],",
                    "    'request.group_add': [group_add],",
                    "    'request.friend': [friend],",
                    "    'admin': [],",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        ctx = PluginContext(send_fn=send, onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"legacy hooks plugin load failed: {plugins!r}")

        loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10001",
                target="20001",
                text="@10000 ping",
                raw_message="[CQ:at,qq=10000] ping",
                segments=(MessageSegment("at", {"qq": "10000"}), MessageSegment("text", {"text": " ping"})),
            )
        )
        loader.dispatch_event(
            PluginEvent(
                type="notice",
                raw={"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 10002},
            )
        )
        loader.dispatch_event(
            PluginEvent(
                type="request",
                raw={
                    "post_type": "request",
                    "request_type": "group",
                    "sub_type": "add",
                    "group_id": 20001,
                    "user_id": 10003,
                    "flag": "flag-1",
                },
            )
        )
        loader.dispatch_event(
            PluginEvent(
                type="request",
                raw={"post_type": "request", "request_type": "friend", "user_id": 10004, "flag": "flag-2"},
            )
        )

        if sent != [("20001", "at:ping", "group"), ("20001", "welcome:10002", "group")]:
            raise RuntimeError(f"legacy hook sends failed: {sent!r}")
        expected_call = (
            "set_group_add_request",
            {"flag": "flag-1", "sub_type": "add", "approve": True, "reason": "ok"},
        )
        if expected_call not in onebot_calls:
            raise RuntimeError(f"legacy hook onebot call missing: {onebot_calls!r}")
        diagnostic = loader.diagnostics()[0]
    capabilities = diagnostic.get("capabilities") or []
    if "legacy-hooks:5" not in capabilities:
        raise RuntimeError(f"legacy hook capability missing: {diagnostic!r}")
    if "legacy-admin-hook" not in capabilities:
        raise RuntimeError(f"legacy admin hook capability missing: {diagnostic!r}")
        commands = "\n".join(diagnostic.get("commands") or [])
        if "旧hook:message.at_bot" not in commands or "旧hook:request.group_add" not in commands:
            raise RuntimeError(f"legacy hook command labels missing: {commands}")
        hits = diagnostic.get("matcher_hit_count") or {}
        for label in ("旧hook:message.at_bot", "旧hook:notice.group_increase", "旧hook:request.group_add"):
            if hits.get(label) != 1:
                raise RuntimeError(f"legacy hook hit missing {label}: {hits!r}")
    print("legacy hooks smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
