from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from xiami_core.kernels.external import NapCatKernel
from xiami_core.storage.config import KernelConfig


class Handler(BaseHTTPRequestHandler):
    login_calls = 0
    status_data: dict[str, object] = {"online": True, "good": True}

    def do_POST(self) -> None:
        if self.path == "/get_login_info":
            Handler.login_calls += 1
            body = {"status": "failed", "retcode": 100, "wording": "无法获取用户信息"}
        elif self.path == "/get_status":
            body = {"status": "ok", "retcode": 0, "data": Handler.status_data}
        elif self.path == "/get_version_info":
            body = {"status": "ok", "retcode": 0, "data": {"app_name": "NapCat"}}
        else:
            body = {"status": "failed", "retcode": 404, "wording": "unknown"}
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    status = _status_for({"online": True, "good": True})
    if status.state != "online" or "OneBot 已连接" not in status.detail:
        raise RuntimeError(f"bad onebot ready status: {status}")
    if Handler.login_calls:
        raise RuntimeError("status() should not call get_login_info when get_status is online")

    status = _status_for({"online": False, "good": True})
    if status.state == "online":
        raise RuntimeError(f"good-only status must not be treated as online: {status}")
    if "等待登录信息" not in status.detail:
        raise RuntimeError(f"good-only status should be treated as HTTP ready: {status}")
    print("onebot ready smoke ok")
    return 0


def _status_for(status_data: dict[str, object]):
    Handler.login_calls = 0
    Handler.status_data = status_data
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        kernel = NapCatKernel(KernelConfig(kind="NapCat", http_url=f"http://127.0.0.1:{server.server_port}"))
        deadline = time.monotonic() + 2
        status = kernel.status()
        while status.state == "offline" and time.monotonic() < deadline:
            time.sleep(0.05)
            status = kernel.status()
        return status
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
