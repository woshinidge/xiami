from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from xiami_core.plugins.ai_provider import AiProviderConfig, Transport
from xiami_core.stability_evidence import StabilityEvidenceReport, build_stability_evidence_report
from xiami_core.stability_observer import StabilityObservation, run_stability_observation
from xiami_core.stability_resume import (
    StabilityResumePlan,
    build_stability_resume_plan,
    format_stability_resume_plan,
)
from xiami_core.storage.config import AppConfig


@dataclass(frozen=True)
class StabilityContinueResult:
    ok: bool
    skipped: bool
    before: StabilityResumePlan
    observation: StabilityObservation | None
    evidence: StabilityEvidenceReport
    after: StabilityResumePlan


def run_stability_continue(
    *,
    log_path: Path | str | None = None,
    duration: float = 3600.0,
    interval: float = 30.0,
    include_provider: bool = False,
    min_samples: int | None = None,
    min_duration: float | None = None,
    min_onebot_ratio: float = 0.99,
    min_provider_ratio: float = 0.95,
    config: AppConfig | None = None,
    provider_config: AiProviderConfig | None = None,
    provider_transport: Transport | None = None,
) -> StabilityContinueResult:
    before = build_stability_resume_plan(
        log_path=log_path,
        duration=duration,
        interval=interval,
        include_provider=include_provider,
        min_samples=min_samples,
        min_duration=min_duration,
        min_onebot_ratio=min_onebot_ratio,
        min_provider_ratio=min_provider_ratio,
    )
    observation: StabilityObservation | None = None
    if not before.ok:
        observation = run_stability_observation(
            duration=_suggested_continue_duration(before, interval),
            interval=interval,
            include_provider=include_provider,
            config=config,
            provider_config=provider_config,
            provider_transport=provider_transport,
            log_path=Path(log_path) if log_path else None,
        )
    evidence = build_stability_evidence_report(
        log_path=log_path,
        min_samples=before.target_samples,
        min_duration=before.target_duration,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=include_provider,
        min_provider_ratio=min_provider_ratio,
    )
    after = build_stability_resume_plan(
        log_path=log_path,
        duration=duration,
        interval=interval,
        include_provider=include_provider,
        min_samples=before.target_samples,
        min_duration=before.target_duration,
        min_onebot_ratio=min_onebot_ratio,
        min_provider_ratio=min_provider_ratio,
    )
    return StabilityContinueResult(
        ok=evidence.ok,
        skipped=before.ok,
        before=before,
        observation=observation,
        evidence=evidence,
        after=after,
    )


def format_stability_continue_result(result: StabilityContinueResult) -> str:
    lines = [
        f"长稳续跑：{'PASS' if result.ok else 'BLOCKED'}",
        f"执行：{'已跳过，证据已满足' if result.skipped else '已按剩余量继续观察'}",
        "",
        "续跑前：",
        *format_stability_resume_plan(result.before).splitlines(),
    ]
    if result.observation is not None:
        lines.extend(
            [
                "",
                "本次观察：",
                f"- samples={result.observation.total}",
                f"- onebot={result.observation.onebot_ok}/{result.observation.total}",
                f"- provider={result.observation.provider_ok}/{result.observation.provider_checked}",
                f"- log={result.observation.log_path}",
            ]
        )
    lines.extend(
        [
            "",
            "续跑后：",
            *format_stability_resume_plan(result.after).splitlines(),
        ]
    )
    return "\n".join(lines)


def stability_continue_to_dict(result: StabilityContinueResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "skipped": result.skipped,
        "before": asdict(result.before),
        "observation": asdict(result.observation) if result.observation else None,
        "evidence": asdict(result.evidence),
        "after": asdict(result.after),
    }


def dumps_stability_continue_result(result: StabilityContinueResult) -> str:
    return json.dumps(stability_continue_to_dict(result), ensure_ascii=False, indent=2)


def _suggested_continue_duration(plan: StabilityResumePlan, interval: float) -> float:
    safe_interval = max(0.1, interval)
    suggested = max(plan.remaining_duration, plan.remaining_samples * safe_interval)
    return suggested if suggested > 0 else safe_interval
