from __future__ import annotations

import re
import threading
from collections import deque
from subprocess import Popen
from typing import Deque

from xiami_core.path_alias import normalize_alias_path_to_real
from xiami_core.text_clean import clean_text


QR_PATTERNS = (
    re.compile(r"https?://txz\.qq\.com/p\?[^\s\"']+", re.IGNORECASE),
    re.compile(r"https?://[^\s\"']*(?:qrcode|qr|login)[^\s\"']*", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\[^\r\n\"']*(?:qrcode|qr-0|qr_code)\.(?:png|jpg|jpeg)", re.IGNORECASE),
    re.compile(r"\S*(?:qrcode|qr-0|qr_code)\.(?:png|jpg|jpeg)", re.IGNORECASE),
)


class ProcessOutputBuffer:
    def __init__(self, max_lines: int = 200) -> None:
        self.lines: Deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def attach(self, process: Popen[bytes]) -> None:
        if process.stdout:
            threading.Thread(target=self._reader, args=(process.stdout,), daemon=True).start()
        if process.stderr:
            threading.Thread(target=self._reader, args=(process.stderr,), daemon=True).start()

    def snapshot(self, limit: int = 40) -> tuple[str, ...]:
        with self._lock:
            return tuple(list(self.lines)[-limit:])

    def qr_hint(self) -> str:
        for line in reversed(self.snapshot(200)):
            for pattern in QR_PATTERNS:
                match = pattern.search(line)
                if match:
                    return _normalize_qr_hint(match.group(0))
        return ""

    def _reader(self, stream) -> None:
        for raw in iter(stream.readline, b""):
            text = _decode(raw).rstrip()
            if text:
                with self._lock:
                    self.lines.append(text)


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk", "cp936"):
        try:
            return clean_text(data.decode(encoding))
        except UnicodeDecodeError:
            continue
    return clean_text(data.decode("utf-8", errors="replace"))


def _normalize_qr_hint(hint: str) -> str:
    return normalize_alias_path_to_real(hint)
