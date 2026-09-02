from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from xiami_core.migration_inventory import inspect_plugins
from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups
from xiami_core.plugins.state import PluginStateStore


COMMAND_CASES = {
    "机器人信息": "机器人信息",
    "登录信息": "登录信息",
    "OneBot状态": "OneBot状态",
    "好友列表": "好友列表",
    "列好友": "列好友",
    "群列表": "群列表",
    "列群": "列群",
    "群信息": "群信息",
    "查询群信息": "查询群信息 20001",
    "查成员": "查成员 10002",
    "成员信息": "成员信息 10002",
    "查询成员": "查询成员 10002",
    "群成员列表": "群成员列表 2",
    "成员列表": "成员列表 2",
    "群成员": "群成员 2",
    "设置群头衔": "设置群头衔 10002 星标",
    "设头衔": "设头衔 10002 星标",
    "设置头衔": "设置头衔 10002 星标",
    "清除群头衔": "清除群头衔 10002",
    "清头衔": "清头衔 10002",
    "删除头衔": "删除头衔 10002",
    "QQ资料": "QQ资料 10002",
    "查QQ": "查QQ 10002",
    "陌生人信息": "陌生人信息 10002",
    "赞": "赞 10002 3",
    "点赞": "点赞 10002 3",
    "撤回消息": "撤回消息 12345",
    "撤回": "撤回 12345",
    "戳一戳": "戳一戳 10002",
    "戳": "戳 10002",
    "设精华": "设精华 12345",
    "设置精华": "设置精华 12345",
    "删精华": "删精华 12345",
    "删除精华": "删除精华 12345",
    "群公告": "群公告 测试公告",
    "发群公告": "发群公告 测试公告",
    "群公告列表": "群公告列表",
    "查群公告": "查群公告",
    "群公告记录": "群公告记录",
    "群荣誉": "群荣誉 talkative",
    "群荣耀": "群荣耀 talkative",
}


@dataclass(frozen=True)
class FakeResponse:
    ok: bool = True
    data: Any = None
    message: str = ""


def _onebot_call(action: str, params: dict[str, object]) -> FakeResponse:
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
        return FakeResponse(data={"user_id": 10002, "nickname": "测试员", "card": "", "role": "member"})
    if action == "get_group_member_list":
        return FakeResponse(
            data=[
                {"user_id": 10001, "nickname": "管理员", "card": "", "role": "admin"},
                {"user_id": 10002, "nickname": "测试员", "card": "", "role": "member"},
            ]
        )
    if action == "get_stranger_info":
        return FakeResponse(data={"user_id": 10002, "nickname": "Tester", "age": 18, "sex": "unknown"})
    if action == "get_group_notice":
        return FakeResponse(data=[{"sender_id": 10001, "publish_time": 0, "message": {"text": "测试公告"}}])
    if action == "get_group_honor_info":
        return FakeResponse(data={"current_talkative": {"user_id": 10002, "nickname": "Tester"}, "talkative_list": []})
    if action in {
        "set_group_special_title",
        "send_like",
        "delete_msg",
        "group_poke",
        "set_essence_msg",
        "delete_essence_msg",
        "_send_group_notice",
        "set_group_notice",
    }:
        return FakeResponse(data={"ok": True})
    return FakeResponse(ok=False, message=f"unexpected action: {action}")


def main() -> int:
    inventory = {item.plugin_id: item for item in inspect_plugins(Path.cwd() / "xiami_plugins")}
    expected_commands = inventory["onebot_tools"].commands
    missing_cases = sorted(expected_commands - set(COMMAND_CASES))
    extra_cases = sorted(set(COMMAND_CASES) - expected_commands)
    if missing_cases or extra_cases:
        raise RuntimeError(f"onebot_tools alias matrix mismatch: missing={missing_cases}, extra={extra_cases}")

    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        shutil.copytree(Path.cwd() / "xiami_plugins" / "onebot_tools", plugin_root / "onebot_tools")
        (plugin_root / "onebot_tools" / "plugin_config.json").write_text('{"admins":["10001"]}', encoding="utf-8")
        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"), onebot_call_fn=_onebot_call)
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        enable_loaded_plugins_for_groups(ctx, plugins)
        if len(plugins) != 1 or plugins[0].error:
            raise RuntimeError(f"onebot_tools plugin load failed: {plugins}")

        for text in COMMAND_CASES.values():
            loader.dispatch_message(XiamiMessage(message_type="group", sender="10001", target="20001", text=text))

        diag = loader.diagnostics()[0]
        if diag["message_handled_count"] != len(COMMAND_CASES) or diag["error_count"]:
            raise RuntimeError(f"onebot_tools alias matrix diagnostic failed: {diag!r}")
        if len(sent) < len(COMMAND_CASES):
            raise RuntimeError(f"onebot_tools alias matrix replies failed: sent={len(sent)}, expected_at_least={len(COMMAND_CASES)}")

    print("onebot_tools alias matrix smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
