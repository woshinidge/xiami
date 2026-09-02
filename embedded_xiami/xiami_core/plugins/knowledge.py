from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import html
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator

from xiami_core.plugins.context import PluginContext


TEXT_EXTENSIONS = {
    ".cfg",
    ".conf",
    ".csv",
    ".htm",
    ".html",
    ".ini",
    ".json",
    ".log",
    ".lua",
    ".md",
    ".py",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
SKIP_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "downloads",
    "kernels",
    "node_modules",
    "runtime",
    "venv",
}

STATE_KEY = "knowledge_chunks"


@dataclass(frozen=True)
class KnowledgeHit:
    source: str
    text: str
    score: int
    title: str = ""
    chunk_id: str = ""
    index: int = 0
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeImportResult:
    files: int
    chunks: int
    skipped: int
    message: str


@dataclass(frozen=True)
class ServerKnowledgeResult:
    files: int
    documents: int
    chunks: int
    characters: int
    skipped: int
    root: str
    message: str


@dataclass(frozen=True)
class KnowledgeStats:
    sources: int
    chunks: int
    characters: int
    documents: int = 0
    tags: int = 0


class KnowledgeService:
    """Small local text index stored in the knowledge plugin state."""

    def __init__(self, ctx: PluginContext):
        self.ctx = ctx

    def import_path(
        self,
        path_text: str,
        *,
        max_files: int = 100,
        max_chars_per_file: int = 200_000,
        chunk_size: int = 900,
        overlap: int = 120,
    ) -> KnowledgeImportResult:
        path_text = path_text.strip().strip('"')
        if not path_text:
            return KnowledgeImportResult(0, 0, 0, "请提供要导入的文件或目录路径。")

        path = Path(path_text).expanduser()
        if not path.exists():
            return KnowledgeImportResult(0, 0, 0, f"知识路径不存在：{path}")

        max_files = max(1, int(max_files or 1))
        candidates = [path] if path.is_file() else self._iter_text_files(path)
        skipped = 0
        imported_files = 0
        added = 0

        for file_path in candidates:
            if imported_files >= max_files:
                skipped += 1
                break
            if not self._is_supported_file(file_path):
                skipped += 1
                continue
            text = self._read_text(file_path, max_chars=max_chars_per_file)
            if not text.strip():
                skipped += 1
                continue
            imported_files += 1
            added += self.add_document(
                str(file_path),
                text,
                title=file_path.name,
                tags=(file_path.suffix.lower().lstrip("."), "imported"),
                chunk_size=chunk_size,
                overlap=overlap,
                replace=True,
            )

        if imported_files == 0:
            return KnowledgeImportResult(0, 0, skipped, "没有导入任何可用文本。")
        return KnowledgeImportResult(
            imported_files,
            added,
            skipped,
            f"已导入 {imported_files} 个文件，新增 {added} 个知识片段。",
        )

    def generate_server_materials(
        self,
        path_text: str,
        *,
        trigger_name: str = "",
        max_files: int = 250,
        max_chars_per_file: int = 80_000,
        max_total_chars: int = 2_000_000,
    ) -> ServerKnowledgeResult:
        """Generate a local knowledge set from version-making files only."""
        trigger_name = str(trigger_name or "").strip()
        trigger_tag = f"trigger:{trigger_name}" if trigger_name else ""
        trigger_tags = (trigger_tag,) if trigger_tag else ()
        title_prefix = f"[{trigger_name}] " if trigger_name else ""
        server_root = _resolve_server_root(path_text)
        envir = server_root / "Mir200" / "Envir"
        db_root = server_root / "Mud2" / "DB"
        map_root = server_root / "Mir200" / "Map"
        source_prefix = f"server:{os.path.normcase(os.path.abspath(str(server_root)))}:"
        base_chunks = [
            item for item in self._chunks()
            if not str(item.get("source", "")).startswith(source_prefix)
        ]
        generated_chunks: list[dict[str, Any]] = []

        candidates = _server_material_files(envir, max_files=max_files)
        imported = 0
        documents = 0
        added_chunks = 0
        total_chars = 0
        skipped = 0
        for file_path in candidates:
            if total_chars >= max_total_chars:
                skipped += 1
                continue
            try:
                text = self._read_text(file_path, max_chars=max_chars_per_file)
            except OSError:
                skipped += 1
                continue
            text = text.strip()
            if not text:
                skipped += 1
                continue
            remaining = max_total_chars - total_chars
            text = text[:remaining]
            rel = str(file_path.relative_to(server_root)).replace("\\", "/")
            records = _document_chunk_records(
                source_prefix + rel,
                text,
                title=title_prefix + rel,
                tags=("server", _server_material_tag(rel), *trigger_tags),
            )
            generated_chunks.extend(records)
            added_chunks += len(records)
            imported += 1
            documents += 1
            total_chars += len(text)

        db_text, db_name = _server_database_material(db_root)
        if db_text and total_chars < max_total_chars:
            db_text = db_text[: max_total_chars - total_chars]
            records = _document_chunk_records(
                source_prefix + f"Mud2/DB/{db_name}#structured",
                db_text,
                title=f"{title_prefix}数据库资料：{db_name}",
                tags=("server", "database", *trigger_tags),
            )
            generated_chunks.extend(records)
            added_chunks += len(records)
            documents += 1
            total_chars += len(db_text)

        map_text = _server_map_inventory(map_root)
        if map_text and total_chars < max_total_chars:
            map_text = map_text[: max_total_chars - total_chars]
            records = _document_chunk_records(
                source_prefix + "Mir200/Map#inventory",
                map_text,
                title=title_prefix + "地图文件清单",
                tags=("server", "map", *trigger_tags),
            )
            generated_chunks.extend(records)
            added_chunks += len(records)
            documents += 1
            total_chars += len(map_text)

        self.ctx.set_state(STATE_KEY, base_chunks + generated_chunks)

        message = (
            f"服务端资料已生成{f'（触发名称：{trigger_name}）' if trigger_name else ''}："
            f"读取 {imported} 个脚本/配置文件，"
            f"生成 {documents} 个文档、{added_chunks} 个知识片段。"
        )
        return ServerKnowledgeResult(
            imported,
            documents,
            added_chunks,
            total_chars,
            skipped,
            str(server_root),
            message,
        )

    def preview_import(self, path_text: str, *, max_files: int = 100) -> KnowledgeImportResult:
        path_text = path_text.strip().strip('"')
        if not path_text:
            return KnowledgeImportResult(0, 0, 0, "请提供要预览的文件或目录路径。")
        path = Path(path_text).expanduser()
        if not path.exists():
            return KnowledgeImportResult(0, 0, 0, f"知识路径不存在：{path}")
        max_files = max(1, int(max_files or 1))
        candidates = [path] if path.is_file() else self._iter_text_files(path)
        files: list[Path] = []
        skipped = 0
        for file_path in candidates:
            if len(files) >= max_files:
                skipped += 1
                break
            if not self._is_supported_file(file_path):
                skipped += 1
                continue
            files.append(file_path)
        if not files:
            return KnowledgeImportResult(0, 0, skipped, "没有发现可导入文本。")
        names = "、".join(file.name for file in files[:5])
        suffix = "；已达到导入上限" if skipped else ""
        return KnowledgeImportResult(len(files), 0, skipped, f"预计导入 {len(files)} 个文件：{names}{suffix}")

    def add_manual(
        self,
        title: str,
        text: str,
        *,
        tags: str | list[str] | tuple[str, ...] = (),
        source: str = "",
        chunk_size: int = 900,
        overlap: int = 120,
    ) -> int:
        title = title.strip() or "未命名知识"
        source = source.strip() or self._next_manual_source(title)
        return self.add_document(
            source,
            text,
            title=title,
            tags=_parse_tags(tags),
            chunk_size=chunk_size,
            overlap=overlap,
            replace=False,
        )

    def add_document(
        self,
        source: str,
        text: str,
        *,
        title: str = "",
        tags: str | list[str] | tuple[str, ...] = (),
        chunk_size: int = 900,
        overlap: int = 120,
        replace: bool = True,
    ) -> int:
        source = source.strip() or "inline"
        title = title.strip() or _title_from_source(source)
        parsed_tags = _parse_tags(tags)
        chunks = self._chunks()
        if replace:
            chunks = [item for item in chunks if item.get("source") != source]

        records = _document_chunk_records(
            source,
            text,
            title=title,
            tags=parsed_tags,
            chunk_size=chunk_size,
            overlap=overlap,
        )
        chunks.extend(records)
        self.ctx.set_state(STATE_KEY, chunks)
        return len(records)

    def search(self, query: str, *, limit: int = 3) -> list[KnowledgeHit]:
        query = query.strip()
        if not query:
            return []

        chunks = self._chunks()
        trigger_name = _matched_trigger_name(query, chunks)
        if trigger_name:
            trigger_tag = f"trigger:{trigger_name}".lower()
            chunks = [
                item for item in chunks
                if trigger_tag in {str(tag).lower() for tag in item.get("tags", [])}
            ]
        terms = _query_terms(query)
        hits: list[KnowledgeHit] = []
        for item in chunks:
            text = str(item.get("text", ""))
            title = str(item.get("title") or _title_from_source(str(item.get("source", ""))))
            tags = tuple(str(tag) for tag in item.get("tags", []) if str(tag).strip())
            score = _score(text=text, title=title, tags=tags, query=query, terms=terms)
            if score > 0:
                hits.append(
                    KnowledgeHit(
                        source=str(item.get("source", "")),
                        title=title,
                        chunk_id=str(item.get("id", "")),
                        index=int(item.get("index", 0) or 0),
                        tags=tags,
                        text=_snippet(text, query, terms),
                        score=score,
                    )
                )
        hits.sort(key=lambda item: item.score, reverse=True)
        return hits[: max(1, int(limit or 1))]

    def delete(self, source_or_id: str) -> int:
        key = source_or_id.strip()
        if not key:
            return 0
        chunks = self._chunks()
        kept = [
            item
            for item in chunks
            if str(item.get("source", "")) != key
            and str(item.get("id", "")) != key
            and str(item.get("title", "")) != key
        ]
        removed = len(chunks) - len(kept)
        if removed:
            self.ctx.set_state(STATE_KEY, kept)
        return removed

    def clear(self) -> None:
        self.ctx.delete_state(STATE_KEY)

    def stats(self) -> KnowledgeStats:
        chunks = self._chunks()
        sources = {str(item.get("source", "")) for item in chunks if item.get("source")}
        titles = {str(item.get("title", "")) for item in chunks if item.get("title")}
        tags = {
            str(tag)
            for item in chunks
            for tag in item.get("tags", [])
            if str(tag).strip()
        }
        characters = sum(len(str(item.get("text", ""))) for item in chunks)
        return KnowledgeStats(
            sources=len(sources),
            chunks=len(chunks),
            characters=characters,
            documents=len(titles or sources),
            tags=len(tags),
        )

    def server_trigger_materials(self) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for item in self._chunks():
            source = str(item.get("source", ""))
            trigger_names = [
                str(tag).split(":", 1)[1].strip()
                for tag in item.get("tags", [])
                if str(tag).lower().startswith("trigger:") and str(tag).split(":", 1)[1].strip()
            ]
            for trigger_name in trigger_names:
                bucket = grouped.setdefault(
                    trigger_name,
                    {"name": trigger_name, "sources": set(), "roots": set(), "chunks": 0},
                )
                bucket["chunks"] += 1
                if source:
                    bucket["sources"].add(source)
                    root = _server_root_from_source(source)
                    if root:
                        bucket["roots"].add(root)
        return [
            {
                "name": name,
                "documents": len(bucket["sources"]),
                "chunks": int(bucket["chunks"]),
                "roots": sorted(bucket["roots"]),
            }
            for name, bucket in sorted(grouped.items(), key=lambda item: item[0].lower())
        ]

    def render_hits(self, hits: list[KnowledgeHit]) -> str:
        if not hits:
            return "未命中本地知识。"
        lines: list[str] = ["本地知识命中："]
        for index, hit in enumerate(hits, start=1):
            label = hit.title or hit.source or hit.chunk_id or "知识片段"
            tag_text = f" #{','.join(hit.tags)}" if hit.tags else ""
            lines.append(f"{index}. {label}{tag_text} score={hit.score}\n{hit.text}")
        return "\n".join(lines)

    def _chunks(self) -> list[dict[str, Any]]:
        value = self.ctx.get_state(STATE_KEY, [])
        if not isinstance(value, list):
            return []
        return [_normalize_chunk(item) for item in value if isinstance(item, dict)]

    def _iter_text_files(self, path: Path) -> Iterator[Path]:
        for root, dirs, files in os.walk(path):
            dirs[:] = [name for name in sorted(dirs) if not _should_skip_dir(name)]
            for name in sorted(files):
                file_path = Path(root) / name
                if self._is_supported_file(file_path):
                    yield file_path

    def _is_supported_file(self, path: Path) -> bool:
        return path.suffix.lower() in TEXT_EXTENSIONS

    def _read_text(self, path: Path, *, max_chars: int) -> str:
        for encoding in ("utf-8", "utf-8-sig", "gb18030"):
            try:
                text = path.read_text(encoding=encoding, errors="ignore")
                return _normalize_document_text(path, text)[: max(1, int(max_chars or 1))]
            except OSError:
                raise
            except UnicodeError:
                continue
        return _normalize_document_text(path, path.read_text(errors="ignore"))[: max(1, int(max_chars or 1))]

    def _next_manual_source(self, title: str) -> str:
        prefix = f"manual:{_safe_id(title)}"
        count = sum(1 for item in self._chunks() if str(item.get("source", "")).startswith(prefix))
        return f"{prefix}:{count + 1}"


_SERVER_SKIP_DIR_PARTS = {
    ".git", "back", "backup", "logs", "log", "temp", "tmp", "test",
    "备份", "数据备份", "新区数据", "测试", "日志", "存销生成备份", "存销一键删除备份",
}


def _resolve_server_root(path_text: str) -> Path:
    raw = str(path_text or "").strip().strip('"')
    if not raw:
        raise ValueError("请选择服务端根目录。")
    selected = Path(raw).expanduser().resolve()
    candidates = [selected]
    if selected.name.lower() == "mir200":
        candidates.append(selected.parent)
    if selected.name.lower() == "envir" and selected.parent.name.lower() == "mir200":
        candidates.append(selected.parent.parent)
    for candidate in candidates:
        if (candidate / "Mir200" / "Envir").is_dir():
            return candidate
    raise ValueError("未找到 Mir200/Envir，请选择 MirServer 服务端根目录。")


def _server_skip_path(path: Path, root: Path) -> bool:
    try:
        parts = path.relative_to(root).parts
    except ValueError:
        return True
    lowered = {str(part).strip().lower() for part in parts}
    return bool(lowered & _SERVER_SKIP_DIR_PARTS)


def _server_material_files(envir: Path, *, max_files: int) -> list[Path]:
    max_files = max(1, int(max_files or 1))
    explicit = (
        "Market_Def/QFunction-0.txt",
        "Market_def/QFunction-0.txt",
        "MapQuest_Def/QManage.txt",
        "MapQuest_def/QManage.txt",
        "Robot_def/AutoRunRobot.txt",
        "Robot_def/RobotManage.txt",
        "MerChant.txt",
        "MapInfo.txt",
        "MonGen.txt",
        "MiniMap.txt",
        "MapDesc.txt",
        "MapEvent.txt",
        "MapQuest.txt",
        "UserCmd.txt",
        "SetItems.txt",
        "CompoundInfo.txt",
        "EffectItemList.txt",
        "ItemDescList.txt",
        "ItemDescTopList.txt",
        "ItemRuleList.txt",
        "MonDropLimitList.txt",
    )
    result: list[Path] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        if len(result) >= max_files or not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            return
        if _server_skip_path(path, envir):
            return
        key = os.path.normcase(os.path.abspath(str(path)))
        if key not in seen:
            seen.add(key)
            result.append(path)

    for rel in explicit:
        add(envir / Path(rel))
    for folder_name in ("Market_Def", "Market_def", "QuestDiary", "MonItems", "Robot_def"):
        folder = envir / folder_name
        if not folder.is_dir():
            continue
        for current, dirs, files in os.walk(str(folder), topdown=True, followlinks=False):
            current_path = Path(current)
            dirs[:] = [
                name for name in sorted(dirs, key=str.lower)
                if not _server_skip_path(current_path / name, envir)
            ]
            for name in sorted(files, key=str.lower):
                add(current_path / name)
                if len(result) >= max_files:
                    return result
    return result


def _server_material_tag(rel: str) -> str:
    normalized = str(rel or "").replace("\\", "/").lower()
    if "/monitems/" in f"/{normalized}":
        return "drops"
    if "/market_def/" in f"/{normalized}":
        return "npc"
    if "/questdiary/" in f"/{normalized}":
        return "script"
    if "map" in Path(normalized).name:
        return "map"
    return "config"


def _server_root_from_source(source: str) -> str:
    text = str(source or "")
    if not text.startswith("server:"):
        return ""
    root, separator, _relative = text[len("server:"):].rpartition(":")
    return root if separator else ""


def _server_database_material(db_root: Path) -> tuple[str, str]:
    if not db_root.is_dir():
        return "", ""
    preferred = ("ApexM2.db", "GEEM2.db", "StdItems.db", "GOM.db")
    by_lower = {path.name.lower(): path for path in db_root.iterdir() if path.is_file()}
    candidates = [by_lower[name.lower()] for name in preferred if name.lower() in by_lower]
    candidates.extend(
        path for path in sorted(db_root.iterdir(), key=lambda value: value.name.lower())
        if path.is_file() and path.suffix.lower() == ".db" and path not in candidates
    )
    for db_path in candidates:
        try:
            uri = db_path.resolve().as_uri() + "?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=1.5)
        except (OSError, sqlite3.Error):
            continue
        try:
            tables = [
                str(row[0]) for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                ).fetchall()
            ]
            selected = [
                name for name in tables
                if any(token in name.lower() for token in ("stditem", "monster", "magic"))
            ]
            sections: list[str] = [f"数据库：{db_path.name}"]
            for table in selected[:6]:
                quoted = '"' + table.replace('"', '""') + '"'
                columns = [str(row[1]) for row in conn.execute(f"PRAGMA table_info({quoted})").fetchall()]
                if not columns:
                    continue
                preferred_columns = [
                    col for col in columns
                    if col.lower() in {
                        "idx", "id", "name", "itemname", "magicname", "monstername",
                        "stdmode", "shape", "race", "level", "hp", "exp", "job",
                        "dc", "dcmax", "mc", "mcmax", "sc", "scmax", "ac", "ac2", "mac", "mac2",
                    }
                ]
                selected_columns = (preferred_columns or columns)[:18]
                select_sql = ",".join('"' + col.replace('"', '""') + '"' for col in selected_columns)
                rows = conn.execute(f"SELECT {select_sql} FROM {quoted} LIMIT 2000").fetchall()
                sections.append(f"\n[{table}] 记录数={len(rows)}")
                for row in rows:
                    values = [f"{col}={value}" for col, value in zip(selected_columns, row) if value not in (None, "")]
                    sections.append(" | ".join(values))
            text = "\n".join(sections).strip()
            return (text if len(sections) > 1 else ""), db_path.name
        except sqlite3.Error:
            continue
        finally:
            conn.close()
    return "", ""


def _server_map_inventory(map_root: Path) -> str:
    if not map_root.is_dir():
        return ""
    names = [path.name for path in sorted(map_root.iterdir(), key=lambda value: value.name.lower()) if path.is_file() and path.suffix.lower() == ".map"]
    if not names:
        return ""
    return "地图文件数量：%d\n%s" % (len(names), "\n".join(names[:10_000]))


def _document_chunk_records(
    source: str,
    text: str,
    *,
    title: str,
    tags: str | list[str] | tuple[str, ...] = (),
    chunk_size: int = 900,
    overlap: int = 120,
) -> list[dict[str, Any]]:
    parsed_tags = _parse_tags(tags)
    created_at = datetime.now().isoformat(timespec="seconds")
    return [
        {
            "id": f"{_safe_id(source)}:{index}",
            "source": source,
            "title": title,
            "index": index,
            "text": chunk,
            "tags": list(parsed_tags),
            "created_at": created_at,
        }
        for index, chunk in enumerate(_chunk_text(text, chunk_size=chunk_size, overlap=overlap))
    ]


def _normalize_chunk(item: dict[str, Any]) -> dict[str, Any]:
    source = str(item.get("source", "inline"))
    title = str(item.get("title") or _title_from_source(source))
    index = int(item.get("index", 0) or 0)
    normalized = dict(item)
    normalized.setdefault("source", source)
    normalized.setdefault("title", title)
    normalized.setdefault("index", index)
    normalized.setdefault("id", f"{_safe_id(source)}:{index}")
    normalized.setdefault("tags", [])
    return normalized


def _should_skip_dir(name: str) -> bool:
    return name.lower() in SKIP_DIR_NAMES


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)

    def text(self) -> str:
        return "\n".join(self.parts)


def _normalize_document_text(path: Path, text: str) -> str:
    if path.suffix.lower() not in {".html", ".htm"}:
        return text
    parser = _HTMLTextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        return html.unescape(re.sub(r"<[^>]+>", " ", text))
    extracted = parser.text()
    return html.unescape(extracted or re.sub(r"<[^>]+>", " ", text))


def _chunk_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    chunk_size = max(200, int(chunk_size or 900))
    overlap = max(0, min(int(overlap or 0), chunk_size // 2))
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunks.append(normalized[start:end])
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _query_terms(query: str) -> list[str]:
    parts = [item.strip().lower() for item in re.split(r"[\s,，。:：/\\]+", query) if item.strip()]
    return parts or [query.lower()]


def _matched_trigger_name(query: str, chunks: list[dict[str, Any]]) -> str:
    query_lower = str(query or "").strip().lower()
    if not query_lower:
        return ""
    names = {
        str(tag).split(":", 1)[1].strip()
        for item in chunks
        for tag in item.get("tags", [])
        if str(tag).lower().startswith("trigger:") and str(tag).split(":", 1)[1].strip()
    }
    matches = [name for name in names if query_lower.startswith(name.lower())]
    return max(matches, key=len) if matches else ""


def _score(*, text: str, title: str, tags: tuple[str, ...], query: str, terms: list[str]) -> int:
    lowered = text.lower()
    lowered_title = title.lower()
    lowered_tags = " ".join(tags).lower()
    query_lower = query.lower()
    score = 0
    if query_lower in lowered_title:
        score += 80
    if query_lower in lowered:
        score += 50
    if query_lower in lowered_tags:
        score += 30
    for term in terms:
        term_weight = max(3, len(term))
        score += lowered_title.count(term) * term_weight * 4
        score += lowered.count(term) * term_weight
        score += lowered_tags.count(term) * term_weight * 2
    return score


def _snippet(text: str, query: str, terms: list[str], *, size: int = 180) -> str:
    lowered = text.lower()
    markers = [query.lower(), *terms]
    positions = [lowered.find(marker) for marker in markers if marker and lowered.find(marker) >= 0]
    center = min(positions) if positions else 0
    start = max(0, center - size // 3)
    end = min(len(text), start + size)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet += "..."
    return snippet


def _parse_tags(tags: str | list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(tags, str):
        raw = re.split(r"[,，#\s]+", tags)
    else:
        raw = [str(item) for item in tags]
    result: list[str] = []
    for item in raw:
        tag = item.strip().strip("#")
        if tag and tag not in result:
            result.append(tag)
    return tuple(result)


def _title_from_source(source: str) -> str:
    if not source:
        return "知识片段"
    try:
        path = Path(source)
        if path.name:
            return path.name
    except (OSError, ValueError):
        pass
    return source


def _safe_id(value: str) -> str:
    lowered = value.strip().lower()
    safe = re.sub(r"[^0-9a-zA-Z_\-\u4e00-\u9fff]+", "_", lowered).strip("_")
    return safe[:80] or "knowledge"
