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
            plugin_id="context_media",
        )

        cq_message = XiamiMessage(
            message_type="group",
            sender="10001",
            target="20001",
            text="hello",
            raw_message="hello[CQ:image,file=file:///tmp/a.png][CQ:reply,id=456]",
        )
        if ctx.image_files(cq_message) != ["file:///tmp/a.png"]:
            raise RuntimeError(f"CQ image files failed: {ctx.image_files(cq_message)!r}")
        if ctx.first_image(cq_message) != "file:///tmp/a.png":
            raise RuntimeError("first_image failed for CQ message")
        if ctx.reply_ids(cq_message) != ["456"] or ctx.first_reply_id(cq_message) != "456":
            raise RuntimeError(f"CQ reply ids failed: {ctx.reply_ids(cq_message)!r}")
        if ctx.plain_text(cq_message) != "hello[图片][回复]":
            raise RuntimeError(f"plain_text failed for CQ message: {ctx.plain_text(cq_message)!r}")

        raw_event = PluginEvent(
            type="message",
            raw={
                "message_type": "group",
                "group_id": 20001,
                "message": [
                    {"type": "text", "data": {"text": "img"}},
                    {"type": "image", "data": {"url": "https://example.com/a.jpg"}},
                    {"type": "reply", "data": {"message_id": "789"}},
                ],
            },
        )
        if ctx.image_files(raw_event) != ["https://example.com/a.jpg"]:
            raise RuntimeError("OneBot image url failed")
        if ctx.reply_ids(raw_event) != ["789"]:
            raise RuntimeError("OneBot reply message_id failed")
        if ctx.segment_data(raw_event, "image") != [{"url": "https://example.com/a.jpg"}]:
            raise RuntimeError(f"segment_data failed: {ctx.segment_data(raw_event, 'image')!r}")

        tuple_message = XiamiMessage(
            message_type="private",
            sender="10002",
            text="tuple",
            segments=(
                MessageSegment("image", {"file": "cache://b.png"}),
                MessageSegment("image", {"path": "C:/tmp/c.png"}),
                MessageSegment("reply", {"id": "900"}),
            ),
        )
        if ctx.image_files(tuple_message) != ["cache://b.png", "C:/tmp/c.png"]:
            raise RuntimeError("tuple image segments failed")
        if ctx.first_reply_id(tuple_message) != "900":
            raise RuntimeError("tuple reply segment failed")

    print("plugin context media smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
