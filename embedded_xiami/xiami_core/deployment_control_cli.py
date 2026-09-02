from __future__ import annotations

import argparse
from pathlib import Path

from xiami_core.deployment_control import (
    build_deployment_summary,
    deployment_summary_json,
    format_deployment_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show Xiami desktop deployment/control summary.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--output", default="", help="Optional output file.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required checks fail.")
    args = parser.parse_args()
    summary = build_deployment_summary()
    text = deployment_summary_json(summary) if args.json else format_deployment_summary(summary)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text)
    return 0 if summary.ok or not args.strict else 1


if __name__ == "__main__":
    raise SystemExit(main())
