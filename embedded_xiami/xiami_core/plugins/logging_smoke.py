from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    def send(target: str, text: str, message_type: str) -> SendResult:
        return SendResult(ok=True)

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = PluginContext(send_fn=send, plugin_id="demo", data_root=root / "data")
        ctx.log("started")
        ctx.log_warning("slow path")
        ctx.log_error("failed once")
        rows = ctx.recent_logs(10)
        if [row.get("level") for row in rows] != ["info", "warning", "error"]:
            raise RuntimeError(f"plugin log levels wrong: {rows!r}")
        if rows[-1].get("message") != "failed once" or rows[-1].get("plugin_id") != "demo":
            raise RuntimeError(f"plugin log payload wrong: {rows!r}")
        if not ctx.log_file().exists():
            raise RuntimeError("plugin log file not written")

        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "logger"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "PLUGIN_ID = 'logger'",
                    "PLUGIN_NAME = 'Logger'",
                    "def on_load(ctx):",
                    "    ctx.log('loaded')",
                    "def on_message(event, ctx):",
                    "    if event.text == 'warn':",
                    "        ctx.log_warning('warned')",
                ]
            ),
            encoding="utf-8",
        )
        loader = PluginLoader(
            plugin_root,
            PluginContext(send_fn=send, data_root=root / "data", state_store=PluginKVStore(root / "state")),
            state_store=PluginStateStore(root / "enabled.json"),
        )
        plugins = loader.load_all()
        if not plugins or plugins[0].error:
            raise RuntimeError(f"logger plugin load failed: {plugins}")
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="warn"))
        diag = loader.diagnostics()[0]
        if "loaded" not in "\n".join(diag.get("logs") or []) or "warned" not in "\n".join(diag.get("logs") or []):
            raise RuntimeError(f"diagnostic memory logs missing: {diag!r}")
        recent = diag.get("recent_logs") or []
        if not any(item.get("message") == "warned" and item.get("level") == "warning" for item in recent):
            raise RuntimeError(f"diagnostic persistent logs missing: {diag!r}")
        if not str(diag.get("log_file") or "").endswith("_logs.jsonl"):
            raise RuntimeError(f"diagnostic log file missing: {diag!r}")

    print("plugin logging smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
