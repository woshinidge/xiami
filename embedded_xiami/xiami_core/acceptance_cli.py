from __future__ import annotations

from xiami_core.acceptance import format_acceptance, run_v1_acceptance


def main() -> int:
    items = run_v1_acceptance()
    print(format_acceptance(items))
    return 0 if all(item.ok for item in items) else 1


if __name__ == "__main__":
    raise SystemExit(main())

