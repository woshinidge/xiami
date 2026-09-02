from __future__ import annotations

from pathlib import Path

from .call_path import normalize_call_path
from .script_render import FileLoader


def _read_text_guess(path: "Path") -> "str":
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030", "cp936"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _normalize_envir_root(path: "Path") -> "Path":
    if path.name.casefold() == "questdiary":
        return path.parent
    if (path / "QuestDiary").is_dir():
        return path
    mir_envir = path / "Mir200" / "Envir"
    if mir_envir.is_dir():
        return mir_envir
    envir = path / "Envir"
    if envir.is_dir():
        return envir
    return path


def envir_file_loader(envir_root: "Path | None") -> "FileLoader":
    def load(relative_path: str) -> str | None:
        if envir_root is None:
            return None
        root = _normalize_envir_root(envir_root)
        if not root.is_dir():
            return None
        rel = normalize_call_path(relative_path)
        quest_root = root if root.name.casefold() == "questdiary" else root / "QuestDiary"
        candidate = quest_root / rel
        if candidate.is_file():
            return _read_text_guess(candidate)
        return None

    return load


def parse_skip_goto_labels(text: "str") -> "frozenset[str]":
    labels = set()
    for part in text.replace("，", ",").split(","):
        label = part.strip()
        if not label:
            continue
        if not label.startswith("@"):
            label = f"@{label}"
        labels.add(label)
    return frozenset(labels)
