from __future__ import annotations

import argparse

from xiami_core.stability_resume import build_stability_resume_plan, format_stability_resume_plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Show resumable Xiami long-run stability plan.")
    parser.add_argument("--log-path", default=None)
    parser.add_argument("--duration", type=float, default=3600.0)
    parser.add_argument("--interval", type=float, default=30.0)
    parser.add_argument("--provider", action="store_true")
    parser.add_argument("--min-samples", type=int, default=None)
    parser.add_argument("--min-duration", type=float, default=None)
    parser.add_argument("--onebot-ratio", type=float, default=0.99)
    parser.add_argument("--provider-ratio", type=float, default=0.95)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    plan = build_stability_resume_plan(
        log_path=args.log_path,
        duration=args.duration,
        interval=args.interval,
        include_provider=args.provider,
        min_samples=args.min_samples,
        min_duration=args.min_duration,
        min_onebot_ratio=args.onebot_ratio,
        min_provider_ratio=args.provider_ratio,
    )
    print(format_stability_resume_plan(plan))
    return 1 if args.strict and not plan.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
