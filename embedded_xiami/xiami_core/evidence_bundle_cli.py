from __future__ import annotations

import argparse

from xiami_core.evidence_bundle import (
    build_evidence_bundle,
    evidence_bundle_json,
    format_evidence_bundle_result,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Xiami delivery evidence bundle.")
    parser.add_argument("--output-dir", default=None, help="Optional target evidence directory.")
    parser.add_argument("--no-zip", action="store_true", help="Do not create zip archive.")
    parser.add_argument("--no-progress", action="store_true", help="Skip progress_report.md generation.")
    parser.add_argument("--min-samples", type=int, default=120)
    parser.add_argument("--min-duration", type=float, default=3600.0)
    parser.add_argument("--onebot-ratio", type=float, default=0.99)
    parser.add_argument("--provider", action="store_true")
    parser.add_argument("--provider-ratio", type=float, default=0.95)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if stability evidence is blocked.")
    args = parser.parse_args()

    result = build_evidence_bundle(
        output_dir=args.output_dir,
        include_zip=not args.no_zip,
        include_progress=not args.no_progress,
        min_samples=args.min_samples,
        min_duration=args.min_duration,
        min_onebot_ratio=args.onebot_ratio,
        require_provider=args.provider,
        min_provider_ratio=args.provider_ratio,
    )
    print(evidence_bundle_json(result) if args.json else format_evidence_bundle_result(result))
    return 1 if args.strict and not result.evidence_ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
