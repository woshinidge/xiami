from __future__ import annotations

from pathlib import Path

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.events import EventBus
from xiami_core.kernels.manager import KernelManager
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.storage.config import KernelConfig


def main() -> int:
    bus = EventBus()
    manager = KernelManager(bus)
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str):
        sent.append((target, text, message_type))
        return manager.send_message(target, text, message_type)

    ctx = PluginContext(send_fn=send)
    loader = PluginLoader(Path.cwd() / "xiami_plugins", ctx)
    plugins = loader.load_all()
    if not any(plugin.name == "Echo" for plugin in plugins):
        raise RuntimeError("Echo plugin not loaded")
    manager.start_login("123456")
    event = manager.simulate_incoming("/echo ping", sender="tester")
    loader.dispatch_message(event)
    if ("tester", "ping", "private") not in sent:
        raise RuntimeError(f"Echo reply missing: {sent}")
    group_event = type(event)(message_type="group", sender="member", target="20001", text="/echo group-ping")
    loader.dispatch_message(group_event)
    if ("20001", "group-ping", "group") not in sent:
        raise RuntimeError(f"Echo group reply missing: {sent}")
    status = manager.set_kernel(KernelConfig(kind="Lagrange"))
    if status.state != "error":
        raise RuntimeError(f"Lagrange without executable should explicit error: {status}")
    print("xiami_core v1 smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
