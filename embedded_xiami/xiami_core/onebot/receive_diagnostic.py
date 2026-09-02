from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from xiami_core.kernels.napcat_config import inspect_napcat_onebot_config
from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.storage.config import load_config
from xiami_core.storage.paths import LOG_HOME


@dataclass(frozen=True)
class ReceiveDiagnostic:
    gateway_host: str
    gateway_port: int
    gateway_listening: bool
    gateway_ws_host: str
    gateway_ws_port: int
    gateway_ws_listening: bool
    onebot_online: bool
    onebot_detail: str
    napcat_config_ok: bool
    napcat_config_detail: str
    event_total: int
    http_events: int
    ws_events: int
    private_events: int
    group_events: int
    unparsed_events: int
    latest_event: str


def run_receive_diagnostic(event_url: str = "", event_ws_url: str = "") -> ReceiveDiagnostic:
    config = load_config().kernel
    gateway_host, gateway_port = _gateway_endpoint(event_url)
    event_ws_url = event_ws_url or _infer_event_ws_url(event_url)
    gateway_ws_host, gateway_ws_port = _gateway_endpoint(event_ws_url, default_port=18082)
    gateway_listening = _is_listening(gateway_host, gateway_port)
    gateway_ws_listening = _is_listening(gateway_ws_host, gateway_ws_port)
    client = OneBotHttpClient(config.http_url, config.access_token, timeout=1.0)
    status = client.get_status()
    onebot_online = False
    onebot_detail = status.message
    if status.ok and isinstance(status.data, dict):
        onebot_online = bool(status.data.get("online"))
        onebot_detail = "OneBot 在线" if onebot_online else f"OneBot 可访问但未在线：{status.data}"

    napcat_state = inspect_napcat_onebot_config(config, event_url=event_url, event_ws_url=event_ws_url)
    napcat_detail = (
        f"files={len(napcat_state.files)}, http={napcat_state.http_enabled}/{napcat_state.http_matched}, "
        f"http_push={napcat_state.event_enabled}/{napcat_state.event_matched}, "
        f"ws_push={napcat_state.ws_event_enabled}/{napcat_state.ws_event_matched}"
    )
    event_stats = _read_event_stats()
    return ReceiveDiagnostic(
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        gateway_listening=gateway_listening,
        gateway_ws_host=gateway_ws_host,
        gateway_ws_port=gateway_ws_port,
        gateway_ws_listening=gateway_ws_listening,
        onebot_online=onebot_online,
        onebot_detail=onebot_detail,
        napcat_config_ok=napcat_state.ok,
        napcat_config_detail=napcat_detail,
        event_total=event_stats["total"],
        http_events=event_stats["http"],
        ws_events=event_stats["ws"],
        private_events=event_stats["private"],
        group_events=event_stats["group"],
        unparsed_events=event_stats["unparsed"],
        latest_event=event_stats["latest"],
    )


def format_receive_diagnostic(result: ReceiveDiagnostic) -> str:
    lines = [
        "接收闭环诊断",
        f"[{'OK' if result.gateway_listening else '待处理'}] Xiami HTTP 事件网关 {result.gateway_host}:{result.gateway_port}",
        f"[{'OK' if result.gateway_ws_listening else '待处理'}] Xiami WS 事件网关 {result.gateway_ws_host}:{result.gateway_ws_port}",
        f"[{'OK' if result.onebot_online else '待处理'}] OneBot HTTP：{result.onebot_detail}",
        f"[{'OK' if result.napcat_config_ok else '待处理'}] NapCat OneBot 配置：{result.napcat_config_detail}",
        (
            f"事件日志：total={result.event_total}, ws={result.ws_events}, http={result.http_events}, "
            f"private={result.private_events}, group={result.group_events}, unparsed={result.unparsed_events}"
        ),
        f"最近事件：{result.latest_event or '无'}",
        "",
        "判断：",
    ]
    if not result.gateway_listening and not result.gateway_ws_listening:
        lines.append("- Xiami 事件网关未监听，NapCat 无法上报消息。")
    elif not result.gateway_ws_listening:
        lines.append("- HTTP 网关已监听，但 WS 事件网关未监听；实时消息可能不稳定。")
    elif not result.onebot_online:
        lines.append("- OneBot HTTP 未在线，先在账号页启动/登录 NapCat。")
    elif result.group_events and result.ws_events:
        lines.append("- 已通过 WS 收到群消息，插件应能实时响应命令。")
    elif result.group_events and not result.private_events:
        lines.append("- 群事件已上报但没有私聊事件；若刚发过私聊，优先检查 NapCat 是否产生私聊上报。")
    elif result.private_events:
        lines.append("- 已记录私聊事件；若界面没显示，问题在 UI 分发/展示。")
    else:
        lines.append("- 尚无 message 事件；发送群聊或私聊后再刷新诊断。")
    return "\n".join(lines)


def _read_event_stats() -> dict[str, Any]:
    path = LOG_HOME / "onebot_events.jsonl"
    stats: dict[str, Any] = {
        "total": 0,
        "http": 0,
        "ws": 0,
        "private": 0,
        "group": 0,
        "unparsed": 0,
        "latest": "",
    }
    if not path.exists():
        return stats
    try:
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except OSError:
        return stats
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        stats["total"] += 1
        transport = str(entry.get("transport") or "")
        if transport == "http":
            stats["http"] += 1
        elif transport == "ws":
            stats["ws"] += 1
        parsed_type = str(entry.get("parsed_type") or "")
        if parsed_type == "private":
            stats["private"] += 1
        elif parsed_type == "group":
            stats["group"] += 1
        elif entry.get("post_type") == "message" or entry.get("parsed") is False:
            stats["unparsed"] += 1
        stats["latest"] = (
            f"{entry.get('time', '')} transport={transport or '-'} type={parsed_type or entry.get('message_type') or ''} "
            f"sender={entry.get('parsed_sender', '')} target={entry.get('parsed_target', '')} "
            f"text={entry.get('parsed_text', '')}"
        ).strip()
    return stats


def _is_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return True
    except OSError:
        return False


def _gateway_endpoint(event_url: str, default_port: int = 18081) -> tuple[str, int]:
    if not event_url:
        return "127.0.0.1", default_port
    parsed = urlparse(event_url)
    return parsed.hostname or "127.0.0.1", parsed.port or default_port


def _infer_event_ws_url(event_url: str) -> str:
    if not event_url:
        return "ws://127.0.0.1:18082/onebot/event"
    parsed = urlparse(event_url)
    host = parsed.hostname or "127.0.0.1"
    port = (parsed.port or 18081) + 1
    path = parsed.path or "/onebot/event"
    return f"ws://{host}:{port}{path}"
