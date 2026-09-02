from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore


def main() -> int:
    def send(target: str, text: str, message_type: str) -> SendResult:
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        store = PluginKVStore(root / "state")
        ctx = PluginContext(send_fn=send, data_root=root / "data", state_store=store, plugin_id="state_api")

        if ctx.increment_state("count") != 1:
            raise RuntimeError("increment_state did not initialize counter")
        if ctx.increment_state("count", 4) != 5:
            raise RuntimeError("increment_state did not add integer amount")
        if ctx.get_state_int("count") != 5:
            raise RuntimeError("get_state_int did not read counter")

        ctx.set_state("cooldown", "1.5")
        if ctx.increment_state("cooldown", 0.5, 0.0) != 2.0:
            raise RuntimeError("increment_state did not handle float counter")

        ctx.set_state("enabled", "yes")
        if not ctx.get_state_bool("enabled"):
            raise RuntimeError("get_state_bool did not parse truthy value")

        ctx.set_state("members", "10001, 10002")
        if ctx.get_state_list("members") != ["10001", "10002"]:
            raise RuntimeError("get_state_list did not parse comma list")
        if ctx.append_state_list("members", "10002", unique=True) != ["10001", "10002"]:
            raise RuntimeError("append_state_list unique duplicated item")
        if ctx.append_state_list("members", "10003", unique=True) != ["10001", "10002", "10003"]:
            raise RuntimeError("append_state_list did not append item")
        if ctx.remove_state_list("members", "10002") != ["10001", "10003"]:
            raise RuntimeError("remove_state_list did not remove item")

        if ctx.update_state_dict("bindings", {"10001": "main"}, group="20001") != {
            "10001": "main",
            "group": "20001",
        }:
            raise RuntimeError("update_state_dict did not merge values")
        if ctx.get_state_dict("bindings")["10001"] != "main":
            raise RuntimeError("get_state_dict did not read merged value")

        if store.get("state_api", "count") != 5:
            raise RuntimeError("state helpers did not persist through kv store")
        if ctx.state_revision < 8:
            raise RuntimeError("state helpers did not update state revision")

    print("plugin state api smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
