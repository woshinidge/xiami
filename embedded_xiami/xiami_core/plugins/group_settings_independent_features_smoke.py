from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.group_settings import BOOLEAN_SETTINGS, NUMBER_SETTINGS, GroupSettingService
from xiami_core.plugins.kv import PluginKVStore


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        ctx = PluginContext(send_fn=_send, state_store=PluginKVStore(root / "state"))
        service = GroupSettingService(ctx)

        group_a = "1072296527"
        group_b = "200020002"

        service.set_plugin_enabled(group_a, "ai_reply", False)
        service.set_plugin_enabled(group_b, "ai_reply", True)
        if service.plugin_enabled(group_a, "ai_reply") is not False:
            raise RuntimeError("group A plugin gate should be disabled")
        if service.plugin_enabled(group_b, "ai_reply") is not True:
            raise RuntimeError("group B plugin gate should stay enabled")

        for key in sorted(BOOLEAN_SETTINGS):
            service.set_enabled(group_a, key, False)
            service.set_enabled(group_b, key, True)
            if service.enabled(group_a, key) is not False:
                raise RuntimeError(f"group A boolean setting leaked or was not saved: {key}")
            if service.enabled(group_b, key) is not True:
                raise RuntimeError(f"group B boolean setting leaked or was not saved: {key}")

        for index, key in enumerate(sorted(NUMBER_SETTINGS), start=1):
            value_a = 10 + index
            value_b = 100 + index
            service.set_number(group_a, key, value_a)
            service.set_number(group_b, key, value_b)
            if service.number(group_a, key) != value_a:
                raise RuntimeError(f"group A number setting leaked or was not saved: {key}")
            if service.number(group_b, key) != value_b:
                raise RuntimeError(f"group B number setting leaked or was not saved: {key}")

        service.set_group_value(group_a, "member_guard", "recall_message_types", ["image", "json", "xml"])
        service.set_group_value(group_b, "member_guard", "recall_message_types", ["video", "url"])
        recall_a = service.group_value(group_a, "member_guard", "recall_message_types", "recall_message_types", [])
        recall_b = service.group_value(group_b, "member_guard", "recall_message_types", "recall_message_types", [])
        if recall_a != ["image", "json", "xml"]:
            raise RuntimeError(f"group A recall types leaked or were not saved: {recall_a}")
        if recall_b != ["video", "url"]:
            raise RuntimeError(f"group B recall types leaked or were not saved: {recall_b}")

        service.set_group_value(group_a, "bindings", "binding_storage_alias", "zone-a")
        service.set_group_value(group_b, "bindings", "binding_storage_alias", "zone-b")
        if service.group_value(group_a, "bindings", "binding_storage_alias", "binding_storage_alias", "") != "zone-a":
            raise RuntimeError("group A binding alias leaked or was not saved")
        if service.group_value(group_b, "bindings", "binding_storage_alias", "binding_storage_alias", "") != "zone-b":
            raise RuntimeError("group B binding alias leaked or was not saved")

        group_c = "300030003"
        if not service.copy_group_settings(group_a, group_c, ["ai_reply", "member_guard", "bindings"]):
            raise RuntimeError("copying group settings should report a change")
        if service.plugin_enabled(group_c, "ai_reply") is not False:
            raise RuntimeError("copied group plugin gate did not match source")
        for key in sorted(BOOLEAN_SETTINGS):
            if service.enabled(group_c, key) is not False:
                raise RuntimeError(f"copied boolean setting mismatch: {key}")
        for key in sorted(NUMBER_SETTINGS):
            if service.number(group_c, key) != service.number(group_a, key):
                raise RuntimeError(f"copied number setting mismatch: {key}")
        copied_recall = service.group_value(group_c, "member_guard", "recall_message_types", "recall_message_types", [])
        if copied_recall != ["image", "json", "xml"]:
            raise RuntimeError(f"copied recall types mismatch: {copied_recall}")
        copied_alias = service.group_value(group_c, "bindings", "binding_storage_alias", "binding_storage_alias", "")
        if copied_alias != "zone-a":
            raise RuntimeError(f"copied binding alias mismatch: {copied_alias}")
        if not service.clear_group_settings(group_c, ["ai_reply", "member_guard", "bindings"]):
            raise RuntimeError("clearing copied group settings should report a change")
        if service.plugin_enabled(group_c, "ai_reply") is not False:
            raise RuntimeError("cleared group plugin gate should return to default closed")
        for key, spec in BOOLEAN_SETTINGS.items():
            if service.enabled(group_c, key) != spec.default:
                raise RuntimeError(f"cleared boolean setting did not return to default: {key}")
        for key, spec in NUMBER_SETTINGS.items():
            if service.number(group_c, key) != spec.default:
                raise RuntimeError(f"cleared number setting did not return to default: {key}")
        if service.group_value(group_c, "bindings", "binding_storage_alias", "binding_storage_alias", "") != "":
            raise RuntimeError("cleared group binding alias should return to default")
        if service.plugin_enabled(group_a, "ai_reply") is not False:
            raise RuntimeError("source group changed after copy/clear")

        enabled_map = service.plugin_enabled_map()
    if enabled_map.get(group_a, {}).get("ai_reply") is not False:
        raise RuntimeError(f"group A plugin enabled map mismatch: {enabled_map}")
    if enabled_map.get(group_b, {}).get("ai_reply") is not True:
        raise RuntimeError(f"group B plugin enabled map mismatch: {enabled_map}")

    print("group settings independent features smoke ok")
    return 0


def _send(_target: str, _text: str, _message_type: str) -> SendResult:
    return SendResult(ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
