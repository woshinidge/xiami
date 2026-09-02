from __future__ import annotations

import argparse
from pathlib import Path

from xiami_core.plugins.real_scene_acceptance import (
    Priority,
    format_real_scene_cases_json,
    format_real_scene_cases_markdown,
    real_scene_cases_by_priority,
    real_scene_summary,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Xiami real-scene acceptance checklist.")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--priority", choices=("all", "P0", "P1", "P2"), default="all")
    parser.add_argument("--output", help="optional output file")
    args = parser.parse_args()

    priority: Priority | None = None if args.priority == "all" else args.priority
    cases = real_scene_cases_by_priority(priority)
    rendered = (
        format_real_scene_cases_json(cases)
        if args.format == "json"
        else format_real_scene_cases_markdown(cases)
    )

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    summary = real_scene_summary(cases)
    missing = summary["missing_plugins"]
    if priority is None and missing:
        print("Missing formal plugin coverage: " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
