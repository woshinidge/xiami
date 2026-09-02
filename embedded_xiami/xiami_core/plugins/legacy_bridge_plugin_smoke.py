from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


LEGACY_BRIDGE_PLUGIN = """
from __future__ import annotations

PLUGIN_ID = "legacy_bridge"
PLUGIN_NAME = "Legacy Bridge"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "旧 OneBot/CQHTTP 风格插件迁移样例。"
PLUGIN_MODE = "legacy"
PLUGIN_CAPABILITIES = ["legacy:onebot-v11", "send:text", "message:private", "message:group", "event:notice"]
PLUGIN_CONFIG = {"trigger": "旧ping", "echo_prefix": "旧echo ", "welcome_enabled": False}


def on_load(ctx) -> None:
    ctx.log("Legacy Bridge 样例插件已加载")


def handle_message(bot, event, ctx) -> None:
    text = event.get_plain_text().strip() or event.text.strip()
    trigger = str(ctx.get_config("trigger", "旧ping"))
    echo_prefix = str(ctx.get_config("echo_prefix", "旧echo "))
    if text == trigger:
        bot.reply(event, f"legacy ok: {event.user_id}")
        return
    if text.startswith(echo_prefix):
        bot.send_msg(
            message_type=event.message_type,
            user_id=event.user_id or None,
            group_id=event.group_id or None,
            message=text[len(echo_prefix):].strip(),
        )


def on_event(bot, event, ctx) -> None:
    if event.notice_type == "group_increase" and ctx.get_config("welcome_enabled", False):
        bot.send_group_msg(event.group_id, f"欢迎 {event.user_id}")
"""


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, message_id="90001")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "legacy_bridge"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(LEGACY_BRIDGE_PLUGIN.strip() + "\n", encoding="utf-8")

        loader = PluginLoader(plugin_root, PluginContext(send_fn=send), PluginStateStore(root / "state.json"))
        plugins = loader.load_all()
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"legacy bridge load failed: {plugins!r}")

        plugin = plugins[0]
        if not plugin.context or "Legacy Bridge 样例插件已加载" not in plugin.context.logs:
            raise RuntimeError(f"legacy bridge on_load missing: {plugin.context.logs if plugin.context else None!r}")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="旧ping"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10002", target="20001", text="旧echo hello"))
        loader.dispatch_event(
            PluginEvent(
                type="notice",
                raw={"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 10003},
            )
        )

    expected = [
        ("10001", "legacy ok: 10001", "private"),
        ("20001", "hello", "group"),
    ]
    if sent != expected:
        raise RuntimeError(f"legacy bridge replies mismatch: {sent!r}")

    print("legacy bridge plugin smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
