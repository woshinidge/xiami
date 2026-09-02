from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from xiami_core.evidence_bundle import (
    EvidenceBundleResult,
    build_evidence_bundle,
    evidence_bundle_to_dict,
    format_evidence_bundle_result,
)
from xiami_core.high_risk_gate import (
    HighRiskGate,
    build_high_risk_gate,
    format_high_risk_gate,
    high_risk_gate_to_dict,
)
from xiami_core.real_acceptance_gate import (
    RealAcceptanceGate,
    format_real_acceptance_gate,
    format_real_acceptance_gate_brief,
    real_acceptance_gate_to_dict,
    run_real_acceptance_gate,
)
from xiami_core.stability_readiness import (
    StabilityReadinessReport,
    build_stability_readiness,
    format_stability_readiness,
)
from xiami_core.stability_suite import (
    StabilitySuiteResult,
    format_stability_suite_result,
    run_stability_suite,
)


@dataclass(frozen=True)
class ProductionGateCheck:
    name: str
    ok: bool
    required: bool
    detail: str


@dataclass(frozen=True)
class ProductionGateResult:
    ok: bool
    phase: str
    checks: tuple[ProductionGateCheck, ...]
    real_acceptance: RealAcceptanceGate
    high_risk: HighRiskGate
    readiness: StabilityReadinessReport
    stability_suite_text: str
    evidence_bundle: EvidenceBundleResult | None
    next_commands: tuple[str, ...]


def run_production_gate(
    *,
    duration: float = 3600.0,
    interval: float = 30.0,
    include_provider: bool = False,
    run_stability: bool = False,
    export_bundle: bool = False,
    min_samples: int | None = None,
    min_duration: float | None = None,
    min_onebot_ratio: float = 0.99,
    min_provider_ratio: float = 0.95,
) -> ProductionGateResult:
    required_samples = min_samples if min_samples is not None else max(2, int(duration / max(interval, 0.1)) + 1)
    required_duration = min_duration if min_duration is not None else duration

    real_gate = run_real_acceptance_gate()
    high_risk = build_high_risk_gate()
    readiness = build_stability_readiness(
        min_samples=required_samples,
        min_duration=required_duration,
        min_onebot_ratio=min_onebot_ratio,
        require_provider=include_provider,
        min_provider_ratio=min_provider_ratio,
    )

    suite: StabilitySuiteResult | None = None
    if run_stability and real_gate.ok and readiness.ready_for_observation:
        suite = run_stability_suite(
            duration=duration,
            interval=interval,
            include_provider=include_provider,
            min_samples=required_samples,
            min_duration=required_duration,
            min_onebot_ratio=min_onebot_ratio,
            min_provider_ratio=min_provider_ratio,
        )
        readiness = suite.readiness_after

    bundle: EvidenceBundleResult | None = None
    if export_bundle:
        bundle = build_evidence_bundle(
            min_samples=required_samples,
            min_duration=required_duration,
            min_onebot_ratio=min_onebot_ratio,
            require_provider=include_provider,
            min_provider_ratio=min_provider_ratio,
        )

    checks = _checks(real_gate, high_risk, readiness, bundle)
    phase = _phase(real_gate, high_risk, readiness, suite)
    return ProductionGateResult(
        ok=phase == "passed",
        phase=phase,
        checks=checks,
        real_acceptance=real_gate,
        high_risk=high_risk,
        readiness=readiness,
        stability_suite_text=format_stability_suite_result(suite) if suite else "",
        evidence_bundle=bundle,
        next_commands=_next_commands(duration, interval, include_provider),
    )


def format_production_gate(result: ProductionGateResult) -> str:
    lines = [
        f"Xiami 产品交付 Gate：{'PASS' if result.ok else 'BLOCKED'}",
        f"阶段：{result.phase}",
        "",
        "检查：",
    ]
    for check in result.checks:
        mark = "OK" if check.ok else "BLOCKED"
        required = "required" if check.required else "optional"
        lines.append(f"- [{mark}] {check.name} ({required})：{check.detail}")

    lines.extend(["", "真实验收：", *format_real_acceptance_gate_brief(result.real_acceptance)])
    lines.extend(["", "高风险场景：", *format_high_risk_gate(result.high_risk).splitlines()])
    lines.extend(["", "长稳预检：", *format_stability_readiness(result.readiness).splitlines()])

    if result.stability_suite_text:
        lines.extend(["", "长稳套件：", *result.stability_suite_text.splitlines()])
    if result.evidence_bundle:
        lines.extend(["", "证据包：", *format_evidence_bundle_result(result.evidence_bundle).splitlines()])

    lines.extend(["", "在线后推荐命令："])
    lines.extend(f"- {command}" for command in result.next_commands)
    return "\n".join(lines)


def production_gate_to_dict(result: ProductionGateResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "phase": result.phase,
        "checks": [asdict(check) for check in result.checks],
        "real_acceptance": real_acceptance_gate_to_dict(result.real_acceptance),
        "high_risk": high_risk_gate_to_dict(result.high_risk),
        "readiness": {
            "phase": result.readiness.phase,
            "ready_for_observation": result.readiness.ready_for_observation,
            "evidence_ok": result.readiness.evidence_ok,
            "account_state": result.readiness.account_state,
            "account": result.readiness.account,
            "checks": [asdict(check) for check in result.readiness.checks],
        },
        "stability_suite_text": result.stability_suite_text,
        "evidence_bundle": evidence_bundle_to_dict(result.evidence_bundle) if result.evidence_bundle else None,
        "next_commands": list(result.next_commands),
    }


def dumps_production_gate(result: ProductionGateResult) -> str:
    return json.dumps(production_gate_to_dict(result), ensure_ascii=False, indent=2)


def _checks(
    real_gate: RealAcceptanceGate,
    high_risk: HighRiskGate,
    readiness: StabilityReadinessReport,
    bundle: EvidenceBundleResult | None,
) -> tuple[ProductionGateCheck, ...]:
    checks = [
        ProductionGateCheck(
            name="real_acceptance",
            ok=real_gate.ok,
            required=True,
            detail=f"{real_gate.phase}; required={sum(1 for item in real_gate.checks if item.required and item.ok)}/"
            f"{sum(1 for item in real_gate.checks if item.required)}",
        ),
        ProductionGateCheck(
            name="high_risk_real",
            ok=high_risk.ok,
            required=True,
            detail=f"{high_risk.required_passed}/{high_risk.required_total}",
        ),
        ProductionGateCheck(
            name="stability_ready",
            ok=readiness.ready_for_observation or readiness.evidence_ok,
            required=True,
            detail=readiness.phase,
        ),
        ProductionGateCheck(
            name="stability_evidence",
            ok=readiness.evidence_ok,
            required=True,
            detail=f"samples={readiness.evidence.sample_count}, onebot_ratio={readiness.evidence.onebot_ratio:.2%}",
        ),
    ]
    if bundle is not None:
        checks.append(
            ProductionGateCheck(
                name="evidence_bundle",
                ok=bool(bundle.ok),
                required=False,
                detail=bundle.bundle_dir,
            )
        )
    return tuple(checks)


def _phase(
    real_gate: RealAcceptanceGate,
    high_risk: HighRiskGate,
    readiness: StabilityReadinessReport,
    suite: StabilitySuiteResult | None,
) -> str:
    if not real_gate.ok:
        return "blocked_real_acceptance"
    if not high_risk.ok:
        return "blocked_high_risk"
    if readiness.evidence_ok:
        return "passed"
    if suite is not None:
        return "blocked_stability_evidence"
    if readiness.ready_for_observation:
        return "ready_for_stability"
    return "blocked_stability_readiness"


def _next_commands(duration: float, interval: float, include_provider: bool) -> tuple[str, ...]:
    provider = " --provider" if include_provider else ""
    return (
        r"python -m xiami_core.real_probe_cli --fast --timeout 120",
        r"python -m xiami_core.high_risk_next_cli",
        r"python -m xiami_core.onebot_tools_probe_cli --strict",
        r"python -m xiami_core.high_risk_probe_cli --strict",
        r"python -m xiami_core.high_risk_evidence_cli",
        r"python -m xiami_core.high_risk_gate_cli --strict",
        f"python -m xiami_core.stability_continue_cli --duration {duration:g} --interval {interval:g}{provider}",
        (
            "python -m xiami_core.production_gate_cli "
            f"--run-stability --export-bundle --duration {duration:g} --interval {interval:g}{provider} --strict"
        ),
        f"python -m xiami_core.evidence_bundle_cli{provider}",
    )
