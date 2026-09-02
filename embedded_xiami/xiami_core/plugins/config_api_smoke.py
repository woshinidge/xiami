from __future__ import annotations

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext


def main() -> int:
    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    ctx = PluginContext(
        send_fn=send,
        config={
            "enabled": "yes",
            "disabled": "0",
            "count": "12",
            "bad_count": "abc",
            "ratio": "1.25",
            "bad_ratio": "nan-value",
            "name": 313,
            "list_json": '["a", "b"]',
            "list_csv": "a, b,, c",
            "list_tuple": ("x", "y"),
            "dict_json": '{"a": 1}',
            "dict_value": {"b": 2},
            "dict_bad": "{bad",
        },
    )
    checks = [
        ctx.get_config_bool("enabled") is True,
        ctx.get_config_bool("disabled", True) is False,
        ctx.get_config_bool("unknown", True) is True,
        ctx.get_config_int("count") == 12,
        ctx.get_config_int("bad_count", 7) == 7,
        ctx.get_config_float("ratio") == 1.25,
        ctx.get_config_float("bad_ratio", 2.5) == 2.5,
        ctx.get_config_str("name") == "313",
        ctx.get_config_list("list_json") == ["a", "b"],
        ctx.get_config_list("list_csv") == ["a", "b", "c"],
        ctx.get_config_list("list_tuple") == ["x", "y"],
        ctx.get_config_list("missing_list", ["fallback"]) == ["fallback"],
        ctx.get_config_dict("dict_json") == {"a": 1},
        ctx.get_config_dict("dict_value") == {"b": 2},
        ctx.get_config_dict("dict_bad", {"fallback": True}) == {"fallback": True},
    ]
    if not all(checks):
        raise RuntimeError("config helper checks failed")
    print("plugin config api smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
