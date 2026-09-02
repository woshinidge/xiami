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
        plugin_dir = plugin_root / "diag_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "PLUGIN_NAME = 'Diag'",
                    "def on_message(event, ctx):",
                    "    ctx.reply(event, 'ok')",
                    "def on_event(event, ctx):",
                    "    ctx.log('event:' + event.type)",
                ]
            ),
            encoding="utf-8",
        )
        loader = PluginLoader(plugin_root, PluginContext(send_fn=send), state_store=PluginStateStore(root / "state.json"))
        loader.load_all()
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="hello"))
        loader.dispatch_event(plugin_event_from_onebot({"post_type": "notice", "notice_type": "poke"}))
        diagnostics = loader.diagnostics()
        if len(diagnostics) != 1:
            raise RuntimeError(diagnostics)
        item = diagnostics[0]
        if item["message_count"] != 1 or item["event_count"] != 1 or item["error_count"] != 0:
            raise RuntimeError(diagnostics)
    print("plugin diagnostics smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
