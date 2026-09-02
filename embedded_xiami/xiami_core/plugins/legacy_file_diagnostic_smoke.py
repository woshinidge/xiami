from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from xiami_core.models import MessageSegment, SendResult, XiamiMessage
from xiami_core.plugins.admin import PluginAdminService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore
from xiami_core.plugins.test_support import enable_loaded_plugins_for_groups


def main() -> int:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        sent: list[tuple[str, str, str]] = []
        _write_old_echo(root)
        _write_at_bot(root)

        def send(_target: str, _text: str, _message_type: str) -> SendResult:
            sent.append((_target, _text, _message_type))
            return SendResult(ok=True, detail="ok")

        loader = PluginLoader(root, PluginContext(send_fn=send), PluginStateStore(root / "plugins.json"))
        plugins = loader.load_all()
        loaded = {plugin.id: plugin for plugin in plugins}
        if set(loaded) != {"at_bot", "old_echo"}:
            raise RuntimeError(f"legacy file plugins not loaded: {plugins!r}")
        if any(plugin.error for plugin in plugins):
            raise RuntimeError(f"legacy file plugin error: {plugins!r}")
        enable_loaded_plugins_for_groups(loader.context, plugins)

        loader.dispatch_message(XiamiMessage(message_type="private", sender="10001", text="hello"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10002", target="20001", text="hi group"))
        loader.dispatch_message(XiamiMessage(message_type="group", sender="10003", target="20001", text="plain group"))
        loader.dispatch_message(
            XiamiMessage(
                message_type="group",
                sender="10003",
                target="20001",
                text="@10000 ping",
                raw_message="[CQ:at,qq=10000] ping",
                segments=(MessageSegment("at", {"qq": "10000"}), MessageSegment("text", {"text": " ping"})),
            )
        )

        expected_sent = [
            ("10001", "handled:hello", "private"),
            ("20001", "at:ping", "group"),
        ]
        if sent != expected_sent:
            raise RuntimeError(f"legacy file plugin replies invalid: {sent!r}")

        diagnostics = {item["id"]: item for item in loader.diagnostics()}
        _assert_old_echo(diagnostics["old_echo"], loader)
        _assert_at_bot(diagnostics["at_bot"])

    print("legacy file diagnostic smoke ok")
    return 0


def _write_old_echo(root: Path) -> None:
    (root / "old_echo.py").write_text(
        "\n".join(
            [
                "plugin_spec = {",
                "    'key': 'old_echo',",
                "    'name': 'Old Echo',",
                "    'hooks': ('message.private', 'admin'),",
                "    'services': ('OldEchoService',),",
                "    'admin_path': '/admin/old_echo',",
                "}",
                "",
                "def handle(context):",
                "    return 'handled:' + context.message",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_at_bot(root: Path) -> None:
    (root / "at_bot.py").write_text(
        "\n".join(
            [
                "plugin_spec = {",
                "    'key': 'at_bot',",
                "    'name': 'At Bot Legacy',",
                "    'hooks': ('message.at_bot',),",
                "}",
                "",
                "def handle(context):",
                "    return 'at:' + context.message",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _assert_old_echo(old_echo: dict[str, object], loader: PluginLoader) -> None:
    if old_echo["message_handled_count"] != 1 or old_echo["message_unhandled_count"] != 3:
        raise RuntimeError(f"old_echo dispatch counters invalid: {old_echo}")
    if old_echo["matcher_hit_count"].get("legacy-file:message.private") != 1:  # type: ignore[index, union-attr]
        raise RuntimeError(f"old_echo hit missing: {old_echo}")
    if "legacy-admin-hook" not in old_echo["capabilities"] or "legacy-admin-path" not in old_echo["capabilities"]:
        raise RuntimeError(f"old_echo admin capabilities missing: {old_echo}")
    admin_schema = old_echo.get("admin_schema") or []
    if not admin_schema or admin_schema[0].get("id") != "legacy_admin_path":  # type: ignore[index, union-attr]
        raise RuntimeError(f"old_echo legacy admin schema missing: {old_echo}")
    admin_preview = old_echo.get("admin_state_preview") or []
    if not admin_preview or "/admin/old_echo" not in str(admin_preview[0].get("summary") or ""):  # type: ignore[index, union-attr]
        raise RuntimeError(f"old_echo legacy admin preview missing: {old_echo}")
    snapshot = PluginAdminService(loader).snapshot("old_echo", include_values=False)
    if not snapshot["items"] or snapshot["items"][0].get("id") != "legacy_admin_path":
        raise RuntimeError(f"old_echo admin service snapshot missing: {snapshot}")


def _assert_at_bot(at_bot: dict[str, object]) -> None:
    if at_bot["message_handled_count"] != 1 or at_bot["message_unhandled_count"] != 3:
        raise RuntimeError(f"at_bot dispatch counters invalid: {at_bot}")
    if at_bot["matcher_hit_count"].get("legacy-file:message.at_bot") != 1:  # type: ignore[index, union-attr]
        raise RuntimeError(f"at_bot hit missing: {at_bot}")


if __name__ == "__main__":
    raise SystemExit(main())
