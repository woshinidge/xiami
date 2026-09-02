from __future__ import annotations

import os
import re
import sqlite3
from functools import lru_cache
from pathlib import Path


_ITEM_LINE_RE = re.compile(r"^\s*1/(\d+)\s+(.+?)\s*$", re.IGNORECASE)
_CHILD_HEADER_RE = re.compile(r"^\s*(#child\s+)1/(\d+)(.*)$", re.IGNORECASE)
_PAREN_OPEN_RE = re.compile(r"^\s*\(\s*$")
_PAREN_CLOSE_RE = re.compile(r"^\s*\)\s*$")
_CALL_RE = re.compile(r"^\s*(?:#ACT\s+)?#call\s*\[\s*(.*?)\s*\]\s*(?:@\s*([^\s;]+))?", re.IGNORECASE)


def _normalize_server_root(root_dir: str) -> str:
    p = os.path.abspath(str(root_dir or "").strip().strip('"').strip("'"))
    if not p:
        return ""
    try:
        if os.path.basename(p).lower() == "monitems":
            return os.path.dirname(os.path.dirname(os.path.dirname(p)))
        if os.path.basename(p).lower() == "envir":
            return os.path.dirname(os.path.dirname(p))
        if os.path.basename(p).lower() == "mir200":
            return os.path.dirname(p)
    except Exception:
        pass
    return p


def _find_monitems_dir(root_dir: str) -> str:
    base = _normalize_server_root(root_dir)
    direct = os.path.join(base, "Mir200", "Envir", "MonItems")
    if os.path.isdir(direct):
        return direct
    for cur_root, dirs, _files in os.walk(base):
        for dn in dirs:
            if dn.lower() == "monitems":
                candidate = os.path.join(cur_root, dn)
                if os.path.isdir(candidate):
                    return candidate
    return ""


def _find_db_dir(root_dir: str) -> Path | None:
    root = Path(_normalize_server_root(root_dir))
    candidates = [
        root / "Mir200" / "DB",
        root / "DB",
        root / "Mud2" / "DB",
        root / "Mud2" / "Mud2" / "DB",
        root / "Mir200" / "M2Data",
    ]
    def _score_dir(candidate: Path) -> int:
        try:
            if not candidate.exists() or (not candidate.is_dir()):
                return -1
            score = 0
            names = {p.name.lower() for p in candidate.iterdir() if p.is_file()}
            if "stditems.db" in names:
                score += 100
            if "apexm2.db" in names:
                score += 60
            if "items.db" in names:
                score += 40
            if "stditems.txt" in names or "items.txt" in names:
                score += 20
            if any("stditems" in name for name in names):
                score += 10
            return score
        except Exception:
            return -1
    best: Path | None = None
    best_score = -1
    for candidate in candidates:
        try:
            score = _score_dir(candidate)
            if score > best_score:
                best = candidate
                best_score = score
        except Exception:
            continue
    if best is not None and best_score >= 0:
        return best
    return None


def _read_text_best_effort(path: str) -> str:
    try:
        data = Path(path).read_bytes()
    except Exception:
        return ""
    if not data:
        return ""
    encodings = ["gbk", "gb18030", "utf-8-sig", "utf-8", "gb2312", "cp936", "latin1"]
    best_text = ""
    best_replace_count: int | None = None
    for enc in encodings:
        try:
            text = data.decode(enc, errors="replace")
        except Exception:
            continue
        replace_count = text.count("\ufffd")
        if best_replace_count is None or replace_count < best_replace_count:
            best_replace_count = replace_count
            best_text = text
            if replace_count == 0:
                break
    return best_text


def _is_sqlite(path: Path) -> bool:
    try:
        with open(path, "rb") as fp:
            header = fp.read(16)
        if header.startswith(b"SQLite format 3"):
            return True
    except Exception:
        pass
    try:
        conn = sqlite3.connect(str(path))
        try:
            cur = conn.cursor()
            cur.execute("PRAGMA schema_version")
            cur.fetchone()
            return True
        finally:
            try:
                conn.close()
            except Exception:
                pass
    except Exception:
        return False


def _strip_inline_comment(text: str) -> str:
    out: list[str] = []
    quote = None
    for ch in str(text or ""):
        if ch in ("'", '"'):
            if quote is None:
                quote = ch
            elif quote == ch:
                quote = None
        if quote is None and ch in (";", "#"):
            break
        out.append(ch)
    return "".join(out).strip()


def _normalize_item_name(name: str) -> str:
    text = str(name or "").strip()
    text = text.replace("\ufeff", "").replace("\u200b", "").replace("\u200c", "").replace("\u200d", "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


@lru_cache(maxsize=16)
def _load_all_item_names_cached(root_dir: str) -> tuple[str, ...]:
    root = Path(_normalize_server_root(root_dir))
    if not str(root):
        return tuple()

    sqlite_db: Path | None = None
    std_db: Path | None = None
    try:
        ini_path = root / "Config.ini"
        if ini_path.exists():
            txt = _read_text_best_effort(str(ini_path))
            for line in txt.splitlines():
                line = line.strip()
                if not line or line.startswith(";") or line.startswith("#"):
                    continue
                if line.startswith("[") and line.endswith("]"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.strip().lower() != "sqlitedbname":
                    continue
                db_path_str = _strip_inline_comment(val).strip()
                if (db_path_str.startswith('"') and db_path_str.endswith('"')) or (
                    db_path_str.startswith("'") and db_path_str.endswith("'")
                ):
                    db_path_str = db_path_str[1:-1].strip()
                db_path_str = os.path.expandvars(db_path_str).strip()
                if not db_path_str:
                    break
                p = Path(db_path_str)
                if not p.is_absolute():
                    p = (ini_path.parent / p).resolve()
                if p.exists() and p.is_file():
                    if _is_sqlite(p):
                        sqlite_db = p
                    else:
                        std_db = p
                break
    except Exception:
        pass

    try:
        if sqlite_db is not None and sqlite_db.exists() and sqlite_db.is_file() and not _is_sqlite(sqlite_db):
            sqlite_db = None
    except Exception:
        sqlite_db = None

    try:
        if std_db is not None and std_db.exists() and std_db.is_file():
            if std_db.suffix.lower() != ".txt" and not _is_sqlite(std_db):
                std_db = None
    except Exception:
        std_db = None

    db_dir = _find_db_dir(str(root))
    if db_dir is not None and not db_dir.exists():
        db_dir = None

    if sqlite_db is None and db_dir is not None:
        for cand in [
            db_dir / "ApexM2.DB",
            db_dir / "GEEM2.db",
            db_dir / "GOM.db",
            db_dir / "GeeM2.db",
            db_dir / "ApexM2.db",
        ]:
            try:
                up = cand.name.upper()
                if not cand.exists():
                    continue
                if ("副本" in cand.name) or ("备份" in cand.name) or ("COPY" in up) or ("BACKUP" in up) or up.endswith(".BAK") or ("TMP" in up) or ("OLD" in up):
                    continue
                if _is_sqlite(cand):
                    sqlite_db = cand
                    break
            except Exception:
                continue

    if sqlite_db is None and db_dir is not None:
        try:
            db_candidates = sorted(
                [p for p in db_dir.glob("*.db") if p.is_file()],
                key=lambda p: (
                    0 if p.name.lower() in {"apexm2.db", "geem2.db", "gom.db"} else 1,
                    0 if "stditems" not in p.name.lower() else 1,
                    p.name.lower(),
                ),
            )
        except Exception:
            db_candidates = []
        for cand in db_candidates:
            try:
                up = cand.name.upper()
                if ("副本" in cand.name) or ("备份" in cand.name) or ("COPY" in up) or ("BACKUP" in up) or up.endswith(".BAK") or ("TMP" in up) or ("OLD" in up):
                    continue
                if _is_sqlite(cand):
                    sqlite_db = cand
                    break
            except Exception:
                continue

    if std_db is None and db_dir is not None:
        for cand in [db_dir / "StdItems.DB", db_dir / "Items.DB", db_dir / "stditems.db", db_dir / "STDITEMS.DB"]:
            try:
                up = cand.name.upper()
                if not cand.exists():
                    continue
                if ("副本" in cand.name) or ("备份" in cand.name) or ("COPY" in up) or ("BACKUP" in up) or up.endswith(".BAK") or ("TMP" in up) or ("OLD" in up):
                    continue
                if _is_sqlite(cand):
                    std_db = cand
                    break
            except Exception:
                continue
        if std_db is None:
            for cand in [db_dir / "StdItems.txt", db_dir / "Items.txt"]:
                try:
                    up = cand.name.upper()
                    if not cand.exists():
                        continue
                    if ("副本" in cand.name) or ("备份" in cand.name) or ("COPY" in up) or ("BACKUP" in up) or up.endswith(".BAK") or ("TMP" in up) or ("OLD" in up):
                        continue
                    std_db = cand
                    break
                except Exception:
                    continue

    if std_db is None and db_dir is not None:
        try:
            txts = list(db_dir.glob("*.txt"))
            txts_sorted = sorted(
                txts,
                key=lambda p: (0 if "stditems" in p.name.lower() else (1 if "items" in p.name.lower() else 2), p.name.lower()),
            )
            if txts_sorted:
                std_db = txts_sorted[0]
        except Exception:
            pass

    names: list[str] = []
    if sqlite_db and _is_sqlite(sqlite_db):
        conn = None
        try:
            conn = sqlite3.connect(str(sqlite_db))
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [r[0] for r in cur.fetchall()]

            def _pick_first(colnames, candidates):
                low_to_orig = {}
                for c in colnames:
                    try:
                        low_to_orig[str(c).lower()] = c
                    except Exception:
                        continue
                for cand in candidates:
                    if cand in low_to_orig:
                        return low_to_orig[cand]
                return None

            def _table_meta(tname):
                try:
                    cur.execute(f"PRAGMA table_info({tname})")
                    meta = cur.fetchall()
                    colnames = [row[1] for row in meta]
                except Exception:
                    return None
                name_col = _pick_first(colnames, ["name", "itemname"])
                idx_col = _pick_first(colnames, ["idx", "id", "itemid"])
                del_col = _pick_first(colnames, ["del", "deleted", "delflag", "del_flag", "isdel", "is_del", "isdelete", "is_delete", "is_deleted"])
                if not name_col:
                    return None
                t_low = str(tname).lower()
                score = 0
                if "stditems" in t_low:
                    score += 100
                elif t_low == "items":
                    score += 40
                elif "item" in t_low:
                    score += 20
                if name_col and idx_col:
                    score += 10
                return {"table": tname, "score": score, "name_col": name_col, "idx_col": idx_col, "del_col": del_col}

            metas = []
            for table in tables:
                meta = _table_meta(table)
                if meta:
                    metas.append(meta)

            def _is_bad_table_name(tname: str) -> bool:
                t_low = (tname or "").lower()
                bad_words = ["log", "history", "record", "temp", "tmp", "backup", "bak", "copy", "old"]
                return any(w in t_low for w in bad_words)

            def _pick_best_table(cands: list[dict]) -> list[dict]:
                if not cands:
                    return []
                good = [m for m in cands if not _is_bad_table_name(str(m.get("table", "")))]
                pool = good or cands

                def _key(m: dict) -> tuple:
                    t_low = str(m.get("table", "")).lower()
                    prefer = 0
                    if t_low == "stditems":
                        prefer = 3
                    elif t_low == "std_items":
                        prefer = 2
                    elif "stditems" in t_low:
                        prefer = 1
                    return (prefer, int(m.get("score", 0)))

                return [max(pool, key=_key)]

            exact_stditems_metas = [m for m in metas if (str(m.get("table", "")).lower() in {"stditems", "std_items"} and m.get("idx_col"))]
            if exact_stditems_metas:
                tables_to_read = _pick_best_table(exact_stditems_metas)
            else:
                stditems_metas = [m for m in metas if ("stditems" in str(m.get("table", "")).lower() and m.get("idx_col"))]
                if stditems_metas:
                    tables_to_read = _pick_best_table(stditems_metas)
                else:
                    tables_to_read = _pick_best_table(sorted(metas, key=lambda x: x.get("score", 0), reverse=True)[:3])

            seen: set[tuple[str, object]] = set()
            for meta in tables_to_read:
                try:
                    idx_col = meta.get("idx_col")
                    name_col = meta.get("name_col")
                    del_col = meta.get("del_col")
                    cols_select = ", ".join([c for c in [idx_col, name_col] if c])
                    where = f" WHERE COALESCE({del_col}, 0) = 0" if del_col else ""
                    cur.execute(f"SELECT {cols_select} FROM {meta['table']}{where}")
                    rows = cur.fetchall()
                except Exception:
                    continue
                for row in rows:
                    ridx = None
                    name = ""
                    pos = 0
                    if idx_col:
                        try:
                            ridx = int(row[pos]) if row[pos] is not None else None
                        except Exception:
                            ridx = None
                        pos += 1
                    try:
                        name = str(row[pos]) if row[pos] is not None else ""
                    except Exception:
                        name = ""
                    name = _normalize_item_name(name)
                    if not name:
                        continue
                    key = ("idx", ridx) if ridx is not None else ("name", name.lower())
                    if key in seen:
                        continue
                    seen.add(key)
                    names.append(name)
        finally:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
    elif std_db and std_db.suffix.lower() == ".txt":
        txt = _read_text_best_effort(str(std_db))
        seen_names: set[str] = set()
        for line in txt.splitlines():
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split("\t") if p.strip()]
            if not parts:
                continue
            kvs = {}
            for seg in parts:
                m = re.match(r"([A-Za-z_]+)\s*[:=]\s*(.+)", seg)
                if m:
                    kvs[m.group(1).strip()] = m.group(2).strip()
            name = kvs.get("Name") or kvs.get("ItemName")
            if not name:
                mname = re.search(r"Name\s*[:=][^\S\t]*([^\t;,]*)", line, re.I)
                if mname:
                    name = mname.group(1).strip()
            if not name:
                cols = re.split(r"[\t ]+", line.strip())
                if len(cols) >= 2 and cols[0].isdigit():
                    name = cols[1]
            name = _normalize_item_name(name)
            if not name:
                continue
            low = name.lower()
            if low in seen_names:
                continue
            seen_names.add(low)
            names.append(name)

    dedup: list[str] = []
    seen_final: set[str] = set()
    for name in names:
        norm = _normalize_item_name(name)
        if not norm:
            continue
        low = norm.lower()
        if low in seen_final:
            continue
        seen_final.add(low)
        dedup.append(norm)
    return tuple(dedup)


def _resolve_call_doc_path(root_path: str, middle_path: str, full_path: str) -> str:
    full_path = (full_path or "").replace("\ufeff", "").strip().strip('"').strip("'")
    full_path = full_path.replace("/", "\\")
    quest_base = os.path.abspath(os.path.join(root_path, middle_path))

    if os.path.isabs(full_path):
        abs_path = os.path.abspath(full_path)
        if os.path.exists(abs_path):
            return abs_path

    p = full_path.strip().lstrip("\\")
    p = re.sub(r"^(?:\.\.?\\)+", "", p)
    m = re.search(r"(?i)(?:^|\\)questdiary\\", p)
    if m:
        rel = p[m.end() :]
    else:
        m2 = re.search(r"(?i)mir200\\envir\\questdiary\\", p)
        rel = p[m2.end() :] if m2 else p
    rel = rel.lstrip("\\")
    new_doc_path = os.path.abspath(os.path.join(quest_base, rel))
    if not os.path.exists(new_doc_path):
        alternative_path = os.path.abspath(os.path.join(root_path, rel))
        if os.path.exists(alternative_path):
            new_doc_path = alternative_path
    return new_doc_path


def _expand_call_includes_text(text: str, base_dir: Path, root_dir: str, depth: int = 8) -> str:
    if not text or depth <= 0:
        return ""
    root_dir = _normalize_server_root(root_dir)
    quest_middle = os.path.join("Mir200", "Envir", "QuestDiary")
    envir_dir = Path(root_dir) / "Mir200" / "Envir"

    def _extract_label_block(text2: str, label: str) -> str:
        if not text2:
            return ""
        lb = str(label or "").strip()
        if lb.startswith("@"):
            lb = lb[1:].strip()
        if not lb:
            return ""
        lines = text2.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        pat = re.compile(rf"^\s*\[@\s*{re.escape(lb)}\s*\]\s*$", re.IGNORECASE)
        start_idx = None
        for idx, line in enumerate(lines):
            if pat.match((line or "").strip()):
                start_idx = idx + 1
                break
        if start_idx is None:
            return ""
        out: list[str] = []
        for line in lines[start_idx:]:
            if re.match(r"^\s*\[@", (line or "")):
                break
            out.append(line)
        return "\n".join(out).strip()

    def _resolve_call_target_path(call_path: str, base_dir2: Path) -> Path | None:
        p = (call_path or "").replace("\ufeff", "").strip().strip('"').strip("'")
        if not p:
            return None
        p = p.replace("/", "\\")
        try:
            if os.path.isabs(p):
                abs_path = Path(p).resolve()
                if abs_path.exists() and abs_path.is_file():
                    return abs_path
        except Exception:
            pass
        try:
            doc_path = Path(_resolve_call_doc_path(root_dir, quest_middle, p))
            if doc_path.exists() and doc_path.is_file():
                return doc_path
        except Exception:
            pass
        rel = p.lstrip("\\/")
        candidates = [Path(root_dir) / rel, envir_dir / rel, base_dir2 / rel]
        for candidate in candidates:
            try:
                if candidate.exists() and candidate.is_file():
                    return candidate
            except Exception:
                continue
        return None

    def _expand_calls(text2: str, base_dir2: Path, seen: set[tuple[str, str]], depth2: int) -> str:
        if not text2 or depth2 <= 0:
            return ""
        buf: list[str] = []
        for line in text2.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            s = (line or "").strip()
            if not s or s.startswith(";"):
                continue
            match = _CALL_RE.match(s)
            if not match:
                continue
            rel_path = (match.group(1) or "").strip()
            label = (match.group(2) or "").strip()
            if not rel_path:
                continue
            target = _resolve_call_target_path(rel_path, base_dir2)
            if target is None:
                continue
            try:
                key_path = str(target.resolve()).lower()
            except Exception:
                key_path = str(target).lower()
            key = (key_path, label.lower())
            if key in seen:
                continue
            seen.add(key)
            content = _read_text_best_effort(str(target))
            if not content:
                continue
            block = _extract_label_block(content, label) or content
            buf.append(block)
            more = _expand_calls(block, target.parent, seen, depth2 - 1)
            if more:
                buf.append(more)
        return "\n".join(buf)

    return _expand_calls(text, Path(base_dir), set(), depth)


def _collect_item_names_from_text(text: str) -> set[str]:
    out: set[str] = set()
    if not text:
        return out
    lines = text.splitlines()
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        stripped = str(line or "").strip()
        if not stripped or stripped.startswith(";") or stripped.startswith("#"):
            child_match = _CHILD_HEADER_RE.match(line)
            if child_match:
                k = idx + 1
                while k < len(lines) and not str(lines[k] or "").strip():
                    k += 1
                if k < len(lines) and _PAREN_OPEN_RE.match(lines[k]):
                    end = k + 1
                    while end < len(lines) and not _PAREN_CLOSE_RE.match(lines[end]):
                        end += 1
                    if end < len(lines):
                        for inner in range(k + 1, end):
                            item_match = _ITEM_LINE_RE.match(lines[inner])
                            if not item_match:
                                continue
                            try:
                                den = int(item_match.group(1))
                            except Exception:
                                den = 0
                            if den <= 0:
                                continue
                            name = _normalize_item_name(item_match.group(2))
                            if name:
                                out.add(name)
                        idx = end + 1
                        continue
            idx += 1
            continue
        item_match = _ITEM_LINE_RE.match(line)
        if item_match:
            try:
                den = int(item_match.group(1))
            except Exception:
                den = 0
            if den > 0:
                name = _normalize_item_name(item_match.group(2))
                if name:
                    out.add(name)
        idx += 1
    return out


@lru_cache(maxsize=16)
def _load_item_names_cached(root_dir: str) -> tuple[str, ...]:
    root = _normalize_server_root(root_dir)
    mon_dir = _find_monitems_dir(root)
    if not mon_dir or not os.path.isdir(mon_dir):
        return tuple()
    try:
        files = sorted(f for f in os.listdir(mon_dir) if str(f).lower().endswith(".txt"))
    except Exception:
        files = []
    names: set[str] = set()
    for fn in files:
        fp = os.path.join(mon_dir, fn)
        text = _read_text_best_effort(fp)
        if not text:
            continue
        try:
            expanded = _expand_call_includes_text(text, Path(fp).parent, root, 8)
            if expanded:
                text = f"{text}\n{expanded}"
        except Exception:
            pass
        names.update(_collect_item_names_from_text(text))
    return tuple(sorted(names))


def load_item_names(root_dir: str) -> list[str]:
    return list(_load_item_names_cached(_normalize_server_root(root_dir)))


def load_all_item_names(root_dir: str) -> list[str]:
    return list(_load_all_item_names_cached(_normalize_server_root(root_dir)))
