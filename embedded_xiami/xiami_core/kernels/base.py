from __future__ import annotations

from abc import ABC, abstractmethod

from xiami_core.models import AccountStatus, SendResult, XiamiMessage
from xiami_core.storage.config import KernelConfig


class LoginKernel(ABC):
    name: str

    def configure(self, config: KernelConfig) -> None:
        self.config = config

    @abstractmethod
    def prepare(self) -> AccountStatus:
        raise NotImplementedError

    @abstractmethod
    def start_login(self, account: str = "") -> AccountStatus:
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> AccountStatus:
        raise NotImplementedError

    @abstractmethod
    def status(self) -> AccountStatus:
        raise NotImplementedError

    @abstractmethod
    def send_message(self, target: str, text: str, message_type: str = "private") -> SendResult:
        raise NotImplementedError

    def simulate_incoming(self, text: str, sender: str = "tester") -> XiamiMessage:
        return XiamiMessage(message_type="private", sender=sender, target="xiami", text=text)
