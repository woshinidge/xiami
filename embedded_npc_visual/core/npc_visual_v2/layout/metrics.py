from __future__ import annotations


class TextMetrics:
    def __init__(self, char_width: int = 6, wide_char_width: int = 11) -> None:
        self.char_width = char_width
        self.wide_char_width = wide_char_width

    def width(self, text: str) -> int:
        total = 0
        for ch in text:
            total += self.wide_char_width if ord(ch) > 127 else self.char_width
        return total
