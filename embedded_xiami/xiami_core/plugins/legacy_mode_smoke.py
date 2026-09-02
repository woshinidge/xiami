from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_dir = root / "legacy_mode_case"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "PLUGIN_ID = 'legacy_mode_case'",
                    "PLUGIN_MODE = 'legacy'",
                    "def handle_message(bot, event):",
                    "    if event.text == 'ping':",
                    "        bot.reply(event, 'legacy-mode:' + event.user_id)",
                    "def on_event(bot, event):",
                    "    if event.notice_type == 'group_decrease':",
                    "        bot.send_group_msg(event.group_id, 'leave:' + event.user_id)",
                ]
            ),
            encoding="utf-8",
        )

        loader = PluginLoader(root, PluginContext(send_fn=send), PluginStateStore(root / "state.json"))
        plugins = loader.load_all()
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"plugin load failed: {plugins!r}")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="ping"))
        loader.dispatch_event(
            PluginEvent(
                type="notice",
                raw={"post_type": "notice", "notice_type": "group_decrease", "group_id": 20001, "user_id": 10002},
            )
        )

        if sent != [("10001", "legacy-mode:10001", "private"), ("20001", "leave:10002", "group")]:
            raise RuntimeError(f"legacy mode dispatch failed: {sent!r}")

        diagnostic = loader.diagnostics()[0]
        capabilities = diagnostic.get("capabilities") or []
        if "legacy-mode" not in capabilities or diagnostic.get("migration_status") != "旧插件兼容接入":
            raise RuntimeError(f"legacy mode diagnostics missing: {diagnostic!r}")
        if "旧模式:hooks" not in "\n".join(diagnostic.get("commands") or []):
            raise RuntimeError(f"legacy mode command label missing: {diagnostic!r}")

    print("plugin legacy mode smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
