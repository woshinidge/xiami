from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from xiami_core.storage.config import KernelConfig


@dataclass(frozen=True)
class KernelTemplateResult:
    files: list[Path]
    detail: str


def write_kernel_templates(config: KernelConfig, event_url: str, event_ws_url: str = "") -> KernelTemplateResult:
    kind = config.kind.lower()
    if kind == "lagrange":
        return _write_lagrange_template(config, event_url)
    if kind == "napcat":
        return _write_napcat_template(config, event_url, event_ws_url)
    return KernelTemplateResult(files=[], detail="Mock 内核不需要配置模板")


def _write_lagrange_template(config: KernelConfig, event_url: str) -> KernelTemplateResult:
    workdir = _workdir(config)
    path = workdir / "appsettings.json"
    payload = {
        "Logging": {
            "LogLevel": {
                "Default": "Information",
                "Microsoft": "Warning",
                "Microsoft.Hosting.Lifetime": "Information",
            }
        },
        "SignServerUrl": "",
        "Account": {
            "Uin": 0,
            "Password": "",
            "Protocol": "Linux",
        },
        "Implementations": [
            {
                "Type": "Http",
                "Host": _host(config.http_url),
                "Port": _port(config.http_url),
                "AccessToken": config.access_token,
            },
            {
                "Type": "HttpPost",
                "Host": event_url,
                "AccessToken": config.access_token,
            },
        ],
    }
    _write_json(path, payload)
    return KernelTemplateResult(files=[path], detail=f"Lagrange OneBot 配置已写入：{path}")


def _write_napcat_template(config: KernelConfig, event_url: str, event_ws_url: str = "") -> KernelTemplateResult:
    workdir = _workdir(config)
    paths = [workdir / "config" / "onebot11.json"]
    account_config_dir = workdir / "napcat" / "config"
    if account_config_dir.exists():
        paths.extend(sorted(account_config_dir.glob("onebot11_*.json")))
        protocol_accounts = _napcat_account_ids(account_config_dir)
        for account in protocol_accounts:
            protocol_path = account_config_dir / f"napcat_protocol_{account}.json"
            if protocol_path not in paths:
                paths.append(protocol_path)
    onebot_payload = _napcat_onebot_payload(config, event_url, event_ws_url)
    protocol_payload = _napcat_protocol_payload(config, event_ws_url)
    written: list[Path] = []
    for path in paths:
        existing = _read_json(path)
        if path.name.startswith("napcat_protocol_"):
            merged = _merge_napcat_protocol(existing, protocol_payload)
        else:
            merged = _merge_napcat_onebot(existing, onebot_payload)
        _write_json(path, merged)
        written.append(path)
    return KernelTemplateResult(files=written, detail="NapCat OneBot 配置已写入：" + "；".join(str(path) for path in written))


def _napcat_onebot_payload(config: KernelConfig, event_url: str, event_ws_url: str = "") -> dict:
    network = {
        "httpServers": [
            {
                "name": "Xiami HTTP API",
                "host": _host(config.http_url),
                "port": _port(config.http_url),
                "enable": True,
                "token": config.access_token,
            }
        ],
        "httpClients": [
            {
                "name": "Xiami Event Push",
                "url": event_url,
                "enable": True,
                "token": config.access_token,
                "reportSelfMessage": False,
                "messagePostFormat": "array",
                "debug": False,
            }
        ],
    }
    if event_ws_url:
        network["websocketClients"] = [
            {
                "name": "Xiami Event WS",
                "url": event_ws_url,
                "enable": True,
                "token": config.access_token,
                "reportSelfMessage": False,
                "messagePostFormat": "array",
                "debug": False,
                "heartInterval": 30000,
                "reconnectInterval": 30000,
                "verifyCertificate": True,
            }
        ]
    return {
        "network": {
            **network,
        }
    }


def _napcat_protocol_payload(config: KernelConfig, event_ws_url: str = "") -> dict:
    network = {
        "httpServers": [
            {
                "name": "Xiami HTTP API",
                "host": _host(config.http_url),
                "port": _port(config.http_url),
                "enable": True,
                "token": config.access_token,
                "enableCors": True,
                "debug": False,
            }
        ],
        "websocketServers": [],
        "websocketClients": [],
    }
    if event_ws_url:
        network["websocketClients"] = [
            {
                "name": "Xiami Event WS",
                "url": event_ws_url,
                "enable": True,
                "token": config.access_token,
                "heartInterval": 30000,
                "reconnectInterval": 30000,
                "debug": False,
            }
        ]
    return {"enable": True, "network": network}


def _merge_napcat_onebot(existing: dict, payload: dict) -> dict:
    merged = dict(existing) if isinstance(existing, dict) else {}
    network = dict(merged.get("network") or {})
    payload_network = payload["network"]
    network["httpServers"] = payload_network["httpServers"]
    network["httpClients"] = payload_network["httpClients"]
    if "websocketClients" in payload_network:
        network["websocketClients"] = payload_network["websocketClients"]
    network.setdefault("httpSseServers", [])
    network.setdefault("websocketServers", [])
    network.setdefault("websocketClients", [])
    network.setdefault("plugins", [])
    merged["network"] = network
    return merged


def _merge_napcat_protocol(existing: dict, payload: dict) -> dict:
    merged = dict(existing) if isinstance(existing, dict) else {}
    merged["enable"] = True
    network = dict(merged.get("network") or {})
    payload_network = payload["network"]
    network["httpServers"] = payload_network["httpServers"]
    network["websocketServers"] = payload_network.get("websocketServers", [])
    network["websocketClients"] = payload_network.get("websocketClients", [])
    merged["network"] = network
    return merged


def _napcat_account_ids(config_dir: Path) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    patterns = ("napcat_*.json", "napcat_protocol_*.json", "onebot11_*.json")
    for pattern in patterns:
        for path in sorted(config_dir.glob(pattern)):
            stem = path.stem
            account = ""
            for prefix in ("napcat_protocol_", "napcat_", "onebot11_"):
                if stem.startswith(prefix):
                    account = stem[len(prefix) :]
                    break
            if account.isdigit() and account not in seen:
                seen.add(account)
                result.append(account)
    return result


def _workdir(config: KernelConfig) -> Path:
    if not config.working_dir:
        raise RuntimeError("缺少内核工作目录")
    path = Path(config.working_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _host(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1"


def _port(url: str) -> int:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80
