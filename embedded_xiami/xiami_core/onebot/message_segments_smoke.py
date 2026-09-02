from __future__ import annotations

from xiami_core.models import MessageSegment
from xiami_core.onebot.message_segments import (
    cq_at,
    cq_image,
    cq_reply,
    cq_text,
    parse_cq_message,
    parse_onebot_segments,
    segments_to_cq,
    segments_to_text,
)


def main() -> int:
    cq = "hello[CQ:at,qq=10001] [CQ:image,file=file:///tmp/a.png][CQ:reply,id=456]"
    segments = parse_cq_message(cq)
    if [segment.type for segment in segments] != ["text", "at", "text", "image", "reply"]:
        raise RuntimeError(f"wrong cq segment types: {segments!r}")
    if segments_to_text(segments) != "hello@10001 [图片][回复]":
        raise RuntimeError(f"wrong segment text: {segments_to_text(segments)!r}")

    array_segments = parse_onebot_segments(
        [
            {"type": "text", "data": {"text": "hi "}},
            {"type": "image", "data": {"file": "abc.png"}},
        ]
    )
    if segments_to_text(array_segments) != "hi [图片]":
        raise RuntimeError(f"wrong array segment text: {array_segments!r}")

    escaped = cq_text("a[b],c&d") + cq_at(10001) + cq_image("file:///tmp/a,b.png") + cq_reply(123)
    if escaped != "a&#91;b&#93;,c&amp;d[CQ:at,qq=10001][CQ:image,file=file:///tmp/a&#44;b.png][CQ:reply,id=123]":
        raise RuntimeError(f"wrong escaped cq: {escaped}")

    rebuilt = segments_to_cq((MessageSegment("text", {"text": "hi"}), MessageSegment("at", {"qq": "10001"})))
    if rebuilt != "hi[CQ:at,qq=10001]":
        raise RuntimeError(f"wrong rebuilt cq: {rebuilt}")

    print("message segments smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
