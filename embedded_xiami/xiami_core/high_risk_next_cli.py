from __future__ import annotations

import argparse

from xiami_core.high_risk_next import (
    build_high_risk_next_plan,
    dumps_high_risk_next_plan,
    format_high_risk_next_plan,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show next Xiami high-risk real verification step.")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    plan = build_high_risk_next_plan()
    print(dumps_high_risk_next_plan(plan) if args.json else format_high_risk_next_plan(plan))
    return 1 if args.strict and not plan.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
