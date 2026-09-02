from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from xiami_core.high_risk_gate import HighRiskGate, build_high_risk_gate, high_risk_gate_to_dict
from xiami_core.real_acceptance_gate import (
    RealAcceptanceGate,
    real_acceptance_gate_to_dict,
    run_real_acceptance_gate,
)
from xiami_core.stability_resume import (
    StabilityResumePlan,
    build_stability_resume_plan,
)


@dataclass(frozen=True)
class DeliveryChecklistStep:
    name: str
    title: str
    ok: bool
    required: bool
    detail: str
    command: str


@dataclass(frozen=True)
class DeliveryChecklist:
    ok: bool
    phase: str
    steps: tuple[DeliveryChecklistStep, ...]
    real_acceptance: RealAcceptanceGate
    high_risk: HighRiskGate
    stability_resume: StabilityResumePlan
    final_command: str


def build_delivery_checklist(
    *,
    duration: float = 3600.0,
    interval: float = 30.0,
    include_provider: bool = False,
    min_samples: int | None = None,
    min_duration: float | None = None,
    min_onebot_ratio: float = 0.99,
    min_provider_ratio: float = 0.95,
) -> DeliveryChecklist:
    real_gate = run_real_acceptance_gate()
    high_risk = build_high_risk_gate()
    stability = build_stability_resume_plan(
        duration=duration,
        interval=interval,
        include_provider=include_provider,
        min_samples=min_samples,
        min_duration=min_duration,
        min_onebot_ratio=min_onebot_ratio,
        min_provider_ratio=min_provider_ratio,
    )
    final_command = _production_gate_command(duration, interval, include_provider)
    steps = (
        DeliveryChecklistStep(
            name="real_acceptance",
            title="真实登录与收发闭环",
            ok=real_gate.ok,
            required=True,
            detail=_real_gate_detail(real_gate),
            command="python -m xiami_core.real_acceptance_gate_cli",
        ),
        DeliveryChecklistStep(
            name="high_risk_real",
            title="高风险真实场景证据",
            ok=high_risk.ok,
            required=True,
            detail=f"已确认 {high_risk.required_passed}/{high_risk.required_total} 个必需场景",
            command="python -m xiami_core.high_risk_evidence_cli",
        ),
        DeliveryChecklistStep(
            name="stability_resume",
            title="长稳观察证据",
            ok=stability.ok,
            required=True,
            detail=_stability_detail(stability),
            command=_stability_continue_command(duration, interval, include_provider),
        ),
        DeliveryChecklistStep(
            name="evidence_bundle",
            title="交付证据包",
            ok=real_gate.ok and high_risk.ok and stability.ok,
            required=True,
            detail="前置证据通过后导出交付包",
            command=_evidence_bundle_command(include_provider),
        ),
        DeliveryChecklistStep(
            name="production_gate",
            title="最终产品 Gate",
            ok=real_gate.ok and high_risk.ok and stability.ok,
            required=True,
            detail="统一运行真实验收、长稳证据、证据包和产品 Gate",
            command=final_command,
        ),
    )
    required_steps = [step for step in steps if step.required]
    ok = all(step.ok for step in required_steps)
    phase = "passed" if ok else _first_blocking_phase(required_steps)
    return DeliveryChecklist(
        ok=ok,
        phase=phase,
        steps=steps,
        real_acceptance=real_gate,
        high_risk=high_risk,
        stability_resume=stability,
        final_command=final_command,
    )


def format_delivery_checklist(checklist: DeliveryChecklist) -> str:
    lines = [
        f"Xiami 交付清单：{'PASS' if checklist.ok else 'BLOCKED'}",
        f"阶段：{checklist.phase}",
        "",
        "执行顺序：",
    ]
    for index, step in enumerate(checklist.steps, start=1):
        mark = "OK" if step.ok else "待处理"
        required = "required" if step.required else "optional"
        lines.extend(
            [
                f"{index}. [{mark}] {step.title} ({required})",
                f"   {step.detail}",
                f"   命令：{step.command}",
            ]
        )
    lines.extend(
        [
            "",
            "最终命令：",
            f"- {checklist.final_command}",
        ]
    )
    if not checklist.ok:
        lines.extend(["", "当前阻塞："])
        for step in checklist.steps:
            if step.required and not step.ok:
                lines.append(f"- {step.title}: {step.detail}")
    return "\n".join(lines)


def delivery_checklist_to_dict(checklist: DeliveryChecklist) -> dict[str, Any]:
    return {
        "ok": checklist.ok,
        "phase": checklist.phase,
        "steps": [asdict(step) for step in checklist.steps],
        "real_acceptance": real_acceptance_gate_to_dict(checklist.real_acceptance),
        "high_risk": high_risk_gate_to_dict(checklist.high_risk),
        "stability_resume": asdict(checklist.stability_resume),
        "final_command": checklist.final_command,
    }


def dumps_delivery_checklist(checklist: DeliveryChecklist) -> str:
    return json.dumps(delivery_checklist_to_dict(checklist), ensure_ascii=False, indent=2)


def _real_gate_detail(gate: RealAcceptanceGate) -> str:
    required = [check for check in gate.checks if check.required]
    passed = sum(1 for check in required if check.ok)
    return f"phase={gate.phase}, required={passed}/{len(required)}"


def _stability_detail(plan: StabilityResumePlan) -> str:
    return (
        f"samples={plan.current_samples}/{plan.target_samples}, "
        f"duration={plan.current_duration:.0f}/{plan.target_duration:.0f}s, "
        f"onebot_ratio={plan.onebot_ratio:.2%}"
    )


def _first_blocking_phase(steps: list[DeliveryChecklistStep]) -> str:
    for step in steps:
        if not step.ok:
            return step.name
    return "passed"


def _production_gate_command(duration: float, interval: float, include_provider: bool) -> str:
    provider = " -Provider" if include_provider else ""
    return (
        ".\\xiami_acceptance.ps1 -Mode real -ProductGate -LongStability -ExportBundle"
        f"{provider} -StabilityDuration {duration:g} -StabilityInterval {interval:g}"
    )


def _evidence_bundle_command(include_provider: bool) -> str:
    provider = " --provider" if include_provider else ""
    return f"python -m xiami_core.evidence_bundle_cli{provider}"


def _stability_continue_command(duration: float, interval: float, include_provider: bool) -> str:
    provider = " --provider" if include_provider else ""
    return (
        "python -m xiami_core.stability_continue_cli "
        f"--duration {duration:g} --interval {interval:g}{provider}"
    )
