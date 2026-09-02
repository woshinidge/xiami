from __future__ import annotations

import tempfile
from pathlib import Path

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
        plugin_dir = plugin_root / "raw_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "def on_event(event, ctx):",
                    "    if event.type == 'message' and event.raw.get('message_id') == 42:",
                    "        ctx.send_private(event.user_id, 'raw:' + event.text)",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "state.json"))
        loader.load_all()
        payload = {"post_type": "message", "message_type": "private", "user_id": 10001, "message_id": 42}
        message = XiamiMessage(message_type="private", sender="10001", text="hello")
        loader.dispatch_event(plugin_event_from_onebot(payload, message))
        if sent != [("10001", "raw:hello", "private")]:
            raise RuntimeError(f"raw event dispatch failed: {sent}")

    print("plugin raw event smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
