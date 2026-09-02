from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.high_risk_evidence import build_high_risk_evidence_suggestions
from xiami_core.onebot.action_log import load_onebot_action_logs
from xiami_core.onebot_tools_probe import format_onebot_tools_probe, run_onebot_tools_probe
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        if length:
            self.rfile.read(length)
        action = self.path.strip("/")
        data = {
            "get_login_info": {"user_id": 10000, "nickname": "Xiami"},
            "get_status": {"online": True, "good": True},
            "get_version_info": {"app_name": "mock-onebot"},
            "get_friend_list": [{"user_id": 10001}],
            "get_group_list": [{"group_id": 20001}],
            "get_group_info": {"group_id": 20001, "group_name": "test"},
        }.get(action, {})
        body = json.dumps({"status": "ok", "retcode": 0, "data": data}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format: str, *args) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        save_config(AppConfig(kernel=KernelConfig(kind="NapCat", http_url=url), probe_group_target="20001"))
        result = run_onebot_tools_probe(timeout=2)
        rendered = format_onebot_tools_probe(result)
        if not result.ok or "OneBot 工具探针：PASS" not in rendered:
            raise RuntimeError(rendered)
        actions = {entry.action for entry in load_onebot_action_logs()}
        required = {"get_login_info", "get_status", "get_friend_list", "get_group_list"}
        if not required.issubset(actions):
            raise RuntimeError(f"missing action logs: {actions}")
        suggestions = build_high_risk_evidence_suggestions()
        candidate = next(item for item in suggestions.candidates if item.name == "onebot_tools_real")
        if not candidate.ok:
            raise RuntimeError(format_onebot_tools_probe(result))
    finally:
        server.shutdown()
        server.server_close()
    print("onebot tools probe smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
