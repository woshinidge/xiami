from __future__ import annotations

import argparse
from pathlib import Path

from xiami_core.real_acceptance_gate import (
    dumps_real_acceptance_gate,
    format_real_acceptance_gate,
    run_real_acceptance_gate,
)
from xiami_core.storage.paths import PROJECT_ROOT


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Xiami real QQ acceptance gate.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--ready-only",
        action="store_true",
        help="Only require kernel/login readiness; skip online/message/send/migration requirements.",
    )
    parser.add_argument("--no-messages", action="store_true", help="Do not require private/group receive and UI history checks.")
    parser.add_argument("--no-sends", action="store_true", help="Do not require private/group send checks.")
    parser.add_argument("--no-migration", action="store_true", help="Do not require migration verification.")
    args = parser.parse_args()

    gate = run_real_acceptance_gate(
        project_root=args.project_root,
        require_online=not args.ready_only,
        require_messages=not args.ready_only and not args.no_messages,
        require_sends=not args.ready_only and not args.no_sends,
        require_migration=not args.ready_only and not args.no_migration,
    )
    rendered = dumps_real_acceptance_gate(gate) if args.format == "json" else format_real_acceptance_gate(gate)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if gate.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
