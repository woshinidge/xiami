from __future__ import annotations

from dataclasses import dataclass

from xiami_core.models import AccountStatus
from xiami_core.recovery_plan import RecoveryPlan, build_recovery_plan
from xiami_core.runtime_diagnostic import RuntimeDiagnostic, build_runtime_diagnostic
from xiami_core.stability_evidence import StabilityEvidenceReport, build_stability_evidence_report


OBSERVER_COMMAND = "python -m xiami_core.stability_observer_cli --duration 3600 --interval 30 --provider"
EVIDENCE_COMMAND = (
    "python -m xiami_core.stability_evidence_cli --min-samples 120 "
    "--min-duration 3600 --onebot-ratio 0.99 --provider --provider-ratio 0.95"
)


@dataclass(frozen=True)
class StabilityReadinessCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class StabilityReadinessReport:
    phase: str
    ready_for_observation: bool
    evidence_ok: bool
    account_state: str
    account: str
    checks: tuple[StabilityReadinessCheck, ...]
    recovery_plan: RecoveryPlan
    evidence: StabilityEvidenceReport
    observer_command: str = OBSERVER_COMMAND
    evidence_command: str = EVIDENCE_COMMAND


def build_stability_readiness(
    *,
    status: AccountStatus | None = None,
    diagnostic: RuntimeDiagnostic | None = None,
    evidence: StabilityEvidenceReport | None = None,
    min_samples: int = 120,
    min_duration: float = 3600.0,
    min_onebot_ratio: float = 0.99,
    require_provider: bool = True,
    min_provider_ratio: float = 0.95,
) -> StabilityReadinessReport:
    diag = diagnostic or build_runtime_diagnostic()
    current = status or _status_from_diagnostic(diag)
    evidence_report = evidence or build_stability_evidence_report(
        min_samples=min_samples,
        min_duration=min_duration,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=require_provider,
        min_provider_ratio=min_provider_ratio,
    )
    recovery = build_recovery_plan(status=current, diagnostic=diag)
    checks = (
        StabilityReadinessCheck(
            "OneBot HTTP",
            diag.onebot_reachable,
            diag.onebot_detail,
        ),
        StabilityReadinessCheck(
            "长稳证据",
            evidence_report.ok,
            f"{evidence_report.onebot_ok}/{evidence_report.sample_count}, {evidence_report.duration_seconds:.1f}s",
        ),
        StabilityReadinessCheck(
            "恢复建议",
            recovery.ok or bool(recovery.actions),
            recovery.summary,
        ),
    )
    if evidence_report.ok:
        phase = "evidence_passed"
    elif diag.onebot_reachable:
        phase = "ready_for_observation"
    else:
        phase = "blocked"
    return StabilityReadinessReport(
        phase=phase,
        ready_for_observation=diag.onebot_reachable,
        evidence_ok=evidence_report.ok,
        account_state=current.state,
        account=current.account,
        checks=checks,
        recovery_plan=recovery,
        evidence=evidence_report,
    )


def format_stability_readiness(report: StabilityReadinessReport) -> str:
    title = {
        "evidence_passed": "证据已通过",
        "ready_for_observation": "可开始观察",
        "blocked": "阻塞",
    }.get(report.phase, report.phase)
    lines = [
        f"长稳预检：{title}",
        f"状态：{report.account_state}",
        f"账号：{report.account or '未登录'}",
        "",
        "检查项：",
    ]
    for check in report.checks:
        lines.append(f"- [{'OK' if check.ok else '待处理'}] {check.name}: {check.detail}")
    lines.extend(
        [
            "",
            "命令：",
            f"- 观察：{report.observer_command}",
            f"- 证据：{report.evidence_command}",
        ]
    )
    if report.phase != "evidence_passed":
        lines.extend(["", "恢复建议："])
        for action in report.recovery_plan.actions[:3]:
            lines.append(f"- {action.title}：{action.detail}（入口：{action.ui_action}）")
    return "\n".join(lines)


def _status_from_diagnostic(diagnostic: RuntimeDiagnostic) -> AccountStatus:
    if diagnostic.onebot_reachable:
        return AccountStatus(state="online", detail=diagnostic.onebot_detail)
    if diagnostic.qr_candidates:
        return AccountStatus(
            state="waiting_qr",
            detail=diagnostic.onebot_detail,
            qr_hint=str(diagnostic.qr_candidates[0]),
        )
    return AccountStatus(state="offline", detail=diagnostic.onebot_detail)
