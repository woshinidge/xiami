from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.models import AccountStatus
from xiami_core.runtime_diagnostic import RuntimeDiagnostic
from xiami_core.stability_suite import format_stability_suite_result, run_stability_suite
from xiami_core.storage.config import AppConfig, KernelConfig
from xiami_core.storage.paths import LOG_HOME


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = {"status": "ok", "retcode": 0, "data": {"online": True, "good": True}}
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    blocked = run_stability_suite(
        duration=0,
        interval=0.1,
        status=AccountStatus(state="offline"),
        diagnostic=_diag(onebot=False),
        log_path=LOG_HOME / "blocked.jsonl",
    )
    if blocked.phase != "blocked" or blocked.observation is not None:
        raise RuntimeError(format_stability_suite_result(blocked))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        http_url = f"http://127.0.0.1:{server.server_port}"
        config = AppConfig(kernel=KernelConfig(kind="NapCat", http_url=http_url))
        result = run_stability_suite(
            duration=0,
            interval=0.1,
            include_provider=False,
            config=config,
            status=AccountStatus(state="online", account="10000"),
            diagnostic=_diag(onebot=True, http_url=http_url),
            log_path=LOG_HOME / "suite.jsonl",
            min_samples=1,
            min_duration=0,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    text = format_stability_suite_result(result)
    if result.phase != "evidence_passed" or "长稳套件：证据已通过" not in text:
        raise RuntimeError(text)
    print("stability suite smoke ok")
    return 0


def _diag(*, onebot: bool, http_url: str = "http://127.0.0.1:1") -> RuntimeDiagnostic:
    return RuntimeDiagnostic(
        config=AppConfig(kernel=KernelConfig(kind="NapCat", http_url=http_url)),
        kernel_candidates=(),
        suggested_kernel=None,
        onebot_reachable=onebot,
        onebot_detail="ok" if onebot else "unreachable",
        configured_port_open=onebot,
        qr_candidates=(),
        napcat_config_ok=True,
        napcat_config_detail="ok",
    )


if __name__ == "__main__":
    raise SystemExit(main())
