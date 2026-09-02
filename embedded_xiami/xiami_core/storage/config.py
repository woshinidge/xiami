from __future__ import annotations

import json
from dataclasses import dataclass

from .paths import CONFIG_FILE, atomic_write_json


@dataclass(frozen=True)
class KernelConfig:
    kind: str = "Mock"
    executable: str = ""
    working_dir: str = ""
    arguments: list[str] | None = None
    http_url: str = "http://127.0.0.1:3000"
    ws_url: str = ""
    access_token: str = ""


@dataclass(frozen=True)
class AppConfig:
    kernel: KernelConfig = KernelConfig()
    probe_private_target: str = ""
    probe_group_target: str = ""


def load_config() -> AppConfig:
    if not CONFIG_FILE.exists():
        return AppConfig()
    data = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    kernel_data = data.get("kernel") or {}
    if not isinstance(kernel_data, dict):
        kernel_data = {}
    kernel_fields = {
        "kind",
        "executable",
        "working_dir",
        "arguments",
        "http_url",
        "ws_url",
        "access_token",
    }
    return AppConfig(
        kernel=KernelConfig(**{key: value for key, value in kernel_data.items() if key in kernel_fields}),
        probe_private_target=str(data.get("probe_private_target") or ""),
        probe_group_target=str(data.get("probe_group_target") or ""),
    )


def save_config(config: AppConfig) -> None:
    existing: dict[str, object] = {}
    if CONFIG_FILE.is_file():
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        if isinstance(raw, dict):
            existing = dict(raw)
    kernel = existing.get("kernel")
    kernel_payload = dict(kernel) if isinstance(kernel, dict) else {}
    kernel_payload.update(
        {
            "kind": config.kernel.kind,
            "executable": config.kernel.executable,
            "working_dir": config.kernel.working_dir,
            "arguments": config.kernel.arguments,
            "http_url": config.kernel.http_url,
            "ws_url": config.kernel.ws_url,
            "access_token": config.kernel.access_token,
        }
    )
    existing.update(
        {
            "kernel": kernel_payload,
            "probe_private_target": config.probe_private_target,
            "probe_group_target": config.probe_group_target,
        }
    )
    atomic_write_json(CONFIG_FILE, existing)
