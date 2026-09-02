from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.admin import PluginAdminService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.knowledge import KnowledgeService
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "knowledge"
        plugin_dir.mkdir(parents=True)
        shutil.copyfile(Path.cwd() / "xiami_plugins" / "knowledge" / "plugin.py", plugin_dir / "plugin.py")
        (plugin_dir / "plugin_config.json").write_text(
            '{"admins":["10001"],"search_limit":2}',
            encoding="utf-8",
        )

        docs = root / "docs"
        docs.mkdir()
        (docs / "guide.md").write_text(
            "Xiami 可以托管 NapCat 登录内核，并加载机器人插件。",
            encoding="utf-8",
        )
        (docs / "ai.txt").write_text(
            "本地知识库检索会在 AI 编排前提供上下文。",
            encoding="utf-8",
        )
        (docs / "legacy.htm").write_text(
            "<html><body><h1>旧知识库</h1><p>HTML 资料也应该进入本地检索。</p></body></html>",
            encoding="utf-8",
        )
        ignored_dir = docs / "node_modules"
        ignored_dir.mkdir()
        (ignored_dir / "ignored.txt").write_text("不应导入 node_modules 内容。", encoding="utf-8")

        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if not plugins or plugins[0].error:
            raise RuntimeError(f"knowledge plugin load failed: {plugins}")

        admin = "10001"
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender=admin, target=admin, text=f"预览知识 {docs}")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender=admin, target=admin, text=f"知识导入 {docs}")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender=admin, target=admin, text="知识搜索 NapCat")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender=admin, target=admin, text="知识搜索 HTML 资料")
        )
        loader.dispatch_message(
            XiamiMessage(
                message_type="private",
                sender=admin,
                target=admin,
                text="知识添加 登录流程 | Xiami 使用 NapCat 扫码登录 | 登录 NapCat",
            )
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender=admin, target=admin, text="查知识 扫码登录")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender=admin, target=admin, text="知识统计")
        )
        loader.dispatch_message(
            XiamiMessage(message_type="private", sender=admin, target=admin, text="删知识 登录流程")
        )

        combined = "\n".join(item[1] for item in sent)
        for expected in ["预计导入", "已导入", "NapCat", "登录流程", "本地知识库", "HTML 资料", "已删除"]:
            if expected not in combined:
                raise RuntimeError(f"knowledge output missing {expected!r}: {combined}")
        if "不应导入" in combined:
            raise RuntimeError(f"skip directory content leaked into knowledge output: {combined}")
        preview_limit = KnowledgeService(ctx).preview_import(str(docs), max_files=2)
        if preview_limit.files != 2 or "上限" not in preview_limit.message:
            raise RuntimeError(f"knowledge import preview limit failed: {preview_limit!r}")

        diagnostic = loader.diagnostics()[0]
        capabilities = diagnostic.get("capabilities") or []
        if "knowledge:search" not in capabilities or "knowledge:add" not in capabilities:
            raise RuntimeError(f"knowledge capabilities missing: {diagnostic!r}")

        service = PluginAdminService(loader)
        status = service.get_item("knowledge", "knowledge_status")
        if not status.ok or status.data["value"].get("chunks", 0) <= 0:
            raise RuntimeError(f"knowledge runtime status failed: {status!r}")

        query = service.set_item("knowledge", "admin_query", "NapCat")
        if not query.ok:
            raise RuntimeError(f"knowledge admin query update failed: {query!r}")
        preview = service.get_item("knowledge", "knowledge_preview")
        hits = preview.data["value"].get("hits", []) if preview.ok else []
        if not hits or "NapCat" not in hits[0].get("text", ""):
            raise RuntimeError(f"knowledge runtime preview failed: {preview!r}")

    print("knowledge_smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
