from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.plugins.ai_provider import AiProviderConfig
from xiami_core.stability_continue import format_stability_continue_result, run_stability_continue
from xiami_core.storage.config import AppConfig, KernelConfig, save_config


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = {"status": "ok", "retcode": 0, "data": {"online": True, "good": True}}
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, _format: str, *_args) -> None:
        return


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        http_url = f"http://127.0.0.1:{server.server_port}"
        save_config(AppConfig(kernel=KernelConfig(kind="NapCat", http_url=http_url)))
        provider = AiProviderConfig(
            provider="openai",
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
        )
        result = run_stability_continue(
            duration=0,
            interval=0.1,
            include_provider=True,
            min_samples=1,
            min_duration=0,
            min_onebot_ratio=1.0,
            min_provider_ratio=1.0,
            provider_config=provider,
            provider_transport=_provider_transport,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    text = format_stability_continue_result(result)
    if not result.ok or result.observation is None or result.observation.total != 1:
        raise RuntimeError(text)
    if "长稳续跑：PASS" not in text or "本次观察" not in text:
        raise RuntimeError(text)
    print("stability continue smoke ok")
    return 0


def _provider_transport(_url, _payload, _headers, _timeout):
    return {"choices": [{"message": {"content": "provider ok"}}]}


if __name__ == "__main__":
    raise SystemExit(main())
