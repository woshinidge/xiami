from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.plugins.ai_provider import AiProviderConfig
from xiami_core.stability_observer import format_stability_observation, run_stability_observation
from xiami_core.storage.config import AppConfig, KernelConfig, save_config
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
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        http_url = f"http://127.0.0.1:{server.server_port}"
        _wait_for_onebot(http_url)
        save_config(
            AppConfig(
                kernel=KernelConfig(kind="NapCat", http_url=http_url)
            )
        )
        provider = AiProviderConfig(
            provider="openai",
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
        )
        result = run_stability_observation(
            duration=0,
            interval=0.1,
            include_provider=True,
            provider_config=provider,
            provider_transport=_provider_transport,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)
    if result.total != 1 or result.onebot_ok != 1 or result.provider_ok != 1:
        raise RuntimeError(f"bad stability observation: {result!r}")
    text = format_stability_observation(result)
    if "OneBot 1/1" not in text or "Provider：1/1" not in text:
        raise RuntimeError(f"bad stability report: {text}")
    log_path = LOG_HOME / "stability_observation.jsonl"
    if not log_path.exists() or not log_path.read_text(encoding="utf-8").strip():
        raise RuntimeError("stability observation log was not written")
    print("stability observer smoke ok")
    return 0


def _provider_transport(url, payload, headers, timeout):
    return {
        "choices": [
            {
                "message": {
                    "content": "provider ok",
                }
            }
        ]
    }


def _wait_for_onebot(http_url: str) -> None:
    client = OneBotHttpClient(http_url, timeout=0.2)
    deadline = time.monotonic() + 3
    last_detail = ""
    while time.monotonic() < deadline:
        result = client.get_status()
        if result.ok:
            return
        last_detail = result.message
        time.sleep(0.05)
    raise RuntimeError(f"fake OneBot server did not become ready: {last_detail}")


if __name__ == "__main__":
    raise SystemExit(main())
