from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
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
        plugin_dir = plugin_root / "state_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin_config.json").write_text('{"prefix":"[override]"}', encoding="utf-8")
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "PLUGIN_CONFIG = {'prefix': '[default]'}",
                    "def on_message(event, ctx):",
                    "    count = int(ctx.get_state('count', 0)) + 1",
                    "    ctx.set_state('count', count)",
                    "    ctx.reply(event, f\"{ctx.get_config('prefix')} {count}\")",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(send_fn=send, data_root=root / "data", state_store=PluginKVStore(root / "plugin_state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        loader.load_all()
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="a"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="b"))
        if sent != [("10001", "[override] 1", "private"), ("10001", "[override] 2", "private")]:
            raise RuntimeError(f"state/config failed: {sent}")
        if loader.plugins[0].context.get_state("count") != 2:
            raise RuntimeError("state was not persisted through plugin context")

    print("plugin state config smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
