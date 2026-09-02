from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import socket
import threading
import time

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.onebot.receive_diagnostic import format_receive_diagnostic, run_receive_diagnostic
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path == "/get_status":
            body = {"status": "ok", "retcode": 0, "data": {"online": False, "good": True}}
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
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    gateway_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    gateway_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    gateway_socket.bind(("127.0.0.1", 0))
    gateway_socket.listen(1)
    try:
        port = int(server.server_address[1])
        gateway_port = int(gateway_socket.getsockname()[1])
        save_config(AppConfig(kernel=KernelConfig(kind="NapCat", http_url=f"http://127.0.0.1:{port}")))
        result = None
        for _attempt in range(5):
            result = run_receive_diagnostic(event_url=f"http://127.0.0.1:{gateway_port}/onebot/event")
            if "可访问" in result.onebot_detail or result.onebot_online:
                break
            time.sleep(0.1)
        if result is None:
            raise RuntimeError("receive diagnostic did not run")
        if result.onebot_online:
            raise RuntimeError(f"good-only status should not be online: {result}")
        text = format_receive_diagnostic(result)
        if f"127.0.0.1:{gateway_port}" not in text:
            raise RuntimeError(f"gateway endpoint not rendered: {text}")
        if "未在线" not in result.onebot_detail:
            raise RuntimeError(f"offline detail missing: {result.onebot_detail}")
    finally:
        gateway_socket.close()
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()
    print("receive diagnostic online smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
