from __future__ import annotations

import json
import urllib.request

from xiami_core.events import EventBus
from xiami_core.onebot.gateway import OneBotEventGateway


def main() -> int:
    bus = EventBus()
    messages = []
    events = []
    bus.subscribe_message(messages.append)
    bus.subscribe_plugin_event(events.append)
    gateway = OneBotEventGateway(bus, port=0)
    url = gateway.start()
    try:
        payload = {
            "post_type": "message",
            "message_type": "group",
            "group_id": 20001,
            "user_id": 10001,
            "message_id": 42,
            "message": [
                {"type": "text", "data": {"text": "raw hello"}},
                {"type": "image", "data": {"file": "abc.png"}},
            ],
        }
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 204:
                raise RuntimeError(f"bad status: {response.status}")
        if not messages or messages[0].target != "20001" or messages[0].text != "raw hello[图片]":
            raise RuntimeError(f"message event missing: {messages}")
        if not events or events[0].raw.get("message_id") != 42 or events[0].group_id != "20001":
            raise RuntimeError(f"plugin event missing: {events}")
        if events[0].text != "raw hello[图片]" or [segment.type for segment in events[0].segments] != ["text", "image"]:
            raise RuntimeError(f"plugin event segments missing: {events}")
    finally:
        gateway.stop()
    print("onebot gateway plugin event smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
