from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from xiami_core.onebot.client import OneBotHttpClient


class Handler(BaseHTTPRequestHandler):
    calls: list[tuple[str, dict[str, object]]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
        Handler.calls.append((self.path, data))
        raw = b'{"status":"ok","retcode":0,"data":{}}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    Handler.calls.clear()
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = OneBotHttpClient(f"http://127.0.0.1:{server.server_port}")
        client.get_login_info()
        client.get_status()
        client.get_version()
        client.get_friend_list()
        client.get_group_list()
        client.get_group_member_list("20001")
        client.get_group_info("20001")
        client.get_group_member_info("20001", "10001")
        client.get_stranger_info("10001", no_cache=False)
        client.get_msg("34567")
        client.send_like("10001", times=3)
        client.send_poke("10001", group_id="20001")
        client.send_private_image("10001", "file:///tmp/a.png")
        client.send_group_image("20001", "file:///tmp/a.png")
        client.upload_group_file("20001", "C:/tmp/report.txt")
        client.get_group_root_files("20001")
        client.get_group_files_by_folder("20001", "/docs")
        client.get_group_file_url("20001", "file-1", "102")
        client.create_group_file_folder("20001", "reports")
        client.delete_group_folder("20001", "/old")
        client.delete_group_file("20001", "file-1", "102")
        client.send_group_forward_msg(
            "20001",
            [
                {"type": "node", "data": {"name": "A", "uin": "10001", "content": "hello"}},
                ("B", "10002", "tuple hello"),
            ],
        )
        client.send_private_forward_msg("10001", "plain hello")
        client.get_image("abc.png")
        client.get_record("abc.amr", out_format="mp3")
        client.set_group_ban("20001", "10001", 60)
        client.set_group_whole_ban("20001", True)
        client.set_group_kick("20001", "10001", reject_add_request=True)
        client.set_group_admin("20001", "10001", enable=True)
        client.set_group_card("20001", "10001", "新名片")
        client.set_group_name("20001", "新群名")
        client.set_group_special_title("20001", "10001", "头衔", duration=3600)
        client.set_group_leave("20001")
        client.set_group_notice("20001", "公告内容")
        client.get_group_notice("20001")
        client.get_group_honor_info("20001")
        client.set_essence_msg("123456")
        client.delete_essence_msg("123456")
        client.set_group_add_request("flag-a", "add", False, "拒绝原因")
        client.set_friend_add_request("friend-flag", True, "好友备注")
        client.delete_msg("123456")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)

    expected = [
        ("/get_login_info", {}),
        ("/get_status", {}),
        ("/get_version_info", {}),
        ("/get_friend_list", {}),
        ("/get_group_list", {}),
        ("/get_group_member_list", {"group_id": 20001}),
        ("/get_group_info", {"group_id": 20001, "no_cache": True}),
        ("/get_group_member_info", {"group_id": 20001, "user_id": 10001, "no_cache": True}),
        ("/get_stranger_info", {"user_id": 10001, "no_cache": False}),
        ("/get_msg", {"message_id": 34567}),
        ("/send_like", {"user_id": 10001, "times": 3}),
        ("/send_poke", {"user_id": 10001, "group_id": 20001}),
            ("/send_private_msg", {"user_id": 10001, "message": "[CQ:image,file=file:///tmp/a.png]"}),
            ("/send_group_msg", {"group_id": 20001, "message": "[CQ:image,file=file:///tmp/a.png]"}),
            ("/upload_group_file", {"group_id": 20001, "file": "C:/tmp/report.txt", "name": "report.txt"}),
            ("/get_group_root_files", {"group_id": 20001}),
            ("/get_group_files_by_folder", {"group_id": 20001, "folder_id": "/docs"}),
            ("/get_group_file_url", {"group_id": 20001, "file_id": "file-1", "busid": 102}),
            ("/create_group_file_folder", {"group_id": 20001, "folder_name": "reports", "parent_id": "/"}),
            ("/delete_group_folder", {"group_id": 20001, "folder_id": "/old"}),
            ("/delete_group_file", {"group_id": 20001, "file_id": "file-1", "busid": 102}),
            (
                "/send_group_forward_msg",
                {
                    "group_id": 20001,
                    "messages": [
                        {"type": "node", "data": {"name": "A", "uin": "10001", "content": "hello"}},
                        {"type": "node", "data": {"name": "B", "uin": "10002", "content": "tuple hello"}},
                    ],
                },
            ),
            (
                "/send_private_forward_msg",
                {"user_id": 10001, "messages": [{"type": "node", "data": {"name": "Xiami", "uin": "0", "content": "plain hello"}}]},
            ),
        ("/get_image", {"file": "abc.png"}),
        ("/get_record", {"file": "abc.amr", "out_format": "mp3"}),
        ("/set_group_ban", {"group_id": 20001, "user_id": 10001, "duration": 60}),
        ("/set_group_whole_ban", {"group_id": 20001, "enable": True}),
        ("/set_group_kick", {"group_id": 20001, "user_id": 10001, "reject_add_request": True}),
        ("/set_group_admin", {"group_id": 20001, "user_id": 10001, "enable": True}),
        ("/set_group_card", {"group_id": 20001, "user_id": 10001, "card": "新名片"}),
        ("/set_group_name", {"group_id": 20001, "group_name": "新群名"}),
            ("/set_group_special_title", {"group_id": 20001, "user_id": 10001, "special_title": "头衔", "duration": 3600}),
            ("/set_group_leave", {"group_id": 20001, "is_dismiss": False}),
            ("/_send_group_notice", {"group_id": 20001, "content": "公告内容", "image": ""}),
            ("/_get_group_notice", {"group_id": 20001}),
            ("/get_group_honor_info", {"group_id": 20001, "type": "all"}),
        ("/set_essence_msg", {"message_id": 123456}),
        ("/delete_essence_msg", {"message_id": 123456}),
        ("/set_group_add_request", {"flag": "flag-a", "sub_type": "add", "approve": False, "reason": "拒绝原因"}),
        ("/set_friend_add_request", {"flag": "friend-flag", "approve": True, "remark": "好友备注"}),
        ("/delete_msg", {"message_id": 123456}),
    ]
    if Handler.calls != expected:
        raise RuntimeError(f"wrong onebot action payloads: {Handler.calls}")
    print("onebot actions smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
