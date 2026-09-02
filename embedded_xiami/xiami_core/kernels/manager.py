from __future__ import annotations

from xiami_core.events import EventBus
from xiami_core.kernels.base import LoginKernel
from xiami_core.kernels.external import LagrangeKernel, NapCatKernel
from xiami_core.kernels.mock import MockLoginKernel
from xiami_core.models import AccountStatus, SendResult, XiamiMessage
from xiami_core.onebot.stats import OneBotActionStats
from xiami_core.storage.config import AppConfig, KernelConfig, load_config, save_config


class KernelManager:
    def __init__(self, event_bus: EventBus | None = None, kernel: LoginKernel | None = None) -> None:
        self.event_bus = event_bus or EventBus()
        self.config = load_config()
        self.kernel = kernel or self._build_kernel(self.config.kernel)

    def set_kernel(self, config: KernelConfig) -> AccountStatus:
        self.config = AppConfig(
            kernel=config,
            probe_private_target=self.config.probe_private_target,
            probe_group_target=self.config.probe_group_target,
        )
        save_config(self.config)
        self.kernel = self._build_kernel(config)
        return self.prepare()

    def prepare(self) -> AccountStatus:
        return self.kernel.prepare()

    def start_login(self, account: str = "") -> AccountStatus:
        return self.kernel.start_login(account)

    def stop(self) -> AccountStatus:
        return self.kernel.stop()

    def status(self) -> AccountStatus:
        return self.kernel.status()

    def send_message(self, target: str, text: str, message_type: str = "private") -> SendResult:
        try:
            return self.kernel.send_message(target, text, message_type)
        except Exception as exc:
            return SendResult(ok=False, detail=f"发送异常：{exc}")

    def action_stats(self) -> OneBotActionStats | None:
        value = getattr(self.kernel, "action_stats", None)
        return value if isinstance(value, OneBotActionStats) else None

    def simulate_incoming(self, text: str, sender: str = "tester") -> XiamiMessage:
        message = self.kernel.simulate_incoming(text=text, sender=sender)
        self.event_bus.publish_message(message)
        return message

    def _build_kernel(self, config: KernelConfig) -> LoginKernel:
        kind = config.kind.lower()
        if kind == "napcat":
            kernel: LoginKernel = NapCatKernel(config)
        elif kind == "lagrange":
            kernel = LagrangeKernel(config)
        else:
            kernel = MockLoginKernel()
        kernel.configure(config)
        return kernel
