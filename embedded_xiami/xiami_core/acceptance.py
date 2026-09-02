from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from xiami_core.events import EventBus
from xiami_core.acceptance_evidence import apply_manual_evidence
from xiami_core.contacts import ContactStore
from xiami_core.kernels.manager import KernelManager
from xiami_core.messages import MessageRecord, MessageStore
from xiami_core.models import SendResult, XiamiMessage
from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.storage.config import load_config
from xiami_core.storage.paths import CONFIG_FILE, LOG_HOME, PROJECT_ROOT


@dataclass(frozen=True)
class AcceptanceItem:
    name: str
    ok: bool
    detail: str


def run_v1_acceptance() -> list[AcceptanceItem]:
    config = load_config()
    bus = EventBus()
    manager = KernelManager(bus)
    status = manager.status()
    real_kernel = config.kernel.kind.lower() != "mock"

    items = [
        AcceptanceItem("desktop_core", True, "xiami_core 可加载"),
        AcceptanceItem("kernel_config", bool(config.kernel.kind), f"当前内核：{config.kernel.kind}"),
        AcceptanceItem(
            "real_kernel_selected",
            real_kernel,
            "已选择真实内核" if real_kernel else "当前为 Mock，仅用于模拟 UI/插件闭环",
        ),
    ]

    login_ok = status.state == "online" and real_kernel
    qr_ready = ((status.state == "waiting_qr" and bool(status.qr_hint)) or status.state == "online") and real_kernel
    items.append(
        AcceptanceItem(
            "login_qr_ready",
            qr_ready,
            f"二维码：{status.qr_hint}" if status.qr_hint else f"状态：{status.state}",
        )
    )
    items.append(AcceptanceItem("real_login", login_ok, f"状态：{status.state}；{status.detail}"))

    onebot = OneBotHttpClient(config.kernel.http_url, config.kernel.access_token).get_login_info()
    items.append(AcceptanceItem("onebot_login_info", onebot.ok and real_kernel, onebot.message))

    event_log = LOG_HOME / "onebot_events.jsonl"
    event_records = _read_event_log()
    items.append(
        AcceptanceItem(
            "onebot_event_log",
            event_log.exists(),
            f"events={len(event_records)} file={event_log}" if event_log.exists() else "尚未产生 OneBot 上报日志",
        )
    )
    items.append(_event_acceptance("receive_private_event", event_records, "private"))
    items.append(_event_acceptance("receive_group_event", event_records, "group"))

    items.extend(_contact_acceptance_items())
    message_items = _message_acceptance_items()
    items.extend(message_items)

    plugin_ok, plugin_detail = _check_plugin_loop()
    items.append(AcceptanceItem("plugin_loop", plugin_ok, plugin_detail))
    return apply_manual_evidence(items)


def format_acceptance(items: list[AcceptanceItem]) -> str:
    passed = sum(1 for item in items if item.ok)
    lines = [f"Xiami v1 验收：{passed}/{len(items)}", ""]
    summary = summarize_acceptance(items)
    if summary:
        lines.extend(["缺口摘要：", summary, ""])
    failed_details = failed_acceptance_details(items)
    if failed_details:
        lines.extend(["待处理明细：", *failed_details, ""])
    lines.extend(["证据路径：", *acceptance_evidence_lines(), ""])
    for item in items:
        mark = "OK" if item.ok else "待处理"
        lines.append(f"[{mark}] {item.name}")
        lines.append(f"  {item.detail}")
    return "\n".join(lines)


def summarize_acceptance(items: list[AcceptanceItem]) -> str:
    failed = {item.name: item.detail for item in items if not item.ok}
    if not failed:
        return "全部验收项已通过。"
    hints: list[str] = []
    if "real_kernel_selected" in failed:
        hints.append("在账号页点击“扫码/登录”会自动准备推荐真实内核；也可在设置页点击“使用推荐真实内核”。")
    if "login_qr_ready" in failed or "real_login" in failed or "onebot_login_info" in failed:
        hints.append("先在账号页启动 NapCat 并完成扫码登录，确保 OneBot HTTP 在线。")
    if "onebot_event_log" in failed:
        hints.append("登录后保持 Xiami 运行，等待 NapCat 向 OneBot 事件上报地址写入事件日志。")
    if "receive_private_event" in failed:
        hints.append("用另一个 QQ 给机器人发一条私聊消息，确认 OneBot 上报私聊事件。")
    if "receive_group_event" in failed:
        hints.append("在机器人所在群发送一条消息，确认 OneBot 上报群聊事件。")
    if "receive_private_event" not in failed and "ui_private_received" in failed:
        hints.append("私聊事件已有上报但未进入消息页历史，需要检查 UI 事件总线或历史回填。")
    if "receive_group_event" not in failed and "ui_group_received" in failed:
        hints.append("群聊事件已有上报但未进入消息页历史，需要检查 UI 事件总线或历史回填。")
    if "send_private_ok" in failed:
        hints.append("在消息页选择好友，填写目标 QQ 并发送一条消息。")
    if "send_group_ok" in failed:
        hints.append("在消息页选择群，填写群号并发送一条消息。")
    if "friend_contacts" in failed or "group_contacts" in failed:
        hints.append("登录后同步联系人，确认好友列表和群列表已缓存。")
    if not hints:
        hints.append("仍有验收项未通过，请查看下方待处理条目。")
    return "\n".join(f"- {hint}" for hint in hints)


def failed_acceptance_details(items: list[AcceptanceItem]) -> list[str]:
    return [f"- {item.name}: {item.detail}" for item in items if not item.ok]


def acceptance_evidence_lines() -> list[str]:
    message_store = MessageStore()
    contact_store = ContactStore()
    return [
        f"- 配置：{CONFIG_FILE}",
        f"- OneBot 事件：{LOG_HOME / 'onebot_events.jsonl'}",
        f"- 消息历史：{message_store.path}",
        f"- 联系人缓存：{contact_store.path}",
    ]


def _read_event_log(limit: int = 500) -> list[dict[str, Any]]:
    path = LOG_HOME / "onebot_events.jsonl"
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


def _event_acceptance(name: str, records: list[dict[str, Any]], message_type: str) -> AcceptanceItem:
    matching = [
        record
        for record in records
        if record.get("parsed") and str(record.get("parsed_type") or record.get("message_type")) == message_type
    ]
    if not matching:
        return AcceptanceItem(name, False, f"未发现 {message_type} OneBot 接收事件")
    latest = matching[-1]
    return AcceptanceItem(
        name,
        True,
        "sender={sender} target={target} text={text}".format(
            sender=latest.get("parsed_sender") or latest.get("user_id") or "",
            target=latest.get("parsed_target") or latest.get("group_id") or "",
            text=latest.get("parsed_text") or "",
        ),
    )


def _message_acceptance_items() -> list[AcceptanceItem]:
    store = MessageStore()
    records = store.recent(500)
    items = [
        AcceptanceItem(
            "ui_message_history",
            bool(records),
            f"messages={len(records)} file={store.path}" if records else f"无消息历史：{store.path}",
        )
    ]
    items.append(_record_acceptance("ui_private_received", records, direction={"incoming", "kernel"}, message_type="private"))
    items.append(_record_acceptance("ui_group_received", records, direction={"incoming", "kernel"}, message_type="group"))
    items.append(_record_acceptance("send_private_ok", records, direction={"outgoing", "plugin"}, message_type="private", ok_only=True))
    items.append(_record_acceptance("send_group_ok", records, direction={"outgoing", "plugin"}, message_type="group", ok_only=True))
    return items


def _contact_acceptance_items() -> list[AcceptanceItem]:
    store = ContactStore()
    contacts = store.load()
    friends = [contact for contact in contacts if contact.kind == "friend"]
    groups = [contact for contact in contacts if contact.kind == "group"]
    return [
        AcceptanceItem(
            "contacts_cache",
            bool(contacts),
            f"contacts={len(contacts)} file={store.path}" if contacts else f"无联系人缓存：{store.path}",
        ),
        AcceptanceItem(
            "friend_contacts",
            bool(friends),
            f"friends={len(friends)}" if friends else "未发现好友联系人",
        ),
        AcceptanceItem(
            "group_contacts",
            bool(groups),
            f"groups={len(groups)}" if groups else "未发现群联系人",
        ),
    ]


def _record_acceptance(
    name: str,
    records: list[MessageRecord],
    *,
    direction: set[str],
    message_type: str,
    ok_only: bool = False,
) -> AcceptanceItem:
    matching = [
        record
        for record in records
        if record.direction in direction and record.message_type == message_type and (not ok_only or record.status == "ok")
        and record.source != "acceptance"
    ]
    if not matching:
        state = "成功发送" if ok_only else "接收"
        return AcceptanceItem(name, False, f"未发现 {message_type} {state}消息记录")
    latest = matching[-1]
    return AcceptanceItem(
        name,
        True,
        f"{latest.timestamp.isoformat(timespec='seconds')} {latest.direction} {latest.target}/{latest.sender}: {latest.text or latest.detail}",
    )


def _check_plugin_loop() -> tuple[bool, str]:
    sent: list[str] = []

    def send(target: str, text: str, message_type: str):
        sent.append(text)
        return SendResult(ok=True, detail=f"acceptance loop {message_type}:{target}")

    ctx = PluginContext(send_fn=send)
    loader = PluginLoader(PROJECT_ROOT / "xiami_plugins", ctx)
    plugins = loader.load_all()
    event = XiamiMessage(message_type="private", sender="tester", target="xiami", text="/echo acceptance")
    loader.dispatch_message(event)
    ok = "acceptance" in sent
    state_ok, state_detail = _check_plugin_state_store(loader)
    plugin_names = ", ".join(_plugin_summary(plugin) for plugin in plugins) if plugins else "未加载插件"
    return ok and bool(plugins) and state_ok, f"plugins={plugin_names}; sent={sent}; state={state_detail}"


def _check_plugin_state_store(loader: PluginLoader) -> tuple[bool, str]:
    if not loader.plugins:
        return False, "未发现插件"
    plugin_id = loader.plugins[0].id
    original = loader.state_store.load()
    original_value = original.get(plugin_id, True)
    try:
        loader.state_store.set_enabled(plugin_id, False)
        disabled = not loader.state_store.is_enabled(plugin_id)
        loader.state_store.set_enabled(plugin_id, True)
        enabled = loader.state_store.is_enabled(plugin_id)
    finally:
        restored = dict(original)
        restored[plugin_id] = original_value
        loader.state_store.save(restored)
    return disabled and enabled, f"{loader.state_store.path}"


def _plugin_summary(plugin) -> str:
    version = f" v{plugin.version}" if plugin.version else ""
    return f"{plugin.name}{version}"
