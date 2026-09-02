from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups
from xiami_core.plugins.state import PluginStateStore


@dataclass(frozen=True)
class FakeResponse:
    ok: bool = True
    message: str = ""


def main() -> int:
    sent: list[tuple[str, str, str]] = []
    calls: list[tuple[str, dict[str, object]]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    def onebot_call(action: str, params: dict[str, object]) -> FakeResponse:
        calls.append((action, params))
        return FakeResponse()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = Path.cwd() / "xiami_plugins" / "moderation"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "moderation"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"), onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"moderation plugin load failed: {plugins}")

        loader.dispatch_message(XiamiMessage(message_type="group", sender="99999", target="20001", text="禁言 10002 60"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="群管帮助"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="禁言 10002 2分钟"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="解禁 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="踢 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="踢黑 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="全员禁言"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="解除全员禁言"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="改名片 10002 测试名片"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="改头衔 10002 测试头衔"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="清头衔 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="设管理员 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="取消管理员 10002"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="改群名 新群名"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="发公告 测试公告"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text="撤回消息 12345"))

        texts = [item[1] for item in sent]
        if texts[0] != "权限不足，需要管理员。":
            raise RuntimeError(f"non-admin not denied: {texts}")
        expected_calls = [
            ("set_group_ban", {"group_id": 20001, "user_id": 10002, "duration": 120}),
            ("set_group_ban", {"group_id": 20001, "user_id": 10002, "duration": 0}),
            ("set_group_kick", {"group_id": 20001, "user_id": 10002, "reject_add_request": False}),
            ("set_group_kick", {"group_id": 20001, "user_id": 10002, "reject_add_request": True}),
            ("set_group_whole_ban", {"group_id": 20001, "enable": True}),
            ("set_group_whole_ban", {"group_id": 20001, "enable": False}),
            ("set_group_card", {"group_id": 20001, "user_id": 10002, "card": "测试名片"}),
            ("set_group_special_title", {"group_id": 20001, "user_id": 10002, "special_title": "测试头衔", "duration": -1}),
            ("set_group_special_title", {"group_id": 20001, "user_id": 10002, "special_title": "", "duration": -1}),
            ("set_group_admin", {"group_id": 20001, "user_id": 10002, "enable": True}),
            ("set_group_admin", {"group_id": 20001, "user_id": 10002, "enable": False}),
            ("set_group_name", {"group_id": 20001, "group_name": "新群名"}),
            ("_send_group_notice", {"group_id": 20001, "content": "测试公告", "image": ""}),
            ("delete_msg", {"message_id": 12345}),
        ]
        if calls != expected_calls:
            raise RuntimeError(f"wrong onebot calls: {calls}")
        if "群管命令：" not in texts[1]:
            raise RuntimeError(f"moderation help missing: {texts}")
        if "已禁言 10002 120 秒。" not in texts or "已解除 10002 的禁言。" not in texts or "已踢出 10002。" not in texts:
            raise RuntimeError(f"moderation replies missing: {texts}")
        for expected_text in (
            "已踢出并拒绝 10002 再次申请。",
            "已开启全员禁言。",
            "已关闭全员禁言。",
            "已设置 10002 的群名片：测试名片",
            "已设置 10002 的专属头衔：测试头衔",
            "已清除 10002 的专属头衔。",
            "已设置 10002 为群管理员。",
            "已取消 10002 的群管理员。",
            "已设置群名：新群名",
            "群公告已发送。",
            "已撤回消息：12345",
        ):
            if expected_text not in texts:
                raise RuntimeError(f"moderation reply missing {expected_text!r}: {texts}")

    print("moderation plugin smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
