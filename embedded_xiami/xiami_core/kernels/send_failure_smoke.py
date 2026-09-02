from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from xiami_core.kernels.external import NapCatKernel
from xiami_core.storage.config import KernelConfig


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        if self.path == "/get_status":
            body = {"status": "ok", "retcode": 0, "data": {"online": True, "good": True}}
        elif self.path == "/send_private_msg":
            body = {"status": "failed", "retcode": 100, "wording": "mock send failed"}
        else:
            body = {"status": "ok", "retcode": 0, "data": {}}
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
    try:
        kernel = NapCatKernel(KernelConfig(kind="NapCat", http_url=f"http://127.0.0.1:{server.server_port}"))
        result = kernel.send_message("123", "hello")
        if result.ok or "mock send failed" not in result.detail:
            raise RuntimeError(f"send failure not surfaced: {result}")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    print("send failure smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
