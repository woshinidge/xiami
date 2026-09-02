from __future__ import annotations

import argparse

from xiami_core.stability_suite import format_stability_suite_result, run_stability_suite


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Xiami stability readiness, observation and evidence as one suite.")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--interval", type=float, default=5.0)
    parser.add_argument("--provider", action="store_true")
    parser.add_argument("--min-samples", type=int, default=None)
    parser.add_argument("--min-duration", type=float, default=None)
    parser.add_argument("--onebot-ratio", type=float, default=1.0)
    parser.add_argument("--provider-ratio", type=float, default=1.0)
    args = parser.parse_args()
    result = run_stability_suite(
        duration=args.duration,
        interval=args.interval,
        include_provider=args.provider,
        min_samples=args.min_samples,
        min_duration=args.min_duration,
        min_onebot_ratio=args.onebot_ratio,
        min_provider_ratio=args.provider_ratio,
    )
    print(format_stability_suite_result(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
