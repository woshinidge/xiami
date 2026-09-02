from __future__ import annotations

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.high_risk_next import build_high_risk_next_plan, format_high_risk_next_plan


def main() -> int:
    plan = build_high_risk_next_plan()
    rendered = format_high_risk_next_plan(plan)
    required = [
        "高风险验证向导",
        "好友审核真实验证",
        "python -m xiami_core.high_risk_gate_cli --record friend_review_real",
        "批量记录命令",
    ]
    missing = [item for item in required if item not in rendered]
    if missing:
        raise RuntimeError(f"high-risk next smoke missing {missing}: {rendered}")
    print("high-risk next smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
