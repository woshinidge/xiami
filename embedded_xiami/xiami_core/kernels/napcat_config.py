from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from xiami_core.kernels.templates import write_kernel_templates
from xiami_core.storage.config import KernelConfig


@dataclass(frozen=True)
class NapCatOneBotConfigState:
    files: tuple[Path, ...]
    http_enabled: bool
    event_enabled: bool
    http_matched: bool
    event_matched: bool
    ws_event_enabled: bool = False
    ws_event_matched: bool = False
    ws_event_required: bool = False

    @property
    def ok(self) -> bool:
        event_ok = (self.event_enabled and self.event_matched) or (
            self.ws_event_required and self.ws_event_enabled and self.ws_event_matched
        )
        return (
            self.http_enabled
            and self.http_matched
            and event_ok
            and (not self.ws_event_required or (self.ws_event_enabled and self.ws_event_matched))
        )


@dataclass(frozen=True)
class NapCatConfigEnsureResult:
    before: NapCatOneBotConfigState
    after: NapCatOneBotConfigState
    changed: bool
    detail: str


def inspect_napcat_onebot_config(
    config: KernelConfig, event_url: str = "", event_ws_url: str = ""
) -> NapCatOneBotConfigState:
    workdir = Path(config.working_dir or Path(config.executable).parent)
    files = _config_files(workdir)
    expected_host = _host(config.http_url)
    expected_port = _port(config.http_url)
    expected_token = config.access_token or ""

    http_enabled = False
    event_enabled = False
    http_matched = False
    event_matched = False
    ws_event_enabled = False
    ws_event_matched = False

    for path in files:
        data = _read_json(path)
        network = data.get("network") if isinstance(data, dict) else {}
        if not isinstance(network, dict):
            continue
        if path.name.startswith("napcat_protocol_") and not data.get("enable"):
            continue

        for server in network.get("httpServers") or []:
            if not isinstance(server, dict) or not server.get("enable"):
                continue
            port = _safe_int(server.get("port"))
            if port <= 0:
                continue
            http_enabled = True
            host = str(server.get("host") or expected_host)
            token = str(server.get("token") or "")
            if port == expected_port and host == expected_host and token == expected_token:
                http_matched = True

        for client in network.get("httpClients") or []:
            if not isinstance(client, dict) or not client.get("enable"):
                continue
            url = str(client.get("url") or "")
            if not url.startswith("http"):
                continue
            event_enabled = True
            token = str(client.get("token") or "")
            if (not event_url or url == event_url) and token == expected_token:
                event_matched = True

        for client in network.get("websocketClients") or []:
            if not isinstance(client, dict) or not client.get("enable"):
                continue
            url = str(client.get("url") or "")
            if not url.startswith("ws"):
                continue
            ws_event_enabled = True
            token = str(client.get("token") or "")
            if (not event_ws_url or url == event_ws_url) and token == expected_token:
                ws_event_matched = True

    if not event_url and event_enabled:
        event_matched = True
    if not event_ws_url and ws_event_enabled:
        ws_event_matched = True

    return NapCatOneBotConfigState(
        files=tuple(files),
        http_enabled=http_enabled,
        event_enabled=event_enabled,
        http_matched=http_matched,
        event_matched=event_matched,
        ws_event_enabled=ws_event_enabled,
        ws_event_matched=ws_event_matched,
        ws_event_required=bool(event_ws_url),
    )


def ensure_napcat_onebot_config(config: KernelConfig, event_url: str, event_ws_url: str = "") -> NapCatConfigEnsureResult:
    before = inspect_napcat_onebot_config(config, event_url, event_ws_url)
    if before.ok:
        return NapCatConfigEnsureResult(before=before, after=before, changed=False, detail=_format_state("NapCat OneBot 配置已匹配", before))
    result = write_kernel_templates(config, event_url, event_ws_url)
    after = inspect_napcat_onebot_config(config, event_url, event_ws_url)
    detail = result.detail if after.ok else _format_state("NapCat OneBot 配置仍未匹配", after)
    return NapCatConfigEnsureResult(before=before, after=after, changed=True, detail=detail)


def _config_files(workdir: Path) -> list[Path]:
    account_dir = workdir / "napcat" / "config"
    if account_dir.exists():
        protocol_files = sorted(account_dir.glob("napcat_protocol_*.json"))
        if protocol_files:
            return protocol_files
    files: list[Path] = []
    root_file = workdir / "config" / "onebot11.json"
    if root_file.exists():
        files.append(root_file)
    if account_dir.exists():
        files.extend(sorted(account_dir.glob("onebot11_*.json")))
    return files


def _format_state(prefix: str, state: NapCatOneBotConfigState) -> str:
    return (
        f"{prefix}：HTTP={state.http_enabled}/{state.http_matched} "
        f"EVENT={state.event_enabled}/{state.event_matched} "
        f"WS={state.ws_event_enabled}/{state.ws_event_matched} "
        f"files={';'.join(str(path) for path in state.files) or '无'}"
    )


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _host(url: str) -> str:
    parsed = urlparse(url)
    return parsed.hostname or "127.0.0.1"


def _port(url: str) -> int:
    parsed = urlparse(url)
    if parsed.port:
        return parsed.port
    return 443 if parsed.scheme == "https" else 80


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
