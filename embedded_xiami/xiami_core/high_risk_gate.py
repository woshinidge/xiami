from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from xiami_core.acceptance_evidence import (
    MANUAL_EVIDENCE_FILE,
    ManualAcceptanceEvidence,
    load_manual_evidence,
    record_manual_evidence,
)


@dataclass(frozen=True)
class HighRiskScenario:
    name: str
    label: str
    required: bool
    command_hint: str


@dataclass(frozen=True)
class HighRiskCheck:
    name: str
    label: str
    ok: bool
    required: bool
    detail: str
    command_hint: str


@dataclass(frozen=True)
class HighRiskGate:
    ok: bool
    required_passed: int
    required_total: int
    checks: tuple[HighRiskCheck, ...]
    evidence_path: str


SCENARIOS: tuple[HighRiskScenario, ...] = (
    HighRiskScenario(
        name="friend_review_real",
        label="好友审核真实验证",
        required=True,
        command_hint="触发好友申请，验证同意/拒绝/关键词审核和记录。",
    ),
    HighRiskScenario(
        name="join_review_real",
        label="入群审核真实验证",
        required=True,
        command_hint="触发入群申请，验证自动/人工审核、欢迎/退群通知和最近记录。",
    ),
    HighRiskScenario(
        name="moderation_real",
        label="群管真实验证",
        required=True,
        command_hint="在测试群验证禁言、解禁、踢出或对应 OneBot action 返回成功。",
    ),
    HighRiskScenario(
        name="member_guard_real",
        label="违禁词/撤回真实验证",
        required=True,
        command_hint="在测试群验证违禁词命中、撤回/禁言策略、黑白名单豁免。",
    ),
    HighRiskScenario(
        name="onebot_tools_real",
        label="OneBot 工具真实验证",
        required=True,
        command_hint="验证 QQ资料、列好友、列群、删精华/群文件等 OneBot 工具 action。",
    ),
)


def build_high_risk_gate(
    *,
    records: dict[str, ManualAcceptanceEvidence] | None = None,
) -> HighRiskGate:
    evidence = records if records is not None else load_manual_evidence()
    checks = tuple(_scenario_check(scenario, evidence.get(scenario.name)) for scenario in SCENARIOS)
    required = [check for check in checks if check.required]
    passed = sum(1 for check in required if check.ok)
    return HighRiskGate(
        ok=passed == len(required),
        required_passed=passed,
        required_total=len(required),
        checks=checks,
        evidence_path=str(MANUAL_EVIDENCE_FILE),
    )


def record_high_risk_scenario(
    name: str,
    detail: str,
    *,
    ok: bool = True,
    source: str = "user",
) -> ManualAcceptanceEvidence:
    if name not in scenario_names():
        allowed = ", ".join(scenario_names())
        raise ValueError(f"unknown high-risk scenario {name!r}; allowed: {allowed}")
    return record_manual_evidence(name, detail, ok=ok, source=source)


def scenario_names() -> tuple[str, ...]:
    return tuple(scenario.name for scenario in SCENARIOS)


def format_high_risk_gate(gate: HighRiskGate) -> str:
    lines = [
        f"高风险真实场景 Gate：{'PASS' if gate.ok else 'BLOCKED'}",
        f"必需项：{gate.required_passed}/{gate.required_total}",
        f"证据：{gate.evidence_path}",
        "",
        "场景：",
    ]
    for check in gate.checks:
        mark = "OK" if check.ok else "待验证"
        lines.append(f"- [{mark}] {check.label}: {check.detail}")
        if not check.ok:
            lines.append(f"  建议：{check.command_hint}")
            lines.append(
                "  记录：python -m xiami_core.high_risk_gate_cli "
                f"--record {check.name} --detail \"真实环境验证通过\""
            )
    return "\n".join(lines)


def high_risk_gate_to_dict(gate: HighRiskGate) -> dict[str, Any]:
    return {
        "ok": gate.ok,
        "required_passed": gate.required_passed,
        "required_total": gate.required_total,
        "evidence_path": gate.evidence_path,
        "checks": [asdict(check) for check in gate.checks],
    }


def dumps_high_risk_gate(gate: HighRiskGate) -> str:
    return json.dumps(high_risk_gate_to_dict(gate), ensure_ascii=False, indent=2)


def _scenario_check(scenario: HighRiskScenario, evidence: ManualAcceptanceEvidence | None) -> HighRiskCheck:
    if evidence and evidence.ok:
        detail = f"{evidence.detail}；{evidence.source} confirmed {evidence.updated_at}"
        return HighRiskCheck(
            name=scenario.name,
            label=scenario.label,
            ok=True,
            required=scenario.required,
            detail=detail,
            command_hint=scenario.command_hint,
        )
    detail = evidence.detail if evidence else "未记录真实环境证据"
    return HighRiskCheck(
        name=scenario.name,
        label=scenario.label,
        ok=False,
        required=scenario.required,
        detail=detail,
        command_hint=scenario.command_hint,
    )
