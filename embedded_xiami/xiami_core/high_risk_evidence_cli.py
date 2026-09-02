from __future__ import annotations

import argparse

from xiami_core.high_risk_evidence import (
    build_high_risk_evidence_suggestions,
    dumps_high_risk_evidence_suggestions,
    format_high_risk_evidence_suggestions,
    record_suggested_high_risk_evidence,
)
from xiami_core.high_risk_gate import build_high_risk_gate, format_high_risk_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect and record Xiami high-risk evidence candidates.")
    parser.add_argument("--limit", type=int, default=500, help="Recent log records to inspect.")
    parser.add_argument("--record-suggested", action="store_true", help="Record all strong unrecorded candidates.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when the high-risk gate is not complete.")
    args = parser.parse_args()

    suggestions = build_high_risk_evidence_suggestions(limit=max(1, args.limit))
    if args.record_suggested:
        recorded = record_suggested_high_risk_evidence(suggestions)
        suggestions = build_high_risk_evidence_suggestions(limit=max(1, args.limit))
        if not args.json:
            print(f"已记录候选：{len(recorded)}")
            print("")

    if args.json:
        print(dumps_high_risk_evidence_suggestions(suggestions))
    else:
        print(format_high_risk_evidence_suggestions(suggestions))
        print("")
        print(format_high_risk_gate(build_high_risk_gate()))
    return 1 if args.strict and not suggestions.gate.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
