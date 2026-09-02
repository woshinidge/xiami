from __future__ import annotations

from typing import Any

from xiami_core.plugins.context import PluginContext


DEFAULT_NOTICE_TEMPLATES = {
    "event": "[{label}] 群：{group} QQ：{qq}\n{detail}",
    "friend": "[{label}] QQ：{qq}\n{detail}",
    "join": "[{label}] 群：{group} QQ：{qq}\n入群成员：{target}\n{detail}",
    "leave": "[{label}] 群：{group} QQ：{qq}\n退群成员：{target}\n{detail}",
    "invite": "[{label}] 群：{group} QQ：{qq}\n邀请人：{inviter}\n邀请奖励：{reward}",
    "review": "[{label}] 群：{group} QQ：{qq}\n{detail}",
}

DEFAULT_NOTICE_SWITCHES = {
    "event": True,
    "friend": True,
    "join": True,
    "leave": True,
    "invite": True,
    "review": True,
}


class _SafeFields(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _bool_value(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on", "enable", "enabled", "开", "开启", "启用"}:
            return True
        if lowered in {"0", "false", "no", "off", "disable", "disabled", "关", "关闭", "禁用"}:
            return False
    return bool(default)


def normalize_notice_templates(value: object) -> dict[str, str]:
    templates = dict(DEFAULT_NOTICE_TEMPLATES)
    if isinstance(value, dict):
        for key, raw in value.items():
            key_text = str(key).strip()
            if key_text:
                templates[key_text] = str(raw)
    return templates


def normalize_notice_switches(value: object) -> dict[str, bool]:
    switches = dict(DEFAULT_NOTICE_SWITCHES)
    if isinstance(value, dict):
        for key, raw in value.items():
            key_text = str(key).strip()
            if key_text:
                switches[key_text] = _bool_value(raw, default=True)
    return switches


def refresh_notice_template_state(ctx: PluginContext) -> None:
    ctx.set_state("notice_templates", normalize_notice_templates(ctx.get_config("notice_templates", {})))
    ctx.set_state("notice_switches", normalize_notice_switches(ctx.get_config("notice_switches", {})))


def notice_template_enabled(ctx: PluginContext, key: str) -> bool:
    template_ctx = ctx.for_plugin("help_menu")
    raw_switches = template_ctx.get_state("notice_switches", {})
    switches = normalize_notice_switches(raw_switches)
    return bool(switches.get(str(key), True))


def render_notice_template(ctx: PluginContext, key: str, fallback: str, **values: Any) -> str:
    template_ctx = ctx.for_plugin("help_menu")
    raw_templates = template_ctx.get_state("notice_templates", {})
    if not isinstance(raw_templates, dict):
        raw_templates = {}
    template = str(raw_templates.get(key) or "")
    if not template or template == DEFAULT_NOTICE_TEMPLATES.get(key):
        template = fallback
    fields = _SafeFields({name: "" if value is None else str(value) for name, value in values.items()})
    try:
        rendered = str(template).format_map(fields)
    except (KeyError, IndexError, ValueError):
        rendered = fallback.format_map(fields)
    return rendered.strip()
