from __future__ import annotations

import argparse

from xiami_core.high_risk_probe import dumps_high_risk_probe, format_high_risk_probe, run_high_risk_probe


def main() -> int:
    parser = argparse.ArgumentParser(description="Run controlled high-risk real scenario probes.")
    parser.add_argument("--group", default="", help="Test group id. Defaults to configured probe group.")
    parser.add_argument("--no-member-guard", action="store_true", help="Skip safe send/delete message probe.")
    parser.add_argument("--moderation-user", default="", help="User id for moderation probe.")
    parser.add_argument("--moderation-duration", type=int, default=1, help="Mute seconds, capped at 60.")
    parser.add_argument("--confirm-moderation", action="store_true", help="Allow moderation probe to mute/unmute.")
    parser.add_argument("--friend-flag", default="", help="Friend request flag from OneBot request event.")
    parser.add_argument("--friend-approve", action="store_true", help="Approve friend request; default rejects.")
    parser.add_argument("--join-flag", default="", help="Group request flag from OneBot request event.")
    parser.add_argument("--join-sub-type", default="add", choices=["add", "invite"], help="Group request subtype.")
    parser.add_argument("--join-approve", action="store_true", help="Approve group request; default rejects.")
    parser.add_argument("--confirm-review", action="store_true", help="Allow friend/group request action probes.")
    parser.add_argument("--timeout", type=float, default=3.0, help="Per-action timeout seconds.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when requested probes fail.")
    args = parser.parse_args()

    result = run_high_risk_probe(
        group_id=args.group,
        member_guard=not args.no_member_guard,
        moderation_user=args.moderation_user,
        moderation_duration=args.moderation_duration,
        confirm_moderation=args.confirm_moderation,
        friend_flag=args.friend_flag,
        friend_approve=args.friend_approve,
        join_flag=args.join_flag,
        join_sub_type=args.join_sub_type,
        join_approve=args.join_approve,
        confirm_review=args.confirm_review,
        timeout=max(0.1, args.timeout),
    )
    print(dumps_high_risk_probe(result) if args.json else format_high_risk_probe(result))
    return 1 if args.strict and not result.ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
