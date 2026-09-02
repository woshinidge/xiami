from __future__ import annotations

import tempfile
from pathlib import Path

from xiami_core.native_rewrite_audit import (
    audit_native_rewrite,
    format_native_rewrite_audit,
    native_rewrite_audit_to_dict,
)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _write(
            root / "native" / "plugin.py",
            """
PLUGIN_ID = "native"
PLUGIN_NAME = "Native"

def on_message(event, ctx):
    return None
""",
        )
        _write(
            root / "helper" / "plugin.py",
            """
from xiami_core.plugins.compat import on_command

PLUGIN_ID = "helper"
PLUGIN_NAME = "Helper"

@on_command("帮助", aliases=("菜单",))
def help_cmd(event, ctx, session):
    ctx.reply(event, "ok")
""",
        )
        _write(
            root / "legacy_bridge" / "plugin.py",
            """
PLUGIN_ID = "legacy_bridge"
PLUGIN_MODE = "legacy"
PLUGIN_CAPABILITIES = ["legacy:onebot-v11"]

def handle_message(bot, event, ctx):
    return None
""",
        )
        _write(
            root / "legacy_file.py",
            """
plugin_spec = {"key": "legacy_file", "name": "Legacy File"}
""",
        )

        audit = audit_native_rewrite(root)
        data = native_rewrite_audit_to_dict(audit)
        if audit.total != 4 or audit.native != 2 or audit.legacy_or_compat != 2:
            raise RuntimeError(data)
        by_id = {item.plugin_id: item for item in audit.items}
        if by_id["helper"].status != "native" or not by_id["helper"].uses_xiami_compat_helpers:
            raise RuntimeError(by_id["helper"])
        if by_id["legacy_bridge"].status != "legacy_bridge":
            raise RuntimeError(by_id["legacy_bridge"])
        if by_id["legacy_file"].status != "legacy_file":
            raise RuntimeError(by_id["legacy_file"])
        text = format_native_rewrite_audit(audit)
        if "Xiami native: 2/4" not in text or "legacy_bridge" not in text:
            raise RuntimeError(text)

    print("native rewrite audit smoke ok")
    return 0


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
