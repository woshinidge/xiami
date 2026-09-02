from __future__ import annotations


class ResourceCache:
    def __init__(self) -> None:
        self._items: dict[tuple[object, ...], object] = {}

    def get(self, key: tuple[object, ...]) -> object | None:
        return self._items.get(key)

    def set(self, key: tuple[object, ...], value: object) -> None:
        self._items[key] = value

    def clear(self) -> None:
        self._items.clear()
