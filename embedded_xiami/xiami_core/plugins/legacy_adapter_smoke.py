from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []
    onebot_calls: list[tuple[str, dict[str, Any]]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, message_id="12345")

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        onebot_calls.append((action, params))
        return {"status": "ok", "retcode": 0, "data": {}}

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "legacy_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.legacy import legacy_bot",
                    "PLUGIN_ID = 'legacy_case'",
                    "PLUGIN_CAPABILITIES = ['legacy:onebot-v11']",
                    "LEGACY_MESSAGE_HANDLERS = []",
                    "LEGACY_EVENT_HANDLERS = []",
                    "def message_handler(bot, event):",
                    "    if event.get('post_type') == 'message' and event.text == 'ping':",
                    "        bot.send_private_msg(event.user_id, 'legacy:' + event.text)",
                    "def event_handler(event, ctx):",
                    "    if event.notice_type == 'group_increase':",
                    "        bot = legacy_bot(ctx)",
                    "        bot.send_group_msg(event.group_id, 'welcome:' + event.user_id)",
                    "        bot.set_group_card(event.group_id, event.user_id, '新成员')",
                    "LEGACY_MESSAGE_HANDLERS.append(message_handler)",
                    "LEGACY_EVENT_HANDLERS.append(event_handler)",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"plugin load failed: {plugins!r}")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="ping"))
        loader.dispatch_event(
            PluginEvent(
                type="notice",
                raw={"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 10002},
            )
        )

        if sent != [("10001", "legacy:ping", "private"), ("20001", "welcome:10002", "group")]:
            raise RuntimeError(f"legacy sends failed: {sent!r}")
        if onebot_calls != [("set_group_card", {"group_id": 20001, "user_id": 10002, "card": "新成员"})]:
            raise RuntimeError(f"legacy onebot calls failed: {onebot_calls!r}")

        diagnostic = loader.diagnostics()[0]
        capabilities = diagnostic.get("capabilities") or []
        for expected in ("legacy:onebot-v11", "legacy-message-handlers:1", "legacy-event-handlers:1"):
            if expected not in capabilities:
                raise RuntimeError(f"legacy capability missing: {expected} from {capabilities!r}")
        if diagnostic.get("migration_status") != "旧插件兼容接入":
            raise RuntimeError(f"legacy migration status missing: {diagnostic!r}")
        labels = "\n".join(diagnostic.get("commands") or [])
        if "旧消息处理器:1" not in labels or "旧事件处理器:1" not in labels:
            raise RuntimeError(f"legacy labels missing: {labels}")

    print("plugin legacy adapter smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
