from __future__ import annotations


class UndoStack:
    def __init__(self, limit: int = 80) -> None:
        self.limit = limit
        self._undo: list[str] = []
        self._redo: list[str] = []

    def push(self, source: str) -> None:
        if self._undo and self._undo[-1] == source:
            return
        self._undo.append(source)
        if len(self._undo) > self.limit:
            self._undo.pop(0)
        self._redo.clear()

    def undo(self, current: str) -> str | None:
        if not self._undo:
            return None
        previous = self._undo.pop()
        self._redo.append(current)
        return previous

    def redo(self, current: str) -> str | None:
        if not self._redo:
            return None
        next_source = self._redo.pop()
        self._undo.append(current)
        return next_source
