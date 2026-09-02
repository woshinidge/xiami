from __future__ import annotations

import json
import urllib.request

from xiami_core.events import EventBus
from xiami_core.onebot.gateway import OneBotEventGateway


def main() -> int:
    bus = EventBus()
    seen = []
    bus.subscribe_message(seen.append)
    gateway = OneBotEventGateway(bus, port=0)
    url = gateway.start()
    try:
        payload = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 123,
            "self_id": 456,
            "message": [{"type": "text", "data": {"text": "/echo hi"}}],
        }
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 204:
                raise RuntimeError(f"bad status: {response.status}")
        if not seen or seen[0].sender != "123" or seen[0].text != "/echo hi":
            raise RuntimeError(f"event not parsed: {seen}")
    finally:
        gateway.stop()
    print("onebot gateway smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

