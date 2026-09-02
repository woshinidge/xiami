from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.kernels.templates import write_kernel_templates
from xiami_core.storage.config import KernelConfig


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        lagrange = KernelConfig(
            kind="Lagrange",
            working_dir=str(root / "lagrange"),
            http_url="http://127.0.0.1:3000",
            access_token="token",
        )
        result = write_kernel_templates(lagrange, "http://127.0.0.1:18081/onebot/event")
        data = json.loads(result.files[0].read_text(encoding="utf-8"))
        if not any(item.get("Type") == "HttpPost" for item in data["Implementations"]):
            raise RuntimeError(f"Lagrange HttpPost missing: {data}")
        napcat = KernelConfig(
            kind="NapCat",
            working_dir=str(root / "napcat"),
            http_url="http://127.0.0.1:3001",
        )
        account_config = root / "napcat" / "napcat" / "config" / "onebot11_313420054.json"
        account_config.parent.mkdir(parents=True)
        account_config.write_text(
            json.dumps({"network": {"websocketServers": []}, "timeout": {"baseTimeout": 10000}}),
            encoding="utf-8",
        )
        protocol_config = account_config.parent / "napcat_protocol_313420054.json"
        protocol_config.write_text(
            json.dumps({"enable": False, "network": {"httpServers": [], "websocketClients": []}}),
            encoding="utf-8",
        )
        result = write_kernel_templates(
            napcat,
            "http://127.0.0.1:18081/onebot/event",
            "ws://127.0.0.1:18082/onebot/event",
        )
        data = json.loads(result.files[0].read_text(encoding="utf-8"))
        if data["network"]["httpClients"][0]["url"] != "http://127.0.0.1:18081/onebot/event":
            raise RuntimeError(f"NapCat event url missing: {data}")
        if data["network"]["websocketClients"][0]["url"] != "ws://127.0.0.1:18082/onebot/event":
            raise RuntimeError(f"NapCat websocket event url missing: {data}")
        account_data = json.loads(account_config.read_text(encoding="utf-8"))
        if account_data["network"]["httpServers"][0]["port"] != 3001:
            raise RuntimeError(f"NapCat account http server missing: {account_data}")
        if account_data["network"]["websocketClients"][0]["messagePostFormat"] != "array":
            raise RuntimeError(f"NapCat account websocket client incomplete: {account_data}")
        if account_data.get("timeout", {}).get("baseTimeout") != 10000:
            raise RuntimeError(f"NapCat account config was not preserved: {account_data}")
        protocol_data = json.loads(protocol_config.read_text(encoding="utf-8"))
        if not protocol_data.get("enable"):
            raise RuntimeError(f"NapCat protocol was not enabled: {protocol_data}")
        if protocol_data["network"]["httpServers"][0]["port"] != 3001:
            raise RuntimeError(f"NapCat protocol http server missing: {protocol_data}")
        if protocol_data["network"]["websocketClients"][0]["url"] != "ws://127.0.0.1:18082/onebot/event":
            raise RuntimeError(f"NapCat protocol websocket client missing: {protocol_data}")
    print("kernel templates smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
