from __future__ import annotations

from xiami_core.kernels.base import LoginKernel
from xiami_core.models import AccountStatus, SendResult


class MockLoginKernel(LoginKernel):
    name = "Mock Kernel"

    def __init__(self) -> None:
        self._status = AccountStatus(state="offline", detail="未登录")

    def prepare(self) -> AccountStatus:
        self._status = AccountStatus(state="offline", detail="Mock 内核已就绪")
        return self._status

    def start_login(self, account: str = "") -> AccountStatus:
        account = account.strip() or "10000"
        self._status = AccountStatus(state="online", account=account, detail="模拟登录：未连接真实 QQ")
        return self._status

    def stop(self) -> AccountStatus:
        self._status = AccountStatus(state="offline", detail="Mock 内核已停止")
        return self._status

    def status(self) -> AccountStatus:
        return self._status

    def send_message(self, target: str, text: str, message_type: str = "private") -> SendResult:
        if self._status.state != "online":
            return SendResult(ok=False, detail="账号未登录")
        if not target.strip():
            return SendResult(ok=False, detail="缺少发送目标")
        if not text.strip():
            return SendResult(ok=False, detail="缺少消息内容")
        return SendResult(ok=True, detail=f"已发送到 {target}")
