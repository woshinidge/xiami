from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ScaffoldResult:
    ok: bool
    plugin_id: str = ""
    path: Path | None = None
    message: str = ""


def create_plugin_scaffold(
    plugin_id: str,
    plugin_root: Path = Path("xiami_plugins"),
    *,
    name: str = "",
    command: str = "",
    kind: str = "command",
    description: str = "",
    overwrite: bool = False,
) -> ScaffoldResult:
    safe_id = _safe_plugin_id(plugin_id)
    if not safe_id:
        return ScaffoldResult(ok=False, message="invalid plugin id")
    scaffold_kind = kind.strip().lower() or "command"
    if scaffold_kind not in {"command", "event", "timer", "hybrid", "full"}:
        return ScaffoldResult(ok=False, plugin_id=safe_id, message="invalid scaffold kind")
    target = plugin_root / safe_id
    plugin_file = target / "plugin.py"
    if plugin_file.exists() and not overwrite:
        return ScaffoldResult(ok=False, plugin_id=safe_id, path=target, message="plugin already exists")
    target.mkdir(parents=True, exist_ok=True)

    display_name = name.strip() or safe_id.replace("_", " ").title()
    command_name = command.strip() or safe_id.replace("_", " ")
    plugin_file.write_text(
        _plugin_template(
            plugin_id=safe_id,
            name=display_name,
            command=command_name,
            kind=scaffold_kind,
            description=description.strip() or f"Migration scaffold for {display_name}.",
        ),
        encoding="utf-8",
    )
    (target / "plugin_config.json").write_text(
        "{\n  \"owners\": [],\n  \"admins\": [],\n  \"group_admins\": {},\n  \"cooldown_seconds\": 3\n}\n",
        encoding="utf-8",
    )
    (target / "README.md").write_text(
        _readme_template(plugin_id=safe_id, command=command_name, kind=scaffold_kind),
        encoding="utf-8",
    )
    return ScaffoldResult(ok=True, plugin_id=safe_id, path=target, message="plugin scaffold created")


def _plugin_template(plugin_id: str, name: str, command: str, kind: str, description: str) -> str:
    bodies: list[str] = []
    if kind in {"command", "hybrid", "full"}:
        bodies.append(_command_body(command))
    if kind in {"event", "hybrid", "full"}:
        bodies.append(_event_body())
    if kind in {"timer", "full"}:
        bodies.append(_timer_body())
    body = "\n\n".join(bodies)
    timer_import = "from xiami_core.plugins.compat import on_interval\n\n" if kind in {"timer", "full"} else ""
    schedules = "SCHEDULES = []\n" if kind in {"timer", "full"} else ""
    return f'''from __future__ import annotations

{timer_import}\
PLUGIN_ID = {plugin_id!r}
PLUGIN_NAME = {name!r}
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = {description!r}
PLUGIN_CONFIG = {{
    "owners": [],
    "admins": [],
    "group_admins": {{}},
    "cooldown_seconds": 3,
    "timer_seconds": 60,
}}
PLUGIN_CAPABILITIES = {_capabilities(kind)!r}
{schedules}\
PLUGIN_ADMIN_SCHEMA = [
    {{"id": "owners", "label": "Owners", "type": "config", "config_key": "owners"}},
    {{"id": "admins", "label": "Admins", "type": "config", "config_key": "admins"}},
    {{"id": "state", "label": "Plugin state", "type": "state", "state_key": "state"}},
    {{"id": "event_count", "label": "Event count", "type": "state", "state_key": "event_count"}},
    {{"id": "timer_count", "label": "Timer count", "type": "state", "state_key": "timer_count"}},
]


def on_load(ctx) -> None:
    ctx.log(f"{{PLUGIN_NAME}} loaded")


{body}
'''


def _command_body(command: str) -> str:
    return f'''\
def on_message(event, ctx) -> None:
    matched = ctx.match_command(event, {command!r})
    if not matched:
        return
    _, argument = matched
    if not ctx.require_admin(event, deny_text="permission denied"):
        return
    ok, remaining = ctx.check_cooldown("command", ctx.get_config_float("cooldown_seconds", 3.0), event=event)
    if not ok:
        ctx.reply(event, f"cooldown: {{remaining:.1f}}s")
        return
    count = ctx.increment_state("handled_count")
    ctx.update_state_dict("state", {{"last_user": ctx.user_id_of(event), "last_argument": argument}})
    ctx.reply(event, f"{{PLUGIN_NAME}} handled #{{count}}: {{argument or 'ok'}}")
'''


def _event_body() -> str:
    return '''\
def on_event(event, ctx) -> None:
    if event.post_type not in {"notice", "request"}:
        return
    count = ctx.increment_state("event_count")
    ctx.update_state_dict(
        "state",
        {
            "last_post_type": event.post_type,
            "last_notice_type": event.notice_type,
            "last_request_type": event.request_type,
            "last_user": event.user_id,
            "last_group": event.group_id,
        },
    )
    ctx.log(f"{PLUGIN_NAME} event #{count}: {event.post_type}/{event.notice_type or event.request_type}")
    if event.group_id:
        ctx.send_group(event.group_id, f"{PLUGIN_NAME} saw {event.post_type} #{count}")
'''


def _timer_body() -> str:
    return '''\
@on_interval(60, name="scaffold_timer", description="迁移脚手架定时任务")
def scaffold_timer(ctx, session) -> None:
    count = ctx.increment_state("timer_count")
    ctx.update_state_dict("state", {"last_timer": session.name, "last_timer_seconds": session.seconds})
    ctx.log(f"{PLUGIN_NAME} timer #{count}: {session.name}/{session.seconds}s")


SCHEDULES.append(scaffold_timer)
'''


def _capabilities(kind: str) -> list[str]:
    capabilities = ["migration:scaffold"]
    if kind in {"command", "hybrid", "full"}:
        capabilities.extend(["message:private", "message:group"])
    if kind in {"event", "hybrid", "full"}:
        capabilities.extend(["event:notice", "event:request"])
    if kind in {"timer", "full"}:
        capabilities.append("schedule:timer")
    return capabilities


def _readme_template(plugin_id: str, command: str, kind: str) -> str:
    features: list[str] = []
    if kind in {"command", "hybrid", "full"}:
        features.append(f"- Command: `{command} <argument>`")
    if kind in {"event", "hybrid", "full"}:
        features.append("- Event hook: `on_event(event, ctx)` for OneBot notice/request migration")
    if kind in {"timer", "full"}:
        features.append("- Timer hook: `@on_interval(60, name=\"scaffold_timer\")` in `SCHEDULES`")
    feature_text = "\n".join(features)
    return f"""# {plugin_id}

Generated Xiami plugin migration scaffold.

- Kind: `{kind}`
{feature_text}
- Configure owners/admins in `plugin_config.json` or the Xiami plugin admin UI.
- The template demonstrates command matching, event hooks, permission checks, cooldowns, state counters, and admin state exposure.
"""


def _safe_plugin_id(value: str) -> str:
    text = value.strip().replace(" ", "_")
    return "".join(ch for ch in text if ch.isalnum() or ch in {"_", "-"})[:80]
