"""Parser for Lingfeng/GOM NPC visual-layout scripts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .ast import NpcComponentNode, NpcDocument, NpcLabelBlock, NpcSayBlock, SourceRef

_LABEL_RE = re.compile(r"^\s*\[@([^\]]+)\]\s*$", re.IGNORECASE)
_DIRECTIVE_RE = re.compile(r"^\s*#([A-Z0-9_()]+)\b", re.IGNORECASE)
_OPENMERCHANT_RE = re.compile(
    r"^\s*(?:OPENMERCHANTBIGDLG|OPENBIGDIALOGBOX)\s+(.+)$", re.IGNORECASE
)
_MOV_ASSIGN_RE = re.compile(r"^\s*mov\s+(?P<name>\S+)(?:\s+(?P<value>.*?))?\s*$", re.IGNORECASE)
_STR_VARIABLE_RE = re.compile(r"<\$\s*STR\((?P<name>[^)]+)\)>", re.IGNORECASE)
_FULL_STR_VARIABLE_RE = re.compile(r"^\$\s*STR\((?P<name>[^)]+)\)$", re.IGNORECASE)
_STR_STRING_VARIABLE_RE = re.compile(r"^S\$[^)\s]+$", re.IGNORECASE)
_STR_NUMBER_VARIABLE_RE = re.compile(r"^N\$[^)\s]+$", re.IGNORECASE)
_STR_ALPHA_NUMERIC_VARIABLE_RE = re.compile(r"^[A-Za-z]+\d+$")
_BRACED_STYLE_RE = re.compile(
    r"^(?P<text>.*?)/(?P<key>FCOLOR|SCOLOR|AUTOCOLOR)\s*=\s*(?P<value>[^{}]+)$",
    re.IGNORECASE,
)
_INLINE_COLOR_RE = re.compile(
    r"\{(?P<key>AUTOCOLOR|FCOLOR|SCOLOR)\s*=\s*(?P<value>[^;{}]+)(?:;[^{}]*)?\}",
    re.IGNORECASE,
)
_PREVIEW_BUILTIN_VARIABLES = {
    "USERNAME": "畅玩可视化",
    "RELEVEL": "0",
}
_UNDEFINED_STR_TAG = "__NPCV2_UNDEFINED_STR__"
_COMMENT_LSTRIP_CHARS = " \t\u3000"
_LAYOUT_GAP_CHARS = " \t\u3000\ue779"
_CONTAINER_ID_PREFIX = "#"


@dataclass(frozen=True)
class _Line:
    text: str
    start: int
    number: int


class NpcScriptParserV2:

    def __init__(self) -> "None":
        self._mov_values = {}
        self._mov_trailing_breaks = {}

    def parse(self, source_text: "str", file_key: "str"='__main__') -> "NpcDocument":
        previous_mov_values = self._mov_values
        previous_mov_trailing_breaks = self._mov_trailing_breaks
        self._mov_trailing_breaks = {}
        self._mov_values = self._parse_mov_assignments(source_text)
        try:
            return self._parse_with_variables(source_text, file_key=file_key)
        finally:
            self._mov_values = previous_mov_values
            self._mov_trailing_breaks = previous_mov_trailing_breaks

    def _parse_with_variables(self, source_text: "str", file_key: "str"='__main__') -> "NpcDocument":
        lines = self._split_lines(source_text)
        document = NpcDocument(file_key=file_key, source_text=source_text)
        current = None
        mode = ""
        say_lines = []
        say_start = None
        say_index = 0
    
        def flush_say() -> None:
            nonlocal current, say_lines, say_start, say_index
            if current is None or not say_lines:
                say_lines = []
                say_start = None
                return None
            raw = "".join(line.text for line in say_lines)
            if not raw.strip():
                say_lines = []
                say_start = None
                return None
            say_index += 1
            first = say_lines[0]
            last = say_lines[-1]
            end = last.start + len(last.text)
            ref = self._ref(file_key, source_text, say_start if say_start is not None else first.start, end)
            nodes = self._parse_say_nodes(raw, file_key, source_text, first.start)
            current.say_blocks.append(NpcSayBlock(id=f"say:{current.label}:{say_index}:{first.start}",
              label=(current.label),
              source=ref,
              nodes=nodes))
            say_lines = []
            say_start = None
            return None
    
        for line in lines:
            label_match = _LABEL_RE.match(line.text.rstrip("\r\n"))
            if label_match:
                flush_say()
                label = "@" + label_match.group(1).strip()
                current = NpcLabelBlock(label=label,
                  source=(self._ref(file_key, source_text, line.start, line.start + len(line.text))))
                document.labels.append(current)
                mode = ""
                say_index = 0
                continue
    
            if current is None:
                continue
    
            directive = _DIRECTIVE_RE.match(line.text)
            if directive:
                keyword = directive.group(1).upper()
                if keyword in {'SAY', 'ELSESAY'}:
                    flush_say()
                    mode = "say"
                    say_start = None
                    continue
                if keyword in {'IF', 'OR', 'ELSEACT', 'ACT', 'ELSE'} or keyword.startswith("IF("):
                    flush_say()
                    mode = "act" if "ACT" in keyword else ""
                    current.act_lines.append(line.text)
                    continue
                flush_say()
                current.act_lines.append(line.text)
                mode = ""
                continue
    
            if mode == "say":
                if self._is_comment_line(line.text):
                    if say_start is not None:
                        say_lines.append(_Line(text=(self._offset_padding_line(line.text)),
                          start=(line.start),
                          number=(line.number)))
                    continue
                if say_start is None:
                    say_start = line.start
                say_lines.append(line)
                continue
    
            open_match = _OPENMERCHANT_RE.match(line.text.strip())
            if open_match:
                current.openmerchant = self._parse_openmerchant(
                    line.text.strip(),
                    file_key,
                    source_text,
                    line.start + line.text.find(line.text.strip()),
                )
            current.act_lines.append(line.text)
    
        flush_say()
        self._ensure_legacy_say(document, lines, file_key, source_text)
        return document


    def _ensure_legacy_say(self, document, lines, file_key, source_text) -> None:
        label_starts = {block.source.start: block for block in document.labels}
        if not document.labels:
            return
        for (index, block) in enumerate(document.labels):
            if block.say_blocks:
                continue

            start = block.source.end
            end = document.labels[index + 1].source.start if index + 1 < len(document.labels) else len(source_text)
            raw = source_text[start:end]
            if any((line.lstrip(_COMMENT_LSTRIP_CHARS).startswith("#") for line in raw.splitlines())):
                continue

            parsed_lines = []
            cursor = start
            for text in raw.splitlines(True):
                stripped = text.strip()
                visible = False
                if self._is_comment_line(text):
                    visible = False
                elif stripped and not stripped.startswith("#"):
                    if not stripped.startswith("%"):
                        if not stripped.startswith("+"):
                            visible = not _OPENMERCHANT_RE.match(stripped)
                parsed_lines.append((cursor, text, visible))
                cursor += len(text)

            visible_indexes = [index for index, (_pos, _text, visible) in enumerate(parsed_lines) if visible]
            if not visible_indexes:
                continue

            first_index = visible_indexes[0]
            last_index = visible_indexes[-1]
            visible_lines = [
                (pos, text)
                for pos, text, visible in parsed_lines[first_index:last_index + 1]
                if visible
            ]
            if not visible_lines:
                continue

            raw_visible = "".join(
                text if visible else self._offset_padding_line(text)
                for _pos, text, visible in parsed_lines[first_index:last_index + 1]
            )
            first_start = visible_lines[0][0]
            (last_start, last_text) = visible_lines[-1]
            ref = self._ref(file_key, source_text, first_start, last_start + len(last_text))
            block.say_blocks.append(NpcSayBlock(id=f"say:{block.label}:legacy:{first_start}",
              label=(block.label),
              source=ref,
              nodes=(self._parse_say_nodes(raw_visible, file_key, source_text, first_start))))

    def _offset_padding_line(self, text: "str") -> "str":
        return "".join((ch if ch in "\r\n" else " " for ch in text))

    def _is_comment_line(self, text: "str") -> "bool":
        return text.lstrip(_COMMENT_LSTRIP_CHARS).startswith(";")

    def _line_end(self, source: "str", index: "int") -> "int":
        line_end = source.find("\n", index)
        if line_end < 0:
            return len(source)
        return line_end

    def _is_line_leading_marker(self, source: "str", index: "int") -> "bool":
        line_start = source.rfind("\n", 0, index) + 1
        return all((ch in _LAYOUT_GAP_CHARS or ch == "\r" for ch in source[line_start:index]))

    def _marker_has_line_content_after(self, source: "str", marker_end: "int") -> "bool":
        line_end = self._line_end(source, marker_end)
        return bool(source[marker_end:line_end].strip(_LAYOUT_GAP_CHARS + "\r"))

    def _parse_say_nodes(self, raw, file_key, source_text, base_offset) -> list[NpcComponentNode]:
        nodes = []
        index = 0
        text_start = None
        pending_trailing_marker = False
    
        def flush_text(until: int) -> None:
            nonlocal text_start, pending_trailing_marker
            if text_start is None or until <= text_start:
                text_start = None
                return None
            text = raw[text_start:until]
            if text:
                absolute = base_offset + text_start
                nodes.append(NpcComponentNode(id=(self._node_id(file_key, absolute, "text")),
                  kind="text",
                  text=(self._replace_variables(text)),
                  raw=text,
                  source=(self._ref(file_key, source_text, absolute, absolute + len(text)))))
                if text.strip(_LAYOUT_GAP_CHARS + "\r\n"):
                    pending_trailing_marker = False
            text_start = None
            return None
    
        while index < len(raw):
            ch = raw[index]
            if ch == "<":
                end = self._find_tag_end(raw, index + 1)
                if end > index:
                    flush_text(index)
                    tag_raw = raw[index:end + 1]
                    absolute = base_offset + index
                    nodes.extend(self._parse_tag_nodes(tag_raw, file_key, source_text, absolute))
                    pending_trailing_marker = False
                    index = end + 1
                    continue
    
            if ch == "{":
                end = self._find_braced_style_end(raw, index + 1)
                if end > index:
                    flush_text(index)
                    braced_raw = raw[index:end + 1]
                    absolute = base_offset + index
                    nodes.append(self._parse_braced_style(braced_raw, file_key, source_text, absolute))
                    pending_trailing_marker = False
                    index = end + 1
                    continue
    
            if ch == "\\":
                flush_text(index)
                group_start = index
                count = 0
                while index < len(raw):
                    while index < len(raw) and raw[index] in _LAYOUT_GAP_CHARS:
                        index += 1
                    if index >= len(raw) or raw[index] != "\\":
                        break
                    while index < len(raw) and raw[index] == "\\":
                        index += 1
                    count += 1
    
                is_line_leading = self._is_line_leading_marker(raw, group_start)
                has_line_content_after = self._marker_has_line_content_after(raw, index)
                if pending_trailing_marker and is_line_leading and has_line_content_after:
                    count -= 1
                elif count > 1 and is_line_leading and not has_line_content_after:
                    count -= 1
                absolute = base_offset + group_start
                marker = raw[group_start:index]
                if count > 0:
                    nodes.append(NpcComponentNode(id=(self._node_id(file_key, absolute, "break")),
                      kind="break",
                      text="",
                      raw=marker,
                      source=(self._ref(file_key, source_text, absolute, absolute + len(marker))),
                      props={"count": count}))
                pending_trailing_marker = not has_line_content_after
                continue
    
            if ch in "\r\n":
                if self._is_whitespace_only_line_segment(raw, text_start, index):
                    text_start = None
                else:
                    flush_text(index)
                if ch == "\r" and index + 1 < len(raw) and raw[index + 1] == "\n":
                    index += 2
                    continue
                index += 1
                continue
    
            if text_start is None:
                text_start = index
            index += 1
    
        flush_text(len(raw))
        self._mark_decorative_link_quotes(nodes)
        return nodes


    def _mark_decorative_link_quotes(self, nodes: "list[NpcComponentNode]") -> "None":
        for (index, node) in enumerate(nodes):
            if node.kind != "text":
                continue
            stripped = str(node.text or node.raw or "").strip(_LAYOUT_GAP_CHARS + "\r\n")
            if (
                stripped == "《"
                and index + 1 < len(nodes)
                and nodes[index + 1].kind == "link"
            ):
                node.props["decorative_text"] = True
            elif (
                stripped == "》"
                and index > 0
                and nodes[index - 1].kind == "link"
            ):
                node.props["decorative_text"] = True

    def _is_whitespace_only_line_segment(self, raw, start, end) -> bool:
        if start is None or end <= start:
            return False
        text = raw[start:end]
        return not text.strip(_LAYOUT_GAP_CHARS + "\r") and self._is_line_leading_marker(raw, start)

    def _find_braced_style_end(self, raw: "str", start: "int") -> "int":
        index = start
        while index < len(raw):
            ch = raw[index]
            if ch in "\r\n":
                return -1
            else:
                if ch == "}":
                    inner = raw[start:index]
                    if _BRACED_STYLE_RE.match(inner.strip()):
                        return index
                    return -1
                index += 1

        return -1

    def _parse_braced_style(self, raw, file_key, source_text, absolute) -> NpcComponentNode:
        inner = raw[1:-1].strip()
        match = _BRACED_STYLE_RE.match(inner)
        props = {}
        text = inner
        if match:
            text = match.group("text")
            color_key = match.group("key").upper()
            color_value = self._replace_variables(match.group("value").strip())
            props[color_key] = color_value
            props["color"] = color_value
        return NpcComponentNode(id=(self._node_id(file_key, absolute, "braced-text")),
          kind="text",
          text=(self._replace_variables(text)),
          raw=raw,
          source=(self._ref(file_key, source_text, absolute, absolute + len(raw))),
          props=props)

    def _parse_tag_nodes(self, raw, file_key, source_text, absolute) -> list[NpcComponentNode]:
        body = raw[1:-1].strip()
        str_match = _FULL_STR_VARIABLE_RE.fullmatch(body)
        if str_match:
            name = str_match.group("name").strip()
            if self._lookup_mov_value(name) is None and _STR_STRING_VARIABLE_RE.fullmatch(name):
                return [self._undefined_str_placeholder(raw, file_key, source_text, absolute, name)]

            expanded = self._resolve_str_value(name)
            expanded_breaks = self._lookup_mov_break_count(name)
            expanded = expanded.strip()
            if expanded.casefold() == raw.strip().casefold():
                return []
            nodes = self._parse_say_nodes(expanded, file_key, expanded, 0) if expanded else []
            if not nodes:
                if not expanded:
                    if expanded_breaks:
                        return [
                         NpcComponentNode(id=(self._node_id(file_key, absolute, "break")),
                           kind="break",
                           text="",
                           raw=raw,
                           source=(self._ref(file_key, source_text, absolute, absolute + len(raw))),
                           props={"count": expanded_breaks})]
                    return []
                nodes = [
                 NpcComponentNode(id=(self._node_id(file_key, absolute, "text")),
                   kind="text",
                   text=expanded,
                   raw=raw,
                   source=(self._ref(file_key, source_text, absolute, absolute + len(raw))))]

            source_ref = self._ref(file_key, source_text, absolute, absolute + len(raw))
            multi_component = sum(1 for node in nodes if node.kind != "break") > 1
            for (index, node) in enumerate(nodes):
                node.id = self._node_id(file_key, absolute + index, f"str{index}:{node.kind}")
                node.source = source_ref
                node.props["expanded_raw"] = node.raw
                node.props["str_expanded"] = True
                node.props["str_parent_raw"] = raw
                if multi_component:
                    node.props["str_multi_expanded"] = True

            if expanded_breaks:
                for node in reversed(nodes):
                    if node.kind != "break":
                        node.props["str_trailing_break_count"] = expanded_breaks
                        break
            return nodes
        return [self._parse_tag(raw, file_key, source_text, absolute)]


    def _parse_tag(self, raw, file_key, source_text, absolute) -> NpcComponentNode:
        raw_body = raw[1:-1]
        body = raw_body.strip()
        display_body = raw_body
        kind = "tag"
        text = body
        props = {}
        lower = body.lower()
        if lower.startswith("&"):
            props["absolute"] = True
            body = body[1:].strip()
            display_body = raw_body[raw_body.find("&") + 1:]
            lower = body.lower()
        if lower.startswith(_UNDEFINED_STR_TAG.lower() + ":"):
            kind = "text"
            text = _PREVIEW_BUILTIN_VARIABLES["USERNAME"]
            props["hidden_placeholder"] = True
        elif lower.startswith("imgex:"):
            kind = "imgex"
            props.update(self._parse_colon_args(body, "ImgEx"))
            text = "ImgEx"
        elif lower.startswith("img:"):
            kind = "img"
            props.update(self._parse_colon_args(body, "Img"))
            text = "Img"
        elif lower.startswith("playimgex:"):
            kind = "playimgex"
            props.update(self._parse_colon_args(body, "PlayImgEx"))
            text = "PlayImgEx"
        elif lower.startswith("playimg:"):
            kind = "playimg"
            props.update(self._parse_colon_args(body, "PlayImg"))
            text = "PlayImg"
        elif lower.startswith("monster:"):
            kind = "monster"
            props.update(self._parse_colon_args(body, "Monster"))
            props["absolute"] = True
            text = "Monster"
        elif lower.startswith("itemshow:"):
            kind = "itemshow"
            props.update(self._parse_colon_args(body, "ItemShow"))
            text = "ItemShow"
        elif lower.startswith("itembox:"):
            kind = "itembox"
            props.update(self._parse_colon_args(body, "ITEMBOX"))
            text = "ITEMBOX"
        elif lower.startswith("progressbar:"):
            kind = "progressbar"
            props.update(self._parse_colon_args(body, "ProgressBar"))
            text = "ProgressBar"
        elif lower.startswith("listview:"):
            kind = "listview"
            props.update(self._parse_colon_args(body, "ListView"))
            text = "ListView"
        elif lower.startswith("layout:"):
            kind = "layout"
            props.update(self._parse_colon_args(body, "Layout"))
            text = "Layout"
        elif lower.startswith("newline:"):
            kind = "container_newline"
            props.update(self._parse_colon_args(body, "NewLine"))
            text = "NewLine"
        elif lower.startswith("mtext:"):
            kind = "mtext"
            text, mtext_props = self._parse_mtext_args(body)
            props.update(mtext_props)
        elif lower.startswith("text:"):
            kind = "positioned_text"
            props.update(self._parse_colon_args(body, "Text"))
            text = props.get("display", "Text")
        elif "/@" in body or "@@" in body:
            kind = "link"
            text = self._display_text_from_body(display_body)
            props["label"] = self._label_from_body(body)
            props["tip"] = self._tip_from_body(display_body)
            props.update(self._inline_style_props(display_body))
        else:
            kind = "text"
            text = self._display_text_from_body(display_body)
            props["color"] = self._color_from_body(body)
            props["tip"] = self._tip_from_body(display_body)
            props.update(self._inline_style_props(display_body))
        return NpcComponentNode(id=(self._node_id(file_key, absolute, kind)),
          kind=kind,
          text=(str(text)),
          raw=raw,
          source=(self._ref(file_key, source_text, absolute, absolute + len(raw))),
          props=props)

    def _parse_mtext_args(self, body: "str") -> "tuple[str, dict[str, object]]":
        payload = body[len("MText") + 1:]
        container_props, payload = self._extract_container_ref(payload)
        parts = payload.split(":", 3)
        while len(parts) < 4:
            parts.append("")
        x_arg, y_arg, color_arg, text = parts
        args = [
            self._replace_variables(x_arg),
            self._replace_variables(y_arg),
            self._replace_variables(color_arg),
            self._replace_variables(text),
        ]
        props: dict[str, object] = {
            "args": args,
            "FCOLOR": args[2],
            "color": args[2],
        }
        props.update(container_props)
        return args[3], props

    def _undefined_str_placeholder(self, raw, file_key, source_text, absolute, name) -> NpcComponentNode:
        return NpcComponentNode(id=(self._node_id(file_key, absolute, "hidden-str")),
          kind="text",
          text=_PREVIEW_BUILTIN_VARIABLES["USERNAME"],
          raw=raw,
          source=(self._ref(file_key, source_text, absolute, absolute + len(raw))),
          props={'hidden_placeholder':True, 
         'undefined_str':name})

    def _parse_openmerchant(self, raw, file_key, source_text, absolute) -> NpcComponentNode:
        raw_parts = raw.split()
        parts = [raw_parts[0]] + [
            self._replace_variables(part) for part in raw_parts[1:]
        ]
        props = {'command':parts[0],  'args':parts[1:]}
        if len(parts) > 2:
            props["file"] = parts[1]
            props["index"] = parts[2]
        return NpcComponentNode(id=(self._node_id(file_key, absolute, "background")),
          kind="background",
          text="背景图",
          raw=raw,
          source=(self._ref(file_key, source_text, absolute, absolute + len(raw))),
          props=props)

    def _parse_colon_args(self, body: "str", command: "str") -> "dict[str, object]":
        payload = body[len(command) + 1:]
        label = ""
        if "/@" in payload:
            (payload, label_tail) = payload.split("/@", 1)
            label = "@" + label_tail.strip()
        if command.lower() == "text":
            props = self._parse_text_args(payload)
            if label:
                props["label"] = label
            return props
        tip = ""
        if "|" in payload:
            (payload, tip) = payload.split("|", 1)
        (container_props, payload) = self._extract_container_ref(payload)
        args = [self._replace_variables(part) for part in payload.split(":")] if payload else []
        props = {"args": args}
        props.update(container_props)
        if label:
            props["label"] = label
        if tip:
            props["tip"] = self._replace_variables(tip)
        return props

    def _parse_text_args(self, payload: "str") -> "dict[str, object]":
        (container_props, payload) = self._extract_container_ref(payload)
        style = ""
        style_props = {}
        style_match = re.search("\\{[^{}]*\\}\\s*$", payload)
        if style_match:
            style = style_match.group(0)
            style_props = self._style_props(style[1:-1])
            payload = payload[:style_match.start()].rstrip()
        parts = payload.rsplit(":", 2)
        if len(parts) == 3:
            (text_and_tip, x_arg, y_arg) = parts
            y_arg = y_arg + style
        else:
            text_and_tip = payload
            x_arg = "0"
            y_arg = "0" + style
        tip = ""
        display = text_and_tip
        if "|" in display:
            (display, tip) = display.split("|", 1)
        elif ":" in display:
            (display, tip) = display.split(":", 1)
        args = [self._replace_variables(display),
         self._replace_variables(x_arg),
         self._replace_variables(y_arg)]
        props = {'args':args, 
         'display':args[0]}
        props.update(container_props)
        props.update(style_props)
        if tip:
            props["tip"] = self._replace_variables(tip)
        return props

    def _extract_container_ref(self, payload: "str") -> "tuple[dict[str, object], str]":
        value = payload.strip()
        if value.startswith(":"):
            value = value[1:]
        if ":" in value:
            (first, rest) = value.split(":", 1)
        else:
            first, rest = value, ""
        if "~" not in first:
            return ({}, payload)
        (parent_id, child_id) = first.split("~", 1)
        props = {'container_ref':(first.strip)(), 
         'parent_id':(self._normalize_container_id)(parent_id), 
         'child_id':(self._normalize_container_id)(child_id)}
        return (
         props, rest)

    def _normalize_container_id(self, value: "str") -> "str":
        text = value.strip()
        if not text:
            return ""
        if text.startswith(_CONTAINER_ID_PREFIX):
            return text
        return _CONTAINER_ID_PREFIX + text

    def _display_text_from_body(self, body: "str") -> "str":
        content = body
        if "/@" in content:
            content = content.split("/@", 1)[0]
        if "@@" in content:
            content = content.split("@@", 1)[0]
        if "|" in content:
            content = content.split("|", 1)[0]
        if "/" in content:
            content = content.rsplit("/", 1)[0]
        content = _INLINE_COLOR_RE.sub("", content)
        return self._replace_variables(content)

    def _label_from_body(self, body: "str") -> "str":
        if "/@" in body:
            return "@" + body.split("/@", 1)[1].strip()
        if "@@" in body:
            return "@@" + body.split("@@", 1)[1].strip()
        return ""

    def _tip_from_body(self, body: "str") -> "str":
        if "|" not in body:
            return ""
        tip = body.split("|", 1)[1]
        if "/@" in tip:
            tip = tip.split("/@", 1)[0]
        return self._replace_variables(tip)

    def _parse_mov_assignments(self, source: "str") -> "dict[str, str]":
        selected = {}
        current_if_lines = []
        conditional_mode = False
        collecting_condition = False
        condition_operator = "and"
        condition_result = True
        branch_priority = 30
        for line in source.splitlines():
            if _LABEL_RE.match(line.strip()):
                current_if_lines = []
                conditional_mode = False
                collecting_condition = False
                condition_operator = "and"
                condition_result = True
                branch_priority = 30
                continue
    
            directive = _DIRECTIVE_RE.match(line)
            if directive:
                keyword = directive.group(1).upper()
                if keyword == "IF" or keyword.startswith("IF(") or keyword == "OR":
                    current_if_lines = []
                    conditional_mode = True
                    collecting_condition = True
                    condition_operator = "or" if keyword == "OR" else "and"
                    condition_result = True
                    branch_priority = 10
                    inline = self._inline_condition_from_directive(line, keyword)
                    if inline:
                        current_if_lines.append(inline)
                    continue
                if keyword == "ACT":
                    condition_result = self._evaluate_preview_condition(current_if_lines, operator=condition_operator) if conditional_mode else True
                    collecting_condition = False
                    branch_priority = 40 if condition_result else 10
                    continue
                if keyword == "ELSEACT":
                    condition_result = self._evaluate_preview_condition(current_if_lines, operator=condition_operator) if conditional_mode else False
                    collecting_condition = False
                    branch_priority = 40 if not condition_result else 10
                    continue
                if keyword in {'SAY', 'ELSESAY'}:
                    collecting_condition = False
                    branch_priority = 0
                    continue
            elif conditional_mode and collecting_condition:
                stripped = line.strip()
                if stripped and not self._is_comment_line(line):
                    current_if_lines.append(stripped)
    
            match = _MOV_ASSIGN_RE.match(line)
            if not match:
                continue
            name = match.group("name").strip()
            value, trailing_breaks = self._split_mov_value((match.group("value") or "").strip())
            previous = selected.get(name)
            if previous is None or branch_priority > previous[0] or (branch_priority == previous[0] and not previous[1] and value):
                selected[name] = (branch_priority, value, trailing_breaks)
    
        self._mov_trailing_breaks = {name: breaks for name, (_priority, _value, breaks) in selected.items()}
        return {name: value for name, (_priority, value, _breaks) in selected.items()}


    def _inline_condition_from_directive(self, line: "str", keyword: "str") -> "str":
        stripped = line.strip()
        if keyword.startswith("IF("):
            return keyword
        parts = stripped.split(maxsplit=1)
        if len(parts) > 1:
            return parts[1].strip()
        return ""

    def _evaluate_preview_condition(self, lines: "list[str]", *, operator: "str"="and") -> "bool":
        meaningful = [line.strip() for line in lines if line.strip()]
        if not meaningful:
            return True
        values = [self._evaluate_preview_condition_line(line) for line in meaningful]
        if operator == "or":
            return any(values)
        return all(values)

    def _evaluate_preview_condition_line(self, line: "str") -> "bool":
        text = line.strip()
        if not text:
            return True
        upper = text.upper()
        if upper.startswith("IF(") and upper.endswith(")"):
            inner = upper[3:-1].strip()
            if inner in {'1', 'TRUE'}:
                return True
            if inner in {'FALSE', '0'}:
                return False
        negated = False
        while upper.startswith("NOT "):
            negated = not negated
            text = text[4:].strip()
            upper = text.upper()

        if upper in {'1', 'TRUE'}:
            result = True
        elif upper in {'FALSE', '0'}:
            result = False
        elif re.match("^CHECK\\s+\\[[^\\]]+\\]\\s+0\\b", upper):
            result = True
        elif re.match("^CHECK\\s+\\[[^\\]]+\\]\\s+1\\b", upper):
            result = False
        elif upper.startswith("EQUAL "):
            result = self._evaluate_preview_equal(text)
        else:
            result = False
        if negated:
            return not result
        return result

    def _evaluate_preview_equal(self, line: "str") -> "bool":
        parts = line.split(maxsplit=2)
        if len(parts) < 2:
            return False
        left = self._preview_condition_token(parts[1])
        right = self._preview_condition_token(parts[2]) if len(parts) >= 3 else ""
        return left == right

    def _preview_condition_token(self, token: "str") -> "str":
        token = token.strip()
        if re.fullmatch("T\\d+", token, re.IGNORECASE):
            return ""
        if re.fullmatch("[A-Z]\\d+", token, re.IGNORECASE):
            return "0"
        return self._replace_variables(token)

    def _split_mov_value(self, value: "str") -> "tuple[str, int]":
        if not value:
            return (value, 0)
        index = len(value) - 1
        while index >= 0 and (value[index] == "\\" or value[index] in _LAYOUT_GAP_CHARS):
            index -= 1
        suffix = value[index + 1:]
        if "\\" not in suffix:
            return (value, 0)
        return (value[:index + 1].rstrip(_LAYOUT_GAP_CHARS), self._count_marker_groups(suffix))


    def _count_marker_groups(self, marker: "str") -> "int":
        count = 0
        index = 0
        while index < len(marker):
            while index < len(marker) and marker[index] in _LAYOUT_GAP_CHARS:
                index += 1
            if index >= len(marker) or marker[index] != "\\":
                break
            while index < len(marker) and marker[index] == "\\":
                index += 1
            count += 1
        return count


    def _lookup_mov_value(self, name: "str") -> "str | None":
        if name in self._mov_values:
            return self._mov_values[name]
        folded = name.casefold()
        for (key, value) in self._mov_values.items():
            if key.casefold() == folded:
                return value

    def _lookup_mov_break_count(self, name: "str") -> "int":
        if name in self._mov_trailing_breaks:
            return self._mov_trailing_breaks[name]
        folded = name.casefold()
        for (key, value) in self._mov_trailing_breaks.items():
            if key.casefold() == folded:
                return value
        return 0


    def _resolve_str_value(self, name: "str") -> "str":
        name = name.strip()
        value = self._lookup_mov_value(name)
        if value is not None:
            if not str(value).strip() and _STR_NUMBER_VARIABLE_RE.fullmatch(name):
                return "0"
            return value
        if _STR_STRING_VARIABLE_RE.fullmatch(name):
            return ""
        if _STR_NUMBER_VARIABLE_RE.fullmatch(name):
            return "0"
        if _STR_ALPHA_NUMERIC_VARIABLE_RE.fullmatch(name):
            return "0"
        return f"<$STR({name})>"

    def _resolve_full_str_body(self, body: "str") -> "str":
        match = _FULL_STR_VARIABLE_RE.fullmatch(body.strip())
        if match:
            return self._resolve_str_value(match.group("name"))
        return ""

    def _resolve_full_str_break_count(self, body: "str") -> "int":
        match = _FULL_STR_VARIABLE_RE.fullmatch(body.strip())
        if match:
            return self._lookup_mov_break_count(match.group("name").strip())
        return 0

    def _replace_variables(self, text: "str") -> "str":
        result = text
        def replace_str(match: re.Match[str]) -> str:
            return self._resolve_str_value(match.group("name"))

        for _ in range(8):
            updated = _STR_VARIABLE_RE.sub(replace_str, result)
            if updated == result:
                break
            result = updated

        now = datetime.now()
        builtin_variables = {
            **_PREVIEW_BUILTIN_VARIABLES,
            "YEAR": str(now.year),
            "MONTH": str(now.month),
            "DAY": str(now.day),
        }
        for name, value in builtin_variables.items():
            escaped_name = re.escape(name)
            result = re.sub(f"<\\$\\s*{escaped_name}\\s*>", value, result, flags=(re.IGNORECASE))
            result = re.sub(f"\\${escaped_name}(?![A-Za-z0-9_])", value, result, flags=(re.IGNORECASE))

        return result

    def _color_from_body(self, body: "str") -> "str":
        match = re.search("/(?:F|S|AUTO)COLOR\\s*=\\s*([^/}]+)", body, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def _style_props(self, text: "str") -> "dict[str, object]":
        match = re.search("\\b(?P<key>FCOLOR|SCOLOR|AUTOCOLOR)\\s*=\\s*(?P<value>[^;{}]+)", text, re.IGNORECASE)
        if not match:
            return {}
        key = match.group("key").upper()
        value = self._replace_variables(match.group("value").strip())
        return {key: value, "color": value}

    def _inline_style_props(self, text: "str") -> "dict[str, object]":
        match = _INLINE_COLOR_RE.search(text)
        if not match:
            return {}
        key = match.group("key").upper()
        value = self._replace_variables(match.group("value").strip())
        return {key: value, "color": value}

    def _find_tag_end(self, raw: "str", start: "int") -> "int":
        index = start
        variable_depth = 0
        while index < len(raw):
            ch = raw[index]
            if ch == "<" and index > start and index + 1 < len(raw) and raw[index + 1] == "$":
                variable_depth += 1
                index += 1
                continue
            else:
                if ch == ">":
                    if variable_depth == 0:
                        return index
                    variable_depth -= 1
            index += 1
        return -1


    def _split_lines(self, source: "str") -> "list[_Line]":
        lines = []
        offset = 0
        for (number, text) in enumerate((source.splitlines(True)), start=1):
            lines.append(_Line(text=text, start=offset, number=number))
            offset += len(text)

        if not source.endswith(('\n', '\r')):
            return lines
        return lines

    def _ref(self, file_key, source, start, end) -> SourceRef:
        start = max(0, min(start, len(source)))
        end = max(start, min(end, len(source)))
        line = source.count("\n", 0, start) + 1
        line_start = source.rfind("\n", 0, start) + 1
        return SourceRef(file_key=file_key,
          start=start,
          end=end,
          line=line,
          column=(start - line_start + 1),
          raw=(source[start:end]))

    def _node_id(self, file_key, absolute, kind) -> str:
        return f"{file_key}:{absolute}:{kind}"

