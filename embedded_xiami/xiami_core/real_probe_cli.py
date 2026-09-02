from __future__ import annotations

import argparse
from pathlib import Path

from xiami_core.progress_report import build_progress_details, format_progress_summary
from xiami_core.real_probe import format_probe, run_real_login_probe
from xiami_core.runtime_diagnostic import apply_suggested_kernel_config
from xiami_core.send_probe import format_send_probe, run_send_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Xiami real QQ login probe.")
    parser.add_argument("--account", default="", help="QQ account hint passed login kernel.")
    parser.add_argument("--start", action="store_true", help="Start configured login kernel before probing.")
    parser.add_argument("--apply", action="store_true", help="Apply suggested real NapCat/Lagrange kernel config before probing.")
    parser.add_argument("--send", action="store_true", help="Run configured private/group send probe after login probe.")
    parser.add_argument("--progress", action="store_true", help="Print Xiami progress report after probing.")
    parser.add_argument("--fast", action="store_true", help="Apply suggested kernel, start login, run send probe, and print progress.")
    parser.add_argument("--timeout", type=int, default=45, help="Probe timeout in seconds.")
    args = parser.parse_args()

    start = args.start or args.fast
    if args.apply or args.fast:
        result = apply_suggested_kernel_config()
        print("== suggested kernel ==")
        print(result.detail)
        print()

    items = run_real_login_probe(account=args.account, start=start, timeout=args.timeout)
    online = any(item.name == "onebot_login_info" and item.ok for item in items)
    print(format_probe(items))

    if args.send or args.fast:
        print()
        print("== send probe ==")
        print(format_send_probe(run_send_probe()))

    if args.progress or args.fast:
        print()
        print("== progress ==")
        summary, acceptance_hint, failed_acceptance, acceptance_items = build_progress_details(Path.cwd())
        print(format_progress_summary(summary, acceptance_hint, failed_acceptance, acceptance_items))

    required = [item for item in items if item.name in {"real_kernel_selected", "kernel_executable", "onebot_http"}]
    return 0 if online and all(item.ok for item in required) else 1


if __name__ == "__main__":
    raise SystemExit(main())
