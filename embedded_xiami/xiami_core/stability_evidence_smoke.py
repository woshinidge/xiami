from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.stability_observer import STABILITY_LOG_FILE, StabilitySample
from xiami_core.stability_evidence import (
    build_stability_evidence_report,
    format_stability_evidence_report,
    load_stability_samples,
)


def main() -> int:
    STABILITY_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    samples = [
        StabilitySample(
            timestamp=(start + timedelta(seconds=offset)).isoformat(),
            onebot_ok=True,
            onebot_detail="online=True, good=True",
            provider_checked=True,
            provider_ok=True,
            provider_detail="openai/test：ok",
        )
        for offset in (0, 60, 120)
    ]
    STABILITY_LOG_FILE.write_text(
        "\n".join(json.dumps(asdict(sample), ensure_ascii=False) for sample in samples),
        encoding="utf-8",
    )

    loaded = load_stability_samples()
    if len(loaded) != 3:
        raise RuntimeError(f"expected 3 loaded samples, got {len(loaded)}")

    report = build_stability_evidence_report(
        min_samples=3,
        min_duration=120,
        min_onebot_ratio=1.0,
        require_provider=True,
        min_provider_ratio=1.0,
    )
    if not report.ok:
        raise RuntimeError(format_stability_evidence_report(report))

    blocked = build_stability_evidence_report(min_samples=4, min_duration=120)
    if blocked.ok:
        raise RuntimeError("expected report to block when min sample count is not met")

    text = format_stability_evidence_report(report)
    if "长稳证据：PASS" not in text or "Provider：3/3" not in text:
        raise RuntimeError(text)
    print("stability evidence smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
