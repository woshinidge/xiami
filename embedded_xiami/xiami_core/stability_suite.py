from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from xiami_core.models import AccountStatus
from xiami_core.plugins.ai_provider import AiProviderConfig, Transport
from xiami_core.runtime_diagnostic import RuntimeDiagnostic, build_runtime_diagnostic
from xiami_core.stability_evidence import StabilityEvidenceReport, build_stability_evidence_report
from xiami_core.stability_observer import StabilityObservation, run_stability_observation
from xiami_core.stability_readiness import (
    StabilityReadinessReport,
    build_stability_readiness,
    format_stability_readiness,
)
from xiami_core.storage.config import AppConfig


@dataclass(frozen=True)
class StabilitySuiteResult:
    phase: str
    readiness_before: StabilityReadinessReport
    observation: StabilityObservation | None
    evidence_after: StabilityEvidenceReport
    readiness_after: StabilityReadinessReport


def run_stability_suite(
    *,
    duration: float = 60.0,
    interval: float = 5.0,
    include_provider: bool = False,
    config: AppConfig | None = None,
    status: AccountStatus | None = None,
    diagnostic: RuntimeDiagnostic | None = None,
    provider_config: AiProviderConfig | None = None,
    provider_transport: Transport | None = None,
    log_path: Path | None = None,
    min_samples: int | None = None,
    min_duration: float | None = None,
    min_onebot_ratio: float = 1.0,
    min_provider_ratio: float = 1.0,
) -> StabilitySuiteResult:
    sample_target = min_samples or max(1, int(math.ceil(max(0.0, duration) / max(0.1, interval))))
    duration_target = duration if min_duration is None else min_duration
    diag = diagnostic or build_runtime_diagnostic(config)
    existing_evidence = build_stability_evidence_report(
        log_path=log_path,
        min_samples=sample_target,
        min_duration=duration_target,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=include_provider,
        min_provider_ratio=min_provider_ratio,
    )
    readiness_before = build_stability_readiness(
        status=status,
        diagnostic=diag,
        evidence=existing_evidence,
        min_samples=sample_target,
        min_duration=duration_target,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=include_provider,
        min_provider_ratio=min_provider_ratio,
    )
    if readiness_before.evidence_ok:
        return StabilitySuiteResult(
            phase="evidence_passed",
            readiness_before=readiness_before,
            observation=None,
            evidence_after=existing_evidence,
            readiness_after=readiness_before,
        )
    if not readiness_before.ready_for_observation:
        return StabilitySuiteResult(
            phase="blocked",
            readiness_before=readiness_before,
            observation=None,
            evidence_after=existing_evidence,
            readiness_after=readiness_before,
        )

    observation = run_stability_observation(
        duration=duration,
        interval=interval,
        include_provider=include_provider,
        config=config,
        provider_config=provider_config,
        provider_transport=provider_transport,
        log_path=log_path,
    )
    evidence_after = build_stability_evidence_report(
        log_path=log_path,
        min_samples=sample_target,
        min_duration=duration_target,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=include_provider,
        min_provider_ratio=min_provider_ratio,
    )
    readiness_after = build_stability_readiness(
        status=status,
        diagnostic=diag,
        evidence=evidence_after,
        min_samples=sample_target,
        min_duration=duration_target,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=include_provider,
        min_provider_ratio=min_provider_ratio,
    )
    return StabilitySuiteResult(
        phase="evidence_passed" if evidence_after.ok else "observation_finished",
        readiness_before=readiness_before,
        observation=observation,
        evidence_after=evidence_after,
        readiness_after=readiness_after,
    )


def format_stability_suite_result(result: StabilitySuiteResult) -> str:
    title = {
        "evidence_passed": "证据已通过",
        "blocked": "预检阻塞",
        "observation_finished": "观察完成",
    }.get(result.phase, result.phase)
    lines = [
        f"长稳套件：{title}",
        "",
        "预检：",
        format_stability_readiness(result.readiness_before),
        "",
    ]
    if result.observation:
        lines.extend(
            [
                "观察：",
                f"- 样本：{result.observation.total}",
                f"- OneBot：{result.observation.onebot_ok}/{result.observation.total}",
                f"- Provider：{result.observation.provider_ok}/{result.observation.provider_checked}",
                f"- 证据日志：{result.observation.log_path}",
                "",
            ]
        )
    lines.extend(
        [
            "证据：",
            f"- {'PASS' if result.evidence_after.ok else 'BLOCKED'}",
            f"- 样本：{result.evidence_after.sample_count}",
            f"- 持续：{result.evidence_after.duration_seconds:.1f}s",
            f"- OneBot：{result.evidence_after.onebot_ok}/{result.evidence_after.sample_count}",
            f"- Provider：{result.evidence_after.provider_ok}/{result.evidence_after.provider_checked}",
        ]
    )
    return "\n".join(lines)
