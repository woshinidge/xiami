from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from xiami_core.high_risk_gate import HighRiskGate, build_high_risk_gate, high_risk_gate_to_dict


@dataclass(frozen=True)
class HighRiskAction:
    name: str
    label: str
    ok: bool
    required: bool
    detail: str
    runbook: str
    record_command: str


@dataclass(frozen=True)
class HighRiskNextPlan:
    ok: bool
    next_name: str
    next_label: str
    evidence_path: str
    actions: tuple[HighRiskAction, ...]
    record_all_command: str
    gate: HighRiskGate


def build_high_risk_next_plan() -> HighRiskNextPlan:
    gate = build_high_risk_gate()
    actions = tuple(_action_from_check(check) for check in gate.checks)
    next_action = next((action for action in actions if action.required and not action.ok), None)
    return HighRiskNextPlan(
        ok=gate.ok,
        next_name=next_action.name if next_action else "",
        next_label=next_action.label if next_action else "",
        evidence_path=gate.evidence_path,
        actions=actions,
        record_all_command='python -m xiami_core.high_risk_gate_cli --record-all --detail "真实环境验证通过"',
        gate=gate,
    )


def format_high_risk_next_plan(plan: HighRiskNextPlan) -> str:
    lines = [
        f"高风险验证向导：{'PASS' if plan.ok else 'CONTINUE'}",
        f"证据文件：{plan.evidence_path}",
        f"下一项：{plan.next_label or '无，全部通过'}",
        "",
        "验证顺序：",
    ]
    for index, action in enumerate(plan.actions, start=1):
        mark = "OK" if action.ok else "待验证"
        required = "required" if action.required else "optional"
        lines.extend(
            [
                f"{index}. [{mark}] {action.label} ({required})",
                f"   当前：{action.detail}",
                f"   动作：{action.runbook}",
                f"   记录：{action.record_command}",
            ]
        )
    lines.extend(
        [
            "",
            "候选证据命令（优先使用）：",
            "- python -m xiami_core.onebot_tools_probe_cli --strict",
            "- python -m xiami_core.high_risk_probe_cli --strict",
            "- python -m xiami_core.high_risk_evidence_cli",
            "",
            "批量记录命令（仅在全部真实验证通过后使用）：",
            f"- {plan.record_all_command}",
        ]
    )
    return "\n".join(lines)


def high_risk_next_plan_to_dict(plan: HighRiskNextPlan) -> dict[str, Any]:
    return {
        "ok": plan.ok,
        "next_name": plan.next_name,
        "next_label": plan.next_label,
        "evidence_path": plan.evidence_path,
        "actions": [asdict(action) for action in plan.actions],
        "record_all_command": plan.record_all_command,
        "gate": high_risk_gate_to_dict(plan.gate),
    }


def dumps_high_risk_next_plan(plan: HighRiskNextPlan) -> str:
    return json.dumps(high_risk_next_plan_to_dict(plan), ensure_ascii=False, indent=2)


def _action_from_check(check) -> HighRiskAction:
    return HighRiskAction(
        name=check.name,
        label=check.label,
        ok=check.ok,
        required=check.required,
        detail=check.detail,
        runbook=check.command_hint,
        record_command=(
            "python -m xiami_core.high_risk_gate_cli "
            f'--record {check.name} --detail "真实环境验证通过" --source ui'
        ),
    )
