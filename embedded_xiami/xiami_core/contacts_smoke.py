from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.contacts import ContactStore, sync_contacts
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path == "/get_friend_list":
            body = {
                "status": "ok",
                "retcode": 0,
                "data": [{"user_id": 10001, "nickname": "好友A", "remark": "备注A"}],
            }
        elif self.path == "/get_group_list":
            body = {
                "status": "ok",
                "retcode": 0,
                "data": [{"group_id": 20001, "group_name": "群A"}],
            }
        else:
            body = {"status": "failed", "retcode": 1, "message": "unknown"}
        payload = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        save_config(AppConfig(kernel=KernelConfig(kind="NapCat", http_url=f"http://127.0.0.1:{server.server_port}")))
        result = sync_contacts()
        if not result.ok or len(result.contacts) != 2:
            raise RuntimeError(f"contact sync failed: {result}")
        cached = ContactStore().load()
        if len(cached) != 2 or {contact.kind for contact in cached} != {"friend", "group"}:
            raise RuntimeError(f"contact cache failed: {cached}")
    finally:
        server.shutdown()
    print("contacts smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
