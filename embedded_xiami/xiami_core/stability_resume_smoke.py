from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.stability_observer import STABILITY_LOG_FILE, StabilitySample
from xiami_core.stability_resume import build_stability_resume_plan, format_stability_resume_plan


def main() -> int:
    STABILITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        StabilitySample(
            timestamp=(start + timedelta(seconds=offset)).isoformat(),
            onebot_ok=True,
            onebot_detail="online=True, good=True",
            provider_checked=False,
            provider_ok=False,
            provider_detail="",
        )
        for offset in (0, 30)
    ]
    STABILITY_LOG_FILE.write_text(
        "\n".join(json.dumps(asdict(sample), ensure_ascii=False) for sample in samples),
        encoding="utf-8",
    )

    plan = build_stability_resume_plan(duration=90, interval=30, min_onebot_ratio=1.0)
    if plan.ok:
        raise RuntimeError("expected partial stability plan to continue")
    if plan.current_samples != 2 or plan.target_samples != 4 or plan.remaining_samples != 2:
        raise RuntimeError(f"unexpected sample progress: {plan}")
    if "--duration 60" not in plan.observer_command:
        raise RuntimeError(f"unexpected observer command: {plan.observer_command}")
    text = format_stability_resume_plan(plan)
    if "长稳恢复计划：继续" not in text or "继续观察" not in text:
        raise RuntimeError(text)

    complete_samples = [
        StabilitySample(
            timestamp=(start + timedelta(seconds=offset)).isoformat(),
            onebot_ok=True,
            onebot_detail="online=True, good=True",
            provider_checked=True,
            provider_ok=True,
            provider_detail="provider ok",
        )
        for offset in (0, 30, 60, 90)
    ]
    STABILITY_LOG_FILE.write_text(
        "\n".join(json.dumps(asdict(sample), ensure_ascii=False) for sample in complete_samples),
        encoding="utf-8",
    )
    complete = build_stability_resume_plan(
        duration=90,
        interval=30,
        include_provider=True,
        min_onebot_ratio=1.0,
        min_provider_ratio=1.0,
    )
    if not complete.ok:
        raise RuntimeError(format_stability_resume_plan(complete))

    print("stability resume smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
