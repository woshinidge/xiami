from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def _load_one(plugin_id: str, sent: list[tuple[str, str, str]], root: Path) -> PluginLoader:
    plugin_root = root / "plugins"
    source = Path.cwd() / "xiami_plugins" / plugin_id
    target = plugin_root / plugin_id
    shutil.copytree(source, target)

    def send(target_id: str, text: str, message_type: str) -> SendResult:
        sent.append((target_id, text, message_type))
        return SendResult(ok=True, detail="ok")

    ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
    loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
    plugins = loader.load_all()
    if len(plugins) != 1 or plugins[0].id != plugin_id or plugins[0].error:
        raise RuntimeError(f"{plugin_id} load failed: {plugins}")
    return loader


def _diag(loader: PluginLoader, plugin_id: str) -> dict:
    for item in loader.diagnostics():
        if item["id"] == plugin_id:
            return item
    raise RuntimeError(f"missing diagnostic for {plugin_id}")


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        sent: list[tuple[str, str, str]] = []
        loader = _load_one("echo", sent, Path(temp) / "echo")
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="/echo hello"))
        if sent != [("10001", "hello", "private")]:
            raise RuntimeError(f"echo reply failed: {sent!r}")
        if _diag(loader, "echo")["message_handled_count"] != 1:
            raise RuntimeError(f"echo diagnostic failed: {_diag(loader, 'echo')!r}")

    with tempfile.TemporaryDirectory() as temp:
        sent = []
        loader = _load_one("compat_echo", sent, Path(temp) / "compat")
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="/cecho hello"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="兼容测试"))
        if ("10001", "[compat] hello", "private") not in sent:
            raise RuntimeError(f"compat command reply failed: {sent!r}")
        if ("10001", "兼容层收到关键词", "private") not in sent:
            raise RuntimeError(f"compat keyword reply failed: {sent!r}")
        diag = _diag(loader, "compat_echo")
        if diag["message_handled_count"] != 2 or diag["error_count"]:
            raise RuntimeError(f"compat diagnostic failed: {diag!r}")

    with tempfile.TemporaryDirectory() as temp:
        sent = []
        loader = _load_one("error_history_case", sent, Path(temp) / "error")
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="boom"))
        diag = _diag(loader, "error_history_case")
        if diag["error_count"] != 1 or "boom-boom" not in str(diag["last_error"]):
            raise RuntimeError(f"error history diagnostic failed: {diag!r}")

    print("basic plugins direct smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
