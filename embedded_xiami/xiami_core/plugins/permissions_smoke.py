from __future__ import annotations

from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = Path.cwd() / "xiami_plugins" / "permissions"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "permissions"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"owners":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if not plugins or plugins[0].error:
            raise RuntimeError(f"permissions plugin load failed: {plugins}")
        enable_loaded_plugins_for_groups(ctx, plugins)

        loader.dispatch_message(XiamiMessage(message_type="group", sender="99999", target="20001", text="加管理员 10002"))
        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="加全局管理员 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10002", target="20001", text="加管理员 10003"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10003", target="20001", text="管理员列表"))

        texts = [item[1] for item in sent]
        if texts[0] != "权限不足，需要管理员。":
            raise RuntimeError(f"non-admin was not denied: {texts}")
        if "已添加全局管理员：1 个。" not in texts:
            raise RuntimeError(f"owner could not add global admin: {texts}")
        if "已添加本群管理员：1 个。" not in texts:
            raise RuntimeError(f"global admin could not add group admin: {texts}")
        if not any("10001" in text and "10002" in text and "10003" in text for text in texts):
            raise RuntimeError(f"admin summary missing ids: {texts}")

    print("permissions plugin smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
