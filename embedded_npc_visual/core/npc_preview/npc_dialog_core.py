from __future__ import annotations

from datetime import datetime
import re
from dataclasses import dataclass, field
from typing import Iterable


@dataclass
class SourceRef:
    key: str
    start: int
    end: int
    line: int
    column: int
    raw: str
    exact: bool = True


@dataclass(frozen=True)
class SourceMapEntry:
    generated_start: int
    generated_end: int
    source_ref: SourceRef


@dataclass
class NpcNode:
    kind: str
    text: str = ""
    command: str = ""
    attrs: dict[str, str] = field(default_factory=dict)
    source_ref: SourceRef | None = None


@dataclass
class MerchantBigDlg:
    wil_index: int
    image_index: int
    movable: int = 0
    position: int = 4
    offset_x: int = 0
    offset_y: int = 0
    show_close: int = 0
    close_x: int = 0
    close_y: int = 0
    persistent: int = 0


@dataclass
class NpcDialog:
    source: str
    nodes: list[NpcNode]
    merchant_bigdlg: MerchantBigDlg | None = None
    label: str = "主对话"
    line_start: int = 0
    line_end: int = 0

    @property
    def commands(self) -> list[str]:
        return [node.command for node in self.nodes if node.command]


PLAYIMGEX_RE = re.compile(r"^playimgex(?P<body>.*)$", re.IGNORECASE | re.DOTALL)
PLAYIMG_RE = re.compile(r"^playimg(?P<body>.*)$", re.IGNORECASE | re.DOTALL)
IMGEX_RE = re.compile(r"^imgex(?P<body>.*)$", re.IGNORECASE | re.DOTALL)
ITEMSHOW_RE = re.compile(r"^itemshow(?P<body>.*)$", re.IGNORECASE)
ITEMBOX_RE = re.compile(r"^itembox(?P<body>.*)$", re.IGNORECASE)
PROGRESSBAR_RE = re.compile(r"^progressbar(?P<body>.*)$", re.IGNORECASE)
INPUTTEXT_RE = re.compile(r"^inputtext(?P<body>.*)$", re.IGNORECASE | re.DOTALL)
INPUTNUM_RE = re.compile(r"^inputnum(?P<body>.*)$", re.IGNORECASE | re.DOTALL)
LISTVIEW_RE = re.compile(r"^listview(?P<body>\s*:.*)$", re.IGNORECASE)
LAYOUT_RE = re.compile(r"^layout(?P<body>\s*:.*)$", re.IGNORECASE)
MTEXT_RE = re.compile(r"^mtext(?P<body>\s*:.*)$", re.IGNORECASE)
NEWLINE_RE = re.compile(r"^newline(?P<body>\s*:?.*)$", re.IGNORECASE)
TEXT_RE = re.compile(r"^text(?P<body>\s*:.*)$", re.IGNORECASE)
IMG_RE = re.compile(r"^img(?P<body>.*)$", re.IGNORECASE | re.DOTALL)
OPENMERCHANT_RE = re.compile(r"^\s*OPENMERCHANTBIGDLG\b(?P<body>.*)$", re.IGNORECASE)
INLINE_COLOR_RE = re.compile(r"\{(?P<key>AUTOCOLOR|FCOLOR|SCOLOR)\s*=\s*(?P<value>[^{}]+)\}", re.IGNORECASE)
SCRIPT_LABEL_RE = re.compile(r"^\s*\[@(?P<label>[^\]]+)\]\s*$")
BRACED_STYLE_RE = re.compile(r"^(?P<text>.+?)(?P<style>/(?:FCOLOR|SCOLOR|AUTOCOLOR)\s*=.*)$", re.IGNORECASE)
MOV_ASSIGN_RE = re.compile(r"^\s*mov\s+(?P<name>\S+)(?:\s+(?P<value>.*?))?\s*$", re.IGNORECASE)
SCRIPT_HEADER_DECL_RE = re.compile(r"^\(\s*@+\S+(?:\s+@+\S+)*\s*\)$", re.IGNORECASE)
SCRIPT_SYSTEM_FLAG_RE = re.compile(r"^[+\-%]\d+\s*$")
STR_VARIABLE_RE = re.compile(r"<\$STR\((?P<name>[^)]+)\)>", re.IGNORECASE)
STR_ALPHA_NUMERIC_VARIABLE_RE = re.compile(r"^[A-Za-z]+\d+$")
STR_STRING_VARIABLE_RE = re.compile(r"^S\$[^)\s]+$", re.IGNORECASE)
STR_NUMBER_VARIABLE_RE = re.compile(r"^N\$[^)\s]+$", re.IGNORECASE)
NPC_LAYOUT_GAP_CHARS = " \t\ue779"
NPC_IGNORED_CONTROL_CHARS = "\ue779"
NPC_BUILTIN_VARIABLES = {"USERNAME": "畅玩可视化"}


def normalize_command(command: str) -> str:
    command = command.strip()
    if command.startswith("@"):
        return command
    return command


def is_input_command(command: str) -> bool:
    return command.lower().startswith("@@inputstring")


def split_tag_command_body(body: str) -> tuple[str, str]:
    body = body.strip(" :")
    command = ""
    if "/@" in body:
        body, label = body.rsplit("/@", 1)
        command = normalize_command("@" + label)
    elif "/" in body:
        body, command = body.rsplit("/", 1)
        command = normalize_command(command)
    return body, command


def split_text_tag_command_body(body: str) -> tuple[str, str]:
    body = body.strip()
    if body.startswith(":"):
        body = body[1:]
    command = ""
    if "/@" in body:
        body, label = body.rsplit("/@", 1)
        command = normalize_command("@" + label)
    elif "/" in body:
        body, command = body.rsplit("/", 1)
        command = normalize_command(command)
    return body, command


def apply_absolute_attr(attrs: dict[str, str], absolute: bool) -> None:
    if absolute:
        attrs["absolute"] = "1"


def extract_container_ref(body: str) -> tuple[dict[str, str], str]:
    attrs: dict[str, str] = {}
    value = body.strip()
    leading_colon = value.startswith(":")
    if leading_colon:
        value = value[1:]
    if ":" in value:
        first, rest = value.split(":", 1)
    else:
        first, rest = value, ""
    if "~" not in first:
        return attrs, body
    parent_id, child_id = first.split("~", 1)
    attrs["parent_id"] = parent_id.strip()
    attrs["child_id"] = child_id.strip()
    attrs["container_ref"] = first.strip()
    prefix = ":" if leading_colon else ""
    return attrs, prefix + rest


def parse_y_input_tooltip(attrs: dict[str, str], tail: str) -> None:
    y_part = tail.strip()
    tooltip_part = ""
    if "|" in y_part:
        y_part, tooltip_part = y_part.split("|", 1)
    input_ids = ""
    if ":" in y_part:
        possible_y, possible_input_ids = y_part.split(":", 1)
        if _looks_like_input_id_list(possible_input_ids):
            y_part = possible_y
            input_ids = possible_input_ids.strip()
    attrs["y"] = y_part.strip()
    if input_ids:
        attrs["input_ids"] = input_ids
    if tooltip_part:
        _label, compact_attrs = extract_compact_label_attrs(f'{attrs["y"]}|{tooltip_part}')
        attrs.update(compact_attrs)
    elif "#" in attrs["y"]:
        y_value, compact_attrs = extract_compact_label_attrs(attrs["y"])
        attrs["y"] = y_value.strip()
        attrs.update(compact_attrs)


def parse_img_attrs(body: str) -> tuple[dict[str, str], str]:
    body = body.strip()
    if body.startswith(":"):
        body = body[1:].strip()
    attrs: dict[str, str] = {}
    if not body:
        return attrs, ""
    command = ""
    if "/@" in body:
        body, label = body.rsplit("/@", 1)
        command = normalize_command("@" + label)
    elif "/" in body:
        body, command = body.rsplit("/", 1)
        command = normalize_command(command)
    body = body.strip()
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    colon_values = [part.strip() for part in body.split(":", 3)]
    if len(colon_values) == 4 and all(value != "" for value in colon_values[:3]):
        attrs["index"], attrs["file"], attrs["x"] = colon_values[:3]
        parse_y_input_tooltip(attrs, colon_values[3])
        if attrs.get("y", "") == "":
            attrs["y"] = "0"
        attrs.setdefault("input_ids", "")
        attrs.setdefault("default", attrs.get("index", ""))
        attrs["_img_kind"] = "resource"
        return attrs, command
    values = [part.strip() for part in re.split(r"[\s,;:]+", body) if part.strip()]
    if len(values) >= 4:
        names = ["index", "file", "x", "y", "input_ids"]
        for index, value in enumerate(values):
            key = names[index] if index < len(names) else f"arg{index}"
            attrs[key] = value
        parse_y_input_tooltip(attrs, attrs.get("y", ""))
        if attrs.get("y", "") == "":
            attrs["y"] = "0"
        attrs.setdefault("input_ids", "")
        attrs.setdefault("default", attrs.get("index", ""))
        attrs["_img_kind"] = "resource"
        return attrs, command
    positional = ["index", "frame", "x", "y"]
    pos_i = 0
    for part in values:
        if "=" in part:
            key, value = part.split("=", 1)
            attrs[key.strip().lower()] = value.strip().strip('"\'')
        elif part.lstrip("-").isdigit():
            key = positional[pos_i] if pos_i < len(positional) else f"arg{pos_i}"
            attrs.setdefault(key, part)
            pos_i += 1
        else:
            attrs.setdefault("raw", part)
    return attrs, command


def parse_style_block(style: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for part in style.split(";"):
        value = part.strip()
        if not value or "=" not in value:
            continue
        key, attr_value = value.split("=", 1)
        attrs[key.strip().upper()] = attr_value.strip()
    return attrs


def parse_positioned_text_attrs(body: str, absolute: bool = False) -> tuple[str, dict[str, str], str]:
    body, command = split_text_tag_command_body(body)
    attrs: dict[str, str] = {}
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    style_match = re.search(r"\{(?P<style>[^{}]*)\}\s*$", body)
    if style_match:
        attrs.update(parse_style_block(style_match.group("style")))
        body = body[: style_match.start()].rstrip()
    body = body.rstrip()
    if body.startswith(":"):
        body = body[1:]
    x = "0"
    y = "0"
    head = body
    parts = body.rsplit(":", 2)
    if len(parts) == 3:
        head, x, y = parts[0], parts[1].strip(), parts[2].strip()
    elif attrs.get("parent_id") or attrs.get("child_id"):
        attrs["flow"] = "1"
    text = head
    tooltip = ""
    if "|" in text:
        text, tooltip = text.split("|", 1)
    elif ":" in text:
        text, tooltip = text.split(":", 1)
    attrs["x"] = x
    attrs["y"] = y
    apply_absolute_attr(attrs, absolute)
    if tooltip.strip():
        attrs["tooltip"] = tooltip.strip()
    return replace_npc_variables(text), attrs, command


def parse_imgex_attrs(body: str) -> tuple[dict[str, str], str]:
    body, command = split_tag_command_body(body)
    attrs: dict[str, str] = {}
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    values = [part.strip() for part in body.split(":", 5)]
    if len(values) >= 6:
        attrs["file"], attrs["default"], attrs["hover"], attrs["down"], attrs["x"] = values[:5]
        parse_y_input_tooltip(attrs, values[5])
    else:
        names = ["file", "default", "hover", "down", "x", "y", "input_ids"]
        values = [part.strip() for part in re.split(r"[\s,;:]+", body) if part.strip()]
        for index, value in enumerate(values):
            key = names[index] if index < len(names) else f"arg{index}"
            attrs[key] = value
        parse_y_input_tooltip(attrs, attrs.get("y", ""))
    attrs.setdefault("index", attrs.get("default", ""))
    attrs.setdefault("input_ids", "")
    attrs["_img_kind"] = "imgex"
    return attrs, command


def _looks_like_input_id_list(value: str) -> bool:
    return bool(re.fullmatch(r"\*|-?\d+(?:,-?\d+)*", value.strip()))


def parse_playimg_attrs(body: str, with_repeat: bool = False) -> tuple[dict[str, str], str]:
    body, command = split_tag_command_body(body)
    container_attrs, body = extract_container_ref(body)
    fixed_names = (
        ["file", "index", "frame_count", "speed", "repeat", "x", "y", "draw_mode"]
        if with_repeat
        else ["file", "index", "frame_count", "speed", "x", "y", "draw_mode"]
    )
    parts = [part.strip() for part in body.split(":", len(fixed_names))]
    attrs: dict[str, str] = {}
    attrs.update(container_attrs)
    for index, name in enumerate(fixed_names):
        attrs[name] = parts[index] if index < len(parts) else ""
    remainder = parts[len(fixed_names)] if len(parts) > len(fixed_names) else ""
    remark = remainder.strip()
    input_ids = ""
    if ":" in remark:
        possible_remark, possible_input_ids = remark.rsplit(":", 1)
        if _looks_like_input_id_list(possible_input_ids):
            remark = possible_remark.strip()
            input_ids = possible_input_ids.strip()
    if remark:
        attrs["tooltip"] = remark
        attrs["remark"] = remark
    if input_ids:
        attrs["input_ids"] = input_ids
    attrs.setdefault("default", attrs.get("index", ""))
    attrs["_img_kind"] = "play"
    attrs["_play_kind"] = "playimgex" if with_repeat else "playimg"
    return attrs, command


def parse_itemshow_attrs(body: str) -> dict[str, str]:
    body = body.strip(" :")
    attrs: dict[str, str] = {}
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    names = ["item_id", "count", "x", "y", "background"]
    values = [part.strip() for part in re.split(r"[\s,;:]+", body) if part.strip()]
    for index, value in enumerate(values):
        key = names[index] if index < len(names) else f"arg{index}"
        attrs[key] = value
    return attrs


def parse_itembox_attrs(body: str) -> dict[str, str]:
    body = body.strip(" :")
    attrs: dict[str, str] = {}
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    names = ["box_id", "file", "index", "x", "y", "width", "height", "stdmode", "tooltip"]
    values = [part.strip() for part in body.split(":", 8)]
    for index, value in enumerate(values):
        key = names[index] if index < len(names) else f"arg{index}"
        attrs[key] = value
    return attrs


def parse_progressbar_attrs(body: str) -> tuple[dict[str, str], str]:
    body, command = split_tag_command_body(body)
    container_attrs, body = extract_container_ref(body)
    names = [
        "x", "y", "file", "background", "progress", "frame_count", "speed",
        "progress_x", "progress_y", "min", "max", "value", "direction", "color",
        "text_x", "text_y", "text", "remark",
    ]
    values = [part.strip() for part in body.strip(" :").split(":", len(names) - 1)]
    attrs: dict[str, str] = {}
    attrs.update(container_attrs)
    for index, name in enumerate(names):
        attrs[name] = values[index] if index < len(values) else ""
    attrs["text"] = replace_npc_variables(attrs.get("text", ""))
    return attrs, command


def parse_inputbox_attrs(body: str, input_type: str) -> tuple[dict[str, str], str]:
    body, command = split_tag_command_body(body)
    container_attrs, body = extract_container_ref(body)
    names = [
        "input_id", "x", "y", "width", "height", "mode", "text_color",
        "background_color", "min", "max", "message", "placeholder", "limit",
    ]
    values = [part.strip() for part in body.strip(" :").split(":", len(names) - 1)]
    attrs: dict[str, str] = {}
    attrs.update(container_attrs)
    for index, name in enumerate(names):
        attrs[name] = values[index] if index < len(values) else ""
    attrs["input_type"] = input_type
    return attrs, command


def parse_layout_attrs(body: str) -> dict[str, str]:
    body = body.strip(" :")
    attrs: dict[str, str] = {}
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    names = ["x", "y", "width", "height", "border_color"]
    values = [part.strip() for part in body.split(":", len(names) - 1)]
    for index, name in enumerate(names):
        attrs[name] = values[index] if index < len(values) else ""
    attrs.setdefault("child_gap", "0")
    attrs.setdefault("direction", "0")
    return attrs


def parse_listview_attrs(body: str) -> dict[str, str]:
    body = body.strip(" :")
    attrs: dict[str, str] = {}
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    names = [
        "x", "y", "width", "height", "child_gap", "start_index", "direction",
        "reserved3", "reserved4", "reserved5", "scroll_file", "scroll_bg",
        "up_default", "up_hover", "up_down", "thumb_default", "thumb_hover",
        "thumb_down", "down_default", "down_hover", "down_down",
    ]
    values = [part.strip() for part in body.split(":", len(names) - 1)]
    for index, name in enumerate(names):
        attrs[name] = values[index] if index < len(values) else ""
    attrs.setdefault("child_gap", "0")
    attrs.setdefault("direction", "0")
    return attrs


def parse_mtext_attrs(body: str) -> tuple[str, dict[str, str]]:
    body = body.strip()
    attrs: dict[str, str] = {}
    if body.startswith(":"):
        body = body[1:]
    container_attrs, body = extract_container_ref(body)
    attrs.update(container_attrs)
    names = ["x", "y", "FCOLOR", "text"]
    values = [part.strip() for part in body.split(":", len(names) - 1)]
    for index, name in enumerate(names):
        attrs[name] = values[index] if index < len(values) else ""
    text = replace_npc_variables(attrs.pop("text", ""))
    return text, attrs


def parse_newline_attrs(body: str) -> dict[str, str]:
    body = body.strip()
    attrs, _rest = extract_container_ref(body)
    return attrs


def parse_style_attrs(parts: list[str]) -> tuple[str, dict[str, str]]:
    command = ""
    attrs: dict[str, str] = {}
    for part in parts:
        value = part.strip()
        if not value:
            continue
        if value.startswith("@"):
            command = normalize_command(value)
        elif "=" in value:
            key, attr_value = value.split("=", 1)
            attrs[key.strip().upper()] = attr_value.strip()
        elif not command:
            command = normalize_command(value)
    return command, attrs


def extract_inline_color_attrs(text: str) -> tuple[str, dict[str, str]]:
    attrs: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        attrs[match.group("key").upper()] = match.group("value").strip()
        return ""

    return INLINE_COLOR_RE.sub(replace, text), attrs


def extract_compact_label_attrs(label: str) -> tuple[str, dict[str, str]]:
    attrs: dict[str, str] = {}
    tooltip = ""
    if "#" in label:
        head, rest = label.split("#", 1)
        if "|" in head:
            text, color_value = head.rsplit("|", 1)
            color_value = color_value.strip()
            while color_value.startswith("^-") or color_value.startswith("^"):
                if color_value.startswith("^-"):
                    color_value = color_value[2:].strip()
                elif color_value.startswith("^"):
                    color_value = color_value[1:].strip()
            if color_value.isdigit():
                label = text
                attrs["tooltip_color"] = color_value
                tooltip = rest
            else:
                label, tooltip_head = label.split("|", 1)
                tooltip = tooltip_head
        else:
            label, tooltip = head, rest
    elif "|" in label:
        label, tooltip = label.split("|", 1)
    tooltip = replace_npc_variables(tooltip.strip())
    if tooltip:
        attrs["tooltip"] = tooltip
    return label, attrs


def npc_datetime_text(now: datetime | None = None) -> str:
    now = now or datetime.now()
    weekdays = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
    return f"{now:%Y年%m月%d日},{weekdays[now.weekday()]},{now:%H:%M:%S}"


def replace_npc_variables(text: str) -> str:
    result = text
    if "$DATETIME" in result.upper():
        result = re.sub(r"\$DATETIME", npc_datetime_text(), result, flags=re.IGNORECASE)
    for name, value in NPC_BUILTIN_VARIABLES.items():
        result = re.sub(f"<\\$\\s*{re.escape(name)}\\s*>", value, result, flags=re.IGNORECASE)
        result = re.sub(f"\\${re.escape(name)}\\b", value, result, flags=re.IGNORECASE)
    return result


def parse_tag(raw: str) -> NpcNode:
    tag = raw.strip()
    if not tag:
        return NpcNode("noop")
    absolute = tag.startswith("&")
    if absolute:
        tag = tag[1:].lstrip()
    listview_match = LISTVIEW_RE.match(tag)
    if listview_match:
        attrs = parse_listview_attrs(listview_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        return NpcNode("list_view", attrs=attrs)
    layout_match = LAYOUT_RE.match(tag)
    if layout_match:
        attrs = parse_layout_attrs(layout_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        return NpcNode("layout", attrs=attrs)
    mtext_match = MTEXT_RE.match(tag)
    if mtext_match:
        text, attrs = parse_mtext_attrs(mtext_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        return NpcNode("mtext", text, attrs=attrs)
    newline_match = NEWLINE_RE.match(tag)
    if newline_match:
        attrs = parse_newline_attrs(newline_match.group("body"))
        return NpcNode("container_newline", attrs=attrs)
    playimgex_match = PLAYIMGEX_RE.match(tag)
    if playimgex_match:
        attrs, command = parse_playimg_attrs(playimgex_match.group("body"), with_repeat=True)
        apply_absolute_attr(attrs, absolute)
        return NpcNode("image_button", command=command, attrs=attrs)
    playimg_match = PLAYIMG_RE.match(tag)
    if playimg_match:
        attrs, command = parse_playimg_attrs(playimg_match.group("body"), with_repeat=False)
        apply_absolute_attr(attrs, absolute)
        return NpcNode("image_button", command=command, attrs=attrs)
    imgex_match = IMGEX_RE.match(tag)
    if imgex_match:
        attrs, command = parse_imgex_attrs(imgex_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        return NpcNode("image_button", command=command, attrs=attrs)
    itemshow_match = ITEMSHOW_RE.match(tag)
    if itemshow_match:
        attrs = parse_itemshow_attrs(itemshow_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        return NpcNode("item_show", attrs=attrs)
    itembox_match = ITEMBOX_RE.match(tag)
    if itembox_match:
        attrs = parse_itembox_attrs(itembox_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        return NpcNode("item_box", attrs=attrs)
    progressbar_match = PROGRESSBAR_RE.match(tag)
    if progressbar_match:
        attrs, command = parse_progressbar_attrs(progressbar_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        return NpcNode("progress_bar", command=command, attrs=attrs)
    inputtext_match = INPUTTEXT_RE.match(tag)
    if inputtext_match:
        attrs, command = parse_inputbox_attrs(inputtext_match.group("body"), "text")
        apply_absolute_attr(attrs, absolute)
        return NpcNode("input_box", command=command, attrs=attrs)
    inputnum_match = INPUTNUM_RE.match(tag)
    if inputnum_match:
        attrs, command = parse_inputbox_attrs(inputnum_match.group("body"), "num")
        apply_absolute_attr(attrs, absolute)
        return NpcNode("input_box", command=command, attrs=attrs)
    text_match = TEXT_RE.match(tag)
    if text_match:
        text, attrs, command = parse_positioned_text_attrs(text_match.group("body"), absolute=absolute)
        return NpcNode("positioned_text", text, command, attrs)
    img_match = IMG_RE.match(tag)
    if img_match:
        attrs, command = parse_img_attrs(img_match.group("body"))
        apply_absolute_attr(attrs, absolute)
        if attrs.get("_img_kind") == "resource" or command:
            return NpcNode("image_button", command=command, attrs=attrs)
        return NpcNode("image", attrs=attrs)
    is_variable_tag = tag.startswith("$")
    label = tag
    command = ""
    attrs: dict[str, str] = {}
    if "/" in tag:
        parts = tag.split("/")
        label = parts[0]
        command, attrs = parse_style_attrs(parts[1:])
    label, compact_attrs = extract_compact_label_attrs(label)
    for key, value in compact_attrs.items():
        attrs.setdefault(key, value)
    label, inline_attrs = extract_inline_color_attrs(replace_npc_variables(label))
    for key, value in inline_attrs.items():
        attrs.setdefault(key, value)
    if command:
        return NpcNode("input" if is_input_command(command) else "link", label, command, attrs)
    if not is_variable_tag:
        attrs.setdefault("_wrapped", "1")
    return NpcNode("text", label, attrs=attrs)


def parse_braced_tag(raw: str) -> NpcNode | None:
    raw = raw.strip()
    style_match = BRACED_STYLE_RE.match(raw)
    if style_match:
        command, attrs = parse_style_attrs([style_match.group("style").lstrip("/")])
        text = replace_npc_variables(style_match.group("text"))
        if command:
            return NpcNode("input" if is_input_command(command) else "link", text, command, attrs)
        return NpcNode("text", text, attrs=attrs)
    if not raw.startswith("<"):
        return None
    end = raw.find(">")
    if end < 0:
        return None
    converted = raw[1:end] + raw[end + 1 :]
    return parse_tag(converted)


def _section_keyword(line: str) -> str:
    lower = line.strip().lower()
    if re.match(r"^#or(?:\s*\([^)]*\))?$", lower):
        return "#if"
    if re.match(r"^#if(?:\s*\([^)]*\))?$", lower):
        return "#if"
    if lower == "#elseact":
        return "#act"
    if lower == "#elsesay":
        return "#say"
    return lower


def split_npc_sections(source: str) -> tuple[list[str], str]:
    act_lines: list[str] = []
    say_lines: list[str] = []
    section = "say"
    saw_control = False
    saw_say = False
    for line in source.splitlines(keepends=True):
        stripped = line.strip()
        lower = _section_keyword(stripped)
        if lower == "#if":
            section = "if"
            saw_control = True
        elif lower == "#act":
            section = "act"
            saw_control = True
        elif lower == "#say":
            section = "say"
            saw_say = True
        elif section == "act" and not saw_say:
            act_lines.append(line.rstrip("\r\n"))
        elif section == "say" and (saw_say or not saw_control):
            say_lines.append(line)
    if saw_say:
        return act_lines, "".join(say_lines)
    if saw_control:
        return act_lines, ""
    return act_lines, source


def _parse_int(value: str, default: int = 0) -> int:
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return default


def _line_end(source: str, index: int) -> int:
    cr = source.find("\r", index)
    lf = source.find("\n", index)
    stops = [pos for pos in (cr, lf) if pos >= 0]
    if stops:
        return min(stops)
    return len(source)


def _consume_physical_newline(source: str, index: int) -> int:
    if index < len(source) and source[index] == "\r":
        index += 1
        if index < len(source) and source[index] == "\n":
            index += 1
        return index
    if index < len(source) and source[index] == "\n":
        return index + 1
    return index


def _split_physical_newline(line: str) -> tuple[str, str]:
    if line.endswith("\r\n"):
        return line[:-2], "\r\n"
    if line.endswith("\n") or line.endswith("\r"):
        return line[:-1], line[-1]
    return line, ""


def _lstrip_layout_gap(text: str) -> str:
    return text.lstrip(NPC_LAYOUT_GAP_CHARS)


def _rstrip_layout_gap(text: str) -> str:
    return text.rstrip(NPC_LAYOUT_GAP_CHARS)


def _strip_layout_gap(text: str) -> str:
    return text.strip(NPC_LAYOUT_GAP_CHARS)


def _is_ignored_physical_line(line: str) -> bool:
    body, _newline = _split_physical_newline(line)
    stripped = _strip_layout_gap(body)
    return (
        not stripped
        or _lstrip_layout_gap(body).startswith(";")
        or SCRIPT_HEADER_DECL_RE.match(stripped) is not None
        or SCRIPT_SYSTEM_FLAG_RE.match(stripped) is not None
        or _is_mov_assignment_line(line)
    )


def _is_section_marker(line: str) -> bool:
    return _section_keyword(line) in frozenset({"#say", "#if", "#act"})


def _count_backslash_groups(text: str) -> int | None:
    index = 0
    count = 0
    while index < len(text):
        while index < len(text) and text[index] in NPC_LAYOUT_GAP_CHARS:
            index += 1
        if index >= len(text):
            break
        if text[index] != "\\":
            return None
        while index < len(text) and text[index] == "\\":
            index += 1
        count += 1
    if count > 0:
        return count
    return None


def _line_ends_with_backslash_marker(line: str) -> bool:
    body, _newline = _split_physical_newline(line)
    body = _rstrip_layout_gap(body)
    if not body.endswith("\\"):
        return False
    start = len(body) - 1
    while start >= 0 and (body[start] == "\\" or body[start] in NPC_LAYOUT_GAP_CHARS):
        start -= 1
    suffix = body[start + 1 :]
    return _count_backslash_groups(suffix) is not None


def _strip_physical_newline(line: str) -> str:
    body, _newline = _split_physical_newline(line)
    return body


def parse_mov_assignments(source: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in source.splitlines():
        match = MOV_ASSIGN_RE.match(line)
        if match:
            values.setdefault(match.group("name").strip(), (match.group("value") or "").strip())
    return values


def lookup_variable_value(values: dict[str, str], name: str) -> str | None:
    if name in values:
        return values[name]
    folded = name.casefold()
    for key, value in values.items():
        if key.casefold() == folded:
            return value
    return None


def replace_str_variables(source: str, local_values: dict[str, str] | None = None, global_values: dict[str, str] | None = None) -> str:
    local_values = local_values or {}
    global_values = global_values or {}

    def replace(match: re.Match[str]) -> str:
        name = match.group("name").strip()
        value = lookup_variable_value(local_values, name)
        if value is not None:
            return value
        value = lookup_variable_value(global_values, name)
        if value is not None:
            return value
        if STR_STRING_VARIABLE_RE.fullmatch(name):
            return ""
        if STR_NUMBER_VARIABLE_RE.fullmatch(name):
            return "0"
        if STR_ALPHA_NUMERIC_VARIABLE_RE.fullmatch(name):
            return "0"
        return match.group(0)

    result = source
    for _ in range(8):
        updated = STR_VARIABLE_RE.sub(replace, result)
        if updated == result:
            return updated
        result = updated
    return result


def _is_mov_assignment_line(line: str) -> bool:
    body, _newline = _split_physical_newline(line)
    return MOV_ASSIGN_RE.match(body) is not None


def _split_backslash_marker_with_remainder(body: str) -> tuple[str, int, str] | None:
    slash = body.find("\\")
    while slash >= 0:
        index = slash
        count = 0
        while index < len(body):
            while index < len(body) and body[index] in NPC_LAYOUT_GAP_CHARS:
                index += 1
            if index >= len(body) or body[index] != "\\":
                break
            while index < len(body) and body[index] == "\\":
                index += 1
            count += 1
        if count > 0:
            remainder = _strip_layout_gap(body[index:])
            if remainder:
                return _rstrip_layout_gap(body[:slash]), count, remainder
        slash = body.find("\\", slash + 1)
    return None


def _backslash_newline_marker(source: str, index: int) -> tuple[int, int] | None:
    if index >= len(source) or source[index] != "\\":
        return None
    end = _line_end(source, index)
    suffix = source[index:end]
    count = _count_backslash_groups(suffix)
    if count is None:
        return None
    return count, _consume_physical_newline(source, end)


def _backslash_marker(source: str, index: int) -> tuple[int, int] | None:
    if index >= len(source) or source[index] != "\\":
        return None
    end = index
    count = 0
    while end < len(source):
        while end < len(source) and source[end] in NPC_LAYOUT_GAP_CHARS:
            end += 1
        if end >= len(source) or source[end] != "\\":
            break
        while end < len(source) and source[end] == "\\":
            end += 1
        count += 1
    if count <= 0:
        return None
    return count, end


def _is_line_leading_marker(source: str, index: int) -> bool:
    line_start = source.rfind("\n", 0, index) + 1
    return all(ch in NPC_LAYOUT_GAP_CHARS or ch == "\r" for ch in source[line_start:index])


def _marker_has_line_content_after(source: str, marker_end: int) -> bool:
    line_end = _line_end(source, marker_end)
    return bool(_strip_layout_gap(source[marker_end:line_end]))


def _find_img_tag_end(source: str, start: int) -> tuple[int, str]:
    index = start
    variable_depth = 0
    while index < len(source):
        ch = source[index]
        if ch == "<" and index > start and index + 1 < len(source) and source[index + 1] == "$":
            variable_depth += 1
            index += 1
        elif ch == ">":
            if variable_depth > 0:
                variable_depth -= 1
                index += 1
                continue
            return index, ">"
        elif ch == "\\":
            if _backslash_marker(source, index):
                return index, "\\"
        elif ch == "<" and index > start:
            return index, "<"
        index += 1
    return len(source), ""


def _find_tag_end(source: str, start: int) -> int:
    index = start
    variable_depth = 0
    while index < len(source):
        ch = source[index]
        if ch == "<" and index > start and index + 1 < len(source) and source[index + 1] == "$":
            variable_depth += 1
            index += 1
        elif ch == ">":
            if variable_depth > 0:
                variable_depth -= 1
                index += 1
                continue
            return index
        index += 1
    return -1


def _drop_ignored_physical_lines(source: str) -> str:
    lines: list[str] = []
    for line in source.splitlines(keepends=True):
        if not _is_ignored_physical_line(line):
            lines.append(line)
    return "".join(lines)


def _normalize_backslash_remainders(source: str) -> str:
    return source


def _normalize_leading_say_backslashes(source: str) -> str:
    start = 0
    while start < len(source) and source[start] in NPC_LAYOUT_GAP_CHARS:
        start += 1
    if start >= len(source) or source[start] != "\\":
        return source
    line_end = _line_end(source, 0)
    body = source[start:line_end]
    count = _count_backslash_groups(body)
    if count is None or count < 2:
        return source
    next_index = _consume_physical_newline(source, line_end)
    newline = source[line_end:next_index]
    normalized_count = count - 1
    normalized_body = " ".join("\\" for _ in range(normalized_count))
    return normalized_body + newline + source[next_index:]


def _tag_gap_space(source: str, index: int) -> tuple[str, int] | None:
    if index >= len(source) or source[index] not in " \t":
        return None
    end = index
    while end < len(source) and source[end] in " \t":
        end += 1
    prev_index = index - 1
    while prev_index >= 0 and source[prev_index] in " \t":
        prev_index -= 1
    if prev_index < 0 or source[prev_index] not in ">}":
        return None
    if end >= len(source):
        return None
    next_is_tag = source[end] == "<" or (source[end] == "{" and end + 1 < len(source) and source[end + 1] == "<")
    if not next_is_tag:
        return None
    return source[index:end], end


def _mixed_layout_ascii_space(source: str, index: int) -> tuple[str, int] | None:
    if index >= len(source) or source[index] not in " \t":
        return None
    end = index
    while end < len(source) and source[end] in " \t":
        end += 1
    prev_char = source[index - 1] if index > 0 else ""
    next_char = source[end] if end < len(source) else ""
    if prev_char == "\u3000" or next_char == "\u3000":
        return source[index:end], end
    return None


def parse_openmerchantbigdlg(act_lines: Iterable[str]) -> MerchantBigDlg | None:
    for line in act_lines:
        match = OPENMERCHANT_RE.match(line)
        if not match:
            continue
        values = match.group("body").split()
        if len(values) < 2:
            continue
        numbers = [_parse_int(value) for value in values[:10]]
        numbers.extend([0] * (10 - len(numbers)))
        return MerchantBigDlg(
            wil_index=numbers[0],
            image_index=numbers[1],
            movable=numbers[2],
            position=numbers[3],
            offset_x=numbers[4],
            offset_y=numbers[5],
            show_close=numbers[6],
            close_x=numbers[7],
            close_y=numbers[8],
            persistent=numbers[9],
        )
    return None


def _line_column_for_offset(source: str, offset: int) -> tuple[int, int]:
    offset = max(0, min(len(source), offset))
    line = source.count("\n", 0, offset) + 1
    last_newline = source.rfind("\n", 0, offset)
    column = offset if last_newline < 0 else offset - last_newline - 1
    return line, column


def _mapped_line_column(line_ref: SourceRef, relative_offset: int) -> tuple[int, int]:
    relative_offset = max(0, min(len(line_ref.raw), relative_offset))
    line_delta = line_ref.raw.count("\n", 0, relative_offset)
    last_newline = line_ref.raw.rfind("\n", 0, relative_offset)
    if last_newline < 0:
        return line_ref.line, line_ref.column + relative_offset
    return line_ref.line + line_delta, relative_offset - last_newline - 1


def _source_ref_for_range(
    source: str,
    start: int,
    end: int,
    *,
    source_key: str,
    source_offset: int = 0,
    source_line_offset: int = 0,
    source_map: list[SourceMapEntry] | None = None,
) -> SourceRef:
    start = max(0, min(len(source), start))
    end = max(start, min(len(source), end))
    raw = source[start:end]
    if source_map:
        for entry in source_map:
            if entry.generated_start <= start and end <= entry.generated_end:
                line_ref = entry.source_ref
                relative_start = start - entry.generated_start
                relative_end = end - entry.generated_start
                original_raw = line_ref.raw
                if 0 <= relative_start <= relative_end <= len(original_raw) and original_raw[relative_start:relative_end] == raw:
                    line, column = _mapped_line_column(line_ref, relative_start)
                    return SourceRef(
                        line_ref.key,
                        line_ref.start + relative_start,
                        line_ref.start + relative_end,
                        line,
                        column,
                        raw,
                        line_ref.exact,
                    )
                found = original_raw.find(raw) if raw else -1
                if found >= 0:
                    line, column = _mapped_line_column(line_ref, found)
                    return SourceRef(
                        line_ref.key,
                        line_ref.start + found,
                        line_ref.start + found + len(raw),
                        line,
                        column,
                        raw,
                        line_ref.exact,
                    )
                return SourceRef(line_ref.key, line_ref.start, line_ref.end, line_ref.line, line_ref.column, raw, False)
    line, column = _line_column_for_offset(source, start)
    return SourceRef(source_key, source_offset + start, source_offset + end, source_line_offset + line, column, raw, True)


def _drop_ignored_physical_lines_with_map(source: str, source_map: list[SourceMapEntry]) -> tuple[str, list[SourceMapEntry]]:
    lines: list[str] = []
    mapped: list[SourceMapEntry] = []
    read_offset = 0
    write_offset = 0
    for line in source.splitlines(keepends=True):
        line_start = read_offset
        line_end = line_start + len(line)
        read_offset = line_end
        if _is_ignored_physical_line(line):
            continue
        lines.append(line)
        for entry in source_map:
            if line_start <= entry.generated_start and entry.generated_end <= line_end:
                mapped.append(
                    SourceMapEntry(
                        write_offset + entry.generated_start - line_start,
                        write_offset + entry.generated_end - line_start,
                        entry.source_ref,
                    )
                )
        write_offset += len(line)
    return "".join(lines), mapped


def _parse_npc_dialog_parts(
    source: str,
    label: str = "主对话",
    line_start: int = 0,
    line_end: int = 0,
    local_mov_values: dict[str, str] | None = None,
    global_mov_values: dict[str, str] | None = None,
    merge_adjacent_text: bool = True,
    source_key: str = "",
    source_offset: int = 0,
    source_line_offset: int = 0,
    source_map: list[SourceMapEntry] | None = None,
) -> NpcDialog:
    if local_mov_values is None:
        local_mov_values = parse_mov_assignments(source)
    source = replace_str_variables(source, local_mov_values, global_mov_values)
    act_lines, dialog_source = split_npc_sections(source)
    if source_map:
        dialog_source, source_map = _drop_ignored_physical_lines_with_map(dialog_source, source_map)
    else:
        dialog_source = _drop_ignored_physical_lines(dialog_source)
    dialog_source = _normalize_backslash_remainders(dialog_source)
    normalized_dialog_source = _normalize_leading_say_backslashes(dialog_source)
    if normalized_dialog_source != dialog_source:
        source_map = None
    dialog_source = normalized_dialog_source
    merchant_bigdlg = parse_openmerchantbigdlg(act_lines)
    nodes: list[NpcNode] = []
    buf: list[str] = []
    buf_start: int | None = None
    buf_end = 0
    preserve_spaces = False
    pending_trailing_marker = False
    i = 0

    def source_ref(start: int, end: int) -> SourceRef:
        return _source_ref_for_range(
            dialog_source,
            start,
            end,
            source_key=source_key,
            source_offset=source_offset,
            source_line_offset=source_line_offset,
            source_map=source_map,
        )

    def append_text(value: str, start: int, end: int) -> None:
        nonlocal buf_start, buf_end
        if buf_start is None:
            buf_start = start
        buf_end = end
        buf.append(value)

    def flush_text() -> None:
        nonlocal buf_start, buf_end
        if not buf:
            return
        ref = source_ref(buf_start or 0, buf_end)
        nodes.append(NpcNode("text", replace_npc_variables("".join(buf)), source_ref=ref))
        buf.clear()
        buf_start = None
        buf_end = 0

    while i < len(dialog_source):
        ch = dialog_source[i]
        if ch == "{":
            end = dialog_source.find("}", i + 1)
            if end >= 0:
                node = parse_braced_tag(dialog_source[i + 1 : end])
                if node is not None:
                    flush_text()
                    node.source_ref = source_ref(i, end + 1)
                    nodes.append(node)
                    pending_trailing_marker = False
                    i = end + 1
                    continue
        if ch == "<":
            if dialog_source[i + 1 : i + 4].lower() == "img":
                stop, marker = _find_img_tag_end(dialog_source, i + 1)
                if marker:
                    flush_text()
                    node = parse_tag(dialog_source[i + 1 : stop])
                    node.source_ref = source_ref(i, stop + 1 if marker == ">" else stop)
                    nodes.append(node)
                    pending_trailing_marker = False
                    i = stop + 1 if marker == ">" else stop
                    continue
                flush_text()
                node = parse_tag(dialog_source[i + 1 :])
                node.source_ref = source_ref(i, len(dialog_source))
                nodes.append(node)
                pending_trailing_marker = False
                break
            end = _find_tag_end(dialog_source, i + 1)
            if end >= 0:
                flush_text()
                raw_tag = dialog_source[i + 1 : end]
                if raw_tag.lower().startswith("$str(") and raw_tag.endswith(")"):
                    node = NpcNode("text", f"<{raw_tag}>")
                else:
                    node = parse_tag(raw_tag)
                node.source_ref = source_ref(i, end + 1)
                if node.kind == "noop" and not raw_tag.strip():
                    nodes.append(NpcNode("text", raw_tag, source_ref=node.source_ref))
                    preserve_spaces = True
                else:
                    nodes.append(node)
                pending_trailing_marker = False
                i = end + 1
                continue
        marker = _backslash_marker(dialog_source, i)
        if marker is not None:
            count, next_index = marker
            flush_text()
            is_line_leading = _is_line_leading_marker(dialog_source, i)
            has_line_content_after = _marker_has_line_content_after(dialog_source, next_index)
            if pending_trailing_marker and is_line_leading and has_line_content_after:
                count -= 1
            elif count > 1 and is_line_leading and not has_line_content_after:
                count -= 1
            if count > 0:
                ref = source_ref(i, next_index)
                for _ in range(count):
                    nodes.append(NpcNode("newline", source_ref=ref))
            pending_trailing_marker = not has_line_content_after
            preserve_spaces = False
            i = next_index
            continue
        if ch in "\r\n":
            if ch == "\r" and i + 1 < len(dialog_source) and dialog_source[i + 1] == "\n":
                i += 1
            preserve_spaces = False
            i += 1
            continue
        gap = _tag_gap_space(dialog_source, i)
        if gap is not None:
            spaces, next_index = gap
            append_text(spaces, i, next_index)
            i = next_index
            continue
        mixed_gap = _mixed_layout_ascii_space(dialog_source, i)
        if mixed_gap is not None:
            spaces, next_index = mixed_gap
            append_text(spaces, i, next_index)
            i = next_index
            continue
        if ch in NPC_IGNORED_CONTROL_CHARS:
            i += 1
            continue
        if preserve_spaces or ch not in " \t":
            append_text(ch, i, i + 1)
            if ch not in NPC_LAYOUT_GAP_CHARS:
                pending_trailing_marker = False
        i += 1

    flush_text()
    return NpcDialog(
        source=source,
        nodes=merge_text_nodes(nodes) if merge_adjacent_text else filter_empty_text_nodes(nodes),
        merchant_bigdlg=merchant_bigdlg,
        label=label,
        line_start=line_start,
        line_end=line_end,
    )


def parse_npc_dialog(source: str, *, merge_adjacent_text: bool = True) -> NpcDialog:
    return _parse_npc_dialog_parts(
        source,
        line_end=len(source.splitlines()),
        global_mov_values=parse_mov_assignments(source),
        merge_adjacent_text=merge_adjacent_text,
    )


def inherit_first_merchant_bigdlg(pages: list[NpcDialog]) -> list[NpcDialog]:
    first = next((page.merchant_bigdlg for page in pages if page.merchant_bigdlg is not None), None)
    if first is None:
        return pages
    for page in pages:
        if page.merchant_bigdlg is None:
            page.merchant_bigdlg = first
    return pages


def _numbered_page_label(base_label: str, page_number: int) -> str:
    if page_number <= 1:
        return base_label
    return f"{base_label}{page_number}"


def _unique_page_label(base_label: str, used_labels: set[str]) -> str:
    if base_label not in used_labels:
        used_labels.add(base_label)
        return base_label
    match = re.match(r"^(?P<prefix>.*?)(?P<number>\d+)$", base_label)
    if match and match.group("prefix"):
        prefix = match.group("prefix")
        suffix = int(match.group("number")) + 1
    else:
        prefix = base_label
        suffix = 2
    while True:
        candidate = f"{prefix}{suffix}"
        if candidate not in used_labels:
            used_labels.add(candidate)
            return candidate
        suffix += 1


def _split_block_say_segments(lines: list[str], start_line: int) -> list[tuple[list[str], int, int]]:
    segments: list[tuple[list[str], int, int]] = []
    pending: list[str] = []
    pending_start = start_line
    current: list[str] = []
    current_start = start_line
    in_say_page = False
    saw_say = False
    divert_after_say = False

    def flush_current(end_line: int) -> None:
        nonlocal current, in_say_page, divert_after_say
        if current:
            segments.append((current, current_start, end_line))
        current = []
        in_say_page = False
        divert_after_say = False

    def current_has_trailing_backslash_marker() -> bool:
        for current_line in reversed(current):
            if _is_ignored_physical_line(current_line) or _is_section_marker(current_line):
                continue
            return _line_ends_with_backslash_marker(current_line)
        return False

    def pending_has_effective_content() -> bool:
        for pending_line in pending:
            if _is_ignored_physical_line(pending_line) or _is_section_marker(pending_line):
                continue
            return True
        return False

    def remove_current_trailing_physical_gap() -> None:
        while current and _is_ignored_physical_line(current[-1]):
            current.pop()
        if current:
            current[-1] = _strip_physical_newline(current[-1])

    for relative_index, line in enumerate(lines):
        absolute_index = start_line + relative_index
        raw_lower = line.strip().lower()
        lower = _section_keyword(line)
        if lower == "#say":
            divert_after_say = False
            if in_say_page:
                if raw_lower == "#elsesay":
                    flush_current(absolute_index)
                    current_start = absolute_index
                    current = [line]
                    in_say_page = True
                elif pending_has_effective_content() or current_has_trailing_backslash_marker():
                    flush_current(absolute_index)
                    current_start = pending_start if pending else absolute_index
                    current = pending + [line]
                    in_say_page = True
                else:
                    remove_current_trailing_physical_gap()
                pending = []
                pending_start = absolute_index + 1
                in_say_page = True
                saw_say = True
            else:
                current_start = pending_start if pending else absolute_index
                current = pending + [line]
                pending = []
                pending_start = absolute_index + 1
                in_say_page = True
                saw_say = True
            continue
        if in_say_page and lower in frozenset({"#if", "#act"}):
            if not pending:
                pending_start = absolute_index
            pending.append(line)
            divert_after_say = True
            continue
        if in_say_page:
            if divert_after_say:
                pending.append(line)
            else:
                current.append(line)
        else:
            if not pending:
                pending_start = absolute_index
            pending.append(line)
    if in_say_page:
        flush_current(start_line + len(lines))
    elif not saw_say and lines:
        segments.append((lines, start_line, start_line + len(lines)))
    return segments


def parse_npc_dialog_pages(source: str, *, merge_adjacent_text: bool = True) -> list[NpcDialog]:
    pages: list[NpcDialog] = []
    used_labels: set[str] = set()
    global_mov_values = parse_mov_assignments(source)
    current_label = "主对话"
    last_label = current_label
    current_lines: list[str] = []
    current_start = 0
    saw_label = False

    def flush() -> None:
        nonlocal current_lines
        if not current_lines:
            return
        page_number = 1
        block_source = "".join(current_lines)
        block_mov_values = parse_mov_assignments(block_source)
        for segment_lines, segment_start, segment_end in _split_block_say_segments(current_lines, current_start):
            page_source = "".join(segment_lines)
            label = _unique_page_label(_numbered_page_label(current_label, page_number), used_labels)
            dialog = _parse_npc_dialog_parts(
                page_source,
                label,
                segment_start,
                segment_end,
                local_mov_values=block_mov_values,
                global_mov_values=global_mov_values,
                merge_adjacent_text=merge_adjacent_text,
            )
            if dialog.nodes or dialog.merchant_bigdlg is not None:
                pages.append(dialog)
            page_number += 1
        current_lines = []

    for line_index, line in enumerate(source.splitlines(keepends=True)):
        match = SCRIPT_LABEL_RE.match(line.strip())
        if match:
            flush()
            current_label = f'@{match.group("label").strip()}'
            last_label = current_label
            current_start = line_index + 1
            saw_label = True
        else:
            if not current_lines:
                current_start = line_index
            current_lines.append(line)
    flush()
    if pages:
        return inherit_first_merchant_bigdlg(pages)
    if saw_label:
        return [NpcDialog(source="", nodes=[], label=last_label)]
    return [
        _parse_npc_dialog_parts(
            source,
            line_end=len(source.splitlines()),
            global_mov_values=parse_mov_assignments(source),
            merge_adjacent_text=merge_adjacent_text,
        )
    ]


def merge_text_nodes(nodes: Iterable[NpcNode]) -> list[NpcNode]:
    merged: list[NpcNode] = []
    for node in nodes:
        if node.kind == "text" and not node.text:
            continue
        if node.kind == "text" and merged and merged[-1].kind == "text" and merged[-1].attrs == node.attrs:
            merged[-1].text += node.text
            left = merged[-1].source_ref
            right = node.source_ref
            if left is not None and right is not None and left.key == right.key and left.end == right.start:
                merged[-1].source_ref = SourceRef(
                    left.key,
                    left.start,
                    right.end,
                    left.line,
                    left.column,
                    left.raw + right.raw,
                    left.exact and right.exact,
                )
            else:
                merged[-1].source_ref = None
        else:
            merged.append(node)
    return merged


def filter_empty_text_nodes(nodes: Iterable[NpcNode]) -> list[NpcNode]:
    return [node for node in nodes if node.kind != "text" or node.text]


def dialog_to_plain_lines(dialog: NpcDialog) -> list[str]:
    lines = [""]
    for node in dialog.nodes:
        if node.kind == "newline":
            lines.append("")
        elif node.kind in {"input_box", "image_button", "positioned_text", "image", "progress_bar", "item_box", "item_show"}:
            lines[-1] += f'[IMG {node.attrs.get("index", node.attrs.get("raw", ""))}]'
        else:
            lines[-1] += node.text
    return lines
