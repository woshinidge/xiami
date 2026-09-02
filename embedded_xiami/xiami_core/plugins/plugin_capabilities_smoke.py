from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    timers: list[tuple[str, float, Callable[[], None]]] = []

    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    def register_timer(name: str, seconds: float, callback: Callable[[], None]) -> None:
        timers.append((name, seconds, callback))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "capability_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_command, on_interval, on_notice",
                    "PLUGIN_ID = 'capability_case'",
                    "PLUGIN_CAPABILITIES = ['onebot:get_login_info', 'send:image']",
                    "MATCHERS = []",
                    "EVENT_MATCHERS = []",
                    "SCHEDULES = []",
                    "@on_command('/cap')",
                    "def cap(ctx, session):",
                    "    ctx.log('cap')",
                    "@on_notice('group_increase')",
                    "def notice(ctx, session):",
                    "    ctx.log('notice')",
                    "@on_interval(5, name='cap-timer')",
                    "def timer(ctx):",
                    "    ctx.log('timer')",
                    "def on_event(event, ctx):",
                    "    ctx.log('event')",
                    "MATCHERS.append(cap)",
                    "EVENT_MATCHERS.append(notice)",
                    "SCHEDULES.append(timer)",
                ]
            ),
            encoding="utf-8",
        )

        ctx = PluginContext(
            send_fn=send,
            data_root=root / "data",
            state_store=PluginKVStore(root / "state"),
            timer_fn=register_timer,
        )
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"plugin load failed: {plugins!r}")

        diagnostics = loader.diagnostics()
        capabilities = diagnostics[0].get("capabilities") or []
        expected = {
            "onebot:get_login_info",
            "send:image",
            "message-matchers:1",
            "event-matchers:1",
            "schedules:1",
            "on_event",
        }
        missing = expected.difference(capabilities)
        if missing:
            raise RuntimeError(f"capabilities missing: {sorted(missing)} from {capabilities!r}")

        labels = "\n".join(diagnostics[0].get("commands") or [])
        if "/cap" not in labels or "事件:notice/group_increase" not in labels or "定时:cap-timer/5s" not in labels:
            raise RuntimeError(f"command labels missing: {labels}")

    print("plugin capabilities smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
