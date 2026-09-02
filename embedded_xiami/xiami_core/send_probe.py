from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from xiami_core.events import EventBus
from xiami_core.kernels.manager import KernelManager
from xiami_core.messages import MessageRecord, MessageStore
from xiami_core.storage.config import load_config


@dataclass(frozen=True)
class SendProbeItem:
    name: str
    ok: bool
    detail: str


def run_send_probe(private_target: str = "", group_target: str = "") -> list[SendProbeItem]:
    config = load_config()
    private_target = private_target.strip() or config.probe_private_target.strip()
    group_target = group_target.strip() or config.probe_group_target.strip()
    manager = KernelManager(EventBus())
    status = manager.status()
    if status.state != "online":
        status = manager.start_login()
    items = [
        SendProbeItem("onebot_online", status.state == "online", f"{status.state}；{status.detail}"),
        SendProbeItem("private_target", bool(private_target), private_target or "未配置好友 QQ"),
        SendProbeItem("group_target", bool(group_target), group_target or "未配置群号"),
    ]
    store = MessageStore()
    if private_target:
        items.append(_send_and_record(manager, store, "private", private_target))
    if group_target:
        items.append(_send_and_record(manager, store, "group", group_target))
    return items


def format_send_probe(items: list[SendProbeItem]) -> str:
    passed = sum(1 for item in items if item.ok)
    lines = [f"真实收发探针：{passed}/{len(items)}", ""]
    for item in items:
        mark = "OK" if item.ok else "待处理"
        lines.append(f"[{mark}] {item.name}")
        lines.append(f"  {item.detail}")
    return "\n".join(lines)


def _send_and_record(manager: KernelManager, store: MessageStore, message_type: str, target: str) -> SendProbeItem:
    text = f"Xiami v1 send probe {message_type} {datetime.now().strftime('%H:%M:%S')}"
    result = manager.send_message(target, text, message_type)
    store.append(
        MessageRecord(
            direction="outgoing",
            message_type=message_type,  # type: ignore[arg-type]
            target=target,
            text=text,
            status="ok" if result.ok else "failed",
            detail=result.detail,
            message_id=result.message_id,
            source="send_probe",
        )
    )
    name = f"send_{message_type}_probe"
    return SendProbeItem(name, result.ok, f"{target}: {result.detail}")
