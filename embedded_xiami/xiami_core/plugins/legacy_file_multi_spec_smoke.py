from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        sent: list[tuple[str, str, str]] = []
        _write_multi_spec_plugin(root)

        def send(target: str, text: str, message_type: str) -> SendResult:
            sent.append((target, text, message_type))
            return SendResult(ok=True, detail="ok")

        loader = PluginLoader(root, PluginContext(send_fn=send), PluginStateStore(root / "plugins.json"))
        plugins = loader.load_all()
        loaded = {plugin.id: plugin for plugin in plugins}
        if set(loaded) != {"multi_private"}:
            raise RuntimeError(f"multi spec legacy file not loaded as primary plugin: {plugins!r}")
        plugin = loaded["multi_private"]
        if plugin.error:
            raise RuntimeError(f"multi spec legacy file has error: {plugin.error}")
        if "旧文件hook:message.private" not in plugin.commands or "旧文件hook:message.group" not in plugin.commands:
            raise RuntimeError(f"multi spec hooks missing from commands: {plugin.commands}")
        if "legacy-admin-hook" not in plugin.capabilities or "legacy-admin-path" not in plugin.capabilities:
            raise RuntimeError(f"multi spec admin capabilities missing: {plugin.capabilities}")
        if "legacy-service:MultiGroupService" not in plugin.capabilities:
            raise RuntimeError(f"multi spec service capability missing: {plugin.capabilities}")
        enable_loaded_plugins_for_groups(loader.context, plugins)

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="hello"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10002", target="20001", text="hi"))

        expected_sent = [("10001", "private:hello", "private"), ("20001", "group:hi", "group")]
        if sent != expected_sent:
            raise RuntimeError(f"multi spec dispatch failed: {sent!r}")

        diagnostics = loader.diagnostics()
        diag = diagnostics[0]
        if diag["message_handled_count"] != 2 or diag["message_unhandled_count"] != 0:
            raise RuntimeError(f"multi spec counters invalid: {diag}")
        hits = diag["matcher_hit_count"]
        if hits.get("legacy-file:message.private") != 1 or hits.get("legacy-file:message.group") != 1:
            raise RuntimeError(f"multi spec matcher hits invalid: {diag}")
        if not diag["admin_schema"]:
            raise RuntimeError(f"multi spec admin schema missing: {diag}")
    return 0


def _write_multi_spec_plugin(root: Path) -> None:
    (root / "multi.py").write_text(
        "\n".join(
            [
                "class Spec:",
                "    def __init__(self, key, name, hooks, services=(), admin_path=''):",
                "        self.key = key",
                "        self.name = name",
                "        self.description = ''",
                "        self.hooks = hooks",
                "        self.services = services",
                "        self.admin_path = admin_path",
                "        self.priority = 100",
                "        self.block = False",
                "",
                "def private_handler(context):",
                "    return 'private:' + context.message",
                "",
                "def group_handler(context):",
                "    return 'group:' + context.message",
                "",
                "def register(manager):",
                "    manager.add_plugin(Spec('multi_private', 'Multi Private', ('message.private',)))",
                "    manager.register_handler('multi_private', private_handler)",
                "    manager.add_plugin(Spec('multi_group', 'Multi Group', ('message.group', 'admin'), ('MultiGroupService',), '/admin/multi_group'))",
                "    manager.register_handler('multi_group', group_handler)",
                "",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
