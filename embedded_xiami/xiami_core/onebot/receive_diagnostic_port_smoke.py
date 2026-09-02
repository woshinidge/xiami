from __future__ import annotations

import socket

from xiami_core.testing import use_temp_xiami_home

use_temp_xiami_home()

from xiami_core.onebot.receive_diagnostic import run_receive_diagnostic


def main() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    try:
        port = int(sock.getsockname()[1])
        result = run_receive_diagnostic(event_url=f"http://127.0.0.1:{port}/onebot/event")
        if not result.gateway_listening:
            raise RuntimeError(f"gateway port drift was not detected: {port}")
    finally:
        sock.close()
    print("receive diagnostic port smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
