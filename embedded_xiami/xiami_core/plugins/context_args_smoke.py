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
        ctx = PluginContext(send_fn=send, data_root=root / "data", state_store=PluginKVStore(root / "state"))

        cq_text = "禁言 [CQ:at,qq=10001] 10002 5分钟"
        if ctx.parse_user_ids(cq_text) != ["10001", "10002"]:
            raise RuntimeError(f"CQ user id parse failed: {ctx.parse_user_ids(cq_text)!r}")
        if ctx.parse_duration(cq_text) != 300:
            raise RuntimeError(f"unit duration parse failed: {ctx.parse_duration(cq_text)!r}")

        command_message = XiamiMessage(
            message_type="group",
            sender="99999",
            target="20001",
            text="禁言 10001 60",
        )
        if ctx.first_user_id(command_message) != "10001":
            raise RuntimeError("first_user_id failed for XiamiMessage")
        if ctx.parse_duration(command_message) != 60:
            raise RuntimeError("unitless duration should use last number")

        raw_event = PluginEvent(
            type="message",
            raw={
                "message_type": "group",
                "group_id": 20001,
                "message": [
                    {"type": "at", "data": {"qq": "10003"}},
                    {"type": "text", "data": {"text": " 2h"}},
                ],
            },
        )
        if ctx.parse_user_ids(raw_event) != ["10003"]:
            raise RuntimeError("OneBot at user id parse failed")
        if ctx.parse_duration(raw_event) != 7200:
            raise RuntimeError("hour duration parse failed")

        if ctx.parse_duration("清理 1天", max_seconds=3600) != 3600:
            raise RuntimeError("max_seconds clamp failed")
        if ctx.parse_duration("无时长", default=600) != 600:
            raise RuntimeError("duration default failed")
        if ctx.parse_key_value("关键词=回复内容") != ("关键词", "回复内容"):
            raise RuntimeError("key=value parse failed")
        if ctx.parse_key_value("标题：内容：保留") != ("标题", "内容：保留"):
            raise RuntimeError("colon key/value parse failed")
        if ctx.parse_key_value("无分隔符") != ("", ""):
            raise RuntimeError("missing key/value separator should return empty pair")

    print("plugin context args smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
