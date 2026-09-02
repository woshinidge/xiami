from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from xiami_core.plugins.context import PluginContext


@dataclass(frozen=True)
class SettingSpec:
    key: str
    label: str
    plugin_id: str
    state_key: str
    config_key: str
    default: bool


@dataclass(frozen=True)
class NumberSpec:
    key: str
    label: str
    plugin_id: str
    state_key: str
    config_key: str
    default: int


BOOLEAN_SETTINGS = {
    "invite_points_enabled": SettingSpec(
        "invite_points_enabled",
        "邀请积分",
        "invites",
        "invite_points_enabled",
        "invite_points_enabled",
        True,
    ),
    "quiz_enabled": SettingSpec("quiz_enabled", "答题", "quiz", "quiz_enabled", "quiz_enabled", True),
    "custom_replies_enabled": SettingSpec(
        "custom_replies_enabled",
        "自定义回复",
        "custom_replies",
        "custom_replies_enabled",
        "custom_replies_enabled",
        True,
    ),
    "ai_reply_enabled": SettingSpec(
        "ai_reply_enabled",
        "AI回答",
        "ai_reply",
        "ai_reply_enabled",
        "ai_reply_enabled",
        True,
    ),
    "ai_ordinary_chat_enabled": SettingSpec(
        "ai_ordinary_chat_enabled",
        "AI普通聊天",
        "ai_reply",
        "ordinary_chat_enabled",
        "ordinary_chat_enabled",
        True,
    ),
    "ai_at_bot_enabled": SettingSpec(
        "ai_at_bot_enabled",
        "AI@触发",
        "ai_reply",
        "at_bot_enabled",
        "at_bot_enabled",
        True,
    ),
    "cards_enabled": SettingSpec("cards_enabled", "卡密兑换", "cards", "cards_enabled", "cards_enabled", True),
    "bindings_enabled": SettingSpec("bindings_enabled", "账号绑定", "bindings", "bindings_enabled", "bindings_enabled", True),
    "member_guard_enabled": SettingSpec(
        "member_guard_enabled",
        "名单风控",
        "member_guard",
        "member_guard_enabled",
        "member_guard_enabled",
        True,
    ),
    "blacklist_kick_enabled": SettingSpec(
        "blacklist_kick_enabled",
        "黑名单踢出",
        "member_guard",
        "blacklist_kick",
        "blacklist_kick",
        True,
    ),
    "forbidden_recall_enabled": SettingSpec(
        "forbidden_recall_enabled",
        "违禁词撤回",
        "member_guard",
        "forbidden_recall_enabled",
        "forbidden_recall_enabled",
        True,
    ),
    "blacklist_recall_enabled": SettingSpec(
        "blacklist_recall_enabled",
        "黑名单发言撤回",
        "member_guard",
        "blacklist_recall_enabled",
        "blacklist_recall_enabled",
        True,
    ),
    "blacklist_kick_notice_enabled": SettingSpec(
        "blacklist_kick_notice_enabled",
        "踢出时通知",
        "member_guard",
        "blacklist_kick_notice_enabled",
        "blacklist_kick_notice_enabled",
        True,
    ),
    "group_number_recall_enabled": SettingSpec(
        "group_number_recall_enabled",
        "群号撤回",
        "member_guard",
        "group_number_recall_enabled",
        "group_number_recall_enabled",
        False,
    ),
    "auto_recall_enabled": SettingSpec(
        "auto_recall_enabled",
        "自动类型撤回",
        "member_guard",
        "auto_recall_enabled",
        "auto_recall_enabled",
        False,
    ),
    "leave_recall_enabled": SettingSpec(
        "leave_recall_enabled",
        "退群撤回",
        "member_guard",
        "leave_recall_enabled",
        "leave_recall_enabled",
        False,
    ),
    "bot_reply_recall_enabled": SettingSpec(
        "bot_reply_recall_enabled",
        "机器人全部回复自动撤回",
        "group_settings",
        "bot_reply_recall_enabled",
        "bot_reply_recall_enabled",
        False,
    ),
}

NUMBER_SETTINGS = {
    "invite_reward_points": NumberSpec(
        "invite_reward_points",
        "邀请奖励积分",
        "invites",
        "invite_reward_points",
        "invite_reward_points",
        1,
    ),
    "quiz_reward_points": NumberSpec("quiz_reward_points", "答题奖励积分", "quiz", "quiz_reward_points", "quiz_reward_points", 1),
    "forbidden_ban_seconds": NumberSpec(
        "forbidden_ban_seconds",
        "违禁词禁言秒数",
        "member_guard",
        "forbidden_ban_seconds",
        "forbidden_ban_seconds",
        600,
    ),
    "leave_recall_limit": NumberSpec(
        "leave_recall_limit",
        "退群撤回条数",
        "member_guard",
        "leave_recall_limit",
        "leave_recall_limit",
        20,
    ),
    "message_cache_limit_per_member": NumberSpec(
        "message_cache_limit_per_member",
        "成员消息缓存条数",
        "member_guard",
        "message_cache_limit_per_member",
        "message_cache_limit_per_member",
        50,
    ),
    "bot_reply_recall_seconds": NumberSpec(
        "bot_reply_recall_seconds",
        "机器人全部回复撤回秒数",
        "group_settings",
        "bot_reply_recall_seconds",
        "bot_reply_recall_seconds",
        30,
    ),
}

GROUP_PLUGIN_ENABLED_STATE_KEY = "plugin_enabled"


class GroupSettingService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def enabled(self, group_id: str, key: str) -> bool:
        spec = BOOLEAN_SETTINGS[key]
        value = self._plugin_group_settings(spec.plugin_id).get(str(group_id), {}).get(spec.state_key)
        if value is None:
            return bool(self.ctx.get_config(spec.config_key, spec.default))
        return bool(value)

    def set_enabled(self, group_id: str, key: str, enabled: bool) -> None:
        spec = BOOLEAN_SETTINGS[key]
        plugin_ctx = self.ctx.for_plugin(spec.plugin_id, config=self.ctx.config)
        settings = _dict_state(plugin_ctx.get_state("settings", {}))
        group_settings = settings.setdefault(str(group_id), {})
        group_settings[spec.state_key] = bool(enabled)
        plugin_ctx.set_state("settings", settings)

    def number(self, group_id: str, key: str) -> int:
        spec = NUMBER_SETTINGS[key]
        value = self._plugin_group_settings(spec.plugin_id).get(str(group_id), {}).get(spec.state_key)
        if value is None:
            value = self.ctx.get_config(spec.config_key, spec.default)
        return _positive_int(value, default=spec.default)

    def set_number(self, group_id: str, key: str, value: int) -> None:
        spec = NUMBER_SETTINGS[key]
        plugin_ctx = self.ctx.for_plugin(spec.plugin_id, config=self.ctx.config)
        settings = _dict_state(plugin_ctx.get_state("settings", {}))
        group_settings = settings.setdefault(str(group_id), {})
        group_settings[spec.state_key] = _positive_int(value, default=spec.default)
        plugin_ctx.set_state("settings", settings)

    def group_value(
        self,
        group_id: str,
        plugin_id: str,
        state_key: str,
        config_key: str,
        default: Any = None,
    ) -> Any:
        value = self._plugin_group_settings(plugin_id).get(str(group_id), {}).get(state_key)
        if value is None:
            return self.ctx.get_config(config_key, default)
        return value

    def set_group_value(self, group_id: str, plugin_id: str, state_key: str, value: Any) -> None:
        plugin_ctx = self.ctx.for_plugin(plugin_id, config=self.ctx.config)
        settings = _dict_state(plugin_ctx.get_state("settings", {}))
        group_settings = settings.setdefault(str(group_id), {})
        group_settings[state_key] = value
        plugin_ctx.set_state("settings", settings)

    def copy_group_settings(
        self,
        source_group_id: str,
        target_group_id: str,
        plugin_ids: Iterable[str] = (),
    ) -> bool:
        source_group_id = str(source_group_id).strip()
        target_group_id = str(target_group_id).strip()
        if not source_group_id or not target_group_id or source_group_id == target_group_id:
            return False
        changed = False
        for plugin_id in self._managed_plugin_ids(plugin_ids):
            plugin_ctx = self.ctx.for_plugin(plugin_id, config=self.ctx.config)
            settings = _dict_state(plugin_ctx.get_state("settings", {}))
            source = settings.get(source_group_id)
            if isinstance(source, dict):
                settings[target_group_id] = deepcopy(source)
                plugin_ctx.set_state("settings", settings)
                changed = True
            elif target_group_id in settings:
                settings.pop(target_group_id, None)
                plugin_ctx.set_state("settings", settings)
                changed = True
        enabled_map = self.plugin_enabled_map()
        source_enabled = enabled_map.get(source_group_id)
        if isinstance(source_enabled, dict):
            enabled_map[target_group_id] = dict(source_enabled)
            self.ctx.state_store.set("group_settings", GROUP_PLUGIN_ENABLED_STATE_KEY, enabled_map)
            changed = True
        elif target_group_id in enabled_map:
            enabled_map.pop(target_group_id, None)
            self.ctx.state_store.set("group_settings", GROUP_PLUGIN_ENABLED_STATE_KEY, enabled_map)
            changed = True
        return changed

    def clear_group_settings(self, group_id: str, plugin_ids: Iterable[str] = ()) -> bool:
        group_id = str(group_id).strip()
        if not group_id:
            return False
        changed = False
        for plugin_id in self._managed_plugin_ids(plugin_ids):
            plugin_ctx = self.ctx.for_plugin(plugin_id, config=self.ctx.config)
            settings = _dict_state(plugin_ctx.get_state("settings", {}))
            if group_id in settings:
                settings.pop(group_id, None)
                plugin_ctx.set_state("settings", settings)
                changed = True
        enabled_map = self.plugin_enabled_map()
        if group_id in enabled_map:
            enabled_map.pop(group_id, None)
            self.ctx.state_store.set("group_settings", GROUP_PLUGIN_ENABLED_STATE_KEY, enabled_map)
            changed = True
        return changed

    def plugin_enabled(self, group_id: str, plugin_id: str, default: bool = False) -> bool:
        return plugin_enabled_for_group(self.ctx, group_id, plugin_id, default=default)

    def set_plugin_enabled(self, group_id: str, plugin_id: str, enabled: bool) -> None:
        group_id = str(group_id).strip()
        plugin_id = str(plugin_id).strip()
        if not group_id or not plugin_id:
            return
        state = self.plugin_enabled_map()
        group_state = state.setdefault(group_id, {})
        group_state[plugin_id] = bool(enabled)
        self.ctx.state_store.set("group_settings", GROUP_PLUGIN_ENABLED_STATE_KEY, state)

    def plugin_enabled_map(self) -> dict[str, dict[str, bool]]:
        raw = self.ctx.state_store.get("group_settings", GROUP_PLUGIN_ENABLED_STATE_KEY, {})
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, bool]] = {}
        for group_id, values in raw.items():
            if not isinstance(values, dict):
                continue
            result[str(group_id)] = {str(plugin_id): bool(enabled) for plugin_id, enabled in values.items()}
        return result

    def summary(self, group_id: str) -> str:
        lines = ["本群配置："]
        for key, spec in BOOLEAN_SETTINGS.items():
            state = "开启" if self.enabled(group_id, key) else "关闭"
            lines.append(f"- {spec.label}：{state}")
        for key, spec in NUMBER_SETTINGS.items():
            lines.append(f"- {spec.label}：{self.number(group_id, key)}")
        return "\n".join(lines)

    def _plugin_group_settings(self, plugin_id: str) -> dict[str, dict[str, Any]]:
        plugin_ctx = self.ctx.for_plugin(plugin_id, config=self.ctx.config)
        return _dict_state(plugin_ctx.get_state("settings", {}))

    def _managed_plugin_ids(self, plugin_ids: Iterable[str] = ()) -> list[str]:
        result = {spec.plugin_id for spec in BOOLEAN_SETTINGS.values()}
        result.update(spec.plugin_id for spec in NUMBER_SETTINGS.values())
        for plugin_id in plugin_ids:
            value = str(plugin_id).strip()
            if value:
                result.add(value)
        return sorted(result)


def setting_key_from_label(label: str) -> str:
    normalized = label.strip()
    aliases = {
        "邀请": "invite_points_enabled",
        "邀请积分": "invite_points_enabled",
        "invite": "invite_points_enabled",
        "答题": "quiz_enabled",
        "quiz": "quiz_enabled",
        "自定义回复": "custom_replies_enabled",
        "回答": "custom_replies_enabled",
        "reply": "custom_replies_enabled",
        "AI回答": "ai_reply_enabled",
        "AI": "ai_reply_enabled",
        "ai": "ai_reply_enabled",
        "AI普通聊天": "ai_ordinary_chat_enabled",
        "普通聊天": "ai_ordinary_chat_enabled",
        "AI聊天": "ai_ordinary_chat_enabled",
        "AI@触发": "ai_at_bot_enabled",
        "AI艾特": "ai_at_bot_enabled",
        "@触发": "ai_at_bot_enabled",
        "卡密": "cards_enabled",
        "卡密兑换": "cards_enabled",
        "cards": "cards_enabled",
        "绑定": "bindings_enabled",
        "账号绑定": "bindings_enabled",
        "bindings": "bindings_enabled",
        "名单": "member_guard_enabled",
        "名单风控": "member_guard_enabled",
        "违禁词": "member_guard_enabled",
        "member_guard": "member_guard_enabled",
        "黑名单踢出": "blacklist_kick_enabled",
        "黑名单入群踢出": "blacklist_kick_enabled",
        "违禁词撤回": "forbidden_recall_enabled",
        "黑名单撤回": "blacklist_recall_enabled",
        "黑名单发言撤回": "blacklist_recall_enabled",
        "踢出通知": "blacklist_kick_notice_enabled",
        "踢出时通知": "blacklist_kick_notice_enabled",
        "群号撤回": "group_number_recall_enabled",
        "撤回群号": "group_number_recall_enabled",
        "自动撤回": "auto_recall_enabled",
        "自动类型撤回": "auto_recall_enabled",
        "退群撤回": "leave_recall_enabled",
        "机器人全部回复撤回": "bot_reply_recall_enabled",
        "机器人全部回复自动撤回": "bot_reply_recall_enabled",
        "全部回复撤回": "bot_reply_recall_enabled",
        "全部回复自动撤回": "bot_reply_recall_enabled",
        "机器人回答撤回": "bot_reply_recall_enabled",
        "机器人回复撤回": "bot_reply_recall_enabled",
        "机器人回答自动撤回": "bot_reply_recall_enabled",
        "机器人回复自动撤回": "bot_reply_recall_enabled",
        "回答撤回": "bot_reply_recall_enabled",
        "回复撤回": "bot_reply_recall_enabled",
    }
    return aliases.get(normalized, normalized)


def number_key_from_label(label: str) -> str:
    normalized = label.strip()
    aliases = {
        "邀请积分奖励": "invite_reward_points",
        "邀请奖励": "invite_reward_points",
        "邀请奖励积分": "invite_reward_points",
        "答题积分": "quiz_reward_points",
        "答题奖励": "quiz_reward_points",
        "答题奖励积分": "quiz_reward_points",
        "禁言秒数": "forbidden_ban_seconds",
        "违禁词禁言秒数": "forbidden_ban_seconds",
        "退群撤回条数": "leave_recall_limit",
        "撤回条数": "leave_recall_limit",
        "成员消息缓存": "message_cache_limit_per_member",
        "成员消息缓存条数": "message_cache_limit_per_member",
        "机器人全部回复撤回秒数": "bot_reply_recall_seconds",
        "全部回复撤回秒数": "bot_reply_recall_seconds",
        "机器人回答撤回秒数": "bot_reply_recall_seconds",
        "机器人回复撤回秒数": "bot_reply_recall_seconds",
        "回答撤回秒数": "bot_reply_recall_seconds",
        "回复撤回秒数": "bot_reply_recall_seconds",
        "撤回秒数": "bot_reply_recall_seconds",
    }
    return aliases.get(normalized, normalized)


def plugin_enabled_for_group(
    ctx: PluginContext,
    group_id: str | int,
    plugin_id: str,
    *,
    default: bool = False,
) -> bool:
    group_key = str(group_id).strip()
    plugin_key = str(plugin_id).strip()
    if not group_key or not plugin_key:
        return bool(default)
    raw = ctx.state_store.get("group_settings", GROUP_PLUGIN_ENABLED_STATE_KEY, {})
    if not isinstance(raw, dict):
        return bool(default)
    group_state = raw.get(group_key)
    if not isinstance(group_state, dict) or plugin_key not in group_state:
        return bool(default)
    return bool(group_state.get(plugin_key))


def _dict_state(value: Any) -> dict[str, dict[str, Any]]:
    return value if isinstance(value, dict) else {}


def _positive_int(value: Any, *, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, parsed)
