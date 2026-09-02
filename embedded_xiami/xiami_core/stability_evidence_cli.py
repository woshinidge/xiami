from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from xiami_core.stability_evidence import (
    build_stability_evidence_report,
    format_stability_evidence_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a Xiami long-run stability evidence report.")
    parser.add_argument("--log-path", default=None)
    parser.add_argument("--min-samples", type=int, default=2)
    parser.add_argument("--min-duration", type=float, default=60.0)
    parser.add_argument("--onebot-ratio", type=float, default=1.0)
    parser.add_argument("--provider", action="store_true")
    parser.add_argument("--provider-ratio", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    report = build_stability_evidence_report(
        log_path=args.log_path,
        min_samples=args.min_samples,
        min_duration=args.min_duration,
        min_onebot_ratio=args.onebot_ratio,
        require_provider=args.provider,
        min_provider_ratio=args.provider_ratio,
    )
    if args.json:
        print(json.dumps(asdict(report), ensure_ascii=False, indent=2))
    else:
        print(format_stability_evidence_report(report))
    return 1 if args.strict and not report.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
