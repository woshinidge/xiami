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
        if action == "get_login_info":
            return FakeResponse(data={"user_id": 313420054, "nickname": "XiamiBot"})
        if action == "get_status":
            return FakeResponse(data={"online": True})
        if action == "get_version_info":
            return FakeResponse(data={"app_name": "NapCat"})
        if action == "get_friend_list":
            return FakeResponse(data=[{"user_id": 10002, "nickname": "Tester"}])
        if action == "get_group_list":
            return FakeResponse(data=[{"group_id": 20001, "group_name": "Xiami测试群", "member_count": 12}])
        if action == "get_group_info":
            return FakeResponse(data={"group_id": 20001, "group_name": "Xiami测试群", "member_count": 12, "max_member_count": 500})
        if action == "get_group_member_info":
            return FakeResponse(data={"group_id": 20001, "user_id": 10002, "nickname": "Tester", "card": "测试员", "role": "member"})
        if action == "get_group_member_list":
            return FakeResponse(
                data=[
                    {"group_id": 20001, "user_id": 10001, "nickname": "Admin", "card": "管理员", "role": "owner"},
                    {"group_id": 20001, "user_id": 10002, "nickname": "Tester", "card": "测试员", "role": "member"},
                ]
            )
        if action == "get_stranger_info":
            return FakeResponse(data={"user_id": 10002, "nickname": "Tester", "sex": "unknown", "age": 18})
        if action == "send_like":
            return FakeResponse(data={})
        if action == "delete_msg":
            return FakeResponse(data={})
        if action == "send_poke":
            return FakeResponse(data={})
        if action == "set_group_special_title":
            return FakeResponse(data={})
        if action == "set_essence_msg":
            return FakeResponse(data={})
        if action == "delete_essence_msg":
            return FakeResponse(data={})
        if action == "_send_group_notice":
            return FakeResponse(data={})
        if action == "_get_group_notice":
            return FakeResponse(
                data=[
                    {"title": "维护通知", "sender_id": 10001},
                    {"content": "今晚 22 点更新", "user_id": 10002},
                ]
            )
        if action == "get_group_honor_info":
            return FakeResponse(
                data={
                    "current_talkative": {"user_id": 10002, "nickname": "Tester"},
                    "talkative_list": [{"user_id": 10002, "nickname": "Tester"}],
                }
            )
        return FakeResponse(ok=False, message=f"unexpected action: {action}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = Path.cwd() / "xiami_plugins" / "onebot_tools"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "onebot_tools"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"]}', encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"), onebot_call_fn=onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if not plugins or plugins[0].error:
            raise RuntimeError(f"onebot_tools plugin load failed: {plugins}")

        loader.dispatch_message(_group("99999", "群信息"))
        loader.dispatch_message(_group("10001", "机器人信息"))
        loader.dispatch_message(_group("10001", "好友列表 1"))
        loader.dispatch_message(_group("10001", "群列表 1"))
        loader.dispatch_message(_group("10001", "群信息"))
        loader.dispatch_message(_group("10001", "查成员 10002"))
        loader.dispatch_message(_group("10001", "群成员列表 2"))
        loader.dispatch_message(_group("10001", "设置群头衔 10002 星标 3600"))
        loader.dispatch_message(_group("10001", "清除群头衔 10002"))
        loader.dispatch_message(_group("10001", "QQ资料 10002"))
        loader.dispatch_message(_group("10001", "赞 10002 3"))
        loader.dispatch_message(_group("10001", "撤回消息 12345"))
        loader.dispatch_message(_group("10001", "戳一戳 10002"))
        loader.dispatch_message(_group("10001", "设精华 12345"))
        loader.dispatch_message(_group("10001", "删精华 12345"))
        loader.dispatch_message(_group("10001", "群公告 维护通知"))
        loader.dispatch_message(_group("10001", "群公告列表"))
        loader.dispatch_message(_group("10001", "群荣誉"))

    expected_calls = [
        ("get_login_info", {}),
        ("get_status", {}),
        ("get_version_info", {}),
        ("get_friend_list", {}),
        ("get_group_list", {}),
            ("get_group_info", {"group_id": 20001, "no_cache": True}),
            ("get_group_member_info", {"group_id": 20001, "user_id": 10002, "no_cache": True}),
            ("get_group_member_list", {"group_id": 20001}),
            ("set_group_special_title", {"group_id": 20001, "user_id": 10002, "special_title": "星标", "duration": 3600}),
            ("set_group_special_title", {"group_id": 20001, "user_id": 10002, "special_title": "", "duration": -1}),
            ("get_stranger_info", {"user_id": 10002, "no_cache": False}),
        ("send_like", {"user_id": 10002, "times": 3}),
        ("delete_msg", {"message_id": 12345}),
        ("send_poke", {"user_id": 10002, "group_id": 20001}),
            ("set_essence_msg", {"message_id": 12345}),
            ("delete_essence_msg", {"message_id": 12345}),
            ("_send_group_notice", {"group_id": 20001, "content": "维护通知", "image": ""}),
            ("_get_group_notice", {"group_id": 20001}),
            ("get_group_honor_info", {"group_id": 20001, "type": "all"}),
        ]
    if calls != expected_calls:
        raise AssertionError(calls)

    texts = [item[1] for item in sent]
    if "权限不足，需要管理员。" not in texts:
        raise AssertionError(texts)
    if not any("机器人信息：XiamiBot(313420054)" in item and "实现：NapCat" in item for item in texts):
        raise AssertionError(texts)
    if not any("好友列表：共 1 个" in item and "Tester(10002)" in item for item in texts):
        raise AssertionError(texts)
    if not any("群列表：共 1 个" in item and "Xiami测试群(20001)" in item for item in texts):
        raise AssertionError(texts)
    if not any("群信息：Xiami测试群(20001)" in item and "成员：12/500" in item for item in texts):
        raise AssertionError(texts)
    if not any("成员信息：测试员(10002)" in item and "角色：member" in item for item in texts):
        raise AssertionError(texts)
        if not any("群成员列表：共 2 人" in item and "管理员(10001)" in item and "测试员(10002)" in item for item in texts):
            raise AssertionError(texts)
        if not any("设置群头衔成功：10002 -> 星标" in item for item in texts):
            raise AssertionError(texts)
        if not any("清除群头衔成功：10002" in item for item in texts):
            raise AssertionError(texts)
        if not any("QQ资料：Tester(10002)" in item and "年龄：18" in item for item in texts):
            raise AssertionError(texts)
    if not any("点赞成功：10002 x3" in item for item in texts):
        raise AssertionError(texts)
    if not any("撤回成功：12345" in item for item in texts):
        raise AssertionError(texts)
    if not any("戳一戳成功：10002" in item for item in texts):
        raise AssertionError(texts)
    if not any("设置精华成功：12345" in item for item in texts):
        raise AssertionError(texts)
    if not any("删除精华成功：12345" in item for item in texts):
        raise AssertionError(texts)
    if "群公告已发送。" not in texts:
        raise AssertionError(texts)
        if not any("群公告列表：" in item and "维护通知" in item and "今晚 22 点更新" in item for item in texts):
            raise AssertionError(texts)
        if not any("群荣誉：当前龙王 Tester(10002)" in item for item in texts):
            raise AssertionError(texts)

    print("onebot_tools_smoke ok")
    return 0


def _group(sender: str, text: str) -> XiamiMessage:
    return XiamiMessage(message_type="group", sender=sender, target="20001", text=text)


if __name__ == "__main__":
    raise SystemExit(main())
