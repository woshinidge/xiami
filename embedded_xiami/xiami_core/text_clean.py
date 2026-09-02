from __future__ import annotations

import re


ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
BROKEN_ANSI_PATTERN = re.compile(r"\[+\d+(?:;\d+)*m\]?")
MOJIBAKE_HINT_PATTERN = re.compile(
    r"[浜鐮淮乁鍔浇閰嶇疆妯绉佽亰鎺ユ敹閫傞厤鍣ㄥ垵濮瀹屾帴铏剧背钏紐绐鋼镯涔濂藉弸缇]"
)
MANUAL_REPAIRS = {
    "浜岀淮鐮佸凡淇濆瓨": "二维码已保存",
    "铏剧背": "虾米",
    "钏剧背": "虾米",
    "鎺ユ敹": "接收",
    "紐ュ敦": "接收",
    "缇よ亰": "群聊",
    "绐你京": "私聊",
    "鍒�": "到",
}


def clean_text(text: object) -> str:
    value = ANSI_PATTERN.sub("", str(text or ""))
    value = BROKEN_ANSI_PATTERN.sub("", value)
    return _repair_mojibake(value).strip()


def clean_optional_text(text: object) -> str:
    if text is None:
        return ""
    return clean_text(text)


def _repair_mojibake(text: str) -> str:
    for source, target in MANUAL_REPAIRS.items():
        text = text.replace(source, target)
    if not MOJIBAKE_HINT_PATTERN.search(text):
        return text
    try:
        repaired = text.encode("gbk").decode("utf-8")
    except UnicodeError:
        return text
    return repaired if _mojibake_score(repaired) < _mojibake_score(text) else text


def _mojibake_score(text: str) -> int:
    return len(MOJIBAKE_HINT_PATTERN.findall(text))
