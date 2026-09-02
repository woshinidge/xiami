from __future__ import annotations

import argparse
from pathlib import Path

from xiami_core.onebot.replay import format_replay_result, replay_onebot_events
from xiami_core.storage.paths import LOG_HOME, PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay OneBot events through Xiami plugins.")
    parser.add_argument("--events", default=str(LOG_HOME / "onebot_events.jsonl"), help="OneBot JSONL event log.")
    parser.add_argument("--plugins", default=str(PROJECT_ROOT / "xiami_plugins"), help="Plugin root directory.")
    parser.add_argument("--plugin", action="append", default=[], help="Only replay against this plugin id. Can repeat.")
    parser.add_argument("--state", default=str(LOG_HOME / "replay_state"), help="Replay state directory.")
    parser.add_argument("--limit", type=int, default=0, help="Replay only the last N events.")
    args = parser.parse_args()

    result = replay_onebot_events(
        event_path=Path(args.events),
        plugin_root=Path(args.plugins),
        state_root=Path(args.state),
        limit=args.limit,
        plugin_ids=tuple(args.plugin or ()),
    )
    print(format_replay_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
