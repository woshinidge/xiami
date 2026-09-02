from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    def send(target: str, text: str, message_type: str) -> SendResult:
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "error_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "PLUGIN_ID = 'error_case'",
                    "PLUGIN_NAME = 'Error Case'",
                    "def on_message(event, ctx):",
                    "    raise RuntimeError('message-' + event.text)",
                    "def on_event(event, ctx):",
                    "    raise RuntimeError('event-' + event.type)",
                ]
            ),
            encoding="utf-8",
        )

        loader = PluginLoader(plugin_root, PluginContext(send_fn=send), state_store=PluginStateStore(root / "state.json"))
        loader.load_all()
        for index in range(12):
            loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text=str(index)))
        loader.dispatch_event(plugin_event_from_onebot({"post_type": "notice", "notice_type": "poke"}))
        diagnostics = loader.diagnostics()

    if len(diagnostics) != 1:
        raise RuntimeError(diagnostics)
    item = diagnostics[0]
    if item["error_count"] != 13:
        raise RuntimeError(diagnostics)
    if item["last_error"] != "事件处理失败：event-notice":
        raise RuntimeError(diagnostics)
    history = item["error_history"]
    if len(history) != 10:
        raise RuntimeError(history)
    if history[0] != "消息处理失败：message-3" or history[-1] != "事件处理失败：event-notice":
        raise RuntimeError(history)

    print("plugin diagnostics history smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
