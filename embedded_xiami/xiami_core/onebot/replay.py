from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from xiami_core.models import SendResult
from xiami_core.onebot.events import parse_onebot_event
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import plugin_event_from_onebot
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.storage.paths import LOG_HOME, PROJECT_ROOT


@dataclass(frozen=True)
class ReplaySend:
    target: str
    text: str
    message_type: str


@dataclass(frozen=True)
class ReplayAction:
    action: str
    params: dict[str, Any]


@dataclass(frozen=True)
class ReplayResult:
    loaded_plugins: int
    events_read: int
    events_replayed: int
    messages_replayed: int
    plugin_events_replayed: int
    sends: tuple[ReplaySend, ...] = ()
    actions: tuple[ReplayAction, ...] = ()
    diagnostics: tuple[dict[str, Any], ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors


def replay_onebot_events(
    *,
    event_path: Path | None = None,
    plugin_root: Path | None = None,
    state_root: Path | None = None,
    limit: int = 0,
    plugin_ids: tuple[str, ...] = (),
) -> ReplayResult:
    source = event_path or LOG_HOME / "onebot_events.jsonl"
    plugins = plugin_root or PROJECT_ROOT / "xiami_plugins"
    state = state_root or (LOG_HOME / "replay_state")
    sends: list[ReplaySend] = []
    actions: list[ReplayAction] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sends.append(ReplaySend(str(target), str(text), str(message_type)))
        return SendResult(ok=True, detail="replay")

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        actions.append(ReplayAction(str(action), dict(params)))
        return {"status": "ok", "retcode": 0, "data": None}

    ctx = PluginContext(send_fn=send, state_store=PluginKVStore(state / "kv"), onebot_call_fn=onebot_call)
    loader = PluginLoader(plugins, ctx, state_store=PluginStateStore(state / "enabled.json"))
    loaded = loader.load_all()
    selected = {plugin_id.strip() for plugin_id in plugin_ids if plugin_id.strip()}
    if selected:
        for plugin in loaded:
            plugin.enabled = plugin.id in selected
    events_read = 0
    events_replayed = 0
    messages_replayed = 0
    plugin_events_replayed = 0
    errors: list[str] = []

    for payload in iter_onebot_payloads(source, limit=limit):
        events_read += 1
        try:
            message = parse_onebot_event(payload)
            plugin_event = plugin_event_from_onebot(payload, message)
            loader.dispatch_event(plugin_event)
            plugin_events_replayed += 1
            if message:
                loader.dispatch_message(message)
                messages_replayed += 1
            events_replayed += 1
        except Exception as exc:
            errors.append(f"event#{events_read}: {exc}")

    diagnostics = tuple(item for item in loader.diagnostics() if not selected or str(item.get("id")) in selected)
    for plugin in loaded:
        if selected and plugin.id not in selected:
            continue
        if plugin.error:
            errors.append(f"plugin:{plugin.id}: {plugin.error}")
    return ReplayResult(
        loaded_plugins=len(loaded),
        events_read=events_read,
        events_replayed=events_replayed,
        messages_replayed=messages_replayed,
        plugin_events_replayed=plugin_events_replayed,
        sends=tuple(sends),
        actions=tuple(actions),
        diagnostics=diagnostics,
        errors=tuple(errors),
    )


def iter_onebot_payloads(path: Path, *, limit: int = 0) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payloads: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        data = _payload_from_json_line(line)
        if data is None:
            continue
        payloads.append(data)
    if limit > 0:
        return payloads[-limit:]
    return payloads


def format_replay_result(result: ReplayResult) -> str:
    lines = [
        "# Xiami OneBot replay",
        "",
        f"Loaded plugins: {result.loaded_plugins}",
        f"Events read: {result.events_read}",
        f"Events replayed: {result.events_replayed}",
        f"Plugin events replayed: {result.plugin_events_replayed}",
        f"Messages replayed: {result.messages_replayed}",
        f"Sends captured: {len(result.sends)}",
        f"OneBot actions captured: {len(result.actions)}",
    ]
    if result.sends:
        lines.extend(["", "## Sends"])
        for item in result.sends[-20:]:
            lines.append(f"- [{item.message_type}] {item.target}: {item.text}")
    if result.actions:
        lines.extend(["", "## OneBot actions"])
        for item in result.actions[-20:]:
            lines.append(f"- {item.action}: {item.params}")
    if result.errors:
        lines.extend(["", "## Errors", *(f"- {error}" for error in result.errors)])
    lines.extend(["", "## Plugin hits"])
    for item in result.diagnostics:
        hits = item.get("matcher_hit_count") or {}
        if hits:
            lines.append(f"- {item.get('id')}: {hits}")
    if not any(item.get("matcher_hit_count") for item in result.diagnostics):
        lines.append("- none")
    return "\n".join(lines)


def _payload_from_json_line(line: str) -> dict[str, Any] | None:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("raw")
    if isinstance(raw, str):
        try:
            raw_data = json.loads(raw)
        except json.JSONDecodeError:
            raw_data = None
        if isinstance(raw_data, dict):
            return raw_data
    if isinstance(raw, dict):
        return raw
    if data.get("post_type"):
        return data
    return None
