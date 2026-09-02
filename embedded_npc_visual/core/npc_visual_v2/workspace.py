from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ScriptFile:
    key: str
    path: str
    text: str
    encoding: str = ""
    dirty: bool = False


class ScriptWorkspace:
    def __init__(self) -> None:
        self.files: dict[str, ScriptFile] = {}

    def set_file(self, key: str, path: str, text: str, encoding: str = "") -> ScriptFile:
        item = ScriptFile(key=key, path=path, text=text, encoding=encoding)
        self.files[key] = item
        return item

    def get_file(self, key: str) -> ScriptFile | None:
        return self.files.get(key)
