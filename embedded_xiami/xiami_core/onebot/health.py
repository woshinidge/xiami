from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xiami_core.messages import MessageRecord
from xiami_core.onebot.events_tail import read_recent_event_summaries
from xiami_core.onebot.receive_diagnostic import ReceiveDiagnostic, run_receive_diagnostic
from xiami_core.onebot.stats import OneBotActionStats, format_onebot_action_stats


@dataclass(frozen=True)
class OneBotHealthSummary:
    receive: ReceiveDiagnostic
    plugin_total: int
    plugin_enabled: int
    plugin_errors: int
    plugin_message_count: int
    plugin_event_count: int
    plugin_message_handled: int
    plugin_message_unhandled: int
    plugin_event_handled: int
    plugin_event_unhandled: int
    plugin_capability_plugins: int
    plugin_capability_count: int
    plugin_capability_message_matchers: int
    plugin_capability_event_matchers: int
    plugin_capability_schedules: int
    plugin_capability_onebot: int
    plugin_capability_send: int
    recent_messages: int
    outgoing_ok: int
    outgoing_failed: int
    plugin_reply_ok: int
    plugin_reply_failed: int
    action_stats: dict[str, Any]
    recent_events: list[str]


def build_onebot_health_summary(
    *,
    plugin_diagnostics: list[dict[str, Any]],
    recent_messages: list[MessageRecord],
    action_stats: OneBotActionStats | dict[str, Any] | None = None,
    event_url: str = "",
    event_limit: int = 5,
) -> OneBotHealthSummary:
    receive = run_receive_diagnostic(event_url=event_url)
    plugin_total = len(plugin_diagnostics)
    plugin_enabled = sum(1 for item in plugin_diagnostics if item.get("enabled"))
    plugin_errors = sum(1 for item in plugin_diagnostics if item.get("error") or int(item.get("error_count") or 0) > 0)
    plugin_message_count = sum(int(item.get("message_count") or 0) for item in plugin_diagnostics)
    plugin_event_count = sum(int(item.get("event_count") or 0) for item in plugin_diagnostics)
    plugin_message_handled = sum(int(item.get("message_handled_count") or 0) for item in plugin_diagnostics)
    plugin_message_unhandled = sum(int(item.get("message_unhandled_count") or 0) for item in plugin_diagnostics)
    plugin_event_handled = sum(int(item.get("event_handled_count") or 0) for item in plugin_diagnostics)
    plugin_event_unhandled = sum(int(item.get("event_unhandled_count") or 0) for item in plugin_diagnostics)
    capability_lists = [item.get("capabilities") or [] for item in plugin_diagnostics]
    capabilities = [str(label) for labels in capability_lists for label in labels if str(label).strip()]

    outgoing = [item for item in recent_messages if item.direction == "outgoing"]
    plugin_replies = [item for item in recent_messages if item.direction == "plugin"]
    return OneBotHealthSummary(
        receive=receive,
        plugin_total=plugin_total,
        plugin_enabled=plugin_enabled,
        plugin_errors=plugin_errors,
        plugin_message_count=plugin_message_count,
        plugin_event_count=plugin_event_count,
        plugin_message_handled=plugin_message_handled,
        plugin_message_unhandled=plugin_message_unhandled,
        plugin_event_handled=plugin_event_handled,
        plugin_event_unhandled=plugin_event_unhandled,
        plugin_capability_plugins=sum(1 for labels in capability_lists if labels),
        plugin_capability_count=len(capabilities),
        plugin_capability_message_matchers=_numeric_capability_total(capabilities, "message-matchers"),
        plugin_capability_event_matchers=_numeric_capability_total(capabilities, "event-matchers"),
        plugin_capability_schedules=_numeric_capability_total(capabilities, "schedules"),
        plugin_capability_onebot=sum(1 for label in capabilities if label.startswith("onebot:")),
        plugin_capability_send=sum(1 for label in capabilities if label.startswith("send:")),
        recent_messages=len(recent_messages),
        outgoing_ok=sum(1 for item in outgoing if item.status == "ok"),
        outgoing_failed=sum(1 for item in outgoing if item.status != "ok"),
        plugin_reply_ok=sum(1 for item in plugin_replies if item.status == "ok"),
        plugin_reply_failed=sum(1 for item in plugin_replies if item.status != "ok"),
        action_stats=_action_stats_snapshot(action_stats),
        recent_events=read_recent_event_summaries(event_limit),
    )


def format_onebot_health_summary(summary: OneBotHealthSummary) -> str:
    receive = summary.receive
    ready_checks = [
        receive.gateway_listening,
        receive.onebot_online,
        receive.napcat_config_ok,
        summary.plugin_errors == 0,
    ]
    ready = sum(1 for item in ready_checks if item)
    lines = [
        f"Xiami 健康摘要：{ready}/{len(ready_checks)}",
        "",
        "OneBot：",
        f"- 事件网关：{'OK' if receive.gateway_listening else '待处理'}",
        f"- HTTP 状态：{'OK' if receive.onebot_online else '待处理'} {receive.onebot_detail}",
        f"- NapCat 配置：{'OK' if receive.napcat_config_ok else '待处理'} {receive.napcat_config_detail}",
        f"- 事件日志：total={receive.event_total}, private={receive.private_events}, group={receive.group_events}, unparsed={receive.unparsed_events}",
        "",
        "插件：",
        f"- 总数：{summary.plugin_total}",
        f"- 启用：{summary.plugin_enabled}",
        f"- 异常：{summary.plugin_errors}",
        f"- 消息分发：{summary.plugin_message_count}",
        f"- 消息命中：{summary.plugin_message_handled}，未命中：{summary.plugin_message_unhandled}",
        f"- 事件分发：{summary.plugin_event_count}",
        f"- 事件命中：{summary.plugin_event_handled}，未命中：{summary.plugin_event_unhandled}",
        "- 迁移能力：覆盖 {plugins} 个插件，能力 {total} 项（消息匹配 {messages}，事件匹配 {events}，定时 {schedules}，OneBot {onebot}，发送 {send}）".format(
            plugins=summary.plugin_capability_plugins,
            total=summary.plugin_capability_count,
            messages=summary.plugin_capability_message_matchers,
            events=summary.plugin_capability_event_matchers,
            schedules=summary.plugin_capability_schedules,
            onebot=summary.plugin_capability_onebot,
            send=summary.plugin_capability_send,
        ),
        "",
        "收发：",
        f"- 最近消息：{summary.recent_messages}",
        f"- 手动发送：成功 {summary.outgoing_ok}，失败 {summary.outgoing_failed}",
        f"- 插件回复：成功 {summary.plugin_reply_ok}，失败 {summary.plugin_reply_failed}",
        "",
        format_onebot_action_stats(summary.action_stats),
        "",
        "最近 OneBot 事件：",
    ]
    lines.extend(f"- {item}" for item in summary.recent_events[:5])
    return "\n".join(lines)


def _action_stats_snapshot(action_stats: OneBotActionStats | dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(action_stats, OneBotActionStats):
        return action_stats.snapshot()
    if isinstance(action_stats, dict):
        return action_stats
    return OneBotActionStats().snapshot()


def _numeric_capability_total(labels: list[str], prefix: str) -> int:
    total = 0
    marker = prefix + ":"
    for label in labels:
        if not label.startswith(marker):
            continue
        value = label[len(marker):]
        try:
            total += int(value)
        except ValueError:
            total += 1
    return total
