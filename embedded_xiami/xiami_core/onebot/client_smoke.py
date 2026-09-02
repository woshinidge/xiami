from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from .client import OneBotHttpClient


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(length)
        if self.path == "/get_login_info":
            body = {"status": "ok", "retcode": 0, "data": {"user_id": 123456, "nickname": "Xiami"}}
        else:
            body = {"status": "ok", "retcode": 0, "data": {"message_id": 1}}
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
        client = OneBotHttpClient(f"http://127.0.0.1:{server.server_port}")
        login = client.get_login_info()
        if not login.ok or login.data["user_id"] != 123456:
            raise RuntimeError(f"login probe failed: {login}")
        sent = client.send_private_msg("123456", "hello")
        if not sent.ok:
            raise RuntimeError(f"send failed: {sent}")
    finally:
        server.shutdown()
    print("onebot client smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

