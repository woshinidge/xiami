from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
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
            plugin_id="context_mention",
            config={"bot_qq": "313420054"},
        )

        cq_message = XiamiMessage(
            message_type="group",
            sender="10001",
            target="20001",
            text="@313420054 hello",
            raw_message="[CQ:at,qq=313420054] hello [CQ:at,qq=10002]",
        )
        if ctx.at_users(cq_message) != ["313420054", "10002"]:
            raise RuntimeError(f"CQ at users failed: {ctx.at_users(cq_message)!r}")
        if not ctx.is_at_me(cq_message):
            raise RuntimeError("is_at_me failed for configured bot_qq")
        if not ctx.has_at(cq_message, "10002"):
            raise RuntimeError("has_at failed for explicit user")
        if ctx.strip_at(cq_message, "313420054") != "hello [CQ:at,qq=10002]":
            raise RuntimeError(f"strip_at failed for selected at: {ctx.strip_at(cq_message, '313420054')!r}")
        if ctx.strip_at(cq_message) != "hello":
            raise RuntimeError(f"strip_at failed for all at: {ctx.strip_at(cq_message)!r}")

        segment_event = PluginEvent(
            type="message",
            raw={
                "message_type": "group",
                "group_id": 20001,
                "user_id": 10001,
                "message": [
                    {"type": "at", "data": {"qq": "all"}},
                    {"type": "text", "data": {"text": " notice "}},
                ],
            },
        )
        if ctx.at_users(segment_event) != ["all"]:
            raise RuntimeError("OneBot segment at users failed")
        if not ctx.has_at(segment_event):
            raise RuntimeError("has_at default all failed")
        if ctx.strip_at(segment_event) != "notice":
            raise RuntimeError("strip_at failed for OneBot segment event")

        tuple_segments = XiamiMessage(
            message_type="group",
            sender="10003",
            target="20001",
            text="问答",
            segments=(
                MessageSegment("at", {"qq": "313420054"}),
                MessageSegment("text", {"text": " 你好"}),
            ),
        )
        if ctx.message_segments(tuple_segments)[0].type != "at":
            raise RuntimeError("message_segments failed for XiamiMessage tuple")
        if ctx.strip_at(tuple_segments) != "你好":
            raise RuntimeError("strip_at failed for XiamiMessage tuple segments")

    print("plugin context mention smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
