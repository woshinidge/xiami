from __future__ import annotations

import json
import sys
from collections import deque

from xiami_core.storage.paths import LOG_HOME


def read_recent_event_summaries(limit: int = 20) -> list[str]:
    path = LOG_HOME / "onebot_events.jsonl"
    if not path.exists():
        return [f"no event log: {path}"]
    lines: deque[str] = deque(maxlen=limit)
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                lines.append(line.strip())
    result: list[str] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            result.append(line)
            continue
        raw = entry.get("raw", "")
        result.append(
            "{time} post={post_type} type={parsed_type} sender={parsed_sender} "
            "target={parsed_target} text={parsed_text}".format(**entry)
        )
        if raw and not entry.get("parsed"):
            result.append(f"  raw={raw}")
    return result


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    limit = int(argv[0]) if argv else 20
    for line in read_recent_event_summaries(limit):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
