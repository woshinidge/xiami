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
        plugin_dir = plugin_root / "interval_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_interval",
                    "PLUGIN_ID = 'interval_case'",
                    "SCHEDULES = []",
                    "FIRED = 0",
                    "@on_interval(0.5, name='heartbeat', description='心跳')",
                    "def heartbeat(ctx, session):",
                    "    ctx.log('interval:' + session.name)",
                    "    ctx.set_state('heartbeat', ctx.get_state('heartbeat', 0) + 1)",
                    "@on_interval(1, name='noarg')",
                    "def noarg():",
                    "    global FIRED",
                    "    FIRED += 1",
                    "@on_interval(1.5, name='async-job')",
                    "async def async_job(ctx):",
                    "    ctx.log('async interval')",
                    "SCHEDULES.extend([heartbeat, noarg, async_job])",
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
            raise RuntimeError(f"plugin load failed: {plugins}")
        labels = "\n".join(plugins[0].commands)
        if "定时:heartbeat/0.5s - 心跳" not in labels or "定时:noarg/1s" not in labels:
            raise RuntimeError(f"interval labels missing: {labels}")
        if [(name, seconds) for name, seconds, _callback in timers] != [
            ("heartbeat", 0.5),
            ("noarg", 1.0),
            ("async-job", 1.5),
        ]:
            raise RuntimeError(f"timers not registered: {timers!r}")

        for _name, _seconds, callback in timers:
            callback()

        plugin = plugins[0]
        if not plugin.context or plugin.context.get_state("heartbeat", 0) != 1:
            raise RuntimeError("interval context callback did not run")
        if not plugin.module or getattr(plugin.module, "FIRED", 0) != 1:
            raise RuntimeError("interval no-arg callback did not run")
        if "interval:heartbeat" not in plugin.context.logs or "async interval" not in plugin.context.logs:
            raise RuntimeError(f"interval logs missing: {plugin.context.logs!r}")

    print("plugin compat interval smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
