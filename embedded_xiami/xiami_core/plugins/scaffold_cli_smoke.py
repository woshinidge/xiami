from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Callable

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.scaffold_cli import main as scaffold_cli_main
from xiami_core.plugins.state import PluginStateStore
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups


def main() -> int:
    sent: list[tuple[str, str, str]] = []
    timers: list[tuple[str, float, Callable[[], None]]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    def register_timer(name: str, seconds: float, callback: Callable[[], None]) -> None:
        timers.append((name, seconds, callback))

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        if scaffold_cli_main(
            [
                "legacy_notice",
                "--plugin-root",
                str(plugin_root),
                "--name",
                "Legacy Notice",
                "--command",
                "公告",
            ]
        ) != 0:
            raise RuntimeError("scaffold cli failed")
        if scaffold_cli_main(
            [
                "legacy_event",
                "--plugin-root",
                str(plugin_root),
                "--name",
                "Legacy Event",
                "--kind",
                "event",
            ]
        ) != 0:
            raise RuntimeError("event scaffold cli failed")
        if scaffold_cli_main(
            [
                "legacy_timer",
                "--plugin-root",
                str(plugin_root),
                "--name",
                "Legacy Timer",
                "--kind",
                "timer",
            ]
        ) != 0:
            raise RuntimeError("timer scaffold cli failed")
        plugin_dir = plugin_root / "legacy_notice"
        if not (plugin_dir / "plugin.py").is_file() or not (plugin_dir / "plugin_config.json").is_file():
            raise RuntimeError("scaffold files missing")
        event_plugin_dir = plugin_root / "legacy_event"
        if not (event_plugin_dir / "plugin.py").is_file() or not (event_plugin_dir / "README.md").is_file():
            raise RuntimeError("event scaffold files missing")
        timer_plugin_dir = plugin_root / "legacy_timer"
        if not (timer_plugin_dir / "plugin.py").is_file() or not (timer_plugin_dir / "README.md").is_file():
            raise RuntimeError("timer scaffold files missing")

        (plugin_dir / "plugin_config.json").write_text(
            '{"admins":["10001"],"cooldown_seconds":30}',
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
        if len(plugins) != 3 or any(plugin.error for plugin in plugins):
            raise RuntimeError(f"scaffold plugin did not load: {plugins!r}")
        enable_loaded_plugins_for_groups(ctx, plugins)
        plugin_by_id = {plugin.id: plugin for plugin in plugins}
        if [(name, seconds) for name, seconds, _callback in timers] != [("scaffold_timer", 60.0)]:
            raise RuntimeError(f"timer scaffold did not register timer: {timers!r}")

        loader.dispatch_message(XiamiMessage(message_type="group", sender="99999", target="20001", text="公告 hello"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="公告 hello"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="公告 again"))
        loader.dispatch_event(
            PluginEvent(
                type="notice",
                raw={"post_type": "notice", "notice_type": "group_increase", "group_id": 20001, "user_id": 10002},
            )
        )

        texts = [item[1] for item in sent]
        if texts[0] != "permission denied":
            raise RuntimeError(f"non-admin was not denied: {texts!r}")
        if "Legacy Notice handled #1: hello" not in texts[1]:
            raise RuntimeError(f"admin command did not run: {texts!r}")
        if not texts[2].startswith("cooldown:"):
            raise RuntimeError(f"cooldown did not trigger: {texts!r}")
        if "Legacy Event saw notice #1" not in texts[3]:
            raise RuntimeError(f"event scaffold did not send notice: {texts!r}")
        command_plugin = plugin_by_id["legacy_notice"]
        event_plugin = plugin_by_id["legacy_event"]
        timer_plugin = plugin_by_id["legacy_timer"]
        if command_plugin.context is None or command_plugin.context.get_state_int("handled_count") != 1:
            raise RuntimeError("scaffold plugin state was not updated")
        if event_plugin.context is None or event_plugin.context.get_state_int("event_count") != 1:
            raise RuntimeError("event scaffold plugin state was not updated")
        timers[0][2]()
        if timer_plugin.context is None or timer_plugin.context.get_state_int("timer_count") != 1:
            raise RuntimeError("timer scaffold plugin state was not updated")
        if "Legacy Timer timer #1: scaffold_timer/60.0s" not in timer_plugin.context.logs:
            raise RuntimeError(f"timer scaffold log missing: {timer_plugin.context.logs!r}")

    print("plugin scaffold cli smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
