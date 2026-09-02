from __future__ import annotations

import time
from dataclasses import dataclass

from xiami_core.events import EventBus
from xiami_core.kernels.manager import KernelManager
from xiami_core.kernels.napcat_config import ensure_napcat_onebot_config, inspect_napcat_onebot_config
from xiami_core.models import AccountStatus
from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.onebot.gateway import OneBotEventGateway
from xiami_core.storage.config import load_config


@dataclass(frozen=True)
class ProbeItem:
    name: str
    ok: bool
    detail: str


def run_real_login_probe(account: str = "", start: bool = False, timeout: int = 45) -> list[ProbeItem]:
    config = load_config()
    real_kernel = config.kernel.kind.lower() != "mock"
    items = [
        ProbeItem("real_kernel_selected", real_kernel, f"当前内核：{config.kernel.kind}"),
        ProbeItem("kernel_executable", bool(config.kernel.executable), config.kernel.executable or "未配置启动程序"),
        ProbeItem("onebot_http", bool(config.kernel.http_url), config.kernel.http_url or "未配置 OneBot HTTP"),
    ]
    if not real_kernel:
        items.append(ProbeItem("real_login", False, "Mock 只能验证 UI/插件，不能作为真实 QQ 登录通过"))
        return items

    bus = EventBus()
    gateway: OneBotEventGateway | None = None
    event_url = ""
    if start:
        try:
            gateway = OneBotEventGateway(bus)
            event_url = gateway.start()
            items.append(ProbeItem("event_gateway", True, event_url))
        except Exception as exc:
            items.append(ProbeItem("event_gateway", False, f"启动失败：{exc}"))

    if config.kernel.kind.lower() == "napcat":
        if start and event_url:
            try:
                ensure = ensure_napcat_onebot_config(config.kernel, event_url)
                if ensure.detail:
                    items.append(ProbeItem("napcat_config_ensure", ensure.after.ok, ensure.detail))
            except Exception as exc:
                items.append(ProbeItem("napcat_config_ensure", False, f"配置失败：{exc}"))
        onebot_config = inspect_napcat_onebot_config(config.kernel)
        items.append(
            ProbeItem(
                "napcat_onebot_config",
                onebot_config.ok,
                f"HTTP={onebot_config.http_enabled} EVENT={onebot_config.event_enabled} "
                f"files={';'.join(str(path) for path in onebot_config.files) if onebot_config.files else '未发现'}",
            )
        )

    manager = KernelManager(bus)
    status = manager.prepare()
    if start and status.state != "error":
        status = manager.start_login(account)
    elif status.state != "error":
        status = manager.status()

    deadline = time.monotonic() + max(1, timeout)
    while start and status.state != "error" and time.monotonic() < deadline:
        status = manager.status()
        if status.state == "online":
            break
        time.sleep(1)

    items.append(ProbeItem("real_login", status.state == "online", _format_status(status, start=start)))
    client = OneBotHttpClient(config.kernel.http_url, config.kernel.access_token, timeout=2)
    response = client.get_login_info()
    items.append(ProbeItem("onebot_login_info", response.ok, response.message or str(response.data)))
    if gateway:
        gateway.stop()
    return items


def format_probe(items: list[ProbeItem]) -> str:
    ready = sum(1 for item in items if item.ok)
    lines = [f"真实登录探针：{ready}/{len(items)}"]
    for item in items:
        prefix = "[OK]" if item.ok else "[待处理]"
        lines.append(f"{prefix} {item.name}: {item.detail}")
    return "\n".join(lines)


def _format_status(status: AccountStatus, start: bool) -> str:
    prefix = "" if start else "未启动内核，仅探测当前连接；"
    qr = f"；二维码线索：{status.qr_hint}" if status.qr_hint else ""
    return f"{prefix}状态：{status.state}；{status.detail}{qr}"
