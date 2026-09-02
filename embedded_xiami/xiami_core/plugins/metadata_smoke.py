from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "meta_case"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text(
            "\n".join(
                [
                    "from xiami_core.plugins.compat import on_command, on_keyword",
                    "MATCHERS = []",
                    "@on_command('/a', aliases=('/b',), description='alpha')",
                    "def a(event, ctx, session): pass",
                    "@on_keyword('hello', description='keyword alpha')",
                    "def k(event, ctx, session): pass",
                    "MATCHERS.extend([a, k])",
                ]
            ),
            encoding="utf-8",
        )

        loader = PluginLoader(plugin_root, PluginContext(send_fn=send), state_store=PluginStateStore(root / "state.json"))
        plugins = loader.load_all()
        commands = plugins[0].commands
        if "/a, /b - alpha" not in commands or "关键词:hello - keyword alpha" not in commands:
            raise RuntimeError(f"metadata missing: {commands}")

    print("plugin metadata smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
