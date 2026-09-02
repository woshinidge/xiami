from __future__ import annotations

import hashlib
import os
import random
import re
import shutil
import stat
import struct
import tempfile
import time
import uuid
from array import array
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Mapping, Optional, Sequence, Tuple

from PySide2 import QtCore, QtGui, QtWidgets

from atomic_target_commit import atomic_restore_bytes, protected_target, target_identity, write_exclusive
from toolbox_target_scope import compute_target_scope_sha256


_MAPINFO_RE = re.compile(r"^\s*\[([^\]\s]+)(?:\s+([^\]]+))?\]")
@dataclass
class MapEntry:
    code: str
    file_code: str
    name: str = ""
    known: bool = True

    @property
    def label(self) -> str:
        file_part = "" if self.file_code.lower() == self.code.lower() else "|%s" % self.file_code
        suffix = (" " + self.name) if self.name else ""
        unknown = "  [未在 MapInfo]" if not self.known else ""
        return "%s%s%s%s" % (self.code, file_part, suffix, unknown)


@dataclass
class SpawnRecord:
    uid: str
    map_code: str
    x: int
    y: int
    monster: str
    radius: int
    count: int
    interval: int
    color: str = "255"
    source_line: Optional[int] = None
    original_content: str = ""
    token_spans: List[Tuple[int, int]] = field(default_factory=list)
    original_fields: List[str] = field(default_factory=list)
    deleted: bool = False

    def fields(self) -> List[str]:
        return [
            self.map_code,
            str(self.x),
            str(self.y),
            self.monster,
            str(self.radius),
            str(self.count),
            str(self.interval),
            self.color or "255",
        ]


@dataclass
class TextDocument:
    path: str
    raw: bytes
    encoding: str
    bom: bytes
    newline: str
    terminal_newline: bool
    lines: List[str]
    line_endings: List[str]
    records: List[SpawnRecord]
    record_by_line: Dict[int, SpawnRecord]
    identity: Tuple[int, int, int, int]
    sha256: str
    core_parse: Optional[Dict[str, object]] = None


def _file_identity(path: str) -> Tuple[int, int, int, int]:
    return target_identity(path)


def _decode_roundtrip(raw: bytes, label: str) -> Tuple[str, str, bytes]:
    bom = b"\xef\xbb\xbf" if raw.startswith(b"\xef\xbb\xbf") else b""
    payload = raw[len(bom) :]
    candidates = ["utf-8"] if bom else ["utf-8", "gbk", "gb18030", "big5"]
    for encoding in candidates:
        try:
            text = payload.decode(encoding, errors="strict")
            if text.encode(encoding, errors="strict") == payload:
                return text, encoding, bom
        except (UnicodeDecodeError, UnicodeEncodeError, LookupError):
            continue
    raise UnicodeError("%s 无法使用 UTF-8、GBK、GB18030 或 Big5 严格往返解码" % label)


def _split_preserving_endings(text: str) -> Tuple[List[str], List[str], str, bool]:
    chunks = text.splitlines(True)
    if not chunks and text:
        chunks = [text]
    lines: List[str] = []
    endings: List[str] = []
    counts: Dict[str, int] = {"\r\n": 0, "\n": 0, "\r": 0}
    for chunk in chunks:
        if chunk.endswith("\r\n"):
            content, ending = chunk[:-2], "\r\n"
        elif chunk.endswith("\n"):
            content, ending = chunk[:-1], "\n"
        elif chunk.endswith("\r"):
            content, ending = chunk[:-1], "\r"
        else:
            content, ending = chunk, ""
        lines.append(content)
        endings.append(ending)
        if ending:
            counts[ending] += 1
    newline = max(counts, key=counts.get) if any(counts.values()) else os.linesep
    terminal = bool(endings and endings[-1])
    return lines, endings, newline, terminal


def _spawn_records_from_core(
    text_lines: Sequence[str], result: Mapping[str, object]
) -> Tuple[List[SpawnRecord], Dict[int, SpawnRecord], Dict[str, object]]:
    rows = result.get("records")
    accepted = result.get("accepted")
    rejected = result.get("rejected")
    if not isinstance(rows, list) or type(accepted) is not int or type(rejected) is not int:
        raise ValueError("刷怪服务器核心返回格式无效")
    records: List[SpawnRecord] = []
    record_by_line: Dict[int, SpawnRecord] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            raise ValueError("刷怪服务器核心返回记录无效")
        line_number = row.get("line_number")
        fields = row.get("fields")
        spans = row.get("token_spans")
        if (
            type(line_number) is not int or line_number < 0 or line_number >= len(text_lines)
            or not isinstance(fields, list) or len(fields) not in (7, 8)
            or not isinstance(spans, list) or len(spans) != len(fields)
        ):
            raise ValueError("刷怪服务器核心返回记录边界无效")
        try:
            record = SpawnRecord(
                uid=uuid.uuid4().hex,
                map_code=str(fields[0]),
                x=int(fields[1]),
                y=int(fields[2]),
                monster=str(fields[3]),
                radius=int(fields[4]),
                count=int(fields[5]),
                interval=int(fields[6]),
                color=str(fields[7]) if len(fields) > 7 else "255",
                source_line=line_number,
                original_content=text_lines[line_number],
                token_spans=[(int(span[0]), int(span[1])) for span in spans],
                original_fields=[str(value) for value in fields],
            )
        except (IndexError, TypeError, ValueError) as exc:
            raise ValueError("刷怪服务器核心返回字段无效") from exc
        if line_number in record_by_line:
            raise ValueError("刷怪服务器核心返回重复行")
        records.append(record)
        record_by_line[line_number] = record
    if accepted != len(records) or accepted < 0 or rejected < 0:
        raise ValueError("刷怪服务器核心返回计数无效")
    return records, record_by_line, {
        "source": "server_rpc",
        "accepted": accepted,
        "rejected": rejected,
    }


def load_spawn_document(
    path: str,
    session: Optional[Mapping[str, object]] = None,
) -> TextDocument:
    with open(path, "rb") as stream:
        raw = stream.read()
    text, encoding, bom = _decode_roundtrip(raw, "MonGen.txt")
    lines, endings, newline, terminal = _split_preserving_endings(text)
    if not isinstance(session, Mapping):
        raise RuntimeError("刷怪可视化需要登录并取得服务器核心授权")
    from toolbox_core_rpc import parse_spawn_document_rpc

    target_scope_sha256 = compute_target_scope_sha256("spawn.visual.edit", (path,))
    expected_pre_sha256 = hashlib.sha256(raw).hexdigest()
    result = parse_spawn_document_rpc(
        session,
        text,
        target_scope_sha256=target_scope_sha256,
        expected_pre_sha256=expected_pre_sha256,
    )
    if not isinstance(result, Mapping):
        raise ValueError("刷怪服务器核心返回格式无效")
    records, record_by_line, core_parse = _spawn_records_from_core(lines, result)
    core_parse.update({
        "target_scope_sha256": target_scope_sha256,
        "expected_pre_sha256": expected_pre_sha256,
    })
    return TextDocument(
        path=os.path.abspath(path),
        raw=raw,
        encoding=encoding,
        bom=bom,
        newline=newline,
        terminal_newline=terminal,
        lines=lines,
        line_endings=endings,
        records=records,
        record_by_line=record_by_line,
        identity=_file_identity(path),
        sha256=hashlib.sha256(raw).hexdigest(),
        core_parse=core_parse,
    )


def _render_existing_record(record: SpawnRecord) -> str:
    content = record.original_content
    replacements = record.fields()
    spans = record.token_spans
    replace_count = min(len(replacements), len(spans), 8)
    for index in range(replace_count - 1, -1, -1):
        if index < len(record.original_fields):
            original = record.original_fields[index]
            unchanged = replacements[index] == original
            if index in (1, 2, 4, 5, 6):
                try:
                    unchanged = int(replacements[index]) == int(original)
                except ValueError:
                    pass
            if unchanged:
                continue
        start, end = spans[index]
        content = content[:start] + replacements[index] + content[end:]
    if len(spans) == 7 and record.color not in ("", "255"):
        content += "\t" + record.color
    return content


def serialize_spawn_document(document: TextDocument) -> bytes:
    output: List[str] = []
    for line_number, content in enumerate(document.lines):
        record = document.record_by_line.get(line_number)
        if record is not None and record.deleted:
            continue
        rendered = _render_existing_record(record) if record is not None else content
        output.append(rendered + document.line_endings[line_number])

    new_records = [record for record in document.records if record.source_line is None and not record.deleted]
    if new_records:
        current = "".join(output)
        if current and not current.endswith(("\n", "\r")):
            output.append(document.newline)
        for index, record in enumerate(new_records):
            ending = document.newline
            if index == len(new_records) - 1 and not document.terminal_newline:
                ending = ""
            output.append("\t".join(record.fields()) + ending)
    payload = "".join(output).encode(document.encoding, errors="strict")
    return document.bom + payload


def _unique_backup_path(path: str) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    directory = os.path.dirname(path)
    name = os.path.basename(path)
    for suffix in range(1000):
        extra = "" if suffix == 0 else "_%03d" % suffix
        candidate = os.path.join(directory, "%s.%s%s.visual_spawn.bak" % (name, stamp, extra))
        if not os.path.exists(candidate):
            return candidate
    raise OSError("无法创建唯一 MonGen 备份名")


def save_spawn_document(
    document: TextDocument,
    session: Optional[Mapping[str, object]] = None,
) -> str:
    if not isinstance(session, Mapping):
        raise RuntimeError("刷怪可视化需要登录并取得服务器核心授权")
    new_raw = serialize_spawn_document(document)
    payload = new_raw[len(document.bom) :]
    candidate_text = payload.decode(document.encoding, errors="strict")
    lines, endings, newline, terminal = _split_preserving_endings(candidate_text)
    from toolbox_core_rpc import parse_spawn_document_rpc

    target_scope_sha256 = compute_target_scope_sha256("spawn.visual.edit", (document.path,))
    result = parse_spawn_document_rpc(
        session,
        candidate_text,
        target_scope_sha256=target_scope_sha256,
        expected_pre_sha256=document.sha256,
    )
    if not isinstance(result, Mapping):
        raise ValueError("刷怪服务器核心返回格式无效")
    records, record_by_line, core_parse = _spawn_records_from_core(lines, result)
    core_parse.update({
        "target_scope_sha256": target_scope_sha256,
        "expected_pre_sha256": document.sha256,
    })

    path = document.path
    backup_path = _unique_backup_path(path)
    directory = os.path.dirname(path)
    stage_path = os.path.join(directory, ".visual-spawn-%s.tmp" % uuid.uuid4().hex)
    replaced = False
    replace_attempted = False
    live_stat = None
    try:
        with protected_target(
            path,
            expected_exists=True,
            expected_raw=document.raw,
            expected_identity=document.identity,
        ) as target_guard:
            live_raw = target_guard.assert_current()
            if hashlib.sha256(live_raw).hexdigest() != document.sha256:
                raise RuntimeError("MonGen.txt 已被其他程序修改，请重新加载后再保存")
            fresh_scope = compute_target_scope_sha256("spawn.visual.edit", (path,))
            if fresh_scope != target_scope_sha256:
                raise RuntimeError("MonGen.txt 目标范围在授权后变化，已拒绝覆盖")
            live_stat = os.stat(path, follow_symlinks=False)
            write_exclusive(backup_path, live_raw)
            with open(backup_path, "rb") as stream:
                if stream.read() != live_raw:
                    raise IOError("MonGen.txt 备份校验失败")
            write_exclusive(stage_path, new_raw)
            if Path(stage_path).read_bytes() != new_raw:
                raise IOError("MonGen.txt 暂存文件回读不一致")
            target_guard.assert_current()
            replace_attempted = True
            target_guard.replace_from(stage_path, new_raw)
            replaced = True
        with protected_target(path, expected_exists=True, expected_raw=new_raw) as committed_guard:
            committed_guard.assert_current()
            new_identity = _file_identity(path)
    except Exception as exc:
        rollback_error = None
        if replace_attempted and os.path.isfile(path) and not os.path.islink(path):
            try:
                installed_raw = Path(path).read_bytes()
                replaced = replaced or installed_raw == new_raw
                if replaced:
                    atomic_restore_bytes(
                        path,
                        document.raw,
                        expected_exists=True,
                        expected_raw=new_raw,
                        prefix="visual-spawn-restore",
                        mode=None if live_stat is None else stat.S_IMODE(live_stat.st_mode),
                        atime_ns=None if live_stat is None else int(getattr(live_stat, "st_atime_ns", 0)),
                        mtime_ns=None if live_stat is None else int(getattr(live_stat, "st_mtime_ns", 0)),
                    )
            except Exception as restore_exc:
                rollback_error = restore_exc
        if rollback_error is not None:
            raise RuntimeError("%s；MonGen.txt 原子回滚失败：%s" % (exc, rollback_error)) from exc
        raise
    finally:
        if os.path.exists(stage_path):
            try:
                os.remove(stage_path)
            except OSError:
                pass
    document.raw = new_raw
    document.newline = newline
    document.terminal_newline = terminal
    document.lines = lines
    document.line_endings = endings
    document.records = records
    document.record_by_line = record_by_line
    document.identity = new_identity
    document.sha256 = hashlib.sha256(new_raw).hexdigest()
    document.core_parse = core_parse
    return backup_path


def load_map_entries(path: str) -> List[MapEntry]:
    with open(path, "rb") as stream:
        raw = stream.read()
    text, _encoding, _bom = _decode_roundtrip(raw, "MapInfo.txt")
    result: List[MapEntry] = []
    seen = set()
    for line in text.splitlines():
        match = _MAPINFO_RE.match(line)
        if not match:
            continue
        identifier = match.group(1).strip()
        if "|" in identifier:
            code, file_code = [part.strip() for part in identifier.split("|", 1)]
        else:
            code = file_code = identifier
        key = code.lower()
        if not code or key in seen:
            continue
        seen.add(key)
        result.append(MapEntry(code=code, file_code=file_code or code, name=(match.group(2) or "").strip()))
    return result


def parse_map_grid(path: str) -> Tuple[int, int, bytes]:
    with open(path, "rb") as stream:
        raw = stream.read()
    layout = None
    for size_offset, data_offset in ((0, 52), (16, 20), (20, 24), (52, 56)):
        if len(raw) < max(size_offset + 4, data_offset):
            continue
        width, height = struct.unpack_from("<HH", raw, size_offset)
        if not (1 <= width <= 1200 and 1 <= height <= 1200):
            continue
        data_length = len(raw) - data_offset
        for cell_size in (12, 14):
            if data_length == width * height * cell_size:
                layout = (width, height, data_offset, cell_size)
                break
        if layout:
            break
    if layout is None:
        raise ValueError("无法识别地图格式或尺寸")
    width, height, data_offset, cell_size = layout
    grid = bytearray(width * height)
    for x in range(width):
        column_offset = data_offset + x * height * cell_size
        for y in range(height):
            cell_offset = column_offset + y * cell_size
            background, middle, foreground = struct.unpack_from("<HHH", raw, cell_offset)
            blocked = (background | middle | foreground) & 0x8000
            grid[y * width + x] = 1 if blocked else 0
    return width, height, bytes(grid)


def build_map_image(width: int, height: int, grid: bytes) -> QtGui.QImage:
    if width <= 0 or height <= 0 or len(grid) != width * height:
        raise ValueError("地图网格尺寸不一致")
    image = QtGui.QImage(width, height, QtGui.QImage.Format_RGB32)
    if image.isNull():
        raise MemoryError("无法分配地图图像")
    image.fill(QtGui.QColor("#2E2824"))
    painter = QtGui.QPainter(image)
    try:
        painter.setPen(QtGui.QPen(QtGui.QColor("#706359"), 1))
        for y in range(height):
            row_offset = y * width
            run_start = -1
            for x in range(width):
                blocked = bool(grid[row_offset + x])
                if blocked and run_start < 0:
                    run_start = x
                elif not blocked and run_start >= 0:
                    painter.drawLine(run_start, y, x - 1, y)
                    run_start = -1
            if run_start >= 0:
                painter.drawLine(run_start, y, width - 1, y)
    finally:
        painter.end()
    return image


def _record_color(value: str) -> QtGui.QColor:
    text = str(value or "255").strip()
    direct = QtGui.QColor(text)
    if direct.isValid() and not text.isdigit():
        return direct
    try:
        number = int(text)
    except ValueError:
        number = 255
    if number == 255:
        return QtGui.QColor("#D25A00")
    if number == 0:
        return QtGui.QColor("#374151")
    return QtGui.QColor.fromHsv((number * 47) % 360, 175, 230)


class _SpawnPointItem(QtWidgets.QGraphicsEllipseItem):
    def __init__(self, record: SpawnRecord, moved: Callable[[SpawnRecord], None], selected: Callable[[str], None]):
        super().__init__(-5, -5, 10, 10)
        self.record = record
        self._moved_callback = moved
        self._selected_callback = selected
        self._suspend_record_update = False
        self.setBrush(_record_color(record.color))
        self.setPen(QtGui.QPen(QtGui.QColor("#FFFFFF"), 1))
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
            | QtWidgets.QGraphicsItem.ItemIgnoresTransformations
        )
        self.setToolTip("%s  (%d, %d)  范围 %d" % (record.monster, record.x, record.y, record.radius))
        self.setPos(record.x, record.y)
        self.setZValue(20)

    def set_display_position(self, x: int, y: int) -> None:
        self._suspend_record_update = True
        try:
            self.setPos(int(x), int(y))
        finally:
            self._suspend_record_update = False

    def set_preview(self, enabled: bool) -> None:
        pen = QtGui.QPen(QtGui.QColor("#F59E0B") if enabled else QtGui.QColor("#FFFFFF"), 2 if enabled else 1)
        pen.setCosmetic(True)
        pen.setStyle(QtCore.Qt.DashLine if enabled else QtCore.Qt.SolidLine)
        self.setPen(pen)
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, not enabled)

    def refresh_style(self) -> None:
        self.setBrush(_record_color(self.record.color))
        self.setToolTip(
            "%s  (%d, %d)  范围 %d"
            % (self.record.monster, self.record.x, self.record.y, self.record.radius)
        )

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and self.scene() is not None:
            rect = self.scene().sceneRect()
            point = value
            return QtCore.QPointF(
                min(max(round(point.x()), rect.left()), rect.right()),
                min(max(round(point.y()), rect.top()), rect.bottom()),
            )
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged and self.scene() is not None:
            if not self._suspend_record_update:
                self.record.x = int(round(self.pos().x()))
                self.record.y = int(round(self.pos().y()))
                self.refresh_style()
                self._moved_callback(self.record)
        elif change == QtWidgets.QGraphicsItem.ItemSelectedHasChanged and bool(value):
            self._selected_callback(self.record.uid)
        return super().itemChange(change, value)


class _MapView(QtWidgets.QGraphicsView):
    addPointRequested = QtCore.Signal(float, float)
    scenePositionChanged = QtCore.Signal(float, float, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setRenderHint(QtGui.QPainter.Antialiasing, False)
        self.setDragMode(QtWidgets.QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
        self.setBackgroundBrush(QtGui.QColor("#171B21"))
        self.setMinimumSize(420, 240)
        self.setMouseTracking(True)
        self.coordinate_hud = QtWidgets.QLabel("X --   Y --", self.viewport())
        self.coordinate_hud.setObjectName("mapCoordinateHud")
        self.coordinate_hud.setAlignment(QtCore.Qt.AlignCenter)
        self.coordinate_hud.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.coordinate_hud.setStyleSheet(
            "QLabel#mapCoordinateHud { color: #F9FAFB; background: rgba(23,27,33,210); "
            "border: 1px solid #4B5563; padding: 4px 8px; }"
        )
        self.coordinate_hud.adjustSize()

    def _place_hud(self) -> None:
        self.coordinate_hud.adjustSize()
        self.coordinate_hud.move(max(8, self.viewport().width() - self.coordinate_hud.width() - 10), 10)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_hud()

    def wheelEvent(self, event):
        factor = 1.15 if event.angleDelta().y() > 0 else (1.0 / 1.15)
        current = self.transform().m11()
        if (factor > 1 and current < 20.0) or (factor < 1 and current > 0.05):
            self.scale(factor, factor)
        event.accept()

    def mouseMoveEvent(self, event):
        point = self.mapToScene(event.pos())
        inside = self.scene() is not None and self.scene().sceneRect().contains(point)
        if inside:
            self.coordinate_hud.setText("X %d   Y %d" % (round(point.x()), round(point.y())))
        else:
            self.coordinate_hud.setText("X --   Y --")
        self._place_hud()
        self.scenePositionChanged.emit(point.x(), point.y(), inside)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.coordinate_hud.setText("X --   Y --")
        self._place_hud()
        self.scenePositionChanged.emit(0.0, 0.0, False)
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            point = self.mapToScene(event.pos())
            if self.scene() is not None and self.scene().sceneRect().contains(point):
                self.addPointRequested.emit(point.x(), point.y())
                event.accept()
                return
        super().mouseDoubleClickEvent(event)


class VisualSpawnPage(QtWidgets.QWidget):
    """Native PySide2 visual editor for MapInfo.txt, MonGen.txt and Mir2 MAP files."""

    projectRootChanged = QtCore.Signal(str)
    statusChanged = QtCore.Signal(str)
    saved = QtCore.Signal(str)

    def __init__(
        self,
        parent=None,
        get_root_dir: Optional[Callable[[], str]] = None,
        get_session: Optional[Callable[[], object]] = None,
    ):
        super().__init__(parent)
        self._get_root_dir = get_root_dir
        self._get_session = get_session
        self._project_root = ""
        self._document: Optional[TextDocument] = None
        self._maps: List[MapEntry] = []
        self._visible_maps: List[MapEntry] = []
        self._current_map: Optional[MapEntry] = None
        self._point_items: Dict[str, _SpawnPointItem] = {}
        self._point_labels: Dict[str, QtWidgets.QGraphicsSimpleTextItem] = {}
        self._range_items: Dict[str, QtWidgets.QGraphicsEllipseItem] = {}
        self._selection_items: List[QtWidgets.QGraphicsItem] = []
        self._row_by_uid: Dict[str, int] = {}
        self._selected_uid = ""
        self._preview_positions: Dict[str, Tuple[int, int]] = {}
        self._map_width = 0
        self._map_height = 0
        self._map_grid = b""
        self._syncing = False
        self._scene = QtWidgets.QGraphicsScene(self)
        self._build_ui()
        initial_root = get_root_dir() if callable(get_root_dir) else ""
        if initial_root:
            self.set_project_root(initial_root)

    def _build_ui(self) -> None:
        self.setObjectName("visualSpawnPage")
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        toolbar = QtWidgets.QHBoxLayout()
        toolbar.setSpacing(6)
        self.path_label = QtWidgets.QLabel("未选择服务端根目录")
        self.path_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.path_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.reload_button = QtWidgets.QPushButton("重新读取")
        self.reload_button.clicked.connect(self.reload)
        self.add_button = QtWidgets.QPushButton("新增刷怪点")
        self.add_button.clicked.connect(self._add_at_center)
        self.delete_button = QtWidgets.QPushButton("删除刷怪点")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self.delete_selected)
        self.save_button = QtWidgets.QPushButton("保存")
        self.save_button.setObjectName("primaryButton")
        self.save_button.setProperty("buttonRole", "primary")
        self.save_button.clicked.connect(self.save)
        for widget in (self.path_label, self.reload_button, self.add_button, self.delete_button, self.save_button):
            toolbar.addWidget(widget)
        outer.addLayout(toolbar)

        self.main_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        self.top_splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)

        map_panel = QtWidgets.QWidget()
        map_layout = QtWidgets.QVBoxLayout(map_panel)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(6)
        map_header = QtWidgets.QHBoxLayout()
        map_title = QtWidgets.QLabel("地图列表")
        map_title.setObjectName("sectionTitle")
        self.map_count_label = QtWidgets.QLabel("0 个地图")
        self.map_count_label.setObjectName("mutedText")
        map_header.addWidget(map_title)
        map_header.addStretch(1)
        map_header.addWidget(self.map_count_label)
        map_layout.addLayout(map_header)
        self.map_search = QtWidgets.QLineEdit()
        self.map_search.setPlaceholderText("搜索地图编号或名称")
        self.map_search.setClearButtonEnabled(True)
        self.map_search.textChanged.connect(self._refresh_map_list)
        map_layout.addWidget(self.map_search)
        self.map_sort = QtWidgets.QComboBox()
        self.map_sort.addItem("原始顺序", "original")
        self.map_sort.addItem("刷怪数量：多到少", "count_desc")
        self.map_sort.addItem("刷怪数量：少到多", "count_asc")
        self.map_sort.currentIndexChanged.connect(self._refresh_map_list)
        map_layout.addWidget(self.map_sort)
        self.map_list = QtWidgets.QListWidget()
        self.map_list.setObjectName("visualSpawnMapList")
        self.map_list.setMinimumWidth(210)
        self.map_list.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.map_list.currentRowChanged.connect(self._map_changed)
        map_layout.addWidget(self.map_list, 1)
        self.top_splitter.addWidget(map_panel)

        canvas = QtWidgets.QWidget()
        canvas_layout = QtWidgets.QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(6)
        canvas_toolbar = QtWidgets.QHBoxLayout()
        canvas_toolbar.setSpacing(6)
        self.map_status = QtWidgets.QLabel("请选择地图")
        self.map_status.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        self.show_points_checkbox = QtWidgets.QCheckBox("点位")
        self.show_points_checkbox.setChecked(True)
        self.show_names_checkbox = QtWidgets.QCheckBox("怪名")
        self.show_names_checkbox.setChecked(True)
        self.show_ranges_checkbox = QtWidgets.QCheckBox("范围")
        self.show_ranges_checkbox.setChecked(False)
        for checkbox in (self.show_points_checkbox, self.show_names_checkbox, self.show_ranges_checkbox):
            checkbox.toggled.connect(self._update_point_visibility)
        self.zoom_out_button = QtWidgets.QPushButton("-")
        self.zoom_out_button.setFixedWidth(34)
        self.zoom_out_button.clicked.connect(lambda: self.map_view.scale(1 / 1.2, 1 / 1.2))
        self.fit_button = QtWidgets.QPushButton("适应窗口")
        self.fit_button.clicked.connect(self.fit_map)
        self.zoom_in_button = QtWidgets.QPushButton("+")
        self.zoom_in_button.setFixedWidth(34)
        self.zoom_in_button.clicked.connect(lambda: self.map_view.scale(1.2, 1.2))
        for widget in (
            self.map_status,
            self.show_points_checkbox,
            self.show_names_checkbox,
            self.show_ranges_checkbox,
            self.zoom_out_button,
            self.fit_button,
            self.zoom_in_button,
        ):
            canvas_toolbar.addWidget(widget)
        canvas_layout.addLayout(canvas_toolbar)
        self.map_view = _MapView()
        self.map_view.setScene(self._scene)
        self.map_view.addPointRequested.connect(self._add_point)
        canvas_layout.addWidget(self.map_view, 1)
        self.top_splitter.addWidget(canvas)
        self.top_splitter.setStretchFactor(0, 0)
        self.top_splitter.setStretchFactor(1, 1)
        self.top_splitter.setChildrenCollapsible(False)
        self.top_splitter.setSizes([220, 1080])
        self.main_splitter.addWidget(self.top_splitter)

        table_panel = QtWidgets.QWidget()
        table_layout = QtWidgets.QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(6)
        batch_toolbar = QtWidgets.QHBoxLayout()
        batch_toolbar.setSpacing(6)
        self.table_title = QtWidgets.QLabel("刷怪点 0")
        self.table_title.setObjectName("sectionTitle")
        self.preview_label = QtWidgets.QLabel("无预览")
        self.preview_label.setObjectName("mutedText")
        self.uniform_scatter_button = QtWidgets.QPushButton("均匀打散")
        self.uniform_scatter_button.clicked.connect(self.preview_uniform_scatter)
        self.random_scatter_button = QtWidgets.QPushButton("随机打散")
        self.random_scatter_button.clicked.connect(self.preview_random_scatter)
        self.apply_preview_button = QtWidgets.QPushButton("应用预览")
        self.apply_preview_button.setProperty("buttonRole", "secondary")
        self.apply_preview_button.clicked.connect(self.apply_scatter_preview)
        self.cancel_preview_button = QtWidgets.QPushButton("撤销预览")
        self.cancel_preview_button.clicked.connect(self.cancel_scatter_preview)
        batch_toolbar.addWidget(self.table_title)
        batch_toolbar.addWidget(self.preview_label)
        batch_toolbar.addStretch(1)
        batch_toolbar.addWidget(QtWidgets.QLabel("批量点位"))
        for widget in (
            self.uniform_scatter_button,
            self.random_scatter_button,
            self.apply_preview_button,
            self.cancel_preview_button,
        ):
            batch_toolbar.addWidget(widget)
        table_layout.addLayout(batch_toolbar)

        self.point_table = QtWidgets.QTableWidget(0, 7)
        self.point_table.setHorizontalHeaderLabels(["怪物", "X", "Y", "范围", "数量", "时间", "颜色"])
        self.point_table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.point_table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.point_table.setEditTriggers(QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed)
        self.point_table.setAlternatingRowColors(True)
        self.point_table.setMinimumHeight(150)
        self.point_table.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.point_table.verticalHeader().setVisible(False)
        self.point_table.verticalHeader().setDefaultSectionSize(28)
        self.point_table.itemSelectionChanged.connect(self._table_selection_changed)
        self.point_table.itemChanged.connect(self._table_item_changed)
        self.point_table.cellDoubleClicked.connect(self._table_cell_double_clicked)
        header = self.point_table.horizontalHeader()
        header.setMinimumSectionSize(64)
        header.setSectionsClickable(True)
        header.setToolTip("双击 X、Y、范围、数量、时间或颜色列头可批量修改")
        header.sectionDoubleClicked.connect(self._batch_header_double_clicked)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for column in range(1, 7):
            header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        table_layout.addWidget(self.point_table, 1)
        self.main_splitter.addWidget(table_panel)
        self.main_splitter.setStretchFactor(0, 3)
        self.main_splitter.setStretchFactor(1, 2)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.setSizes([320, 220])
        outer.addWidget(self.main_splitter, 1)

        self.status_label = QtWidgets.QLabel("双击地图可新增刷怪点；拖动圆点可调整坐标。")
        self.status_label.setObjectName("mutedText")
        self.status_label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        outer.addWidget(self.status_label)
        self._update_preview_controls()

    @property
    def project_root(self) -> str:
        return self._project_root

    @property
    def scatter_preview_active(self) -> bool:
        return bool(self._preview_positions)

    @property
    def preview_positions(self) -> Dict[str, Tuple[int, int]]:
        return dict(self._preview_positions)

    def set_project_root(self, path: str) -> bool:
        root = self._normalize_root(path)
        if not root:
            self._set_status("未找到 Mir200\\Envir\\MapInfo.txt 和 MonGen.txt")
            return False
        self._project_root = root
        self.path_label.setText(root)
        self.path_label.setToolTip(root)
        self.projectRootChanged.emit(root)
        return self.reload()

    def _normalize_root(self, path: str) -> str:
        candidate = os.path.abspath(os.path.normpath(str(path or "").strip()))
        options = [candidate]
        if os.path.basename(candidate).lower() == "mir200":
            options.append(os.path.dirname(candidate))
        if os.path.basename(candidate).lower() == "envir" and os.path.basename(os.path.dirname(candidate)).lower() == "mir200":
            options.append(os.path.dirname(os.path.dirname(candidate)))
        for option in options:
            envir = os.path.join(option, "Mir200", "Envir")
            if os.path.isfile(os.path.join(envir, "MapInfo.txt")) and os.path.isfile(os.path.join(envir, "MonGen.txt")):
                return option
        return ""

    def reload(self) -> bool:
        if not self._project_root:
            root = self._get_root_dir() if callable(self._get_root_dir) else ""
            if root:
                return self.set_project_root(root)
            return False
        self._clear_preview_state()
        try:
            envir = os.path.join(self._project_root, "Mir200", "Envir")
            session = None
            if callable(self._get_session):
                try:
                    session = self._get_session()
                except Exception:
                    session = None
            self._document = load_spawn_document(
                os.path.join(envir, "MonGen.txt"), session=session if isinstance(session, Mapping) else None
            )
            self._maps = load_map_entries(os.path.join(envir, "MapInfo.txt"))
            known = {entry.code.lower() for entry in self._maps}
            for code in sorted({record.map_code for record in self._document.records}, key=str.lower):
                if code.lower() not in known:
                    self._maps.append(MapEntry(code=code, file_code=code, known=False))
                    known.add(code.lower())
            previous = self._current_map.code.lower() if self._current_map else ""
            self._refresh_map_list(select_code=previous)
            if not self._maps:
                self._clear_scene("MapInfo.txt 中没有可用地图")
            self._set_status("已读取 %d 个地图、%d 条刷怪记录" % (len(self._maps), len(self._document.records)))
            return True
        except Exception as exc:
            self._document = None
            self._maps = []
            self._visible_maps = []
            self._current_map = None
            self.map_list.clear()
            self.map_count_label.setText("0 个地图")
            self._clear_scene("读取失败")
            self._set_status("读取失败：%s" % exc)
            return False

    def _active_records(self, entry: Optional[MapEntry] = None) -> List[SpawnRecord]:
        if self._document is None:
            return []
        target = entry or self._current_map
        if target is None:
            return []
        return [
            record
            for record in self._document.records
            if not record.deleted and record.map_code.lower() == target.code.lower()
        ]

    def _map_record_count(self, entry: MapEntry) -> int:
        return len(self._active_records(entry))

    def _refresh_map_list(self, _value=None, select_code: str = "") -> None:
        current_code = select_code or (self._current_map.code if self._current_map else "")
        query = self.map_search.text().strip().lower()
        visible = [
            entry
            for entry in self._maps
            if not query or query in entry.code.lower() or query in entry.file_code.lower() or query in entry.name.lower()
        ]
        mode = str(self.map_sort.currentData() or "original")
        if mode in ("count_desc", "count_asc"):
            original_order = {entry.code.lower(): index for index, entry in enumerate(self._maps)}
            reverse = mode == "count_desc"
            visible.sort(
                key=lambda entry: (
                    self._map_record_count(entry),
                    -original_order.get(entry.code.lower(), 0) if reverse else original_order.get(entry.code.lower(), 0),
                ),
                reverse=reverse,
            )
        self._visible_maps = visible
        self.map_list.blockSignals(True)
        try:
            self.map_list.clear()
            selected_row = -1
            for index, entry in enumerate(visible):
                count = self._map_record_count(entry)
                item = QtWidgets.QListWidgetItem("%s    [%d]" % (entry.label, count))
                item.setData(QtCore.Qt.UserRole, entry.code)
                item.setToolTip("%s\n刷怪点：%d" % (entry.label, count))
                self.map_list.addItem(item)
                if entry.code.lower() == current_code.lower():
                    selected_row = index
            if selected_row < 0 and visible:
                selected_row = 0
            self.map_list.setCurrentRow(selected_row)
        finally:
            self.map_list.blockSignals(False)
        self.map_count_label.setText("%d / %d 个地图" % (len(visible), len(self._maps)))
        if selected_row >= 0:
            self._map_changed(selected_row)
        elif visible:
            self._map_changed(0)
        else:
            self._current_map = None
            self._clear_scene("没有匹配的地图")

    def _map_changed(self, row: int) -> None:
        if row < 0 or row >= self.map_list.count():
            return
        self._clear_preview_state()
        item = self.map_list.item(row)
        code = str(item.data(QtCore.Qt.UserRole) or "")
        self._current_map = next((entry for entry in self._maps if entry.code.lower() == code.lower()), None)
        if self._current_map is None:
            return
        self._render_current_map()

    def _map_file_path(self, entry: MapEntry) -> str:
        file_name = entry.file_code
        if not os.path.splitext(file_name)[1]:
            file_name += ".map"
        candidates = [
            os.path.join(self._project_root, "Mir200", "Map", file_name),
            os.path.join(self._project_root, "Map", file_name),
            os.path.join(self._project_root, "Map", "Map", file_name),
        ]
        for candidate in candidates:
            if os.path.isfile(candidate):
                return candidate
        return ""

    def _render_current_map(self) -> None:
        entry = self._current_map
        document = self._document
        if entry is None or document is None:
            return
        path = self._map_file_path(entry)
        width = height = 0
        grid = b""
        self._map_width = 0
        self._map_height = 0
        self._map_grid = b""
        error = ""
        if path:
            try:
                width, height, grid = parse_map_grid(path)
            except Exception as exc:
                error = str(exc)
        else:
            error = "未找到地图文件"
        self._scene.clear()
        self._point_items.clear()
        self._point_labels.clear()
        self._range_items.clear()
        self._selection_items.clear()
        selected_uid = self._selected_uid
        self._selected_uid = ""
        if width and height:
            self._map_width = width
            self._map_height = height
            self._map_grid = grid
            image = build_map_image(width, height, grid)
            background = self._scene.addPixmap(QtGui.QPixmap.fromImage(image))
            background.setZValue(0)
            self._scene.setSceneRect(0, 0, width - 1, height - 1)
            self.map_status.setText("%s  %d x %d" % (entry.label, width, height))
        else:
            self._scene.setSceneRect(0, 0, 800, 600)
            self._scene.addText(error).setDefaultTextColor(QtGui.QColor("#AAB2BF"))
            self.map_status.setText("%s  %s" % (entry.label, error))

        records = self._active_records(entry)
        self._populate_table(records)
        for record in records:
            color = _record_color(record.color)
            range_pen = QtGui.QPen(color, 1)
            range_pen.setCosmetic(True)
            range_pen.setStyle(QtCore.Qt.DashLine)
            range_color = QtGui.QColor(color)
            range_color.setAlpha(145)
            range_pen.setColor(range_color)
            radius = max(0, record.radius)
            range_item = self._scene.addEllipse(
                record.x - radius,
                record.y - radius,
                radius * 2,
                radius * 2,
                range_pen,
                QtGui.QBrush(QtCore.Qt.NoBrush),
            )
            range_item.setZValue(5)
            self._range_items[record.uid] = range_item

            label = self._scene.addSimpleText(record.monster)
            label.setBrush(QtGui.QBrush(QtGui.QColor("#F9FAFB")))
            label.setFlag(QtWidgets.QGraphicsItem.ItemIgnoresTransformations, True)
            label.setPos(record.x + 7, record.y - 15)
            label.setZValue(15)
            self._point_labels[record.uid] = label

            point = _SpawnPointItem(record, self._point_moved, self._select_uid)
            self._scene.addItem(point)
            self._point_items[record.uid] = point
        self._update_point_visibility()
        self._update_preview_controls()
        self.fit_map()
        if selected_uid in self._point_items:
            self._select_uid(selected_uid)

    def _populate_table(self, records: Sequence[SpawnRecord]) -> None:
        self._syncing = True
        try:
            self.point_table.setRowCount(0)
            self._row_by_uid.clear()
            for row, record in enumerate(records):
                self.point_table.insertRow(row)
                values = [record.monster, record.x, record.y, record.radius, record.count, record.interval, record.color]
                for column, value in enumerate(values):
                    item = QtWidgets.QTableWidgetItem(str(value))
                    item.setFlags(item.flags() | QtCore.Qt.ItemIsEditable)
                    item.setData(QtCore.Qt.UserRole, record.uid)
                    if column == 6:
                        color = _record_color(record.color)
                        item.setBackground(QtGui.QBrush(color))
                        luminance = color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114
                        item.setForeground(QtGui.QBrush(QtGui.QColor("#111827" if luminance > 150 else "#FFFFFF")))
                        item.setTextAlignment(QtCore.Qt.AlignCenter)
                    elif column > 0:
                        item.setTextAlignment(QtCore.Qt.AlignCenter)
                    self.point_table.setItem(row, column, item)
                self._row_by_uid[record.uid] = row
            self.table_title.setText("刷怪点 %d" % len(records))
        finally:
            self._syncing = False

    def _clear_scene(self, message: str) -> None:
        self._scene.clear()
        self._point_items.clear()
        self._point_labels.clear()
        self._range_items.clear()
        self._selection_items.clear()
        self._selected_uid = ""
        self._scene.setSceneRect(0, 0, 800, 600)
        text_item = self._scene.addText(message)
        text_item.setDefaultTextColor(QtGui.QColor("#AAB2BF"))
        self.point_table.setRowCount(0)
        self.table_title.setText("刷怪点 0")
        self._update_preview_controls()

    def _update_point_visibility(self) -> None:
        show_points = self.show_points_checkbox.isChecked()
        show_names = self.show_names_checkbox.isChecked()
        show_ranges = self.show_ranges_checkbox.isChecked()
        for item in self._point_items.values():
            item.setVisible(show_points)
        for item in self._point_labels.values():
            item.setVisible(show_names)
        for uid, item in self._range_items.items():
            item.setVisible(show_ranges or uid == self._selected_uid)
        self._update_selection_overlay(self._selected_uid)

    def _update_auxiliary_items(self, record: SpawnRecord, x: Optional[int] = None, y: Optional[int] = None) -> None:
        display_x = record.x if x is None else int(x)
        display_y = record.y if y is None else int(y)
        label = self._point_labels.get(record.uid)
        if label is not None:
            label.setText(record.monster)
            label.setPos(display_x + 7, display_y - 15)
        range_item = self._range_items.get(record.uid)
        if range_item is not None:
            radius = max(0, record.radius)
            range_item.setRect(display_x - radius, display_y - radius, radius * 2, radius * 2)
            color = _record_color(record.color)
            color.setAlpha(145)
            pen = range_item.pen()
            pen.setColor(color)
            range_item.setPen(pen)
        point = self._point_items.get(record.uid)
        if point is not None:
            point.refresh_style()
        if record.uid == self._selected_uid:
            self._update_selection_overlay(record.uid)

    def fit_map(self) -> None:
        if not self._scene.items():
            return
        self.map_view.fitInView(self._scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def _record_by_uid(self, uid: str) -> Optional[SpawnRecord]:
        if self._document is None:
            return None
        return next((record for record in self._document.records if record.uid == uid), None)

    def _table_selection_changed(self) -> None:
        if self._syncing:
            return
        row = self.point_table.currentRow()
        item = self.point_table.item(row, 0) if row >= 0 else None
        if item is not None:
            self._select_uid(str(item.data(QtCore.Qt.UserRole) or ""), from_table=True)

    def _select_uid(self, uid: str, from_table: bool = False) -> None:
        if uid not in self._point_items:
            uid = ""
        self._selected_uid = uid
        self._syncing = True
        try:
            for item_uid, point in self._point_items.items():
                point.setSelected(item_uid == uid)
            if not from_table and uid in self._row_by_uid:
                self.point_table.selectRow(self._row_by_uid[uid])
        finally:
            self._syncing = False
        self.delete_button.setEnabled(bool(uid) and not self._preview_positions)
        self._update_point_visibility()
        record = self._record_by_uid(uid)
        if record is not None and not self._preview_positions:
            self._set_status(
                "已选择 %s · 坐标 (%d, %d) · 范围 %d"
                % (record.monster, record.x, record.y, record.radius)
            )

    def _update_selection_overlay(self, uid: str) -> None:
        for item in self._selection_items:
            if item.scene() is self._scene:
                self._scene.removeItem(item)
        self._selection_items.clear()
        point = self._point_items.get(uid)
        record = self._record_by_uid(uid)
        if point is None or record is None:
            return
        x, y = point.pos().x(), point.pos().y()
        radius = max(0, record.radius)
        accent = QtGui.QColor("#F59E0B")
        pen = QtGui.QPen(accent, 1)
        pen.setCosmetic(True)
        pen.setStyle(QtCore.Qt.DashLine)
        horizontal = self._scene.addLine(x - 11, y, x + 11, y, pen)
        vertical = self._scene.addLine(x, y - 11, x, y + 11, pen)
        circle = self._scene.addEllipse(
            x - radius,
            y - radius,
            radius * 2,
            radius * 2,
            pen,
            QtGui.QBrush(QtCore.Qt.NoBrush),
        )
        for item in (horizontal, vertical, circle):
            item.setZValue(25)
            self._selection_items.append(item)

    def _table_item_changed(self, item: QtWidgets.QTableWidgetItem) -> None:
        if self._syncing:
            return
        uid = str(item.data(QtCore.Qt.UserRole) or "")
        record = self._record_by_uid(uid)
        if record is None:
            return
        row = item.row()
        try:
            monster = self.point_table.item(row, 0).text().strip()
            if not monster:
                raise ValueError("怪物名称不能为空")
            x = int(self.point_table.item(row, 1).text())
            y = int(self.point_table.item(row, 2).text())
            radius = int(self.point_table.item(row, 3).text())
            count = int(self.point_table.item(row, 4).text())
            interval = int(self.point_table.item(row, 5).text())
            if radius < 0 or count < 0 or interval < 0:
                raise ValueError("范围、数量和时间不能小于 0")
            record.monster = monster
            record.x = x
            record.y = y
            record.radius = radius
            record.count = count
            record.interval = interval
            record.color = self.point_table.item(row, 6).text().strip() or "255"
        except ValueError:
            self._set_status("名称不能为空；坐标、范围、数量和时间必须是有效整数")
            self._render_current_map()
            return
        point = self._point_items.get(uid)
        if point is not None:
            point.set_display_position(record.x, record.y)
        color_item = self.point_table.item(row, 6)
        color = _record_color(record.color)
        color_item.setBackground(QtGui.QBrush(color))
        luminance = color.red() * 0.299 + color.green() * 0.587 + color.blue() * 0.114
        color_item.setForeground(QtGui.QBrush(QtGui.QColor("#111827" if luminance > 150 else "#FFFFFF")))
        self._update_auxiliary_items(record)
        self._set_status("已修改 %s，尚未保存" % record.monster)

    def _table_cell_double_clicked(self, row: int, column: int) -> None:
        if self._preview_positions:
            self.cancel_scatter_preview()

        def begin_edit() -> None:
            item = self.point_table.item(row, column)
            if item is None:
                return
            self.point_table.setCurrentItem(item)
            self.point_table.editItem(item)

        QtCore.QTimer.singleShot(0, begin_edit)

    def _batch_header_double_clicked(self, column: int) -> None:
        column_names = {1: "X", 2: "Y", 3: "范围", 4: "数量", 5: "时间", 6: "颜色"}
        name = column_names.get(int(column))
        if name is None:
            self._set_status("怪物名称不支持数值批量运算")
            return
        if self._preview_positions:
            self.cancel_scatter_preview()

        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("批量修改 %s" % name)
        dialog.setModal(True)
        dialog.setMinimumWidth(360)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        title = QtWidgets.QLabel("批量修改当前地图的 %s" % name)
        title.setStyleSheet("font-weight: 600;")
        layout.addWidget(title)

        form = QtWidgets.QFormLayout()
        operation_combo = QtWidgets.QComboBox()
        for text, value in (("加 (+)", "+"), ("减 (-)", "-"), ("乘 (×)", "*"), ("除 (÷)", "/"), ("等于 (=)", "=")):
            operation_combo.addItem(text, value)
        operand_input = QtWidgets.QDoubleSpinBox()
        operand_input.setDecimals(3)
        operand_input.setRange(-1000000000.0, 1000000000.0)
        operand_input.setValue(1.0)
        operand_input.setSingleStep(1.0)
        form.addRow("运算", operation_combo)
        form.addRow("数值", operand_input)
        layout.addLayout(form)
        hint = QtWidgets.QLabel("对当前地图全部刷怪点执行，结果按整数保存；任何一项越界时整批不修改。")
        hint.setWordWrap(True)
        hint.setObjectName("mutedText")
        layout.addWidget(hint)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("应用")
        buttons.button(QtWidgets.QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return
        operation = str(operation_combo.currentData() or "")
        self._apply_batch_operation(column, operation, float(operand_input.value()))

    def _apply_batch_operation(self, column: int, operation: str, operand: float) -> bool:
        columns = {
            1: ("X", "x"),
            2: ("Y", "y"),
            3: ("范围", "radius"),
            4: ("数量", "count"),
            5: ("时间", "interval"),
            6: ("颜色", "color"),
        }
        field = columns.get(int(column))
        records = self._active_records()
        if field is None or not records:
            self._set_status("当前列或当前地图不支持批量修改")
            return False
        if operation not in ("+", "-", "*", "/", "="):
            self._set_status("不支持的批量运算：%s" % operation)
            return False
        if operation == "/" and operand == 0:
            self._set_status("批量除法的除数不能为 0")
            return False

        values: List[int] = []
        try:
            for record in records:
                current = int(getattr(record, field[1]))
                if operation == "+":
                    result = current + operand
                elif operation == "-":
                    result = current - operand
                elif operation == "*":
                    result = current * operand
                elif operation == "/":
                    result = current / operand
                else:
                    result = operand
                value = int(round(result))
                if column == 1 and not (0 <= value < self._map_width):
                    raise ValueError("X 必须在 0 到 %d 之间" % max(0, self._map_width - 1))
                if column == 2 and not (0 <= value < self._map_height):
                    raise ValueError("Y 必须在 0 到 %d 之间" % max(0, self._map_height - 1))
                if column in (3, 4, 5) and value < 0:
                    raise ValueError("%s 不能小于 0" % field[0])
                if column == 6 and not (0 <= value <= 255):
                    raise ValueError("颜色必须在 0 到 255 之间")
                values.append(value)
        except (TypeError, ValueError, OverflowError) as exc:
            self._set_status("批量修改未执行：%s" % exc)
            return False

        for record, value in zip(records, values):
            setattr(record, field[1], str(value) if column == 6 else value)
        self._render_current_map()
        self._set_status(
            "已批量修改 %s：%s %s，共 %d 个刷怪点，尚未保存"
            % (field[0], operation, operand, len(records))
        )
        return True

    def _point_moved(self, record: SpawnRecord) -> None:
        if self._syncing:
            return
        row = self._row_by_uid.get(record.uid)
        if row is None:
            return
        self._syncing = True
        try:
            self.point_table.item(row, 1).setText(str(record.x))
            self.point_table.item(row, 2).setText(str(record.y))
        finally:
            self._syncing = False
        self._update_auxiliary_items(record)
        self._set_status("已移动 %s 到 (%d, %d)，尚未保存" % (record.monster, record.x, record.y))

    def _clear_preview_state(self) -> None:
        self._preview_positions.clear()
        if hasattr(self, "preview_label"):
            self._update_preview_controls()

    def _update_preview_controls(self) -> None:
        active = bool(self._preview_positions)
        ready = self._document is not None and self._current_map is not None
        map_ready = (
            self._map_width > 0
            and self._map_height > 0
            and len(self._map_grid) == self._map_width * self._map_height
        )
        self.preview_label.setText(
            "预览中 · %d 个点 · 未写入" % len(self._preview_positions)
            if active
            else "无预览"
        )
        if active:
            self.preview_label.setStyleSheet("color: #B45309; font-weight: 600;")
        else:
            self.preview_label.setStyleSheet("")
        self.apply_preview_button.setEnabled(active)
        self.cancel_preview_button.setEnabled(active)
        self.save_button.setEnabled(ready and not active)
        self.add_button.setEnabled(ready and not active)
        self.delete_button.setEnabled(not active and bool(self._selected_uid))
        self.uniform_scatter_button.setEnabled(ready and map_ready)
        self.random_scatter_button.setEnabled(ready and map_ready)
        self.point_table.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers
            if active
            else QtWidgets.QAbstractItemView.DoubleClicked | QtWidgets.QAbstractItemView.EditKeyPressed
        )

    def _walkable_indexes(self) -> array:
        if len(self._map_grid) != self._map_width * self._map_height:
            return array("I")
        return array("I", (index for index, blocked in enumerate(self._map_grid) if not blocked))

    def _uniform_walkable_indexes(self, walkable: array, count: int) -> List[int]:
        candidate_limit = max(25000, count * 128)
        if len(walkable) <= candidate_limit:
            candidates = list(walkable)
        else:
            last = len(walkable) - 1
            candidates = [walkable[(index * last) // (candidate_limit - 1)] for index in range(candidate_limit)]

        center_x = (self._map_width - 1) / 2.0
        center_y = (self._map_height - 1) / 2.0
        first = min(
            range(len(candidates)),
            key=lambda index: (
                (candidates[index] % self._map_width - center_x) ** 2
                + (candidates[index] // self._map_width - center_y) ** 2
            ),
        )
        selected = [candidates[first]]
        chosen = {first}
        minimum_distances = [float("inf")] * len(candidates)
        while len(selected) < count:
            last_index = selected[-1]
            last_x = last_index % self._map_width
            last_y = last_index // self._map_width
            best_candidate = -1
            best_distance = -1.0
            for index, candidate in enumerate(candidates):
                if index in chosen:
                    continue
                x = candidate % self._map_width
                y = candidate // self._map_width
                distance = float((x - last_x) ** 2 + (y - last_y) ** 2)
                if distance < minimum_distances[index]:
                    minimum_distances[index] = distance
                if minimum_distances[index] > best_distance:
                    best_distance = minimum_distances[index]
                    best_candidate = index
            if best_candidate < 0:
                break
            chosen.add(best_candidate)
            selected.append(candidates[best_candidate])
        return selected

    def _preview_scatter(self, mode: str) -> bool:
        records = self._active_records()
        if not records:
            self._set_status("当前地图没有可打散的刷怪点")
            return False
        walkable = self._walkable_indexes()
        if len(walkable) < len(records):
            self._set_status(
                "当前地图只有 %d 个可通行格，无法放置 %d 个不重复刷怪点"
                % (len(walkable), len(records))
            )
            return False
        if mode == "uniform":
            selected_indexes = self._uniform_walkable_indexes(walkable, len(records))
            label = "均匀打散"
        else:
            generator = random.Random(time.time_ns())
            selected_indexes = [
                walkable[index]
                for index in generator.sample(range(len(walkable)), len(records))
            ]
            label = "随机打散"
        positions = [
            (index % self._map_width, index // self._map_width)
            for index in selected_indexes
        ]
        self._preview_positions = {
            record.uid: (x, y)
            for record, (x, y) in zip(records, positions)
        }
        blocker = QtCore.QSignalBlocker(self.point_table)
        try:
            for record in records:
                point = self._point_items.get(record.uid)
                x, y = self._preview_positions[record.uid]
                if point is not None:
                    point.set_display_position(x, y)
                    point.set_preview(True)
                self._update_auxiliary_items(record, x, y)
                row = self._row_by_uid.get(record.uid)
                if row is not None:
                    for column in range(self.point_table.columnCount()):
                        item = self.point_table.item(row, column)
                        if item is None:
                            continue
                        item.setData(QtCore.Qt.UserRole + 1, "preview")
                        item.setToolTip("打散预览，尚未写入 MonGen.txt")
                        if column < 6:
                            item.setBackground(QtGui.QBrush(QtGui.QColor("#FFF3E6")))
        finally:
            del blocker
        self._update_preview_controls()
        self._update_selection_overlay(self._selected_uid)
        self._set_status("%s预览：%d 个点位，应用前不会修改或保存" % (label, len(records)))
        return True

    def preview_uniform_scatter(self) -> bool:
        return self._preview_scatter("uniform")

    def preview_random_scatter(self) -> bool:
        return self._preview_scatter("random")

    def apply_scatter_preview(self) -> bool:
        if not self._preview_positions:
            self._set_status("当前没有可应用的打散预览")
            return False
        applied = 0
        for uid, (x, y) in self._preview_positions.items():
            record = self._record_by_uid(uid)
            if record is not None and not record.deleted:
                record.x, record.y = int(x), int(y)
                applied += 1
        self._clear_preview_state()
        self._render_current_map()
        self._set_status("已应用 %d 个预览点位，尚未保存" % applied)
        return True

    def cancel_scatter_preview(self) -> bool:
        if not self._preview_positions:
            self._set_status("当前没有打散预览")
            return False
        self._clear_preview_state()
        self._render_current_map()
        self._set_status("已撤销打散预览，原始点位未修改")
        return True

    def _add_at_center(self) -> None:
        center = self.map_view.mapToScene(self.map_view.viewport().rect().center())
        self._add_point(center.x(), center.y())

    def _add_point(self, x: float, y: float) -> None:
        if self._preview_positions:
            self._set_status("请先应用或撤销打散预览")
            return
        if self._document is None or self._current_map is None:
            self._set_status("请先读取并选择地图")
            return
        monster, accepted = QtWidgets.QInputDialog.getText(self, "新增刷怪点", "怪物名称：")
        if not accepted or not monster.strip():
            return
        record = SpawnRecord(
            uid=uuid.uuid4().hex,
            map_code=self._current_map.code,
            x=max(1, int(round(x))),
            y=max(1, int(round(y))),
            monster=monster.strip(),
            radius=50,
            count=1,
            interval=60,
        )
        self._document.records.append(record)
        current_code = self._current_map.code
        self._refresh_map_list(select_code=current_code)
        self._select_uid(record.uid)
        self._set_status("已新增 %s，尚未保存" % record.monster)

    def delete_selected(self) -> None:
        if self._preview_positions:
            self._set_status("请先应用或撤销打散预览")
            return
        row = self.point_table.currentRow()
        item = self.point_table.item(row, 0) if row >= 0 else None
        record = self._record_by_uid(str(item.data(QtCore.Qt.UserRole) or "")) if item is not None else None
        if record is None:
            self._set_status("请选择要删除的刷怪点")
            return
        record.deleted = True
        current_code = self._current_map.code if self._current_map else ""
        self._selected_uid = ""
        self._refresh_map_list(select_code=current_code)
        self._set_status("已标记删除 %s，保存后生效" % record.monster)

    def save(self) -> bool:
        if self._preview_positions:
            self._set_status("打散仍处于预览状态，请先应用或撤销；本次未保存")
            return False
        if self._document is None:
            self._set_status("没有可保存的数据")
            return False
        try:
            session = None
            if callable(self._get_session):
                try:
                    session = self._get_session()
                except Exception:
                    session = None
            backup_path = save_spawn_document(
                self._document,
                session=session if isinstance(session, Mapping) else None,
            )
            current_map = self._current_map.code if self._current_map else ""
            self._refresh_map_list(select_code=current_map)
            self._set_status("保存成功，备份：%s" % backup_path)
            self.saved.emit(backup_path)
            return True
        except Exception as exc:
            self._set_status("保存失败：%s" % exc)
            QtWidgets.QMessageBox.critical(self, "保存失败", str(exc))
            return False

    def _set_status(self, text: str) -> None:
        self.status_label.setText(str(text))
        self.statusChanged.emit(str(text))


__all__ = [
    "VisualSpawnPage",
    "MapEntry",
    "SpawnRecord",
    "TextDocument",
    "load_map_entries",
    "load_spawn_document",
    "parse_map_grid",
    "build_map_image",
    "save_spawn_document",
    "serialize_spawn_document",
]
