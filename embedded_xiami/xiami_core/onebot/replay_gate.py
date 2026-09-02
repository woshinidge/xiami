from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xiami_core.onebot.events import parse_onebot_event
from xiami_core.onebot.replay import ReplayResult, iter_onebot_payloads, replay_onebot_events
from xiami_core.storage.paths import LOG_HOME, PROJECT_ROOT


@dataclass(frozen=True)
class ReplayGateCheck:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class ReplayGateResult:
    replay: ReplayResult
    checks: tuple[ReplayGateCheck, ...]

    @property
    def ok(self) -> bool:
        return self.replay.ok and all(item.ok for item in self.checks)


def run_replay_gate(
    *,
    event_path: Path | None = None,
    plugin_root: Path | None = None,
    state_root: Path | None = None,
    limit: int = 0,
    plugin_ids: tuple[str, ...] = (),
    min_events: int = 1,
    min_sends: int = 0,
    min_actions: int = 0,
    require_private_message: bool = False,
    require_group_message: bool = False,
    require_notice: bool = False,
    require_request: bool = False,
    require_actions: tuple[str, ...] = (),
) -> ReplayGateResult:
    source = event_path or LOG_HOME / "onebot_events.jsonl"
    plugins = plugin_root or PROJECT_ROOT / "xiami_plugins"
    state = state_root or (LOG_HOME / "replay_gate_state")
    payloads = iter_onebot_payloads(source, limit=limit)
    metadata = _event_metadata(payloads)
    replay = replay_onebot_events(
        event_path=source,
        plugin_root=plugins,
        state_root=state,
        limit=limit,
        plugin_ids=plugin_ids,
    )
    checks = [
        ReplayGateCheck(
            "events",
            replay.events_replayed >= min_events,
            f"{replay.events_replayed}/{min_events} events replayed",
        ),
        ReplayGateCheck(
            "plugin_errors",
            not replay.errors,
            "; ".join(replay.errors) if replay.errors else "no replay/plugin errors",
        ),
    ]
    if require_private_message:
        checks.append(
            ReplayGateCheck(
                "private_message",
                "private" in metadata["message_types"],
                "private message seen" if "private" in metadata["message_types"] else "private message missing",
            )
        )
    if require_group_message:
        checks.append(
            ReplayGateCheck(
                "group_message",
                "group" in metadata["message_types"],
                "group message seen" if "group" in metadata["message_types"] else "group message missing",
            )
        )
    if require_notice:
        checks.append(
            ReplayGateCheck(
                "notice",
                "notice" in metadata["post_types"],
                "notice event seen" if "notice" in metadata["post_types"] else "notice event missing",
            )
        )
    if require_request:
        checks.append(
            ReplayGateCheck(
                "request",
                "request" in metadata["post_types"],
                "request event seen" if "request" in metadata["post_types"] else "request event missing",
            )
        )
    if min_sends:
        checks.append(
            ReplayGateCheck(
                "sends",
                len(replay.sends) >= min_sends,
                f"{len(replay.sends)}/{min_sends} sends captured",
            )
        )
    if min_actions:
        checks.append(
            ReplayGateCheck(
                "actions",
                len(replay.actions) >= min_actions,
                f"{len(replay.actions)}/{min_actions} OneBot actions captured",
            )
        )
    for action in require_actions:
        action_names = {item.action for item in replay.actions}
        checks.append(
            ReplayGateCheck(
                f"action:{action}",
                action in action_names,
                f"{action} captured" if action in action_names else f"{action} missing",
            )
        )
    return ReplayGateResult(replay=replay, checks=tuple(checks))


def format_replay_gate_result(result: ReplayGateResult) -> str:
    lines = [
        "# Xiami OneBot replay gate",
        "",
        f"Gate: {'PASS' if result.ok else 'FAIL'}",
        f"Loaded plugins: {result.replay.loaded_plugins}",
        f"Events replayed: {result.replay.events_replayed}",
        f"Messages replayed: {result.replay.messages_replayed}",
        f"Plugin events replayed: {result.replay.plugin_events_replayed}",
        f"Sends captured: {len(result.replay.sends)}",
        f"OneBot actions captured: {len(result.replay.actions)}",
        "",
        "## Checks",
    ]
    for check in result.checks:
        mark = "OK" if check.ok else "FAIL"
        lines.append(f"- [{mark}] {check.name}: {check.detail}")
    if result.replay.sends:
        lines.extend(["", "## Sends"])
        for item in result.replay.sends[-20:]:
            lines.append(f"- [{item.message_type}] {item.target}: {item.text}")
    if result.replay.actions:
        lines.extend(["", "## Actions"])
        for item in result.replay.actions[-20:]:
            lines.append(f"- {item.action}: {item.params}")
    return "\n".join(lines)


def _event_metadata(payloads: list[dict[str, Any]]) -> dict[str, set[str]]:
    post_types: set[str] = set()
    message_types: set[str] = set()
    for payload in payloads:
        post_type = str(payload.get("post_type") or "").strip()
        if post_type:
            post_types.add(post_type)
        message = parse_onebot_event(payload)
        if message:
            message_types.add(message.message_type)
    return {"post_types": post_types, "message_types": message_types}
