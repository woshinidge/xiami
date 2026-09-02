from __future__ import annotations

from xiami_core.onebot.receive_diagnostic import format_receive_diagnostic, run_receive_diagnostic


def main() -> int:
    print(format_receive_diagnostic(run_receive_diagnostic()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
