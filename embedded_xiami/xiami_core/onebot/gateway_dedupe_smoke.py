from __future__ import annotations

from xiami_core.events import EventBus
from xiami_core.onebot import gateway


def _reset_dedupe() -> None:
    with gateway._EVENT_DEDUPE_LOCK:
        gateway._RECENT_EVENT_KEYS.clear()
        gateway._RECENT_EVENT_KEY_SET.clear()


def _message_payload(message_id: int, text: str) -> dict[str, object]:
    return {
        "self_id": 3996078542,
        "post_type": "message",
        "message_type": "group",
        "group_id": 723236947,
        "group_name": "虾米AI售后群",
        "user_id": 313420054,
        "time": 1783167030,
        "message_id": message_id,
        "message_seq": message_id,
        "real_id": message_id,
        "raw_message": text,
        "message": [{"type": "text", "data": {"text": text}}],
    }


def main() -> int:
    _reset_dedupe()
    bus = EventBus()
    messages = []
    events = []
    bus.subscribe_message(messages.append)
    bus.subscribe_plugin_event(events.append)

    payload = _message_payload(10001, "开启邀请积分")
    gateway._handle_payload(bus, dict(payload), transport="ws")
    gateway._handle_payload(bus, dict(payload), transport="http")
    if len(messages) != 1 or len(events) != 1:
        raise RuntimeError(f"duplicate event was not filtered: messages={len(messages)}, events={len(events)}")

    gateway._handle_payload(bus, _message_payload(10002, "开启入群审核"), transport="ws")
    if len(messages) != 2 or len(events) != 2:
        raise RuntimeError(f"new event was filtered unexpectedly: messages={len(messages)}, events={len(events)}")

    print("onebot gateway dedupe smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
