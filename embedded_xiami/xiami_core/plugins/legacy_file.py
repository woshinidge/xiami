from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

from xiami_core.models import XiamiMessage
from xiami_core.plugins.async_utils import resolve_awaitable
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.legacy_hooks import legacy_hook_context, legacy_hook_names

try:
    from xiami_onebot.plugins.context import PluginEventContext
except Exception:  # pragma: no cover - fallback only when old package is absent

    @dataclass(frozen=True)
    class PluginEventContext:  # type: ignore[no-redef]
        hook: str
        event: dict[str, Any]
        group_id: str = ""
        user_id: str = ""
        message: str = ""


@dataclass(frozen=True)
class LegacyFileSpec:
    key: str
    name: str
    description: str = ""
    hooks: tuple[str, ...] = ()
    services: tuple[str, ...] = ()
    admin_path: str = ""
    priority: int = 100
    block: bool = False


@dataclass(frozen=True)
class LegacyTimerSpec:
    name: str
    seconds: float
    handler: Callable[..., Any]
    description: str = ""
    plugin_key: str = ""


@dataclass
class LegacyFileRuntime:
    spec: LegacyFileSpec
    specs: dict[str, LegacyFileSpec]
    handlers: dict[str, Callable[[Any], Any]]
    timers: tuple[LegacyTimerSpec, ...] = ()


class LegacyFilePluginManager:
    def __init__(self) -> None:
        self.specs: dict[str, LegacyFileSpec] = {}
        self.handlers: dict[str, Callable[[Any], Any]] = {}
        self.timers: list[LegacyTimerSpec] = []

    def add_plugin(self, spec: Any) -> bool:
        item = coerce_legacy_spec(spec, "")
        if not item.key or item.key in self.specs:
            return False
        self.specs[item.key] = item
        return True

    def register_handler(self, key: str, handler: Callable[[Any], Any]) -> None:
        if key not in self.specs:
            raise KeyError(f"unknown plugin: {key}")
        self.handlers[key] = handler

    def register_timer(
        self,
        name: str,
        seconds: float,
        handler: Callable[..., Any],
        *,
        description: str = "",
        key: str = "",
    ) -> None:
        if not callable(handler):
            raise TypeError("legacy timer handler must be callable")
        interval = float(seconds)
        if interval <= 0:
            raise ValueError("legacy timer interval must be positive")
        timer_name = str(name or getattr(handler, "__name__", "legacy_timer")).strip() or "legacy_timer"
        plugin_key = str(key or "").strip()
        if plugin_key and plugin_key not in self.specs:
            raise KeyError(f"unknown plugin: {plugin_key}")
        self.timers.append(
            LegacyTimerSpec(
                name=timer_name,
                seconds=interval,
                handler=handler,
                description=str(description or ""),
                plugin_key=plugin_key,
            )
        )


def build_legacy_file_runtime(module: ModuleType, fallback_key: str) -> LegacyFileRuntime:
    manager = LegacyFilePluginManager()
    register = getattr(module, "register", None)
    spec: LegacyFileSpec | None = None
    try:
        spec = extract_legacy_spec(module, fallback_key)
        manager.add_plugin(spec)
    except ValueError:
        if not callable(register):
            raise
    if callable(register):
        register(manager)
    else:
        if spec is None:
            raise ValueError("legacy file plugin must expose plugin_spec or XiamiPlugin instance")
        handler = _default_handler(module)
        if handler:
            manager.register_handler(spec.key, handler)
    if not manager.specs:
        raise ValueError("legacy file plugin must expose plugin_spec, XiamiPlugin instance, or register plugins")
    primary = spec if spec is not None and spec.key in manager.specs else _primary_spec(manager, fallback_key)
    return LegacyFileRuntime(
        spec=primary,
        specs=dict(manager.specs),
        handlers=dict(manager.handlers),
        timers=tuple(manager.timers),
    )


def extract_legacy_spec(module: ModuleType, fallback_key: str) -> LegacyFileSpec:
    raw = getattr(module, "plugin_spec", None)
    if raw is not None and not isinstance(raw, property):
        spec = coerce_legacy_spec(raw, fallback_key)
        if spec.hooks:
            return spec
    if raw is None or isinstance(raw, property):
        for value in vars(module).values():
            raw = getattr(value, "plugin_spec", None)
            if raw is None or isinstance(raw, property):
                continue
            spec = coerce_legacy_spec(raw, fallback_key)
            if spec.hooks:
                return spec
    return coerce_legacy_spec(raw, fallback_key)


def coerce_legacy_spec(raw: Any, fallback_key: str) -> LegacyFileSpec:
    if isinstance(raw, dict):
        return LegacyFileSpec(
            key=str(raw.get("key") or fallback_key),
            name=str(raw.get("name") or fallback_key),
            description=str(raw.get("description") or ""),
            hooks=tuple(str(item) for item in raw.get("hooks", ()) if str(item).strip()),
            services=tuple(str(item) for item in raw.get("services", ()) if str(item).strip()),
            admin_path=str(raw.get("admin_path") or ""),
            priority=_int_value(raw.get("priority"), 100),
            block=bool(raw.get("block", False)),
        )
    if raw is not None:
        return LegacyFileSpec(
            key=str(getattr(raw, "key", "") or fallback_key),
            name=str(getattr(raw, "name", "") or fallback_key),
            description=str(getattr(raw, "description", "") or ""),
            hooks=tuple(str(item) for item in getattr(raw, "hooks", ()) if str(item).strip()),
            services=tuple(str(item) for item in getattr(raw, "services", ()) if str(item).strip()),
            admin_path=str(getattr(raw, "admin_path", "") or ""),
            priority=_int_value(getattr(raw, "priority", 100), 100),
            block=bool(getattr(raw, "block", False)),
        )
    raise ValueError("legacy file plugin must expose plugin_spec or XiamiPlugin instance")


def dispatch_legacy_file_message(runtime: LegacyFileRuntime, event: XiamiMessage, ctx: PluginContext) -> list[str]:
    return _dispatch(runtime, event, ctx, legacy_hook_names(event))


def dispatch_legacy_file_event(runtime: LegacyFileRuntime, event: PluginEvent, ctx: PluginContext) -> list[str]:
    return _dispatch(runtime, event, ctx, legacy_hook_names(event))


def _dispatch(runtime: LegacyFileRuntime, event: XiamiMessage | PluginEvent, ctx: PluginContext, hooks: list[str]) -> list[str]:
    hits: list[str] = []
    specs = runtime.specs or {runtime.spec.key: runtime.spec}
    for hook in hooks:
        hook_context = legacy_hook_context(hook, event)
        context = PluginEventContext(
            hook=hook_context.hook,
            event=dict(hook_context.event),
            group_id=hook_context.group_id,
            user_id=hook_context.user_id,
            message=hook_context.message,
        )
        for spec in specs.values():
            if hook not in spec.hooks:
                continue
            handler = runtime.handlers.get(spec.key)
            if not handler:
                continue
            result = resolve_awaitable(handler(context))
            if _handled(result):
                message = _result_message(result)
                if message and isinstance(event, XiamiMessage):
                    ctx.reply(event, message)
                hits.append(f"legacy-file:{hook}")
    return hits


def _primary_spec(manager: LegacyFilePluginManager, fallback_key: str) -> LegacyFileSpec:
    if fallback_key in manager.specs:
        return manager.specs[fallback_key]
    return next(iter(manager.specs.values()))

def _default_handler(module: ModuleType) -> Callable[[Any], Any] | None:
    for name in ("handle", "handler", "on_event"):
        handler = getattr(module, name, None)
        if callable(handler):
            return handler
    return None


def _handled(result: Any) -> bool:
    if hasattr(result, "handled"):
        return bool(getattr(result, "handled"))
    if isinstance(result, bool):
        return result
    if isinstance(result, str):
        return bool(result)
    if isinstance(result, dict):
        return bool(result.get("handled"))
    return False


def _result_message(result: Any) -> str:
    if isinstance(result, str):
        return result
    if hasattr(result, "message"):
        return str(getattr(result, "message") or "")
    if isinstance(result, dict):
        return str(result.get("message") or "")
    return ""


def looks_like_legacy_file_plugin(path: Path) -> bool:
    if path.name == "__init__.py" or path.suffix != ".py":
        return False
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    markers = ("XiamiPlugin", "PluginSpec", "plugin_spec", "register(", "def handle(", "def handler(", "def on_event(")
    return any(marker in source for marker in markers)


def legacy_file_admin_schema(runtime: LegacyFileRuntime) -> list[dict[str, Any]]:
    specs = list((runtime.specs or {runtime.spec.key: runtime.spec}).values())
    admin_specs = [spec for spec in specs if "admin" in spec.hooks or spec.admin_path]
    if not admin_specs:
        return []
    description_parts: list[str] = []
    for spec in admin_specs:
        if spec.admin_path:
            label = spec.name or spec.key
            description_parts.append(f"{label} 旧后台路径：{spec.admin_path}")
    if any("admin" in spec.hooks for spec in admin_specs):
        description_parts.append("旧 admin hook 已识别；请迁移为 PLUGIN_ADMIN_SCHEMA 管理项。")
    services = _unique([service for spec in admin_specs for service in spec.services])
    if services:
        description_parts.append("旧服务：" + ", ".join(services))
    return [
        {
            "id": "legacy_admin_path",
            "label": "旧后台入口",
            "type": "legacy-admin",
            "description": "；".join(description_parts) or "旧插件后台入口待迁移。",
            "actions": ["migrate-to-plugin-admin-schema"],
        }
    ]


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
