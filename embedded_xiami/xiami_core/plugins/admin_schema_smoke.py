from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    with TemporaryDirectory() as temp:
        root = Path(temp)
        plugin_dir = root / "admin_demo"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "PLUGIN_ID = 'admin_demo'",
                    "PLUGIN_NAME = '后台管理样例'",
                    "PLUGIN_CONFIG = {'enabled': True, 'mode': 'auto'}",
                    "PLUGIN_CONFIG_SCHEMA = [",
                    "    {'key': 'enabled', 'label': '启用开关', 'type': 'bool', 'required': True, 'description': '是否启用插件'},",
                    "    {'key': 'token', 'label': '访问令牌', 'type': 'str', 'secret': True},",
                    "    {'key': 'mode', 'label': '运行模式', 'type': 'str', 'choices': ['auto', 'manual']},",
                    "]",
                    "PLUGIN_ADMIN_SCHEMA = [",
                    "    {'id': 'members', 'label': '成员名单', 'type': 'state', 'state_key': 'members', 'commands': ['加成员', '删成员']},",
                    "    {'id': 'enabled', 'label': '开关', 'type': 'config', 'config_key': 'enabled'},",
                    "]",
                    "def on_load(ctx):",
                    "    ctx.set_state('members', {'group:10000:black': ['123', '456']})",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        loader = PluginLoader(root, PluginContext(send_fn=send), PluginStateStore(root / "enabled.json"))
        loader.load_all()
        diagnostic = loader.diagnostics()[0]
        config_schema = diagnostic.get("config_schema") or []
        schema = diagnostic.get("admin_schema") or []
        preview = diagnostic.get("admin_state_preview") or []
        if len(config_schema) != 3 or config_schema[0].get("key") != "enabled":
            raise RuntimeError(f"config schema missing: {diagnostic!r}")
        if not config_schema[0].get("required") or config_schema[0].get("default") is not True:
            raise RuntimeError(f"config schema metadata wrong: {diagnostic!r}")
        if not config_schema[1].get("secret"):
            raise RuntimeError(f"config secret metadata missing: {diagnostic!r}")
        invalid = loader.validate_user_config("admin_demo", {"enabled": "yes", "mode": "bad"})
        if invalid.ok or "启用开关" not in " ".join(invalid.errors) or "运行模式" not in " ".join(invalid.errors):
            raise RuntimeError(f"config validation missing: {invalid!r}")
        valid = loader.validate_user_config("admin_demo", {"enabled": False, "mode": "manual"})
        if not valid.ok:
            raise RuntimeError(f"config validation rejected valid config: {valid!r}")
        if len(schema) != 2 or schema[0].get("state_key") != "members":
            raise RuntimeError(f"admin schema missing: {diagnostic!r}")
        state_row = next((item for item in preview if item.get("state_key") == "members"), None)
        if not state_row or state_row.get("count") != 1 or state_row.get("summary") != "1 项":
            raise RuntimeError(f"state preview missing: {diagnostic!r}")
        config_row = next((item for item in preview if item.get("config_key") == "enabled"), None)
        if not config_row or config_row.get("summary") != "开启":
            raise RuntimeError(f"config preview missing: {diagnostic!r}")
    print("admin schema smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
