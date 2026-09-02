from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from xiami_core.kernels.external import LagrangeKernel, _build_command
from xiami_core.storage.config import KernelConfig


class Handler(BaseHTTPRequestHandler):
    sent: list[dict[str, object]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = self.rfile.read(length)
        data = json.loads(payload.decode("utf-8") or "{}")
        if self.path == "/get_status":
            body = {"status": "ok", "retcode": 0, "data": {"online": True, "good": True}}
        elif self.path == "/get_login_info":
            body = {"status": "ok", "retcode": 0, "data": {"user_id": 31420054, "nickname": "Xiami"}}
        else:
            Handler.sent.append({"path": self.path, "data": data})
            body = {"status": "ok", "retcode": 0, "data": {"message_id": 1}}
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        napcat_bat = tmp_path / "napcat.bat"
        napcat_bat.write_text("node.exe ./index.js\n", encoding="utf-8")
        (tmp_path / "node.exe").write_text("", encoding="utf-8")
        command = _build_command(napcat_bat, [], tmp_path)
        if Path(command[0]).name.lower() != "node.exe" or command[1] != "./index.js":
            raise RuntimeError(f"simple node bat was not flattened: {command}")

    command = _build_command(Path(r"C:\kernel\start.bat"), [], Path(r"C:\kernel"))
    if "cmd" not in Path(command[0]).name.lower() or command[1:5] != ["/d", "/s", "/c", "call"]:
        raise RuntimeError(f"bat command invalid: {command}")

    Handler.sent.clear()
    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    workdir_guard = tempfile.TemporaryDirectory()
    kernel = LagrangeKernel(
        KernelConfig(
            kind="Lagrange",
            executable=sys.executable,
            working_dir=workdir_guard.name,
            arguments=["-c", "import time; time.sleep(30)"],
            http_url=f"http://127.0.0.1:{server.server_port}",
        )
    )
    try:
        status = kernel.start_login()
        deadline = time.monotonic() + 3
        while status.state != "online" and time.monotonic() < deadline:
            time.sleep(0.1)
            status = kernel.status()
        if status.state != "online":
            raise RuntimeError(f"kernel did not become online: {status}")

        sent = kernel.send_message("10001", "hello")
        if not sent.ok or sent.message_id != "1":
            raise RuntimeError(f"private send failed: {sent}")

        group_sent = kernel.send_message("20001", "group hello", "group")
        if not group_sent.ok or group_sent.message_id != "1":
            raise RuntimeError(f"group send failed: {group_sent}")

        private_call = next((call for call in Handler.sent if call["path"] == "/send_private_msg"), None)
        if not private_call or private_call["data"].get("user_id") != 10001:
            raise RuntimeError(f"wrong private payload: {Handler.sent}")

        group_call = next((call for call in Handler.sent if call["path"] == "/send_group_msg"), None)
        if not group_call or group_call["data"].get("group_id") != 20001:
            raise RuntimeError(f"wrong group payload: {Handler.sent}")
    finally:
        kernel.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        workdir_guard.cleanup()
    print("external kernel smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
