from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from xiami_core.acceptance_evidence import ManualAcceptanceEvidence
from xiami_core.high_risk_gate import (
    HighRiskGate,
    SCENARIOS,
    build_high_risk_gate,
    record_high_risk_scenario,
)
from xiami_core.messages import MessageRecord, MessageStore
from xiami_core.onebot.action_log import ONEBOT_ACTION_LOG_FILE, OneBotActionLogEntry, load_onebot_action_logs
from xiami_core.storage.paths import LOG_HOME


EVENT_LOG_FILE = LOG_HOME / "onebot_events.jsonl"

MODERATION_ACTIONS = {
    "set_group_ban",
    "set_group_kick",
    "set_group_admin",
    "set_group_whole_ban",
    "set_group_card",
    "set_group_special_title",
}
MEMBER_GUARD_ACTIONS = {"delete_msg", "set_group_ban", "set_group_kick"}
ONEBOT_TOOLS_ACTIONS = {
    "get_login_info",
    "get_status",
    "get_friend_list",
    "get_group_list",
    "get_group_member_info",
    "get_group_member_list",
    "get_group_info",
    "get_group_root_files",
    "get_group_files_by_folder",
    "get_group_file_url",
    "set_essence_msg",
    "delete_essence_msg",
    "upload_group_file",
    "delete_group_file",
}


@dataclass(frozen=True)
class HighRiskEvidenceCandidate:
    name: str
    label: str
    ok: bool
    recorded: bool
    confidence: str
    detail: str
    evidence: str
    record_command: str


@dataclass(frozen=True)
class HighRiskEvidenceSuggestions:
    ok: bool
    recordable_count: int
    evidence_path: str
    action_log_path: str
    event_log_path: str
    message_log_path: str
    candidates: tuple[HighRiskEvidenceCandidate, ...]
    gate: HighRiskGate


def build_high_risk_evidence_suggestions(limit: int = 500) -> HighRiskEvidenceSuggestions:
    gate = build_high_risk_gate()
    gate_checks = {check.name: check for check in gate.checks}
    actions = load_onebot_action_logs(limit)
    events = _load_event_logs(EVENT_LOG_FILE, limit)
    messages = MessageStore().recent(limit)
    candidates = tuple(
        _build_candidate(scenario.name, scenario.label, gate_checks.get(scenario.name), actions, events, messages)
        for scenario in SCENARIOS
    )
    recordable_count = sum(1 for item in candidates if item.ok and not item.recorded)
    return HighRiskEvidenceSuggestions(
        ok=gate.ok,
        recordable_count=recordable_count,
        evidence_path=gate.evidence_path,
        action_log_path=str(ONEBOT_ACTION_LOG_FILE),
        event_log_path=str(EVENT_LOG_FILE),
        message_log_path=str(MessageStore().path),
        candidates=candidates,
        gate=gate,
    )


def record_suggested_high_risk_evidence(
    suggestions: HighRiskEvidenceSuggestions | None = None,
    *,
    source: str = "xiami_evidence",
) -> list[ManualAcceptanceEvidence]:
    suggestions = suggestions or build_high_risk_evidence_suggestions()
    recorded: list[ManualAcceptanceEvidence] = []
    for candidate in suggestions.candidates:
        if not candidate.ok or candidate.recorded:
            continue
        detail = f"{candidate.detail}；证据：{candidate.evidence}"
        recorded.append(record_high_risk_scenario(candidate.name, detail, source=source))
    return recorded


def format_high_risk_evidence_suggestions(suggestions: HighRiskEvidenceSuggestions) -> str:
    lines = [
        f"高风险证据候选：{'PASS' if suggestions.ok else 'CONTINUE'}",
        f"可记录候选：{suggestions.recordable_count}",
        f"手动证据：{suggestions.evidence_path}",
        f"Action 日志：{suggestions.action_log_path}",
        f"事件日志：{suggestions.event_log_path}",
        f"消息日志：{suggestions.message_log_path}",
        "",
        "场景候选：",
    ]
    for item in suggestions.candidates:
        mark = "已记录" if item.recorded else "可记录" if item.ok else "缺证据"
        lines.append(f"- [{mark}] {item.label}: {item.detail}")
        if item.evidence:
            lines.append(f"  证据：{item.evidence}")
        if item.ok and not item.recorded:
            lines.append(f"  记录：{item.record_command}")
    if suggestions.recordable_count:
        lines.extend(
            [
                "",
                "批量记录候选：python -m xiami_core.high_risk_evidence_cli --record-suggested",
            ]
        )
    return "\n".join(lines)


def high_risk_evidence_suggestions_to_dict(suggestions: HighRiskEvidenceSuggestions) -> dict[str, Any]:
    return {
        "ok": suggestions.ok,
        "recordable_count": suggestions.recordable_count,
        "evidence_path": suggestions.evidence_path,
        "action_log_path": suggestions.action_log_path,
        "event_log_path": suggestions.event_log_path,
        "message_log_path": suggestions.message_log_path,
        "candidates": [asdict(item) for item in suggestions.candidates],
    }


def dumps_high_risk_evidence_suggestions(suggestions: HighRiskEvidenceSuggestions) -> str:
    return json.dumps(high_risk_evidence_suggestions_to_dict(suggestions), ensure_ascii=False, indent=2)


def _build_candidate(
    name: str,
    label: str,
    check: object,
    actions: list[OneBotActionLogEntry],
    events: list[dict[str, Any]],
    messages: list[MessageRecord],
) -> HighRiskEvidenceCandidate:
    recorded = bool(getattr(check, "ok", False))
    if recorded:
        detail = str(getattr(check, "detail", "已记录真实环境证据"))
        return HighRiskEvidenceCandidate(
            name=name,
            label=label,
            ok=True,
            recorded=True,
            confidence="recorded",
            detail=detail,
            evidence="manual_acceptance",
            record_command=_record_command(name, detail),
        )
    detail, evidence = _infer_candidate(name, actions, events, messages)
    ok = bool(evidence)
    return HighRiskEvidenceCandidate(
        name=name,
        label=label,
        ok=ok,
        recorded=False,
        confidence="strong" if ok else "missing",
        detail=detail,
        evidence=evidence,
        record_command=_record_command(name, detail),
    )


def _infer_candidate(
    name: str,
    actions: list[OneBotActionLogEntry],
    events: list[dict[str, Any]],
    messages: list[MessageRecord],
) -> tuple[str, str]:
    if name == "friend_review_real":
        action = _latest_ok_action(actions, {"set_friend_add_request"})
        if action:
            return "发现好友审核 OneBot action 成功", _action_evidence(action)
        event = _latest_request_event(events, {"friend"})
        if event:
            return "发现好友申请 request 事件", _event_evidence(event)
        return "未发现好友申请 request 或 set_friend_add_request 成功记录", ""
    if name == "join_review_real":
        action = _latest_ok_action(actions, {"set_group_add_request"})
        if action:
            return "发现入群审核 OneBot action 成功", _action_evidence(action)
        event = _latest_request_event(events, {"group"})
        if event:
            return "发现入群申请 request 事件", _event_evidence(event)
        return "未发现入群 request 或 set_group_add_request 成功记录", ""
    if name == "moderation_real":
        action = _latest_ok_action(actions, MODERATION_ACTIONS)
        if action:
            return "发现群管 OneBot action 成功", _action_evidence(action)
        message = _latest_keyword_message(messages, {"禁言", "解禁", "踢出", "群管", "管理员"})
        if message:
            return "发现群管相关消息线索，仍建议补 action 成功记录", _message_evidence(message)
        return "未发现群管 action 成功记录", ""
    if name == "member_guard_real":
        delete_action = _latest_ok_action(actions, {"delete_msg"})
        if delete_action:
            return "发现撤回/删消息 OneBot action 成功", _action_evidence(delete_action)
        action = _latest_ok_action(actions, MEMBER_GUARD_ACTIONS)
        message = _latest_keyword_message(messages, {"违禁", "撤回", "黑名单", "白名单", "敏感词"})
        if message and action:
            return "发现成员守护消息线索和群管 action 成功", f"{_message_evidence(message)}；{_action_evidence(action)}"
        return "未发现违禁词/撤回真实处理证据", ""
    if name == "onebot_tools_real":
        action = _latest_ok_action(actions, ONEBOT_TOOLS_ACTIONS)
        if action:
            return "发现 OneBot 工具 action 成功", _action_evidence(action)
        return "未发现 OneBot 工具 action 成功记录", ""
    return "未知场景", ""


def _latest_ok_action(actions: Iterable[OneBotActionLogEntry], names: set[str]) -> OneBotActionLogEntry | None:
    for action in reversed(list(actions)):
        if action.ok and action.action in names:
            return action
    return None


def _latest_request_event(events: Iterable[dict[str, Any]], request_types: set[str]) -> dict[str, Any] | None:
    for event in reversed(list(events)):
        raw = _raw_event(event)
        request_type = str(event.get("request_type") or raw.get("request_type") or "")
        post_type = str(event.get("post_type") or raw.get("post_type") or "")
        if post_type == "request" and request_type in request_types:
            return event
    return None


def _latest_keyword_message(messages: Iterable[MessageRecord], keywords: set[str]) -> MessageRecord | None:
    for message in reversed(list(messages)):
        text = f"{message.text} {message.detail}"
        if any(keyword in text for keyword in keywords):
            return message
    return None


def _load_event_logs(path: Path, limit: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]:
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            records.append(data)
    return records


def _raw_event(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("raw")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
    return {}


def _action_evidence(action: OneBotActionLogEntry) -> str:
    return f"{action.timestamp.isoformat(timespec='seconds')} action={action.action} ok={action.ok}"


def _event_evidence(event: dict[str, Any]) -> str:
    return "{time} post_type={post_type} request_type={request_type}".format(
        time=event.get("time") or "",
        post_type=event.get("post_type") or _raw_event(event).get("post_type") or "",
        request_type=event.get("request_type") or _raw_event(event).get("request_type") or "",
    )


def _message_evidence(message: MessageRecord) -> str:
    return (
        f"{message.timestamp.isoformat(timespec='seconds')} "
        f"{message.message_type} {message.sender}->{message.target}: {message.text[:80]}"
    )


def _record_command(name: str, detail: str) -> str:
    safe_detail = detail.replace('"', "'")
    return f'python -m xiami_core.high_risk_gate_cli --record {name} --detail "{safe_detail}"'
