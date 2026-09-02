from __future__ import annotations

import argparse

from xiami_core.production_gate import dumps_production_gate, format_production_gate, run_production_gate


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Xiami product delivery gate.")
    parser.add_argument("--duration", type=float, default=3600.0)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--provider", action="store_true")
    parser.add_argument("--run-stability", action="store_true", help="Run stability observation when real gate is ready.")
    parser.add_argument("--export-bundle", action="store_true", help="Export evidence bundle after gate checks.")
    parser.add_argument("--min-samples", type=int, default=None)
    parser.add_argument("--min-duration", type=float, default=None)
    parser.add_argument("--onebot-ratio", type=float, default=0.99)
    parser.add_argument("--provider-ratio", type=float, default=0.95)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless product gate passes.")
    args = parser.parse_args()

    result = run_production_gate(
        duration=args.duration,
        interval=args.interval,
        include_provider=args.provider,
        run_stability=args.run_stability,
        export_bundle=args.export_bundle,
        min_samples=args.min_samples,
        min_duration=args.min_duration,
        min_onebot_ratio=args.onebot_ratio,
        min_provider_ratio=args.provider_ratio,
    )
    print(dumps_production_gate(result) if args.json else format_production_gate(result))
    return 1 if args.strict and not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
