from __future__ import annotations

from xiami_core.plugins.ai_provider import (
    AiProviderConfig,
    call_ai_provider,
    describe_ai_provider,
    probe_ai_provider,
    stream_ai_provider,
)


def main() -> int:
    captured: dict[str, object] = {}

    def transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {"choices": [{"message": {"content": "模型回复"}}]}

    result = call_ai_provider(
        AiProviderConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="http://127.0.0.1:9999/v1",
            model="test-model",
            timeout=3,
        ),
        prompt="上下文",
        question="问题",
        transport=transport,
    )
    if not result.ok or result.text != "模型回复":
        raise RuntimeError(f"provider call failed: {result}")
    if captured.get("url") != "http://127.0.0.1:9999/v1/chat/completions":
        raise RuntimeError(f"bad provider url: {captured}")
    payload = captured.get("payload")
    if not isinstance(payload, dict) or payload.get("model") != "test-model":
        raise RuntimeError(f"bad provider payload: {captured}")
    headers = captured.get("headers")
    if not isinstance(headers, dict) or headers.get("Authorization") != "Bearer test-key":
        raise RuntimeError(f"bad provider headers: {captured}")

    retry_attempts = {"count": 0}

    def retry_transport(url, payload, headers, timeout):
        retry_attempts["count"] += 1
        if retry_attempts["count"] == 1:
            raise RuntimeError("temporary model failure")
        return {"choices": [{"message": {"content": "重试后回复"}}]}

    retry_result = call_ai_provider(
        AiProviderConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="http://127.0.0.1:9999/v1",
            model="test-model",
            retries=1,
        ),
        prompt="上下文",
        question="问题",
        transport=retry_transport,
    )
    if not retry_result.ok or retry_result.text != "重试后回复" or retry_attempts["count"] != 2:
        raise RuntimeError(f"provider retry failed: {retry_result}, attempts={retry_attempts}")
    if not isinstance(retry_result.raw, dict) or retry_result.raw.get("_xiami_attempts") != 2:
        raise RuntimeError(f"provider retry attempts missing: {retry_result.raw}")

    diagnostic = describe_ai_provider(
        AiProviderConfig(
            provider="openai",
            api_key="test-key",
            model="test-model",
            retries=1,
        )
    )
    if (
        diagnostic.get("chat_url") != "https://api.openai.com/v1/chat/completions"
        or diagnostic.get("preset") is not True
        or diagnostic.get("stream_supported") is not True
        or diagnostic.get("missing")
    ):
        raise RuntimeError(f"provider diagnostic failed: {diagnostic}")

    captured.clear()
    preset = call_ai_provider(
        AiProviderConfig(
            provider="openai",
            api_key="test-key",
            model="test-model",
            timeout=3,
        ),
        prompt="上下文",
        question="问题",
        transport=transport,
    )
    if not preset.ok or captured.get("url") != "https://api.openai.com/v1/chat/completions":
        raise RuntimeError(f"openai provider preset failed: preset={preset}, captured={captured}")

    preset_urls = {
        "deepseek": "https://api.deepseek.com/v1/chat/completions",
        "kimi": "https://api.moonshot.cn/v1/chat/completions",
        "moonshot": "https://api.moonshot.cn/v1/chat/completions",
        "openrouter": "https://openrouter.ai/api/v1/chat/completions",
        "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
    }
    for provider, expected_url in preset_urls.items():
        captured.clear()
        result = call_ai_provider(
            AiProviderConfig(provider=provider, api_key="test-key", model="test-model", timeout=3),
            prompt="上下文",
            question="问题",
            transport=transport,
        )
        if not result.ok or captured.get("url") != expected_url:
            raise RuntimeError(f"{provider} provider preset failed: result={result}, captured={captured}")

    missing = call_ai_provider(
        AiProviderConfig(provider="openai_compatible", base_url="", api_key="", model=""),
        prompt="",
        question="hi",
        transport=transport,
    )
    if missing.ok or "missing" not in missing.error:
        raise RuntimeError(f"provider missing config not detected: {missing}")

    captured.clear()

    def tool_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        return {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {
                                "id": "call_1",
                                "type": "function",
                                "function": {
                                    "name": "knowledge_search",
                                    "arguments": "{\"query\":\"NapCat\",\"limit\":2}",
                                },
                            }
                        ]
                    }
                }
            ]
        }

    tool_result = call_ai_provider(
        AiProviderConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="http://127.0.0.1:9999/v1",
            model="test-model",
        ),
        prompt="上下文",
        question="问题",
        transport=tool_transport,
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "knowledge_search",
                    "description": "search local knowledge",
                    "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                },
            }
        ],
    )
    tool_payload = captured.get("payload")
    if not tool_result.ok or len(tool_result.tool_calls) != 1:
        raise RuntimeError(f"provider tool calls not parsed: {tool_result}")
    if tool_result.tool_calls[0].name != "knowledge_search" or tool_result.tool_calls[0].arguments.get("query") != "NapCat":
        raise RuntimeError(f"provider tool call arguments failed: {tool_result.tool_calls}")
    if not isinstance(tool_payload, dict) or "tools" not in tool_payload or tool_payload.get("tool_choice") != "auto":
        raise RuntimeError(f"provider tools payload failed: {captured}")

    captured.clear()
    probe = probe_ai_provider(
        AiProviderConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="http://127.0.0.1:9999/v1",
            model="test-model",
            max_tokens=800,
            timeout=99,
        ),
        transport=transport,
    )
    probe_payload = captured.get("payload")
    if not probe.ok or "模型回复" not in probe.text:
        raise RuntimeError(f"provider probe failed: {probe}")
    if not isinstance(probe_payload, dict) or probe_payload.get("max_tokens") != 16 or captured.get("timeout") != 10.0:
        raise RuntimeError(f"provider probe limits failed: {captured}")

    captured.clear()

    def stream_transport(url, payload, headers, timeout):
        captured["url"] = url
        captured["payload"] = payload
        captured["headers"] = headers
        captured["timeout"] = timeout
        yield 'data: {"choices":[{"delta":{"content":"流式"}}]}\n\n'
        yield 'data: {"choices":[{"delta":{"content":"回复"}}]}'
        yield "data: [DONE]"

    stream_result = stream_ai_provider(
        AiProviderConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="http://127.0.0.1:9999/v1",
            model="test-model",
            timeout=3,
        ),
        prompt="上下文",
        question="问题",
        transport=stream_transport,
    )
    if not stream_result.ok or stream_result.text != "流式回复":
        raise RuntimeError(f"provider stream failed: {stream_result}")
    stream_payload = captured.get("payload")
    if not isinstance(stream_payload, dict) or stream_payload.get("stream") is not True:
        raise RuntimeError(f"provider stream payload failed: {captured}")

    stream_retry_attempts = {"count": 0}

    def stream_retry_transport(url, payload, headers, timeout):
        stream_retry_attempts["count"] += 1
        if stream_retry_attempts["count"] == 1:
            raise RuntimeError("temporary stream failure")
        yield 'data: {"choices":[{"delta":{"content":"重试流式"}}]}'
        yield "data: [DONE]"

    stream_retry_result = stream_ai_provider(
        AiProviderConfig(
            provider="openai_compatible",
            api_key="test-key",
            base_url="http://127.0.0.1:9999/v1",
            model="test-model",
            retries=1,
        ),
        prompt="上下文",
        question="问题",
        transport=stream_retry_transport,
    )
    if not stream_retry_result.ok or stream_retry_result.text != "重试流式" or stream_retry_attempts["count"] != 2:
        raise RuntimeError(f"provider stream retry failed: {stream_retry_result}, attempts={stream_retry_attempts}")
    if not isinstance(stream_retry_result.raw, dict) or stream_retry_result.raw.get("attempts") != 2:
        raise RuntimeError(f"provider stream retry attempts missing: {stream_retry_result.raw}")

    local = call_ai_provider(AiProviderConfig(provider="local_knowledge"), prompt="", question="hi", transport=transport)
    if local.ok or "local" not in local.error:
        raise RuntimeError(f"local provider should not call model: {local}")

    print("ai provider smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
