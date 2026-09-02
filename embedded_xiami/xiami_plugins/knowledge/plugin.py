from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.knowledge import KnowledgeService
from xiami_core.plugins.permissions import PluginPermissionService


PLUGIN_ID = "knowledge"
PLUGIN_NAME = "本地知识库"
PLUGIN_VERSION = "0.2.0"
PLUGIN_DESCRIPTION = "提供本地知识导入、添加、检索、删除和后台预览能力。"
PLUGIN_MIGRATION_STATUS = "Xiami 原生接入"
PLUGIN_CAPABILITIES = [
    "knowledge:import",
    "knowledge:import-preview",
    "knowledge:add",
    "knowledge:search",
    "knowledge:delete",
    "knowledge:admin-preview",
    "message-matchers:6",
]
PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
    "max_import_files": 100,
    "max_chars_per_file": 200000,
    "search_limit": 3,
    "admin_query": "",
}
PLUGIN_ADMIN_SCHEMA = [
    {"id": "knowledge_chunks", "label": "知识库分片", "type": "state", "state_key": "knowledge_chunks", "commands": ["知识导入", "预览知识", "知识添加", "知识搜索", "知识统计"]},
    {"id": "search_limit", "label": "默认搜索条数", "type": "config", "config_key": "search_limit"},
    {"id": "admin_query", "label": "后台检索关键词", "type": "config", "config_key": "admin_query"},
    {"id": "max_import_files", "label": "最大导入文件数", "type": "config", "config_key": "max_import_files"},
    {"id": "max_chars_per_file", "label": "单文件最大字符数", "type": "config", "config_key": "max_chars_per_file"},
    {"id": "admins", "label": "知识库管理员", "type": "config", "config_key": "admins"},
    {"id": "knowledge_status", "label": "知识库状态", "type": "runtime", "runtime_key": "status", "commands": ["知识统计"]},
    {"id": "knowledge_preview", "label": "知识检索预览", "type": "runtime", "runtime_key": "preview", "commands": ["知识搜索"]},
]
PLUGIN_ADMIN_HANDLERS = {}


def _admin_status(ctx) -> dict[str, int]:
    stats = KnowledgeService(ctx).stats()
    return {
        "documents": stats.documents,
        "sources": stats.sources,
        "chunks": stats.chunks,
        "characters": stats.characters,
        "tags": stats.tags,
    }


def _admin_preview(ctx) -> dict[str, object]:
    query = str(ctx.get_config("admin_query", "") or "").strip()
    if not query:
        return {
            "query": "",
            "message": "请先在后台检索关键词(admin_query)中填写要预览的关键词。",
            "hits": [],
        }
    limit = int(ctx.get_config("search_limit", 3) or 3)
    hits = KnowledgeService(ctx).search(query, limit=limit)
    return {
        "query": query,
        "limit": limit,
        "hits": [
            {
                "title": hit.title,
                "source": hit.source,
                "chunk_id": hit.chunk_id,
                "score": hit.score,
                "text": hit.text[:240],
                "tags": list(hit.tags),
            }
            for hit in hits
        ],
    }


PLUGIN_ADMIN_HANDLERS.update({
    "status": _admin_status,
    "preview": _admin_preview,
})

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("本地知识库插件已加载")


@on_command("知识导入", aliases=("导入知识",), description="知识导入 <文件或目录路径>")
def import_knowledge(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    service = KnowledgeService(ctx)
    result = service.import_path(
        session.argument,
        max_files=int(ctx.get_config("max_import_files", 100) or 100),
        max_chars_per_file=int(ctx.get_config("max_chars_per_file", 200000) or 200000),
    )
    ctx.reply(event, result.message)


@on_command("预览知识", aliases=("导入预览",), description="预览知识 <文件或目录路径>")
def preview_knowledge_import(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    result = KnowledgeService(ctx).preview_import(
        session.argument,
        max_files=int(ctx.get_config("max_import_files", 100) or 100),
    )
    ctx.reply(event, result.message)


@on_command("知识添加", aliases=("添加知识", "记知识"), description="知识添加 <标题> | <内容> | <标签>")
def add_knowledge(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    title, content, tags = _parse_add_argument(session.argument)
    if not content:
        ctx.reply(event, "格式：知识添加 <标题> | <内容> | <标签，可选>")
        return
    count = KnowledgeService(ctx).add_manual(title, content, tags=tags)
    ctx.reply(event, f"已添加知识：{title}，新增 {count} 个片段。")


@on_command("知识搜索", aliases=("知识", "查知识"), description="知识搜索 <关键词>")
def search_knowledge(event, ctx, session) -> None:
    query = session.argument.strip()
    if not query:
        ctx.reply(event, "请输入要检索的关键词。")
        return
    service = KnowledgeService(ctx)
    hits = service.search(query, limit=int(ctx.get_config("search_limit", 3) or 3))
    ctx.reply(event, service.render_hits(hits))


@on_command("知识删除", aliases=("删除知识", "删知识"), description="知识删除 <来源/标题/片段ID>")
def delete_knowledge(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    key = session.argument.strip()
    if not key:
        ctx.reply(event, "请输入要删除的来源、标题或片段 ID。")
        return
    removed = KnowledgeService(ctx).delete(key)
    ctx.reply(event, f"已删除 {removed} 个知识片段。")


@on_command("知识统计", aliases=("知识库状态",), description="查看知识库统计")
def knowledge_stats(event, ctx, session) -> None:
    stats = KnowledgeService(ctx).stats()
    ctx.reply(
        event,
        "本地知识库："
        f"{stats.documents} 个文档，{stats.sources} 个来源，"
        f"{stats.chunks} 个片段，{stats.characters} 字，{stats.tags} 个标签。",
    )


@on_command("知识清空", aliases=("清空知识",), description="清空知识库")
def clear_knowledge(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    KnowledgeService(ctx).clear()
    ctx.reply(event, "本地知识库已清空。")


@on_command("知识帮助", aliases=("知识库帮助",), description="查看知识库命令")
def knowledge_help(event, ctx, session) -> None:
    ctx.reply(
        event,
        "知识库命令：\n"
        "- 预览知识 <文件或目录路径>\n"
        "- 知识导入 <文件或目录路径>\n"
        "- 知识添加 <标题> | <内容> | <标签，可选>\n"
        "- 知识搜索 <关键词>\n"
        "- 知识删除 <来源/标题/片段ID>\n"
        "- 知识统计",
    )


def _require_admin(event, ctx, session) -> bool:
    group_id = session.group_id if getattr(session, "message_type", "") == "group" else ""
    ok, message = PluginPermissionService(ctx).require_admin(session.user_id, group_id)
    if not ok:
        ctx.reply(event, message)
    return ok


def _parse_add_argument(argument: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in argument.split("|", 2)]
    if len(parts) == 1:
        return "手动知识", parts[0], ""
    if len(parts) == 2:
        return parts[0] or "手动知识", parts[1], ""
    return parts[0] or "手动知识", parts[1], parts[2]


MATCHERS.extend(
    [
        import_knowledge,
        preview_knowledge_import,
        add_knowledge,
        search_knowledge,
        delete_knowledge,
        knowledge_stats,
        clear_knowledge,
        knowledge_help,
    ]
)
