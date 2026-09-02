from __future__ import annotations

from xiami_core.plugins.command_coverage_report import build_command_coverage_report, format_command_coverage_report


def main() -> int:
    items = build_command_coverage_report()
    missing = [item.plugin_id for item in items if not item.covered]
    if missing:
        raise RuntimeError(f"plugins with commands but no smoke evidence: {missing}")
    report = format_command_coverage_report(items)
    for expected in ("onebot_tools", "compat_echo", "member_guard", "knowledge"):
        if expected not in report:
            raise RuntimeError(f"coverage report missing {expected}: {report}")
    print("plugin command coverage report smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
