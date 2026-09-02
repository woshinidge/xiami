from __future__ import annotations

import json
import math
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.plugins.ai_provider import AiProviderConfig, Transport, probe_ai_provider
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import LoadedPlugin, PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.storage.config import AppConfig, load_config
from xiami_core.storage.paths import LOG_HOME, PROJECT_ROOT, ensure_runtime_dirs


STABILITY_LOG_FILE = LOG_HOME / "stability_observation.jsonl"


@dataclass(frozen=True)
class StabilitySample:
    timestamp: str
    onebot_ok: bool
    onebot_detail: str
    provider_checked: bool
    provider_ok: bool
    provider_detail: str


@dataclass(frozen=True)
class StabilityObservation:
    samples: list[StabilitySample]
    log_path: str

    @property
    def total(self) -> int:
        return len(self.samples)

    @property
    def onebot_ok(self) -> int:
        return sum(1 for sample in self.samples if sample.onebot_ok)

    @property
    def provider_checked(self) -> int:
        return sum(1 for sample in self.samples if sample.provider_checked)

    @property
    def provider_ok(self) -> int:
        return sum(1 for sample in self.samples if sample.provider_checked and sample.provider_ok)


def run_stability_observation(
    *,
    duration: float = 60.0,
    interval: float = 5.0,
    include_provider: bool = False,
    config: AppConfig | None = None,
    provider_config: AiProviderConfig | None = None,
    provider_transport: Transport | None = None,
    log_path: Path | None = None,
) -> StabilityObservation:
    app_config = config or load_config()
    target_log = log_path or STABILITY_LOG_FILE
    ensure_runtime_dirs()
    target_log.parent.mkdir(parents=True, exist_ok=True)
    sample_count = max(1, int(math.ceil(max(0.0, duration) / max(0.1, interval))))
    samples: list[StabilitySample] = []
    resolved_provider = provider_config or (_load_ai_provider_config() if include_provider else None)
    for index in range(sample_count):
        sample = _observe_once(app_config, include_provider, resolved_provider, provider_transport)
        samples.append(sample)
        _append_sample(target_log, sample)
        if index + 1 < sample_count:
            time.sleep(max(0.1, interval))
    return StabilityObservation(samples=samples, log_path=str(target_log))


def format_stability_observation(result: StabilityObservation) -> str:
    lines = [
        f"长稳观察：OneBot {result.onebot_ok}/{result.total}",
        f"Provider：{result.provider_ok}/{result.provider_checked}" if result.provider_checked else "Provider：未启用观察",
        f"证据日志：{result.log_path}",
    ]
    if result.samples:
        latest = result.samples[-1]
        lines.append(f"最近 OneBot：{'OK' if latest.onebot_ok else 'FAIL'} / {latest.onebot_detail}")
        if latest.provider_checked:
            lines.append(f"最近 Provider：{'OK' if latest.provider_ok else 'FAIL'} / {latest.provider_detail}")
    return "\n".join(lines)


def _observe_once(
    config: AppConfig,
    include_provider: bool,
    provider_config: AiProviderConfig | None,
    provider_transport: Transport | None,
) -> StabilitySample:
    onebot_ok, onebot_detail = _observe_onebot(config)
    provider_checked = include_provider
    provider_ok = False
    provider_detail = "未启用观察"
    if include_provider:
        if provider_config is None:
            provider_detail = "未找到 ai_reply provider 配置"
        else:
            result = probe_ai_provider(provider_config, transport=provider_transport)
            provider_ok = result.ok
            provider_detail = f"{result.provider}/{result.model or '未配置模型'}：{result.error or result.text or 'ok'}"
    return StabilitySample(
        timestamp=datetime.now(timezone.utc).isoformat(),
        onebot_ok=onebot_ok,
        onebot_detail=onebot_detail,
        provider_checked=provider_checked,
        provider_ok=provider_ok,
        provider_detail=provider_detail,
    )


def _observe_onebot(config: AppConfig) -> tuple[bool, str]:
    kernel = config.kernel
    if not kernel.http_url:
        return False, "未配置 OneBot HTTP"
    client = OneBotHttpClient(kernel.http_url, kernel.access_token, timeout=2.0)
    status = client.get_status()
    if not status.ok:
        return False, status.message or "OneBot 不可访问"
    if isinstance(status.data, dict):
        online = bool(status.data.get("online"))
        good = bool(status.data.get("good"))
        return online, f"online={online}, good={good}"
    return False, str(status.data)


def _load_ai_provider_config() -> AiProviderConfig | None:
    plugin = _load_ai_reply_plugin()
    if plugin is None:
        return None
    config = plugin.config
    return AiProviderConfig(
        provider=str(config.get("provider") or "local_knowledge"),
        api_key=str(config.get("api_key") or ""),
        base_url=str(config.get("base_url") or ""),
        model=str(config.get("model") or ""),
        temperature=_float_config(config, "temperature", 0.2),
        max_tokens=_int_config(config, "max_tokens", 512),
        timeout=_float_config(config, "timeout", 20.0),
        retries=_int_config(config, "retries", 0),
        retry_delay=_float_config(config, "retry_delay", 0.0),
    )


def _load_ai_reply_plugin() -> LoadedPlugin | None:
    def send(_target: str, _text: str, _message_type: str = "private"):
        return None

    loader = PluginLoader(
        PROJECT_ROOT / "xiami_plugins",
        PluginContext(send_fn=send),
        PluginStateStore(LOG_HOME / "stability_plugins_enabled.json"),
    )
    loader.load_all()
    for plugin in loader.plugins:
        if plugin.id == "ai_reply":
            return plugin
    return None


def _append_sample(path: Path, sample: StabilitySample) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(asdict(sample), ensure_ascii=False) + "\n")


def _float_config(config: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(config.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_config(config: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError):
        return default
