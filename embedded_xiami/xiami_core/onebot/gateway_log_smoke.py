from __future__ import annotations

import json
import urllib.request

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.events import EventBus
from xiami_core.onebot.gateway import OneBotEventGateway
from xiami_core.storage.paths import LOG_HOME


def main() -> int:
    log_file = LOG_HOME / "onebot_events.jsonl"
    if log_file.exists():
        log_file.unlink()
    bus = EventBus()
    seen = []
    bus.subscribe_message(seen.append)
    gateway = OneBotEventGateway(bus, port=0)
    url = gateway.start()
    try:
        payload = {
            "post_type": "message",
            "message_type": "private",
            "user_id": 10001,
            "self_id": 10000,
            "message": "log probe",
        }
        request = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), method="POST")
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=2) as response:
            if response.status != 204:
                raise RuntimeError(f"bad status: {response.status}")
    finally:
        gateway.stop()
    if not seen or seen[0].message_type != "private":
        raise RuntimeError(f"message not published: {seen}")
    if not log_file.exists():
        raise RuntimeError(f"event log not written: {log_file}")
    last = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    if last.get("parsed_type") != "private" or "log probe" not in str(last.get("raw", "")):
        raise RuntimeError(f"event log content invalid: {last}")
    print("onebot gateway log smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
