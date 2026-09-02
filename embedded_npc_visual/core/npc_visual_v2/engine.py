from __future__ import annotations

from collections.abc import Callable

from .ast import LayoutDocument, NpcDocument
from .layout.engine import LayoutEngineV2


class NpcVisualEngine:
    def __init__(
        self,
        parse_provider: Callable[[str, str], NpcDocument] | None = None,
    ) -> None:
        self._parse_provider = parse_provider
        self.layout_engine = LayoutEngineV2()

    def parse(self, source_text: str, file_key: str = "__main__") -> NpcDocument:
        if self._parse_provider is None:
            raise RuntimeError("NPC parser provider is not configured")
        document = self._parse_provider(source_text, file_key)
        if not isinstance(document, NpcDocument):
            raise TypeError("NPC parser provider returned an invalid document")
        return document

    def layout(
        self,
        document: NpcDocument,
        label: str = "",
        image_size_resolver: Callable[[object], tuple[int, int]] | None = None,
    ) -> LayoutDocument:
        block = document.label_by_name(label) if label else document.labels[0] if document.labels else None
        return self.layout_engine.layout(block, image_size_resolver=image_size_resolver)
