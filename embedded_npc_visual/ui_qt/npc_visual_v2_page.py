from __future__ import annotations

import contextlib
import hashlib
import os
import re
import secrets
import sqlite3
import threading
from dataclasses import replace
from functools import partial
from pathlib import Path, PureWindowsPath
from typing import Any, Iterable, Mapping

from PySide2.QtCore import QEvent, QMimeData, Qt, QRectF, QTimer, QPoint, QSize
from PySide2.QtGui import QColor, QBrush, QCursor, QDrag, QFont, QIcon, QImage, QKeySequence, QPainter, QPen, QPixmap, QTextCursor
from PySide2.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QMenu,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSlider,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from atomic_target_commit import atomic_restore_bytes, protected_target, target_identity, write_exclusive
from toolbox_native_asset_worker import NativeAssetWorkerError
from toolbox_native_core import build_npc_item_tooltip, open_local_npc_tooltip_data
from toolbox_target_scope import compute_target_scope_sha256

from embedded_npc_visual.core.npc_visual_v2 import LayoutComponent, LayoutDocument, NpcDocument, NpcVisualEngine, SourceRef
from embedded_npc_visual.core.npc_visual_v2.rpc_codec import npc_document_from_rpc
from embedded_npc_visual.core.npc_visual_v2.colors import NPC_COLOR_TABLE
from embedded_npc_visual.core.npc_visual_v2.components import EDITABLE_COORDINATE_INDEXES, PIXMAP_COMPONENT_KINDS
from embedded_npc_visual.core.npc_visual_v2.edit import DeleteComponentOperation, InsertComponentOperation, MoveComponentOperation, UndoStack
from embedded_npc_visual.core.npc_visual_v2.monster_frames import monster_frame_sequence
from embedded_npc_visual.core.npc_visual_v2.resources import ResourceImage, ResourceProvider
from embedded_npc_visual.core.npc_visual_v2.resources.asset_providers import (
    AssetAuthorizationSnapshot,
    NativeAssetAuthorizationError,
    NativeAssetReadGate,
)
from embedded_npc_visual.ui_qt.npc_visual_support import (
    LOCAL_STORE_IMPORT_ERROR,
    NpcToolContext,
    _error_text,
    _load_record_image,
    _load_thumbnail_batch,
    _pil_to_pixmap,
    connect_local_store,
)

try:
    from embedded_npc_visual.core.dbc_reader import DbcTable
except Exception:
    DbcTable = None

try:
    from PIL import Image, ImageChops
except BaseException:
    Image = None
    ImageChops = None

try:
    from PIL.ImageQt import ImageQt
except BaseException:
    ImageQt = None

from toolbox_core_rpc import CoreRpcError, parse_npc_document_rpc

NPC_V2_COMPONENT_MIME = "application/x-legendary-npc-v2-component"
NPC_V2_RESOURCE_DETAIL_MIME = "application/x-legendary-npc-v2-resource-detail"
_CALL_RE = re.compile(r"^\s*#CALL\s+\[(?P<path>[^\]]+)\]\s+(?P<label>@\S+)", re.IGNORECASE | re.MULTILINE)
_LABEL_HEADER_RE = re.compile(r"^\s*\[(?P<label>@[^\]]+)\]\s*$", re.IGNORECASE | re.MULTILINE)
_CALL_EXPANDED_MARKER = "; ---- #CALL "
_COMPONENT_PIXMAP_CACHE_LIMIT = 512
_RESOURCE_DETAIL_LOAD_TIMEOUT_MS = 45_000
_PIXMAP_COMPONENT_KINDS = PIXMAP_COMPONENT_KINDS
_RESOURCE_RECORD_FILE_SUFFIXES = {".pak", ".wzl", ".wil", ".wis"}
_RESOURCE_RECORD_INDEX_SUFFIXES = {".wix", ".wzx"}
_RESOURCE_PROBE_READABLE = "readable"
_RESOURCE_PROBE_UNVERIFIABLE = "unverifiable"
_RESOURCE_PROBE_LOCKED = "locked"
_RESOURCE_PROBE_ERROR = "error"
_STR_REF_RE = re.compile(r"<\$\s*STR\((?P<name>[^)]+)\)>", re.IGNORECASE)
_MOV_ASSIGN_RE = re.compile(r"^\s*mov\s+(?P<name>\S+)(?:\s+(?P<value>.*?))?\s*$", re.IGNORECASE)
_ITEMSHOW_STR_ID_RE = re.compile(
    r"<\s*ItemShow\s*:\s*<\$\s*STR\((?P<name>[^)]+)\)>",
    re.IGNORECASE,
)
_GET_DB_ITEM_FIELD_RE = re.compile(
    r"^\s*GetDBItemFieldValue\s+(?P<item>.+?)\s+(?P<field>\S+)\s+"
    r"<\$\s*STR\((?P<name>[^)]+)\)>\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_RUNTIME_ARG_COMPONENT_KINDS = {
    "img", "imgex", "playimg", "playimgex", "monster", "itemshow",
    "itembox", "progressbar", "layout", "listview",
}
_XY_COMPONENT_ARG_INDEXES = EDITABLE_COORDINATE_INDEXES
_COMPONENT_LIBRARY = (('普通文本', '<普通文本/SCOLOR=251>'),
 ('文本标签', '<Text:文本标签|提示:0:0{FCOLOR=250;FSIZE=14;FNAME=黑体}/@测试>'),
 ('多行文本', '<MText:0:0:255:多行文本>'),
 ('IMG', '<Img:-1:-1:0:0:*/@Label>'),
 ('IMGEX', '<ImgEx:-1:-1:-1:-1:0:0:*/@Label>'),
 ('PlayImg', '<PlayImg:-1:-1:1:100:0:0:0:备注文字内容:*/@Label>'),
 ('PlayImgEx', '<PlayImgEx:-1:-1:1:100:0:0:0:0:备注文字内容:*/@Label>'),
 ('Monster', '<Monster:0:0:1:0:0:0>'),
 ('ItemShow', '<ItemShow:0:0:0:0:0:0:0/@Label>'),
 ('ITEMBOX', '<ITEMBOX:0:-1:-1:0:0:36:36:*:未放入装备>'),
 ('ProgressBar', '<ProgressBar:0:0:-1:-1:-1:1:100:0:0:0:100:50:0:250:0:0:50%:进度条>'),
 ('文本写入框', '<INPUTTEXT:1:0:0:80:15:0:249:255:4:10:姓名必须在4-10位长:输入姓名:160>'),
 ('数字写入框', '<INPUTNUM:2:0:2:80:15:0:249:255:1:100:年龄必须输入1-100之间的数字:输入年龄:160>'),
 ('文本输入弹框', '<文本输入弹框|0#/@@InputString0()>'),
 ('数字输入弹框', '<数字输入弹框|0#/@@InPutInteger0()>'))
_GOM_COMPONENT_TAGS = {'PLAYIMG', 'PLAYIMGEX', 'MONSTER', 'IMG', 'ITEMBOX', 'PROGRESSBAR', 'MTEXT', 'TEXT', 'INPUTSTRING_POPUP', 'IMGEX', 'ITEMSHOW', 'INPUTINTEGER_POPUP'}
def _normalize_call_path(path: str) -> str:
    value = str(path or "").strip().strip("\"'")
    value = value.replace("/", "\\")
    while "\\\\" in value:
        value = value.replace("\\\\", "\\")
    value = value.lstrip("\\/")
    parts = []
    for part in value.split("\\"):
        if not part or part == ".":
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)

def _is_spacer_component(component: LayoutComponent) -> bool:
    if bool(component.node.props.get("hidden_placeholder")):
        return True
    if component.node.kind != "text":
        return False
    if component.node.text.strip():
        return False
    raw = component.node.raw
    if raw.startswith("<") and raw.endswith(">"):
        return raw[1:-1].strip() == ""
    return raw.strip() == ""

def _is_decorative_text_component(component: LayoutComponent) -> bool:
    return component.node.kind == "text" and bool(component.node.props.get("decorative_text"))

def _component_library_tag(tag: str) -> str:
    text = str(tag or "").strip()
    lower = text.casefold()
    if lower.startswith("<imgex:"):
        return "IMGEX"
    if lower.startswith("<img:"):
        return "IMG"
    if lower.startswith("<playimg:"):
        return "PLAYIMG"
    if lower.startswith("<playimgex:"):
        return "PLAYIMGEX"
    if lower.startswith("<monster:"):
        return "MONSTER"
    if lower.startswith("<itemshow:"):
        return "ITEMSHOW"
    if lower.startswith("<itembox:"):
        return "ITEMBOX"
    if lower.startswith("<progressbar:"):
        return "PROGRESSBAR"
    if lower.startswith("<mtext:"):
        return "MTEXT"
    if lower.startswith("<inputtext:"):
        return "INPUTTEXT"
    if lower.startswith("<inputnum:"):
        return "INPUTNUM"
    if lower.startswith("<text:"):
        return "LABEL"
    if "@@inputstring" in lower:
        return "INPUTSTRING_POPUP"
    if "@@inputinteger" in lower:
        return "INPUTINTEGER_POPUP"
    return "TEXT"


def _uses_transparent_effect_mode(node: Any) -> bool:
    kind = str(getattr(node, "kind", "") or "").casefold()
    args = getattr(node, "props", {}).get("args")
    if not isinstance(args, list):
        return False
    mode_index = 6 if kind == "playimg" else 7 if kind == "playimgex" else None
    if mode_index is None or len(args) <= mode_index:
        return False
    try:
        return int(str(args[mode_index]).strip()) == 1
    except (TypeError, ValueError):
        return False

def _component_library_for_engine(engine_family: str) -> tuple[tuple[str, str], ...]:
    if str(engine_family or "").casefold() == "gom":
        return tuple((item for item in _COMPONENT_LIBRARY if _component_library_tag(item[1]) in _GOM_COMPONENT_TAGS))
    return _COMPONENT_LIBRARY

def _placeholder_icon(size: QSize, title: str = '') -> QIcon:
    pixmap = QPixmap(size)
    pixmap.fill(QColor("#f3f5f8"))
    painter = QPainter(pixmap)
    painter.setPen(QPen(QColor("#b7c0cc"), 1))
    painter.drawRect(0, 0, size.width() - 1, size.height() - 1)
    if title:
        painter.setPen(QColor("#7d8794"))
        painter.drawText(pixmap.rect(), Qt.AlignCenter, title)
    painter.end()
    return QIcon(pixmap)


_RESOURCE_DETAIL_ICON_EXTENT = 64
_RESOURCE_DETAIL_CONTENT_EXTENT = 60


def _resource_detail_thumbnail_pixmap(source: QPixmap) -> QPixmap:
    """Center native-size art; only oversized art is resampled."""
    if source is None or source.isNull():
        return QPixmap()
    content = source
    if (
        source.width() > _RESOURCE_DETAIL_CONTENT_EXTENT
        or source.height() > _RESOURCE_DETAIL_CONTENT_EXTENT
    ):
        content = source.scaled(
            QSize(
                _RESOURCE_DETAIL_CONTENT_EXTENT,
                _RESOURCE_DETAIL_CONTENT_EXTENT,
            ),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
    canvas = QPixmap(
        QSize(_RESOURCE_DETAIL_ICON_EXTENT, _RESOURCE_DETAIL_ICON_EXTENT)
    )
    canvas.fill(Qt.transparent)
    painter = QPainter(canvas)
    painter.drawPixmap(
        (canvas.width() - content.width()) // 2,
        (canvas.height() - content.height()) // 2,
        content,
    )
    painter.end()
    return canvas


class _ComponentPaletteList(QListWidget):
    def startDrag(self, _supported_actions: Any) -> None:
        item = self.currentItem()
        if item is None:
            return
        tag = str(item.data(Qt.UserRole) or "")
        if not tag:
            return
        mime = QMimeData()
        mime.setData(NPC_V2_COMPONENT_MIME, tag.encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec_(Qt.CopyAction)


class _ResourceDetailList(QListWidget):
    _COLUMN_COUNT = 3
    _CELL_HEIGHT = 96

    def __init__(self, page: 'NpcVisualV2Page') -> None:
        super().__init__()
        self.page = page

    def _sync_column_grid(self) -> None:
        viewport_width = max(0, self.viewport().width())
        spacing = max(0, self.spacing())
        usable_width = max(0, viewport_width - spacing * (self._COLUMN_COUNT + 1) - 2)
        cell_width = max(56, usable_width // self._COLUMN_COUNT)
        target = QSize(cell_width, self._CELL_HEIGHT)
        if self.gridSize() != target:
            self.setGridSize(target)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        self._sync_column_grid()
        self.page._schedule_resource_detail_thumbnail_refresh()

    def startDrag(self, _supported_actions: Any) -> None:
        items = list(self.selectedItems())
        if not items and self.currentItem() is not None:
            items = [self.currentItem()]
        tag = self.page._resource_detail_drag_tag(items)
        if not tag:
            return
        mime = QMimeData()
        mime.setData(NPC_V2_COMPONENT_MIME, tag.encode("utf-8"))
        mime.setData(NPC_V2_RESOURCE_DETAIL_MIME, b"1")
        drag = QDrag(self)
        drag.setMimeData(mime)
        anchor = self.currentItem() or items[0]
        pixmap = anchor.icon().pixmap(self.iconSize())
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(0, 0))
        drag.exec_(Qt.CopyAction)


class _ResourcePreviewDialog(QDialog):
    def __init__(self, pixmap: QPixmap, title: str, previous: Any, next_: Any, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("npcV2ResourcePreviewDialog")
        self.setWindowTitle(title)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.original_pixmap = pixmap
        self.zoom_factor = 1.0
        self.fit_to_window = True

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)
        self.title_label = QLabel(title)
        self.title_label.setToolTip(title)
        layout.addWidget(self.title_label)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        self.previous_button = QPushButton("上一张")
        self.previous_button.setFixedWidth(64)
        self.previous_button.clicked.connect(previous)
        toolbar.addWidget(self.previous_button)
        self.next_button = QPushButton("下一张")
        self.next_button.setFixedWidth(64)
        self.next_button.clicked.connect(next_)
        toolbar.addWidget(self.next_button)
        toolbar.addStretch(1)
        zoom_out = QPushButton("-")
        zoom_out.setFixedSize(30, 28)
        zoom_out.setToolTip("缩小")
        zoom_out.clicked.connect(lambda: self._set_zoom(self.zoom_factor / 1.25))
        toolbar.addWidget(zoom_out)
        fit_button = QPushButton("适应窗口")
        fit_button.setFixedWidth(76)
        fit_button.clicked.connect(self._fit_pixmap)
        toolbar.addWidget(fit_button)
        actual_button = QPushButton("100%")
        actual_button.setFixedWidth(62)
        actual_button.clicked.connect(lambda: self._set_zoom(1.0))
        toolbar.addWidget(actual_button)
        zoom_in = QPushButton("+")
        zoom_in.setFixedSize(30, 28)
        zoom_in.setToolTip("放大")
        zoom_in.clicked.connect(lambda: self._set_zoom(self.zoom_factor * 1.25))
        toolbar.addWidget(zoom_in)
        self.zoom_label = QLabel("100%")
        self.zoom_label.setMinimumWidth(48)
        self.zoom_label.setAlignment(Qt.AlignCenter)
        toolbar.addWidget(self.zoom_label)
        layout.addLayout(toolbar)

        self.scroll_area = QScrollArea()
        self.scroll_area.setAlignment(Qt.AlignCenter)
        self.scroll_area.setWidgetResizable(False)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet("background: #171b22;")
        self.scroll_area.setWidget(self.preview_label)
        layout.addWidget(self.scroll_area, 1)
        self.resize(760, 600)
        QTimer.singleShot(0, self._fit_pixmap)

    def set_preview(self, pixmap: QPixmap, title: str, can_previous: bool, can_next: bool) -> None:
        self.original_pixmap = pixmap
        self.setWindowTitle(title)
        self.title_label.setText(title)
        self.title_label.setToolTip(title)
        self.previous_button.setEnabled(can_previous)
        self.next_button.setEnabled(can_next)
        QTimer.singleShot(0, self._fit_pixmap)

    def _set_zoom(self, factor: float) -> None:
        self.fit_to_window = False
        self.zoom_factor = max(0.1, min(8.0, float(factor)))
        size = self.original_pixmap.size() * self.zoom_factor
        # Nearest-neighbour keeps pixel art crisp when magnifying;
        # smoothing still reads better when shrinking.
        zoom_mode = (
            Qt.FastTransformation
            if self.zoom_factor >= 1.0
            else Qt.SmoothTransformation
        )
        scaled = self.original_pixmap.scaled(size, Qt.KeepAspectRatio, zoom_mode)
        self.preview_label.setPixmap(scaled)
        self.preview_label.resize(scaled.size())
        self.zoom_label.setText(f"{round(self.zoom_factor * 100)}%")

    def _fit_pixmap(self) -> None:
        viewport_size = self.scroll_area.viewport().size()
        if viewport_size.width() <= 1 or viewport_size.height() <= 1:
            return
        self.fit_to_window = True
        fit_mode = (
            Qt.FastTransformation
            if viewport_size.width() >= self.original_pixmap.width()
            else Qt.SmoothTransformation
        )
        scaled = self.original_pixmap.scaled(
            viewport_size, Qt.KeepAspectRatio, fit_mode
        )
        self.preview_label.setPixmap(scaled)
        self.preview_label.resize(scaled.size())
        width_ratio = scaled.width() / max(1, self.original_pixmap.width())
        height_ratio = scaled.height() / max(1, self.original_pixmap.height())
        self.zoom_factor = min(width_ratio, height_ratio)
        self.zoom_label.setText(f"{round(self.zoom_factor * 100)}%")

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if self.fit_to_window:
            QTimer.singleShot(0, self._fit_pixmap)

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Left and self.previous_button.isEnabled():
            self.previous_button.click()
            event.accept()
            return
        if event.key() == Qt.Key_Right and self.next_button.isEnabled():
            self.next_button.click()
            event.accept()
            return
        super().keyPressEvent(event)


class _NpcCanvasView(QGraphicsView):
    def __init__(self, page: 'NpcVisualV2Page', scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.page = page
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAlignment(Qt.AlignCenter)

    def _canvas_point(self, event_pos: QPoint | None = None, event: Any | None = None) -> tuple[int, int, str]:
        viewport = self.viewport()
        global_pos = None
        global_getter = getattr(event, "globalPos", None) if event is not None else None
        if callable(global_getter):
            try:
                global_pos = global_getter()
            except Exception:
                global_pos = None
        if global_pos is None:
            global_pos = QCursor.pos()
        viewport_pos = viewport.mapFromGlobal(global_pos)
        event_text = "无"
        if event_pos is not None:
            event_text = f"{int(event_pos.x())},{int(event_pos.y())}"
            if not viewport.rect().contains(viewport_pos):
                if self.rect().contains(event_pos):
                    viewport_pos = viewport.mapFrom(self, event_pos)

        scene_point = self.mapToScene(viewport_pos)
        rect = self.sceneRect()
        canvas_x = int(round(scene_point.x() - rect.left()))
        canvas_y = int(round(scene_point.y() - rect.top()))
        debug = f"拖放坐标：event={event_text}；global={int(global_pos.x())},{int(global_pos.y())}；viewport={int(viewport_pos.x())},{int(viewport_pos.y())}；scene={scene_point.x():.2f},{scene_point.y():.2f}；canvas={canvas_x},{canvas_y}；sceneRect={rect.left():.2f},{rect.top():.2f},{rect.width():.2f}x{rect.height():.2f}"
        return (
         canvas_x, canvas_y, debug)

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat(NPC_V2_COMPONENT_MIME):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat(NPC_V2_COMPONENT_MIME):
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event: Any) -> None:
        if not event.mimeData().hasFormat(NPC_V2_COMPONENT_MIME):
            super().dropEvent(event)
            return
        tag = bytes(event.mimeData().data(NPC_V2_COMPONENT_MIME)).decode("utf-8", errors="ignore")
        x, y, debug = self._canvas_point(event.pos(), event)
        self.page.insert_component_tag(
            tag,
            x,
            y,
            pointer_debug=debug,
            exact_coordinates=event.mimeData().hasFormat(NPC_V2_RESOURCE_DETAIL_MIME),
        )
        event.acceptProposedAction()

    def keyPressEvent(self, event: Any) -> None:
        if event.matches(QKeySequence.SelectAll):
            self.page.select_all_components()
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self.page.clear_component_selection()
            event.accept()
            return
        if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
            self.page.delete_selected_components()
            event.accept()
            return
        if self.page.handle_keyboard_move_key(event):
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Control:
            self.page.commit_keyboard_move()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def wheelEvent(self, event: Any) -> None:
        if event.modifiers() & Qt.ControlModifier:
            delta = int(event.angleDelta().y())
            if delta:
                self.page.zoom_canvas_by(10 if delta > 0 else -10)
                event.accept()
                return
        x, y, _debug = self._canvas_point(event.pos(), event)
        if self.page.scroll_listview_at(x, y, int(event.angleDelta().y())):
            event.accept()
            return
        super().wheelEvent(event)

    def resizeEvent(self, event: Any) -> None:
        super().resizeEvent(event)
        if not getattr(self.page, "_canvas_manual_zoom", False):
            self.page.fit_canvas_to_view()


class _NpcV2TooltipOverlay(QWidget):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("npcV2TooltipOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.hide()
        self.lines = []
        self.padding_x = 12
        self.padding_y = 9
        self.line_gap = 3
        self._transparent_background = False
        self._content_key = None

    def show_component(
        self,
        component: LayoutComponent,
        global_pos: QPoint,
        *,
        raw_tip: str | None = None,
        default_code: str | None = None,
        transparent_background: bool = False,
    ) -> None:
        component_raw, component_default_code = self._component_tip(component)
        raw = component_raw if raw_tip is None else str(raw_tip)
        default_code = str(default_code or component_default_code or "250")
        if not raw:
            self.hide()
            return
        raw, default_code = self._extract_default_color(raw, default_code)
        content_key = (raw, default_code, bool(transparent_background))
        if content_key != self._content_key:
            self.lines = self._parse_lines(raw, self._color_from_code(default_code))
            if not self.lines:
                self.hide()
                return
            parent = self.parentWidget()
            parent_width = parent.width() if parent is not None else 460
            max_content_width = max(
                80,
                min(420, parent_width - self.padding_x * 2 - 24),
            )
            self.lines = self._wrap_lines(self.lines, max_content_width)
            self._limit_height_to_parent()
            self._transparent_background = bool(transparent_background)
            self._content_key = content_key
            self._resize_to_content()
            self.update()
        self.move_near(global_pos)
        self.show()
        self.raise_()

    def move_near(self, global_pos: QPoint) -> None:
        parent = self.parentWidget()
        if parent is not None:
            local = parent.mapFromGlobal(global_pos)
            x = local.x() + 14
            y = local.y() + 18
            if x + self.width() > parent.width() - 4:
                x = max(4, local.x() - self.width() - 14)
            if y + self.height() > parent.height() - 4:
                y = max(4, local.y() - self.height() - 14)
            self.move(x, y)

    def _component_tip(self, component: LayoutComponent) -> tuple[str, str]:
        node = component.node
        props = node.props or {}
        tip = str(props.get("tip", "") or props.get("tooltip", "") or "").strip()
        default_code = str(props.get("tooltip_color", "") or "250")
        if not tip:
            if node.kind == "itembox":
                args = props.get("args")
                if isinstance(args, list):
                    if len(args) >= 9:
                        tip = str(args[8] or "").strip()
        return (tip, default_code)

    def _extract_default_color(self, raw: str, default_code: str) -> tuple[str, str]:
        match = re.match("^\\s*(?P<code>\\d{1,3})#(?P<text>.*)$", raw, re.DOTALL)
        if match:
            return (match.group("text"), match.group("code"))
        return (raw, default_code)

    def _parse_lines(self, raw: str, default_color: QColor) -> list[tuple[list[tuple[str, QColor]], bool]]:
        lines = []
        color = default_color
        separator = False
        text = ""
        index = 0
        while index < len(raw):
            char = raw[index]
            if char in "\r\n":
                lines.append((self._parse_segments(text, color), separator))
                text = ""
                separator = False
                if char == "\r" and index + 1 < len(raw) and raw[index + 1] == "\n":
                    index += 2
                else:
                    index += 1
                color_match = re.match("(?P<code>\\d{1,3})#", raw[index:])
                if color_match:
                    color = self._color_from_code(color_match.group("code"))
                    index += color_match.end()
                continue
            if char != "^":
                text += char
                index += 1
            else:
                lines.append((self._parse_segments(text, color), separator))
                text = ""
                separator = False
                index += 1
                if index < len(raw):
                    if raw[index] == "-":
                        separator = True
                        index += 1
                        if index < len(raw):
                            if raw[index] == "^":
                                index += 1
                color_match = re.match("(?P<code>\\d{1,3})#", raw[index:])
                if color_match:
                    color = self._color_from_code(color_match.group("code"))
                    index += color_match.end()

        lines.append((self._parse_segments(text, color), separator))
        return [(segments, line_separator) for segments, line_separator in lines if segments or line_separator]

    def _parse_segments(self, text: str, default_color: QColor) -> list[tuple[str, QColor]]:
        segments = []
        position = 0
        for match in re.finditer("\\{(?P<text>[^{}|]*)\\|(?P<code>\\d{1,3})\\}", text):
            if match.start() > position:
                segments.append((text[position:match.start()], default_color))
            segment_text = match.group("text")
            if segment_text:
                segments.append((segment_text, self._color_from_code(match.group("code"))))
            position = match.end()

        if position < len(text):
            segments.append((text[position:], default_color))
        return [(segment_text, color) for segment_text, color in segments if segment_text]

    def _color_from_code(self, code: str) -> QColor:
        try:
            index = int(str(code).strip())
        except (TypeError, ValueError):
            index = 250
        if index == 300:
            return QColor("#9a332e")
        if 0 <= index < len(NPC_COLOR_TABLE):
            r, g, b, a = NPC_COLOR_TABLE[index]
            return QColor(int(r), int(g), int(b), int(a))
        return QColor("#00ff00")

    def _wrap_lines(
        self,
        lines: list[tuple[list[tuple[str, QColor]], bool]],
        max_width: int,
    ) -> list[tuple[list[tuple[str, QColor]], bool]]:
        metrics = self.fontMetrics()
        wrapped = []
        for segments, separator in lines:
            current_segments = []
            current_width = 0
            first_line = True
            for text, color in segments:
                for char in text:
                    char_width = max(1, metrics.horizontalAdvance(char))
                    if current_segments and current_width + char_width > max_width:
                        wrapped.append((current_segments, separator if first_line else False))
                        current_segments = []
                        current_width = 0
                        first_line = False
                    if current_segments and current_segments[-1][1] == color:
                        previous_text, previous_color = current_segments[-1]
                        current_segments[-1] = (previous_text + char, previous_color)
                    else:
                        current_segments.append((char, QColor(color)))
                    current_width += char_width
            if current_segments or separator:
                wrapped.append((current_segments, separator if first_line else False))
        return wrapped

    def _limit_height_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None or not self.lines:
            return
        metrics = self.fontMetrics()
        usable_height = max(30, parent.height() - 16 - self.padding_y * 2)
        line_height = max(1, metrics.height() + self.line_gap)
        max_lines = max(1, usable_height // line_height)
        if len(self.lines) <= max_lines:
            return
        self.lines = self.lines[:max_lines]
        self.lines[-1] = ([('...', self._color_from_code('255'))], False)

    def _resize_to_content(self) -> None:
        metrics = self.fontMetrics()
        width = 0
        height = self.padding_y * 2
        for segments, separator in self.lines:
            line_width = sum((metrics.horizontalAdvance(text) for text, _color in segments))
            width = max(width, line_width)
            if separator:
                height += 7
            height += metrics.height() + self.line_gap

        height = max(30, height - self.line_gap)
        width = max(48, width + self.padding_x * 2)
        self.resize(width, height)

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        rect = self.rect().adjusted(0, 0, -1, -1)
        if not self._transparent_background:
            painter.fillRect(rect, QColor(8, 8, 6, 235))
            painter.setPen(QPen(QColor("#3d2a0a"), 1))
            painter.drawRect(rect)
            painter.setPen(QPen(QColor("#d0a94d"), 1))
            painter.drawRect(rect.adjusted(2, 2, -2, -2))
            painter.setPen(QPen(QColor("#6d4a16"), 1))
            painter.drawRect(rect.adjusted(4, 4, -4, -4))
        y = self.padding_y
        metrics = painter.fontMetrics()
        for segments, separator in self.lines:
            if separator:
                line_y = y + 1
                painter.setPen(QPen(QColor("#8c6422"), 1))
                painter.drawLine(self.padding_x - 2, line_y, self.width() - self.padding_x + 2, line_y)
                y += 7
            x = self.padding_x
            for text, color in segments:
                if self._transparent_background:
                    painter.setPen(QColor(0, 0, 0, 230))
                    painter.drawText(x + 1, y + metrics.ascent() + 1, text)
                painter.setPen(color)
                painter.drawText(x, y + metrics.ascent(), text)
                x += metrics.horizontalAdvance(text)

            y += metrics.height() + self.line_gap

        painter.end()


class _GameTextItem(QGraphicsItem):
    ASCII_ADVANCE = 6
    WIDE_ADVANCE = 11
    def __init__(self, text: str, color: QColor, width: int, height: int, font: QFont, parent: QGraphicsItem | None = None) -> None:
        super().__init__(parent)
        self.text = text.replace("\r\n", "\n").replace("\r", "\n")
        self.color = QColor(color)
        self.width = max(1, int(width))
        self.height = max(1, int(height))
        self.font = QFont(font)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        painter.setClipRect(self.boundingRect())
        painter.setRenderHint(QPainter.TextAntialiasing, False)
        painter.setPen(self.color)
        painter.setFont(self.font)
        metrics = painter.fontMetrics()
        line_height = max(1, metrics.height())
        x = 0
        y = 0
        for char in self.text:
            if char == "\n":
                x = 0
                y += line_height
                continue
            advance = self._advance(char)
            if char == "\t":
                x += advance * 4
                continue
            baseline = min(max(1, self.height - 1), y + metrics.ascent())
            if not char.isspace():
                char_width = max(1, metrics.horizontalAdvance(char))
                scale_x = min(1.0, advance / char_width)
                painter.save()
                painter.translate(x, y)
                if scale_x < 1.0:
                    painter.scale(scale_x, 1.0)
                painter.drawText(0, int(metrics.ascent()), char)
                painter.restore()
            else:
                painter.drawText(int(x), int(baseline), char)
            x += advance

    def _advance(self, char: str) -> int:
        if ord(char) > 127:
            return self.WIDE_ADVANCE
        return self.ASCII_ADVANCE


class _AdditivePixmapItem(QGraphicsPixmapItem):
    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        painter.save()
        painter.setCompositionMode(QPainter.CompositionMode_Plus)
        painter.drawPixmap(0, 0, self.pixmap())
        painter.restore()


class _VisualComponentItem(QGraphicsRectItem):
    def __init__(self, page: 'NpcVisualV2Page', component: LayoutComponent, pixmap: QPixmap | None = None, image_origin: tuple[int, int] = (0, 0)) -> None:
        width = max(component.visual_rect.width, pixmap.width() + max(0, image_origin[0]) if pixmap is not None else 0)
        height = max(component.visual_rect.height, pixmap.height() + max(0, image_origin[1]) if pixmap is not None else 0)
        super().__init__(0, 0, width, height)
        self.page = page
        self.component = component
        self.pixmap = pixmap
        self.pixmap_item = None
        self.image_origin = image_origin
        self.show_frame = False
        self._press_item_pos = None
        self.setPos(component.visual_rect.x, component.visual_rect.y)
        self.setZValue(component.z_index)
        if _is_decorative_text_component(component):
            self.setFlags(QGraphicsRectItem.GraphicsItemFlags())
            self.setAcceptedMouseButtons(Qt.NoButton)
            self.setAcceptHoverEvents(False)
        else:
            self.setFlags(QGraphicsRectItem.ItemIsSelectable | QGraphicsRectItem.ItemIsMovable | QGraphicsRectItem.ItemSendsGeometryChanges)
            self.setAcceptHoverEvents(True)
        self._apply_style(False)
        self._add_pixmap()
        self._add_label()
        self.setToolTip("")

    def _apply_style(self, selected: bool) -> None:
        if _is_decorative_text_component(self.component):
            self.setPen(QPen(Qt.NoPen))
            self.setBrush(QBrush(QColor(255, 255, 255, 0)))
            return
        if selected:
            pen = QPen(QColor("#ffd400"), 1)
        elif self.show_frame:
            pen = QPen(QColor("#ff3030"), 1)
        else:
            pen = QPen(Qt.NoPen)
        if self.component.node.kind in _PIXMAP_COMPONENT_KINDS:
            if pen.style() != Qt.NoPen:
                pen.setStyle(Qt.DashLine)
        self.setPen(pen)
        self.setBrush(QBrush(QColor(255, 255, 255, 0)))

    def _add_label(self) -> None:
        node = self.component.node
        if self.component.node.kind in _PIXMAP_COMPONENT_KINDS:
            return
        text = str(node.text or "")
        if not text:
            text = node.kind
        if node.kind == "mtext":
            text = re.sub(r"\|[ \t]*\r?\n", "\n", text)
            text = text.replace("|", "\n")
        if node.kind in _PIXMAP_COMPONENT_KINDS:
            text = node.kind.upper()
        font = QFont("SimSun")
        font.setPixelSize(11)
        font.setUnderline(node.kind == "link")
        child = _GameTextItem(text, self._text_color(node), max(1, self.component.visual_rect.width), max(1, self.component.visual_rect.height), font, self)
        child.setPos(0, 0)

    def _add_pixmap(self) -> None:
        if self.pixmap is None:
            return
        item_type = _AdditivePixmapItem if _uses_transparent_effect_mode(self.component.node) else QGraphicsPixmapItem
        self.pixmap_item = item_type(self.pixmap, self)
        self.pixmap_item.setPos(self.image_origin[0], self.image_origin[1])
        self.pixmap_item.setZValue(-1)

    def update_pixmap(self, pixmap: QPixmap, image_origin: tuple[int, int] = (0, 0)) -> None:
        self.pixmap = pixmap
        self.image_origin = image_origin
        if self.pixmap_item is None:
            self.pixmap_item = QGraphicsPixmapItem(pixmap, self)
            self.pixmap_item.setZValue(-1)
        else:
            self.pixmap_item.setPixmap(pixmap)
        self.pixmap_item.setPos(image_origin[0], image_origin[1])

    def _text_color(self, node: Any) -> QColor:
        color_value = self._node_color_value(node)
        if color_value:
            color = self._color_from_code(color_value)
            if color is not None:
                return color
        kind = str(getattr(node, "kind", "") or "")
        if kind == "link":
            return QColor("#fff200")
        if kind in _PIXMAP_COMPONENT_KINDS:
            return QColor("#00ff66")
        return QColor("#ffffff")

    def _node_color_value(self, node: Any) -> str:
        props = getattr(node, "props", {}) or {}
        for key in ('color', 'FCOLOR', 'SCOLOR', 'AUTOCOLOR', 'fcolor', 'scolor', 'autocolor'):
            value = props.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""

    def _color_from_code(self, value: str) -> QColor | None:
        try:
            index = int(str(value).strip().split(",", 1)[0])
        except Exception:
            return
        else:
            if 0 <= index < len(NPC_COLOR_TABLE):
                r, g, b, a = NPC_COLOR_TABLE[index]
                return QColor(int(r), int(g), int(b), int(a))

    def mousePressEvent(self, event: Any) -> None:
        self.page.hide_component_tooltip()
        self.page.view.setFocus()
        self._press_item_pos = (int(self.pos().x()), int(self.pos().y()))
        additive = bool(event.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier))
        if not additive:
            preserve = self.isSelected() and len(self.page._selected_visual_items()) > 1
            self.page.select_component(
                self.component,
                jump_source=True,
                preserve_selection=preserve,
            )
        super().mousePressEvent(event)
        if additive and self.isSelected():
            self.page.select_component(
                self.component,
                jump_source=True,
                preserve_selection=True,
            )
        self.page._prepare_component_drag(self)

    def hoverEnterEvent(self, event: Any) -> None:
        self.page.show_component_tooltip(self.component, event.screenPos())
        super().hoverEnterEvent(event)

    def hoverMoveEvent(self, event: Any) -> None:
        self.page.move_component_tooltip(event.screenPos())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: Any) -> None:
        self.page.hide_component_tooltip()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        page = self.page
        component = self.component
        page.select_component(component, jump_source=True, focus_source=True)
        super().mouseDoubleClickEvent(event)
        QTimer.singleShot(0, lambda: page.activate_component(component))

    def contextMenuEvent(self, event: Any) -> None:
        self.page.select_component(
            self.component,
            jump_source=True,
            preserve_selection=self.isSelected(),
        )
        selected_count = len(self.page._selected_visual_items())
        menu = QMenu()
        delete_action = menu.addAction(f"删除所选 ({selected_count})" if selected_count > 1 else "删除")
        action = menu.exec_(event.screenPos())
        if action == delete_action:
            if selected_count > 1:
                self.page.delete_selected_components()
            else:
                self.page.delete_component(self.component)
            event.accept()
            return
        super().contextMenuEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        super().mouseReleaseEvent(event)
        pos = self.pos()
        current_pos = (int(pos.x()), int(pos.y()))
        moved = self._press_item_pos is not None and current_pos != self._press_item_pos
        self._press_item_pos = None
        if self.page._finish_component_drag(self):
            return
        if moved:
            self.page.component_moved(self.component, current_pos[0], current_pos[1])
            return

    def itemChange(self, change: Any, value: Any) -> Any:
        if change == QGraphicsRectItem.ItemSelectedHasChanged:
            self._apply_style(bool(value))
        return super().itemChange(change, value)


class NpcVisualV2Page(QWidget):
    def __init__(self, parent: QWidget, context: NpcToolContext) -> None:
        super().__init__(parent)
        self.context = context
        self._rpc_parse_auth_context: tuple[str, str, str, str, int] | None = None
        self._resource_auth_context: tuple[str, str, str, str, int] | None = None
        self._resource_auth_generation = 0
        self._rpc_parse_cache: dict[tuple, NpcDocument] = {}
        self._rpc_parse_cache_order: list[tuple] = []
        self._rpc_parse_session_local = threading.local()
        self._rpc_editor_scope_sha256 = hashlib.sha256(secrets.token_bytes(32)).hexdigest()
        self._source_file_identities: dict[str, tuple[int, int, str]] = {}
        self._item_tooltip_cache_lock = threading.RLock()
        self._item_tooltip_authorizations: dict[tuple, dict[str, Any]] = {}
        self._item_tooltip_authorization_waiters: dict[tuple, threading.Event] = {}
        self._item_tooltip_cache: dict[tuple, tuple[dict[str, Any], str]] = {}
        self._item_tooltip_request_token = 0
        self._item_tooltip_context_generation = 0
        self._item_tooltip_hover_pos: QPoint | None = None
        self.engine = NpcVisualEngine(self._parse_document_via_rpc)
        self.npcs = []
        self.filtered_npcs = []
        self.current_entry = None
        self.current_path = ""
        self.current_encoding = ""
        self.primary_source = ""
        self.source_view_path = ""
        self.source_view_encoding = ""
        self.template_mode = False
        self.current_template_name = ""
        self.template_dirty = False
        self.visual_templates = {}
        self._component_palette_engine_last = ""
        self._event_log_messages = []
        self._setting_source_editor_text = False
        self.document = None
        self.layout_document = None
        self.component_items = {}
        self.resource_provider = ResourceProvider(self._native_backend_session)
        self.selected_component_id = ""
        self._syncing_canvas_selection = False
        self._component_drag_anchor_id = ""
        self._component_drag_snapshot = {}
        self._keyboard_move_source = None
        self._keyboard_move_component = None
        self._keyboard_move_target = None
        self._keyboard_group_snapshot = {}
        self.move_operation = MoveComponentOperation()
        self.insert_operation = InsertComponentOperation()
        self.delete_operation = DeleteComponentOperation()
        self.undo_stack = UndoStack()
        self._monster_cache_path = None
        self._monster_cache = {}
        self._main_background_cache_key = None
        self._main_background_cache = None
        self._resource_config_signature = None
        self._parsed_document_cache_key = None
        self._parsed_document_cache = None
        self._pending_edit_document: tuple[str, str, NpcDocument] | None = None
        self._canvas_manual_zoom = True
        self._canvas_zoom_scale = 1.0
        self._call_source_overrides = {}
        self._component_resource_cache = {}
        self._component_pixmap_cache = {}
        self._missing_resource_notices = set()
        self._animated_component_ids = set()
        self._animation_elapsed_ms = 0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(50)
        self._animation_timer.timeout.connect(self._advance_component_animations)
        self._npc_load_token = 0
        self._pending_npc_load = None
        self._npc_load_timer = QTimer(self)
        self._npc_load_timer.setSingleShot(True)
        self._npc_load_timer.setInterval(80)
        self._npc_load_timer.timeout.connect(self._start_pending_npc_load)
        self._render_generation = 0
        self._asset_prewarm_active = False
        self._queued_asset_prewarm_request: tuple[LayoutDocument, int] | None = None
        self.resource_detail_records = []
        self.resource_detail_slots = []
        self.resource_detail_effect_index = 0
        self.resource_detail_file_name = ""
        self.resource_detail_token = 0
        self.resource_detail_request_id = 0
        self.resource_detail_thumb_token = 0
        self.resource_detail_thumb_icons = {}
        self.resource_detail_slot_rows = {}
        self._resource_detail_thumb_active = None
        self._resource_detail_thumb_refresh_pending = False
        self._resource_scan_token = 0
        self.resource_detail_placeholder_icon = _placeholder_icon(QSize(64, 64), "")
        self.resource_preview_dialog = None
        self.resource_preview_position = -1
        self._build_ui()
        self.tooltip_overlay = _NpcV2TooltipOverlay(self)
        self.reload_npcs()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 8)
        root.setSpacing(8)
        header_host = QWidget(self)
        header_host.setObjectName("npcVisualPrimaryActions")
        header = QHBoxLayout(header_host)
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("可视化NPC")
        title.setObjectName("npcV2Title")
        title.setStyleSheet("font-size: 17px; font-weight: 700; color: #162033;")
        self.status_label = QLabel("v2 引擎：等待选择 NPC")
        self.status_label.setStyleSheet("color: #607086;")
        choose_patch_btn = QPushButton("选择游戏客户端")
        choose_patch_btn.clicked.connect(self._choose_patch_folder)
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(132)
        self.template_combo.addItem("选择模板", "")
        save_template_btn = QPushButton("保存模板")
        save_template_btn.clicked.connect(self._save_visual_template)
        new_template_btn = QPushButton("新建模板")
        new_template_btn.clicked.connect(self._new_visual_template)
        import_template_btn = QPushButton("导入布局")
        import_template_btn.clicked.connect(self._import_visual_template_layout)
        self.grid_checkbox = QCheckBox("网格线")
        self.grid_checkbox.setChecked(False)
        self.grid_checkbox.stateChanged.connect(self._grid_state_changed)
        reload_btn = QPushButton("刷新NPC")
        reload_btn.clicked.connect(self.reload_npcs)
        render_btn = QPushButton("重新渲染")
        render_btn.setObjectName("npcVisualRenderButton")
        render_btn.setProperty("buttonRole", "primary")
        render_btn.clicked.connect(self.render_current_source)
        undo_btn = QPushButton("撤回")
        undo_btn.clicked.connect(self.undo)
        redo_btn = QPushButton("恢复")
        redo_btn.clicked.connect(self.redo)
        header.addWidget(title)
        header.addWidget(self.status_label, 1)
        header.addWidget(choose_patch_btn)
        header.addWidget(self.template_combo)
        header.addWidget(save_template_btn)
        header.addWidget(new_template_btn)
        header.addWidget(import_template_btn)
        header.addWidget(self.grid_checkbox)
        header.addWidget(reload_btn)
        header.addWidget(render_btn)
        header.addWidget(undo_btn)
        header.addWidget(redo_btn)
        root.addWidget(header_host)
        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)
        splitter.addWidget(self._build_left_panel())
        splitter.addWidget(self._build_canvas_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setSizes([270, 760, 420])
        self._load_visual_templates()

    def _grid_state_changed(self, _state: int) -> None:
        if self.layout_document is not None:
            self._paint_layout(self.layout_document)

    def _source_editor_text_changed(self) -> None:
        if self._setting_source_editor_text:
            return
        if self.template_mode:
            self.template_dirty = True

    def _set_source_editor_text_programmatically(self, text: str) -> None:
        self._setting_source_editor_text = True
        try:
            self.source_editor.setPlainText(text)
        finally:
            self._setting_source_editor_text = False

    def _template_store_conn(self):
        if connect_local_store is None:
            raise RuntimeError(_error_text(LOCAL_STORE_IMPORT_ERROR))
        conn = connect_local_store()
        conn.execute("\n            CREATE TABLE IF NOT EXISTS visual_npc_templates (\n                id INTEGER PRIMARY KEY AUTOINCREMENT,\n                name TEXT NOT NULL UNIQUE,\n                script TEXT NOT NULL,\n                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,\n                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP\n            )\n            ")
        conn.commit()
        return conn

    def _load_visual_templates(self) -> None:
        if not hasattr(self, "template_combo"):
            return
        self.visual_templates = {}
        current_name = self.current_template_name
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        self.template_combo.addItem("选择模板", "")
        try:
            with self._template_store_conn() as conn:
                rows = conn.execute("SELECT name, script FROM visual_npc_templates ORDER BY name COLLATE NOCASE").fetchall()
            for row in rows:
                name = str(row["name"] if hasattr(row, "keys") else row[0])
                script = str((row["script"] if hasattr(row, "keys") else row[1]) or "")
                self.visual_templates[name] = script
                self.template_combo.addItem(name, name)

        except BaseException as exc:
            self.status_label.setText(f"模板加载失败：{_error_text(exc)}")

        if current_name:
            index = self.template_combo.findData(current_name)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)
        self.template_combo.blockSignals(False)

    def _default_template_script(self) -> str:
        return "[@MAIN]\n#IF\n#ACT\n#SAY\n<普通文本/SCOLOR=251>\\\n"

    def _reset_to_template_source(self, script: str, name: str = '') -> None:
        if hasattr(self, "npc_list"):
            self.npc_list.blockSignals(True)
            self.npc_list.clearSelection()
            self.npc_list.setCurrentRow(-1)
            self.npc_list.blockSignals(False)
        self.current_entry = None
        self.current_path = ""
        self.current_encoding = "gb18030"
        self.source_view_path = "__editor__"
        self.source_view_encoding = "gb18030"
        self.primary_source = script
        self.template_mode = True
        self.current_template_name = name
        self.template_dirty = False
        self._call_source_overrides.clear()
        self.undo_stack = UndoStack()
        self.selected_component_id = ""
        self._sync_component_palette_selection(None)
        self.component_items.clear()
        self._set_source_editor_text_programmatically(script)
        self.document = self.engine.parse(script, file_key="__editor__")
        self.layout_document = None
        self._load_labels()
        if not self.label_list.count():
            self.render_current_source()
        self.template_dirty = False
        if name:
            index = self.template_combo.findData(name)
            if index >= 0:
                self.template_combo.setCurrentIndex(index)
        self.status_label.setText("已进入新建模板状态")

    def _new_visual_template(self) -> None:
        if not self._confirm_template_switch():
            return
        self._reset_to_template_source(self._default_template_script())

    def _confirm_template_switch(self) -> bool:
        if not (self.template_mode and self.template_dirty):
            return True
        answer = QMessageBox.question(self, "保存模板", "当前模板有改动，是否保存模板？", QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.Yes)
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Yes:
            return self._save_visual_template()
        return True

    def _ask_template_name(self, initial: str = '') -> str:
        name, ok = QInputDialog.getText(self, "保存模板", "模板名称：", text=initial)
        if not ok:
            return ""
        return name.strip()

    def _save_visual_template(self) -> bool:
        script = self._template_script_for_save()
        if not script.strip():
            QMessageBox.warning(self, "保存模板", "当前没有可保存的模板脚本。")
            return False
        name = self.current_template_name.strip()
        if not name:
            default_name = ""
            if self.current_entry is not None:
                npc_name = str(getattr(self.current_entry, "npc_name", "") or "").strip()
                map_name = str(getattr(self.current_entry, "map_name", "") or "").strip()
                default_name = f"{map_name}-{npc_name}".strip("-") or npc_name
            name = self._ask_template_name(default_name)
        if not name:
            return False
        if name in self.visual_templates and name != self.current_template_name:
            QMessageBox.warning(self, "保存模板", "模板名称不能相同。")
            return False
        try:
            with self._template_store_conn() as conn:
                if name in self.visual_templates or self.current_template_name:
                    cursor = conn.execute(
                        "UPDATE visual_npc_templates SET name=?, script=?, updated_at=CURRENT_TIMESTAMP WHERE name=?",
                        (name, script, self.current_template_name or name),
                    )
                    if cursor.rowcount == 0:
                        conn.execute("INSERT INTO visual_npc_templates(name, script) VALUES(?, ?)", (name, script))
                else:
                    conn.execute("INSERT INTO visual_npc_templates(name, script) VALUES(?, ?)", (name, script))
                conn.commit()
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "保存模板", "模板名称不能相同。")
            return False
        except BaseException as exc:
            QMessageBox.critical(self, "保存模板失败", _error_text(exc))
            return False
        self.current_template_name = name if self.template_mode else self.current_template_name
        if self.template_mode:
            self.template_dirty = False
        self._load_visual_templates()
        index = self.template_combo.findData(name)
        if index >= 0:
            self.template_combo.setCurrentIndex(index)
        self.status_label.setText(f"模板已保存：{name}")
        return True

    def _template_script_for_save(self) -> str:
        if self.template_mode:
            self.primary_source = self.source_editor.toPlainText()
            return self.primary_source
        return self._extract_current_layout_template_script()

    def _extract_current_layout_template_script(self) -> str:
        if self.layout_document is None:
            self.render_current_source()
        base_source = self._render_base_source()
        render_source = self._source_for_render(base_source)
        document = self.engine.parse(render_source, file_key=self.current_path or "__editor__")
        label = str(getattr(self.layout_document, "label", "") or self._current_label() or "")
        block = document.label_by_name(label) if label else document.labels[0] if document.labels else None
        open_line = ""
        say_source = ""
        if block is not None:
            if block.openmerchant is not None:
                open_line = block.openmerchant.raw.strip()
            try:
                block_index = document.labels.index(block)
            except ValueError:
                block_index = -1
            if not open_line and block_index >= 0:
                start = block.source.end
                end = document.labels[block_index + 1].source.start if block_index + 1 < len(document.labels) else len(render_source)
                for line in render_source[start:end].splitlines():
                    if re.match(
                        r"^\s*(?:OPENMERCHANTBIGDLG|OPENBIGDIALOGBOX)\b",
                        line,
                        re.IGNORECASE,
                    ):
                        open_line = line.strip()
                        break
            say_parts = [say.source.raw.strip() for say in block.say_blocks if say.source.raw.strip()]
            say_source = "\n".join(say_parts).strip()

        if not say_source:
            say_source = self._extract_say_source_only(base_source)
        parts = [
         "[@MAIN]", "#IF", "#ACT"]
        if open_line:
            parts.append(open_line)
        parts.append("#SAY")
        parts.append(say_source.strip() or "<普通文本/SCOLOR=251>\\")
        return "\n".join(parts).rstrip() + "\n"

    def _extract_say_source_only(self, source: str) -> str:
        lines = source.splitlines()
        out = []
        in_say = False
        for line in lines:
            stripped = line.strip()
            if re.match("^#(?:say|elsesay)\\b", stripped, re.IGNORECASE):
                in_say = True
                continue
            if not in_say:
                continue
            if re.match("^#(?:if|act|elseact|else|elseif|or)\\b", stripped, re.IGNORECASE):
                break
            out.append(line.rstrip())
        return "\n".join(out).strip()

    def _selected_template_script(self) -> tuple[str, str]:
        item_data = self.template_combo.currentData() if hasattr(self, "template_combo") else ""
        name = str(item_data or "")
        if not name:
            return ('', '')
        return (name, self.visual_templates.get(name, ""))

    def _import_visual_template_layout(self) -> None:
        name, script = self._selected_template_script()
        if not name or not script.strip():
            QMessageBox.warning(self, "导入布局", "请先选择模板。")
            return None
        if self.current_entry is None or not self.current_path:
            self._reset_to_template_source(script, "")
            self.status_label.setText(f"已从模板新建画布：{name}")
            return None
        self._render_base_source()
        source = self.primary_source or self.source_editor.toPlainText()
        label = self._next_visual_template_label()
        block = self._template_script_with_label(script, label)
        prefix = "" if (not source or source.endswith(("\n", "\r"))) else "\n"
        updated = source + prefix + block
        if not self._set_editor_source_after_edit(self.current_path, updated, source):
            return None
        self.undo_stack.push(source)
        self.template_mode = False
        self.current_template_name = ""
        self.template_dirty = False
        self.document = self.engine.parse(self._source_for_render(updated), file_key=self.current_path or "__editor__")
        self._load_labels()
        self._select_label(label)
        self.status_label.setText(f"已导入模板：{name} -> {label}")
        return None

    def _next_visual_template_label(self) -> str:
        existing = set()
        if hasattr(self, "label_list"):
            existing.update((str(self.label_list.item(i).data(Qt.UserRole) or "") for i in range(self.label_list.count())))
        if self.document is not None:
            existing.update(self.document.label_names())
        index = 1
        while True:
            label = f"@畅玩可视化标签{index}"
            if label not in existing:
                return label
            else:
                index += 1

    def _template_script_with_label(self, script: str, label: str) -> str:
        body = script.strip()
        if re.search("^\\s*\\[@[^\\]]+\\]", body, re.MULTILINE):
            body = re.sub("^\\s*\\[@[^\\]]+\\]", f"[{label}]", body, count=1, flags=re.MULTILINE)
        else:
            body = f"[{label}]\n#IF\n#ACT\n#SAY\n{body}"
        return body.rstrip() + "\n"

    def show_component_tooltip(self, component: LayoutComponent, global_pos: QPoint) -> None:
        if not hasattr(self, "tooltip_overlay"):
            return
        if str(getattr(component.node, "kind", "") or "").casefold() == "itemshow":
            self._show_item_tooltip_async(component, global_pos)
            return
        self._item_tooltip_request_token += 1
        self._item_tooltip_hover_pos = None
        self.tooltip_overlay.show_component(component, global_pos)

    def move_component_tooltip(self, global_pos: QPoint) -> None:
        if self._item_tooltip_hover_pos is not None:
            self._item_tooltip_hover_pos = QPoint(global_pos)
        if hasattr(self, "tooltip_overlay") and self.tooltip_overlay.isVisible():
            self.tooltip_overlay.move_near(global_pos)

    def hide_component_tooltip(self) -> None:
        self._item_tooltip_request_token += 1
        self._item_tooltip_hover_pos = None
        if hasattr(self, "tooltip_overlay"):
            self.tooltip_overlay.hide()

    def _build_left_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("npcV2Left")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(QLabel("NPC列表"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索NPC...")
        self.search_edit.textChanged.connect(self._filter_npcs)
        layout.addWidget(self.search_edit)
        self.npc_list = QListWidget()
        self.npc_list.setSelectionMode(QAbstractItemView.SingleSelection)
        self.npc_list.setFocusPolicy(Qt.StrongFocus)
        self.npc_list.currentItemChanged.connect(self._npc_item_changed)
        layout.addWidget(self.npc_list, 1)
        layout.addWidget(QLabel("素材库"))
        self.resource_tabs = QTabWidget()
        self.resource_tabs.addTab(self._build_resource_files_tab(), "PAK")
        self.resource_tabs.addTab(self._build_resource_detail_tab(), "素材详情")
        layout.addWidget(self.resource_tabs, 1)
        return panel

    def _build_component_library_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("npcV2ComponentLibrary")
        panel.setMaximumHeight(118)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        component_header = QHBoxLayout()
        component_header.setContentsMargins(0, 0, 0, 0)
        component_header.addWidget(QLabel("组件库"))
        component_header.addStretch(1)
        component_header.addWidget(QLabel("引擎"))
        self.component_engine_combo = QComboBox()
        self.component_engine_combo.setMinimumWidth(120)
        self.component_engine_combo.addItem("领风", "lf")
        self.component_engine_combo.addItem("GOM", "gom")
        self._set_component_engine_combo(self._context_engine_family())
        self.component_engine_combo.currentIndexChanged.connect(lambda _index: self._refresh_component_palette())
        component_header.addWidget(self.component_engine_combo)
        layout.addLayout(component_header)

        self.component_palette = _ComponentPaletteList()
        self.component_palette.setViewMode(QListView.IconMode)
        self.component_palette.setFlow(QListView.LeftToRight)
        self.component_palette.setWrapping(True)
        self.component_palette.setResizeMode(QListView.Adjust)
        self.component_palette.setMovement(QListView.Static)
        self.component_palette.setUniformItemSizes(True)
        self.component_palette.setGridSize(QSize(112, 28))
        self.component_palette.setDragEnabled(True)
        self.component_palette.setDragDropMode(QAbstractItemView.DragOnly)
        self.component_palette.setDefaultDropAction(Qt.CopyAction)
        self.component_palette.itemDoubleClicked.connect(self._component_palette_double_clicked)
        self._refresh_component_palette()
        layout.addWidget(self.component_palette, 1)
        return panel

    def _context_engine_family(self) -> str:
        value = self._context_value("get_engine_family")
        if value:
            return value.casefold()
        return "lf"

    def _selected_component_engine_family(self) -> str:
        combo = getattr(self, "component_engine_combo", None)
        if combo is None:
            return self._context_engine_family()
        value = str(combo.currentData() or "").strip().casefold()
        return value or self._context_engine_family()

    def _set_component_engine_combo(self, engine_family: str) -> None:
        combo = getattr(self, "component_engine_combo", None)
        if combo is None:
            return
        family = str(engine_family or "lf").strip().casefold()
        target = "gom" if family == "gom" else "lf"
        for index in range(combo.count()):
            if str(combo.itemData(index) or "").casefold() == target:
                if combo.currentIndex() != index:
                    combo.setCurrentIndex(index)
                else:
                    return

    def _refresh_component_palette(self) -> None:
        palette = getattr(self, "component_palette", None)
        if palette is None:
            return
        engine_family = self._selected_component_engine_family()
        components = _component_library_for_engine(engine_family)
        tags_before = {str(palette.item(index).data(Qt.UserRole) or "") for index in range(palette.count())}
        tags_after = {tag for _name, tag in components}
        if engine_family == self._component_palette_engine_last and tags_before == tags_after:
            return
        current_tag = ""
        current_item = palette.currentItem()
        if current_item is not None:
            current_tag = str(current_item.data(Qt.UserRole) or "")
        palette.blockSignals(True)
        palette.clear()
        selected_row = -1
        for row, (name, tag) in enumerate(components):
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, tag)
            item.setToolTip(tag)
            palette.addItem(item)
            if tag == current_tag:
                selected_row = row
        palette.blockSignals(False)

        if selected_row >= 0:
            palette.setCurrentRow(selected_row)
        elif palette.count():
            palette.setCurrentRow(0)
        self._component_palette_engine_last = engine_family
        selected_item = self.component_items.get(self.selected_component_id)
        if selected_item is not None:
            self._sync_component_palette_selection(selected_item.component)

    @staticmethod
    def _component_palette_key(component: LayoutComponent) -> str:
        kind = str(component.node.kind or "").strip().casefold()
        aliases = {
            "positioned_text": "LABEL",
            "playimg": "PLAYIMG",
            "playimgex": "PLAYIMGEX",
            "itemshow": "ITEMSHOW",
            "itembox": "ITEMBOX",
            "progressbar": "PROGRESSBAR",
            "mtext": "MTEXT",
        }
        if kind == "link":
            return _component_library_tag(component.node.raw)
        return aliases.get(kind, kind.upper())

    def _sync_component_palette_selection(self, component: LayoutComponent | None) -> None:
        palette = getattr(self, "component_palette", None)
        if palette is None:
            return
        target_key = self._component_palette_key(component) if component is not None else ""
        target_item = None
        if target_key:
            for row in range(palette.count()):
                item = palette.item(row)
                if _component_library_tag(str(item.data(Qt.UserRole) or "")) == target_key:
                    target_item = item
                    break
        palette.blockSignals(True)
        try:
            palette.clearSelection()
            for row in range(palette.count()):
                item = palette.item(row)
                item.setBackground(QBrush())
                item.setForeground(QBrush())
            if target_item is None:
                palette.setCurrentRow(-1)
                return
            palette.setCurrentItem(target_item)
            target_item.setSelected(True)
            target_item.setBackground(QBrush(QColor("#d45500")))
            target_item.setForeground(QBrush(QColor("#ffffff")))
            palette.scrollToItem(target_item, QAbstractItemView.PositionAtCenter)
        finally:
            palette.blockSignals(False)

    def _build_resource_files_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        # Grouped by folder: a flat list cannot distinguish same-named assets
        # staged in different directories.
        self.effect_file_tree = QTreeWidget()
        self.effect_file_tree.setHeaderHidden(True)
        self.effect_file_tree.setColumnCount(1)
        self.effect_file_tree.setUniformRowHeights(True)
        self.effect_file_tree.setIndentation(12)
        self.effect_file_tree.itemClicked.connect(self._effect_file_selected)
        self.effect_file_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.effect_file_tree.customContextMenuRequested.connect(
            self._effect_file_context_menu
        )
        layout.addWidget(self.effect_file_tree)
        return page

    def _build_resource_detail_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.resource_detail_list = _ResourceDetailList(self)
        self.resource_detail_list.setViewMode(QListView.IconMode)
        self.resource_detail_list.setFlow(QListView.LeftToRight)
        self.resource_detail_list.setWrapping(True)
        self.resource_detail_list.setResizeMode(QListWidget.Adjust)
        self.resource_detail_list.setMovement(QListWidget.Static)
        self.resource_detail_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.resource_detail_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.resource_detail_list.setDragEnabled(True)
        self.resource_detail_list.setDragDropMode(QAbstractItemView.DragOnly)
        self.resource_detail_list.setDefaultDropAction(Qt.CopyAction)
        self.resource_detail_list.setGridSize(QSize(72, 96))
        self.resource_detail_list.setIconSize(QSize(64, 64))
        self.resource_detail_list.setUniformItemSizes(True)
        self.resource_detail_list.setSpacing(2)
        self.resource_detail_list.itemClicked.connect(self._resource_detail_selected)
        self.resource_detail_list.itemDoubleClicked.connect(self._resource_detail_double_clicked)
        detail_scrollbar = self.resource_detail_list.verticalScrollBar()
        detail_scrollbar.valueChanged.connect(
            self._schedule_resource_detail_thumbnail_refresh
        )
        detail_scrollbar.rangeChanged.connect(
            self._schedule_resource_detail_thumbnail_refresh
        )
        layout.addWidget(self.resource_detail_list)
        return page

    def _build_canvas_panel(self) -> QWidget:
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(5)
        toolbar.addWidget(QLabel("画布缩放"))
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedSize(28, 26)
        zoom_out_btn.setToolTip("缩小画布")
        zoom_out_btn.clicked.connect(lambda: self.zoom_canvas_by(-10))
        toolbar.addWidget(zoom_out_btn)
        self.canvas_zoom_slider = QSlider(Qt.Horizontal)
        self.canvas_zoom_slider.setRange(50, 300)
        self.canvas_zoom_slider.setSingleStep(10)
        self.canvas_zoom_slider.setPageStep(25)
        self.canvas_zoom_slider.setValue(100)
        self.canvas_zoom_slider.setFixedWidth(150)
        self.canvas_zoom_slider.setToolTip("调节画布显示倍率（50% - 300%）")
        self.canvas_zoom_slider.valueChanged.connect(self.set_canvas_zoom_percent)
        toolbar.addWidget(self.canvas_zoom_slider)
        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedSize(28, 26)
        zoom_in_btn.setToolTip("放大画布")
        zoom_in_btn.clicked.connect(lambda: self.zoom_canvas_by(10))
        toolbar.addWidget(zoom_in_btn)
        self.canvas_zoom_label = QLabel("100%")
        self.canvas_zoom_label.setAlignment(Qt.AlignCenter)
        self.canvas_zoom_label.setMinimumWidth(46)
        toolbar.addWidget(self.canvas_zoom_label)
        actual_size_btn = QPushButton("100%")
        actual_size_btn.setToolTip("按原始分辨率显示")
        actual_size_btn.clicked.connect(lambda: self.set_canvas_zoom_percent(100))
        toolbar.addWidget(actual_size_btn)
        fit_btn = QPushButton("适应窗口")
        fit_btn.setToolTip("完整显示画布")
        fit_btn.clicked.connect(self.fit_canvas_to_view)
        toolbar.addWidget(fit_btn)
        self.canvas_resolution_label = QLabel("0 x 0")
        self.canvas_resolution_label.setStyleSheet("color: #607086;")
        toolbar.addWidget(self.canvas_resolution_label)
        toolbar.addStretch(1)
        toolbar.addWidget(QLabel("Ctrl+滚轮缩放"))
        layout.addLayout(toolbar)

        edit_toolbar = QHBoxLayout()
        edit_toolbar.setContentsMargins(0, 0, 0, 0)
        edit_toolbar.setSpacing(5)
        edit_toolbar.addWidget(QLabel("画布编辑"))
        self.canvas_selection_label = QLabel("已选 0")
        self.canvas_selection_label.setMinimumWidth(52)
        self.canvas_selection_label.setStyleSheet("color: #607086;")
        edit_toolbar.addWidget(self.canvas_selection_label)
        self.canvas_arrange_button = QPushButton("排列")
        self.canvas_arrange_button.setToolTip("对齐或均布所选组件")
        arrange_menu = QMenu(self.canvas_arrange_button)
        self._arrange_actions = {}
        arrange_entries = (
            ("left", "左对齐"),
            ("hcenter", "水平居中"),
            ("right", "右对齐"),
            ("top", "顶部对齐"),
            ("vcenter", "垂直居中"),
            ("bottom", "底部对齐"),
            ("hdistribute", "横向均布"),
            ("vdistribute", "纵向均布"),
        )
        for index, (mode, title) in enumerate(arrange_entries):
            if index in (3, 6):
                arrange_menu.addSeparator()
            action = arrange_menu.addAction(title)
            action.triggered.connect(
                lambda _checked=False, selected_mode=mode: self.arrange_selected_components(selected_mode)
            )
            self._arrange_actions[mode] = action
        self.canvas_arrange_button.setMenu(arrange_menu)
        edit_toolbar.addWidget(self.canvas_arrange_button)
        self.canvas_delete_selected_button = QPushButton()
        self.canvas_delete_selected_button.setFixedSize(28, 26)
        self.canvas_delete_selected_button.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.canvas_delete_selected_button.setToolTip("删除所选组件 (Delete)")
        self.canvas_delete_selected_button.clicked.connect(self.delete_selected_components)
        edit_toolbar.addWidget(self.canvas_delete_selected_button)
        edit_toolbar.addStretch(1)
        edit_toolbar.addWidget(QLabel("Ctrl+A 全选  Ctrl+方向微移"))
        layout.addLayout(edit_toolbar)

        self.scene = QGraphicsScene(self)
        self.scene.selectionChanged.connect(self._canvas_selection_changed)
        self.view = _NpcCanvasView(self, self.scene)
        self.view.setRenderHints(self.view.renderHints())
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        self.view.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.view.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.view.setBackgroundBrush(QBrush(QColor("#171b22")))
        layout.addWidget(self.view, 1)
        self._update_selection_controls()
        layout.addWidget(self._build_component_library_panel())
        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.source_tabs = QTabWidget()
        source_page = QWidget()
        source_layout = QVBoxLayout(source_page)
        source_layout.setContentsMargins(0, 0, 0, 0)
        source_layout.setSpacing(0)
        self.source_editor = QPlainTextEdit()
        self.source_editor.setLineWrapMode(QPlainTextEdit.NoWrap)
        self.source_editor.setStyleSheet("font-family: Consolas, 'Microsoft YaHei UI'; font-size: 12px;")
        self.source_editor.installEventFilter(self)
        self.source_editor.viewport().installEventFilter(self)
        self.source_editor.textChanged.connect(self._source_editor_text_changed)
        source_layout.addWidget(self.source_editor)
        self.source_tabs.addTab(source_page, "源码")
        label_page = QWidget()
        label_layout = QVBoxLayout(label_page)
        label_layout.setContentsMargins(0, 0, 0, 0)
        label_layout.setSpacing(0)
        self.label_list = QListWidget()
        self.label_list.currentItemChanged.connect(self._label_item_changed)
        label_layout.addWidget(self.label_list)
        self.source_tabs.addTab(label_page, "标签")
        layout.addWidget(self.source_tabs, 1)
        layout.addWidget(QLabel("组件属性"))
        self.props_table = QTableWidget(0, 2)
        self.props_table.setHorizontalHeaderLabels(('属性', '值'))
        self.props_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.props_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.props_table.verticalHeader().setVisible(False)
        self.props_table.setMaximumHeight(210)
        layout.addWidget(self.props_table)
        return panel

    def eventFilter(self, obj: Any, event: Any) -> bool:
        source_editor = getattr(self, "source_editor", None)
        source_viewport = source_editor.viewport() if source_editor is not None else None
        if obj in (source_editor, source_viewport):
            if event.type() == QEvent.KeyPress:
                if self.handle_keyboard_move_key(event):
                    return True
                if self._keyboard_move_active() and not event.modifiers() & Qt.ControlModifier:
                    self.commit_keyboard_move()
            elif event.type() == QEvent.KeyRelease:
                if event.key() == Qt.Key_Control:
                    if self._keyboard_move_active():
                        self.commit_keyboard_move()
                        return True
        return super().eventFilter(obj, event)

    def _keyboard_move_active(self) -> bool:
        return bool(self._keyboard_group_snapshot) or self._keyboard_move_component is not None

    def keyPressEvent(self, event: Any) -> None:
        if self.handle_keyboard_move_key(event):
            return
        if self._keyboard_move_active():
            if not event.modifiers() & Qt.ControlModifier:
                self.commit_keyboard_move()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: Any) -> None:
        if event.key() == Qt.Key_Control:
            if self._keyboard_move_active():
                self.commit_keyboard_move()
                event.accept()
                return
        super().keyReleaseEvent(event)

    def reload_npcs(self) -> None:
        self._configure_resources(force=True)
        try:
            self.npcs = list(self.context.load_npcs())
        except Exception as exc:
            self.npcs = []
            self._log(f"NPC列表加载失败：{exc}")

        self._filter_npcs()
        self.status_label.setText(f"共 {len(self.npcs)} 个 NPC")

    def refresh_resource_context(self) -> None:
        """Apply a changed database/patch selection without rebuilding the NPC list."""
        selection_hint = self.selected_component_id
        self._configure_resources(force=True)
        self._monster_cache_path = None
        self._monster_cache = {}
        self._clear_item_tooltip_caches()
        if self.current_path or self.primary_source or self.source_editor.toPlainText():
            self.render_current_source(selection_hint=selection_hint)

    def _choose_patch_folder(self) -> None:
        self.context.choose_patch_folder()
        self.reload_npcs()

    def _filter_npcs(self) -> None:
        keyword = self.search_edit.text().strip().casefold() if hasattr(self, "search_edit") else ""
        self.filtered_npcs = []
        self.npc_list.clear()
        for entry in self.npcs:
            text = self._entry_text(entry)
            if keyword and keyword not in text.casefold():
                continue
            self.filtered_npcs.append(entry)
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry)
            self.npc_list.addItem(item)

    def _entry_text(self, entry: Any) -> str:
        map_name = str(getattr(entry, "map_name", ""))
        npc_name = str(getattr(entry, "npc_name", ""))
        coord = str(getattr(entry, "coord", ""))
        return f"{map_name} / {npc_name}  {coord}".strip()

    def _entry_detail_log(self, entry: Any) -> str:
        npc_name = str(getattr(entry, "npc_name", "") or "")
        map_name = str(getattr(entry, "map_name", "") or "")
        map_code = str(getattr(entry, "map_code", "") or "")
        x_value, y_value = self._entry_coord_xy(entry)
        return f"{npc_name}  {map_name}  {map_code}  {x_value}  {y_value}"

    def _entry_coord_xy(self, entry: Any) -> tuple[str, str]:
        coord = str(getattr(entry, "coord", "") or "").strip()
        parts = [part for part in re.split("[\\s,，]+", coord) if part]
        if len(parts) >= 2:
            return (parts[0], parts[1])
        return (coord, "")

    def _npc_item_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        entry = current.data(Qt.UserRole)
        self._npc_load_token += 1
        self._pending_npc_load = (self._npc_load_token, entry)
        self._npc_load_timer.start()
        self.status_label.setText(f"正在加载：{self._entry_text(entry)}")
        self._focus_npc_list_for_keyboard()

    def _start_pending_npc_load(self) -> None:
        pending = self._pending_npc_load
        self._pending_npc_load = None
        if not pending:
            return
        token, entry = pending
        if token != self._npc_load_token:
            return
        self.load_entry(entry, request_token=token)

    def _focus_npc_list_for_keyboard(self) -> None:
        if not hasattr(self, "npc_list"):
            return
        self.npc_list.setFocus(Qt.OtherFocusReason)
        QTimer.singleShot(0, lambda: self.npc_list.setFocus(Qt.OtherFocusReason))

    def load_entry(self, entry: Any, *, request_token: int | None = None) -> None:
        if request_token is None:
            self._npc_load_token += 1
            request_token = self._npc_load_token
        if request_token != self._npc_load_token:
            return None
        if not self._confirm_template_switch():
            return None
        self.current_entry = entry
        self.template_mode = False
        self.current_template_name = ""
        self.template_dirty = False
        path = self._resolve_entry_path(entry)
        if not path:
            self._log("NPC脚本不存在：未找到候选路径")
            return None
        self._source_file_identities.clear()
        try:
            source, encoding = self.context.read_text_file(path)
            self._remember_source_file_identity(path)
        except Exception as exc:
            self._log(f"NPC脚本读取失败：{path} / {exc}")
            return None
        self.current_path = path
        self.current_encoding = encoding
        self.primary_source = source
        self.source_view_path = path
        self.source_view_encoding = encoding
        self._call_source_overrides.clear()
        self.undo_stack = UndoStack()
        self._set_source_editor_text_programmatically(source)
        render_source = self._source_for_render(source)
        self._configure_resources()
        start_session = self._native_backend_session()
        self._sync_resource_auth_context(start_session)
        start_auth_context = (
            self._rpc_session_context(start_session)
            if isinstance(start_session, Mapping)
            else None
        )
        start_auth_generation = self._resource_auth_generation
        self._render_generation += 1
        self._queued_asset_prewarm_request = None
        self.document = None
        self.layout_document = None
        self.label_list.blockSignals(True)
        try:
            self.label_list.clear()
        finally:
            self.label_list.blockSignals(False)
        self.scene.clear()
        self.component_items.clear()
        self.status_label.setText(f"正在解析：{self._entry_text(entry)}")
        self.context.run_async(
            lambda: self._parse_render_document_for_session(
                render_source,
                path,
                start_session,
            ),
            partial(
                self._entry_parse_succeeded,
                request_token,
                entry,
                path,
                start_auth_context,
                start_auth_generation,
            ),
            partial(
                self._entry_parse_failed,
                request_token,
                start_auth_context,
                start_auth_generation,
            ),
        )
        return None

    def _entry_parse_succeeded(
        self,
        request_token: int,
        entry: Any,
        path: str,
        start_auth_context: tuple[str, str, str, str, int] | None,
        start_auth_generation: int,
        document: NpcDocument,
    ) -> None:
        current_session = self._native_backend_session()
        self._sync_resource_auth_context(current_session)
        current_auth_context = (
            self._rpc_session_context(current_session)
            if isinstance(current_session, Mapping)
            else None
        )
        if (
            request_token != self._npc_load_token
            or current_auth_context != start_auth_context
            or self._resource_auth_generation != start_auth_generation
        ):
            return
        self.document = document
        self._load_labels()
        self.status_label.setText(f"已加载：{self._entry_text(entry)}")
        self._log(f"加载NPC：{path}")
        self._log(self._entry_detail_log(entry))

    def _entry_parse_failed(
        self,
        request_token: int,
        start_auth_context: tuple[str, str, str, str, int] | None,
        start_auth_generation: int,
        exc: BaseException,
    ) -> None:
        current_session = self._native_backend_session()
        self._sync_resource_auth_context(current_session)
        current_auth_context = (
            self._rpc_session_context(current_session)
            if isinstance(current_session, Mapping)
            else None
        )
        if (
            request_token != self._npc_load_token
            or current_auth_context != start_auth_context
            or self._resource_auth_generation != start_auth_generation
        ):
            return
        self.document = None
        self.layout_document = None
        self.label_list.blockSignals(True)
        try:
            self.label_list.clear()
        finally:
            self.label_list.blockSignals(False)
        message = _error_text(exc)
        self.status_label.setText("NPC 服务器核心解析失败")
        self._log("NPC 服务器核心解析失败：%s" % message)

    def _resolve_entry_path(self, entry: Any) -> str:
        candidates = list(getattr(entry, "script_candidates", ()) or ())
        script_path = str(getattr(entry, "script_path", "") or "")
        if script_path:
            candidates.insert(0, script_path)
        for path in candidates:
            if path:
                if os.path.exists(path):
                    return path
        if script_path and os.path.exists(script_path):
            return script_path
        return ""

    def _configure_resources(self, force: bool = False) -> None:
        version_path = self._context_value("get_version_path")
        login_folder = self._context_value("get_login_folder")
        patch_folder = self._context_value("get_patch_folder")
        client_folder = self._context_value("get_client_folder")
        engine_family = self._context_value("get_engine_family") or "lf"
        database_path = self._context_value("get_database_path")
        signature = tuple(str(value or "") for value in (
            version_path,
            login_folder,
            patch_folder,
            engine_family,
            database_path,
            client_folder,
        ))
        if not force and signature == self._resource_config_signature:
            return
        try:
            self._component_resource_cache.clear()
            self._component_pixmap_cache.clear()
            missing_notices = getattr(self, "_missing_resource_notices", None)
            if missing_notices is not None:
                missing_notices.clear()
            if force and signature == self._resource_config_signature:
                background_provider = getattr(self.resource_provider, "background_provider", None)
                candidate_cache = getattr(background_provider, "data_file_candidates_cache", None)
                if candidate_cache is not None:
                    candidate_cache.clear()
            self.resource_provider.configure(
                version_path, login_folder, patch_folder, engine_family,
                database_path, client_folder,
            )
            self._set_component_engine_combo(self._context_engine_family())
            self._refresh_component_palette()
            self._refresh_effect_file_list()
            self._resource_config_signature = signature
            self._clear_item_tooltip_caches()
        except Exception as exc:
            self._log(f"素材资源配置失败：{exc}")

    def _parse_render_document(self, render_source: str, file_key: str) -> NpcDocument:
        _session, auth_context = self._require_rpc_parse_session()
        scope_sha256, expected_pre_sha256 = self._npc_rpc_target_binding(render_source, file_key)
        cache_key = (auth_context, file_key, render_source, scope_sha256, expected_pre_sha256)
        if cache_key == self._parsed_document_cache_key and self._parsed_document_cache is not None:
            return self._parsed_document_cache
        document = self.engine.parse(render_source, file_key=file_key)
        self._hydrate_document_runtime_values(document)
        self._parsed_document_cache_key = cache_key
        self._parsed_document_cache = document
        return document

    def _parse_render_document_for_session(
        self,
        render_source: str,
        file_key: str,
        session: Mapping[str, Any] | None,
    ) -> NpcDocument:
        self._rpc_parse_session_local.bound_session = (
            dict(session) if isinstance(session, Mapping) else None
        )
        try:
            return self._parse_render_document(render_source, file_key)
        finally:
            with contextlib.suppress(AttributeError):
                del self._rpc_parse_session_local.bound_session

    def _hydrate_document_runtime_values(self, document: NpcDocument) -> None:
        for label in document.labels:
            variables = self._runtime_variables_for_act_lines(label.act_lines)
            if not variables:
                continue
            if label.openmerchant is not None:
                self._hydrate_node_runtime_args(label.openmerchant, variables)
            for say_block in label.say_blocks:
                for node in say_block.nodes:
                    self._hydrate_node_runtime_args(node, variables)

    def _runtime_variables_for_act_lines(self, act_lines: list[str]) -> dict[str, str]:
        variables = {}
        field_resolver = getattr(self.resource_provider, "item_field_for_name", None)
        for line in act_lines:
            mov_match = _MOV_ASSIGN_RE.match(str(line or ""))
            if mov_match:
                value = self._runtime_token_value(mov_match.group("value") or "", variables)
                if value is not None:
                    variables[mov_match.group("name").strip().casefold()] = value
                continue
            field_match = _GET_DB_ITEM_FIELD_RE.match(str(line or ""))
            if field_match is None or not callable(field_resolver):
                continue
            item_name = self._runtime_token_value(field_match.group("item"), variables)
            if not item_name:
                continue
            value = field_resolver(item_name, field_match.group("field"))
            if value is not None:
                variables[field_match.group("name").strip().casefold()] = str(value)
        return variables

    @staticmethod
    def _runtime_token_value(raw_value: str, variables: dict[str, str]) -> str | None:
        value = str(raw_value or "").strip()
        match = _STR_REF_RE.fullmatch(value)
        if match:
            return variables.get(match.group("name").strip().casefold())
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        return value

    def _hydrate_node_runtime_args(self, node: Any, variables: dict[str, str]) -> None:
        if getattr(node, "kind", "") in _RUNTIME_ARG_COMPONENT_KINDS:
            args = node.props.get("args")
            raw_args = self._raw_component_args(node)
            if isinstance(args, list) and len(raw_args) == len(args):
                hydrated = list(args)
                for index, raw_arg in enumerate(raw_args):
                    match = _STR_REF_RE.fullmatch(raw_arg.strip())
                    if match:
                        value = variables.get(match.group("name").strip().casefold())
                        if value is not None:
                            hydrated[index] = value
                node.props["args"] = hydrated
        for child in getattr(node, "children", ()) or ():
            self._hydrate_node_runtime_args(child, variables)

    @staticmethod
    def _raw_component_args(node: Any) -> list[str]:
        raw = str(getattr(getattr(node, "source", None), "raw", "") or getattr(node, "raw", "") or "").strip()
        match = re.match(r"^\s*<\s*[^:>]+\s*:(?P<body>.*)>\s*$", raw, re.DOTALL)
        if match is None:
            return []
        body = match.group("body").strip()
        if body.endswith("/"):
            body = body[:-1].rstrip()
        parts = body.split(":")
        if node.props.get("parent_id") and parts and parts[0].strip().endswith("~"):
            parts = parts[1:]
        return parts

    def _clear_rpc_parse_caches(self) -> None:
        self._rpc_parse_cache.clear()
        self._rpc_parse_cache_order.clear()
        self._parsed_document_cache_key = None
        self._parsed_document_cache = None

    def _clear_item_tooltip_caches(self) -> None:
        with self._item_tooltip_cache_lock:
            authorizations = tuple(self._item_tooltip_authorizations.values())
            self._item_tooltip_authorizations.clear()
            self._item_tooltip_cache.clear()
            self._item_tooltip_context_generation += 1
        self._close_item_tooltip_authorizations(authorizations)
        self._item_tooltip_request_token += 1
        self._item_tooltip_hover_pos = None
        if hasattr(self, "tooltip_overlay"):
            self.tooltip_overlay.hide()

    def _item_tooltip_asset_broker(self) -> Any:
        asset_gate = getattr(self.resource_provider, "_asset_gate", None)
        return getattr(asset_gate, "asset_broker", None)

    def _close_item_tooltip_authorizations(
        self,
        authorizations: Iterable[Mapping[str, Any]],
        asset_broker: Any = None,
    ) -> None:
        broker = (
            asset_broker
            if asset_broker is not None
            else self._item_tooltip_asset_broker()
        )
        close_asset = getattr(broker, "close_asset", None)
        if not callable(close_asset):
            return
        try:
            current_generation = int(getattr(broker, "generation", 0) or 0)
        except (TypeError, ValueError):
            return
        closed: set[tuple[str, int]] = set()
        for authorization in authorizations:
            try:
                handle = str(authorization.get("tooltip_handle") or "")
                generation = int(authorization.get("worker_generation") or 0)
            except (AttributeError, TypeError, ValueError):
                continue
            identity = (handle, generation)
            if not handle or generation != current_generation or identity in closed:
                continue
            closed.add(identity)
            try:
                close_asset(handle, generation)
            except Exception:
                pass

    def _sync_resource_auth_context(self, session: Mapping[str, Any] | None) -> None:
        auth_context = self._rpc_session_context(session) if isinstance(session, Mapping) else None
        if auth_context == self._resource_auth_context:
            return
        self._clear_item_tooltip_caches()
        self._component_resource_cache.clear()
        self._component_pixmap_cache.clear()
        self._missing_resource_notices.clear()
        self.resource_detail_records = []
        self.resource_detail_slots = []
        self.resource_detail_token = int(getattr(self, "resource_detail_token", 0)) + 1
        clear_provider = getattr(self.resource_provider, "clear_authorized_caches", None)
        if callable(clear_provider):
            clear_provider()
        self._resource_auth_context = auth_context
        self._resource_auth_generation += 1

    def _rpc_session_context(self, session: dict[str, Any]) -> tuple[str, str, str, str, int]:
        server = str(session.get("server") or "").strip().rstrip("/").casefold()
        username = str(
            session.get("username")
            or session.get("account_id")
            or session.get("account")
            or ""
        ).strip().casefold()
        device_id = str(session.get("device_id") or "").strip()
        token = str(session.get("token") or "").strip()
        token_digest = hashlib.sha256(token.encode("utf-8", errors="strict")).hexdigest()
        try:
            auth_epoch = int(session.get("_auth_epoch") or 0)
        except (TypeError, ValueError):
            auth_epoch = 0
        return (server, username, device_id, token_digest, auth_epoch)

    def _require_rpc_parse_session(self) -> tuple[dict[str, Any], tuple[str, str, str, str, int]]:
        if hasattr(self._rpc_parse_session_local, "bound_session"):
            bound_session = self._rpc_parse_session_local.bound_session
            if not isinstance(bound_session, Mapping):
                raise RuntimeError("NPC 可视化需要登录并取得服务器核心授权")
            session = dict(bound_session)
            return session, self._rpc_session_context(session)
        session = self._native_backend_session()
        if session is None:
            self._sync_resource_auth_context(None)
            self._clear_rpc_parse_caches()
            self._rpc_parse_auth_context = None
            raise RuntimeError("NPC 可视化需要登录并取得服务器核心授权")
        auth_context = self._rpc_session_context(session)
        self._sync_resource_auth_context(session)
        if auth_context != self._rpc_parse_auth_context:
            self._clear_rpc_parse_caches()
            self._rpc_parse_auth_context = auth_context
        return session, auth_context

    def _npc_rpc_target_binding(self, source_text: str, file_key: str) -> tuple[str, str]:
        key = str(file_key or "__editor__")
        target = Path(key)
        if key not in {"__editor__", "__main__", "__insert__"} and target.is_file() and not target.is_symlink():
            raw = target.read_bytes()
            current_identity = self._source_file_identity(target, raw)
            identity_key = self._source_identity_key(target)
            remembered = self._source_file_identities.get(identity_key)
            if remembered is not None and remembered != current_identity:
                raise RuntimeError("NPC 源文件已被其他程序修改，请重新加载")
            if remembered is None:
                self._source_file_identities[identity_key] = current_identity
            return (
                compute_target_scope_sha256("npc.visual.parse", (target,)),
                str(current_identity[2]),
            )
        digest = hashlib.sha256(source_text.encode("utf-8", errors="strict")).hexdigest()
        return self._rpc_editor_scope_sha256, digest

    def _parse_document_via_rpc(self, source_text: str, file_key: str) -> NpcDocument:
        session, auth_context = self._require_rpc_parse_session()
        digest = hashlib.sha256(source_text.encode("utf-8", errors="strict")).hexdigest()
        scope_sha256, expected_pre_sha256 = self._npc_rpc_target_binding(source_text, file_key)
        cache_key = (
            auth_context,
            str(file_key or "__main__"),
            digest,
            scope_sha256,
            expected_pre_sha256,
        )
        cached = self._rpc_parse_cache.get(cache_key)
        if cached is not None and cached.source_text == source_text:
            return cached
        try:
            payload = parse_npc_document_rpc(
                session,
                source_text,
                target_scope_sha256=scope_sha256,
                expected_pre_sha256=expected_pre_sha256,
                allow_local_http=True,
            )
            document = npc_document_from_rpc(payload, source_text, str(file_key or "__main__"))
        except CoreRpcError as exc:
            raise RuntimeError("NPC 服务器核心解析失败：%s" % exc) from exc
        except Exception as exc:
            raise RuntimeError("NPC 服务器核心返回无效") from exc
        self._rpc_parse_cache[cache_key] = document
        self._rpc_parse_cache_order.append(cache_key)
        while len(self._rpc_parse_cache_order) > 8:
            expired = self._rpc_parse_cache_order.pop(0)
            self._rpc_parse_cache.pop(expired, None)
        return document

    def _refresh_effect_file_list(self) -> None:
        tree = getattr(self, "effect_file_tree", None)
        if tree is None:
            return None
        tree.clear()
        self._resource_scan_token += 1
        scan_token = self._resource_scan_token
        self.resource_detail_records = []
        self.resource_detail_slots = []
        self.resource_detail_effect_index = 0
        self.resource_detail_file_name = ""
        self.resource_detail_token += 1
        self.resource_detail_thumb_token += 1
        self.resource_detail_thumb_icons.clear()
        self._render_resource_details()
        if not self.resource_provider.configured:
            return None
        provider = self.resource_provider.background_provider
        if provider is None:
            return None
        try:
            files = provider.load_effect_files()
        except Exception as exc:
            self._log(f"素材文件列表加载失败：{exc}")
            return None
        groups: dict[str, QTreeWidgetItem] = {}
        probe_rows: list[tuple[Path, str, QTreeWidgetItem, bool, str]] = []

        def group_for(label: str) -> QTreeWidgetItem:
            node = groups.get(label)
            if node is None:
                node = QTreeWidgetItem([label])
                node.setToolTip(0, label)
                tree.addTopLevelItem(node)
                groups[label] = node
            return node

        # EffectImageList only assigns indexes; the tab lists whatever the
        # client actually contains so unregistered or locked files stay visible.
        index_by_name: dict[str, int] = {}
        for index, file_name in enumerate(files):
            name = str(file_name or "").strip()
            if name:
                index_by_name.setdefault(name.casefold(), index)

        for asset_path in self._discover_asset_files(provider):
            listed_index = index_by_name.get(asset_path.name.casefold(), -1)
            is_pak = asset_path.suffix.lower() == ".pak"
            password = self._known_asset_password(provider, asset_path)
            registered = bool(password) or not is_pak
            label_index = "%04d" % listed_index if listed_index >= 0 else "----"
            child = QTreeWidgetItem(["%s  %s" % (label_index, asset_path.name)])
            child.setData(0, Qt.UserRole, (listed_index, asset_path.name))
            child.setData(0, Qt.UserRole + 2, False)
            child.setData(0, Qt.UserRole + 3, str(asset_path))
            child.setData(0, Qt.UserRole + 4, registered)
            try:
                size_text = "%.1f MB" % (asset_path.stat().st_size / 1024 / 1024)
            except OSError:
                size_text = "?"
            hint = "正在后台验证素材格式..."
            child.setToolTip(0, "%s\n%s\n%s" % (asset_path, size_text, hint))
            group_for(str(asset_path.parent)).addChild(child)
            probe_rows.append((asset_path, password, child, registered, size_text))

        # Names the scripts reference but the client does not ship.
        for index, file_name in enumerate(files):
            name = str(file_name or "").strip()
            if not name or name.startswith("<"):
                continue
            if self._effect_asset_path(name) is not None:
                continue
            child = QTreeWidgetItem(["%04d  %s" % (index, name)])
            child.setData(0, Qt.UserRole, (index, name))
            child.setData(0, Qt.UserRole + 2, False)
            child.setToolTip(0, "%s\n未找到" % name)
            child.setForeground(0, QBrush(QColor("#d93025")))
            group_for("未找到").addChild(child)

        for label, node in groups.items():
            node.setText(0, "%s  (%d)" % (label, node.childCount()))
        tree.expandAll()
        if probe_rows:
            def work() -> list[tuple[str, str, str]]:
                return [
                    (
                        str(asset_path),
                        *self._resource_candidate_probe(asset_path, password),
                    )
                    for asset_path, password, _item, _registered, _size in probe_rows
                ]

            def done(results: object) -> None:
                if scan_token != self._resource_scan_token:
                    return
                probe_by_path = {
                    str(path): (str(status), str(reason))
                    for path, status, reason in results
                } if isinstance(results, list) else {}
                for asset_path, _password, child, registered, size_text in probe_rows:
                    status, reason = probe_by_path.get(
                        str(asset_path),
                        (_RESOURCE_PROBE_ERROR, "后台校验未返回结果"),
                    )
                    readable = status in {
                        _RESOURCE_PROBE_READABLE,
                        _RESOURCE_PROBE_UNVERIFIABLE,
                    }
                    child.setData(0, Qt.UserRole + 2, not readable)
                    child.setData(0, Qt.UserRole + 5, status)
                    child.setData(0, Qt.UserRole + 6, reason)
                    if status == _RESOURCE_PROBE_LOCKED:
                        hint = "无法读取，右键填写密码"
                        child.setForeground(0, QBrush(QColor("#d93025")))
                    elif status == _RESOURCE_PROBE_ERROR:
                        hint = "格式校验失败：%s" % (reason or "未知错误")
                        child.setForeground(0, QBrush(QColor("#d93025")))
                    elif status == _RESOURCE_PROBE_UNVERIFIABLE:
                        hint = (
                            "密码已登记；GEEPAK2 不做快速判密"
                            if registered
                            else "GEEPAK2 不做快速判密；右键登记密码"
                        )
                        child.setForeground(0, QBrush(QColor("#e8710a")))
                    elif not registered:
                        hint = "可读取，但 pak.txt 未登记；右键可补录密码"
                        child.setForeground(0, QBrush(QColor("#e8710a")))
                    else:
                        hint = "已登记密码，可读取"
                        child.setForeground(0, QBrush())
                    child.setToolTip(0, "%s\n%s\n%s" % (asset_path, size_text, hint))

            def failed(exc: BaseException) -> None:
                if scan_token == self._resource_scan_token:
                    self._log("素材格式后台验证失败：%s" % _error_text(exc))

            self.context.run_async(work, done, failed)
        return None

    def _effect_file_context_menu(self, position: Any) -> None:
        """Offer EffectImageList registration and PAK password entry."""
        tree = getattr(self, "effect_file_tree", None)
        if tree is None:
            return
        item = tree.itemAt(position)
        if not isinstance(item, QTreeWidgetItem):
            return
        stored_path = item.data(0, Qt.UserRole + 3)
        if not stored_path:
            return
        asset_path = Path(str(stored_path))
        menu = QMenu(tree)
        register_action = None
        if self._listed_index_of(item) < 0:
            register_action = menu.addAction("加入 EffectImageList.txt")

        password_action = None
        locked = bool(item.data(0, Qt.UserRole + 2))
        password_registered = bool(item.data(0, Qt.UserRole + 4))
        if asset_path.suffix.lower() == ".pak":
            if register_action is not None:
                menu.addSeparator()
            label = "填写密码" if locked else (
                "重新填写密码" if password_registered else "登记密码到 pak.txt"
            )
            password_action = menu.addAction(label)

        if register_action is None and password_action is None:
            return
        selected_action = menu.exec_(tree.viewport().mapToGlobal(position))
        if selected_action is None:
            return
        try:
            if selected_action is register_action:
                effect_index = self._ensure_effect_file_registered(asset_path.name)
                self.status_label.setText(
                    "已加入 EffectImageList.txt：%04d %s"
                    % (effect_index, asset_path.name)
                )
                return
            if selected_action is password_action:
                self._prompt_asset_password(item, asset_path, locked)
        except Exception as exc:
            # An exception escaping here would leave Qt holding the grab from
            # the context menu, making the whole window beep at every click.
            self._log("素材登记失败：%s" % exc)
            QMessageBox.warning(self, "素材库", "操作失败：%s" % exc)

    def _prompt_asset_password(
        self, item: Any, asset_path: Path, locked: bool
    ) -> None:
        """Ask for a password, verify it, then record it in pak.txt."""
        listed_probe_status = ""
        if isinstance(item, QTreeWidgetItem):
            listed_probe_status = str(item.data(0, Qt.UserRole + 5) or "")
        if listed_probe_status == _RESOURCE_PROBE_UNVERIFIABLE:
            prompt = (
                "%s\n\nGEEPAK2 无法通过本地文件头准确判定密码。\n"
                "输入内容将直接登记到 pak.txt，留空则取消：" % asset_path.name
            )
        else:
            prompt = (
                "%s\n\n该文件无法读取，请输入密码：" % asset_path.name
                if locked
                else "%s\n\n该文件可直接读取，pak.txt 尚未登记。\n"
                     "请输入要登记的密码，留空则取消：" % asset_path.name
            )
        password, accepted = QInputDialog.getText(
            self, "填写 PAK 密码", prompt,
        )
        if not accepted:
            return
        password = str(password or "").strip()
        if not password and not locked:
            # Readable already, so an empty answer just cancels.
            return
        probe_status, probe_reason = self._resource_candidate_probe(
            asset_path, password
        )
        if probe_status == _RESOURCE_PROBE_LOCKED:
            QMessageBox.warning(
                self, "素材库", "密码不正确，未写入 pak.txt。"
            )
            return
        if probe_status == _RESOURCE_PROBE_ERROR:
            QMessageBox.warning(
                self,
                "素材库",
                "文件格式校验失败，未写入 pak.txt：%s"
                % (probe_reason or "未知错误"),
            )
            return
        written, message = self._record_asset_password(asset_path, password)
        if not written:
            QMessageBox.warning(self, "素材库", message)
            return
        provider = self.resource_provider.background_provider
        if provider is not None:
            # Only the password table changed. The candidate cache maps names to
            # paths, and rebuilding it costs a recursive scan per name, so it is
            # deliberately left alone here.
            provider.passwords = None
        # Read the index before rebuilding: _refresh_effect_file_list clears the
        # tree, which destroys every item, and touching one afterwards raises
        # inside the slot and leaves Qt holding the input grab.
        listed_index = self._listed_index_of(item)
        self._refresh_effect_file_list()
        if probe_status == _RESOURCE_PROBE_UNVERIFIABLE:
            self.status_label.setText(
                "已登记 PAK 密码：%s" % asset_path.name
            )
            return
        self._open_asset_detail(listed_index, asset_path)

    @staticmethod
    def _listed_index_of(item: Any) -> int:
        """EffectImageList index for this row, -1 when it has none."""
        if not isinstance(item, QTreeWidgetItem):
            return -1
        try:
            data = item.data(0, Qt.UserRole)
        except RuntimeError:
            return -1
        try:
            return int(data[0]) if data else -1
        except (TypeError, ValueError, IndexError):
            return -1

    def _ensure_effect_file_registered(self, file_name: str) -> int:
        """Return a stable EffectImageList index, appending the name if needed."""
        normalized_name = PureWindowsPath(str(file_name or "").strip()).name
        if not normalized_name:
            raise RuntimeError("素材文件名为空，无法登记。")
        provider = self.resource_provider.background_provider
        if provider is None:
            raise RuntimeError("素材提供者不可用。")
        configured_path = getattr(provider, "effect_list_path", None)
        if configured_path is None or not str(configured_path).strip():
            raise RuntimeError("找不到 EffectImageList.txt 的位置。")
        effect_list_path = Path(str(configured_path))
        try:
            data = effect_list_path.read_bytes() if effect_list_path.is_file() else b""
        except OSError as exc:
            raise RuntimeError("读取 EffectImageList.txt 失败：%s" % exc) from exc

        if data.startswith(b"\xef\xbb\xbf"):
            encoding = "utf-8-sig"
            candidates = (encoding,)
        else:
            # ASCII-only legacy files are byte-identical in UTF-8 and GB18030;
            # Mir server text files conventionally use GB18030, so keep that
            # default until a non-ASCII byte gives us a reliable distinction.
            candidates = (
                ("utf-8", "gb18030")
                if any(byte >= 0x80 for byte in data)
                else ("gb18030", "utf-8")
            )
            encoding = ""
        existing = ""
        for candidate in candidates:
            try:
                existing = data.decode(candidate)
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
        if not encoding:
            raise RuntimeError("EffectImageList.txt 编码无法识别。")

        lines = existing.splitlines()
        target_key = normalized_name.casefold()
        for index, line in enumerate(lines):
            recorded_name = PureWindowsPath(str(line or "").strip()).name
            if recorded_name and recorded_name.casefold() == target_key:
                provider.effect_files = list(lines)
                self._apply_effect_file_index(normalized_name, index)
                return index

        if "\r\n" in existing:
            newline = "\r\n"
        elif "\r" in existing and "\n" not in existing:
            newline = "\r"
        elif existing:
            newline = "\n"
        else:
            newline = os.linesep
        body = existing
        if body and not body.endswith(("\r\n", "\n", "\r")):
            body += newline
        effect_index = len(lines)
        body += normalized_name + newline
        try:
            effect_list_path.parent.mkdir(parents=True, exist_ok=True)
            effect_list_path.write_bytes(body.encode(encoding, errors="strict"))
        except (OSError, UnicodeEncodeError) as exc:
            raise RuntimeError("写入 EffectImageList.txt 失败：%s" % exc) from exc

        provider.effect_files = body.splitlines()
        self._apply_effect_file_index(normalized_name, effect_index)
        return effect_index

    def _apply_effect_file_index(self, file_name: str, effect_index: int) -> None:
        """Update current tree/detail rows without destroying a live drag source."""
        target_key = PureWindowsPath(str(file_name or "")).name.casefold()
        if not target_key:
            return

        tree = getattr(self, "effect_file_tree", None)
        if tree is not None:
            pending = [tree.topLevelItem(index) for index in range(tree.topLevelItemCount())]
            while pending:
                row = pending.pop()
                if row is None:
                    continue
                pending.extend(row.child(index) for index in range(row.childCount()))
                data = row.data(0, Qt.UserRole)
                if not isinstance(data, (tuple, list)) or len(data) < 2:
                    continue
                row_name = PureWindowsPath(str(data[1] or "")).name
                if row_name.casefold() != target_key:
                    continue
                row.setData(0, Qt.UserRole, (int(effect_index), row_name))
                row.setText(0, "%04d  %s" % (int(effect_index), row_name))

        detail_list = getattr(self, "resource_detail_list", None)
        if detail_list is not None:
            for row_index in range(detail_list.count()):
                row = detail_list.item(row_index)
                data = row.data(Qt.UserRole)
                if not isinstance(data, (tuple, list)) or len(data) < 3:
                    continue
                row_name = PureWindowsPath(str(data[1] or "")).name
                if row_name.casefold() == target_key:
                    row.setData(
                        Qt.UserRole,
                        (int(effect_index), row_name, int(data[2])),
                    )

        if PureWindowsPath(str(self.resource_detail_file_name or "")).name.casefold() == target_key:
            old_index = int(self.resource_detail_effect_index)
            self.resource_detail_effect_index = int(effect_index)
            icons = getattr(self, "resource_detail_thumb_icons", None)
            if isinstance(icons, dict) and old_index != int(effect_index):
                replacements = {
                    (int(effect_index), key[1], key[2]): value
                    for key, value in list(icons.items())
                    if isinstance(key, tuple)
                    and len(key) == 3
                    and str(key[1]).casefold() == target_key
                }
                for key in list(icons):
                    if (
                        isinstance(key, tuple)
                        and len(key) == 3
                        and str(key[1]).casefold() == target_key
                    ):
                        icons.pop(key, None)
                icons.update(replacements)

    def _open_asset_detail(self, listed_index: int, asset_path: Path) -> None:
        """Show this asset in the detail tab."""
        if hasattr(self, "resource_tabs"):
            self.resource_tabs.setCurrentIndex(1)
        self._load_resource_detail(int(listed_index), asset_path.name)

    def _record_asset_password(self, asset_path: Path, password: str) -> tuple[bool, str]:
        """Append the password to pak.txt, matching the existing entry style."""
        provider = self.resource_provider.background_provider
        if provider is None:
            return (False, "素材提供者不可用。")
        pak_txt = Path(str(getattr(provider, "pak_password_path", "") or ""))
        if not str(pak_txt):
            return (False, "找不到 pak.txt 的位置。")
        try:
            data = pak_txt.read_bytes() if pak_txt.is_file() else b""
        except OSError as exc:
            return (False, "读取 pak.txt 失败：%s" % exc)
        encoding = "gb18030"
        for candidate in ("utf-8-sig", "utf-8", "gb18030"):
            try:
                existing = data.decode(candidate)
                encoding = candidate
                break
            except UnicodeDecodeError:
                continue
        else:
            return (False, "pak.txt 编码无法识别。")
        newline = "\r\n" if "\r\n" in existing else "\n"
        prefix = ""
        for line in existing.splitlines():
            candidate_line = line.strip()
            if not candidate_line or "|" not in candidate_line:
                continue
            recorded = PureWindowsPath(candidate_line.split("|", 1)[0].strip())
            if str(recorded.parent) not in ("", "."):
                prefix = str(recorded.parent)
                break
        entry_path = ("%s\\%s" % (prefix, asset_path.name)) if prefix else asset_path.name
        body = existing
        if body and not body.endswith(("\r\n", "\n")):
            body += newline
        body += "%s|%s%s" % (entry_path, password, newline)
        try:
            pak_txt.parent.mkdir(parents=True, exist_ok=True)
            pak_txt.write_bytes(body.encode(encoding, errors="strict"))
        except (OSError, UnicodeEncodeError) as exc:
            return (False, "写入 pak.txt 失败：%s" % exc)
        return (True, entry_path)

    def _discover_asset_files(self, provider: Any) -> list[Path]:
        """Every asset container in the configured search directories."""
        found: list[Path] = []
        seen: set[str] = set()
        directories = list(getattr(provider, "data_dirs", ()) or ())
        data_dir = getattr(provider, "data_dir", None)
        if data_dir is not None and data_dir not in directories:
            directories.append(data_dir)
        for directory in directories:
            try:
                entries = sorted(
                    Path(directory).iterdir(), key=lambda item: item.name.lower()
                )
            except OSError:
                continue
            for entry in entries:
                if not entry.is_file():
                    continue
                if entry.suffix.lower() not in _RESOURCE_RECORD_FILE_SUFFIXES:
                    continue
                try:
                    key = str(entry.resolve()).casefold()
                except OSError:
                    continue
                if key in seen:
                    continue
                seen.add(key)
                found.append(entry)
        return found

    @staticmethod
    def _known_asset_password(provider: Any, asset_path: Path) -> str:
        """Password pak.txt declares for this file, empty when absent."""
        if asset_path.suffix.lower() != ".pak":
            return ""
        try:
            return str(provider.password_for_file(asset_path.name) or "")
        except Exception:
            return ""

    def _effect_asset_path(self, file_name: str) -> Any:
        """Where this entry actually resolves to, or None when missing."""
        if not file_name or file_name.startswith("<"):
            return None
        provider = self.resource_provider.background_provider
        if provider is None:
            return None
        try:
            candidates = provider.data_file_candidates(file_name)
        except Exception:
            return None
        return candidates[0] if candidates else None

    def _effect_asset_exists(self, file_name: str) -> bool:
        if not file_name or file_name.startswith("<"):
            return True
        provider = self.resource_provider.background_provider
        if provider is None:
            return False
        try:
            return bool(provider.data_file_candidates(file_name))
        except Exception:
            return False

    def _effect_file_selected(self, item: Any, column: int = 0) -> None:
        # A locked asset has nothing to show; point at the right-click menu
        # rather than opening an empty detail tab.
        if isinstance(item, QTreeWidgetItem) and item.data(0, Qt.UserRole + 3):
            if bool(item.data(0, Qt.UserRole + 2)):
                name = Path(str(item.data(0, Qt.UserRole + 3))).name
                QMessageBox.information(
                    self,
                    "素材库",
                    "%s 无法读取。\n\n请右键点击该文件并填写密码。" % name,
                )
                return
        # Folder rows carry no payload; only leaf entries open a file.
        data = item.data(0, Qt.UserRole) if isinstance(item, QTreeWidgetItem) else item.data(Qt.UserRole)
        if not data:
            return
        effect_index, file_name = data
        file_name = str(file_name or "").strip()
        if not file_name:
            return
        if hasattr(self, "resource_tabs"):
            self.resource_tabs.setCurrentIndex(1)
        self._load_resource_detail(int(effect_index), file_name)

    def _load_resource_detail(self, effect_index: int, file_name: str) -> None:
        provider = self.resource_provider.background_provider
        if provider is None:
            return
        start_session = self._native_backend_session()
        self._sync_resource_auth_context(start_session)
        start_auth_context = (
            self._rpc_session_context(start_session)
            if isinstance(start_session, Mapping)
            else None
        )
        start_auth_generation = self._resource_auth_generation
        self.resource_detail_token = int(getattr(self, "resource_detail_token", 0)) + 1
        token = self.resource_detail_token
        self.resource_detail_request_id = int(
            getattr(self, "resource_detail_request_id", 0)
        ) + 1
        request_id = self.resource_detail_request_id
        settled = {"value": False}
        self.resource_detail_thumb_token = int(getattr(self, "resource_detail_thumb_token", 0)) + 1
        self.resource_detail_thumb_icons = {}
        self.resource_detail_effect_index = int(effect_index)
        self.resource_detail_file_name = str(file_name)
        self.resource_detail_records = []
        self.resource_detail_slots = []
        self._render_resource_details()
        self.status_label.setText(f"正在读取素材索引：{file_name}，界面可继续操作...")

        def work() -> tuple[str, object, str]:
            asset_path = None
            try:
                asset_path, password, _cache_key = self._resource_record_source(file_name)
                records = provider.records_for_file(
                    asset_path,
                    password,
                    asset_index=-1,
                    purpose="npc-resource",
                )
                return ("records", (asset_path, password, records), "")
            except FileNotFoundError:
                raise
            except NativeAssetAuthorizationError:
                raise
            except BaseException as exc:
                if asset_path is not None and asset_path.suffix.lower() == ".pak":
                    raise
                slots = self._probe_resource_slots(effect_index, file_name)
                return ("slots", slots, _error_text(exc))

        def done(result: object) -> None:
            if settled["value"] or request_id != self.resource_detail_request_id:
                return
            was_current = token == self.resource_detail_token
            current_session = self._native_backend_session()
            self._sync_resource_auth_context(current_session)
            current_auth_context = (
                self._rpc_session_context(current_session)
                if isinstance(current_session, Mapping)
                else None
            )
            if (
                current_auth_context != start_auth_context
                or self._resource_auth_generation != start_auth_generation
            ):
                settled["value"] = True
                if was_current and request_id == self.resource_detail_request_id:
                    self.status_label.setText(
                        f"素材索引读取已取消：{file_name} / 登录会话已变化，请重试"
                    )
                return
            if token != self.resource_detail_token:
                return
            settled["value"] = True
            kind, values, fallback_error = result
            if (
                kind == "records"
                and isinstance(values, tuple)
                and len(values) == 3
                and isinstance(values[2], list)
            ):
                _asset_path, _password, records = values
                self._populate_resource_detail_records(
                    token, effect_index, file_name, records, from_cache=False
                )
                return
            self.resource_detail_records = []
            self.resource_detail_slots = list(values) if isinstance(values, list) else []
            if fallback_error:
                self._log(f"素材索引读取失败，已回退槽位探测：{file_name} / {fallback_error}")
            if not self.resource_detail_slots:
                self._log(f"素材详情为空：{file_name}")
            self._render_resource_details()

        def failed(exc: object) -> None:
            if settled["value"] or request_id != self.resource_detail_request_id:
                return
            was_current = token == self.resource_detail_token
            current_session = self._native_backend_session()
            self._sync_resource_auth_context(current_session)
            current_auth_context = (
                self._rpc_session_context(current_session)
                if isinstance(current_session, Mapping)
                else None
            )
            if (
                current_auth_context != start_auth_context
                or self._resource_auth_generation != start_auth_generation
            ):
                settled["value"] = True
                if was_current and request_id == self.resource_detail_request_id:
                    self.status_label.setText(
                        f"素材索引读取已取消：{file_name} / 登录会话已变化，请重试"
                    )
                return
            if token != self.resource_detail_token:
                return
            settled["value"] = True
            if isinstance(exc, FileNotFoundError):
                self._show_missing_pak_message(file_name)
                return
            self.status_label.setText(f"素材详情加载失败：{file_name} / {_error_text(exc)}")

        def timed_out() -> None:
            if settled["value"] or request_id != self.resource_detail_request_id:
                return
            settled["value"] = True
            self.status_label.setText(
                f"素材索引读取超时：{file_name} / 请重试或重新登录"
            )

        QTimer.singleShot(_RESOURCE_DETAIL_LOAD_TIMEOUT_MS, timed_out)
        self._run_resource_detail_async(work, done, failed)

    def _run_resource_detail_async(self, work: Any, done: Any, failed: Any) -> None:
        runner = getattr(getattr(self, "context", None), "run_async", None)
        if callable(runner):
            runner(work, done, failed)
            return
        try:
            done(work())
        except BaseException as exc:
            failed(exc)

    def _populate_resource_detail_records(self, token: int, effect_index: int, file_name: str, records: object, *, from_cache: bool) -> None:
        if token != self.resource_detail_token or not isinstance(records, list):
            return
        self.resource_detail_records = records
        self.resource_detail_slots = list(range(len(records)))
        self.resource_detail_effect_index = int(effect_index)
        self.resource_detail_file_name = str(file_name)
        source = "缓存" if from_cache else "索引"
        self.status_label.setText(f"素材索引已加载：{effect_index:04d} {file_name} / {len(records)} 张（{source}）")
        self._render_resource_details()

    @staticmethod
    def _resource_candidate_probe(
        asset_path: Path, password: str
    ) -> tuple[str, str]:
        """Classify a cheap local PAK probe without misreporting format errors."""
        if asset_path.suffix.lower() != ".pak":
            return (_RESOURCE_PROBE_READABLE, "")
        try:
            from embedded_npc_visual.core.npc_preview.pak_asset_browser import read_magic
        except Exception as exc:
            return (_RESOURCE_PROBE_ERROR, _error_text(exc))
        try:
            magic = str(read_magic(asset_path) or "").upper()
        except Exception as exc:
            return (_RESOURCE_PROBE_ERROR, _error_text(exc))
        if magic in {"GOMPACK", "SWPAK"}:
            # The real loader handles these with frame scanning rather than a
            # password/index header, so the generic header probe is invalid.
            return (_RESOURCE_PROBE_READABLE, "")
        if magic == "GEEPAK2":
            # GEEPAK2 keeps password-dependent metadata separate from the
            # resource stream. A failed generic index decode cannot prove that
            # the supplied password is wrong, so allow pak.txt registration
            # without making a false password claim.
            try:
                if asset_path.stat().st_size < 266:
                    raise ValueError("GEEPAK2 文件头不完整")
                with asset_path.open("rb") as handle:
                    if handle.read(8) != b"\x07GEEPAK2":
                        raise ValueError("GEEPAK2 文件标识不正确")
            except Exception as exc:
                return (_RESOURCE_PROBE_ERROR, _error_text(exc))
            return (
                _RESOURCE_PROBE_UNVERIFIABLE,
                "GEEPAK2 密码不能通过本地文件头快速判定",
            )
        return (
            _RESOURCE_PROBE_UNVERIFIABLE,
            "素材密码将在服务器授权和原生 worker 打开时校验",
        )

    @staticmethod
    def _resource_candidate_opens(asset_path: Path, password: str) -> bool:
        status, _reason = NpcVisualV2Page._resource_candidate_probe(
            asset_path, password
        )
        return status in {
            _RESOURCE_PROBE_READABLE,
            _RESOURCE_PROBE_UNVERIFIABLE,
        }

    def _resource_record_source(self, file_name: str) -> tuple[Path, str, tuple[object, ...]]:
        provider = self.resource_provider.background_provider
        if provider is None:
            raise FileNotFoundError(file_name)
        candidates = provider.data_file_candidates(file_name)
        ordered = [
            path for path in candidates
            if path.suffix.lower() in _RESOURCE_RECORD_FILE_SUFFIXES
        ]
        if not ordered and Path(file_name).suffix.lower() in _RESOURCE_RECORD_INDEX_SUFFIXES:
            ordered = [
                path for path in candidates
                if path.suffix.lower() in _RESOURCE_RECORD_INDEX_SUFFIXES
            ]
        if not ordered:
            raise FileNotFoundError(file_name)

        def described(asset_path: Path) -> tuple[Path, str, tuple[object, ...]]:
            password = (
                provider.password_for_file(asset_path.name)
                if asset_path.suffix.lower() == ".pak"
                else ""
            )
            resolved_path = asset_path.resolve()
            stat = resolved_path.stat()
            return (
                asset_path,
                password,
                (resolved_path, password, stat.st_mtime_ns, stat.st_size),
            )

        for asset_path in ordered:
            described_source = described(asset_path)
            if self._resource_candidate_opens(asset_path, described_source[1]):
                return described_source
        # None opened; keep the first so the caller surfaces the real error.
        return described(ordered[0])

    def _resource_records_for_file(self, file_name: str) -> list[Any]:
        provider = self.resource_provider.background_provider
        if provider is None:
            return []
        asset_path, password, _cache_key = self._resource_record_source(file_name)
        return list(provider.records_for_file(asset_path, password))

    def _show_missing_pak_message(self, file_name: str) -> None:
        QMessageBox.warning(self, "素材库", "pak不存在请检查路径是否正确")
        self.status_label.setText(f"PAK不存在：{file_name}")

    def _probe_resource_slots(self, effect_index: int, file_name: str) -> list[int]:
        slots = []
        misses = 0
        for slot in range(500):
            image = self.resource_provider.get_image(effect_index, slot)
            if image is not None:
                slots.append(slot)
                misses = 0
                continue
            misses += 1
            if slots and misses >= 20:
                break

        return slots

    def _render_resource_details(self) -> None:
        if not hasattr(self, "resource_detail_list"):
            return
        self.resource_detail_thumb_token = int(getattr(self, "resource_detail_thumb_token", 0)) + 1
        thumb_token = self.resource_detail_thumb_token
        self._resource_detail_thumb_active = None
        self.resource_detail_list.blockSignals(True)
        self.resource_detail_list.setUpdatesEnabled(False)
        self.resource_detail_slot_rows = {}
        start = 0
        end = 0
        try:
            self.resource_detail_list.clear()
            if not self.resource_detail_slots:
                return
            end = len(self.resource_detail_slots)
            placeholder = getattr(
                self, "resource_detail_placeholder_icon", None
            ) or _placeholder_icon(QSize(64, 64), "")
            icons = getattr(self, "resource_detail_thumb_icons", {})
            for pos in range(start, end):
                slot = self.resource_detail_slots[pos]
                self.resource_detail_slot_rows[int(slot)] = pos
                item = QListWidgetItem((f"{slot:04d}"))
                item.setData(Qt.UserRole, (self.resource_detail_effect_index, self.resource_detail_file_name, slot))
                item.setToolTip(f"{self.resource_detail_file_name} #{slot:04d}")
                item.setIcon(icons.get(self._resource_detail_thumb_key(slot), placeholder))
                self.resource_detail_list.addItem(item)
        finally:
            self.resource_detail_list.setUpdatesEnabled(True)
            self.resource_detail_list.blockSignals(False)
        self.status_label.setText(f"素材库：{self.resource_detail_effect_index:04d} {self.resource_detail_file_name} / {len(self.resource_detail_slots)} 张")
        self._schedule_resource_detail_thumbnail_refresh()

    def _resource_detail_thumb_key(self, slot: int) -> tuple[int, str, int]:
        return (self.resource_detail_effect_index, self.resource_detail_file_name.casefold(), int(slot))

    def _schedule_resource_detail_thumbnail_refresh(self, *_args: object) -> None:
        if (
            not hasattr(self, "resource_detail_list")
            or not self.resource_detail_slots
            or self._resource_detail_thumb_refresh_pending
        ):
            return
        thumb_token = self.resource_detail_thumb_token
        self._resource_detail_thumb_refresh_pending = True

        def trigger() -> None:
            self._resource_detail_thumb_refresh_pending = False
            if thumb_token != self.resource_detail_thumb_token:
                self._schedule_resource_detail_thumbnail_refresh()
                return
            start, end, _visible_start, _visible_end = (
                self._resource_detail_thumbnail_window()
            )
            self._start_resource_detail_thumbnail_load(start, end, thumb_token)

        QTimer.singleShot(0, trigger)

    def _resource_detail_thumbnail_window(self) -> tuple[int, int, int, int]:
        count = min(
            self.resource_detail_list.count(), len(self.resource_detail_slots)
        )
        if count <= 0:
            return (0, 0, 0, 0)

        detail_list = self.resource_detail_list
        viewport = detail_list.viewport()
        viewport_width = max(1, viewport.width())
        viewport_height = max(1, viewport.height())
        grid = detail_list.gridSize()
        column_count = max(1, int(getattr(detail_list, "_COLUMN_COUNT", 3)))
        grid_width = max(1, grid.width())
        grid_height = max(1, grid.height())
        x_points = [
            min(viewport_width - 1, column * grid_width + grid_width // 2)
            for column in range(column_count)
        ]
        y_step = max(8, min(24, grid_height // 3))
        y_points = list(range(0, viewport_height, y_step))
        if not y_points or y_points[-1] != viewport_height - 1:
            y_points.append(viewport_height - 1)

        visible_rows = []
        for y in y_points:
            for x in x_points:
                model_index = detail_list.indexAt(QPoint(x, y))
                if model_index.isValid():
                    row = int(model_index.row())
                    if 0 <= row < count:
                        visible_rows.append(row)

        if visible_rows:
            visible_start = (min(visible_rows) // column_count) * column_count
            visible_end = min(
                count,
                ((max(visible_rows) // column_count) + 1) * column_count,
            )
        else:
            visible_start = 0
            visible_row_count = max(1, (viewport_height + grid_height - 1) // grid_height)
            visible_end = min(count, visible_row_count * column_count)

        prefetch_count = column_count * 2
        return (
            max(0, visible_start - prefetch_count),
            min(count, visible_end + prefetch_count),
            visible_start,
            visible_end,
        )

    def _resource_detail_thumbnail_positions(
        self, start: int, end: int
    ) -> list[int]:
        window_start, window_end, visible_start, visible_end = (
            self._resource_detail_thumbnail_window()
        )
        start = max(int(start), window_start)
        end = min(int(end), window_end)
        if start >= end:
            return []
        visible_start = max(start, visible_start)
        visible_end = min(end, visible_end)
        return (
            list(range(visible_start, visible_end))
            + list(range(visible_start - 1, start - 1, -1))
            + list(range(visible_end, end))
        )

    def _start_resource_detail_thumbnail_load(self, start: int, end: int, thumb_token: int) -> None:
        if thumb_token != self.resource_detail_thumb_token or start >= end:
            return
        detail_token = self.resource_detail_token
        active_key = (detail_token, thumb_token)
        if self._resource_detail_thumb_active == active_key:
            return
        effect_index = self.resource_detail_effect_index
        file_name = self.resource_detail_file_name
        icons = getattr(self, "resource_detail_thumb_icons", {})
        positions = self._resource_detail_thumbnail_positions(start, end)
        pending = []
        for position in positions:
            slot = self.resource_detail_slots[position]
            if self._resource_detail_thumb_key(slot) not in icons:
                pending.append(slot)
        if not pending:
            self.status_label.setText(f"素材库：{effect_index:04d} {file_name} / {len(self.resource_detail_slots)} 张")
            return
        chunk = pending[:4]
        records = self.resource_detail_records
        loaded_count = min(len(self.resource_detail_slots), len(icons))
        self.status_label.setText(f"PAK {effect_index:04d} {file_name} / 正在加载缩略图 {loaded_count}/{len(self.resource_detail_slots)}...")
        self._resource_detail_thumb_active = active_key

        def work() -> tuple[str, object]:
            if records and all(0 <= slot < len(records) for slot in chunk):
                return ("records", _load_thumbnail_batch([(slot, records[slot]) for slot in chunk]))
            return ("resources", [(slot, self.resource_provider.get_image(effect_index, slot)) for slot in chunk])

        def done(result: object) -> None:
            if self._resource_detail_thumb_active == active_key:
                self._resource_detail_thumb_active = None
            if detail_token != self.resource_detail_token or thumb_token != self.resource_detail_thumb_token:
                return
            mode, thumbnails = result
            for thumbnail in thumbnails:
                slot = int(thumbnail[0])
                icon = None
                try:
                    if mode == "records":
                        image = thumbnail[1]
                        if image is not None:
                            icon = QIcon(
                                _resource_detail_thumbnail_pixmap(
                                    _pil_to_pixmap(image)
                                )
                            )
                    else:
                        pixmap = self._pixmap_from_resource(thumbnail[1])
                        if pixmap is not None and not pixmap.isNull():
                            icon = QIcon(_resource_detail_thumbnail_pixmap(pixmap))
                except BaseException:
                    icon = None
                self.resource_detail_thumb_icons[self._resource_detail_thumb_key(slot)] = icon or self.resource_detail_placeholder_icon

                row = self.resource_detail_slot_rows.get(slot)
                if row is None:
                    continue
                item = self.resource_detail_list.item(row)
                if item is not None:
                    item.setIcon(
                        self.resource_detail_thumb_icons[
                            self._resource_detail_thumb_key(slot)
                        ]
                    )
            QTimer.singleShot(1, self._schedule_resource_detail_thumbnail_refresh)

        def failed(exc: object) -> None:
            if self._resource_detail_thumb_active == active_key:
                self._resource_detail_thumb_active = None
            if detail_token == self.resource_detail_token and thumb_token == self.resource_detail_thumb_token:
                self.status_label.setText(f"缩略图加载失败：{_error_text(exc)}")

        self._run_resource_detail_async(work, done, failed)

    def _resource_detail_icon(self, slot: int) -> QIcon | None:
        image = self.resource_provider.get_image(self.resource_detail_effect_index, int(slot))
        pixmap = self._pixmap_from_resource(image)
        if pixmap is None or pixmap.isNull():
            return
        return QIcon(_resource_detail_thumbnail_pixmap(pixmap))

    def _resource_detail_selected(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if not data:
            return
        _effect_index, file_name, slot = data
        selected_count = len(self.resource_detail_list.selectedItems())
        if selected_count > 1:
            self.status_label.setText(f"已选动态素材：{file_name} / {selected_count} 帧")
            return
        self.status_label.setText(f"已选素材：{file_name} #{int(slot):04d}")

    def _resource_detail_drag_tag(self, items: list[QListWidgetItem]) -> str:
        records: list[tuple[int, str, int]] = []
        for item in items:
            data = item.data(Qt.UserRole)
            if not isinstance(data, (tuple, list)) or len(data) < 3:
                self.status_label.setText("无法拖动：素材信息无效")
                return ""
            try:
                effect_index = int(data[0])
                slot = int(data[2])
            except (TypeError, ValueError):
                self.status_label.setText("无法拖动：素材编号无效")
                return ""
            records.append((effect_index, str(data[1] or ""), slot))

        if not records:
            return ""
        effect_index, file_name, _slot = records[0]
        source_names = {record[1].casefold() for record in records}
        if len(source_names) != 1:
            self.status_label.setText("无法生成动态图：请选择同一个 PAK 内的素材")
            return ""

        if any(record[0] < 0 for record in records):
            try:
                effect_index = self._ensure_effect_file_registered(file_name)
            except Exception as exc:
                self.status_label.setText(
                    "无法拖动：EffectImageList.txt 登记失败 / %s" % _error_text(exc)
                )
                return ""
            records = [(effect_index, name, slot) for _index, name, slot in records]

        source_keys = {(record[0], record[1].casefold()) for record in records}
        if len(source_keys) != 1 or effect_index < 0:
            self.status_label.setText("无法拖动：素材未登记到 EffectImageList.txt")
            return ""

        slots = sorted(record[2] for record in records)
        if len(slots) == 1:
            self.status_label.setText(f"拖动素材：{file_name} #{slots[0]:04d}")
            return f"<Img:{slots[0]}:{effect_index}:0:0>"

        expected_slots = list(range(slots[0], slots[0] + len(slots)))
        if slots != expected_slots:
            self.status_label.setText("无法生成动态图：多选素材编号必须连续")
            return ""
        self.status_label.setText(
            f"拖动动态素材：{file_name} #{slots[0]:04d}-#{slots[-1]:04d} / {len(slots)} 帧"
        )
        return f"<PlayImg:{effect_index}:{slots[0]}:{len(slots)}:100:0:0:0>"

    def _resource_detail_double_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if not data:
            return
        effect_index, file_name, slot = data
        self.resource_detail_effect_index = int(effect_index)
        self.resource_detail_file_name = str(file_name)
        try:
            position = self.resource_detail_slots.index(int(slot))
        except ValueError:
            return
        previous = self.resource_preview_dialog
        if previous is not None:
            try:
                previous.close()
            except RuntimeError:
                pass
        pixmap = self._resource_detail_preview_pixmap(int(effect_index), int(slot))
        if pixmap is None or pixmap.isNull():
            self.status_label.setText(f"素材预览失败：{file_name} #{int(slot):04d}")
            return
        title = self._resource_preview_title(str(file_name), int(slot), pixmap)
        dialog = _ResourcePreviewDialog(
            pixmap,
            title,
            lambda: self._navigate_resource_preview(-1),
            lambda: self._navigate_resource_preview(1),
            self,
        )
        self.resource_preview_dialog = dialog
        self.resource_preview_position = position
        dialog.set_preview(pixmap, title, position > 0, position < len(self.resource_detail_slots) - 1)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self.status_label.setText(f"素材：{file_name} #{int(slot):04d} / {pixmap.width()} x {pixmap.height()}")

    def _navigate_resource_preview(self, delta: int) -> None:
        offset = int(delta)
        if offset == 0:
            return
        dialog = self.resource_preview_dialog
        if dialog is None:
            return
        step = 1 if offset > 0 else -1
        position = self.resource_preview_position + offset
        skipped = 0
        pixmap = None
        slot = -1
        while 0 <= position < len(self.resource_detail_slots):
            slot = int(self.resource_detail_slots[position])
            pixmap = self._resource_detail_preview_pixmap(self.resource_detail_effect_index, slot)
            if pixmap is not None and not pixmap.isNull():
                break
            skipped += 1
            position += step
        if pixmap is None or pixmap.isNull() or not 0 <= position < len(self.resource_detail_slots):
            if step > 0:
                dialog.next_button.setEnabled(False)
                direction = "后面"
            else:
                dialog.previous_button.setEnabled(False)
                direction = "前面"
            suffix = f"，已跳过 {skipped} 个无效素材" if skipped else ""
            self.status_label.setText(f"{direction}没有可预览素材{suffix}")
            return
        title = self._resource_preview_title(self.resource_detail_file_name, slot, pixmap)
        self.resource_preview_position = position
        dialog.set_preview(pixmap, title, position > 0, position < len(self.resource_detail_slots) - 1)
        skipped_text = f"，跳过 {skipped} 个无效素材" if skipped else ""
        self.status_label.setText(
            f"素材：{self.resource_detail_file_name} #{slot:04d} / {pixmap.width()} x {pixmap.height()}{skipped_text}"
        )

    @staticmethod
    def _resource_preview_title(file_name: str, slot: int, pixmap: QPixmap) -> str:
        return f"素材预览 - {file_name} #{slot:04d} - {pixmap.width()} x {pixmap.height()}"

    def _resource_detail_preview_pixmap(self, effect_index: int, slot: int) -> QPixmap | None:
        records = self.resource_detail_records
        if records and 0 <= int(slot) < len(records):
            try:
                return _pil_to_pixmap(_load_record_image(records[int(slot)]))
            except BaseException as exc:
                self._log(
                    f"素材记录预览失败，已回退资源提供器："
                    f"{self.resource_detail_file_name} #{int(slot):04d} / {_error_text(exc)}"
                )
        return self._pixmap_from_resource(self.resource_provider.get_image(effect_index, slot))

    def _context_value(self, name: str) -> str:
        getter = getattr(self.context, name, None)
        if not callable(getter):
            return ""
        try:
            return str(getter() or "")
        except Exception:
            return ""

    def _source_for_render(self, source: str) -> str:
        return self._expand_call_source(self._strip_call_expansion(source), seen=set(), depth=0)

    def _strip_call_expansion(self, source: str) -> str:
        marker_index = source.find(_CALL_EXPANDED_MARKER)
        if marker_index < 0:
            return source
        return source[:marker_index].rstrip() + "\n"

    def _expand_call_source(self, source: str, seen: set[str], depth: int) -> str:
        if depth >= 8:
            return source
        parts = [
         source]
        for match in _CALL_RE.finditer(source):
            call_path = match.group("path")
            file_path = self._resolve_call_file(call_path)
            if file_path is None:
                continue
            else:
                key = str(file_path).casefold()
                if key in seen:
                    continue
                else:
                    seen.add(key)
                    call_source = self._read_call_file(file_path)
                    if not call_source:
                        continue
                    else:
                        expanded = self._expand_call_source(call_source, seen=seen, depth=(depth + 1))
                        parts.append(f"\n\n; ---- #CALL {_normalize_call_path(call_path)} ----\n")
                        parts.append(expanded)
        return "".join(parts)

    def _resolve_call_file(self, call_path: str) -> Path | None:
        rel = _normalize_call_path(call_path)
        if not rel:
            return
        rel_path = Path(rel)
        if any((part == ".." for part in rel_path.parts)):
            return
        quest_root = self._quest_diary_root()
        if quest_root is None:
            return
        candidate = quest_root / rel_path
        if candidate.is_file():
            return candidate

    def _quest_diary_root(self) -> Path | None:
        version_path = self._context_value("get_version_path")
        if version_path:
            root = Path(version_path)
            if root.name.casefold() == "questdiary":
                return root
            if root.name.casefold() == "envir":
                return root / "QuestDiary"
            if (root / "QuestDiary").is_dir():
                return root / "QuestDiary"
            if (root / "Mir200" / "Envir" / "QuestDiary").is_dir():
                return root / "Mir200" / "Envir" / "QuestDiary"
            if (root / "Envir" / "QuestDiary").is_dir():
                return root / "Envir" / "QuestDiary"
            return root / "Mir200" / "Envir" / "QuestDiary"
        current_path = Path(self.current_path) if self.current_path else None
        if current_path is None:
            return
        for parent in current_path.parents:
            if parent.name.casefold() == "envir":
                return parent / "QuestDiary"

    def _read_call_file(self, path: Path) -> str:
        override = self._call_source_override(path)
        if override is not None:
            return override
        with contextlib.suppress(Exception):
            text, _encoding = self.context.read_text_file(str(path))
            self._remember_source_file_identity(path)
            return text
        try:
            data = path.read_bytes()
        except Exception:
            return ""
        for encoding in ("utf-8-sig", "gb18030", "cp936"):
            try:
                text = data.decode(encoding)
                self._remember_source_file_identity(path, data)
                return text
            except UnicodeDecodeError:
                continue
        text = data.decode("utf-8", errors="replace")
        self._remember_source_file_identity(path, data)
        return text

    def _native_backend_session(self) -> dict[str, Any] | None:
        getter = getattr(self.context, "get_native_session", None)
        if not callable(getter):
            getter = getattr(self.context, "get_session", None)
        if not callable(getter):
            version_getter = getattr(self.context, "get_version_path", None)
            host = getattr(version_getter, "__self__", None)
            toolbox_context = getattr(host, "toolbox_context", None)
            getter = getattr(toolbox_context, "get_session", None)
        if not callable(getter):
            return None
        try:
            session = getter()
        except Exception:
            return None
        if not isinstance(session, dict):
            return None
        required = ("token", "device_id", "server")
        if any(not isinstance(session.get(name), str) or not session.get(name).strip() for name in required):
            return None
        return dict(session)

    def _source_identity_key(self, path: str | Path) -> str:
        try:
            return os.path.normcase(os.path.abspath(os.path.normpath(str(path))))
        except Exception:
            return str(path).casefold()

    def _source_file_identity(self, path: str | Path, raw: bytes | None = None) -> tuple[int, int, str]:
        target = Path(path)
        if raw is None:
            raw = target.read_bytes()
        stat = target.stat()
        if len(raw) != int(stat.st_size):
            raise RuntimeError("NPC 源文件在读取期间发生变化")
        return (
            int(stat.st_size),
            int(stat.st_mtime_ns),
            hashlib.sha256(raw).hexdigest(),
        )

    def _remember_source_file_identity(self, path: str | Path, raw: bytes | None = None) -> None:
        target = Path(path)
        if not target.is_file() or target.is_symlink():
            return
        self._source_file_identities[self._source_identity_key(target)] = self._source_file_identity(target, raw)

    def _call_source_key(self, path: str | Path) -> str:
        try:
            return str(Path(path).resolve()).casefold()
        except Exception:
            return str(path).casefold()

    def _set_call_source_override(self, path: str | Path, text: str) -> None:
        if not path:
            return
        self._call_source_overrides[self._call_source_key(path)] = text

    def _call_source_override(self, path: str | Path) -> str | None:
        if not path:
            return None
        return self._call_source_overrides.get(self._call_source_key(path))

    def _effective_render_label(self, source: str, selected_label: str) -> str:
        block = self._exact_label_block(selected_label)
        if block is not None and block.say_blocks:
            return selected_label
        call_label = self._first_call_target_for_label(source, selected_label)
        if call_label:
            if self._exact_label_block(call_label) is not None:
                return call_label
        return selected_label

    def _exact_label_block(self, label: str) -> Any:
        if not label or self.document is None:
            return
        needle = label.casefold()
        for block in self.document.labels:
            if block.label.casefold() == needle:
                return block

    def _first_call_target_for_label(self, source: str, label: str) -> str:
        if not label:
            return ""
        matches = list(_LABEL_HEADER_RE.finditer(source))
        for (index, match) in enumerate(matches):
            if match.group("label").strip().casefold() != label.casefold():
                continue
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
            call_match = _CALL_RE.search(source[start:end])
            return call_match.group("label").strip() if call_match else ""

        return ""

    def _load_labels(self) -> None:
        self.label_list.blockSignals(True)
        try:
            self.label_list.clear()
            if self.document is not None:
                for index, label in enumerate(self.document.label_names()):
                    item = QListWidgetItem(label)
                    item.setData(Qt.UserRole, label)
                    item.setData(Qt.UserRole + 1, index)
                    self.label_list.addItem(item)
                if self.label_list.count():
                    self.label_list.setCurrentRow(0)
        finally:
            self.label_list.blockSignals(False)

        current = self.label_list.currentItem()
        if current is not None:
            self._label_item_changed(current, None)
        else:
            self.render_current_source()

    def _label_item_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current is None:
            return
        label = str(current.data(Qt.UserRole) or "")
        index = self._item_label_index(current)
        self.render_current_source()
        source = self._render_base_source()
        block, effective_label = self._effective_render_block(source, label, index)
        if block is not None:
            self._jump_to_label_block(block)
        else:
            self._jump_to_label_source(effective_label or label)

    def render_current_source(self, selection_hint: Any = None) -> None:
        if isinstance(selection_hint, bool):
            selection_hint = None
        source = self._render_base_source()
        file_key = self.current_path or "__editor__"
        current_label = self._current_label()
        current_index = self._current_label_index()
        render_source = self._source_for_render(source)
        try:
            self.document = self._parse_render_document(render_source, file_key)
        except Exception as exc:
            self.document = None
            self.layout_document = None
            self.label_list.blockSignals(True)
            try:
                self.label_list.clear()
            finally:
                self.label_list.blockSignals(False)
            message = _error_text(exc)
            self.status_label.setText("NPC 服务器核心解析失败")
            self._log("NPC 服务器核心解析失败：%s" % message)
            return None
        main_label = self._main_or_first_document_label(self.document)
        rendering_main_label = bool(current_label and main_label and current_label.casefold() == main_label.casefold())
        fallback_background = self._main_background_node(source, file_key, document=self.document)
        block, label = self._effective_render_block(source, current_label, current_index)
        self.layout_document = self.engine.layout_engine.layout(
            block,
            image_size_resolver=self._measure_node_size,
            fallback_background_node=fallback_background,
        )
        if rendering_main_label:
            self._main_background_cache_key = (file_key, source)
            self._main_background_cache = self.layout_document.background.node if self.layout_document.background is not None else None
        self._paint_layout(self.layout_document)
        self._restore_selection(selection_hint)
        self.status_label.setText(f'已渲染：{label or "无标签"} / {len(self.layout_document.components)} 个组件')

    def _render_base_source(self) -> str:
        if self.template_mode:
            self.primary_source = self.source_editor.toPlainText()
            return self.primary_source
        if self.source_view_path and self.current_path and self.source_view_path == self.current_path:
            self.primary_source = self.source_editor.toPlainText()
            return self.primary_source
        if self.source_view_path and self.current_path and self.source_view_path != self.current_path:
            self._set_call_source_override(self.source_view_path, self.source_editor.toPlainText())
        return self.primary_source or self.source_editor.toPlainText()

    def _current_label(self) -> str:
        item = self.label_list.currentItem()
        if item is not None:
            return str(item.data(Qt.UserRole) or "")
        if self.document:
            if self.document.labels:
                return self.document.labels[0].label
            return ""
        return ""

    def _current_label_index(self) -> int | None:
        return self._item_label_index(self.label_list.currentItem())

    def _item_label_index(self, item: QListWidgetItem | None) -> int | None:
        if item is None:
            return
        try:
            return int(item.data(Qt.UserRole + 1))
        except Exception:
            return

    def _main_background_node(
        self,
        source: str,
        file_key: str,
        document: NpcDocument | None = None,
    ) -> Any | None:
        cache_key = (
         file_key, source)
        if self._main_background_cache_key == cache_key:
            return self._main_background_cache
        self._main_background_cache_key = cache_key
        self._main_background_cache = None
        render_source = self._source_for_render(source)
        source_document = document or self.engine.parse(
            render_source, file_key=f"{file_key}::main-background-source"
        )
        entry_label = self._main_or_first_document_label(source_document)
        if not entry_label:
            return
        source_block = self._label_block_from_document(source_document, entry_label)
        if source_block is not None and source_block.openmerchant is not None:
            self._main_background_cache = source_block.openmerchant
            return self._main_background_cache
        layout_doc = self.engine.layout_engine.layout(
            source_block,
            image_size_resolver=self._measure_node_size,
        )
        if layout_doc is not None:
            if layout_doc.background is not None:
                self._main_background_cache = layout_doc.background.node
            return self._main_background_cache

    def _main_or_first_document_label(self, document: NpcDocument | None) -> str:
        if document is None or not document.labels:
            return ""
        for block in document.labels:
            if block.label.casefold() == "@main":
                return block.label
        return document.labels[0].label

    def _main_or_first_source_label(self, source: str) -> str:
        first = ""
        for match in _LABEL_HEADER_RE.finditer(source):
            label = match.group("label").strip()
            if not first:
                first = label
            if label.casefold() == "@main":
                return label
        return first

    def _label_block_from_document(self, document: NpcDocument, label: str) -> Any:
        needle = str(label or "").casefold()
        for block in document.labels:
            if block.label.casefold() == needle:
                return block

        if document.labels:
            return document.labels[0]

    def _first_source_label(self, source: str) -> str:
        match = _LABEL_HEADER_RE.search(source)
        if match:
            return match.group("label").strip()
        return ""

    def _current_envir_root(self) -> Path | None:
        if self.current_path:
            try:
                path = Path(self.current_path)
            except Exception:
                path = None
            if path is not None:
                for parent in path.parents:
                    if parent.name.casefold() == "envir":
                        return parent
        version_path = self._context_value("get_version_path")
        if version_path:
            root = Path(version_path)
            if root.name.casefold() == "envir":
                return root
            if (root / "Mir200" / "Envir").is_dir():
                return root / "Mir200" / "Envir"
            if (root / "Envir").is_dir():
                return root / "Envir"

    def _runtime_text_loader(self, raw_path: str) -> str | None:
        envir_root = self._current_envir_root()
        if envir_root is None:
            return
        raw_value = str(raw_path or "").strip().strip('"\'')
        current_dir = None
        if self.current_path:
            try:
                current_dir = Path(self.current_path).parent
            except Exception:
                current_dir = None
        rel = _normalize_call_path(raw_path)
        candidates = []
        if raw_value:
            raw_candidate = Path(raw_value)
            if raw_candidate.is_absolute():
                candidates.append(raw_candidate)
            if current_dir is not None:
                candidates.append(current_dir / raw_value)
                candidates.append(current_dir / rel)
        lowered = rel.casefold()
        prefixes = ('../questdiary/', '..//questdiary/', 'questdiary/', '/questdiary/')
        for prefix in prefixes:
            if lowered.startswith(prefix):
                candidates.append(envir_root / "QuestDiary" / rel[len(prefix):])
        marker = "/questdiary/"
        if marker in lowered:
            pos = lowered.rfind(marker)
            candidates.append(envir_root / "QuestDiary" / rel[pos + len(marker):])
        candidates.append(envir_root / "QuestDiary" / rel)
        candidates.append(envir_root / rel)
        seen = set()
        for candidate in candidates:
            key = str(candidate).casefold()
            if key in seen:
                continue
            seen.add(key)
            if candidate.is_file():
                override = self._call_source_override(candidate)
                if override is not None:
                    return override
                return self._read_call_file(candidate)

    def _show_item_tooltip_async(
        self,
        component: LayoutComponent,
        global_pos: QPoint,
    ) -> None:
        node = component.node
        props = node.props or {}
        args = props.get("args")
        item_id = (
            self._itemshow_item_id(node, list(args))
            if isinstance(args, (list, tuple)) and args
            else None
        )
        self._item_tooltip_request_token += 1
        self._item_tooltip_hover_pos = QPoint(global_pos)
        if item_id is None:
            self.tooltip_overlay.show_component(
                component,
                global_pos,
                raw_tip="249#无法解析物品编号",
                default_code="249",
                transparent_background=False,
            )
            return

        request_token = self._item_tooltip_request_token
        context_generation = self._item_tooltip_context_generation
        asset_broker = self._item_tooltip_asset_broker()
        self.tooltip_overlay.show_component(
            component,
            global_pos,
            raw_tip="254#正在加载物品信息...",
            default_code="254",
            transparent_background=False,
        )

        def work() -> tuple[dict[str, Any], str]:
            return self._itemshow_tooltip_text(
                int(item_id),
                context_generation,
                asset_broker,
            )

        def done(result: tuple[dict[str, Any], str]) -> None:
            if not self._item_tooltip_request_is_current(
                request_token, context_generation
            ):
                return
            _dto, text = result
            position = self._item_tooltip_hover_pos or QPoint(global_pos)
            self.tooltip_overlay.show_component(
                component,
                position,
                raw_tip=text,
                default_code="255",
                transparent_background=False,
            )

        def failed(exc: BaseException) -> None:
            if not self._item_tooltip_request_is_current(
                request_token, context_generation
            ):
                return
            position = self._item_tooltip_hover_pos or QPoint(global_pos)
            self.tooltip_overlay.show_component(
                component,
                position,
                raw_tip="249#物品信息加载失败: " + _error_text(exc),
                default_code="249",
                transparent_background=False,
            )

        try:
            self.context.run_async(work, done, failed)
        except BaseException as exc:
            failed(exc)

    def _item_tooltip_request_is_current(
        self,
        request_token: int,
        context_generation: int,
    ) -> bool:
        return (
            request_token == self._item_tooltip_request_token
            and context_generation == self._item_tooltip_context_generation
            and self._item_tooltip_hover_pos is not None
        )

    def _open_local_item_tooltip_source(
        self,
        context_generation: int,
        source_identity: tuple[tuple[str, int, int], ...],
        source_paths: tuple[Path, Path | None, Path | None],
        asset_broker: Any,
    ) -> tuple[tuple, dict[str, Any]]:
        starter = getattr(asset_broker, "start", None)
        if not callable(starter):
            raise RuntimeError("原生物品信息工作进程不可用")
        try:
            worker_generation = int(starter())
        except Exception as exc:
            raise RuntimeError("原生物品信息工作进程不可用") from exc
        if worker_generation <= 0:
            raise RuntimeError("原生物品信息工作进程代次无效")

        while True:
            authorization_key = (source_identity, worker_generation)
            waiter_key = (context_generation, authorization_key)
            with self._item_tooltip_cache_lock:
                if context_generation != self._item_tooltip_context_generation:
                    raise RuntimeError("物品信息本地数据源已变化")
                stale_authorization_keys = [
                    key
                    for key in self._item_tooltip_authorizations
                    if key[1] != worker_generation
                ]
                for key in stale_authorization_keys:
                    self._item_tooltip_authorizations.pop(key, None)
                stale_cache_keys = [
                    key
                    for key in self._item_tooltip_cache
                    if key[1] != worker_generation
                ]
                for key in stale_cache_keys:
                    self._item_tooltip_cache.pop(key, None)
                authorization = self._item_tooltip_authorizations.get(
                    authorization_key
                )
                if authorization is not None:
                    return authorization_key, authorization
                waiter = self._item_tooltip_authorization_waiters.get(waiter_key)
                if waiter is None:
                    waiter = threading.Event()
                    self._item_tooltip_authorization_waiters[waiter_key] = waiter
                    owns_authorization = True
                else:
                    owns_authorization = False
            if owns_authorization:
                break
            if not waiter.wait(30.0):
                raise RuntimeError("物品信息本地数据集打开超时")
            try:
                worker_generation = int(starter())
            except Exception as exc:
                raise RuntimeError("原生物品信息工作进程不可用") from exc

        redundant: list[dict[str, Any]] = []
        try:
            candidate = dict(
                open_local_npc_tooltip_data(
                    source_paths[0],
                    source_paths[1],
                    source_paths[2],
                    asset_broker=asset_broker,
                )
            )
            try:
                candidate_generation = int(
                    candidate.get("worker_generation") or 0
                )
                current_worker_generation = int(
                    getattr(asset_broker, "generation", 0) or 0
                )
            except (TypeError, ValueError) as exc:
                raise RuntimeError("原生物品信息工作进程代次无效") from exc
            installed_key = (source_identity, candidate_generation)
            with self._item_tooltip_cache_lock:
                context_is_current = (
                    context_generation == self._item_tooltip_context_generation
                )
                can_install = (
                    context_is_current
                    and candidate_generation > 0
                    and candidate_generation == current_worker_generation
                )
                installed = (
                    self._item_tooltip_authorizations.get(installed_key)
                    if can_install
                    else None
                )
                if can_install:
                    obsolete_keys = [
                        key
                        for key in self._item_tooltip_authorizations
                        if key[1] == candidate_generation
                        and key != installed_key
                    ]
                    for key in obsolete_keys:
                        obsolete = self._item_tooltip_authorizations.pop(key, None)
                        if obsolete is not None:
                            redundant.append(obsolete)
                    obsolete_cache_keys = [
                        key
                        for key in self._item_tooltip_cache
                        if key[1] == candidate_generation
                        and key[0] != source_identity
                    ]
                    for key in obsolete_cache_keys:
                        self._item_tooltip_cache.pop(key, None)
                    if installed is None:
                        self._item_tooltip_authorizations[installed_key] = candidate
                        installed = candidate
                    else:
                        redundant.append(candidate)
            if installed is None or not context_is_current:
                redundant.append(candidate)
                raise RuntimeError("物品信息本地数据源已变化")
            return installed_key, installed
        finally:
            with self._item_tooltip_cache_lock:
                current_waiter = self._item_tooltip_authorization_waiters.get(
                    waiter_key
                )
                if current_waiter is waiter:
                    self._item_tooltip_authorization_waiters.pop(waiter_key, None)
                waiter.set()
            self._close_item_tooltip_authorizations(redundant, asset_broker)

    def _itemshow_tooltip_text(
        self,
        item_id: int,
        context_generation: int,
        asset_broker: Any,
    ) -> tuple[dict[str, Any], str]:
        source_identity, source_paths = self._item_tooltip_sources()
        authorization_key, authorization = self._open_local_item_tooltip_source(
            context_generation,
            source_identity,
            source_paths,
            asset_broker,
        )
        worker_generation = int(authorization.get("worker_generation") or 0)
        source_revision = str(authorization.get("source_revision") or "")
        cache_key = (
            source_identity,
            worker_generation,
            source_revision,
            int(item_id),
        )
        with self._item_tooltip_cache_lock:
            cached = self._item_tooltip_cache.get(cache_key)
        try:
            current_worker_generation = int(
                getattr(asset_broker, "generation", 0) or 0
            )
        except (TypeError, ValueError):
            current_worker_generation = 0
        if cached is not None and current_worker_generation == worker_generation:
            return cached
        try:
            dto = build_npc_item_tooltip(
                asset_broker,
                str(authorization.get("tooltip_handle") or ""),
                worker_generation,
                int(item_id),
                source_revision,
            )
        except BaseException:
            with self._item_tooltip_cache_lock:
                if (
                    self._item_tooltip_authorizations.get(authorization_key)
                    is authorization
                ):
                    self._item_tooltip_authorizations.pop(authorization_key, None)
            self._close_item_tooltip_authorizations((authorization,), asset_broker)
            raise
        normalized_dto = dict(dto)
        text = self._item_tooltip_text_from_dto(normalized_dto, int(item_id))
        result = (normalized_dto, text)
        try:
            cache_worker_generation = int(
                getattr(asset_broker, "generation", 0) or 0
            )
        except (TypeError, ValueError):
            cache_worker_generation = 0
        with self._item_tooltip_cache_lock:
            if (
                context_generation == self._item_tooltip_context_generation
                and cache_worker_generation == worker_generation
            ):
                if len(self._item_tooltip_cache) >= 256:
                    self._item_tooltip_cache.pop(next(iter(self._item_tooltip_cache)))
                self._item_tooltip_cache[cache_key] = result
        return result

    def _item_tooltip_sources(
        self,
    ) -> tuple[tuple[tuple[str, int, int], ...], tuple[Path, Path | None, Path | None]]:
        item_provider = getattr(self.resource_provider, "item_provider", None)
        candidates: list[Path] = []
        seen_candidates: set[str] = set()

        def add_candidate(path: Path) -> None:
            key = self._source_identity_key(path)
            if key not in seen_candidates:
                seen_candidates.add(key)
                candidates.append(path)

        resolved_item_db = getattr(item_provider, "item_looks_path", None)
        if resolved_item_db is not None:
            add_candidate(Path(resolved_item_db))
        configured_item_db = getattr(item_provider, "stditems_db_path", None)
        configured_database_path = self._context_value("get_database_path")
        configured_paths = [
            Path(configured_item_db) if configured_item_db else None,
            Path(configured_database_path) if configured_database_path else None,
        ]
        version_path = self._context_value("get_version_path")
        if version_path:
            configured_paths.append(Path(version_path))
        envir_root = self._current_envir_root()
        if envir_root is not None:
            configured_paths.append(envir_root)

        for configured in configured_paths:
            if configured is None:
                continue
            if configured.is_file():
                add_candidate(configured)
                continue
            search_directories = (
                configured,
                configured / "Mud2" / "DB",
                configured / "Mir200" / "Envir",
                configured / "Mir200",
            )
            for directory in search_directories:
                for name in ("ApexM2.db", "StdItems.DB"):
                    found = self._case_insensitive_file(directory / name)
                    if found is not None:
                        add_candidate(found)
        stditems_path = next(
            (
                path
                for path in candidates
                if path.is_file()
                and path.name.casefold() in {"apexm2.db", "stditems.db"}
            ),
            None,
        )
        if stditems_path is None:
            raise RuntimeError("未找到物品数据库")
        top_path = envir_root / "ItemDescTopList.txt" if envir_root is not None else None
        list_path = envir_root / "ItemDescList.txt" if envir_root is not None else None
        if top_path is not None and (
            not top_path.is_file() or top_path.stat().st_size <= 0
        ):
            top_path = None
        if list_path is not None and (
            not list_path.is_file() or list_path.stat().st_size <= 0
        ):
            list_path = None

        def identity(path: Path | None) -> tuple[str, int, int]:
            if path is None:
                return ("", 0, 0)
            stat = path.stat()
            return (
                self._source_identity_key(path),
                int(stat.st_size),
                int(stat.st_mtime_ns),
            )

        source_paths = (stditems_path, top_path, list_path)
        return tuple(identity(path) for path in source_paths), source_paths

    @staticmethod
    def _item_tooltip_text_from_dto(dto: Mapping[str, Any], item_id: int) -> str:
        if not bool(dto.get("found")):
            return f"251#物品 ID: {int(item_id)}\n249#未找到该物品"
        title = str(dto.get("title") or "").strip() or f"物品 {int(item_id)}"
        try:
            title_color = int(dto.get("title_color") or 251)
        except (TypeError, ValueError):
            title_color = 251
        lines = [f"{title_color}#{title}"]
        section_titles = {
            "attributes": "[基础属性]",
            "notes": "[装备备注]",
        }
        for section in dto.get("sections") or ():
            if not isinstance(section, Mapping):
                continue
            section_lines = section.get("lines")
            if not isinstance(section_lines, (list, tuple)) or not section_lines:
                continue
            section_title = section_titles.get(str(section.get("kind") or ""))
            if section_title:
                lines.append("254#" + section_title)
            for line in section_lines:
                if not isinstance(line, Mapping):
                    continue
                text = str(line.get("text") or "")
                if not text:
                    continue
                try:
                    color = int(line.get("color"))
                except (TypeError, ValueError):
                    color = 255
                lines.append(f"{color}#{text}")
        return "\n".join(lines)

    def _runtime_monster_field_loader(self, monster_name: str, field_name: str, _target_name: str | None = None) -> str | None:
        row = self._monster_rows_by_name().get(str(monster_name or "").strip().casefold())
        if row is None:
            return None
        value = row.get(str(field_name or "").strip().casefold())
        if value is None:
            return None
        return str(value).strip()

    def _monster_rows_by_name(self) -> dict[str, dict[str, Any]]:
        path = self._monster_db_path()
        if path is None:
            return {}
        if self._monster_cache_path == path:
            return self._monster_cache
        rows = self._load_monster_rows(path)
        self._monster_cache_path = path
        self._monster_cache = rows
        return rows

    def _monster_db_path(self) -> Path | None:
        configured = str(self._context_value("get_database_path") or "").strip()
        candidates = []
        if configured:
            configured_path = Path(configured)
            if configured_path.is_file():
                candidates.append(configured_path)
            elif configured_path.is_dir():
                candidates.extend(sorted(configured_path.glob("*.db")))
        envir_root = self._current_envir_root()
        if envir_root is not None:
            version_root = (
                envir_root.parent.parent
                if envir_root.name.casefold() == "envir"
                and envir_root.parent.name.casefold() == "mir200"
                else envir_root
            )
            db_dir = version_root / "Mud2" / "DB"
            monster_db = self._case_insensitive_file(db_dir / "Monster.DB")
            if monster_db is not None:
                candidates.append(monster_db)
            if db_dir.is_dir():
                candidates.extend(sorted(db_dir.glob("*.db")))
        seen = set()
        for candidate in candidates:
            key = str(candidate).casefold()
            if key in seen:
                continue
            seen.add(key)
            if self._database_has_table(candidate, "Monster"):
                return candidate
        return None

    def _database_has_table(self, path: Path, table_name: str) -> bool:
        if not path.is_file():
            return False
        if self._path_is_sqlite(path):
            conn = None
            try:
                conn = sqlite3.connect(str(path))
                row = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1",
                    (table_name,),
                ).fetchone()
                return row is not None
            except sqlite3.Error:
                return False
            finally:
                if conn is not None:
                    conn.close()
        return path.stem.casefold() == table_name.casefold()

    def _load_monster_rows(self, path: Path) -> dict[str, dict[str, Any]]:
        try:
            if self._path_is_sqlite(path):
                conn = sqlite3.connect(str(path))
                try:
                    table_row = conn.execute(
                        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND lower(name)=lower(?) LIMIT 1",
                        ("Monster",),
                    ).fetchone()
                    if table_row is None:
                        return {}
                    table_name = str(table_row[0])
                    columns = [str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table_name}")')]
                    name_index = next((index for index, name in enumerate(columns) if name.casefold() == "name"), None)
                    if name_index is None:
                        return {}
                    result = {}
                    for row in conn.execute(f'SELECT * FROM "{table_name}"'):
                        name = str(row[name_index] or "").strip()
                        if name:
                            result[name.casefold()] = {
                                columns[index].casefold(): row[index]
                                for index in range(min(len(columns), len(row)))
                            }
                    return result
                finally:
                    conn.close()
            if DbcTable is None:
                return {}
            table = DbcTable(str(path))
            columns = [str(column.name) for column in table.columns]
            name_index = next((index for index, name in enumerate(columns) if name.casefold() == "name"), None)
            if name_index is None:
                return {}
            result = {}
            for row in table.rows():
                name = str(row[name_index] or "").strip()
                if name:
                    result[name.casefold()] = {
                        columns[index].casefold(): row[index]
                        for index in range(min(len(columns), len(row)))
                    }
            return result
        except Exception as exc:
            self._log(f"Monster database load failed: {exc}")
            return {}

    def _case_insensitive_file(self, path: Path) -> Path | None:
        if path.is_file():
            return path
        parent = path.parent
        if not parent.is_dir():
            return
        target = path.name.casefold()
        for child in parent.iterdir():
            if child.is_file():
                if child.name.casefold() == target:
                    return child

    def _path_is_sqlite(self, path: Path) -> bool:
        try:
            with path.open("rb") as handle:
                return handle.read(16) == b"SQLite format 3\x00"
        except OSError:
            return False

    def _effective_render_block(self, source: str, selected_label: str, selected_index: int | None) -> tuple[Any | None, str]:
        if self.document is None:
            return (None, selected_label)
        block = None
        if selected_index is not None:
            if 0 <= selected_index < len(self.document.labels):
                candidate = self.document.labels[selected_index]
                if candidate.label.casefold() == selected_label.casefold():
                    block = candidate
        if block is None:
            block = self._exact_label_block(selected_label)
        if block is not None and block.say_blocks:
            return (
             block, block.label)
        if block is not None:
            start_index = self.document.labels.index(block)
            for candidate in self.document.labels[start_index + 1:]:
                if candidate.say_blocks:
                    return (candidate, candidate.label)
        call_label = self._first_call_target_for_label(source, selected_label)
        call_block = self._exact_label_block(call_label) if call_label else None
        if call_block is not None:
            return (call_block, call_block.label)
        return (block, selected_label)

    def _paint_layout(
        self,
        layout_doc: LayoutDocument,
        *,
        assets_prewarmed: bool = False,
    ) -> None:
        self._render_generation += 1
        render_generation = self._render_generation
        if not assets_prewarmed and self._queue_layout_asset_prewarm(
            layout_doc, render_generation
        ):
            return
        self.hide_component_tooltip()
        self._animation_timer.stop()
        self._animated_component_ids.clear()
        self._animation_elapsed_ms = 0
        self.scene.clear()
        self.component_items.clear()
        show_guides = self.grid_checkbox.isChecked()
        guide_pen = QPen(Qt.NoPen)
        background_pixmap = self._background_pixmap(layout_doc)
        if background_pixmap is not None:
            width = background_pixmap.width()
            height = background_pixmap.height()
        elif layout_doc.background is not None:
            width = layout_doc.background.rect.width
            height = layout_doc.background.rect.height
        else:
            width = layout_doc.width
            height = layout_doc.height
        layout_doc.width = width
        layout_doc.height = height
        self.scene.setSceneRect(QRectF(0, 0, width, height))
        grid_rect = QRectF(0, 0, width, height)
        resolution_label = getattr(self, "canvas_resolution_label", None)
        if resolution_label is not None:
            resolution_label.setText(f"{width} x {height}")
        if background_pixmap is not None:
            background_item = self.scene.addPixmap(background_pixmap)
            background_item.setPos(0, 0)
            background_item.setZValue(-100)
            background = self.scene.addRect(0, 0, width, height, guide_pen, QBrush(QColor(255, 255, 255, 0)))
            background.setZValue(-90)
        else:
            background = self.scene.addRect(0, 0, width, height, guide_pen, QBrush(QColor("#1c1f24")))
            background.setZValue(-100)
            if layout_doc.background is None:
                panel_left = 156
                panel_top = 157
                panel_width = 448
                panel_height = 246
                panel = self.scene.addRect(panel_left, panel_top, panel_width, panel_height, QPen(QColor(144, 111, 63), 2), QBrush(QColor(42, 37, 32, 245)))
                panel.setZValue(-95)
                inner = self.scene.addRect(panel_left + 8, panel_top + 8, panel_width - 16, panel_height - 16, QPen(QColor(72, 61, 48), 1), QBrush(QColor(255, 255, 255, 0)))
                inner.setZValue(-94)
                grid_rect = QRectF(panel_left + 2, panel_top + 2, panel_width - 4, panel_height - 4)
        if show_guides:
            self._add_canvas_grid(grid_rect, layout_doc)

        if layout_doc.background is not None:
            if background_pixmap is None:
                label = self.scene.addText(f"背景：{layout_doc.background.node.raw}")
                label.setDefaultTextColor(QColor("#d9a531"))
                label.setPos(8, 4)
                label.setZValue(-40)
        pending_item_components: dict[int, list[str]] = {}
        for component in sorted(layout_doc.components, key=lambda item: item.z_index):
            if _is_spacer_component(component):
                continue
            if component.node.kind == "itemshow":
                spec = self._node_resource_spec(component.node)
                item_id = (
                    int(spec[1])
                    if spec is not None and str(spec[0]).casefold() == "__item__"
                    else None
                )
                resource_image = (
                    self._component_resource_cache.get(("__item__", item_id))
                    if item_id is not None
                    else None
                )
                if item_id is not None and resource_image is None:
                    pending_item_components.setdefault(item_id, []).append(component.node.id)
            else:
                resource_image = self._resource_image_for_component(component)
            pixmap = self._pixmap_from_resource(resource_image)
            if self._should_skip_component_visual(component, pixmap, resource_image):
                continue
            origin = self._component_image_origin(component, pixmap, resource_image)
            item = _VisualComponentItem(self, component, pixmap=pixmap, image_origin=origin)
            self.scene.addItem(item)
            self.component_items[component.node.id] = item
            if self._component_is_animated(component.node):
                self._animated_component_ids.add(component.node.id)
        if pending_item_components:
            self._queue_item_resource_batch(render_generation, pending_item_components)
        if self._animated_component_ids:
            self._animation_timer.start()
        if self._canvas_manual_zoom:
            self._apply_canvas_zoom(self._canvas_zoom_scale, preserve_center=False)
        else:
            self.fit_canvas_to_view()

    def _add_canvas_grid(self, rect: QRectF, layout_doc: LayoutDocument) -> None:
        grid_size = max(8, int(layout_doc.row_height or 16))
        left = float(rect.left())
        top = float(rect.top())
        right = float(rect.right())
        bottom = float(rect.bottom())

        minor_pen = QPen(QColor(58, 139, 235, 70), 1, Qt.DotLine)
        major_pen = QPen(QColor(58, 139, 235, 135), 1, Qt.SolidLine)
        for pen in (minor_pen, major_pen):
            pen.setCosmetic(True)

        column = 0
        x = left
        while x <= right:
            line = self.scene.addLine(x, top, x, bottom, major_pen if column % 5 == 0 else minor_pen)
            line.setZValue(-50)
            column += 1
            x += grid_size
        row = 0
        y = top
        while y <= bottom:
            line = self.scene.addLine(left, y, right, y, major_pen if row % 5 == 0 else minor_pen)
            line.setZValue(-50)
            row += 1
            y += grid_size

    def fit_canvas_to_view(self) -> None:
        if not (hasattr(self, "view") and hasattr(self, "scene")):
            return
        rect = self.scene.sceneRect()
        if rect.width() <= 0 or rect.height() <= 0:
            return
        viewport = self.view.viewport().rect()
        if viewport.width() <= 0 or viewport.height() <= 0:
            return
        scale = min(viewport.width() / rect.width(), viewport.height() / rect.height(), 1.0)
        self._canvas_manual_zoom = False
        self._apply_canvas_zoom(scale, preserve_center=False)

    def _apply_canvas_zoom(self, scale: float, *, preserve_center: bool = True) -> None:
        if not hasattr(self, "view"):
            return
        scale = max(0.05, float(scale))
        center = (
            self.view.mapToScene(self.view.viewport().rect().center())
            if preserve_center
            else self.scene.sceneRect().center()
        )
        self.view.resetTransform()
        self.view.scale(scale, scale)
        self.view.centerOn(center)
        self._canvas_zoom_scale = scale
        percent = int(round(scale * 100))
        label = getattr(self, "canvas_zoom_label", None)
        if label is not None:
            label.setText(f"{percent}%")
        slider = getattr(self, "canvas_zoom_slider", None)
        if slider is not None:
            slider_value = max(slider.minimum(), min(slider.maximum(), percent))
            old_block = slider.blockSignals(True)
            try:
                slider.setValue(slider_value)
            finally:
                slider.blockSignals(old_block)

    def set_canvas_zoom_percent(self, value: int, _checked: bool = False) -> None:
        try:
            value = int(value)
        except (TypeError, ValueError):
            return
        slider = getattr(self, "canvas_zoom_slider", None)
        minimum = slider.minimum() if slider is not None else 80
        maximum = slider.maximum() if slider is not None else 260
        value = max(minimum, min(maximum, value))
        self._canvas_manual_zoom = True
        if not hasattr(self, "view"):
            return

        scale = value / 100.0
        self._apply_canvas_zoom(scale)

    def zoom_canvas_by(self, delta_percent: int, _checked: bool = False) -> None:
        if not hasattr(self, "view"):
            return
        current = self.view.transform().m11() or getattr(self, "_canvas_zoom_scale", 1.0) or 1.0
        self.set_canvas_zoom_percent(int(round(current * 100)) + int(delta_percent))

    def scroll_listview_at(self, x: int, y: int, wheel_delta: int) -> bool:
        layout_engine = getattr(self.engine, "layout_engine", None)
        regions = list(getattr(layout_engine, "list_view_regions", []) or [])
        if not regions:
            return False
        for (rect, container_id, max_offset, _direction) in reversed(regions):
            if not rect.x <= x <= rect.x + rect.width:
                continue
            if not rect.y <= y <= rect.y + rect.height:
                continue
            if max_offset <= 0:
                return False
            offsets = getattr(layout_engine, "list_view_scroll_offsets", None)
            if offsets is None:
                return False
            current = int(offsets.get(container_id, 0) or 0)
            row_height = self.layout_document.row_height if self.layout_document is not None else 16
            step = max(24, row_height * 3)
            updated = current - step if wheel_delta > 0 else current + step
            updated = max(0, min(max_offset, updated))
            if updated == current:
                return True
            offsets[container_id] = updated
            self.render_current_source(selection_hint=self.selected_component_id)
            self._log(f"ListView {container_id} 滚动：{updated}/{max_offset}")
            return True
        return False

    def _layout_asset_specs(self, layout_doc: LayoutDocument) -> list[tuple[str, int]]:
        specs: list[tuple[str, int]] = []
        seen: set[tuple[str, int]] = set()

        def add(file_id: Any, index: Any) -> None:
            text = str(file_id or "").strip()
            resolved_index = self._int_value(index)
            if (
                not text
                or text.casefold() == "__item__"
                or resolved_index is None
                or resolved_index < 0
            ):
                return
            key = (text.casefold(), resolved_index)
            if key in seen:
                return
            seen.add(key)
            specs.append((text, resolved_index))

        def collect(node: Any) -> None:
            if node is None:
                return
            kind = str(getattr(node, "kind", "") or "").casefold()
            args = getattr(node, "props", {}).get("args")
            if kind in {"playimg", "playimgex"} and isinstance(args, list) and len(args) >= 3:
                start = self._int_value(args[1])
                frame_count = self._int_value(args[2])
                if start is not None and frame_count is not None and frame_count > 0:
                    for frame_index in range(start, start + frame_count):
                        add(args[0], frame_index)
                return
            if kind == "monster":
                sequence = self._monster_sequence_for_node(node)
                if sequence is not None:
                    for frame_index in sequence.frames:
                        add(f"Mon{sequence.file_index}.wzl", frame_index)
                return
            if kind == "progressbar" and isinstance(args, list) and len(args) >= 6:
                add(args[2], args[3])
                start = self._int_value(args[4])
                frame_count = max(1, self._int_value(args[5]) or 1)
                if start is not None:
                    for frame_index in range(start, start + frame_count):
                        add(args[2], frame_index)
                return
            spec = self._node_resource_spec(node)
            if spec is not None:
                add(spec[0], spec[1])

        try:
            background = getattr(layout_doc, "background", None)
            collect(getattr(background, "node", None))
            for component in getattr(layout_doc, "components", ()) or ():
                collect(getattr(component, "node", None))
        except Exception:
            return []
        return specs

    def _relayout_with_cached_assets(
        self, layout_doc: LayoutDocument
    ) -> LayoutDocument:
        if self.document is None:
            return layout_doc
        label = str(getattr(layout_doc, "label", "") or "")
        block = self._exact_label_block(label) if label else None
        fallback_background = (
            layout_doc.background.node if layout_doc.background is not None else None
        )
        try:
            return self.engine.layout_engine.layout(
                block,
                image_size_resolver=self._measure_node_size,
                fallback_background_node=fallback_background,
            )
        except Exception as exc:
            self._log("NPC 素材预热后重新布局失败：%s" % _error_text(exc))
            return layout_doc

    def _queue_layout_asset_prewarm(
        self,
        layout_doc: LayoutDocument,
        render_generation: int,
    ) -> bool:
        warmer = getattr(self.resource_provider, "prewarm_images", None)
        specs = self._layout_asset_specs(layout_doc)
        if not callable(warmer) or not specs:
            return False
        if self._asset_prewarm_active:
            self._queued_asset_prewarm_request = (layout_doc, render_generation)
            self.status_label.setText("正在后台准备 NPC 素材，已切换到最新预览请求...")
            return True
        self._asset_prewarm_active = True
        start_session = self._native_backend_session()
        self._sync_resource_auth_context(start_session)
        start_auth_context = (
            self._rpc_session_context(start_session)
            if isinstance(start_session, Mapping)
            else None
        )
        start_auth_generation = self._resource_auth_generation
        self.status_label.setText("正在后台准备 NPC 素材，界面可继续操作...")

        def work() -> int:
            return int(warmer(specs))

        def done(_count: object) -> None:
            self._asset_prewarm_active = False
            current_session = self._native_backend_session()
            self._sync_resource_auth_context(current_session)
            current_auth_context = (
                self._rpc_session_context(current_session)
                if isinstance(current_session, Mapping)
                else None
            )
            if (
                current_auth_context != start_auth_context
                or self._resource_auth_generation != start_auth_generation
            ):
                self._resume_queued_asset_prewarm()
                return
            if render_generation != self._render_generation:
                self._resume_queued_asset_prewarm()
                return
            prepared_layout = self._relayout_with_cached_assets(layout_doc)
            self.layout_document = prepared_layout
            self._paint_layout(prepared_layout, assets_prewarmed=True)
            self._restore_selection(self.selected_component_id)
            self._queued_asset_prewarm_request = None

        def failed(exc: BaseException) -> None:
            self._asset_prewarm_active = False
            current_session = self._native_backend_session()
            self._sync_resource_auth_context(current_session)
            current_auth_context = (
                self._rpc_session_context(current_session)
                if isinstance(current_session, Mapping)
                else None
            )
            if (
                current_auth_context != start_auth_context
                or self._resource_auth_generation != start_auth_generation
            ):
                self._resume_queued_asset_prewarm()
                return
            if render_generation != self._render_generation:
                self._resume_queued_asset_prewarm()
                return
            self._log("NPC 素材后台准备失败：%s" % _error_text(exc))
            self._paint_layout(layout_doc, assets_prewarmed=True)
            self._queued_asset_prewarm_request = None

        self.context.run_async(work, done, failed)
        return True

    def _resume_queued_asset_prewarm(self) -> None:
        request = self._queued_asset_prewarm_request
        self._queued_asset_prewarm_request = None
        if request is None:
            return
        layout_doc, render_generation = request
        if render_generation != self._render_generation:
            return
        if not self._queue_layout_asset_prewarm(layout_doc, render_generation):
            self.layout_document = layout_doc
            self._paint_layout(layout_doc, assets_prewarmed=True)
            self._restore_selection(self.selected_component_id)

    def _background_pixmap(self, layout_doc: LayoutDocument) -> QPixmap | None:
        self._sync_resource_auth_context(self._native_backend_session())
        node = layout_doc.background.node if layout_doc.background is not None else None
        if node is None:
            return
        file_id = node.props.get("file")
        index = self._int_value(node.props.get("index"))
        if file_id is None or index is None:
            return
        return self._pixmap_from_resource(self.resource_provider.get_image(str(file_id), index))

    def _measure_node_size(self, node: Any) -> tuple[int, int] | None:
        if getattr(node, "kind", "") == "itemshow":
            return (36, 36)
        if getattr(node, "kind", "") == "progressbar":
            return None
        spec = self._node_resource_spec(node)
        if spec is None or str(spec[0]).casefold() == "__item__":
            return None
        getter = getattr(self.resource_provider, "get_cached_image", None)
        resource = getter(spec[0], spec[1]) if callable(getter) else None
        if resource is None or resource.image is None or not hasattr(resource.image, "size"):
            return
        width, height = resource.image.size
        return (
         int(width), int(height))

    @staticmethod
    def _component_image_origin(
        component: LayoutComponent,
        pixmap: QPixmap | None,
        resource_image: ResourceImage | None,
    ) -> tuple[int, int]:
        if component.node.kind == "itemshow" and pixmap is not None:
            return (
                max(0, (int(component.visual_rect.width) - pixmap.width()) // 2),
                max(0, (int(component.visual_rect.height) - pixmap.height()) // 2),
            )
        if resource_image is not None:
            return (int(resource_image.origin_x), int(resource_image.origin_y))
        return (0, 0)

    def _queue_item_resource_batch(
        self,
        render_generation: int,
        pending_item_components: dict[int, list[str]],
    ) -> None:
        start_session = self._native_backend_session()
        self._sync_resource_auth_context(start_session)
        start_auth_context = (
            self._rpc_session_context(start_session)
            if isinstance(start_session, Mapping)
            else None
        )
        start_auth_generation = self._resource_auth_generation
        self._item_resource_batch_token = int(
            getattr(self, "_item_resource_batch_token", 0)
        ) + 1
        batch_token = self._item_resource_batch_token
        item_ids = tuple(pending_item_components)
        asset_gate = getattr(self.resource_provider, "_asset_gate", None)
        batch_snapshot = None
        if isinstance(asset_gate, NativeAssetReadGate):
            try:
                batch_snapshot = asset_gate.capture_snapshot()
                asset_gate.ensure_snapshot_current(batch_snapshot)
            except NativeAssetAuthorizationError:
                batch_snapshot = None

        def load_batch() -> list[tuple[int, ResourceImage | None, str]]:
            active_snapshot = batch_snapshot

            def worker_error_from(exc: BaseException | None, message: str) -> bool:
                current = exc
                seen = set()
                while isinstance(current, BaseException) and id(current) not in seen:
                    if isinstance(
                        current,
                        (NativeAssetWorkerError, NativeAssetAuthorizationError),
                    ):
                        return True
                    seen.add(id(current))
                    current = current.__cause__ or current.__context__
                lowered = str(message or "").casefold()
                return any(
                    marker in lowered
                    for marker in (
                        "native asset worker",
                        "expired worker generation",
                        "stale handle",
                        "worker generation",
                    )
                )

            def load_one(
                item_id: int,
                snapshot: AssetAuthorizationSnapshot | None,
            ) -> tuple[int, ResourceImage | None, str, bool]:
                try:
                    if snapshot is None:
                        resource = self.resource_provider.get_item_image(item_id)
                    else:
                        resource = self.resource_provider.get_item_image(
                            item_id, _snapshot=snapshot
                        )
                except Exception as exc:
                    error = _error_text(exc)
                    return (item_id, None, error, worker_error_from(exc, error))
                error = "" if resource is not None else str(
                    getattr(self.resource_provider, "last_status", "")
                    or "素材未返回"
                )
                return (
                    item_id,
                    resource,
                    error,
                    resource is None and worker_error_from(None, error),
                )

            results: dict[int, tuple[int, ResourceImage | None, str, bool]] = {}
            worker_failed = False
            for item_id in item_ids:
                result = load_one(item_id, active_snapshot)
                results[item_id] = result
                if result[3]:
                    worker_failed = True
                    break

            if worker_failed and isinstance(asset_gate, NativeAssetReadGate):
                asset_gate.clear()
                try:
                    active_snapshot = asset_gate.capture_snapshot()
                    asset_gate.ensure_snapshot_current(active_snapshot)
                except NativeAssetAuthorizationError:
                    active_snapshot = None
                for item_id in item_ids:
                    previous = results.get(item_id)
                    if previous is not None and previous[1] is not None:
                        continue
                    results[item_id] = load_one(item_id, active_snapshot)
            else:
                for item_id in item_ids:
                    if item_id not in results:
                        results[item_id] = load_one(item_id, active_snapshot)
                for item_id in item_ids:
                    previous = results[item_id]
                    if previous[1] is None:
                        results[item_id] = load_one(item_id, active_snapshot)

            return [
                (item_id, results[item_id][1], results[item_id][2])
                for item_id in item_ids
            ]

        self.context.run_async(
            load_batch,
            partial(
                self._item_resource_batch_succeeded,
                render_generation,
                batch_token,
                pending_item_components,
                start_auth_context,
                start_auth_generation,
            ),
            partial(
                self._item_resource_batch_failed,
                render_generation,
                batch_token,
                start_auth_context,
                start_auth_generation,
            ),
        )

    def _item_resource_batch_succeeded(
        self,
        render_generation: int,
        batch_token: int,
        pending_item_components: dict[int, list[str]],
        start_auth_context: tuple[str, str, str, str, int] | None,
        start_auth_generation: int,
        results: list[tuple[int, ResourceImage | None, str]],
    ) -> None:
        current_session = self._native_backend_session()
        self._sync_resource_auth_context(current_session)
        current_auth_context = (
            self._rpc_session_context(current_session)
            if isinstance(current_session, Mapping)
            else None
        )
        if (
            current_auth_context != start_auth_context
            or self._resource_auth_generation != start_auth_generation
        ):
            return
        if (
            render_generation != self._render_generation
            or batch_token != getattr(self, "_item_resource_batch_token", 0)
        ):
            return
        for item_id, resource, error in results:
            if resource is None:
                if error:
                    self._log(f"ItemShow 物品 {item_id} 未渲染：{error}")
                continue
            normalized = ResourceImage(
                resource.image,
                0,
                0,
                resource.file_name,
                resource.status,
            )
            self._component_resource_cache[("__item__", item_id)] = normalized
            pixmap = self._pixmap_from_resource(normalized)
            if pixmap is None:
                continue
            for component_id in pending_item_components.get(item_id, ()):
                item = self.component_items.get(component_id)
                if item is None:
                    continue
                origin = self._component_image_origin(item.component, pixmap, normalized)
                item.update_pixmap(pixmap, origin)

    def _item_resource_batch_failed(
        self,
        render_generation: int,
        batch_token: int,
        start_auth_context: tuple[str, str, str, str, int] | None,
        start_auth_generation: int,
        exc: BaseException,
    ) -> None:
        current_session = self._native_backend_session()
        self._sync_resource_auth_context(current_session)
        current_auth_context = (
            self._rpc_session_context(current_session)
            if isinstance(current_session, Mapping)
            else None
        )
        if (
            current_auth_context != start_auth_context
            or self._resource_auth_generation != start_auth_generation
        ):
            return
        if (
            render_generation != self._render_generation
            or batch_token != getattr(self, "_item_resource_batch_token", 0)
        ):
            return
        self._log(f"ItemShow 后台素材加载失败：{_error_text(exc)}")

    def _resource_image_for_component(self, component: LayoutComponent) -> ResourceImage | None:
        return self._resource_image_for_node(component.node)

    def _resource_image_for_node(self, node: Any) -> ResourceImage | None:
        self._sync_resource_auth_context(self._native_backend_session())
        if getattr(node, "kind", "") == "progressbar":
            return self._progressbar_resource_for_node(node)
        if getattr(node, "kind", "") == "monster":
            sequence = self._monster_sequence_for_node(node)
            if sequence is None or not sequence.frames:
                return None
            frame_index = sequence.frames[
                (self._animation_elapsed_ms // max(1, sequence.interval_ms))
                % len(sequence.frames)
            ]
            cache_key = ("__monster__", sequence.file_index, frame_index)
            if cache_key not in self._component_resource_cache:
                resource = self.resource_provider.get_monster_image(sequence.file_index, frame_index)
                if resource is not None:
                    self._component_resource_cache[cache_key] = resource
            else:
                resource = self._component_resource_cache[cache_key]
            if resource is None:
                self._report_missing_resource(node)
            return resource
        if getattr(node, "kind", "") in {"playimg", "playimgex"}:
            args = node.props.get("args")
            frame_index = self._playimg_frame_index(node)
            if not isinstance(args, list) or not args or frame_index is None:
                return None
            file_id_value = self._int_value(args[0])
            file_id = file_id_value if file_id_value is not None else str(args[0])
            transparent_mode = _uses_transparent_effect_mode(node)
            cache_key = ("__playimg__", str(file_id), int(frame_index), transparent_mode)
            if cache_key not in self._component_resource_cache:
                resource = self.resource_provider.get_image(file_id, frame_index)
                if resource is not None:
                    if transparent_mode:
                        resource = self._transparent_effect_resource(resource)
                    resource = ResourceImage(resource.image, 0, 0, resource.file_name, resource.status)
                if resource is not None:
                    self._component_resource_cache[cache_key] = resource
            else:
                resource = self._component_resource_cache[cache_key]
            if resource is None:
                self._report_missing_resource(node)
            return resource
        spec = self._node_resource_spec(node)
        if spec is None:
            return
        file_id, index = spec
        cache_key = (str(file_id), int(index))
        if cache_key in self._component_resource_cache:
            return self._component_resource_cache[cache_key]
        if str(file_id).casefold() == "__item__":
            resource = self.resource_provider.get_item_image(index)
            if resource is not None:
                if getattr(node, "kind", "") == "itemshow":
                    resource = ResourceImage(resource.image, 0, 0, resource.file_name, resource.status)
            if resource is not None:
                self._component_resource_cache[cache_key] = resource
            if resource is None:
                self._report_missing_resource(node)
            return resource
        resource = self.resource_provider.get_image(file_id, index)
        if resource is not None:
            if getattr(node, "kind", "") in {
                "img",
                "imgex",
                "playimg",
                "playimgex",
                "itembox",
            }:
                resource = ResourceImage(resource.image, 0, 0, resource.file_name, resource.status)
        if resource is not None:
            self._component_resource_cache[cache_key] = resource
        if resource is None:
            self._report_missing_resource(node)
        return resource

    def _transparent_effect_resource(self, resource: ResourceImage) -> ResourceImage:
        image = resource.image
        if Image is None or ImageChops is None or not hasattr(image, "convert"):
            return resource
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        black_key = rgba.convert("RGB").convert("L").point(
            lambda value: 0 if value <= 8 else 255
        )
        rgba.putalpha(ImageChops.multiply(alpha, black_key))
        return ResourceImage(
            rgba,
            resource.origin_x,
            resource.origin_y,
            resource.file_name,
            resource.status,
        )

    def _progressbar_resource_for_node(self, node: Any) -> ResourceImage | None:
        args = node.props.get("args")
        if not isinstance(args, list) or len(args) < 12 or Image is None:
            return None
        file_id_value = self._int_value(args[2])
        file_id = file_id_value if file_id_value is not None else str(args[2])
        background_index = self._int_value(args[3])
        progress_start = self._int_value(args[4])
        if progress_start is None:
            return None
        frame_count = max(1, self._int_value(args[5]) or 1)
        interval_ms = max(1, self._int_value(args[6]) or 100)
        frame_index = progress_start + (
            (self._animation_elapsed_ms // interval_ms) % frame_count
        )
        minimum = self._int_value(args[9]) or 0
        maximum = self._int_value(args[10])
        value = self._int_value(args[11])
        maximum = maximum if maximum is not None else 100
        value = value if value is not None else minimum
        span = max(1, maximum - minimum)
        ratio = max(0.0, min(1.0, (value - minimum) / span))
        direction = self._int_value(args[12]) if len(args) > 12 else 0
        cache_key = (
            "__progressbar__", str(file_id), background_index, frame_index,
            round(ratio, 6), direction,
        )
        if cache_key in self._component_resource_cache:
            return self._component_resource_cache[cache_key]

        background = (
            self.resource_provider.get_image(file_id, background_index)
            if background_index is not None and background_index >= 0
            else None
        )
        progress = self.resource_provider.get_image(file_id, frame_index)
        if background is None and progress is None:
            self._report_missing_resource(node)
            return None

        progress_x = self._int_value(args[7]) or 0
        progress_y = self._int_value(args[8]) or 0
        bg_image = background.image.convert("RGBA") if background is not None else None
        bar_image = progress.image.convert("RGBA") if progress is not None else None
        width = bg_image.width if bg_image is not None else max(1, progress_x + bar_image.width)
        height = bg_image.height if bg_image is not None else max(1, progress_y + bar_image.height)
        canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        if bg_image is not None:
            canvas.alpha_composite(bg_image, (0, 0))
        if bar_image is not None and ratio > 0:
            self._paste_progressbar_slice(
                canvas, bar_image, progress_x, progress_y, ratio, direction or 0
            )
        resource = ResourceImage(
            canvas,
            0,
            0,
            progress.file_name if progress is not None else background.file_name,
            "ProgressBar",
        )
        self._component_resource_cache[cache_key] = resource
        return resource

    def _paste_progressbar_slice(
        self, canvas: Any, bar: Any, x: int, y: int, ratio: float, direction: int
    ) -> None:
        width, height = bar.size
        if direction in (2, 3):
            amount = max(0, min(height, int(round(height * ratio))))
            if amount <= 0:
                return
            top = 0 if direction == 2 else height - amount
            piece = bar.crop((0, top, width, top + amount))
            canvas.alpha_composite(piece, (x, y + top))
            return
        amount = max(0, min(width, int(round(width * ratio))))
        if amount <= 0:
            return
        left = 0 if direction == 0 else width - amount
        piece = bar.crop((left, 0, left + amount, height))
        canvas.alpha_composite(piece, (x + left, y))

    def _report_missing_resource(self, node: Any) -> None:
        key = (str(getattr(node, "kind", "")), str(getattr(node, "raw", "")))
        if key in self._missing_resource_notices:
            return
        self._missing_resource_notices.add(key)
        status = str(getattr(self.resource_provider, "last_status", "") or "素材文件或帧不存在")
        self._log(f"素材未渲染：{key[0]} / {status} / {key[1]}")

    def _monster_sequence_for_node(self, node: Any):
        args = node.props.get("args")
        if not isinstance(args, list) or len(args) < 6:
            return None
        values = [self._int_value(value) for value in args[:4]]
        if any(value is None for value in values):
            return None
        return monster_frame_sequence(values[0], values[1], values[2], values[3])

    def _component_is_animated(self, node: Any) -> bool:
        if getattr(node, "kind", "") == "monster":
            sequence = self._monster_sequence_for_node(node)
            return sequence is not None and len(sequence.frames) > 1
        if getattr(node, "kind", "") == "progressbar":
            args = node.props.get("args")
            return isinstance(args, list) and len(args) > 5 and (self._int_value(args[5]) or 0) > 1
        if getattr(node, "kind", "") not in {"playimg", "playimgex"}:
            return False
        args = node.props.get("args")
        if not isinstance(args, list):
            return False
        frame_count_index = 2
        return self._int_value(args[frame_count_index]) not in (None, 0, 1)

    def _playimg_frame_index(self, node: Any) -> int | None:
        args = node.props.get("args")
        if not isinstance(args, list) or len(args) < 4:
            return None
        start = self._int_value(args[1])
        frame_count = self._int_value(args[2])
        interval_ms = self._int_value(args[3])
        if start is None or frame_count is None or frame_count <= 0:
            return None
        interval_ms = max(1, interval_ms or 150)
        frame_step = self._animation_elapsed_ms // interval_ms
        if getattr(node, "kind", "") == "playimgex" and len(args) >= 5:
            repeat = self._int_value(args[4]) or 0
            if repeat > 0:
                frame_step = min(frame_step, frame_count * repeat - 1)
        return start + frame_step % frame_count

    def _advance_component_animations(self) -> None:
        if not self._animated_component_ids:
            self._animation_timer.stop()
            return
        self._animation_elapsed_ms += self._animation_timer.interval()
        stale_ids = []
        for component_id in tuple(self._animated_component_ids):
            item = self.component_items.get(component_id)
            if item is None:
                stale_ids.append(component_id)
                continue
            resource = self._resource_image_for_node(item.component.node)
            pixmap = self._pixmap_from_resource(resource)
            if pixmap is None or resource is None:
                continue
            item.update_pixmap(pixmap, (resource.origin_x, resource.origin_y))
        for component_id in stale_ids:
            self._animated_component_ids.discard(component_id)

    def _component_resource_spec(self, component: LayoutComponent) -> tuple[str | int, int] | None:
        return self._node_resource_spec(component.node)

    def _should_skip_component_visual(self, component: LayoutComponent, pixmap: QPixmap | None, resource_image: ResourceImage | None = None) -> bool:
        node = component.node
        if node.kind in {'layout', 'listview'}:
            return True
        if node.kind == "positioned_text":
            if not str(node.text or "").strip():
                return True
        parent_raw = str(node.props.get("str_parent_raw", "") or "")
        expanded_raw = str(node.props.get("expanded_raw", "") or "")
        label = str(node.props.get("label", "") or "")
        if node.kind == "img" and bool(node.props.get("str_expanded")):
            if expanded_raw.lower().startswith("<img:78:"):
                if label == "@无用" or "/@无用" in expanded_raw:
                    return True
        if node.kind in {'playimgex', 'img', 'imgex', 'playimg'} and label == "@无用":
            if self._resource_image_is_fully_transparent(resource_image):
                return True
            spec = self._node_resource_spec(node)
            if spec is not None and str(spec[0]) == "4":
                if int(spec[1]) == 78:
                    return True
        if pixmap is None:
            if re.match("<\\$\\s*STR\\(S\\$武学红\\d+\\)\\s*>", parent_raw, re.IGNORECASE):
                return True
        return False

    def _resource_image_is_fully_transparent(self, resource_image: ResourceImage | None) -> bool:
        if resource_image is None or resource_image.image is None:
            return False
        image = resource_image.image
        if not hasattr(image, "convert"):
            return False
        try:
            alpha = image.convert("RGBA").getchannel("A")
            return alpha.getbbox() is None
        except Exception:
            return False

    def _node_resource_spec(self, node: Any) -> tuple[str | int, int] | None:
        if getattr(node, "kind", "") == "background":
            file_id = node.props.get("file")
            index = self._int_value(node.props.get("index"))
            if file_id is not None and index is not None:
                return (str(file_id), index)
            return None
        args = node.props.get("args")
        if not isinstance(args, list):
            return None
        kind = node.kind
        if kind == "monster":
            sequence = self._monster_sequence_for_node(node)
            if sequence is not None and sequence.frames:
                return (f"Mon{sequence.file_index}.wzl", sequence.frames[0])
            return None
        if kind == "img" and len(args) >= 2:
            index = self._int_value(args[0])
            file_id = self._int_value(args[1])
            if index is not None:
                return (file_id if file_id is not None else str(args[1]), index)
            return None
        if kind == "imgex" and len(args) >= 2:
            file_id = self._int_value(args[0])
            index = self._int_value(args[1])
            if index is not None:
                return (file_id if file_id is not None else str(args[0]), index)
            return None
        if kind == "playimg" and len(args) >= 2:
            file_id = self._int_value(args[0])
            index = self._int_value(args[1])
            if index is not None:
                return (file_id if file_id is not None else str(args[0]), index)
            return None
        if kind == "playimgex" and len(args) >= 2:
            file_id = self._int_value(args[0])
            index = self._int_value(args[1])
            if index is not None:
                return (file_id if file_id is not None else str(args[0]), index)
            return None
        if kind == "itembox" and len(args) >= 3:
            file_id = self._int_value(args[1])
            index = self._int_value(args[2])
            if index is not None:
                return (file_id if file_id is not None else str(args[1]), index)
            return None
        if kind == "progressbar" and len(args) >= 5:
            file_id = self._int_value(args[2])
            index = self._int_value(args[4])
            if index is not None:
                return (file_id if file_id is not None else str(args[2]), index)
            return None
        if kind == "itemshow" and args:
            item_id = self._itemshow_item_id(node, args)
            if item_id is not None:
                return ("__item__", item_id)
            return None
        return None

    def _itemshow_item_id(self, node: Any, args: list[Any]) -> int | None:
        variable_name = ""
        for raw in (
            getattr(getattr(node, "source", None), "raw", ""),
            getattr(node, "raw", ""),
        ):
            match = _ITEMSHOW_STR_ID_RE.search(str(raw or ""))
            if match:
                variable_name = match.group("name").strip()
                break
        if variable_name:
            resolved = self._item_id_for_db_variable(variable_name)
            if resolved is not None:
                return resolved
        return self._int_value(args[0])

    def _item_id_for_db_variable(self, variable_name: str) -> int | None:
        folded_name = str(variable_name or "").strip().casefold()
        if not folded_name:
            return None
        resolver = getattr(self.resource_provider, "item_id_for_name", None)
        if not callable(resolver):
            return None
        for _path, source in self._component_edit_source_candidates():
            for match in _GET_DB_ITEM_FIELD_RE.finditer(source):
                if match.group("name").strip().casefold() != folded_name:
                    continue
                if match.group("field").strip().casefold() not in {"idx", "index", "id"}:
                    continue
                item_name = match.group("item").strip()
                if not item_name or "<$" in item_name:
                    continue
                item_id = resolver(item_name)
                if item_id is not None:
                    return int(item_id)
        return None

    def _pixmap_from_resource(self, resource: ResourceImage | None) -> QPixmap | None:
        if resource is None or resource.image is None:
            return None
        image = resource.image
        if isinstance(image, QPixmap):
            return image
        if isinstance(image, QImage):
            return QPixmap.fromImage(image)
        cache_key = id(image)
        cached = self._component_pixmap_cache.get(cache_key)
        if isinstance(cached, tuple) and len(cached) == 2 and cached[0] is image:
            return cached[1]
        if not hasattr(image, "convert"):
            return None
        try:
            rgba = image.convert("RGBA")
            width, height = rgba.size
            data = rgba.tobytes("raw", "RGBA")
            qimage = QImage(data, width, height, width * 4, QImage.Format_RGBA8888).copy()
            pixmap = QPixmap.fromImage(qimage)
            self._cache_component_pixmap(cache_key, image, pixmap)
            return pixmap
        except Exception:
            if ImageQt is None:
                return None
            try:
                pixmap = QPixmap.fromImage(ImageQt(image.convert("RGBA")))
                self._cache_component_pixmap(cache_key, image, pixmap)
                return pixmap
            except Exception:
                return None

    def _cache_component_pixmap(self, cache_key: int, image: Any, pixmap: QPixmap) -> None:
        cache = self._component_pixmap_cache
        if cache_key not in cache and len(cache) >= _COMPONENT_PIXMAP_CACHE_LIMIT:
            cache.pop(next(iter(cache)), None)
        # Keep the PIL image alive so Python cannot recycle its id for another sprite.
        cache[cache_key] = (image, pixmap)

    def _int_value(self, value: Any) -> int | None:
        try:
            return int(str(value).strip())
        except Exception:
            return

    def _selected_visual_items(self) -> list[_VisualComponentItem]:
        scene = getattr(self, "scene", None)
        if scene is None:
            return []
        try:
            selected_items = scene.selectedItems()
        except RuntimeError:
            return []
        items = [item for item in selected_items if isinstance(item, _VisualComponentItem)]
        items.sort(
            key=lambda item: (
                0 if item.component.node.id == self.selected_component_id else 1,
                item.component.node.source.start,
                item.component.node.id,
            )
        )
        return items

    def _canvas_selection_changed(self) -> None:
        if self._syncing_canvas_selection:
            return
        try:
            items = self._selected_visual_items()
            if not items:
                self.selected_component_id = ""
                self._clear_component_props()
                self._sync_component_palette_selection(None)
                self._update_selection_controls()
                return
            current = self.component_items.get(self.selected_component_id)
            if current is None or not current.isSelected():
                self.selected_component_id = items[0].component.node.id
                self._show_component_props(items[0].component)
                current = items[0]
            if current is not None:
                self._sync_component_palette_selection(current.component)
            self._update_selection_controls()
        except RuntimeError:
            return

    def _update_selection_controls(self) -> None:
        count = len(self._selected_visual_items())
        label = getattr(self, "canvas_selection_label", None)
        if label is not None:
            label.setText(f"已选 {count}")
        editable = count > 0 and all(
            item.component.node.kind in _XY_COMPONENT_ARG_INDEXES
            for item in self._selected_visual_items()
        )
        arrange_button = getattr(self, "canvas_arrange_button", None)
        if arrange_button is not None:
            arrange_button.setEnabled(count >= 2 and editable)
        for mode, action in getattr(self, "_arrange_actions", {}).items():
            minimum = 3 if mode in {"hdistribute", "vdistribute"} else 2
            action.setEnabled(count >= minimum and editable)
        delete_button = getattr(self, "canvas_delete_selected_button", None)
        if delete_button is not None:
            delete_button.setEnabled(count > 0)

    def _clear_component_props(self) -> None:
        table = getattr(self, "props_table", None)
        if table is None:
            return
        table.clearContents()
        table.setRowCount(0)

    def clear_component_selection(self) -> None:
        self._syncing_canvas_selection = True
        try:
            self.scene.clearSelection()
        finally:
            self._syncing_canvas_selection = False
        self.selected_component_id = ""
        self._clear_component_props()
        self._sync_component_palette_selection(None)
        self._update_selection_controls()

    def select_all_components(self) -> None:
        self._syncing_canvas_selection = True
        try:
            for item in self.component_items.values():
                if item.flags() & QGraphicsItem.ItemIsSelectable:
                    item.setSelected(True)
        finally:
            self._syncing_canvas_selection = False
        items = self._selected_visual_items()
        if items:
            self.selected_component_id = items[0].component.node.id
            self._show_component_props(items[0].component)
            self._sync_component_palette_selection(items[0].component)
        self._update_selection_controls()

    def select_component(
        self,
        component: LayoutComponent,
        jump_source: bool = True,
        preserve_selection: bool = False,
        focus_source: bool = False,
    ) -> None:
        self.selected_component_id = component.node.id
        self._syncing_canvas_selection = True
        try:
            if not preserve_selection:
                self.scene.clearSelection()
            item = self.component_items.get(component.node.id)
            if item is not None:
                item.setSelected(True)
        finally:
            self._syncing_canvas_selection = False

        self._show_component_props(component)
        self._sync_component_palette_selection(component)
        if jump_source:
            self._jump_to_source(component, focus=focus_source)
        self._update_selection_controls()
        self._log(f"选中组件：{component.node.kind} row={component.row} rect={component.visual_rect.x},{component.visual_rect.y},{component.visual_rect.width}x{component.visual_rect.height}")

    def activate_component(self, component: LayoutComponent) -> None:
        label = str(component.node.props.get("label", "") or "").strip()
        if not label:
            fallback = self._overlapped_labeled_component(component)
            if fallback is not None:
                component = fallback
                label = str(component.node.props.get("label", "") or "").strip()
        if not label:
            return
        if self._select_label(label):
            self._log(f"trigger label: {label}")
        else:
            self._log(f"label not found: {label}")

    def _overlapped_labeled_component(self, component: LayoutComponent) -> LayoutComponent | None:
        rect = component.visual_rect
        candidates = []
        for item in self.component_items.values():
            other = item.component
            if other.node.id == component.node.id:
                continue
            label = str(other.node.props.get("label", "") or "").strip()
            if not label:
                continue
            area = self._overlap_area(rect, other.visual_rect)
            if area <= 0:
                continue
            candidates.append((other.z_index, area, -other.node.source.start, other))

        if not candidates:
            return
        candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return candidates[0][3]

    def _overlap_area(self, left: Any, right: Any) -> int:
        x1 = max(int(left.x), int(right.x))
        y1 = max(int(left.y), int(right.y))
        x2 = min(int(left.x + left.width), int(right.x + right.width))
        y2 = min(int(left.y + left.height), int(right.y + right.height))
        return max(0, x2 - x1) * max(0, y2 - y1)

    def _select_label(self, label: str) -> bool:
        target = label.strip().lower()
        if not target:
            return False
        for row in range(self.label_list.count()):
            item = self.label_list.item(row)
            item_label = str(item.data(Qt.UserRole) or "").strip().lower()
            if item_label == target:
                self.label_list.setCurrentRow(row)
                return True
        return False

    def component_moved(self, component: LayoutComponent, x: int, y: int) -> None:
        if x == component.visual_rect.x and y == component.visual_rect.y:
            self._show_component_props(component)
            return
        block_reason = self._str_expanded_move_block_reason(component)
        if block_reason:
            self._log(block_reason)
            item = self.component_items.get(component.node.id)
            if item is not None:
                item.setPos(component.visual_rect.x, component.visual_rect.y)
            self._show_component_props(component, moved_to=(x, y))
            return
        edit_context = self._component_edit_context(component)
        if edit_context is None:
            source = ""
            edit_component = component
            edit_layout = self.layout_document
            edit_path = self.source_view_path or self.current_path
        else:
            source, edit_component, edit_layout, edit_path = edit_context
        if edit_context is None:
            self._log("当前组件来自 #CALL 展开内容，不能写回入口脚本；请在被调用脚本中编辑。")
            item = self.component_items.get(component.node.id)
            if item is not None:
                item.setPos(component.visual_rect.x, component.visual_rect.y)
            self._show_component_props(component, moved_to=(x, y))
            return
        result = self.move_operation.apply(source, edit_component, x, y, layout=edit_layout)
        self._log(f"移动组件：{component.node.kind} {component.node.id} -> {x},{y}；{result.message}")
        if result.changed:
            if not self._set_editor_source_after_edit(edit_path, result.source, source):
                item = self.component_items.get(component.node.id)
                if item is not None:
                    item.setPos(component.visual_rect.x, component.visual_rect.y)
                return
            self.undo_stack.push(source)
            self._render_after_edit(result)
        else:
            item = self.component_items.get(component.node.id)
            if item is not None:
                item.setPos(component.visual_rect.x, component.visual_rect.y)
            self._show_component_props(component, moved_to=(x, y))

    def _prepare_component_drag(self, anchor: _VisualComponentItem) -> None:
        items = self._selected_visual_items()
        if len(items) <= 1 or anchor not in items:
            self._component_drag_anchor_id = ""
            self._component_drag_snapshot = {}
            return
        self._component_drag_anchor_id = anchor.component.node.id
        self._component_drag_snapshot = {
            item.component.node.id: (
                item.component,
                int(round(item.pos().x())),
                int(round(item.pos().y())),
            )
            for item in items
        }

    def _finish_component_drag(self, anchor: _VisualComponentItem) -> bool:
        if anchor.component.node.id != self._component_drag_anchor_id:
            return False
        snapshot = self._component_drag_snapshot
        self._component_drag_anchor_id = ""
        self._component_drag_snapshot = {}
        if len(snapshot) <= 1:
            return False
        moved = any(
            item_id in self.component_items
            and (
                int(round(self.component_items[item_id].pos().x())) != old_x
                or int(round(self.component_items[item_id].pos().y())) != old_y
            )
            for item_id, (_component, old_x, old_y) in snapshot.items()
        )
        if not moved:
            return False
        self._clamp_component_group_to_canvas(snapshot)
        self._commit_component_positions(snapshot, "组移动")
        return True

    def _clamp_component_group_to_canvas(self, snapshot: dict[str, tuple[LayoutComponent, int, int]]) -> None:
        if self.layout_document is None:
            return
        items = [self.component_items[item_id] for item_id in snapshot if item_id in self.component_items]
        if not items:
            return
        left = min(float(item.pos().x()) for item in items)
        top = min(float(item.pos().y()) for item in items)
        right = max(float(item.pos().x()) + float(item.rect().width()) for item in items)
        bottom = max(float(item.pos().y()) + float(item.rect().height()) for item in items)
        shift_x = -left if left < 0 else min(0.0, float(self.layout_document.width) - right)
        shift_y = -top if top < 0 else min(0.0, float(self.layout_document.height) - bottom)
        if not shift_x and not shift_y:
            return
        for item in items:
            item.setPos(item.pos().x() + shift_x, item.pos().y() + shift_y)

    def _restore_component_positions(self, snapshot: dict[str, tuple[LayoutComponent, int, int]]) -> None:
        for item_id, (_component, old_x, old_y) in snapshot.items():
            item = self.component_items.get(item_id)
            if item is not None:
                item.setPos(old_x, old_y)

    def _commit_component_positions(
        self,
        snapshot: dict[str, tuple[LayoutComponent, int, int]],
        action_name: str,
    ) -> bool:
        records = []
        for item_id, (component, old_x, old_y) in snapshot.items():
            item = self.component_items.get(item_id)
            if item is None:
                self._restore_component_positions(snapshot)
                return False
            records.append(
                (
                    0 if item_id == self.selected_component_id else 1,
                    component.node.source.start,
                    item,
                    component,
                    old_x,
                    old_y,
                    int(round(item.pos().x())),
                    int(round(item.pos().y())),
                )
            )
        records.sort(key=lambda record: (record[0], record[1]))
        if not any(record[6] != record[4] or record[7] != record[5] for record in records):
            return False
        flow_records = [
            record
            for record in records
            if record[3].node.kind not in _XY_COMPONENT_ARG_INDEXES
        ]
        if flow_records and len(flow_records) != len(records):
            self._restore_component_positions(snapshot)
            message = "坐标组件与流式组件请分开微移"
            self.status_label.setText(message)
            self._log(message)
            return False
        if flow_records:
            return self._commit_flow_component_positions(snapshot, records, action_name)

        source = None
        edit_path = ""
        moves = []
        for _primary, _offset, _item, component, old_x, old_y, x, y in records:
            block_reason = self._str_expanded_move_block_reason(component)
            if block_reason:
                self._restore_component_positions(snapshot)
                self.status_label.setText(block_reason)
                self._log(block_reason)
                return False
            edit_context = self._component_edit_context(component)
            if edit_context is None:
                self._restore_component_positions(snapshot)
                message = "所选组件包含无法定位写回源码的内容"
                self.status_label.setText(message)
                self._log(message)
                return False
            component_source, edit_component, edit_layout, component_path = edit_context
            if source is None:
                source = component_source
                edit_path = component_path
            elif component_path.casefold() != edit_path.casefold() or component_source != source:
                self._restore_component_positions(snapshot)
                message = "所选组件来自不同脚本，不能批量编辑"
                self.status_label.setText(message)
                self._log(message)
                return False
            target_x = edit_component.visual_rect.x + (x - old_x)
            target_y = edit_component.visual_rect.y + (y - old_y)
            moves.append((edit_component, target_x, target_y))

        if source is None:
            self._restore_component_positions(snapshot)
            return False
        result = self.move_operation.apply_many(source, moves)
        self._log(f"{action_name}：{len(moves)} 个组件；{result.message}")
        if not result.changed:
            self._restore_component_positions(snapshot)
            self.status_label.setText(result.message)
            return False
        if not self._set_editor_source_after_edit(edit_path, result.source, source):
            self._restore_component_positions(snapshot)
            return False
        self.undo_stack.push(source)
        self._render_after_edit(result)
        return True

    def _commit_flow_component_positions(
        self,
        snapshot: dict[str, tuple[LayoutComponent, int, int]],
        records: list[tuple[Any, ...]],
        action_name: str,
    ) -> bool:
        deltas = {(record[6] - record[4], record[7] - record[5]) for record in records}
        if len(deltas) != 1:
            self._restore_component_positions(snapshot)
            message = "流式组件必须保持相同位移"
            self.status_label.setText(message)
            self._log(message)
            return False
        dx, dy = next(iter(deltas))
        if not dx and not dy:
            return False

        source = None
        edit_path = ""
        group_layout = None
        edit_components = []
        for _primary, _offset, _item, component, _old_x, _old_y, _x, _y in records:
            block_reason = self._str_expanded_move_block_reason(component)
            if block_reason:
                self._restore_component_positions(snapshot)
                self.status_label.setText(block_reason)
                self._log(block_reason)
                return False
            edit_context = self._component_edit_context(component)
            if edit_context is None:
                self._restore_component_positions(snapshot)
                message = "所选组件包含无法定位写回源码的内容"
                self.status_label.setText(message)
                self._log(message)
                return False
            component_source, edit_component, edit_layout, component_path = edit_context
            if edit_layout is None:
                self._restore_component_positions(snapshot)
                message = "缺少流式布局结果，不能批量微移"
                self.status_label.setText(message)
                self._log(message)
                return False
            if source is None:
                source = component_source
                edit_path = component_path
                group_layout = edit_layout
            elif component_path.casefold() != edit_path.casefold() or component_source != source:
                self._restore_component_positions(snapshot)
                message = "所选组件来自不同脚本，不能批量编辑"
                self.status_label.setText(message)
                self._log(message)
                return False
            if edit_layout is not group_layout:
                mapped = next(
                    (
                        candidate
                        for candidate in group_layout.components
                        if candidate.node.kind == edit_component.node.kind
                        and candidate.node.source.start == edit_component.node.source.start
                        and candidate.node.source.end == edit_component.node.source.end
                    ),
                    None,
                )
                if mapped is None:
                    self._restore_component_positions(snapshot)
                    message = "流式组件布局来源不一致，不能批量编辑"
                    self.status_label.setText(message)
                    self._log(message)
                    return False
                edit_component = mapped
            edit_components.append(edit_component)

        if source is None or group_layout is None:
            self._restore_component_positions(snapshot)
            return False
        result = self.move_operation.apply_flow_group(
            source,
            edit_components,
            dx,
            dy,
            layout=group_layout,
        )
        self._log(f"{action_name}：{len(edit_components)} 个流式组件；{result.message}")
        if not result.changed:
            self._restore_component_positions(snapshot)
            self.status_label.setText(result.message)
            return False
        if not self._set_editor_source_after_edit(edit_path, result.source, source):
            self._restore_component_positions(snapshot)
            return False
        self.undo_stack.push(source)
        self._render_after_edit(result)
        return True

    def arrange_selected_components(self, mode: str) -> None:
        items = self._selected_visual_items()
        minimum = 3 if mode in {"hdistribute", "vdistribute"} else 2
        if len(items) < minimum:
            return
        if any(item.component.node.kind not in _XY_COMPONENT_ARG_INDEXES for item in items):
            self.status_label.setText("所选内容包含流式组件，不能批量排列")
            return
        snapshot = {
            item.component.node.id: (
                item.component,
                int(round(item.pos().x())),
                int(round(item.pos().y())),
            )
            for item in items
        }
        positions = {
            item.component.node.id: [int(round(item.pos().x())), int(round(item.pos().y()))]
            for item in items
        }
        left = min(positions[item.component.node.id][0] for item in items)
        top = min(positions[item.component.node.id][1] for item in items)
        right = max(
            positions[item.component.node.id][0] + int(round(item.rect().width()))
            for item in items
        )
        bottom = max(
            positions[item.component.node.id][1] + int(round(item.rect().height()))
            for item in items
        )

        if mode == "left":
            for item in items:
                positions[item.component.node.id][0] = left
        elif mode == "hcenter":
            center = (left + right) / 2.0
            for item in items:
                positions[item.component.node.id][0] = int(round(center - item.rect().width() / 2.0))
        elif mode == "right":
            for item in items:
                positions[item.component.node.id][0] = right - int(round(item.rect().width()))
        elif mode == "top":
            for item in items:
                positions[item.component.node.id][1] = top
        elif mode == "vcenter":
            center = (top + bottom) / 2.0
            for item in items:
                positions[item.component.node.id][1] = int(round(center - item.rect().height() / 2.0))
        elif mode == "bottom":
            for item in items:
                positions[item.component.node.id][1] = bottom - int(round(item.rect().height()))
        elif mode == "hdistribute":
            ordered = sorted(items, key=lambda item: (positions[item.component.node.id][0], item.component.node.source.start))
            total_width = sum(float(item.rect().width()) for item in ordered)
            gap = (right - left - total_width) / (len(ordered) - 1)
            if gap < 0:
                self.status_label.setText("横向空间不足，无法均布")
                return
            cursor = float(left)
            for item in ordered:
                positions[item.component.node.id][0] = int(round(cursor))
                cursor += float(item.rect().width()) + gap
        elif mode == "vdistribute":
            ordered = sorted(items, key=lambda item: (positions[item.component.node.id][1], item.component.node.source.start))
            total_height = sum(float(item.rect().height()) for item in ordered)
            gap = (bottom - top - total_height) / (len(ordered) - 1)
            if gap < 0:
                self.status_label.setText("纵向空间不足，无法均布")
                return
            cursor = float(top)
            for item in ordered:
                positions[item.component.node.id][1] = int(round(cursor))
                cursor += float(item.rect().height()) + gap
        else:
            return

        for item in items:
            x, y = positions[item.component.node.id]
            item.setPos(x, y)
        titles = {
            "left": "左对齐",
            "hcenter": "水平居中",
            "right": "右对齐",
            "top": "顶部对齐",
            "vcenter": "垂直居中",
            "bottom": "底部对齐",
            "hdistribute": "横向均布",
            "vdistribute": "纵向均布",
        }
        self._commit_component_positions(snapshot, titles.get(mode, "批量排列"))

    def handle_keyboard_move_key(self, event: Any) -> bool:
        if not event.modifiers() & Qt.ControlModifier:
            return False
        deltas = {
            Qt.Key_Left: (-1, 0),
            Qt.Key_Right: (1, 0),
            Qt.Key_Up: (0, -1),
            Qt.Key_Down: (0, 1),
        }
        delta = deltas.get(event.key())
        if delta is None:
            return False
        if not self.nudge_selected_component(*delta):
            return False
        event.accept()
        return True

    def nudge_selected_component(self, dx: int, dy: int) -> bool:
        selected_items = self._selected_visual_items()
        if len(selected_items) > 1:
            return self._nudge_selected_group(selected_items, dx, dy)
        item = self._selected_item()
        if item is None or self.layout_document is None:
            return False
        if self._keyboard_move_component is None:
            self._keyboard_move_source = self.source_editor.toPlainText()
            self._keyboard_move_component = item.component
        (dx, dy) = self._keyboard_nudge_delta(item.component, dx, dy)
        current = item.pos()
        max_x = max(0, self.layout_document.width - item.component.visual_rect.width)
        max_y = max(0, self.layout_document.height - item.component.visual_rect.height)
        x = max(0, min(max_x, int(current.x()) + dx))
        y = max(0, min(max_y, int(current.y()) + dy))
        item.setPos(x, y)
        self._keyboard_move_target = (x, y)
        self._show_component_props((item.component), moved_to=(x, y))
        self.status_label.setText(f"键盘移动预览：{item.component.node.kind} -> {x},{y}")
        return True

    def _nudge_selected_group(self, items: list[_VisualComponentItem], dx: int, dy: int) -> bool:
        if self.layout_document is None:
            return False
        xy_flags = [item.component.node.kind in _XY_COMPONENT_ARG_INDEXES for item in items]
        if any(xy_flags) and not all(xy_flags):
            self.status_label.setText("坐标组件与流式组件请分开微移")
            return True
        flow_group = not any(xy_flags)
        if flow_group:
            char_width = max(1, int(self.move_operation.serializer.flow_engine.char_width))
            row_height = max(1, int(self.layout_document.row_height))
            dx *= char_width
            dy *= row_height
            left = min(int(round(item.pos().x())) for item in items)
            top = min(int(round(item.pos().y())) for item in items)
            right = max(
                int(round(item.pos().x())) + int(round(item.rect().width()))
                for item in items
            )
            bottom = max(
                int(round(item.pos().y())) + int(round(item.rect().height()))
                for item in items
            )
            if dx < 0 and left + dx < int(self.layout_document.content_x):
                dx = 0
            if dx > 0 and right + dx > int(self.layout_document.width):
                dx = 0
            if dy < 0 and top + dy < int(self.layout_document.content_y):
                dy = 0
            if dy > 0 and bottom + dy > int(self.layout_document.height):
                dy = 0
            if not dx and not dy:
                self.status_label.setText("所选组件已经到达画布边界")
                return True
        if not self._keyboard_group_snapshot:
            self._keyboard_move_source = None
            self._keyboard_move_component = None
            self._keyboard_move_target = None
            self._keyboard_group_snapshot = {
                item.component.node.id: (
                    item.component,
                    int(round(item.pos().x())),
                    int(round(item.pos().y())),
                )
                for item in items
            }
        for item in items:
            item.setPos(int(round(item.pos().x())) + dx, int(round(item.pos().y())) + dy)
        if not flow_group:
            self._clamp_component_group_to_canvas(self._keyboard_group_snapshot)
        kind_text = "流式组件" if flow_group else "组件"
        self.status_label.setText(f"键盘移动预览：{len(items)} 个{kind_text}")
        return True

    def _keyboard_nudge_delta(self, component: LayoutComponent, dx: int, dy: int) -> tuple[int, int]:
        if component.node.kind in _XY_COMPONENT_ARG_INDEXES:
            return (dx, dy)
        char_width = 6
        try:
            char_width = int(self.move_operation.serializer.flow_engine.char_width)
        except Exception:
            char_width = 6
        row_height = self.layout_document.row_height if self.layout_document is not None else 16
        return (
         dx * max(1, char_width), dy * max(1, row_height))

    def commit_keyboard_move(self) -> None:
        if self._keyboard_group_snapshot:
            snapshot = self._keyboard_group_snapshot
            self._keyboard_group_snapshot = {}
            self._keyboard_move_source = None
            self._keyboard_move_component = None
            self._keyboard_move_target = None
            self._commit_component_positions(snapshot, "键盘组移动")
            return
        component = self._keyboard_move_component
        target = self._keyboard_move_target
        source = self._keyboard_move_source
        self._keyboard_move_component = None
        self._keyboard_move_target = None
        self._keyboard_move_source = None
        if component is None or target is None:
            return
        block_reason = self._str_expanded_move_block_reason(component)
        if block_reason:
            self._log(block_reason)
            item = self.component_items.get(component.node.id)
            if item is not None:
                item.setPos(component.visual_rect.x, component.visual_rect.y)
            self._show_component_props(component, moved_to=target)
            return
        edit_context = self._component_edit_context(component)
        if edit_context is None:
            source = source or ""
            edit_component = component
            edit_layout = self.layout_document
            edit_path = self.source_view_path or self.current_path
        else:
            source, edit_component, edit_layout, edit_path = edit_context
        if edit_context is None:
            self._log("当前组件来自 #CALL 展开内容，键盘移动不会写回入口脚本。")
            item = self.component_items.get(component.node.id)
            if item is not None:
                item.setPos(component.visual_rect.x, component.visual_rect.y)
            self._show_component_props(component, moved_to=target)
            return
        x, y = target
        if x == component.visual_rect.x and y == component.visual_rect.y:
            item = self.component_items.get(component.node.id)
            if item is not None:
                item.setPos(component.visual_rect.x, component.visual_rect.y)
            return
        result = self.move_operation.apply(source, edit_component, x, y, layout=edit_layout)
        self._log(f"键盘移动组件：{component.node.kind} {component.node.id} -> {x},{y}；{result.message}")
        if result.changed:
            if not self._set_editor_source_after_edit(edit_path, result.source, source):
                item = self.component_items.get(component.node.id)
                if item is not None:
                    item.setPos(component.visual_rect.x, component.visual_rect.y)
                return
            self.undo_stack.push(source)
            self._render_after_edit(result)
            return
        item = self.component_items.get(component.node.id)
        if item is not None:
            item.setPos(component.visual_rect.x, component.visual_rect.y)
        self._show_component_props(component, moved_to=(x, y))

    def _selected_item(self) -> _VisualComponentItem | None:
        if self.selected_component_id:
            item = self.component_items.get(self.selected_component_id)
            if item is not None and item.isSelected():
                return item
        for item in self.component_items.values():
            if item.isSelected():
                return item

    def delete_component(self, component: LayoutComponent) -> None:
        edit_context = self._component_edit_context(component)
        if edit_context is None:
            source = ""
            edit_component = component
            edit_layout = self.layout_document
            edit_path = self.source_view_path or self.current_path
        else:
            source, edit_component, edit_layout, edit_path = edit_context
        if edit_context is None:
            self._log("当前组件来自 #CALL 展开内容，不能从入口脚本删除。")
            self._show_component_props(component)
            return
        result = self.delete_operation.apply(source, edit_component, layout=edit_layout)
        self._log(f"删除组件：{component.node.kind} {component.node.id}；{result.message}")
        if not result.changed:
            self._show_component_props(component)
            return
        if not self._set_editor_source_after_edit(edit_path, result.source, source):
            return
        self.undo_stack.push(source)
        self.selected_component_id = ""
        self._sync_component_palette_selection(None)
        self.props_table.clearContents()
        self.props_table.setRowCount(0)
        self._render_after_edit(result)

    def delete_selected_components(self) -> None:
        items = self._selected_visual_items()
        if not items:
            return
        if len(items) == 1:
            self.delete_component(items[0].component)
            return
        source = None
        edit_path = ""
        edit_components = []
        for item in items:
            edit_context = self._component_edit_context(item.component)
            if edit_context is None:
                message = "所选组件包含无法定位写回源码的内容"
                self.status_label.setText(message)
                self._log(message)
                return
            component_source, edit_component, _edit_layout, component_path = edit_context
            if source is None:
                source = component_source
                edit_path = component_path
            elif component_path.casefold() != edit_path.casefold() or component_source != source:
                message = "所选组件来自不同脚本，不能批量删除"
                self.status_label.setText(message)
                self._log(message)
                return
            edit_components.append(edit_component)
        if source is None:
            return
        result = self.delete_operation.apply_many(source, edit_components)
        self._log(f"批量删除：{len(edit_components)} 个组件；{result.message}")
        if not result.changed:
            self.status_label.setText(result.message)
            return
        if not self._set_editor_source_after_edit(edit_path, result.source, source):
            return
        self.undo_stack.push(source)
        self.selected_component_id = ""
        self._clear_component_props()
        self._sync_component_palette_selection(None)
        self._render_after_edit(result)

    def _component_palette_double_clicked(self, item: QListWidgetItem) -> None:
        tag = str(item.data(Qt.UserRole) or "")
        if not tag:
            return
        if self.layout_document is None:
            self.render_current_source()
        layout_doc = self.layout_document
        x = layout_doc.content_x if layout_doc is not None else 24
        y = layout_doc.content_y if layout_doc is not None else 14
        self.insert_component_tag(tag, x, y)

    def insert_component_tag(
        self,
        tag: str,
        x: int,
        y: int,
        pointer_debug: str = '',
        exact_coordinates: bool = False,
    ) -> None:
        tag = tag.strip()
        if not tag:
            return
        if self.layout_document is None:
            self.render_current_source()
        prototype = self._prototype_component(tag)
        if prototype is None:
            self._log(f"组件解析失败：{tag}")
            return
        source, edit_layout, edit_path = self._insert_edit_context()
        result = self.insert_operation.apply(
            source,
            prototype,
            x,
            y,
            layout=edit_layout,
            exact_coordinates=exact_coordinates,
        )
        self._log(f"插入组件：{tag} -> {x},{y}；{result.message}")
        if pointer_debug:
            self._log(pointer_debug)
        for line in tuple(getattr(result, "debug_lines", ()) or ()):
            self._log(str(line))

        if not result.changed:
            self._show_component_props(prototype, moved_to=(x, y))
            return
        if not self._set_editor_source_after_edit(edit_path, result.source, source):
            return
        self.undo_stack.push(source)
        result = replace(result, dirty_rows=())
        self._render_after_edit(result)

    def _insert_edit_context(self) -> tuple[str, LayoutDocument | None, str]:
        source = self.source_editor.toPlainText()
        edit_path = self.source_view_path or self.current_path or "__editor__"
        edit_layout = self._edit_layout_for_source_text(edit_path, source)
        return (
         source, edit_layout or self.layout_document, edit_path)

    def _prototype_component(self, tag: str) -> LayoutComponent | None:
        sample = f"[@insert]\n#SAY\n{tag}\\\n"
        document = self.engine.parse(sample, file_key="__insert__")
        layout = self.engine.layout(document, label="@insert", image_size_resolver=self._measure_node_size)
        if not layout.components:
            return
        component = layout.components[0]
        return component

    def undo(self) -> None:
        current = self.source_editor.toPlainText()
        undo_before = list(self.undo_stack._undo)
        redo_before = list(self.undo_stack._redo)
        previous = self.undo_stack.undo(current)
        if previous is None:
            self._log("没有可撤回的操作")
            return
        if not self._set_editor_source_after_edit(
            self.source_view_path or self.current_path,
            previous,
            current,
        ):
            self.undo_stack._undo = undo_before
            self.undo_stack._redo = redo_before
            return
        self.render_current_source()
        self._log("已撤回一步")

    def redo(self) -> None:
        current = self.source_editor.toPlainText()
        undo_before = list(self.undo_stack._undo)
        redo_before = list(self.undo_stack._redo)
        next_source = self.undo_stack.redo(current)
        if next_source is None:
            self._log("没有可恢复的操作")
            return
        if not self._set_editor_source_after_edit(
            self.source_view_path or self.current_path,
            next_source,
            current,
        ):
            self.undo_stack._undo = undo_before
            self.undo_stack._redo = redo_before
            return
        self.render_current_source()
        self._log("已恢复一步")

    def _jump_to_source(self, component: LayoutComponent, focus: bool = False) -> None:
        source = component.node.source
        start = source.start
        end = source.end
        editor_source = self.source_editor.toPlainText()
        if end > len(editor_source) or editor_source[start:end] != source.raw:
            needle = source.raw
            start = editor_source.find(needle)
            if start < 0:
                needle = component.node.raw
                start = editor_source.find(needle)
            expanded_raw = str(component.node.props.get("expanded_raw", "") or "")
            if start < 0:
                if expanded_raw:
                    needle = expanded_raw
                    start = editor_source.find(expanded_raw)
            if start < 0:
                if self._jump_to_called_component_source(component, focus=focus):
                    return
                self._log(f"未找到源码位置：{component.node.kind} {component.node.raw}")
                return
            end = start + len(needle)
        cursor = self.source_editor.textCursor()
        cursor.setPosition(max(0, start))
        cursor.setPosition(max(start, end), QTextCursor.KeepAnchor)
        self.source_editor.setTextCursor(cursor)
        if focus:
            self.source_editor.setFocus()

    def _jump_to_called_component_source(self, component: LayoutComponent, focus: bool = False) -> bool:
        needles = self._component_source_needles(component)
        if not needles:
            return False
        for file_path in self._call_files_for_source(self._render_base_source()):
            text = self._read_call_file(file_path)
            if not text:
                continue
            for needle in needles:
                start = text.find(needle)
                if start < 0:
                    start = text.casefold().find(needle.casefold())
                if start < 0:
                    continue
                self._show_source_text(str(file_path), text, start, start + len(needle), focus=focus)
                self._log(f"定位到 #CALL 源码：{file_path}")
                return True
        return False

    def _component_source_needles(self, component: LayoutComponent) -> list[str]:
        values = []
        for value in (
         component.node.source.raw,
         component.node.raw,
         str(component.node.props.get("expanded_raw", "") or ""),
         str(component.node.props.get("str_parent_raw", "") or "")):
            value = str(value or "").strip()
            if not value:
                continue
            if value not in values:
                values.append(value)
        return values

    def _show_source_text(self, path: str, text: str, start: int, end: int, focus: bool = True) -> None:
        self.source_view_path = path
        self.source_view_encoding = self._encoding_for_source_path(path)
        if self.source_editor.toPlainText() != text:
            self._set_source_editor_text_programmatically(text)
        cursor = self.source_editor.textCursor()
        cursor.setPosition(max(0, start))
        cursor.setPosition(max(start, end), QTextCursor.KeepAnchor)
        self.source_editor.setTextCursor(cursor)
        if focus:
            self.source_editor.setFocus()

    def _call_files_for_source(self, source: str) -> list[Path]:
        result = []
        seen = set()

        def collect(text: str, depth: int) -> None:
            if depth >= 8:
                return
            for match in _CALL_RE.finditer(text):
                file_path = self._resolve_call_file(match.group("path"))
                if file_path is None:
                    continue
                key = str(file_path).casefold()
                if key in seen:
                    continue
                seen.add(key)
                result.append(file_path)
                nested = self._read_call_file(file_path)
                if nested:
                    collect(nested, depth + 1)


        collect(source, 0)
        return result

    def _str_expanded_move_block_reason(self, component: LayoutComponent) -> str:
        if not bool(component.node.props.get("str_expanded")):
            return ""
        if self._str_expanded_component_has_xy(component):
            return ""
        return "STR 变量展开出来的组件没有可回写的 X/Y 坐标，已取消移动"

    def _str_expanded_component_has_xy(self, component: LayoutComponent) -> bool:
        if component.node.kind not in _XY_COMPONENT_ARG_INDEXES:
            return False
        raw = str(component.node.props.get("expanded_raw") or component.node.raw or "").strip()
        if not raw:
            return False
        if component.node.kind == "positioned_text":
            return self._positioned_text_raw_has_xy(raw)
        indexes = _XY_COMPONENT_ARG_INDEXES.get(component.node.kind)
        if indexes is None:
            return False
        args = self._colon_tag_raw_args(raw)
        if args is None or len(args) <= max(indexes):
            return False
        return self._raw_int_arg(args[indexes[0]]) is not None and self._raw_int_arg(args[indexes[1]]) is not None

    def _colon_tag_raw_args(self, raw: str) -> list[str] | None:
        if not (raw.startswith("<") and raw.endswith(">")):
            return
        body = raw[1:-1].strip()
        if body.startswith("&"):
            body = body[1:].strip()
        if ":" not in body:
            return
        _command, payload = body.split(":", 1)
        if "/@" in payload:
            payload = payload.split("/@", 1)[0]
        if "|" in payload:
            payload = payload.split("|", 1)[0]
        if payload:
            return payload.split(":")
        return []

    def _positioned_text_raw_has_xy(self, raw: str) -> bool:
        if not (raw.startswith("<") and raw.endswith(">")):
            return False
        body = raw[1:-1].strip()
        if body.startswith("&"):
            body = body[1:].strip()
        if not body.lower().startswith("text:"):
            return False
        payload = body[5:]
        if "/@" in payload:
            payload = payload.split("/@", 1)[0]
        parts = payload.rsplit(":", 2)
        if len(parts) != 3:
            return False
        return self._raw_int_arg(parts[1]) is not None and self._raw_int_arg(parts[2]) is not None

    def _raw_int_arg(self, value: object) -> int | None:
        text = str(value).strip()
        match = re.match("^-?\\d+", text)
        if match:
            return int(match.group(0))
        return None

    def _component_edit_source_candidates(self, base_source: str | None = None) -> list[tuple[str, str]]:
        source = self._render_base_source() if base_source is None else base_source
        result = []
        seen = set()

        def add(path: str | Path | None, text: str) -> None:
            if not text:
                return
            key = self._call_source_key(path or "__editor__")
            if key in seen:
                return
            seen.add(key)
            result.append((str(path or "__editor__"), text))


        add(self.current_path or "__editor__", source)
        if self.source_view_path and self.current_path:
            if self.source_view_path != self.current_path:
                add(self.source_view_path, self.source_editor.toPlainText())
        for file_path in self._call_files_for_source(source):
            add(file_path, self._read_call_file(file_path))

        return result

    def _str_variable_name(self, component: LayoutComponent) -> str:
        for value in (
         component.node.props.get("str_parent_raw"),
         component.node.source.raw):
            match = _STR_REF_RE.fullmatch(str(value or "").strip())
            if match:
                return match.group("name").strip()
        return ""

    def _locate_str_expanded_component_source(self, component: LayoutComponent) -> tuple[str, str, int, int, str, bool] | None:
        raw = str(component.node.props.get("expanded_raw") or component.node.raw or "").strip()
        if not raw:
            return
        variable_name = self._str_variable_name(component)
        base_source = self._render_base_source()
        candidates = self._component_edit_source_candidates(base_source)
        if variable_name:
            for path, text in candidates:
                match = self._find_mov_value_component(text, variable_name, raw)
                if match is None:
                    continue
                start, end = match
                return (
                 path, text, start, end, text[start:end], True)
        for path, text in candidates:
            start = text.find(raw)
            if start < 0:
                start = text.casefold().find(raw.casefold())
            if start < 0:
                continue
            end = start + len(raw)
            return (
             path, text, start, end, text[start:end], self._source_span_is_mov_value(text, start, end))

    def _find_mov_value_component(self, source: str, variable_name: str, raw: str) -> tuple[int, int] | None:
        folded_name = variable_name.casefold()
        offset = 0
        for line in source.splitlines(True):
            text = line.rstrip("\r\n")
            match = _MOV_ASSIGN_RE.match(text)
            if match and match.group("name").casefold() == folded_name:
                if match.group("value") is not None:
                    value = match.group("value")
                    relative = value.find(raw)
                    if relative < 0:
                        relative = value.casefold().find(raw.casefold())
                    if relative >= 0:
                        start = offset + match.start("value") + relative
                        return (
                         start, start + len(raw))
            offset += len(line)

    def _component_edit_context(self, component: LayoutComponent) -> tuple[str, LayoutComponent, LayoutDocument | None, str] | None:
        editor_source = self.source_editor.toPlainText()
        if bool(component.node.props.get("str_expanded")):
            located = self._locate_str_expanded_component_source(component)
            if located is None:
                return
            file_path, text, start, end, raw, in_mov = located
            remapped = self._component_with_source_range(component,
              str(file_path),
              text,
              start,
              end,
              raw,
              props_update=({"mov_value_source": True} if in_mov else None))
            return (
             text, remapped, None, str(file_path))
        viewing_entry_source = not (
            self.source_view_path
            and self.current_path
            and self.source_view_path != self.current_path
        )
        if viewing_entry_source and self._component_belongs_to_editor_source(component, editor_source):
            return (
             editor_source, component, self.layout_document, self.source_view_path or self.current_path)
        if viewing_entry_source and self._component_from_simulated_source(component):
            located = self._locate_editor_component_source(component, editor_source, self.source_view_path or self.current_path or "__editor__")
            if located is not None:
                (text, start, end, raw, edit_component, edit_layout, in_mov, edit_path) = located
                if edit_component is not None:
                    return (text, edit_component, edit_layout, edit_path)
                remapped = self._component_with_source_range(component,
                  edit_path,
                  text,
                  start,
                  end,
                  raw,
                  props_update=({"mov_value_source": True} if in_mov else None))
                return (
                 text, remapped, None, edit_path)
        located = self._locate_called_component_source(component)
        if located is None:
            return
        (file_path, text, start, end, raw, edit_component, edit_layout, in_mov) = located
        if edit_component is not None:
            return (text, edit_component, edit_layout, str(file_path))
        remapped = self._component_with_source_range(component,
          str(file_path),
          text,
          start,
          end,
          raw,
          props_update=({"mov_value_source": True} if in_mov else None))
        return (
         text, remapped, None, str(file_path))

    def _component_from_simulated_source(self, component: LayoutComponent) -> bool:
        file_key = str(component.node.source.file_key or "").casefold()
        return "::simulated" in file_key or "::preview-simulated" in file_key

    def _locate_editor_component_source(self, component: LayoutComponent, text: str, path: str) -> tuple[str, int, int, str, LayoutComponent | None, LayoutDocument | None, bool, str] | None:
        if not text:
            return
        try:
            file_path = Path(path)
        except Exception:
            file_path = Path("__editor__")
        for needle in self._component_edit_needles(component):
            best_direct = self._best_direct_source_match(file_path, text, needle, component)
            if best_direct is not None:
                start, end, edit_component, edit_layout = best_direct
                return (
                 text, start, end, text[start:end], edit_component, edit_layout, False, path)
            for start in self._find_source_occurrences(text, needle):
                end = start + len(needle)
                in_mov = self._source_span_is_mov_value(text, start, end)
                if self._component_edit_needs_layout(component):
                    continue
                return (
                 text, start, end, text[start:end], None, None, in_mov, path)

        layout_match = self._best_called_layout_component_match(file_path, text, component)
        if layout_match is None:
            return
        (start, end, edit_component, edit_layout) = layout_match
        in_mov = self._source_span_is_mov_value(text, start, end)
        return (
         text, start, end, text[start:end], edit_component, edit_layout, in_mov, path)

    def _locate_called_component_source(self, component: LayoutComponent) -> tuple[Path, str, int, int, str, LayoutComponent | None, LayoutDocument | None, bool] | None:
        needles = self._component_edit_needles(component)
        base_source = self._render_base_source()
        candidates = []
        if self.source_view_path and self.current_path and self.source_view_path != self.current_path:
            with contextlib.suppress(Exception):
                candidates.append(Path(self.source_view_path))
        candidates.extend(self._call_files_for_source(base_source))
        seen = set()
        for file_path in candidates:
            key = self._call_source_key(file_path)
            if key in seen:
                continue
            seen.add(key)
            text = self._read_call_file(file_path)
            if not text:
                continue
            for needle in needles:
                best_direct = self._best_direct_source_match(file_path, text, needle, component)
                if best_direct is not None:
                    start, end, edit_component, edit_layout = best_direct
                    return (
                     file_path, text, start, end, text[start:end], edit_component, edit_layout, False)
                for start in self._find_source_occurrences(text, needle):
                    end = start + len(needle)
                    in_mov = self._source_span_is_mov_value(text, start, end)
                    if self._component_edit_needs_layout(component):
                        continue
                    return (
                     file_path, text, start, end, text[start:end], None, None, in_mov)

                layout_match = self._best_called_layout_component_match(file_path, text, component)
                if layout_match is not None:
                    (start, end, edit_component, edit_layout) = layout_match
                    in_mov = self._source_span_is_mov_value(text, start, end)
                    return (
                     file_path, text, start, end, text[start:end], edit_component, edit_layout, in_mov)
        return None

    def _find_source_occurrences(self, source: str, needle: str) -> list[int]:
        if not needle:
            return []
        result = []
        start = source.find(needle)
        while start >= 0:
            result.append(start)
            start = source.find(needle, start + max(1, len(needle)))

        if result:
            return result
        folded_source = source.casefold()
        folded_needle = needle.casefold()
        start = folded_source.find(folded_needle)
        while start >= 0:
            result.append(start)
            start = folded_source.find(folded_needle, start + max(1, len(folded_needle)))

        return result

    def _source_span_is_mov_value(self, source: str, start: int, end: int) -> bool:
        line_start = source.rfind("\n", 0, start) + 1
        line_end = source.find("\n", end)
        if line_end < 0:
            line_end = len(source)
        line = source[line_start:line_end].rstrip("\r")
        match = _MOV_ASSIGN_RE.match(line)
        if not match or match.group("value") is None:
            return False
        relative_start = start - line_start
        relative_end = end - line_start
        return relative_start >= match.start("value") and relative_end <= match.end("value")

    def _best_direct_source_match(self, file_path: Path, text: str, needle: str, component: LayoutComponent) -> tuple[int, int, LayoutComponent, LayoutDocument] | None:
        layout = self._edit_layout_for_source_text(str(file_path), text)
        if layout is None:
            return
        best = None
        for start in self._find_source_occurrences(text, needle):
            end = start + len(needle)
            if self._source_span_is_mov_value(text, start, end):
                continue
            candidates = [
                item for item in layout.components
                if item.node.kind == component.node.kind
                and item.node.source.start == start
                and item.node.source.end == end
            ]
            if not candidates:
                candidates = [
                    item for item in layout.components
                    if item.node.kind == component.node.kind
                    and item.node.raw == needle
                    and item.node.source.start == start
                ]
            for candidate in candidates:
                score = (abs(candidate.visual_rect.y - component.visual_rect.y),
                 abs(candidate.visual_rect.x - component.visual_rect.x),
                 candidate.node.source.start)
                if best is None or score < best[0]:
                    best = (
                     score, start, end, candidate)

        if best is None:
            return
        _score, start, end, edit_component = best
        return (
         start, end, edit_component, layout)

    def _best_called_layout_component_match(self, file_path: Path, text: str, component: LayoutComponent) -> tuple[int, int, LayoutComponent, LayoutDocument] | None:
        layout = self._edit_layout_for_source_text(str(file_path), text)
        if layout is None:
            return
        target_raws = {value.casefold() for value in self._component_edit_needles(component)}
        target_text = self._component_match_text(component)
        text_can_identify = self._component_text_can_identify(component)
        target_resource = self._component_resource_spec(component)
        best = None
        for candidate in layout.components:
            if candidate.node.kind != component.node.kind:
                continue
            start = int(candidate.node.source.start)
            end = int(candidate.node.source.end)
            if start < 0 or end <= start or end > len(text):
                continue
            raw_match = any((value.casefold() in target_raws for value in self._component_edit_needles(candidate)))
            text_match = bool(text_can_identify and target_text and target_text == self._component_match_text(candidate))
            resource_match = target_resource is not None and target_resource == self._component_resource_spec(candidate)
            if not (raw_match or text_match or resource_match):
                continue
            source_slice = text[start:end]
            if source_slice != candidate.node.source.raw:
                continue
            score = (
             0 if raw_match else 1,
             0 if resource_match else 1,
             abs(candidate.visual_rect.y - component.visual_rect.y),
             abs(candidate.visual_rect.x - component.visual_rect.x),
             start)
            if best is None or score < best[0]:
                best = (
                 score, candidate)

        if best is None:
            return
        candidate = best[1]
        return (
         int(candidate.node.source.start),
         int(candidate.node.source.end),
         candidate,
         layout)

    def _component_match_text(self, component: LayoutComponent) -> str:
        return str(component.node.text or "").strip()

    def _component_text_can_identify(self, component: LayoutComponent) -> bool:
        if component.node.kind in _PIXMAP_COMPONENT_KINDS:
            return False
        if component.node.kind in {'break', 'layout', 'listview', 'tag', 'container_newline'}:
            return False
        return True

    def _component_edit_needs_layout(self, component: LayoutComponent) -> bool:
        return component.node.kind not in _XY_COMPONENT_ARG_INDEXES

    def _edit_layout_for_source_text(self, file_key: str, text: str) -> LayoutDocument | None:
        try:
            document = self.engine.parse(text, file_key=file_key)
        except Exception:
            return
        else:
            label = str(getattr(self.layout_document, "label", "") or "")
            block = document.label_by_name(label) if label else document.labels[0] if document.labels else None
            fallback_background = None
            if self.layout_document is not None:
                if self.layout_document.background is not None:
                    fallback_background = self.layout_document.background.node
            try:
                return self.engine.layout_engine.layout(block,
                  image_size_resolver=self._measure_node_size,
                  fallback_background_node=fallback_background)
            except Exception:
                return

    def _component_edit_needles(self, component: LayoutComponent) -> list[str]:
        values = []
        for value in (
         component.node.source.raw,
         component.node.raw,
         str(component.node.props.get("expanded_raw", "") or ""),
         str(component.node.props.get("str_parent_raw", "") or "")):
            text = str(value or "").strip()
            if not text:
                continue
            if text not in values:
                values.append(text)
        return values

    def _component_with_source_range(self, component: LayoutComponent, file_key: str, source_text: str, start: int, end: int, raw: str, props_update: dict[str, Any] | None = None) -> LayoutComponent:
        line = source_text.count("\n", 0, start) + 1
        line_start = source_text.rfind("\n", 0, start) + 1
        column = start - line_start + 1
        source_ref = SourceRef(file_key=file_key, start=start, end=end, line=line, column=column, raw=raw)
        props = dict(component.node.props)
        if props_update:
            props.update(props_update)
        node = replace((component.node), source=source_ref, props=props)
        return replace(component, node=node)

    def _encoding_for_source_path(self, path: str | Path) -> str:
        path_text = str(path or "")
        if path_text and self.current_path:
            if path_text.casefold() == self.current_path.casefold():
                return self.current_encoding or "gb18030"
        if path_text and self.source_view_path:
            if path_text.casefold() == self.source_view_path.casefold():
                if self.source_view_encoding:
                    return self.source_view_encoding
        if path_text and Path(path_text).is_file():
            try:
                _text, encoding = self.context.read_text_file(path_text)
                if encoding:
                    return encoding
            except Exception:
                pass
        return self.current_encoding or "gb18030"

    def _write_source_file(self, path: str, source: str, expected_source: str) -> bool:
        if not path or path == "__editor__":
            return True
        target = Path(path)
        stage_path: Path | None = None
        replaced = False
        replace_attempted = False
        original_raw = b""
        original_stat = None
        encoded = b""
        try:
            if not target.is_file() or target.is_symlink():
                raise RuntimeError("NPC 源文件不是可写的普通文件")
            identity_key = self._source_identity_key(target)
            expected_identity = self._source_file_identities.get(identity_key)
            encoding = self._encoding_for_source_path(path) or "gb18030"
            normalize = lambda value: str(value).replace("\r\n", "\n").replace("\r", "\n")
            token = secrets.token_hex(8)
            backup_path = target.with_name(f".{target.name}.xiami-npc-backup-{token}.bak")
            stage_path = target.with_name(f".{target.name}.xiami-npc-stage-{token}.tmp")
            initial_raw = target.read_bytes()
            initial_guard_identity = target_identity(target)
            with protected_target(
                target,
                expected_exists=True,
                expected_raw=initial_raw,
                expected_identity=initial_guard_identity,
            ) as target_guard:
                original_raw = target_guard.assert_current()
                original_stat = os.stat(str(target), follow_symlinks=False)
                current_identity = self._source_file_identity(target, original_raw)
                current_text = original_raw.decode(encoding, errors="strict")
                if expected_identity is not None and current_identity != expected_identity:
                    raise RuntimeError("NPC 源文件已被其他程序修改（identity 漂移），已拒绝覆盖")
                if normalize(current_text) != normalize(expected_source):
                    raise RuntimeError("NPC 源文件已被其他程序修改（内容漂移），已拒绝覆盖")

                newline = "\r\n" if b"\r\n" in original_raw else "\n"
                normalized = normalize(source)
                if newline == "\r\n":
                    normalized = normalized.replace("\n", "\r\n")
                encoded = normalized.encode(encoding, errors="strict")
                write_exclusive(backup_path, original_raw)
                if backup_path.read_bytes() != original_raw:
                    raise IOError("NPC 源文件备份回读不一致")
                write_exclusive(stage_path, encoded)
                if stage_path.read_bytes() != encoded:
                    raise IOError("NPC 源文件 stage 回读不一致")
                target_guard.assert_current()
                replace_attempted = True
                target_guard.replace_from(stage_path, encoded)
                replaced = True
                stage_path = None
            with protected_target(target, expected_exists=True, expected_raw=encoded) as committed_guard:
                if original_stat is not None:
                    os.chmod(str(target), int(original_stat.st_mode) & 0o7777)
                committed_raw = committed_guard.assert_current()
                self._source_file_identities[identity_key] = self._source_file_identity(target, committed_raw)
            self._log(f"NPC 源文件已原子写入，备份：{backup_path.name}")
            return True
        except Exception as exc:
            if replace_attempted and target.is_file() and not target.is_symlink():
                try:
                    installed_raw = target.read_bytes()
                    replaced = replaced or installed_raw == encoded
                    if not replaced:
                        raise RuntimeError("提交未安装，跳过回滚")
                    atomic_restore_bytes(
                        target,
                        original_raw,
                        expected_exists=True,
                        expected_raw=encoded,
                        prefix="xiami-npc-restore",
                        mode=None if original_stat is None else int(original_stat.st_mode) & 0o7777,
                        atime_ns=None if original_stat is None else int(getattr(original_stat, "st_atime_ns", 0)),
                        mtime_ns=None if original_stat is None else int(getattr(original_stat, "st_mtime_ns", 0)),
                    )
                    restored_raw = target.read_bytes()
                    if restored_raw != original_raw:
                        raise IOError("回滚回读不一致")
                    self._source_file_identities[self._source_identity_key(target)] = self._source_file_identity(
                        target,
                        restored_raw,
                    )
                except Exception as rollback_exc:
                    if replaced:
                        exc = RuntimeError(f"{exc}；NPC 源文件回滚失败：{rollback_exc}")
            self._log(f"源码写入失败：{path} / {exc}")
            self.status_label.setText(f"源码写入失败：{exc}")
            return False
        finally:
            for residue in (stage_path,):
                if residue is None:
                    continue
                with contextlib.suppress(OSError):
                    residue.unlink()

    def _set_editor_source_after_edit(self, path: str, source: str, expected_source: str | None = None) -> bool:
        file_key = str(path or "__editor__")
        self._pending_edit_document = None
        try:
            parsed_document = self.engine.parse(source, file_key=file_key)
            self._hydrate_document_runtime_values(parsed_document)
        except Exception as exc:
            message = _error_text(exc)
            self.status_label.setText("NPC 编辑预解析失败，未写入源文件")
            self._log(f"NPC 编辑预解析失败，未写入源文件：{message}")
            return False
        if self.template_mode or not path or path == "__editor__":
            self.primary_source = source
            self.source_view_path = "__editor__"
            self.source_view_encoding = "gb18030"
            if self.template_mode:
                self.template_dirty = True
            self._set_source_editor_text_programmatically(source)
            self._pending_edit_document = (file_key, source, parsed_document)
            return True
        expected = self.source_editor.toPlainText() if expected_source is None else expected_source
        if not self._write_source_file(path, source, expected):
            return False
        if path and self.current_path and str(path).casefold() != str(self.current_path).casefold():
            encoding = self._encoding_for_source_path(path)
            self._set_call_source_override(path, source)
            self.source_view_path = path
            self.source_view_encoding = encoding
        else:
            self.primary_source = source
            self.source_view_path = self.current_path
            self.source_view_encoding = self.current_encoding
        self._set_source_editor_text_programmatically(source)
        self._pending_edit_document = (file_key, source, parsed_document)
        return True

    def _component_belongs_to_editor_source(self, component: LayoutComponent, editor_source: str) -> bool:
        source = component.node.source
        start = max(0, int(source.start))
        end = max(start, int(source.end))
        if end > len(editor_source):
            return False
        raw = str(source.raw or component.node.raw or "")
        return editor_source[start:end] == raw

    def _jump_to_label_source(self, label: str) -> None:
        block = self._exact_label_block(label)
        if block is None:
            return
        self._jump_to_label_block(block)

    def _jump_to_label_block(self, block: Any) -> None:
        source = block.source
        editor_source = self.source_editor.toPlainText()
        start = max(0, int(source.start))
        end = max(start, int(source.end))
        if end > len(editor_source):
            if self._jump_to_call_line_for_label(str(block.label or "")):
                return
            self._log(f"标签来自 #CALL 展开内容，当前源码框不直接定位：{block.label}")
            return
        cursor = self.source_editor.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        self.source_editor.setTextCursor(cursor)
        self.source_editor.setFocus()

    def _jump_to_call_line_for_label(self, label: str) -> bool:
        if not label:
            return False
        editor_source = self.source_editor.toPlainText()
        for match in _CALL_RE.finditer(editor_source):
            if match.group("label").strip().casefold() != label.casefold():
                continue
            cursor = self.source_editor.textCursor()
            cursor.setPosition(match.start())
            cursor.setPosition(match.end(), QTextCursor.KeepAnchor)
            self.source_editor.setTextCursor(cursor)
            self.source_editor.setFocus()
            return True

        return False

    def _render_after_edit(self, result: Any) -> None:
        source = self._render_base_source()
        file_key = self.current_path or "__editor__"
        current_label = self._current_label()
        current_index = self._current_label_index()
        render_source = self._source_for_render(source)
        pending = self._pending_edit_document
        self._pending_edit_document = None
        if pending is not None and pending[0] == file_key and pending[1] == render_source:
            self.document = pending[2]
            # Parsing and runtime hydration already succeeded before the file
            # commit. Do not introduce a second authorization failure window
            # after the source has been replaced on disk.
            self._parsed_document_cache_key = None
            self._parsed_document_cache = None
        else:
            self.document = self._parse_render_document(render_source, file_key)
        fallback_background = self._main_background_node(source, file_key, document=self.document)
        block, current_label = self._effective_render_block(source, current_label, current_index)
        new_layout = self.engine.layout_engine.layout(
            block,
            image_size_resolver=self._measure_node_size,
            fallback_background_node=fallback_background,
        )
        if self._can_partial_refresh(new_layout, result):
            self._refresh_dirty_rows(new_layout, result)
            self._restore_selection(result)
            self._log(f'局部刷新行：{tuple(getattr(result, "dirty_rows", ()) or ())}')
            self.status_label.setText(f'局部刷新：{current_label or "无标签"} / {len(new_layout.components)} 个组件')
            return
        self.layout_document = new_layout
        self._paint_layout(new_layout)
        self._restore_selection(result)
        self.status_label.setText(f'已渲染：{current_label or "无标签"} / {len(new_layout.components)} 个组件')

    def _can_partial_refresh(self, new_layout: LayoutDocument, result: Any) -> bool:
        if self.layout_document is None:
            return False
        dirty_rows = tuple(getattr(result, "dirty_rows", ()) or ())
        if not dirty_rows:
            return False
        old = self.layout_document
        return old.width == new_layout.width and old.height == new_layout.height and old.row_height == new_layout.row_height and old.content_x == new_layout.content_x and old.content_y == new_layout.content_y

    def _refresh_dirty_rows(self, new_layout: LayoutDocument, result: Any) -> None:
        dirty_rows = set(getattr(result, "dirty_rows", ()) or ())
        for node_id, item in list(self.component_items.items()):
            if item.component.row in dirty_rows:
                self.scene.removeItem(item)
                del self.component_items[node_id]

        for component in sorted(new_layout.components, key=lambda item: item.z_index):
            if component.row not in dirty_rows:
                continue
            if _is_spacer_component(component):
                continue
            resource_image = self._resource_image_for_component(component)
            pixmap = self._pixmap_from_resource(resource_image)
            if self._should_skip_component_visual(component, pixmap, resource_image):
                continue
            origin = (
                (resource_image.origin_x, resource_image.origin_y)
                if resource_image is not None
                else (0, 0)
            )
            item = _VisualComponentItem(self, component, pixmap=pixmap, image_origin=origin)
            self.scene.addItem(item)
            self.component_items[component.node.id] = item
        self.layout_document = new_layout
        self._sync_existing_component_refs(new_layout, dirty_rows)

    def _sync_existing_component_refs(self, new_layout: LayoutDocument, dirty_rows: set[int]) -> None:
        unmatched = [component for component in new_layout.components if component.row not in dirty_rows if not _is_spacer_component(component)]
        used_ids = set(self.component_items)
        for item in list(self.component_items.values()):
            if item.component.row in dirty_rows:
                continue
            match = self._match_component_for_item(item.component, unmatched, used_ids)
            if match is not None:
                old_id = item.component.node.id
                item.component = match
                if old_id != match.node.id:
                    self.component_items.pop(old_id, None)
                    self.component_items[match.node.id] = item
                used_ids.add(match.node.id)

    def _match_component_for_item(self, old_component: LayoutComponent, candidates: list[LayoutComponent], used_ids: set[str]) -> LayoutComponent | None:
        best = None
        best_score = None
        for candidate in candidates:
            if candidate.node.id in used_ids:
                continue
            if candidate.row != old_component.row:
                continue
            if candidate.node.kind != old_component.node.kind:
                continue
            if candidate.node.raw != old_component.node.raw and candidate.node.text != old_component.node.text:
                continue
            score = (
             abs(candidate.rect.x - old_component.rect.x),
             abs(candidate.rect.width - old_component.rect.width),
             candidate.node.source.start)
            if best_score is None or score < best_score:
                best = candidate
                best_score = score
        return best

    def _restore_selection(self, selection_hint: Any) -> None:
        if selection_hint is None or self.layout_document is None:
            return
        hints = tuple(getattr(selection_hint, "selected_hints", ()) or ())
        if hints:
            matched = []
            used_ids = set()
            for hint in hints:
                component = self._find_component_by_hint(hint, used_ids=used_ids)
                if component is None or component.node.id not in self.component_items:
                    continue
                matched.append(component)
                used_ids.add(component.node.id)
            if matched:
                self._syncing_canvas_selection = True
                try:
                    self.scene.clearSelection()
                    for component in matched:
                        self.component_items[component.node.id].setSelected(True)
                finally:
                    self._syncing_canvas_selection = False
                self.selected_component_id = matched[0].node.id
                self._show_component_props(matched[0])
                self._sync_component_palette_selection(matched[0])
                self._update_selection_controls()
                return
        if not any((getattr(selection_hint, name, None) for name in ('selected_node_id', 'selected_raw',
                                                                     'selected_kind', 'selected_text'))):
            return
        component = self._find_component_by_hint(selection_hint)
        if component is None:
            self._log("移动后未能恢复选中组件")
            return
        self.select_component(component, jump_source=True)

    def _find_component_by_hint(self, hint: Any, used_ids: set[str] | None = None) -> LayoutComponent | None:
        if self.layout_document is None:
            return
        used_ids = used_ids or set()
        components = [
            component
            for component in self.layout_document.components
            if not _is_spacer_component(component) and component.node.id not in used_ids
        ]
        selected_id = str(getattr(hint, "selected_node_id", "") or "")
        if selected_id:
            for component in components:
                if component.node.id == selected_id:
                    return component
        selected_raw = str(getattr(hint, "selected_raw", "") or "")
        selected_kind = str(getattr(hint, "selected_kind", "") or "")
        selected_text = str(getattr(hint, "selected_text", "") or "")
        selected_row = self._hint_int(hint, "selected_row")
        selected_x = self._hint_int(hint, "selected_x")
        candidates = components
        if selected_raw:
            raw_matches = [component for component in candidates if component.node.raw == selected_raw]
            if raw_matches:
                return self._nearest_component(raw_matches, selected_row, selected_x)
        if selected_kind:
            candidates = [component for component in components if component.node.kind == selected_kind]
        if selected_text:
            text_matches = [component for component in candidates if component.node.text == selected_text]
            if text_matches:
                return self._nearest_component(text_matches, selected_row, selected_x)
        if selected_kind and candidates:
            return self._nearest_component(candidates, selected_row, selected_x)

    def _hint_int(self, hint: Any, name: str) -> int:
        try:
            return int(getattr(hint, name, -1))
        except Exception:
            return -1

    def _nearest_component(self, components: list[LayoutComponent], target_row: int, target_x: int) -> LayoutComponent:
        def score(component: LayoutComponent) -> tuple[int, int, int]:
            row_score = abs(component.row - target_row) if target_row >= 0 else 0
            x_score = abs(component.rect.x - target_x) if target_x >= 0 else 0
            return (
             row_score, x_score, component.node.source.start)


        return min(components, key=score)

    def _show_component_props(self, component: LayoutComponent, moved_to: tuple[int, int] | None = None) -> None:
        node = component.node
        rows = [
         (
          "ID", node.id),
         (
          "类型", node.kind),
         (
          "源码", node.raw),
         (
          "显示文本", node.text),
         (
          "源码位置", f"{node.source.line}:{node.source.column}"),
         (
          "占位", f"{component.rect.x},{component.rect.y} {component.rect.width}x{component.rect.height}"),
          (
           "显示", f"{component.visual_rect.x},{component.visual_rect.y} {component.visual_rect.width}x{component.visual_rect.height}")]
        if moved_to is not None:
            rows.append(("移动预览", f"{moved_to[0]},{moved_to[1]}"))
        for key, value in node.props.items():
            rows.append((str(key), str(value)))

        self.props_table.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            self.props_table.setItem(row, 0, QTableWidgetItem(key))
            self.props_table.setItem(row, 1, QTableWidgetItem(value))

    def _log(self, message: str) -> None:
        self._event_log_messages.append(message)
        del self._event_log_messages[:-200]


def create_npc_visual_v2_page(parent: QWidget, context: NpcToolContext) -> QWidget:
    return NpcVisualV2Page(parent, context)
