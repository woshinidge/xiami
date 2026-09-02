from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from xiami_core.messages import MessageRecord, format_message_record
from xiami_core.migration_verify import MigrationVerification, format_migration_verification
from xiami_core.onebot.health import (
    OneBotHealthSummary,
    build_onebot_health_summary,
    format_onebot_health_summary,
)
from xiami_core.onebot.stats import OneBotActionStats
from xiami_core.real_acceptance_gate import RealAcceptanceGate, format_real_acceptance_gate
from xiami_core.storage.paths import LOG_HOME, ensure_runtime_dirs


@dataclass(frozen=True)
class DiagnosticReport:
    path: Path
    content: str


def export_diagnostic_report(
    *,
    plugin_diagnostics: list[dict[str, Any]],
    recent_messages: list[MessageRecord],
    action_stats: OneBotActionStats | dict[str, Any] | None = None,
    migration_verification: MigrationVerification | None = None,
    real_acceptance_gate: RealAcceptanceGate | None = None,
    output_dir: Path | None = None,
) -> DiagnosticReport:
    summary = build_onebot_health_summary(
        plugin_diagnostics=plugin_diagnostics,
        recent_messages=recent_messages,
        action_stats=action_stats,
    )
    content = render_diagnostic_report(
        summary,
        plugin_diagnostics=plugin_diagnostics,
        recent_messages=recent_messages,
        migration_verification=migration_verification,
        real_acceptance_gate=real_acceptance_gate,
    )
    ensure_runtime_dirs()
    target_dir = output_dir or LOG_HOME / "diagnostics"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = target_dir / f"xiami_diagnostic_{timestamp}.md"
    path.write_text(content, encoding="utf-8")
    return DiagnosticReport(path=path, content=content)


def render_diagnostic_report(
    summary: OneBotHealthSummary,
    *,
    plugin_diagnostics: list[dict[str, Any]],
    recent_messages: list[MessageRecord],
    migration_verification: MigrationVerification | None = None,
    real_acceptance_gate: RealAcceptanceGate | None = None,
) -> str:
    lines = [
        "# Xiami Diagnostic Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Health Summary",
        "",
        "```text",
        format_onebot_health_summary(summary),
        "```",
        "",
        "## Plugins",
        "",
        "| ID | Name | Enabled | Messages | Msg Hit/Miss | Events | Event Hit/Miss | Errors | Last Error |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in plugin_diagnostics:
        lines.append(
            "| {id} | {name} | {enabled} | {messages} | {message_health} | {events} | {event_health} | {errors} | {last_error} |".format(
                id=_cell(item.get("id", "")),
                name=_cell(item.get("name", "")),
                enabled="yes" if item.get("enabled") else "no",
                messages=int(item.get("message_count") or 0),
                message_health=f"{int(item.get('message_handled_count') or 0)}/{int(item.get('message_unhandled_count') or 0)}",
                events=int(item.get("event_count") or 0),
                event_health=f"{int(item.get('event_handled_count') or 0)}/{int(item.get('event_unhandled_count') or 0)}",
                errors=int(item.get("error_count") or 0),
                last_error=_cell(str(item.get("last_error") or item.get("error") or "")),
            )
        )

    status_items = [item for item in plugin_diagnostics if item.get("migration_status")]
    if status_items:
        lines.extend(["", "## Plugin Migration Status", ""])
        for item in status_items:
            lines.append(f"- {_cell(item.get('name') or item.get('id') or '')}: {_cell(item.get('migration_status') or '')}")

    capability_items = [item for item in plugin_diagnostics if item.get("capabilities")]
    if capability_items:
        lines.extend(["", "## Plugin Capabilities", ""])
        for item in capability_items:
            labels = ", ".join(_cell(str(value)) for value in item.get("capabilities", []))
            lines.append(f"- {_cell(item.get('name') or item.get('id') or '')}: {labels}")

    history_items = [item for item in plugin_diagnostics if item.get("error_history")]
    if history_items:
        lines.extend(["", "## Plugin Error History", ""])
        for item in history_items:
            lines.append(f"### {_cell(item.get('name') or item.get('id') or '')}")
            for error in list(item.get("error_history") or [])[-10:]:
                lines.append(f"- {_cell(error)}")

    lines.extend(["", "## Recent Messages", ""])
    if recent_messages:
        for record in recent_messages[-50:]:
            lines.append(f"- {format_message_record(record)}")
    else:
        lines.append("- No recent messages.")

    lines.extend(["", "## Recent OneBot Events", ""])
    if summary.recent_events:
        for item in summary.recent_events[:20]:
            lines.append(f"- {item}")
    else:
        lines.append("- No recent OneBot events.")
    if migration_verification is not None:
        lines.extend(["", "## Migration Verification", "", "```text"])
        lines.extend(format_migration_verification(migration_verification).splitlines())
        lines.append("```")
    if real_acceptance_gate is not None:
        lines.extend(["", "## Real Acceptance Gate", "", "```text"])
        lines.extend(format_real_acceptance_gate(real_acceptance_gate).splitlines())
        lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _cell(value: object) -> str:
    text = str(value or "")
    return text.replace("|", "\\|").replace("\n", " ")[:300]
