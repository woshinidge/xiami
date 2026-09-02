from __future__ import annotations

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    ctx = PluginContext(send_fn=send)
    ctx.send_private_segments(
        "10001",
        [
            MessageSegment("text", {"text": "hi["}),
            MessageSegment("image", {"file": "file:///tmp/a,b.png"}),
        ],
    )
    ctx.send_group_segments(
        "20001",
        [
            {"type": "at", "data": {"qq": "10002"}},
            " ok",
        ],
    )
    ctx.reply_segments(
        XiamiMessage(message_type="group", sender="10003", target="20002", text="in"),
        [
            MessageSegment("reply", {"id": "88"}),
            MessageSegment("text", {"text": "收到"}),
        ],
    )
    mixed = ctx.message_from_segments(
        [
            "a[CQ:at,qq=10004]",
            {"type": "image", "data": {"file": "https://example.com/b.png"}},
            123,
        ]
    )

    expected = [
        ("10001", "hi&#91;[CQ:image,file=file:///tmp/a&#44;b.png]", "private"),
        ("20001", "[CQ:at,qq=10002] ok", "group"),
        ("20002", "[CQ:reply,id=88]收到", "group"),
    ]
    if sent != expected:
        raise RuntimeError(f"segment sends failed: {sent!r}")
    if mixed != "a[CQ:at,qq=10004][CQ:image,file=https://example.com/b.png]123":
        raise RuntimeError(f"mixed segment conversion failed: {mixed!r}")
    print("plugin context segments smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
