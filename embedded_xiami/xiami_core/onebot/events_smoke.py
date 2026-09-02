from __future__ import annotations

from xiami_core.onebot.events import parse_onebot_event


def main() -> int:
    private = parse_onebot_event(
        {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "self_id": 313420054,
            "message": [{"type": "text", "data": {"text": "hello"}}],
        }
    )
    if not private or private.message_type != "private" or private.sender != "10001" or private.text != "hello":
        raise RuntimeError(f"private event parse failed: {private}")
    if private.self_id != "313420054":
        raise RuntimeError(f"private self_id parse failed: {private}")
    if private.raw_message or [segment.type for segment in private.segments] != ["text"]:
        raise RuntimeError(f"private segments parse failed: {private}")

    private_sender_object = parse_onebot_event(
        {
            "post_type": "message",
            "detail_type": "private",
            "sender": {"user_id": 10002},
            "self_id": 313420054,
            "target_id": 313420054,
            "raw_message": "raw hello",
        }
    )
    if (
        not private_sender_object
        or private_sender_object.message_type != "private"
        or private_sender_object.sender != "10002"
        or private_sender_object.self_id != "313420054"
        or private_sender_object.text != "raw hello"
    ):
        raise RuntimeError(f"private sender object parse failed: {private_sender_object}")
    if private_sender_object.raw_message != "raw hello" or private_sender_object.segments[0].data.get("text") != "raw hello":
        raise RuntimeError(f"private raw message parse failed: {private_sender_object}")

    group = parse_onebot_event(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 20001,
            "user_id": 10003,
            "self_id": 313420054,
            "message": "/echo group",
        }
    )
    if not group or group.message_type != "group" or group.target != "20001" or group.sender != "10003" or group.self_id != "313420054":
        raise RuntimeError(f"group event parse failed: {group}")
    group_with_media = parse_onebot_event(
        {
            "post_type": "message",
            "message_type": "group",
            "group_id": 20001,
            "user_id": 10003,
            "self_id": 313420054,
            "raw_message": "hello[CQ:at,qq=10001][CQ:image,file=abc.png]",
        }
    )
    if not group_with_media or group_with_media.text != "hello@10001[图片]":
        raise RuntimeError(f"group media text parse failed: {group_with_media}")
    if [segment.type for segment in group_with_media.segments] != ["text", "at", "image"]:
        raise RuntimeError(f"group media segments parse failed: {group_with_media}")
    print("onebot events smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
