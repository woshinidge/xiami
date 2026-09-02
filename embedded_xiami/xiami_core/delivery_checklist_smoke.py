from __future__ import annotations

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.delivery_checklist import build_delivery_checklist, format_delivery_checklist
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


def main() -> int:
    save_config(AppConfig(kernel=KernelConfig(kind="Mock")))
    checklist = build_delivery_checklist(duration=60, interval=30, include_provider=False)
    rendered = format_delivery_checklist(checklist)
    required = [
        "Xiami 交付清单",
        "真实登录与收发闭环",
        "高风险真实场景证据",
        "长稳观察证据",
        "xiami_core.high_risk_evidence_cli",
        "xiami_acceptance.ps1 -Mode real -ProductGate",
    ]
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError(f"delivery checklist smoke missing {missing}: {rendered}")
    print("delivery checklist smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
