from __future__ import annotations

import argparse

from xiami_core.stability_readiness import build_stability_readiness, format_stability_readiness


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight Xiami long-run stability observation and evidence.")
    parser.add_argument("--min-samples", type=int, default=120)
    parser.add_argument("--min-duration", type=float, default=3600.0)
    parser.add_argument("--onebot-ratio", type=float, default=0.99)
    parser.add_argument("--provider", action="store_true", default=True)
    parser.add_argument("--no-provider", action="store_false", dest="provider")
    parser.add_argument("--provider-ratio", type=float, default=0.95)
    args = parser.parse_args()
    report = build_stability_readiness(
        min_samples=args.min_samples,
        min_duration=args.min_duration,
        min_onebot_ratio=args.onebot_ratio,
        require_provider=args.provider,
        min_provider_ratio=args.provider_ratio,
    )
    print(format_stability_readiness(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
