from __future__ import annotations

import argparse

from xiami_core.acceptance_evidence import (
    MANUAL_EVIDENCE_FILE,
    record_manual_evidence,
    record_real_loop_confirmation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record Xiami manual real acceptance evidence.")
    parser.add_argument("--real-loop", action="store_true", help="Mark real login, OneBot, receive and send loop as verified.")
    parser.add_argument("--item", action="append", default=[], help="Acceptance item to mark as verified.")
    parser.add_argument("--detail", default="人工真实环境验证通过", help="Evidence detail.")
    parser.add_argument("--source", default="user", help="Evidence source label.")
    args = parser.parse_args()

    if args.real_loop:
        records = record_real_loop_confirmation(args.detail, source=args.source)
    else:
        records = [record_manual_evidence(name, args.detail, source=args.source) for name in args.item]
    if not records:
        parser.error("use --real-loop or at least one --item")

    print(f"manual acceptance evidence saved: {MANUAL_EVIDENCE_FILE}")
    for item in records:
        print(f"- {item.name}: {'OK' if item.ok else 'FAILED'} {item.detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
