from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
from typing import Any

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups
from xiami_core.plugins.state import PluginStateStore


@dataclass(frozen=True)
class FakeResponse:
    ok: bool = True
    data: Any = None
    message: str = ""


def main() -> int:
    sent: list[tuple[str, str, str]] = []
    calls: list[tuple[str, dict[str, object]]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    def onebot_call(action: str, params: dict[str, object]) -> FakeResponse:
        calls.append((action, params))
        if action == "get_group_member_list":
            return FakeResponse(
                data=[
                    {"user_id": 10002, "nickname": "black-a"},
                    {"user_id": 10003, "nickname": "normal"},
                    {"user_id": 10004, "nickname": "black-b"},
                ]
            )
        return FakeResponse()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = Path.cwd() / "xiami_plugins" / "member_guard"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "member_guard"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"), onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"member_guard plugin load failed: {plugins}")

        loader.dispatch_message(_group("10001", "加黑名单 10002 10004"))
        loader.dispatch_message(_group("10001", "清理黑名单"))

    expected_calls = [
        ("get_group_member_list", {"group_id": 20001}),
        ("set_group_kick", {"group_id": 20001, "user_id": 10002, "reject_add_request": False}),
        ("set_group_kick", {"group_id": 20001, "user_id": 10004, "reject_add_request": False}),
    ]
    if calls != expected_calls:
        raise AssertionError(calls)

    texts = [item[1] for item in sent]
    if not any("已添加本群黑名单：2 个" in item for item in texts):
        raise AssertionError(texts)
    if not any("清理黑名单完成：命中 2 人，成功移出 2 人，失败 0 人" in item for item in texts):
        raise AssertionError(texts)

    print("member_guard_sweep_smoke ok")
    return 0


def _group(sender: str, text: str) -> XiamiMessage:
    return XiamiMessage(message_type="group", sender=sender, target="20001", text=text)


if __name__ == "__main__":
    raise SystemExit(main())
