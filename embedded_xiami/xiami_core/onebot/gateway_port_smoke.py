from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from xiami_core.events import EventBus
from xiami_core.onebot.gateway import OneBotEventGateway


class BusyHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return


def main() -> int:
    busy = ThreadingHTTPServer(("127.0.0.1", 18081), BusyHandler)
    busy_thread = threading.Thread(target=busy.serve_forever, daemon=True)
    busy_thread.start()
    gateway = OneBotEventGateway(EventBus(), port=18081)
    try:
        url = gateway.start()
        if ":18081/" in url:
            raise RuntimeError(f"gateway did not move to next port: {url}")
    finally:
        gateway.stop()
        busy.shutdown()
        busy.server_close()
    print("onebot gateway port smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
