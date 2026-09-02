from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from xiami_core.stability_evidence import StabilityEvidenceReport, build_stability_evidence_report
from xiami_core.stability_observer import STABILITY_LOG_FILE


@dataclass(frozen=True)
class StabilityResumePlan:
    ok: bool
    log_path: str
    target_samples: int
    current_samples: int
    remaining_samples: int
    target_duration: float
    current_duration: float
    remaining_duration: float
    onebot_ratio: float
    provider_ratio: float
    evidence: StabilityEvidenceReport
    observer_command: str
    evidence_command: str


def build_stability_resume_plan(
    *,
    log_path: Path | str | None = None,
    duration: float = 3600.0,
    interval: float = 30.0,
    include_provider: bool = False,
    min_samples: int | None = None,
    min_duration: float | None = None,
    min_onebot_ratio: float = 0.99,
    min_provider_ratio: float = 0.95,
) -> StabilityResumePlan:
    target_log = Path(log_path) if log_path else STABILITY_LOG_FILE
    safe_interval = max(0.1, interval)
    target_samples = min_samples if min_samples is not None else max(2, int(math.ceil(duration / safe_interval)) + 1)
    target_duration = min_duration if min_duration is not None else duration
    evidence = build_stability_evidence_report(
        log_path=target_log,
        min_samples=target_samples,
        min_duration=target_duration,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=include_provider,
        min_provider_ratio=min_provider_ratio,
    )
    remaining_samples = max(0, target_samples - evidence.sample_count)
    remaining_duration = max(0.0, target_duration - evidence.duration_seconds)
    suggested_duration = max(remaining_duration, remaining_samples * safe_interval)
    if suggested_duration <= 0 and not evidence.ok:
        suggested_duration = safe_interval

    provider = " --provider" if include_provider else ""
    observer_command = (
        "python -m xiami_core.stability_observer_cli "
        f"--duration {suggested_duration:g} --interval {safe_interval:g}{provider}"
    )
    evidence_command = (
        "python -m xiami_core.stability_evidence_cli "
        f"--min-samples {target_samples} --min-duration {target_duration:g} "
        f"--onebot-ratio {min_onebot_ratio:g}{provider}"
    )
    if include_provider:
        evidence_command += f" --provider-ratio {min_provider_ratio:g}"

    return StabilityResumePlan(
        ok=evidence.ok,
        log_path=str(target_log),
        target_samples=target_samples,
        current_samples=evidence.sample_count,
        remaining_samples=remaining_samples,
        target_duration=target_duration,
        current_duration=evidence.duration_seconds,
        remaining_duration=remaining_duration,
        onebot_ratio=evidence.onebot_ratio,
        provider_ratio=evidence.provider_ratio,
        evidence=evidence,
        observer_command=observer_command,
        evidence_command=evidence_command,
    )


def format_stability_resume_plan(plan: StabilityResumePlan) -> str:
    lines = [
        f"长稳恢复计划：{'PASS' if plan.ok else '继续'}",
        f"日志：{plan.log_path}",
        f"样本：{plan.current_samples}/{plan.target_samples}，剩余 {plan.remaining_samples}",
        f"持续：{plan.current_duration:.1f}s/{plan.target_duration:.1f}s，剩余 {plan.remaining_duration:.1f}s",
        f"OneBot：{plan.evidence.onebot_ok}/{plan.current_samples} ({plan.onebot_ratio:.2%})",
    ]
    if plan.evidence.provider_checked:
        lines.append(f"Provider：{plan.evidence.provider_ok}/{plan.evidence.provider_checked} ({plan.provider_ratio:.2%})")
    lines.extend(
        [
            "",
            "推荐命令：",
            f"- 继续观察：{plan.observer_command}",
            f"- 验证证据：{plan.evidence_command}",
        ]
    )
    if not plan.ok:
        lines.extend(["", "未满足项："])
        for check in plan.evidence.checks:
            if not check.ok:
                lines.append(f"- {check.name}: {check.detail}")
    return "\n".join(lines)
