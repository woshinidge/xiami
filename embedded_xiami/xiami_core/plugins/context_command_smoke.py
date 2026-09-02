from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.kv import PluginKVStore


def main() -> int:
    def send(target: str, text: str, message_type: str) -> SendResult:
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = PluginContext(
            send_fn=send,
            data_root=root / "data",
            state_store=PluginKVStore(root / "state"),
            plugin_id="context_command",
        )

        group_message = XiamiMessage(message_type="group", sender="10001", target="20001", text="/答题 今天")
        private_message = XiamiMessage(message_type="private", sender="10002", text="菜单 今日")
        raw_event = PluginEvent(
            type="message",
            raw={"message_type": "group", "group_id": 20002, "user_id": 10003, "raw_message": "!Echo Hello"},
        )
        segment_event = PluginEvent(
            type="message",
            raw={
                "message_type": "private",
                "user_id": 10004,
                "message": [{"type": "text", "data": {"text": "帮助 参数"}}],
            },
        )

        if not ctx.is_group_message(group_message) or ctx.is_private_message(group_message):
            raise RuntimeError("group/private message helpers failed for group")
        if not ctx.is_private_message(private_message) or ctx.is_group_message(private_message):
            raise RuntimeError("group/private message helpers failed for private")
        if ctx.message_text(group_message) != "/答题 今天":
            raise RuntimeError("message_text failed for XiamiMessage")
        if ctx.match_command(group_message, "答题") != ("答题", "今天"):
            raise RuntimeError("match_command failed for prefixed command")
        if ctx.command_args(private_message, "菜单") != "今日":
            raise RuntimeError("command_args failed for no-prefix command")
        if ctx.match_command(raw_event, "echo") != ("echo", "Hello"):
            raise RuntimeError("match_command failed for raw PluginEvent")
        if ctx.group_id_of(raw_event) != "20002" or ctx.user_id_of(raw_event) != "10003":
            raise RuntimeError("raw PluginEvent id helpers failed")
        if ctx.message_text(segment_event) != "帮助 参数":
            raise RuntimeError("message_text failed for OneBot segment list")
        if ctx.match_command(segment_event, "帮助") != ("帮助", "参数"):
            raise RuntimeError("match_command failed for segment text")
        if ctx.match_command(group_message, "不存在") is not None:
            raise RuntimeError("match_command matched wrong command")

    print("plugin context command smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
