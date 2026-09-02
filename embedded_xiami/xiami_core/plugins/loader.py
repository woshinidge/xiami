from __future__ import annotations

import importlib.util
import json
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType
from typing import Any

from xiami_core.models import XiamiMessage
from xiami_core.plugins.async_utils import resolve_awaitable
from xiami_core.plugins.compat import (
    CommandHookSession,
    IntervalSession,
    call_command_hook_handler,
    call_interval_handler,
)
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.events import PluginEvent
from xiami_core.plugins.group_settings import plugin_enabled_for_group
from xiami_core.plugins.legacy import dispatch_legacy_handlers
from xiami_core.plugins.legacy_file import (
    LegacyFileRuntime,
    build_legacy_file_runtime,
    dispatch_legacy_file_event,
    dispatch_legacy_file_message,
    legacy_file_admin_schema,
    looks_like_legacy_file_plugin,
)
from xiami_core.plugins.legacy_hooks import dispatch_legacy_hook_handlers
from xiami_core.plugins.state import PluginStateStore
from xiami_core.storage.paths import atomic_write_json


@dataclass
class LoadedPlugin:
    id: str
    name: str
    path: Path
    description: str = ""
    version: str = ""
    module: ModuleType | None = None
    legacy_file: LegacyFileRuntime | None = None
    enabled: bool = True
    error: str = ""
    context: PluginContext | None = None
    config: dict[str, Any] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    config_schema: list[dict[str, Any]] = field(default_factory=list)
    admin_schema: list[dict[str, Any]] = field(default_factory=list)
    message_count: int = 0
    event_count: int = 0
    message_handled_count: int = 0
    message_unhandled_count: int = 0
    event_handled_count: int = 0
    event_unhandled_count: int = 0
    error_count: int = 0
    last_error: str = ""
    error_history: list[str] = field(default_factory=list)
    matcher_hit_count: dict[str, int] = field(default_factory=dict)


@dataclass
class ConfigValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


class PluginLoader:
    def __init__(
        self,
        plugin_root: Path,
        context: PluginContext,
        state_store: PluginStateStore | None = None,
        user_config_root: Path | None = None,
    ) -> None:
        self.plugin_root = plugin_root
        self.context = context
        self.state_store = state_store or PluginStateStore()
        self.user_config_root = Path(user_config_root) if user_config_root is not None else None
        self.plugins: list[LoadedPlugin] = []

    def discover(self) -> list[Path]:
        if not self.plugin_root.exists():
            return []
        return sorted(path for path in self.plugin_root.iterdir() if (path / "plugin.py").exists())

    def load_all(self) -> list[LoadedPlugin]:
        self.plugins = []
        for plugin_dir in self.discover():
            plugin_id = plugin_dir.name
            try:
                plugin = self._load_plugin(plugin_dir)
            except Exception as exc:
                error = str(exc)
                plugin = LoadedPlugin(
                    id=plugin_id,
                    name=plugin_id,
                    path=plugin_dir,
                    enabled=False,
                    error=error,
                    error_count=1,
                    last_error=error,
                    error_history=[error],
                )
            self.plugins.append(plugin)
            if plugin.enabled and plugin.module and plugin.context:
                hook = getattr(plugin.module, "on_load", None)
                if callable(hook):
                    try:
                        resolve_awaitable(hook(plugin.context))
                    except Exception as exc:
                        _record_plugin_error(plugin, "on_load 失败", exc)
                        plugin.enabled = False
            if plugin.enabled:
                try:
                    _register_plugin_schedules(plugin)
                except Exception as exc:
                    _record_plugin_error(plugin, "定时任务注册失败", exc)
        for plugin_file in _legacy_file_plugin_files(self.plugin_root):
            plugin_id = plugin_file.stem
            try:
                plugin = self._load_legacy_file_plugin(plugin_file)
            except Exception as exc:
                error = f"旧文件式插件加载失败：{exc}"
                plugin = LoadedPlugin(
                    id=plugin_id,
                    name=plugin_id,
                    path=plugin_file,
                    enabled=False,
                    error=error,
                    capabilities=["legacy-file-plugin"],
                    error_count=1,
                    last_error=error,
                    error_history=[error],
                )
            if plugin.enabled and plugin.module and plugin.context:
                hook = getattr(plugin.module, "on_load", None)
                if callable(hook):
                    try:
                        resolve_awaitable(hook(plugin.context))
                    except Exception as exc:
                        _record_plugin_error(plugin, "on_load 失败", exc)
                        plugin.enabled = False
                if plugin.enabled:
                    try:
                        _register_plugin_schedules(plugin)
                    except Exception as exc:
                        _record_plugin_error(plugin, "定时任务注册失败", exc)
            self.plugins.append(plugin)
        _publish_plugin_catalog(self)
        return self.plugins

    def dispatch_message(self, event: XiamiMessage) -> None:
        try:
            for plugin in list(self.plugins):
                if not plugin.enabled or not plugin.module or not plugin.context:
                    continue
                if not self._plugin_allowed_for_group(plugin, event):
                    continue
                try:
                    handled = self._dispatch_message_to_plugin(plugin, event)
                    plugin.message_count += 1
                    if handled:
                        plugin.message_handled_count += 1
                    else:
                        plugin.message_unhandled_count += 1
                except Exception as exc:
                    _record_plugin_error(plugin, "消息处理失败", exc)
        finally:
            _publish_plugin_catalog(self)

    def _plugin_allowed_for_group(self, plugin: LoadedPlugin, event: XiamiMessage) -> bool:
        if event.message_type != "group":
            return True
        group_id = str(event.target or "").strip()
        if not group_id:
            return True
        return plugin_enabled_for_group(self.context, group_id, plugin.id, default=False)

    def dispatch_event(self, event: PluginEvent) -> None:
        try:
            for plugin in list(self.plugins):
                if not plugin.enabled or not plugin.module or not plugin.context:
                    continue
                if not self._plugin_allowed_for_plugin_event(plugin, event):
                    continue
                try:
                    handled = self._dispatch_event_to_plugin(plugin, event)
                    plugin.event_count += 1
                    if handled:
                        plugin.event_handled_count += 1
                    else:
                        plugin.event_unhandled_count += 1
                except Exception as exc:
                    _record_plugin_error(plugin, "事件处理失败", exc)
        finally:
            _publish_plugin_catalog(self)

    def _plugin_allowed_for_plugin_event(self, plugin: LoadedPlugin, event: PluginEvent) -> bool:
        group_id = str(event.group_id or "").strip()
        if not group_id:
            return True
        return plugin_enabled_for_group(self.context, group_id, plugin.id, default=False)

    def reload(self) -> list[LoadedPlugin]:
        return self.load_all()

    def set_enabled(self, plugin_id: str, enabled: bool) -> None:
        state = self.state_store.load()
        state[plugin_id] = enabled
        matched = []
        for plugin in self.plugins:
            if plugin.id == plugin_id:
                state[plugin.path.name] = enabled
                matched.append(plugin)
        self.state_store.save(state)
        for plugin in matched:
            plugin.enabled = enabled
        _publish_plugin_catalog(self)

    def plugin_dir(self, plugin_id: str) -> Path:
        return self.plugin_root / plugin_id

    def default_config(self, plugin_id: str) -> dict[str, Any]:
        plugin_dir = self.plugin_dir(plugin_id)
        if not (plugin_dir / "plugin.py").exists():
            return {}
        try:
            module = _load_module(plugin_id, plugin_dir / "plugin.py")
        except Exception:
            return {}
        value = getattr(module, "PLUGIN_CONFIG", {})
        return value.copy() if isinstance(value, dict) else {}

    def config_schema(self, plugin_id: str) -> list[dict[str, Any]]:
        plugin_dir = self.plugin_dir(plugin_id)
        if not (plugin_dir / "plugin.py").exists():
            return []
        try:
            module = _load_module(plugin_id, plugin_dir / "plugin.py")
        except Exception:
            return []
        return _plugin_config_schema(module, self.default_config(plugin_id))

    def validate_user_config(self, plugin_id: str, config: dict[str, Any]) -> ConfigValidationResult:
        if not isinstance(config, dict):
            return ConfigValidationResult(False, ["配置必须是 JSON 对象"])
        merged = self.default_config(plugin_id)
        merged.update(config)
        errors = _validate_config_with_schema(merged, self.config_schema(plugin_id))
        return ConfigValidationResult(not errors, errors)

    def user_config(self, plugin_id: str) -> dict[str, Any]:
        return self._read_user_config(str(plugin_id), self.plugin_dir(plugin_id))

    def save_user_config(self, plugin_id: str, config: dict[str, Any]) -> None:
        plugin_dir = self.plugin_dir(plugin_id)
        if not plugin_dir.exists():
            raise FileNotFoundError(f"plugin not found: {plugin_id}")
        validation = self.validate_user_config(plugin_id, config)
        if not validation.ok:
            raise ValueError("；".join(validation.errors))
        path = self._user_config_path(str(plugin_id), plugin_dir)
        atomic_write_json(path, config)

    def _user_config_path(self, plugin_id: str, plugin_dir: Path) -> Path:
        if self.user_config_root is None:
            return plugin_dir / "plugin_config.json"
        safe_id = str(plugin_id or plugin_dir.name).strip()
        if not safe_id or safe_id in {".", ".."} or any(ch in safe_id for ch in '<>:"/\\|?*'):
            raise ValueError("invalid plugin id")
        return self.user_config_root / f"{safe_id}.json"

    def _read_user_config(self, plugin_id: str, plugin_dir: Path) -> dict[str, Any]:
        legacy_path = plugin_dir / "plugin_config.json"
        path = self._user_config_path(plugin_id, plugin_dir)
        if path != legacy_path and path.is_file():
            return _read_plugin_config_file(path)
        legacy = _read_plugin_config_file(legacy_path)
        if legacy and path != legacy_path:
            atomic_write_json(path, legacy)
        return legacy

    def diagnostics(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for plugin in self.plugins:
            result.append(
                {
                    "id": plugin.id,
                    "name": plugin.name,
                    "enabled": plugin.enabled,
                    "error": plugin.error,
                    "message_count": plugin.message_count,
                    "event_count": plugin.event_count,
                    "message_handled_count": plugin.message_handled_count,
                    "message_unhandled_count": plugin.message_unhandled_count,
                    "event_handled_count": plugin.event_handled_count,
                    "event_unhandled_count": plugin.event_unhandled_count,
                "error_count": plugin.error_count,
                "last_error": plugin.last_error,
                "error_history": list(plugin.error_history),
                "logs": list(plugin.context.logs[-20:]) if plugin.context else [],
                "recent_logs": plugin.context.recent_logs(20) if plugin.context else [],
                "log_file": str(plugin.context.log_file()) if plugin.context else "",
                "matcher_hit_count": dict(plugin.matcher_hit_count),
                "commands": list(plugin.commands),
                "capabilities": list(plugin.capabilities),
                "config_schema": list(plugin.config_schema),
                "admin_schema": list(plugin.admin_schema),
                    "admin_state_preview": _plugin_admin_state_preview(plugin.context, plugin.admin_schema),
                    "migration_status": _plugin_migration_status(plugin.capabilities, plugin.commands),
                }
            )
        return result

    def _load_plugin(self, plugin_dir: Path) -> LoadedPlugin:
        plugin_file = plugin_dir / "plugin.py"
        module = _load_module(plugin_dir.name, plugin_file)
        if looks_like_legacy_file_plugin(plugin_file):
            try:
                return self._loaded_legacy_file_plugin(module, plugin_dir.name, plugin_dir, plugin_file)
            except ValueError:
                pass

        plugin_id = str(getattr(module, "PLUGIN_ID", plugin_dir.name))
        config = _plugin_config(module, plugin_dir, self._read_user_config(plugin_id, plugin_dir))
        context = self.context.for_plugin(plugin_id, config=config)
        enabled = self.state_store.is_enabled(plugin_id) and self.state_store.is_enabled(plugin_dir.name)
        return LoadedPlugin(
            id=plugin_id,
            name=_plugin_text(module, "PLUGIN_NAME") or plugin_id,
            path=plugin_dir,
            description=_plugin_text(module, "PLUGIN_DESCRIPTION"),
            version=_plugin_text(module, "PLUGIN_VERSION"),
            module=module,
            enabled=enabled,
            context=context,
            config=config,
            commands=_plugin_commands(module),
            capabilities=_plugin_capabilities(module),
            config_schema=_plugin_config_schema(module, config),
            admin_schema=_plugin_admin_schema(module),
        )

    def _load_legacy_file_plugin(self, plugin_file: Path) -> LoadedPlugin:
        module = _load_module(plugin_file.stem, plugin_file)
        return self._loaded_legacy_file_plugin(module, plugin_file.stem, plugin_file, plugin_file)

    def _loaded_legacy_file_plugin(self, module: ModuleType, fallback_key: str, path: Path, plugin_file: Path) -> LoadedPlugin:
        runtime = build_legacy_file_runtime(module, fallback_key)
        context = self.context.for_plugin(runtime.spec.key, config={})
        return LoadedPlugin(
            id=runtime.spec.key,
            name=runtime.spec.name or runtime.spec.key,
            path=path,
            description=runtime.spec.description,
            module=module,
            legacy_file=runtime,
            enabled=self.state_store.is_enabled(runtime.spec.key) and self.state_store.is_enabled(fallback_key),
            context=context,
            commands=[
                *[f"旧文件hook:{hook}" for hook in _legacy_file_hooks(runtime)],
                *[f"旧文件定时:{label}" for label in _legacy_file_timer_labels(runtime)],
            ],
            capabilities=_legacy_file_capabilities(runtime),
            admin_schema=legacy_file_admin_schema(runtime),
        )

    def _dispatch_message_to_plugin(self, plugin: LoadedPlugin, event: XiamiMessage) -> bool:
        assert plugin.module is not None
        assert plugin.context is not None
        if plugin.legacy_file is not None:
            labels = dispatch_legacy_file_message(plugin.legacy_file, event, plugin.context)
            _record_matcher_hits(plugin, labels)
            return bool(labels)
        before = _context_snapshot(plugin.context)

        for hook_name in ("on_message", "handle_message"):
            hook = getattr(plugin.module, hook_name, None)
            if callable(hook):
                if _is_legacy_plugin(plugin.module):
                    dispatch_legacy_handlers([hook], event, plugin.context)
                else:
                    resolve_awaitable(hook(event, plugin.context))

        matchers = getattr(plugin.module, "MATCHERS", None)
        if matchers:
            _record_matcher_hits(plugin, _dispatch_matchers(matchers, event, plugin.context))
        handled = False
        command_hooks = getattr(plugin.module, "COMMAND_HOOKS", None)
        if command_hooks:
            handled, labels = _dispatch_command_hooks(command_hooks, event, plugin.context)
            _record_matcher_hits(plugin, labels)
        legacy_handlers = getattr(plugin.module, "LEGACY_MESSAGE_HANDLERS", None)
        if legacy_handlers:
            dispatch_legacy_handlers(legacy_handlers, event, plugin.context)
        hook_handlers = getattr(plugin.module, "LEGACY_HOOK_HANDLERS", None)
        if hook_handlers:
            _record_matcher_hits(plugin, dispatch_legacy_hook_handlers(hook_handlers, event, plugin.context))
        return _context_changed(plugin.context, before) or handled

    def _dispatch_event_to_plugin(self, plugin: LoadedPlugin, event: PluginEvent) -> bool:
        assert plugin.module is not None
        assert plugin.context is not None
        if plugin.legacy_file is not None:
            labels = dispatch_legacy_file_event(plugin.legacy_file, event, plugin.context)
            _record_matcher_hits(plugin, labels)
            return bool(labels)
        before = _context_snapshot(plugin.context)

        event_hook = getattr(plugin.module, "on_event", None)
        if callable(event_hook) and not getattr(event_hook, "__xiami_api_decorator__", False):
            if _is_legacy_plugin(plugin.module):
                dispatch_legacy_handlers([event_hook], event, plugin.context)
            else:
                resolve_awaitable(event_hook(event, plugin.context))

        if event.message:
            message_hook = getattr(plugin.module, "on_raw_message", None)
            if callable(message_hook):
                if _is_legacy_plugin(plugin.module):
                    dispatch_legacy_handlers([message_hook], event, plugin.context)
                else:
                    resolve_awaitable(message_hook(event, plugin.context))
        event_matchers = getattr(plugin.module, "EVENT_MATCHERS", None)
        if event_matchers:
            _record_matcher_hits(plugin, _dispatch_matchers(event_matchers, event, plugin.context))
        legacy_handlers = getattr(plugin.module, "LEGACY_EVENT_HANDLERS", None)
        if legacy_handlers:
            dispatch_legacy_handlers(legacy_handlers, event, plugin.context)
        hook_handlers = getattr(plugin.module, "LEGACY_HOOK_HANDLERS", None)
        if hook_handlers:
            _record_matcher_hits(plugin, dispatch_legacy_hook_handlers(hook_handlers, event, plugin.context))
        return _context_changed(plugin.context, before)


def _load_module(module_id: str, plugin_file: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"xiami_plugin_{module_id}", plugin_file)
    if not spec or not spec.loader:
        raise RuntimeError("无法加载插件模块")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _plugin_text(module: ModuleType, name: str) -> str:
    value = getattr(module, name, "")
    return value if isinstance(value, str) else ""


def _plugin_config(
    module: ModuleType,
    plugin_dir: Path,
    user_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = getattr(module, "PLUGIN_CONFIG", {})
    config = value.copy() if isinstance(value, dict) else {}
    if user_config is None:
        user_config = _read_plugin_config_file(plugin_dir / "plugin_config.json")
    config.update(user_config)
    return config


def _read_plugin_config_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        override = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError:
        return {}
    return override if isinstance(override, dict) else {}


def _record_matcher_hits(plugin: LoadedPlugin, labels: list[str]) -> None:
    for label in labels:
        plugin.matcher_hit_count[label] = plugin.matcher_hit_count.get(label, 0) + 1


def _matcher_label(matcher: object) -> str:
    for attr in ("__xiami_matcher__", "__xiami_interval__", "__xiami_command_hook__"):
        meta = getattr(matcher, attr, None)
        if isinstance(meta, dict):
            return str(meta.get("label") or meta.get("description") or "").strip()
    return ""


def _dispatch_matchers(matchers: object, event: object, context: PluginContext) -> list[str]:
    if not isinstance(matchers, list):
        return []
    hits: list[str] = []
    for matcher in list(matchers):
        if callable(matcher):
            before = _context_snapshot(context)
            resolve_awaitable(matcher(event, context))
            if _context_changed(context, before):
                label = _matcher_label(matcher)
                if label:
                    hits.append(label)
    return hits


def _dispatch_command_hooks(hooks: object, event: XiamiMessage, context: PluginContext) -> tuple[bool, list[str]]:
    if not isinstance(hooks, list):
        return False, []
    session = CommandHookSession(
        hook="command",
        message=event.text,
        message_type=event.message_type,
        user_id=event.sender,
        group_id=event.target if event.message_type == "group" else "",
        raw={
            "message_type": event.message_type,
            "user_id": event.sender,
            "group_id": event.target if event.message_type == "group" else "",
            "message": event.text,
            "raw_message": event.raw_message or event.text,
        },
    )
    for hook in list(hooks):
        if not callable(hook):
            continue
        result = call_command_hook_handler(hook, event, context, session)
        if _handle_command_hook_result(result, event, context):
            label = _matcher_label(hook)
            return True, [label] if label else []
    return False, []


def _handle_command_hook_result(result: Any, event: XiamiMessage, context: PluginContext) -> bool:
    if result is None or result is False:
        return False
    if isinstance(result, str):
        if result:
            context.reply(event, result)
        return True
    if isinstance(result, dict):
        handled = bool(result.get("handled", True))
        message = str(result.get("message") or "")
        if handled and message:
            context.reply(event, message)
        return handled
    if hasattr(result, "handled"):
        handled = bool(getattr(result, "handled"))
        message = str(getattr(result, "message", "") or "")
        if handled and message:
            context.reply(event, message)
        return handled
    return bool(result)


def _publish_plugin_catalog(loader: PluginLoader) -> None:
    registry = getattr(loader.context, "runtime_registry", None)
    if not isinstance(registry, dict):
        return
    catalog: list[dict[str, Any]] = []
    for plugin in loader.plugins:
        catalog.append(
            {
                "id": plugin.id,
                "name": plugin.name,
                "description": plugin.description,
                "version": plugin.version,
                "enabled": bool(plugin.enabled),
                "error": plugin.error,
                "commands": list(plugin.commands),
                "capabilities": list(plugin.capabilities),
                "admin_schema": list(plugin.admin_schema),
                "message_count": plugin.message_count,
                "event_count": plugin.event_count,
                "message_handled_count": plugin.message_handled_count,
                "message_unhandled_count": plugin.message_unhandled_count,
                "event_handled_count": plugin.event_handled_count,
                "event_unhandled_count": plugin.event_unhandled_count,
                "error_count": plugin.error_count,
                "last_error": plugin.last_error,
                "error_history": list(plugin.error_history),
                "matcher_hit_count": dict(plugin.matcher_hit_count),
                "migration_status": _plugin_migration_status(plugin.capabilities, plugin.commands),
            }
        )
    registry["plugins"] = catalog
    registry["plugin_catalog"] = catalog


def _register_plugin_schedules(plugin: LoadedPlugin) -> None:
    assert plugin.module is not None
    assert plugin.context is not None
    if plugin.legacy_file is not None:
        for timer in plugin.legacy_file.timers:
            session = IntervalSession(name=timer.name, seconds=timer.seconds)

            def callback(handler=timer.handler, context=plugin.context, session=session) -> None:
                call_interval_handler(handler, context, session)

            plugin.context.every(timer.name, timer.seconds, callback)
    schedules = getattr(plugin.module, "SCHEDULES", None)
    if not isinstance(schedules, list):
        return
    for schedule in list(schedules):
        if not callable(schedule):
            continue
        meta = getattr(schedule, "__xiami_interval__", None)
        if not isinstance(meta, dict):
            continue
        name = str(meta.get("name") or getattr(schedule, "__name__", "interval"))
        seconds = float(meta.get("seconds", 0))
        session = IntervalSession(name=name, seconds=seconds)

        def callback(schedule=schedule, context=plugin.context, session=session) -> None:
            call_interval_handler(schedule, context, session)

        plugin.context.every(name, seconds, callback)


def _context_snapshot(context: PluginContext) -> tuple[int, int, int]:
    return (len(context.logs), context.send_count, context.state_revision)


def _context_changed(context: PluginContext, snapshot: tuple[int, int, int]) -> bool:
    return (len(context.logs), context.send_count, context.state_revision) != snapshot


def _record_plugin_error(plugin: LoadedPlugin, stage: str, exc: Exception) -> None:
    message = f"{stage}：{exc}"
    plugin.error = message
    plugin.last_error = message
    plugin.error_count += 1
    plugin.error_history.append(message)
    if len(plugin.error_history) > 10:
        del plugin.error_history[:-10]


def _plugin_commands(module: ModuleType) -> list[str]:
    result: list[str] = []
    matchers: list[object] = []
    message_matchers = getattr(module, "MATCHERS", None)
    event_matchers = getattr(module, "EVENT_MATCHERS", None)
    if isinstance(message_matchers, list):
        matchers.extend(message_matchers)
    if isinstance(event_matchers, list):
        matchers.extend(event_matchers)
    schedules = getattr(module, "SCHEDULES", None)
    if isinstance(schedules, list):
        matchers.extend(schedules)
    command_hooks = getattr(module, "COMMAND_HOOKS", None)
    if isinstance(command_hooks, list):
        matchers.extend(command_hooks)
    for matcher in matchers:
        meta = getattr(matcher, "__xiami_matcher__", None)
        if not isinstance(meta, dict):
            meta = getattr(matcher, "__xiami_event__", None)
        if not isinstance(meta, dict):
            meta = getattr(matcher, "__xiami_interval__", None)
        if not isinstance(meta, dict):
            meta = getattr(matcher, "__xiami_command_hook__", None)
        if not isinstance(meta, dict):
            continue
        label = str(meta.get("label") or "").strip()
        if label:
            result.append(label)
    legacy_messages = getattr(module, "LEGACY_MESSAGE_HANDLERS", None)
    if isinstance(legacy_messages, list) and legacy_messages:
        result.append(f"旧消息处理器:{len(legacy_messages)}")
    legacy_events = getattr(module, "LEGACY_EVENT_HANDLERS", None)
    if isinstance(legacy_events, list) and legacy_events:
        result.append(f"旧事件处理器:{len(legacy_events)}")
    legacy_hooks = getattr(module, "LEGACY_HOOK_HANDLERS", None)
    if isinstance(legacy_hooks, dict) and legacy_hooks:
        for hook in sorted(str(key) for key in legacy_hooks):
            result.append(f"旧hook:{hook}")
    if _is_legacy_plugin(module):
        result.append("旧模式:hooks")
    return result


def _plugin_capabilities(module: ModuleType) -> list[str]:
    labels: list[str] = []
    declared = getattr(module, "PLUGIN_CAPABILITIES", None)
    if isinstance(declared, dict):
        declared = declared.values()
    if isinstance(declared, (list, tuple, set)):
        labels.extend(str(item).strip() for item in declared if str(item).strip())

    message_matchers = getattr(module, "MATCHERS", None)
    if isinstance(message_matchers, list) and message_matchers:
        labels.append(f"message-matchers:{len(message_matchers)}")

    event_matchers = getattr(module, "EVENT_MATCHERS", None)
    if isinstance(event_matchers, list) and event_matchers:
        labels.append(f"event-matchers:{len(event_matchers)}")

    schedules = getattr(module, "SCHEDULES", None)
    if isinstance(schedules, list) and schedules:
        labels.append(f"schedules:{len(schedules)}")
    command_hooks = getattr(module, "COMMAND_HOOKS", None)
    if isinstance(command_hooks, list) and command_hooks:
        labels.append(f"legacy-command-hooks:{len(command_hooks)}")
    legacy_messages = getattr(module, "LEGACY_MESSAGE_HANDLERS", None)
    if isinstance(legacy_messages, list) and legacy_messages:
        labels.append(f"legacy-message-handlers:{len(legacy_messages)}")
    legacy_events = getattr(module, "LEGACY_EVENT_HANDLERS", None)
    if isinstance(legacy_events, list) and legacy_events:
        labels.append(f"legacy-event-handlers:{len(legacy_events)}")
    legacy_hooks = getattr(module, "LEGACY_HOOK_HANDLERS", None)
    if isinstance(legacy_hooks, dict) and legacy_hooks:
        labels.append(f"legacy-hooks:{len(legacy_hooks)}")
        if "admin" in legacy_hooks:
            labels.append("legacy-admin-hook")
    if _is_legacy_plugin(module):
        labels.append("legacy-mode")

    for hook_name in ("on_load", "on_message", "handle_message", "on_event", "on_raw_message"):
        if callable(getattr(module, hook_name, None)):
            labels.append(hook_name)

    return _unique_labels(labels)


def _plugin_config_schema(module: ModuleType, config: dict[str, Any]) -> list[dict[str, Any]]:
    declared = getattr(module, "PLUGIN_CONFIG_SCHEMA", None)
    raw_items = declared.get("items", []) if isinstance(declared, dict) else declared
    if not isinstance(raw_items, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, str):
            key = item
            row: dict[str, Any] = {
                "key": key,
                "label": key,
                "type": _config_type_name(config.get(key)),
            }
            if key in config:
                row["default"] = config.get(key)
        elif isinstance(item, dict):
            key = _admin_text(item.get("key") or item.get("config_key") or item.get("id") or f"config_{index + 1}")
            row = {
                "key": key,
                "label": _admin_text(item.get("label") or item.get("name") or key),
                "type": _admin_text(item.get("type") or _config_type_name(config.get(key))),
                "description": _admin_text(item.get("description") or item.get("help")),
                "required": bool(item.get("required", False)),
                "secret": bool(item.get("secret", False)),
                "choices": _admin_string_list(item.get("choices") or item.get("options")),
            }
            if "default" in item:
                row["default"] = item.get("default")
            elif key in config:
                row["default"] = config.get(key)
        else:
            continue
        result.append({key: value for key, value in row.items() if value not in ("", [], None)})
    return result


def _plugin_admin_schema(module: ModuleType) -> list[dict[str, Any]]:
    declared = getattr(module, "PLUGIN_ADMIN_SCHEMA", None)
    raw_items = declared.get("items", []) if isinstance(declared, dict) else declared
    if not isinstance(raw_items, (list, tuple)):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw_items):
        if isinstance(item, str):
            normalized: dict[str, Any] = {"id": item, "label": item, "type": "state", "state_key": item}
        elif isinstance(item, dict):
                normalized = {
                    "id": _admin_text(item.get("id") or item.get("state_key") or item.get("config_key") or f"item_{index + 1}"),
                    "label": _admin_text(item.get("label") or item.get("name") or item.get("id") or f"管理项 {index + 1}"),
                    "type": _admin_text(item.get("type") or "state"),
                    "state_key": _admin_text(item.get("state_key")),
                    "config_key": _admin_text(item.get("config_key")),
                    "runtime_key": _admin_text(item.get("runtime_key") or item.get("runtime")),
                    "description": _admin_text(item.get("description")),
                    "commands": _admin_string_list(item.get("commands")),
                    "actions": _admin_string_list(item.get("actions")),
                }
        else:
            continue
        result.append({key: value for key, value in normalized.items() if value not in ("", [])})
    return result


def _plugin_admin_state_preview(context: PluginContext | None, schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if context is None or not schema:
        return []
    preview: list[dict[str, Any]] = []
    for item in schema:
        state_key = str(item.get("state_key") or "").strip()
        config_key = str(item.get("config_key") or "").strip()
        row: dict[str, Any] = {
            "id": str(item.get("id") or state_key or config_key),
            "label": str(item.get("label") or state_key or config_key),
            "type": str(item.get("type") or "state"),
        }
        if state_key:
            row.update({"state_key": state_key, **_admin_value_summary(context.get_state(state_key, None))})
        elif config_key:
            row.update({"config_key": config_key, **_admin_value_summary(context.get_config(config_key, None))})
        else:
            row.update({"summary": str(item.get("description") or "未绑定状态键"), "count": 0})
        preview.append(row)
    return preview


def _admin_value_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {"value_type": "missing", "count": 0, "summary": "未写入"}
    if isinstance(value, dict):
        return {"value_type": "dict", "count": len(value), "summary": f"{len(value)} 项"}
    if isinstance(value, (list, tuple, set)):
        return {"value_type": "list", "count": len(value), "summary": f"{len(value)} 项"}
    if isinstance(value, bool):
        return {"value_type": "bool", "count": 1 if value else 0, "summary": "开启" if value else "关闭"}
    if isinstance(value, (int, float)):
        return {"value_type": "number", "count": 1, "summary": str(value)}
    text = str(value)
    return {"value_type": "text", "count": 1 if text else 0, "summary": f"文本 {len(text)} 字"}


def _admin_text(value: Any) -> str:
    return str(value or "").strip()


def _admin_string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _validate_config_with_schema(config: dict[str, Any], schema: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    for item in schema:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        label = str(item.get("label") or key).strip()
        field_name = f"{label}({key})" if label != key else key
        required = bool(item.get("required", False))
        present = key in config and config.get(key) is not None and config.get(key) != ""
        if required and not present:
            errors.append(f"{field_name} 必填")
            continue
        if key not in config or config.get(key) is None:
            continue
        value = config.get(key)
        expected = str(item.get("type") or "").strip().lower()
        if expected and not _config_value_matches_type(value, expected):
            errors.append(f"{field_name} 应为 {expected}")
            continue
        choices = item.get("choices") or []
        if choices:
            allowed = {str(choice) for choice in choices}
            if isinstance(value, list):
                invalid = [str(entry) for entry in value if str(entry) not in allowed]
            else:
                invalid = [] if str(value) in allowed else [str(value)]
            if invalid:
                errors.append(f"{field_name} 不在允许选项内：{', '.join(sorted(allowed))}")
    return errors


def _config_value_matches_type(value: Any, expected: str) -> bool:
    if expected in {"any", "json"}:
        return True
    if expected in {"str", "string", "text"}:
        return isinstance(value, str)
    if expected in {"bool", "boolean"}:
        return isinstance(value, bool)
    if expected in {"int", "integer"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected in {"float", "number"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected in {"list", "array"}:
        return isinstance(value, list)
    if expected in {"dict", "object", "map"}:
        return isinstance(value, dict)
    return True


def _config_type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "str"


def _plugin_migration_status(capabilities: list[str], commands: list[str]) -> str:
    if any(item.startswith("legacy-") for item in capabilities):
        return "旧插件兼容接入"
    if capabilities or commands:
        return "Xiami 原生接入"
    return "未声明能力"


def _legacy_file_plugin_files(plugin_root: Path) -> list[Path]:
    if not plugin_root.exists():
        return []
    return sorted(path for path in plugin_root.glob("*.py") if looks_like_legacy_file_plugin(path))


def _legacy_file_capabilities(runtime: LegacyFileRuntime) -> list[str]:
    labels = ["legacy-file-plugin"]
    specs = list((runtime.specs or {runtime.spec.key: runtime.spec}).values())
    if any("admin" in spec.hooks for spec in specs):
        labels.append("legacy-admin-hook")
    if any(spec.admin_path for spec in specs):
        labels.append("legacy-admin-path")
    if runtime.timers:
        labels.append(f"legacy-schedules:{len(runtime.timers)}")
    labels.extend(f"legacy-service:{service}" for spec in specs for service in spec.services)
    return _unique_labels(labels)


def _legacy_file_hooks(runtime: LegacyFileRuntime) -> list[str]:
    specs = list((runtime.specs or {runtime.spec.key: runtime.spec}).values())
    return _unique_labels([hook for spec in specs for hook in spec.hooks])


def _legacy_file_timer_labels(runtime: LegacyFileRuntime) -> list[str]:
    return _unique_labels(
        [
            f"{timer.name}/{timer.seconds:g}s" + (f" - {timer.description}" if timer.description else "")
            for timer in runtime.timers
        ]
    )


def _is_legacy_plugin(module: ModuleType) -> bool:
    mode = str(getattr(module, "PLUGIN_MODE", "") or getattr(module, "PLUGIN_COMPAT", "")).strip().lower()
    return mode in {"legacy", "onebot", "onebot-v11", "cqhttp", "cq-http"}


def _unique_labels(labels: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for label in labels:
        value = str(label).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
