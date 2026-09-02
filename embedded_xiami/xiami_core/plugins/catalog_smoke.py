from __future__ import annotations

from pathlib import Path

from xiami_core.plugins.catalog import build_plugin_catalog, format_plugin_catalog
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.testing import use_temp_xiami_home


def main() -> int:
    home = Path(use_temp_xiami_home())
    loader = PluginLoader(
        Path.cwd() / "xiami_plugins",
        PluginContext(send_fn=lambda _message: None),
        state_store=PluginStateStore(home / "plugin_state.json"),
    )
    loader.load_all()
    items = build_plugin_catalog(loader)
    by_id = {item.plugin_id: item for item in items}
    if len(items) != 18:
        raise RuntimeError(f"catalog plugin count changed: {len(items)}")
    for plugin_id in ("ai_reply", "knowledge", "onebot_tools", "echo"):
        if plugin_id not in by_id:
            raise RuntimeError(f"catalog missing {plugin_id}")
    if by_id["ai_reply"].category != "AI":
        raise RuntimeError(f"ai category failed: {by_id['ai_reply']}")
    if by_id["knowledge"].category != "Knowledge":
        raise RuntimeError(f"knowledge category failed: {by_id['knowledge']}")
    if by_id["onebot_tools"].category != "OneBot":
        raise RuntimeError(f"onebot category failed: {by_id['onebot_tools']}")
    if not by_id["echo"].healthy:
        raise RuntimeError("echo should be healthy")
    text = format_plugin_catalog(items)
    if "Xiami plugin catalog" not in text or "onebot_tools" not in text or "commands=" not in text:
        raise RuntimeError(f"catalog format failed: {text}")
    print("plugin catalog smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
