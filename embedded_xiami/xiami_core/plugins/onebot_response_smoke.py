from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext


@dataclass(frozen=True)
class FakeResponse:
    ok: bool
    data: Any = None
    message: str = ""


def main() -> int:
    ctx = PluginContext(send_fn=lambda target, text, message_type: SendResult(ok=True))
    response = FakeResponse(ok=True, data={"value": 1}, message="ok")
    if not ctx.onebot_ok(response) or ctx.onebot_data(response) != {"value": 1} or ctx.onebot_message(response) != "ok":
        raise RuntimeError("object response helpers failed")

    payload = {"status": "ok", "retcode": 0, "data": [1, 2], "wording": "fine"}
    if not ctx.onebot_ok(payload) or ctx.onebot_data(payload) != [1, 2] or ctx.onebot_message(payload) != "fine":
        raise RuntimeError("dict response helpers failed")

    failed = {"status": "failed", "retcode": 1400, "message": "bad request"}
    if ctx.onebot_ok(failed) or ctx.onebot_message(failed) != "bad request":
        raise RuntimeError("failed response helpers failed")

    print("onebot response smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
