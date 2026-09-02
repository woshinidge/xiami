from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


PLUGIN_CODE = '''
PLUGIN_ID = "gate_echo"
PLUGIN_NAME = "Gate Echo"


def on_message(event, ctx):
    if event.text == "/gate":
        ctx.reply(event, "ok")


def on_event(event, ctx):
    if event.raw.get("notice_type") == "group_increase":
        ctx.send_group(event.group_id, "event-ok")
'''


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "gate_echo"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(PLUGIN_CODE, encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        loader.load_all()

        def group_message(group_id: str) -> XiamiMessage:
            return XiamiMessage(message_type="group", sender="10001", target=group_id, text="/gate")

        def group_event(group_id: str) -> PluginEvent:
            return PluginEvent(
                type="notice",
                raw={
                    "post_type": "notice",
                    "notice_type": "group_increase",
                    "group_id": group_id,
                    "user_id": "10001",
                },
            )

        loader.dispatch_message(group_message("20001"))
        loader.dispatch_event(group_event("20001"))
        expected_initial: list[tuple[str, str, str]] = []
        if sent != expected_initial:
            raise RuntimeError(f"default-closed group dispatch should not reply: {sent}")

        GroupSettingService(ctx).set_plugin_enabled("20001", "gate_echo", False)
        loader.dispatch_message(group_message("20001"))
        loader.dispatch_event(group_event("20001"))
        if sent != expected_initial:
            raise RuntimeError(f"disabled group still dispatched plugin: {sent}")

        loader.dispatch_message(group_message("20002"))
        loader.dispatch_event(group_event("20002"))
        expected_other_group = expected_initial
        if sent != expected_other_group:
            raise RuntimeError(f"other group should also default closed: {sent}")

        GroupSettingService(ctx).set_plugin_enabled("20001", "gate_echo", True)
        loader.dispatch_message(group_message("20001"))
        loader.dispatch_event(group_event("20001"))
        if sent[-2:] != [("20001", "ok", "group"), ("20001", "event-ok", "group")]:
            raise RuntimeError(f"re-enabled group dispatch failed: {sent}")

    print("group_plugin_gate_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
