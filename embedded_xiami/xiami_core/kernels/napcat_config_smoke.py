from __future__ import annotations

import json
import tempfile
from pathlib import Path

from xiami_core.kernels.napcat_config import ensure_napcat_onebot_config, inspect_napcat_onebot_config
from xiami_core.storage.config import KernelConfig


def main() -> int:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "napcat" / "config" / "onebot11_10000.json"
        path.parent.mkdir(parents=True)
        path.write_text(
            json.dumps(
                {
                    "network": {
                        "httpServers": [{"enable": True, "port": 3000}],
                        "httpClients": [{"enable": True, "url": "http://127.0.0.1:18081/onebot/event"}],
                    }
                }
            ),
            encoding="utf-8",
        )
        state = inspect_napcat_onebot_config(KernelConfig(kind="NapCat", working_dir=str(root)))
        if not state.ok or state.files != (path,):
            raise RuntimeError(f"bad napcat config state: {state}")
        ws_required = inspect_napcat_onebot_config(
            KernelConfig(kind="NapCat", working_dir=str(root)),
            "http://127.0.0.1:18081/onebot/event",
            "ws://127.0.0.1:18082/onebot/event",
        )
        if ws_required.ok:
            raise RuntimeError(f"napcat config should require websocket event channel: {ws_required}")
        empty = root / "empty"
        ensure = ensure_napcat_onebot_config(
            KernelConfig(kind="NapCat", working_dir=str(empty), http_url="http://127.0.0.1:3007"),
            "http://127.0.0.1:18081/onebot/event",
            "ws://127.0.0.1:18082/onebot/event",
        )
        if not ensure.changed or not ensure.after.ok:
            raise RuntimeError(f"napcat config ensure failed: {ensure}")
        protocol = root / "protocol" / "napcat" / "config" / "napcat_protocol_10001.json"
        protocol.parent.mkdir(parents=True)
        protocol.write_text(
            json.dumps({"enable": False, "network": {"httpServers": [], "websocketClients": []}}),
            encoding="utf-8",
        )
        protocol_config = KernelConfig(kind="NapCat", working_dir=str(root / "protocol"), http_url="http://127.0.0.1:3008")
        disabled_protocol = inspect_napcat_onebot_config(
            protocol_config,
            "http://127.0.0.1:18081/onebot/event",
            "ws://127.0.0.1:18082/onebot/event",
        )
        if disabled_protocol.ok:
            raise RuntimeError(f"disabled napcat protocol should not be ok: {disabled_protocol}")
        fixed_protocol = ensure_napcat_onebot_config(
            protocol_config,
            "http://127.0.0.1:18081/onebot/event",
            "ws://127.0.0.1:18082/onebot/event",
        )
        if not fixed_protocol.changed or not fixed_protocol.after.ok:
            raise RuntimeError(f"napcat protocol ensure failed: {fixed_protocol}")
        print("napcat config smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
