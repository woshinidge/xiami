from __future__ import annotations

import argparse

from xiami_core.stability_observer import format_stability_observation, run_stability_observation


def main() -> int:
    parser = argparse.ArgumentParser(description="Observe Xiami real OneBot/provider stability and write JSONL evidence.")
    parser.add_argument("--duration", type=float, default=60.0, help="Observation duration in seconds.")
    parser.add_argument("--interval", type=float, default=5.0, help="Sampling interval in seconds.")
    parser.add_argument("--provider", action="store_true", help="Also probe the configured ai_reply provider.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any checked sample fails.")
    args = parser.parse_args()
    result = run_stability_observation(
        duration=args.duration,
        interval=args.interval,
        include_provider=args.provider,
    )
    print(format_stability_observation(result))
    if args.strict:
        onebot_failed = result.onebot_ok != result.total
        provider_failed = result.provider_checked and result.provider_ok != result.provider_checked
        if onebot_failed or provider_failed:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
