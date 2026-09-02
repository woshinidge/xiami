from __future__ import annotations

import argparse
from pathlib import Path

from xiami_core.onebot.replay_gate import format_replay_gate_result, run_replay_gate
from xiami_core.storage.paths import LOG_HOME, PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay OneBot events and assert Xiami migration gates.")
    parser.add_argument("--events", default=str(LOG_HOME / "onebot_events.jsonl"), help="OneBot JSONL event log.")
    parser.add_argument("--plugins", default=str(PROJECT_ROOT / "xiami_plugins"), help="Plugin root directory.")
    parser.add_argument("--state", default=str(LOG_HOME / "replay_gate_state"), help="Replay state directory.")
    parser.add_argument("--plugin", action="append", default=[], help="Only replay against plugin id. Repeatable.")
    parser.add_argument("--limit", type=int, default=0, help="Replay only last N events.")
    parser.add_argument("--min-events", type=int, default=1, help="Minimum replayed events.")
    parser.add_argument("--min-sends", type=int, default=0, help="Minimum captured send calls.")
    parser.add_argument("--min-actions", type=int, default=0, help="Minimum captured OneBot action calls.")
    parser.add_argument("--require-private", action="store_true", help="Require at least one private message event.")
    parser.add_argument("--require-group", action="store_true", help="Require at least one group message event.")
    parser.add_argument("--require-notice", action="store_true", help="Require at least one notice event.")
    parser.add_argument("--require-request", action="store_true", help="Require at least one request event.")
    parser.add_argument(
        "--require-action",
        action="append",
        default=[],
        help="Require a captured OneBot action name. Repeatable.",
    )
    args = parser.parse_args()
    result = run_replay_gate(
        event_path=Path(args.events),
        plugin_root=Path(args.plugins),
        state_root=Path(args.state),
        limit=args.limit,
        plugin_ids=tuple(args.plugin or ()),
        min_events=args.min_events,
        min_sends=args.min_sends,
        min_actions=args.min_actions,
        require_private_message=args.require_private,
        require_group_message=args.require_group,
        require_notice=args.require_notice,
        require_request=args.require_request,
        require_actions=tuple(args.require_action or ()),
    )
    print(format_replay_gate_result(result))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
