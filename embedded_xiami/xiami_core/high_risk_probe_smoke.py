from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.high_risk_evidence import build_high_risk_evidence_suggestions
from xiami_core.high_risk_probe import format_high_risk_probe, run_high_risk_probe
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        if length:
            self.rfile.read(length)
        action = self.path.strip("/")
        data = {"message_id": 98765} if action == "send_group_msg" else {}
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
        result = run_high_risk_probe(
            moderation_user="10001",
            confirm_moderation=True,
            friend_flag="friend-flag",
            join_flag="join-flag",
            confirm_review=True,
            timeout=2,
        )
        rendered = format_high_risk_probe(result)
        if not result.ok:
            raise RuntimeError(rendered)
        suggestions = build_high_risk_evidence_suggestions()
        ok_names = {item.name for item in suggestions.candidates if item.ok}
        expected = {"friend_review_real", "join_review_real", "moderation_real", "member_guard_real"}
        if not expected.issubset(ok_names):
            raise RuntimeError(f"missing candidates: {expected - ok_names}\n{rendered}")
    finally:
        server.shutdown()
        server.server_close()
    print("high-risk probe smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
