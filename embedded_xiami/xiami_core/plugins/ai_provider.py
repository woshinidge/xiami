from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Union


Transport = Callable[[str, Dict[str, Any], Dict[str, str], float], Dict[str, Any]]
StreamTransport = Callable[[str, Dict[str, Any], Dict[str, str], float], Iterable[Union[Dict[str, Any], str, bytes]]]


@dataclass(frozen=True)
class AiProviderConfig:
    provider: str = "local_knowledge"
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = 0.2
    max_tokens: int = 800
    timeout: float = 20.0
    retries: int = 0
    retry_delay: float = 0.0


@dataclass(frozen=True)
class AiToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw_arguments: str = ""


@dataclass(frozen=True)
class AiStreamChunk:
    text: str = ""
    done: bool = False
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class AiProviderResult:
    ok: bool
    text: str
    provider: str
    model: str = ""
    error: str = ""
    raw: dict[str, Any] | None = None
    tool_calls: tuple[AiToolCall, ...] = ()


PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {"base_url": "https://api.openai.com/v1"},
    "deepseek": {"base_url": "https://api.deepseek.com/v1"},
    "kimi": {"base_url": "https://api.moonshot.cn/v1"},
    "moonshot": {"base_url": "https://api.moonshot.cn/v1"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1"},
    "dashscope": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
}
OPENAI_COMPATIBLE_PROVIDERS = frozenset({"openai_compatible", "compatible", *PROVIDER_PRESETS.keys()})


def resolve_provider_config(config: AiProviderConfig) -> AiProviderConfig:
    provider = (config.provider or "local_knowledge").strip().lower()
    preset = PROVIDER_PRESETS.get(provider, {})
    base_url = config.base_url.strip() or preset.get("base_url", "")
    return AiProviderConfig(
        provider=provider,
        api_key=config.api_key,
        base_url=base_url,
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=config.timeout,
        retries=config.retries,
        retry_delay=config.retry_delay,
    )


def call_ai_provider(
    config: AiProviderConfig,
    *,
    prompt: str,
    question: str,
    transport: Transport | None = None,
    tools: list[dict[str, Any]] | None = None,
    assistant_tool_calls: list[dict[str, Any]] | None = None,
    tool_messages: list[dict[str, Any]] | None = None,
) -> AiProviderResult:
    config = resolve_provider_config(config)
    provider = config.provider
    if provider in {"", "local", "local_knowledge", "knowledge"}:
        return AiProviderResult(False, "", provider or "local_knowledge", config.model, "local provider does not call model")
    if provider not in OPENAI_COMPATIBLE_PROVIDERS:
        return AiProviderResult(False, "", provider, config.model, f"unsupported provider: {config.provider}")
    missing = []
    if not config.base_url.strip():
        missing.append("base_url")
    if not config.api_key.strip():
        missing.append("api_key")
    if not config.model.strip():
        missing.append("model")
    if missing:
        return AiProviderResult(False, "", provider, config.model, "missing " + ", ".join(missing))

    url = _chat_url(config.base_url)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "你是 Xiami QQ 机器人助手。请优先依据本地知识库上下文回答。"},
        {"role": "user", "content": prompt or question},
    ]
    if assistant_tool_calls and tool_messages:
        messages.append({"role": "assistant", "content": None, "tool_calls": assistant_tool_calls})
        messages.extend(tool_messages)
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": float(config.temperature),
        "max_tokens": int(config.max_tokens),
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    attempts = _retry_attempts(config)
    last_error = ""
    data: dict[str, Any] | None = None
    for attempt in range(1, attempts + 1):
        try:
            data = (transport or _urllib_transport)(url, payload, headers, float(config.timeout))
            if attempt > 1:
                data.setdefault("_xiami_attempts", attempt)
            break
        except Exception as exc:
            last_error = str(exc)
            if attempt < attempts:
                _retry_pause(config)
                continue
            return AiProviderResult(False, "", provider, config.model, f"{last_error} (attempts={attempt})")
    if data is None:
        return AiProviderResult(False, "", provider, config.model, last_error or "empty provider transport")
    text = _extract_chat_text(data)
    tool_calls = _extract_tool_calls(data)
    if not text and not tool_calls:
        return AiProviderResult(False, "", provider, config.model, "empty model response", data)
    return AiProviderResult(True, text, provider, config.model, raw=data, tool_calls=tool_calls)


def probe_ai_provider(config: AiProviderConfig, *, transport: Transport | None = None) -> AiProviderResult:
    config = resolve_provider_config(config)
    probe_config = AiProviderConfig(
        provider=config.provider,
        api_key=config.api_key,
        base_url=config.base_url,
        model=config.model,
        temperature=0.0,
        max_tokens=min(max(1, int(config.max_tokens or 1)), 16),
        timeout=min(max(1.0, float(config.timeout or 1.0)), 10.0),
        retries=config.retries,
        retry_delay=config.retry_delay,
    )
    return call_ai_provider(
        probe_config,
        prompt="请回复 Xiami provider ok。",
        question="ping",
        transport=transport,
    )


def describe_ai_provider(config: AiProviderConfig) -> dict[str, Any]:
    config = resolve_provider_config(config)
    provider = config.provider.strip().lower() or "local_knowledge"
    remote = provider in OPENAI_COMPATIBLE_PROVIDERS
    missing: list[str] = []
    if remote:
        if not config.base_url.strip():
            missing.append("base_url")
        if not config.api_key.strip():
            missing.append("api_key")
        if not config.model.strip():
            missing.append("model")
    return {
        "provider": provider,
        "preset": provider in PROVIDER_PRESETS,
        "remote": remote,
        "supported": remote or provider in {"local", "local_knowledge", "knowledge"},
        "base_url": config.base_url,
        "chat_url": _chat_url(config.base_url) if config.base_url.strip() else "",
        "model": config.model,
        "api_key_configured": bool(config.api_key.strip()),
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout,
        "retries": config.retries,
        "retry_delay": config.retry_delay,
        "stream_supported": remote,
        "tool_calls_supported": remote,
        "missing": missing,
    }


def stream_ai_provider(
    config: AiProviderConfig,
    *,
    prompt: str,
    question: str,
    transport: StreamTransport | None = None,
) -> AiProviderResult:
    config = resolve_provider_config(config)
    provider = config.provider.strip().lower()
    if provider not in OPENAI_COMPATIBLE_PROVIDERS:
        return AiProviderResult(False, "", provider, config.model, f"unsupported provider: {provider}")

    missing: list[str] = []
    if not config.base_url.strip():
        missing.append("base_url")
    if not config.api_key.strip():
        missing.append("api_key")
    if not config.model.strip():
        missing.append("model")
    if missing:
        return AiProviderResult(False, "", provider, config.model, "missing " + ", ".join(missing))

    url = _chat_url(config.base_url)
    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": "你是 Xiami QQ 机器人助手。请优先依据本地知识库上下文回答。"},
            {"role": "user", "content": prompt or question},
        ],
        "temperature": float(config.temperature),
        "max_tokens": int(config.max_tokens),
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    attempts = _retry_attempts(config)
    last_error = ""
    last_chunks: list[dict[str, Any]] = []
    for attempt in range(1, attempts + 1):
        chunks: list[dict[str, Any]] = []
        parts: list[str] = []
        try:
            for raw_chunk in (transport or _urllib_stream_transport)(url, payload, headers, float(config.timeout)):
                chunk = _normalize_stream_chunk(raw_chunk)
                if not chunk:
                    continue
                chunks.append(chunk)
                if chunk.get("done") is True:
                    break
                piece = _extract_stream_text(chunk)
                if piece:
                    parts.append(piece)
        except Exception as exc:
            last_error = str(exc)
            last_chunks = chunks
            if attempt < attempts:
                _retry_pause(config)
                continue
            return AiProviderResult(False, "", provider, config.model, f"{last_error} (attempts={attempt})", {"chunks": chunks})

        text = "".join(parts).strip()
        if text:
            return AiProviderResult(True, text, provider, config.model, raw={"chunks": chunks, "attempts": attempt})
        last_error = "empty stream response"
        last_chunks = chunks
        if attempt < attempts:
            _retry_pause(config)
            continue
    return AiProviderResult(False, "", provider, config.model, f"{last_error} (attempts={attempts})", {"chunks": last_chunks})


def _retry_attempts(config: AiProviderConfig) -> int:
    try:
        retries = int(config.retries or 0)
    except (TypeError, ValueError):
        retries = 0
    return max(1, min(retries + 1, 4))


def _retry_pause(config: AiProviderConfig) -> None:
    try:
        delay = float(config.retry_delay or 0.0)
    except (TypeError, ValueError):
        delay = 0.0
    if delay > 0:
        time.sleep(min(delay, 3.0))


def _chat_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return base + "/chat/completions"
    return base + "/v1/chat/completions"


def _urllib_transport(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _urllib_stream_transport(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    timeout: float,
) -> Iterable[dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for raw_line in response:
                chunk = _normalize_stream_chunk(raw_line)
                if chunk:
                    yield chunk
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(str(exc.reason)) from exc


def _extract_chat_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message.get("content")).strip()
            if first.get("text") is not None:
                return str(first.get("text")).strip()
    if data.get("text") is not None:
        return str(data.get("text")).strip()
    return ""


def _normalize_stream_chunk(raw_chunk: dict[str, Any] | str | bytes) -> dict[str, Any] | None:
    if isinstance(raw_chunk, dict):
        return raw_chunk
    if isinstance(raw_chunk, bytes):
        raw_chunk = raw_chunk.decode("utf-8", errors="replace")
    line = str(raw_chunk).strip()
    if not line:
        return None
    if line.startswith("data:"):
        line = line[5:].strip()
    if not line:
        return None
    if line == "[DONE]":
        return {"done": True}
    return json.loads(line)


def _extract_stream_text(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
            message = first.get("message")
            if isinstance(message, dict) and message.get("content") is not None:
                return str(message.get("content"))
            if first.get("text") is not None:
                return str(first.get("text"))
    delta = data.get("delta")
    if isinstance(delta, dict) and delta.get("content") is not None:
        return str(delta.get("content"))
    if data.get("content") is not None:
        return str(data.get("content"))
    if data.get("text") is not None:
        return str(data.get("text"))
    return ""


def _extract_tool_calls(data: dict[str, Any]) -> tuple[AiToolCall, ...]:
    raw_calls: Any = None
    choices = data.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                raw_calls = message.get("tool_calls")
            if raw_calls is None:
                raw_calls = first.get("tool_calls")
    if raw_calls is None:
        raw_calls = data.get("tool_calls")
    if not isinstance(raw_calls, list):
        return ()
    calls: list[AiToolCall] = []
    for index, item in enumerate(raw_calls):
        if not isinstance(item, dict):
            continue
        function = item.get("function") if isinstance(item.get("function"), dict) else item
        name = str(function.get("name") or item.get("name") or "").strip()
        raw_arguments = function.get("arguments") if isinstance(function, dict) else item.get("arguments")
        if not name:
            continue
        arguments = _tool_arguments(raw_arguments)
        calls.append(
            AiToolCall(
                id=str(item.get("id") or f"tool_call_{index}"),
                name=name,
                arguments=arguments,
                raw_arguments=str(raw_arguments or ""),
            )
        )
    return tuple(calls)


def _tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if raw is None:
        return {}
    try:
        value = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}
