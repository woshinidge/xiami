from __future__ import annotations

import re


def normalize_call_path(path: "str | None") -> "str":
    """Normalize Mir #CALL paths so common slash variants share one key."""
    text = str(path or "").strip().replace("\\", "/")
    text = re.sub("/+", "/", text)
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def normalize_call_key(path: "str | None") -> "str":
    return normalize_call_path(path).casefold()

