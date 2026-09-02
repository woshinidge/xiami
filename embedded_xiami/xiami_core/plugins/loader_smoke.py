from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[str] = []

    def send(_target: str, text: str, _message_type: str) -> SendResult:
        sent.append(text)
        return SendResult(ok=True, detail="ok")

    with TemporaryDirectory() as temp:
        root = Path(temp)
        good = root / "good"
        good.mkdir()
        (good / "plugin.py").write_text(
            "\n".join(
                [
                    'PLUGIN_NAME = "Good"',
                    'PLUGIN_VERSION = "0.1.0"',
                    'PLUGIN_DESCRIPTION = "Good test plugin"',
                    "def on_load(ctx): ctx.log('good loaded')",
                    "def on_message(event, ctx):",
                    "    if event.text == 'ping': ctx.reply(event, 'pong')",
                ]
            ),
            encoding="utf-8",
        )

        bad = root / "bad"
        bad.mkdir()
        (bad / "plugin.py").write_text("raise RuntimeError('bad import')\n", encoding="utf-8")

        state = PluginStateStore(root / "plugins.json")
        ctx = PluginContext(send_fn=send)
        loader = PluginLoader(root, ctx, state)
        plugins = loader.load_all()
        if len(plugins) != 2:
            raise RuntimeError(f"plugin discovery failed: {plugins}")
        if not any(plugin.error for plugin in plugins if plugin.id == "bad"):
            raise RuntimeError(f"bad plugin error missing: {plugins}")
        bad_plugin = next(plugin for plugin in plugins if plugin.id == "bad")
        if bad_plugin.error_count != 1 or "bad import" not in bad_plugin.last_error:
            raise RuntimeError(f"bad plugin diagnostics missing: {bad_plugin}")
        good_plugin = next(plugin for plugin in plugins if plugin.id == "good")
        if good_plugin.version != "0.1.0" or good_plugin.description != "Good test plugin":
            raise RuntimeError(f"plugin metadata missing: {good_plugin}")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="tester", text="ping"))
        if sent != ["pong"]:
            raise RuntimeError(f"enabled plugin did not respond: {sent}")
        good_diag = next(item for item in loader.diagnostics() if item["id"] == "good")
        if good_diag["message_handled_count"] != 1 or good_diag["message_unhandled_count"] != 0:
            raise RuntimeError(f"message health not tracked: {good_diag}")

        loader.dispatch_message(XiamiMessage(message_type="private", sender="tester", text="noop"))
        good_diag = next(item for item in loader.diagnostics() if item["id"] == "good")
        if good_diag["message_handled_count"] != 1 or good_diag["message_unhandled_count"] != 1:
            raise RuntimeError(f"unhandled message not tracked: {good_diag}")
        catalog = ctx.runtime_registry.get("plugin_catalog", [])
        good_catalog = next(item for item in catalog if item["id"] == "good")
        bad_catalog = next(item for item in catalog if item["id"] == "bad")
        if good_catalog.get("message_unhandled_count") != 1 or "matcher_hit_count" not in good_catalog:
            raise RuntimeError(f"runtime catalog health not published: {good_catalog}")
        if bad_catalog.get("error_count") != 1 or "bad import" not in str(bad_catalog.get("last_error")):
            raise RuntimeError(f"runtime catalog error not published: {bad_catalog}")

        loader.set_enabled("good", False)
        loader.load_all()
        sent.clear()
        loader.dispatch_message(XiamiMessage(message_type="private", sender="tester", text="ping"))
        if sent:
            raise RuntimeError(f"disabled plugin responded: {sent}")

    print("plugin loader smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
