from __future__ import annotations

from xiami_core.onebot.gateway import _read_ws_frame, _safe_send_ws_frame


class ResetStream:
    def read(self, _size: int) -> bytes:
        raise ConnectionResetError(10054, "remote host closed connection")


class ResetConnection:
    def sendall(self, _data: bytes) -> None:
        raise ConnectionResetError(10054, "remote host closed connection")


def main() -> int:
    if _read_ws_frame(ResetStream()) is not None:
        raise RuntimeError("reset stream should close websocket frame reader")
    _safe_send_ws_frame(ResetConnection(), 8, b"")
    print("onebot gateway websocket disconnect smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
