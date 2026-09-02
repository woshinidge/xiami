from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
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

    with TemporaryDirectory() as temp:
        root = Path(temp)
        plugin_root = root / "plugins"
        plugin_root.mkdir()
        (plugin_root / "legacy_timer.py").write_text(
            "\n".join(
                [
                    "def handler(context):",
                    "    return 'handled:' + context.message",
                    "",
                    "def tick(ctx, session):",
                    "    ctx.log('legacy timer:' + session.name)",
                    "    ctx.set_state('legacy_timer', session.name)",
                    "",
                    "def register(manager):",
                    "    manager.add_plugin({'key': 'legacy_timer', 'name': 'Legacy Timer', 'hooks': ('message.private',)})",
                    "    manager.register_handler('legacy_timer', handler)",
                    "    manager.register_timer('legacy_tick', 2, tick, description='旧心跳', key='legacy_timer')",
                    "",
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
        loader = PluginLoader(plugin_root, ctx, PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if len(plugins) != 1:
            raise RuntimeError(f"legacy timer plugin count mismatch: {plugins!r}")
        plugin = plugins[0]
        if plugin.error:
            raise RuntimeError(f"legacy timer plugin error: {plugin.error}")
        if "旧文件hook:message.private" not in plugin.commands:
            raise RuntimeError(f"legacy hook command missing: {plugin.commands}")
        if "旧文件定时:legacy_tick/2s - 旧心跳" not in plugin.commands:
            raise RuntimeError(f"legacy timer command missing: {plugin.commands}")
        if "legacy-schedules:1" not in plugin.capabilities:
            raise RuntimeError(f"legacy timer capability missing: {plugin.capabilities}")
        if [(name, seconds) for name, seconds, _callback in timers] != [("legacy_tick", 2.0)]:
            raise RuntimeError(f"legacy timer not registered: {timers!r}")
        timers[0][2]()
        if not plugin.context or plugin.context.get_state("legacy_timer") != "legacy_tick":
            raise RuntimeError("legacy timer callback did not update plugin state")
        if "legacy timer:legacy_tick" not in plugin.context.logs:
            raise RuntimeError(f"legacy timer log missing: {plugin.context.logs!r}")
    print("legacy file timer smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
