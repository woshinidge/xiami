from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True, message_id=str(len(sent)))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "compat_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_command",
                    "PLUGIN_ID = 'compat_case'",
                    "PLUGIN_CONFIG = {'prefix': '[ok]'}",
                    "MATCHERS = []",
                    "def on_load(ctx):",
                    "    (ctx.data_dir() / 'loaded.txt').write_text('yes', encoding='utf-8')",
                    "@on_command('/test')",
                    "def test_cmd(event, ctx, arg):",
                    "    ctx.reply(event, ctx.get_config('prefix') + ' ' + arg)",
                    "@on_command('兑换', aliases=('兑换卡密',))",
                    "def redeem_cmd(event, ctx, session):",
                    "    ctx.reply(event, session.command + ':' + session.argument)",
                    "MATCHERS.append(test_cmd)",
                    "MATCHERS.append(redeem_cmd)",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, data_root=root / "data")
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "state.json"))
        plugins = loader.load_all()
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"plugin load failed: {plugins}")
        if not (root / "data" / "compat_case" / "loaded.txt").exists():
            raise RuntimeError("plugin data dir was not created")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="/test hello"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="兑换卡密 TEST-B"))
        if sent != [("10001", "[ok] hello", "private"), ("10001", "兑换卡密:TEST-B", "private")]:
            raise RuntimeError(f"compat matcher reply failed: {sent}")

    print("plugin compat smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
