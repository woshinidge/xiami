from __future__ import annotations

import json

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.high_risk_gate import (
    build_high_risk_gate,
    dumps_high_risk_gate,
    format_high_risk_gate,
    record_high_risk_scenario,
    scenario_names,
)


def main() -> int:
    empty = build_high_risk_gate()
    if empty.ok or empty.required_passed != 0:
        raise RuntimeError(f"empty high-risk gate should block: {empty}")
    text = format_high_risk_gate(empty)
    if "高风险真实场景 Gate：BLOCKED" not in text or "friend_review_real" not in text:
        raise RuntimeError(text)

    first = record_high_risk_scenario("friend_review_real", "好友审核真实通过", source="smoke")
    if first.name != "friend_review_real":
        raise RuntimeError(first)
    partial = build_high_risk_gate()
    if partial.ok or partial.required_passed != 1:
        raise RuntimeError(f"partial high-risk gate mismatch: {partial}")

    for name in scenario_names():
        record_high_risk_scenario(name, f"{name} verified", source="smoke")
    complete = build_high_risk_gate()
    if not complete.ok or complete.required_passed != complete.required_total:
        raise RuntimeError(format_high_risk_gate(complete))
    payload = json.loads(dumps_high_risk_gate(complete))
    if not payload["ok"] or len(payload["checks"]) != len(scenario_names()):
        raise RuntimeError(f"invalid high-risk gate json: {payload}")

    print("high-risk gate smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
