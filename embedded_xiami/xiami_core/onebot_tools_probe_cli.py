from __future__ import annotations

import argparse

from xiami_core.onebot_tools_probe import (
    dumps_onebot_tools_probe,
    format_onebot_tools_probe,
    run_onebot_tools_probe,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run safe read-only OneBot tool probes.")
    parser.add_argument("--group", default="", help="Optional group id for get_group_info.")
    parser.add_argument("--timeout", type=float, default=3.0, help="Per-action timeout seconds.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required probes fail.")
    args = parser.parse_args()

    result = run_onebot_tools_probe(group_id=args.group, timeout=max(0.1, args.timeout))
    print(dumps_onebot_tools_probe(result) if args.json else format_onebot_tools_probe(result))
    return 1 if args.strict and not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
