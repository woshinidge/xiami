from __future__ import annotations

from xiami_core.recovery_plan import build_recovery_plan, format_recovery_plan


def main() -> int:
    print(format_recovery_plan(build_recovery_plan()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
