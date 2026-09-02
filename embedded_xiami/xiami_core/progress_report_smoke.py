from __future__ import annotations

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.progress_report import build_progress_details, format_progress_summary
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


def main() -> int:
    save_config(AppConfig(kernel=KernelConfig(kind="Mock")))
    summary, hint, failed_acceptance, acceptance_items = build_progress_details()
    if summary.plugins <= 0:
        raise RuntimeError("progress report did not see plugins")
    if summary.covered_commands != summary.mvp_commands:
        raise RuntimeError(f"progress report command coverage mismatch: {summary!r}")
    if summary.onebot_api_missing != 0:
        raise RuntimeError(f"progress report OneBot API coverage mismatch: {summary!r}")
    text = format_progress_summary(summary, hint, failed_acceptance, acceptance_items)
    if (
        "Xiami progress report" not in text
        or "MVP command coverage" not in text
        or "Product phase summary" not in text
        or "Xiami Core / 插件迁移" not in text
        or "Pending acceptance items" not in text
        or "Real acceptance gate" not in text
        or "Evidence paths" not in text
        or "Offline replay gate" not in text
        or "Fast-track status" not in text
        or "使用推荐真实内核" not in text
        or "待账号页自动准备真实内核" not in text
    ):
        raise RuntimeError(f"progress report format missing: {text}")
    print("progress report smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
