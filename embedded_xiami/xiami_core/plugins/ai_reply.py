from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any

from xiami_core.plugins.ai_provider import (
    OPENAI_COMPATIBLE_PROVIDERS,
    AiProviderConfig,
    AiProviderResult,
    AiToolCall,
    StreamTransport,
    Transport,
    call_ai_provider,
    describe_ai_provider,
    probe_ai_provider,
    resolve_provider_config,
    stream_ai_provider,
)
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.knowledge import KnowledgeHit, KnowledgeService


@dataclass(frozen=True)
class AiReplyResult:
    ok: bool
    text: str
    hits: list[KnowledgeHit]
    prompt: str = ""


class LocalAiOrchestrator:
    """Local-first AI orchestration with optional OpenAI-compatible model calls."""

    def __init__(
        self,
        ctx: PluginContext,
        transport: Transport | None = None,
        stream_transport: StreamTransport | None = None,
    ):
        self.ctx = ctx
        self.transport = transport
        self.stream_transport = stream_transport

    def answer(
        self,
        question: str,
        *,
        limit: int = 3,
        event: Any | None = None,
        history_limit: int = 0,
    ) -> AiReplyResult:
        question = question.strip()
        if not question:
            return AiReplyResult(False, "请输入问题。", [])
        started = time.perf_counter()

        knowledge_ctx = self.ctx.for_plugin("knowledge", config=self.ctx.config)
        knowledge = KnowledgeService(knowledge_ctx)
        hits = knowledge.search(question, limit=limit)
        history = self._recent_history(event, history_limit=history_limit, current_question=question)
        prompt = self._build_prompt(question, hits, history)

        provider = resolve_provider_config(self._provider_config())

        def finalize(result: AiReplyResult, *, tool_calls: int = 0, model_error: str = "") -> AiReplyResult:
            self._audit_result("answer", provider, question, result, started, tool_calls=tool_calls, model_error=model_error)
            return result

        tools = _ai_tool_specs() if _is_remote_provider(provider.provider) and self._tools_enabled() else None
        model_reply = call_ai_provider(provider, prompt=prompt, question=question, transport=self.transport, tools=tools)
        if model_reply.ok and model_reply.tool_calls:
            tool_messages, tool_hits = self._run_tool_calls(model_reply.tool_calls, knowledge, default_limit=limit)
            if tool_messages:
                final_reply = call_ai_provider(
                    provider,
                    prompt=prompt,
                    question=question,
                    transport=self.transport,
                    assistant_tool_calls=_assistant_tool_payloads(model_reply),
                    tool_messages=tool_messages,
                )
                merged_hits = _merge_hits(hits, tool_hits)
                if final_reply.ok and final_reply.text:
                    return finalize(
                        AiReplyResult(True, self._append_sources(final_reply.text, merged_hits), merged_hits, prompt),
                        tool_calls=len(model_reply.tool_calls),
                    )
                if tool_hits:
                    return finalize(
                        AiReplyResult(True, self._tool_fallback(tool_hits), merged_hits, prompt),
                        tool_calls=len(model_reply.tool_calls),
                        model_error=final_reply.error,
                    )
        if model_reply.ok:
            return finalize(AiReplyResult(True, self._append_sources(model_reply.text, hits), hits, prompt))

        if not hits:
            if _is_remote_provider(provider.provider):
                friendly_error = _friendly_model_error(model_reply.error)
                return finalize(
                    AiReplyResult(False, friendly_error, [], prompt),
                    model_error=model_reply.error,
                )
            return finalize(AiReplyResult(False, "本地知识库暂无相关内容。", [], prompt))

        lines = ["本地知识库参考："]
        for index, hit in enumerate(hits, start=1):
            label = hit.title or hit.source or "知识片段"
            lines.append(f"{index}. {label} score={hit.score}\n{hit.text}")
        lines.append("")
        if _is_remote_provider(provider.provider):
            lines.append(f"{_friendly_model_error(model_reply.error)}；已降级返回本地知识参考。")
        else:
            lines.append("建议回复：请基于以上本地知识回答；当前未配置外部模型，先返回检索到的参考内容。")
        return finalize(
            AiReplyResult(True, self._append_sources("\n".join(lines), hits), hits, prompt),
            model_error=model_reply.error,
        )

    def stream_answer(
        self,
        question: str,
        *,
        limit: int = 3,
        event: Any | None = None,
        history_limit: int = 0,
    ) -> AiReplyResult:
        question = question.strip()
        if not question:
            return AiReplyResult(False, "请输入问题。", [])
        started = time.perf_counter()

        knowledge_ctx = self.ctx.for_plugin("knowledge", config=self.ctx.config)
        knowledge = KnowledgeService(knowledge_ctx)
        hits = knowledge.search(question, limit=limit)
        history = self._recent_history(event, history_limit=history_limit, current_question=question)
        prompt = self._build_prompt(question, hits, history)

        provider = resolve_provider_config(self._provider_config())
        if not _is_remote_provider(provider.provider):
            return self.answer(question, limit=limit, event=event, history_limit=history_limit)

        def finalize(result: AiReplyResult, *, model_error: str = "") -> AiReplyResult:
            self._audit_result("stream", provider, question, result, started, model_error=model_error, stream=True)
            return result

        model_reply = stream_ai_provider(
            provider,
            prompt=prompt,
            question=question,
            transport=self.stream_transport,
        )
        if model_reply.ok:
            return finalize(AiReplyResult(True, self._append_sources(model_reply.text, hits), hits, prompt))
        if hits:
            lines = [_friendly_model_error(model_reply.error), "以下为本地知识库参考："]
            for index, hit in enumerate(hits, start=1):
                label = hit.title or hit.source or hit.chunk_id or "知识片段"
                lines.append(f"{index}. {label} score={hit.score}\n{hit.text}")
            return finalize(AiReplyResult(True, self._append_sources("\n".join(lines), hits), hits, prompt), model_error=model_reply.error)
        return finalize(AiReplyResult(False, _friendly_model_error(model_reply.error), [], prompt), model_error=model_reply.error)

    def status(self) -> str:
        provider = resolve_provider_config(self._provider_config())
        knowledge = KnowledgeService(self.ctx.for_plugin("knowledge", config=self.ctx.config)).stats()
        remote_ready = bool(provider.base_url.strip() and provider.api_key.strip() and provider.model.strip())
        lines = [
            "AI 知识问答状态：",
            f"Provider：{provider.provider}",
            f"Model：{provider.model or '未配置'}",
            f"Base URL：{'已配置' if provider.base_url else '未配置'}",
            f"API Key：{'已配置' if provider.api_key else '未配置'}",
            f"失败重试：{provider.retries} 次，间隔 {provider.retry_delay}s",
            f"远程模型：{'可调用' if _is_remote_provider(provider.provider) and remote_ready else '未就绪'}",
            f"知识库：{knowledge.chunks} 个片段，{knowledge.documents} 个文档",
        ]
        return "\n".join(lines)

    def provider_report(self) -> str:
        data = describe_ai_provider(self._provider_config())
        missing = data.get("missing") or []
        lines = [
            "AI Provider 诊断：",
            f"Provider：{data.get('provider')}",
            f"预设：{'是' if data.get('preset') else '否'}",
            f"远程模型：{'是' if data.get('remote') else '否'}",
            f"支持状态：{'支持' if data.get('supported') else '不支持'}",
            f"Base URL：{data.get('base_url') or '未配置'}",
            f"Chat URL：{data.get('chat_url') or '未配置'}",
            f"Model：{data.get('model') or '未配置'}",
            f"API Key：{'已配置' if data.get('api_key_configured') else '未配置'}",
            f"Timeout：{data.get('timeout')}s",
            f"Max Tokens：{data.get('max_tokens')}",
            f"Temperature：{data.get('temperature')}",
            f"失败重试：{data.get('retries')} 次，间隔 {data.get('retry_delay')}s",
            f"流式：{'支持' if data.get('stream_supported') else '不支持'}",
            f"工具调用：{'支持' if data.get('tool_calls_supported') else '不支持'}",
        ]
        if missing:
            lines.append("缺项：" + ", ".join(str(item) for item in missing))
        else:
            lines.append("缺项：无")
        return "\n".join(lines)

    def audit_report(self, limit: int = 20) -> str:
        entries = self._read_audit_entries(limit=limit)
        if not entries:
            return "暂无 AI 模型调用审计记录。"
        lines = [f"AI 模型调用审计：最近 {len(entries)} 条"]
        for item in entries:
            status = "OK" if item.get("ok") else "FAIL"
            mode = item.get("kind") or "answer"
            provider = item.get("provider") or "unknown"
            model = item.get("model") or "未配置"
            duration = item.get("duration_ms", 0)
            hits = item.get("hits", 0)
            tools = item.get("tool_calls", 0)
            text_chars = item.get("text_chars", 0)
            error = str(item.get("error") or "")
            suffix = f" error={error}" if error else ""
            lines.append(
                f"- {item.get('time', '')} [{status}] {mode} provider={provider} model={model} "
                f"hits={hits} tools={tools} chars={text_chars} {duration}ms{suffix}"
            )
        return "\n".join(lines)

    def _audit_result(
        self,
        kind: str,
        provider: AiProviderConfig,
        question: str,
        result: AiReplyResult,
        started: float,
        *,
        tool_calls: int = 0,
        model_error: str = "",
        stream: bool = False,
    ) -> None:
        if not bool(self.ctx.get_config("audit_enabled", True)):
            return
        entry: dict[str, Any] = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "kind": kind,
            "provider": provider.provider,
            "model": provider.model,
            "remote": _is_remote_provider(provider.provider),
            "stream": stream,
            "ok": bool(result.ok),
            "error": model_error or ("" if result.ok else result.text[:160]),
            "hits": len(result.hits),
            "tool_calls": int(tool_calls or 0),
            "text_chars": len(result.text or ""),
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        if bool(self.ctx.get_config("audit_question_preview", False)):
            entry["question_preview"] = question[:120]
        try:
            self.ctx.append_text("ai_calls.jsonl", json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as exc:
            self.ctx.log(f"AI 调用审计写入失败：{exc}", level="warning")

    def _read_audit_entries(self, *, limit: int = 20) -> list[dict[str, Any]]:
        raw = self.ctx.read_text("ai_calls.jsonl", "")
        rows: list[dict[str, Any]] = []
        for line in raw.splitlines()[-max(1, int(limit or 1)) :]:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
        return rows

    def _append_sources(self, text: str, hits: list[KnowledgeHit]) -> str:
        if not hits or not bool(self.ctx.get_config("show_sources", False)):
            return text
        lines = [text.rstrip(), "", "参考来源："]
        for index, hit in enumerate(hits, start=1):
            label = hit.title or hit.source or hit.chunk_id or "知识片段"
            detail = hit.source or hit.chunk_id
            if hit.source and hit.chunk_id:
                detail = f"{hit.source}#{hit.chunk_id}"
            score = f"score={hit.score}"
            suffix = f"（{detail}，{score}）" if detail else f"（{score}）"
            lines.append(f"[{index}] {label}{suffix}")
        return "\n".join(lines)

    def health_check(self) -> str:
        provider = resolve_provider_config(self._provider_config())
        provider_name = (provider.provider or "local_knowledge").strip().lower()
        knowledge = KnowledgeService(self.ctx.for_plugin("knowledge", config=self.ctx.config)).stats()
        checks: list[tuple[str, str]] = []

        if provider_name in {"", "local", "local_knowledge", "knowledge"}:
            checks.append(("OK", "本地知识库模式已启用，不需要外部模型配置。"))
        elif _is_remote_provider(provider_name):
            missing = []
            if not provider.base_url.strip():
                missing.append("base_url")
            if not provider.api_key.strip():
                missing.append("api_key")
            if not provider.model.strip():
                missing.append("model")
            if missing:
                checks.append(("TODO", "远程模型缺少配置：" + ", ".join(missing)))
            else:
                checks.append(("OK", "远程模型配置完整，可发起 OpenAI-compatible 调用。"))
        else:
            checks.append(("FAIL", f"不支持的 Provider：{provider.provider}"))

        if knowledge.chunks > 0:
            checks.append(("OK", f"本地知识库可检索：{knowledge.chunks} 个片段，{knowledge.documents} 个文档。"))
        else:
            checks.append(("WARN", "本地知识库为空，AI 回复无法获得本地上下文。"))

        if provider.timeout <= 0:
            checks.append(("FAIL", "timeout 必须大于 0。"))
        if provider.max_tokens <= 0:
            checks.append(("FAIL", "max_tokens 必须大于 0。"))
        if provider.retries < 0 or provider.retries > 3:
            checks.append(("FAIL", "retries 必须在 0 到 3 之间。"))
        if provider.retry_delay < 0:
            checks.append(("FAIL", "retry_delay 不能小于 0。"))

        ok = all(level in {"OK", "WARN"} for level, _ in checks)
        lines = [
            "AI 自检：",
            f"状态：{'通过' if ok else '待配置'}",
            f"Provider：{provider.provider or 'local_knowledge'}",
            f"Model：{provider.model or '未配置'}",
        ]
        lines.extend(f"[{level}] {message}" for level, message in checks)
        return "\n".join(lines)

    def probe_provider(self) -> str:
        provider = resolve_provider_config(self._provider_config())
        provider_name = (provider.provider or "local_knowledge").strip().lower()
        if not _is_remote_provider(provider_name):
            return "AI 试连：本地知识库模式不需要远程 Provider。"
        result = probe_ai_provider(provider, transport=self.transport)
        if result.ok:
            return f"AI 试连成功：{result.provider} / {result.model or '未配置模型'}，回复：{_clip(result.text, 120)}"
        return f"AI 试连失败：{result.provider} / {result.model or '未配置模型'}，{result.error or '未知错误'}"

    def _build_prompt(self, question: str, hits: list[KnowledgeHit], history: list[str] | None = None) -> str:
        lines = ["你是 Xiami QQ 机器人助手。"]
        if hits:
            lines.append("本地知识库上下文：")
            for index, hit in enumerate(hits, start=1):
                label = hit.title or hit.source or hit.chunk_id or "知识片段"
                lines.append(f"[{index}] {label}\n{hit.text}")
        else:
            lines.append("本地知识库未命中。")
        if history:
            lines.append("最近会话上下文：")
            for index, text in enumerate(history, start=1):
                lines.append(f"[H{index}] {text}")
        lines.append(f"用户问题：{question}")
        lines.append("请给出简洁、可执行的回答。")
        return "\n".join(lines)

    def _recent_history(self, event: Any | None, *, history_limit: int, current_question: str) -> list[str]:
        try:
            limit = max(0, int(history_limit))
        except (TypeError, ValueError):
            limit = 0
        if limit <= 0:
            return []
        rows = self.ctx.recent_messages(event, limit + 3)
        history: list[str] = []
        for row in rows:
            text = _record_text(row)
            if not text or text.strip() == current_question:
                continue
            label = _record_label(row)
            history.append(_clip(f"{label}: {text}", 240))
        return history[-limit:]

    def _tools_enabled(self) -> bool:
        return bool(self.ctx.get_config("enable_tools", True))

    def _run_tool_calls(
        self,
        calls: tuple[AiToolCall, ...],
        knowledge: KnowledgeService,
        *,
        default_limit: int,
    ) -> tuple[list[dict[str, Any]], list[KnowledgeHit]]:
        messages: list[dict[str, Any]] = []
        hits: list[KnowledgeHit] = []
        for call in calls[:3]:
            payload: dict[str, Any]
            if call.name == "knowledge_search":
                query = str(call.arguments.get("query") or call.arguments.get("q") or "").strip()
                limit = _bounded_int(call.arguments.get("limit"), default_limit, lower=1, upper=5)
                found = knowledge.search(query, limit=limit) if query else []
                hits.extend(found)
                payload = {
                    "ok": bool(found),
                    "query": query,
                    "hits": [
                        {
                            "title": hit.title,
                            "source": hit.source,
                            "score": hit.score,
                            "text": hit.text,
                        }
                        for hit in found
                    ],
                }
            elif call.name == "knowledge_stats":
                stats = knowledge.stats()
                payload = {
                    "ok": True,
                    "documents": stats.documents,
                    "sources": stats.sources,
                    "chunks": stats.chunks,
                    "characters": stats.characters,
                    "tags": stats.tags,
                }
            else:
                payload = {"ok": False, "error": f"unsupported tool: {call.name}"}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.name,
                    "content": json.dumps(payload, ensure_ascii=False),
                }
            )
        return messages, hits

    def _tool_fallback(self, hits: list[KnowledgeHit]) -> str:
        lines = ["AI 工具调用已执行，模型未返回最终文本；以下为本地工具结果："]
        for index, hit in enumerate(hits, start=1):
            label = hit.title or hit.source or "知识片段"
            lines.append(f"{index}. {label} score={hit.score}\n{hit.text}")
        return "\n".join(lines)

    def _provider_config(self) -> AiProviderConfig:
        provider_name = str(self.ctx.get_config("provider", "local_knowledge") or "local_knowledge")
        remote = _is_remote_provider(provider_name)
        timeout = _float_config(self.ctx.config, "timeout", 90.0 if remote else 20.0)
        retries = _int_config(self.ctx.config, "retries", 1 if remote else 0)
        retry_delay = _float_config(self.ctx.config, "retry_delay", 0.5 if remote else 0.0)
        if remote:
            timeout = max(60.0, timeout)
            retries = max(1, retries)
        return AiProviderConfig(
            provider=provider_name,
            api_key=str(self.ctx.get_config("api_key", "") or ""),
            base_url=str(self.ctx.get_config("base_url", "") or ""),
            model=str(self.ctx.get_config("model", "") or ""),
            temperature=_float_config(self.ctx.config, "temperature", 0.2),
            max_tokens=_int_config(self.ctx.config, "max_tokens", 800),
            timeout=timeout,
            retries=retries,
            retry_delay=retry_delay,
        )


def _is_remote_provider(provider: str) -> bool:
    return provider.strip().lower() in OPENAI_COMPATIBLE_PROVIDERS


def _ai_tool_specs() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "knowledge_search",
                "description": "Search Xiami local knowledge base before answering user questions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search keywords."},
                        "limit": {"type": "integer", "description": "Maximum number of hits, 1 to 5."},
                    },
                    "required": ["query"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "knowledge_stats",
                "description": "Get current Xiami local knowledge base statistics.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ]


def _assistant_tool_payloads(result: AiProviderResult) -> list[dict[str, Any]]:
    return [
        {
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.name,
                "arguments": call.raw_arguments or json.dumps(call.arguments, ensure_ascii=False),
            },
        }
        for call in result.tool_calls
    ]


def _merge_hits(primary: list[KnowledgeHit], extra: list[KnowledgeHit]) -> list[KnowledgeHit]:
    seen: set[tuple[str, str]] = set()
    merged: list[KnowledgeHit] = []
    for hit in [*primary, *extra]:
        key = (hit.source, hit.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        merged.append(hit)
    return merged


def _bounded_int(value: Any, default: int, *, lower: int, upper: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = int(default)
    return min(max(parsed, lower), upper)


def _int_config(config: dict[str, Any], key: str, default: int) -> int:
    try:
        return int(config.get(key, default))
    except (TypeError, ValueError):
        return default


def _float_config(config: dict[str, Any], key: str, default: float) -> float:
    try:
        return float(config.get(key, default))
    except (TypeError, ValueError):
        return default


def _friendly_model_error(error: str) -> str:
    raw = str(error or "").strip()
    lower = raw.lower()
    if "timed out" in lower or "timeout" in lower:
        return "AI 模型响应超时，请稍后重试；已自动把远程请求超时保护提高到 60 秒以上。"
    if raw.startswith("HTTP 401") or raw.startswith("HTTP 403"):
        return "AI 模型认证失败，请检查访问令牌是否正确。"
    if raw.startswith("HTTP 429"):
        return "AI 模型请求过于频繁，请稍后重试。"
    if raw:
        return f"AI 模型调用失败：{raw}"
    return "AI 模型调用失败：未知错误。"


def _record_text(record: Any) -> str:
    if isinstance(record, dict):
        return str(record.get("text") or record.get("message") or "").strip()
    return str(getattr(record, "text", "") or getattr(record, "message", "") or "").strip()


def _record_label(record: Any) -> str:
    if isinstance(record, dict):
        direction = str(record.get("direction") or "").strip()
        sender = str(record.get("sender") or "").strip()
        target = str(record.get("target") or "").strip()
    else:
        direction = str(getattr(record, "direction", "") or "").strip()
        sender = str(getattr(record, "sender", "") or "").strip()
        target = str(getattr(record, "target", "") or "").strip()
    if direction in {"outgoing", "plugin"}:
        return "我"
    return sender or target or "用户"


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."
