from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "async_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_command, on_keyword",
                    "PLUGIN_ID = 'async_case'",
                    "PLUGIN_NAME = 'Async Case'",
                    "MATCHERS = []",
                    "async def on_load(ctx):",
                    "    ctx.set_state('loaded', True)",
                    "    ctx.log('async loaded')",
                    "async def on_message(event, ctx):",
                    "    if event.text == 'native async':",
                    "        ctx.reply(event, 'native async ok')",
                    "async def on_event(event, ctx):",
                    "    if event.raw.get('notice_type') == 'poke':",
                    "        ctx.log('async event ok')",
                    "@on_command('/async')",
                    "async def async_cmd(event, ctx, session):",
                    "    ctx.reply(event, 'cmd:' + session.argument)",
                    "@on_keyword('async-key')",
                    "async def async_keyword(event, ctx, session):",
                    "    ctx.reply(event, 'keyword:' + session.argument)",
                    "MATCHERS.extend([async_cmd, async_keyword])",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, data_root=root / "data")
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "state.json"))
        plugins = loader.load_all()
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"async plugin load failed: {plugins}")
        plugin_ctx = plugins[0].context
        if not plugin_ctx or plugin_ctx.get_state("loaded") is not True:
            raise RuntimeError("async on_load was not awaited")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="native async"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="/async hello"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="prefix async-key"))
        loader.dispatch_event(plugin_event_from_onebot({"post_type": "notice", "notice_type": "poke", "user_id": 10001}))

        expected = [
            ("10001", "native async ok", "private"),
            ("10001", "cmd:hello", "private"),
            ("10001", "keyword:prefix async-key", "private"),
        ]
        if sent != expected:
            raise RuntimeError(f"async plugin replies failed: {sent}")
        if "async event ok" not in ctx.logs:
            raise RuntimeError(f"async on_event was not awaited: {ctx.logs}")

    print("async compat smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
