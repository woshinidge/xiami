from __future__ import annotations

from typing import Any

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.legacy import legacy_bot


def main() -> int:
    calls: list[tuple[str, dict[str, Any]]] = []

    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    def onebot_call(action: str, params: dict[str, Any]) -> dict[str, Any]:
        calls.append((action, params))
        return {"status": "ok", "retcode": 0, "data": {"action": action}}

    ctx = PluginContext(send_fn=send, onebot_call_fn=onebot_call)
    ctx.get_group_root_files("20001")
    ctx.get_group_files_by_folder("20001", "/docs")
    ctx.get_group_file_url("20001", "file-1", "102")
    ctx.create_group_file_folder("20001", "reports")
    ctx.create_group_file_folder("20001", "reports", parent_id="/root")
    ctx.delete_group_folder("20001", "/old")
    ctx.delete_group_file("20001", "file-1", "102")

    bot = legacy_bot(ctx)
    bot.get_group_root_files("20002")
    bot.get_group_files_by_folder("20002", "/legacy")
    bot.get_group_file_url("20002", "legacy-file", 103)
    bot.create_group_file_folder("20002", "legacy", parent_id="/parent")
    bot.delete_group_folder("20002", "/legacy-old")
    bot.delete_group_file("20002", "legacy-file", 103)

    expected = [
        ("get_group_root_files", {"group_id": 20001}),
        ("get_group_files_by_folder", {"group_id": 20001, "folder_id": "/docs"}),
        ("get_group_file_url", {"group_id": 20001, "file_id": "file-1", "busid": 102}),
        ("create_group_file_folder", {"group_id": 20001, "folder_name": "reports", "parent_id": "/"}),
        ("create_group_file_folder", {"group_id": 20001, "folder_name": "reports", "parent_id": "/root"}),
        ("delete_group_folder", {"group_id": 20001, "folder_id": "/old"}),
        ("delete_group_file", {"group_id": 20001, "file_id": "file-1", "busid": 102}),
        ("get_group_root_files", {"group_id": 20002}),
        ("get_group_files_by_folder", {"group_id": 20002, "folder_id": "/legacy"}),
        ("get_group_file_url", {"group_id": 20002, "file_id": "legacy-file", "busid": 103}),
        ("create_group_file_folder", {"group_id": 20002, "folder_name": "legacy", "parent_id": "/parent"}),
        ("delete_group_folder", {"group_id": 20002, "folder_id": "/legacy-old"}),
        ("delete_group_file", {"group_id": 20002, "file_id": "legacy-file", "busid": 103}),
    ]
    if calls != expected:
        raise RuntimeError(f"wrong group file calls: {calls}")

    print("group files smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
