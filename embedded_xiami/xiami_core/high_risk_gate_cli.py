from __future__ import annotations

import argparse

from xiami_core.high_risk_gate import (
    build_high_risk_gate,
    dumps_high_risk_gate,
    format_high_risk_gate,
    record_high_risk_scenario,
    scenario_names,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify or record Xiami high-risk real scenario evidence.")
    parser.add_argument("--record", action="append", choices=scenario_names(), default=[], help="Record scenario evidence.")
    parser.add_argument("--record-all", action="store_true", help="Record all high-risk scenarios with the same detail.")
    parser.add_argument("--detail", default="真实环境验证通过")
    parser.add_argument("--source", default="user")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    targets = list(args.record)
    if args.record_all:
        targets = list(scenario_names())
    for name in targets:
        record_high_risk_scenario(name, args.detail, source=args.source)

    gate = build_high_risk_gate()
    print(dumps_high_risk_gate(gate) if args.json else format_high_risk_gate(gate))
    return 1 if args.strict and not gate.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
