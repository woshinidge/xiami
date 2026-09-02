from __future__ import annotations

import argparse

from xiami_core.stability_continue import (
    dumps_stability_continue_result,
    format_stability_continue_result,
    run_stability_continue,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Continue Xiami stability observation from existing evidence.")
    parser.add_argument("--log-path", default=None)
    parser.add_argument("--duration", type=float, default=3600.0)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--provider", action="store_true")
    parser.add_argument("--min-samples", type=int, default=None)
    parser.add_argument("--min-duration", type=float, default=None)
    parser.add_argument("--onebot-ratio", type=float, default=0.99)
    parser.add_argument("--provider-ratio", type=float, default=0.95)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    result = run_stability_continue(
        log_path=args.log_path,
        duration=args.duration,
        interval=args.interval,
        include_provider=args.provider,
        min_samples=args.min_samples,
        min_duration=args.min_duration,
        min_onebot_ratio=args.onebot_ratio,
        min_provider_ratio=args.provider_ratio,
    )
    print(dumps_stability_continue_result(result) if args.json else format_stability_continue_result(result))
    return 1 if args.strict and not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
