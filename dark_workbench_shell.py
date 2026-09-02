# -*- coding: utf-8 -*-
"""Dark Workbench shell prototype shared by preview and migration work."""

from __future__ import annotations

import json
import os
from typing import Optional

from toolbox_crash_logging import write_event as _write_crash_event

try:
    from __main__ import QtCore, QtGui, QtWidgets  # type: ignore[attr-defined]
except Exception:  # pragma: no cover - standalone preview/import fallback
    try:
        from PySide2 import QtCore, QtGui, QtWidgets
    except Exception:
        from PySide6 import QtCore, QtGui, QtWidgets


def ensure_dark_workbench_qt_plugins() -> None:
    """Point Qt at the bundled Qt plugins for the active interpreter."""
    binding_module = str(getattr(QtCore, "__package__", "") or "").split(".", 1)[0]
    if binding_module not in {"PySide2", "PySide6"}:
        return
    try:
        _PySide = __import__(binding_module)
    except Exception:
        return

    root = os.path.dirname(getattr(_PySide, "__file__", "") or "")
    if not root:
        return
    plugins_dir = os.path.join(root, "plugins")
    platforms_dir = os.path.join(plugins_dir, "platforms")
    qwindows = os.path.join(platforms_dir, "qwindows.dll")
    if not os.path.exists(qwindows):
        return

    os.environ["QT_PLUGIN_PATH"] = plugins_dir
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = platforms_dir
    try:
        QtCore.QCoreApplication.setLibraryPaths([plugins_dir])
    except Exception:
        pass


ensure_dark_workbench_qt_plugins()


class DarkWorkbenchTokens:
    BG = "#F3F5F7"
    CHROME = "#FCFDFE"
    PANEL = "#FCFDFE"
    PANEL_2 = "#F7F8FA"
    LINE = "#D4DAE1"
    LINE_SOFT = "#E6EAEF"
    TEXT = "#17202A"
    TEXT_SOFT = "#475467"
    MUTED = "#667085"
    SUBTLE = "#98A2B3"
    BRAND = "#C45100"
    BRAND_2 = "#2563A6"
    WINDOW_W = 1440
    WINDOW_H = 860
    TITLE_H = 56
    SIDEBAR_W = 224
    PAGE_HEAD_H = 42
    STATUS_H = 32
    LOG_H = 128
    RADIUS = 6


def dw_apply_role(widget: QtWidgets.QWidget, name: str, value: str) -> QtWidgets.QWidget:
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    return widget


def dw_label(text: str, role: str = "normal") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    dw_apply_role(label, "labelRole", role)
    return label


def dw_button(text: str, role: str = "secondary") -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setCursor(QtCore.Qt.PointingHandCursor)
    dw_apply_role(button, "buttonRole", role)
    if role in ("primary", "secondary", "tertiary", "danger", "compact", "segmented", "icon"):
        height = 28 if role in ("compact", "segmented", "icon") else 32
        button.setMinimumHeight(height)
        button.setMaximumHeight(height)
        if role == "icon":
            button.setMinimumWidth(28)
            button.setMaximumWidth(28)
    return button


class DarkWorkbenchDropButton(QtWidgets.QPushButton):
    payloadDropped = QtCore.Signal(str, str, str)

    def __init__(self, text: str, key: str) -> None:
        super().__init__(text)
        self._drop_key = str(key or "").strip()
        self.setAcceptDrops(True)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        dw_apply_role(self, "buttonRole", "global-tool")

    def _payload_from_mime(self, mime) -> tuple[str, str]:
        try:
            if mime is not None and mime.hasUrls():
                urls = mime.urls()
                if urls:
                    url = urls[0]
                    local = url.toLocalFile()
                    if local:
                        return "file", local
                    text = url.toString()
                    if text:
                        return "url", text
        except Exception:
            pass
        try:
            if mime is not None and mime.hasText():
                text = str(mime.text() or "").strip()
                if text:
                    return "text", text
        except Exception:
            pass
        return "", ""

    def dragEnterEvent(self, event) -> None:
        kind, payload = self._payload_from_mime(event.mimeData())
        if kind and payload:
            self.setProperty("dropState", "hover")
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dropState", "")
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self.setProperty("dropState", "")
        self.style().unpolish(self)
        self.style().polish(self)
        kind, payload = self._payload_from_mime(event.mimeData())
        if kind and payload:
            self.payloadDropped.emit(self._drop_key, kind, payload)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


class DarkWorkbenchGlobalToolsButton(QtWidgets.QToolButton):
    payloadDropped = QtCore.Signal(str, str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)

    @staticmethod
    def _payload_from_mime(mime) -> tuple[str, str]:
        try:
            if mime is not None and mime.hasUrls():
                urls = mime.urls()
                if urls:
                    local = urls[0].toLocalFile()
                    if local:
                        return "file" if os.path.isfile(local) else "folder", local
                    value = urls[0].toString()
                    if value:
                        return "url", value
        except Exception:
            pass
        try:
            if mime is not None and mime.hasText():
                value = str(mime.text() or "").strip()
                if value:
                    return "text", value
        except Exception:
            pass
        return "", ""

    def dragEnterEvent(self, event) -> None:
        kind, payload = self._payload_from_mime(event.mimeData())
        if kind and payload:
            self.setProperty("dropState", "hover")
            self.style().unpolish(self)
            self.style().polish(self)
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("dropState", "")
        self.style().unpolish(self)
        self.style().polish(self)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self.setProperty("dropState", "")
        self.style().unpolish(self)
        self.style().polish(self)
        kind, payload = self._payload_from_mime(event.mimeData())
        if kind and payload:
            self.payloadDropped.emit(kind, payload)
            event.acceptProposedAction()
            return
        super().dropEvent(event)


def dw_panel(role: str = "panel") -> QtWidgets.QFrame:
    frame = QtWidgets.QFrame()
    frame.setFrameShape(QtWidgets.QFrame.NoFrame)
    dw_apply_role(frame, "panelRole", role)
    return frame


def dw_input(text: str, role: str = "normal") -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    dw_apply_role(label, "fieldRole", role)
    return label


def dw_badge(text: str, role: str = "muted") -> QtWidgets.QLabel:
    badge = QtWidgets.QLabel(text)
    badge.setAlignment(QtCore.Qt.AlignCenter)
    dw_apply_role(badge, "badgeRole", role)
    return badge


class DarkWorkbenchNavItem(QtWidgets.QFrame):
    clicked = QtCore.Signal(str)

    def __init__(self, key: str, icon: str, text: str, badge: str = "", active: bool = False) -> None:
        super().__init__()
        self.key = str(key or "")
        self.indicator: Optional[QtWidgets.QFrame] = None
        self.icon_label: Optional[QtWidgets.QLabel] = None
        self.text_label: Optional[QtWidgets.QLabel] = None
        self._drag_press_pos: Optional[QtCore.QPoint] = None
        self._drag_started = False
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setToolTip(f"{icon} · {text}")
        dw_apply_role(self, "panelRole", "nav-active" if active else "nav")
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(3, 0, 5, 0)
        layout.setSpacing(4)
        indicator = QtWidgets.QFrame()
        indicator.setObjectName("navActiveIndicator")
        indicator.setFixedWidth(3)
        dw_apply_role(indicator, "stateRole", "active" if active else "idle")
        self.indicator = indicator
        layout.addWidget(indicator)
        icon_label = QtWidgets.QLabel(icon)
        icon_label.setAlignment(QtCore.Qt.AlignCenter)
        dw_apply_role(icon_label, "labelRole", "nav-icon-active" if active else "nav-icon")
        self.icon_label = icon_label
        layout.addWidget(icon_label)
        text_label = dw_label(text, "nav-active" if active else "nav")
        self.text_label = text_label
        layout.addWidget(text_label, 1)
        if badge:
            layout.addWidget(dw_badge(badge, "nav"))

    def mousePressEvent(self, event) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_press_pos = event.pos()
            self._drag_started = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if (
            self._drag_press_pos is not None
            and bool(event.buttons() & QtCore.Qt.LeftButton)
            and bool(self.property("navDragEnabled") is not False)
            and (event.pos() - self._drag_press_pos).manhattanLength() >= QtWidgets.QApplication.startDragDistance()
        ):
            self._drag_started = True
            drag = QtGui.QDrag(self)
            mime = QtCore.QMimeData()
            mime.setData("application/x-xiami-sidebar-nav", self.key.encode("utf-8"))
            drag.setMimeData(mime)
            pixmap = self.grab()
            drag.setPixmap(pixmap)
            drag.setHotSpot(event.pos())
            self.setProperty("navDragging", True)
            self.style().unpolish(self)
            self.style().polish(self)
            try:
                drag.exec_(QtCore.Qt.MoveAction)
            except AttributeError:
                drag.exec(QtCore.Qt.MoveAction)
            self.setProperty("navDragging", False)
            self.style().unpolish(self)
            self.style().polish(self)
            self._drag_press_pos = None
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == QtCore.Qt.LeftButton and self._drag_press_pos is not None and not self._drag_started:
            self.clicked.emit(self.key)
        self._drag_press_pos = None
        self._drag_started = False
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space):
            self.clicked.emit(self.key)
            event.accept()
            return
        super().keyPressEvent(event)

    def set_active(self, active: bool) -> None:
        dw_apply_role(self, "panelRole", "nav-active" if active else "nav")
        if self.indicator is not None:
            dw_apply_role(self.indicator, "stateRole", "active" if active else "idle")
        if self.icon_label is not None:
            dw_apply_role(self.icon_label, "labelRole", "nav-icon-active" if active else "nav-icon")
        if self.text_label is not None:
            dw_apply_role(self.text_label, "labelRole", "nav-active" if active else "nav")


class DarkWorkbenchNavContainer(QtWidgets.QWidget):
    navDropped = QtCore.Signal(str, str, bool)
    navHoverChanged = QtCore.Signal(str, str)
    navHoverCleared = QtCore.Signal()
    MIME_TYPE = "application/x-xiami-sidebar-nav"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def _source_key(self, event) -> str:
        try:
            return bytes(event.mimeData().data(self.MIME_TYPE)).decode("utf-8", "ignore").strip()
        except Exception:
            return ""

    def _target_at(self, pos: QtCore.QPoint) -> tuple[Optional[DarkWorkbenchNavItem], bool]:
        widget = self.childAt(pos)
        while widget is not None and widget is not self:
            if isinstance(widget, DarkWorkbenchNavItem):
                return widget, pos.y() < widget.geometry().center().y()
            widget = widget.parentWidget()
        rows = [row for row in self.findChildren(DarkWorkbenchNavItem) if row.isVisible()]
        if not rows:
            return None, True
        target = min(rows, key=lambda row: abs(row.geometry().center().y() - pos.y()))
        return target, pos.y() < target.geometry().center().y()

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(self.MIME_TYPE):
            event.setDropAction(QtCore.Qt.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragMoveEvent(self, event) -> None:
        if not self._source_key(event):
            event.ignore()
            return
        target, before = self._target_at(event.pos())
        if target is not None:
            self.navHoverChanged.emit(target.key, "before" if before else "after")
            event.setDropAction(QtCore.Qt.MoveAction)
            event.accept()
            return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self.navHoverCleared.emit()
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        source_key = self._source_key(event)
        target, before = self._target_at(event.pos())
        self.navHoverCleared.emit()
        if source_key and target is not None:
            self.navDropped.emit(source_key, target.key, before)
            event.setDropAction(QtCore.Qt.MoveAction)
            event.accept()
            return
        event.ignore()


class DarkWorkbenchDockTab(QtWidgets.QFrame):
    clicked = QtCore.Signal(str)
    MIN_W = 58
    MAX_W = 76

    def __init__(self, key: str, icon: str, title: str, subtitle: str, active: bool = False) -> None:
        super().__init__()
        self.key = str(key or "")
        self.status_bar: Optional[QtWidgets.QFrame] = None
        self.icon_label: Optional[QtWidgets.QLabel] = None
        self.title_label: Optional[QtWidgets.QLabel] = None
        self.subtitle_label: Optional[QtWidgets.QLabel] = None
        self.setMinimumWidth(self.MIN_W)
        self.setMaximumWidth(self.MAX_W)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setToolTip(f"{title} ({icon}) · {subtitle}")
        dw_apply_role(self, "panelRole", "dock-active" if active else "dock")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(2, 1, 2, 1)
        layout.setSpacing(1)

        status_bar = QtWidgets.QFrame()
        status_bar.setObjectName("dockTabStatus")
        dw_apply_role(status_bar, "stateRole", "active" if active else "idle")
        self.status_bar = status_bar
        layout.addWidget(status_bar)

        icon_label = QtWidgets.QLabel(icon)
        icon_label.setAlignment(QtCore.Qt.AlignCenter)
        dw_apply_role(icon_label, "labelRole", "dock-icon-active" if active else "dock-icon")
        self.icon_label = icon_label
        layout.addWidget(icon_label, 0, QtCore.Qt.AlignCenter)

        text_box = QtWidgets.QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(0)
        title_label = dw_label(title, "dock-title-active" if active else "dock-title")
        title_label.setAlignment(QtCore.Qt.AlignCenter)
        title_label.setMinimumWidth(0)
        self.title_label = title_label
        self.subtitle_label = None
        text_box.addWidget(title_label)
        layout.addLayout(text_box)

    def mousePressEvent(self, event) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self.clicked.emit(self.key)
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        dw_apply_role(self, "panelRole", "dock-active" if active else "dock")
        if self.status_bar is not None:
            dw_apply_role(self.status_bar, "stateRole", "active" if active else "idle")
        if self.icon_label is not None:
            dw_apply_role(self.icon_label, "labelRole", "dock-icon-active" if active else "dock-icon")
        if self.title_label is not None:
            dw_apply_role(self.title_label, "labelRole", "dock-title-active" if active else "dock-title")


class DarkWorkbenchPlaceholderPage(QtWidgets.QFrame):
    def __init__(self, title: str, body: str, *, accent: str = "info") -> None:
        super().__init__()
        dw_apply_role(self, "panelRole", "page")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)
        layout.addWidget(dw_label(title, "page-title"))
        layout.addWidget(dw_badge(body, accent))
        filler = QtWidgets.QLabel("这里会接入真实功能页。")
        filler.setWordWrap(True)
        dw_apply_role(filler, "labelRole", "muted")
        layout.addWidget(filler)
        layout.addStretch(1)


def _dw_effectively_visible(widget: QtWidgets.QWidget) -> bool:
    cur: QtWidgets.QWidget | None = widget
    while cur is not None:
        if cur.isHidden():
            return False
        cur = cur.parentWidget()
    return True


class DarkWorkbenchShell(QtWidgets.QWidget):
    SHELL_BREAKPOINT = 1320
    BRAND_ASSET_RELATIVE = os.path.join("outputs", "ui-assets", "brand-v2", "xiami-brand-v2-a.png")
    BRAND_ASSET_SHA256 = "f9e6d06e41281c12a3176afce5a98fceacdd910a63dcabf79251954038d72efe"

    def minimumSizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(1180, 720)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("darkWorkbenchWindow")
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowSystemMenuHint
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground, False)
        self.setWindowTitle("虾米工具箱 - Dark Workbench")
        self.resize(DarkWorkbenchTokens.WINDOW_W, DarkWorkbenchTokens.WINDOW_H)
        self.setMinimumSize(1180, 720)
        self._title_dragging = False
        self._title_drag_start_pos = QtCore.QPoint(0, 0)
        self._title_drag_start_top_left = QtCore.QPoint(0, 0)
        self._titlebar: Optional[QtWidgets.QFrame] = None
        self._sidebar_widget: Optional[QtWidgets.QFrame] = None
        self._sidebar_brand: Optional[QtWidgets.QFrame] = None
        self._sidebar_search_host: Optional[QtWidgets.QWidget] = None
        self._sidebar_footer: Optional[QtWidgets.QFrame] = None
        self._workspace_widget: Optional[QtWidgets.QFrame] = None
        self._page_header: Optional[QtWidgets.QFrame] = None
        self._page_content: Optional[QtWidgets.QWidget] = None
        self._page_title_row: Optional[QtWidgets.QWidget] = None
        self._statusbar_widget: Optional[QtWidgets.QFrame] = None
        self._sidebar_collapse_button: Optional[QtWidgets.QPushButton] = None
        self._sidebar_collapsed = False
        self._responsive_mode = "wide"
        self._shell_metrics_applied = False
        self._window_max_button: Optional[QtWidgets.QPushButton] = None
        self.window_close_requested = None
        self._allow_direct_close = False
        self.pages: dict[str, int] = {}
        self.page_widgets: dict[str, QtWidgets.QWidget] = {}
        self.page_meta: dict[str, dict[str, str]] = {}
        self.nav_rows: list[QtWidgets.QFrame] = []
        self.nav_items: dict[str, DarkWorkbenchNavItem] = {}
        self.sidebar_search_edit: Optional[QtWidgets.QLineEdit] = None
        self.sidebar_nav_scroll: Optional[QtWidgets.QScrollArea] = None
        self.sidebar_nav_groups: list[tuple[QtWidgets.QLabel, list[DarkWorkbenchNavItem]]] = []
        self._sidebar_nav_content: Optional[DarkWorkbenchNavContainer] = None
        self._sidebar_nav_layout: Optional[QtWidgets.QVBoxLayout] = None
        self.dock_items: dict[str, DarkWorkbenchDockTab] = {}
        self.bottom_ad_frame: Optional[QtWidgets.QFrame] = None
        self.bottom_ad_hint_label: Optional[QtWidgets.QLabel] = None
        self.bottom_ad_buttons: list[QtWidgets.QPushButton] = []
        self.bottom_ad_links: list[dict[str, object]] = []
        self.bottom_ad_style: dict[str, object] = {}
        self.friend_link_requested = None
        self.mounted_pages: dict[str, QtWidgets.QWidget] = {}
        self.project_edit: Optional[QtWidgets.QLabel] = None
        self.project_browse_btn: Optional[QtWidgets.QPushButton] = None
        self.brand_version_label: Optional[QtWidgets.QLabel] = None
        self.app_version_text = ""
        self.account_panel: Optional[QtWidgets.QFrame] = None
        self.account_avatar_label: Optional[QtWidgets.QLabel] = None
        self.account_name_label: Optional[QtWidgets.QLabel] = None
        self.account_state_label: Optional[QtWidgets.QLabel] = None
        self.account_logout_button: Optional[QtWidgets.QPushButton] = None
        self.account_requested = None
        self.account_logout_requested = None
        self.sidebar_collapse_requested = None
        self.auth_state = "logged_out"
        self.auth_user = ""
        self.auth_summary = "点击登录"
        self.auth_gate_enabled = False
        self.auth_gate_bypass = False
        self._current_page_key = ""
        self.project_root_requested = None
        self.global_tool_requested = None
        self.global_tool_drop_requested = None
        self.global_tool_buttons: dict[str, QtWidgets.QPushButton] = {}
        self.global_tool_actions: dict[str, QtWidgets.QAction] = {}
        self._sidebar_global_tools_host: Optional[QtWidgets.QWidget] = None
        self._sidebar_global_tools_header_layout: Optional[QtWidgets.QHBoxLayout] = None
        self.global_reload_actions: list[str] = []
        self.global_reload_popup_mode = ""
        self.global_custom_tools: dict[str, dict[str, str]] = {}
        self.top_context_widgets: dict[str, QtWidgets.QWidget] = {}
        self.top_context_box: Optional[QtWidgets.QWidget] = None
        self.top_context_layout: Optional[QtWidgets.QHBoxLayout] = None
        self.overview_stat_badges: dict[str, QtWidgets.QLabel] = {}
        self.overview_stat_captions: dict[str, QtWidgets.QLabel] = {}
        self.overview_completion_labels: list[QtWidgets.QLabel] = []
        self.overview_next_step_labels: list[QtWidgets.QLabel] = []
        self.overview_validation_labels: list[QtWidgets.QLabel] = []
        self._build_ui()
        self._configure_shell_tab_order()
        self.set_sample_chrome_visible(False)
        ui_font = QtGui.QFont()
        if hasattr(ui_font, "setFamilies"):
            ui_font.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
        else:
            ui_font.setFamily("Segoe UI")
        ui_font.setPointSize(10)
        self.setFont(ui_font)
        self.setStyleSheet(self.qss())
        self._apply_shell_metrics()
        self.set_current_page("micro")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_window_max_button()
        key = self.current_page_key()
        if key:
            self._ensure_active_nav_visible(key)
            QtCore.QTimer.singleShot(0, lambda k=key: self._ensure_active_nav_visible(k))

    def closeEvent(self, event) -> None:
        if getattr(self, "_allow_direct_close", False):
            super().closeEvent(event)
            return
        handler = getattr(self, "window_close_requested", None)
        if callable(handler):
            handled = False
            try:
                handled = bool(handler(event))
            except TypeError:
                try:
                    handled = bool(handler())
                except Exception:
                    handled = False
            except Exception:
                handled = False
            if handled:
                return
        super().closeEvent(event)

    def set_window_close_requested_handler(self, handler) -> None:
        self.window_close_requested = handler

    def request_direct_close(self) -> None:
        self._allow_direct_close = True
        self.close()

    def minimize_to_taskbar(self) -> None:
        try:
            self.setWindowState(self.windowState() | QtCore.Qt.WindowMinimized)
        except Exception:
            pass
        try:
            self.showMinimized()
        except Exception:
            pass

    def snapshot_contract(self) -> dict[str, object]:
        current_widget = self.current_page_widget()
        current_key = self.current_page_key()
        top_context = self.top_context_widgets.get(current_key)
        button_scope = current_widget if current_widget is not None else self
        visible_nav_keys = [key for key in self.nav_items.keys() if key != "overview"]
        nav_keys = ["overview"] + visible_nav_keys
        nav_titles: list[str] = ["账号登录"]
        for _key in visible_nav_keys:
            item = self.nav_items[_key]
            label = getattr(item, "text_label", None)
            nav_titles.append(str(label.text() if label is not None else ""))
        primary_buttons = [
            b
            for b in button_scope.findChildren(QtWidgets.QPushButton)
            if b.property("buttonRole") == "primary"
        ]
        currency_cells = []
        currency_evidence: dict[str, object] = {}
        micro_evidence: dict[str, object] = {}
        free_micro_evidence: dict[str, object] = {}
        if current_widget is not None:
            currency_cells = [
                str(label.text() or "")
                for label in current_widget.findChildren(QtWidgets.QLabel, "currencyCellLabel")
            ]
            if current_key == "currency":
                rows = list(getattr(current_widget, "_exchange_rows", []) or [])
                active_rules = 0
                for row in rows:
                    try:
                        if str(row.get("left_amount").text() or "").strip() and str(row.get("right_amount").text() or "").strip():
                            active_rules += 1
                    except Exception:
                        pass
                tabs = getattr(current_widget, "tabs", None)
                body_scroll = getattr(current_widget, "body_scroll", None)
                currency_evidence = {
                    "breadcrumb": str(getattr(getattr(self, "crumb_label", None), "text", lambda: "")()),
                    "currencyRouteMode": current_widget.property("currencyRouteMode"),
                    "searchRouteMode": current_widget.property("searchRouteMode"),
                    "compareRouteMode": current_widget.property("compareRouteMode"),
                    "rule_slots": len(rows),
                    "active_rules": active_rules,
                    "builtin_currencies": 7,
                    "reference_expanded": bool(getattr(getattr(current_widget, "currency_reference_toggle", None), "isChecked", lambda: False)()),
                    "tab_bar_visible": bool(isinstance(tabs, QtWidgets.QTabWidget) and tabs.tabBar().isVisible()),
                    "horizontal_scroll_visible": bool(isinstance(body_scroll, QtWidgets.QScrollArea) and body_scroll.horizontalScrollBar().isVisible()),
                    "setup_thread_active": getattr(current_widget, "_currency_setup_thread", None) is not None,
                    "consume_thread_active": getattr(current_widget, "_consume_thread", None) is not None,
                }
            if current_key == "micro":
                def _micro_widget(name: str):
                    return current_widget.findChild(QtWidgets.QWidget, name)

                def _micro_rect(name: str) -> list[int]:
                    widget = _micro_widget(name)
                    if widget is None:
                        return [0, 0, 0, 0]
                    point = widget.mapTo(self, QtCore.QPoint(0, 0))
                    return [point.x(), point.y(), widget.width(), widget.height()]

                editor_scroll = _micro_widget("microConfigEditorScroll")
                required_names = (
                    "microConfigListPanel", "microConfigEditorPanel", "microConfigTable",
                    "microConfigForm", "microPrimaryActions", "microToolActions",
                    "microVisibilityActions", "microDeleteButton", "microDeletePatchButton",
                )
                micro_evidence = {
                    "breadcrumb": str(getattr(getattr(self, "crumb_label", None), "text", lambda: "")()),
                    "page_type": type(current_widget).__name__,
                    "page_object": current_widget.objectName(),
                    "rects": {name: _micro_rect(name) for name in required_names},
                    "visible": {
                        name: bool(_micro_widget(name) is not None and _micro_widget(name).isVisible())
                        for name in required_names
                    },
                    "horizontal_scroll_visible": bool(
                        isinstance(editor_scroll, QtWidgets.QScrollArea)
                        and editor_scroll.horizontalScrollBar().isVisible()
                    ),
                    "status_thread_active": getattr(current_widget, "_status_scan_thread", None) is not None,
                    "status_worker_active": getattr(current_widget, "_status_scan_worker", None) is not None,
                    "status_timer_active": bool(getattr(getattr(current_widget, "_status_timer", None), "isActive", lambda: False)()),
                    "item_count": len(getattr(current_widget, "_items", []) or []),
                    "current_id": str(getattr(current_widget, "_current_id", "") or ""),
                    "duplicate_internal_tabs": len(current_widget.findChildren(QtWidgets.QTabWidget)),
                }
            if current_key == "free_micro":
                def _free_micro_widget(name: str):
                    return current_widget.findChild(QtWidgets.QWidget, name)

                def _free_micro_rect(name: str) -> list[int]:
                    widget = _free_micro_widget(name)
                    if widget is None:
                        return [0, 0, 0, 0]
                    point = widget.mapTo(self, QtCore.QPoint(0, 0))
                    return [point.x(), point.y(), widget.width(), widget.height()]

                required_names = (
                    "freeMicroInputPanel", "freeMicroSourceModes", "freeMicroSourceStack",
                    "freeMicroStartButton", "freeMicroStopButton", "freeMicroOutputSection",
                    "freeMicroOutputPanel", "freeMicroCopyButton", "freeMicroClearButton",
                )
                output = _free_micro_widget("freeMicroOutputPanel")
                free_micro_evidence = {
                    "breadcrumb": str(getattr(getattr(self, "crumb_label", None), "text", lambda: "")()),
                    "page_type": type(current_widget).__name__,
                    "page_object": current_widget.objectName(),
                    "source_mode": str(getattr(current_widget, "_source_mode", "") or ""),
                    "rects": {name: _free_micro_rect(name) for name in required_names},
                    "visible": {
                        name: bool(_free_micro_widget(name) is not None and _free_micro_widget(name).isVisible())
                        for name in required_names
                    },
                    "horizontal_scroll_visible": bool(
                        isinstance(output, QtWidgets.QPlainTextEdit)
                        and output.horizontalScrollBar().isVisible()
                    ),
                    "thread_active": getattr(current_widget, "_thread", None) is not None,
                    "worker_active": getattr(current_widget, "_worker", None) is not None,
                    "duplicate_internal_tabs": len(current_widget.findChildren(QtWidgets.QTabWidget)),
                }
        qq_bot_page = self.mounted_pages.get("qq_bot")
        qq_permissions_button = getattr(qq_bot_page, "account_permissions_button", None) if qq_bot_page is not None else None
        qq_bot_tabs = getattr(qq_bot_page, "tabs", None) if qq_bot_page is not None else None
        qq_runtime = getattr(qq_bot_page, "plugin_runtime", None) if qq_bot_page is not None else None
        qq_account_status = getattr(qq_runtime, "account_status", {}) if qq_runtime is not None else {}
        if not isinstance(qq_account_status, dict):
            qq_account_status = {}
        qq_group_ids: list[str] = []
        for item in getattr(qq_runtime, "group_list", []) or []:
            if not isinstance(item, dict):
                continue
            group_id = str(item.get("group_id") or "").strip()
            if group_id:
                qq_group_ids.append(group_id)
        qq_plugin_ids: list[str] = []
        qq_plugin_names: list[str] = []
        qq_plugin_descriptions: list[str] = []
        for plugin in getattr(qq_bot_page, "plugins", []) or []:
            if not isinstance(plugin, dict):
                continue
            plugin_id = str(plugin.get("id") or "").strip()
            plugin_name = str(plugin.get("name") or "").strip()
            plugin_description = str(plugin.get("description") or "").strip()
            if plugin_id:
                qq_plugin_ids.append(plugin_id)
            if plugin_name:
                qq_plugin_names.append(plugin_name)
            if plugin_description:
                qq_plugin_descriptions.append(plugin_description)
        return {
            "window_title": self.windowTitle(),
            "brand_version": str(
                self.brand_version_label.text()
                if self.brand_version_label is not None
                else ""
            ),
            "auth_state": str(getattr(self, "auth_state", "") or ""),
            "auth_user": str(getattr(self, "auth_user", "") or ""),
            "auth_summary": str(getattr(self, "auth_summary", "") or ""),
            "account_center_connected": bool(callable(self.account_requested)),
            "account_logout_connected": bool(callable(self.account_logout_requested)),
            "window_close_connected": bool(callable(getattr(self, "window_close_requested", None))),
            "account_logout_visible": bool(
                self.account_logout_button is not None and not self.account_logout_button.isHidden()
            ),
            "login_nav_visible": bool(
                self.account_panel is not None and not self.account_panel.isHidden()
            ),
            "auth_gate_enabled": bool(getattr(self, "auth_gate_enabled", False)),
            "auth_gate_bypass": bool(getattr(self, "auth_gate_bypass", False)),
            "auth_gate_locked": bool(self._auth_gate_locked()),
            "account_card_title": str(
                self.account_name_label.text()
                if self.account_name_label is not None
                else ""
            ),
            "account_card_subtitle": str(
                self.account_state_label.text()
                if self.account_state_label is not None
                else ""
            ),
            "size": [self.width(), self.height()],
            "shell_geometry": self.shell_geometry_snapshot(),
            "shell_object_names": {
                "window": self.objectName(),
                "sidebar": getattr(self._sidebar_widget, "objectName", lambda: "")(),
                "brand": getattr(self._sidebar_brand, "objectName", lambda: "")(),
                "project_bar": getattr(self._titlebar, "objectName", lambda: "")(),
                "breadcrumb_bar": getattr(self._page_header, "objectName", lambda: "")(),
                "page_content": getattr(self._page_content, "objectName", lambda: "")(),
                "status_bar": getattr(self._statusbar_widget, "objectName", lambda: "")(),
            },
            "frameless_window": bool(int(self.windowFlags()) & int(QtCore.Qt.FramelessWindowHint)),
            "legacy_windows_compat": str(os.environ.get("XIAMI_WINDOWS_LEGACY_COMPAT") or "").strip().lower()
            not in {"", "0", "false", "no", "off"}
            or str(os.environ.get("QT_OPENGL") or "").strip().lower() == "software",
            "qt_opengl": str(os.environ.get("QT_OPENGL") or "default"),
            "maximized": bool(self.isMaximized()),
            "pages": len(self.pages),
            "nav_keys": nav_keys,
            "nav_titles": nav_titles,
            "global_tool_keys": list(self.global_tool_buttons.keys()),
            "global_tool_connected": bool(callable(self.global_tool_requested)),
            "global_tool_drop_connected": bool(callable(self.global_tool_drop_requested)),
            "global_tools_entry": self._focus_probe(self.findChild(QtWidgets.QToolButton, "shellToolsMenuButton")),
            "global_tool_actions": {
                key: {
                    "objectName": action.objectName(),
                    "text": action.text(),
                    "visible": bool(action.isVisible()),
                    "enabled": bool(action.isEnabled()),
                }
                for key, action in sorted(self.global_tool_actions.items())
            },
            "global_tool_drop_entry": {
                "acceptDrops": bool(
                    getattr(self.findChild(QtWidgets.QToolButton, "shellToolsMenuButton"), "acceptDrops", lambda: False)()
                ),
                "assignmentOrder": ["custom1", "custom2"],
            },
            "sidebar_footer_controls": {
                "account": self._focus_probe(self.account_panel),
                "collapse": self._focus_probe(self._sidebar_collapse_button),
            },
            "shell_tab_focus_order": list(getattr(self, "_shell_tab_focus_order", []) or []),
            "global_custom_tools": {
                key: {
                    "title": str((data or {}).get("title") or ""),
                    "kind": str((data or {}).get("kind") or ""),
                    "value": str((data or {}).get("value") or ""),
                }
                for key, data in sorted(self.global_custom_tools.items())
            },
            "global_reload_actions": list(getattr(self, "global_reload_actions", []) or []),
            "global_reload_popup_mode": str(getattr(self, "global_reload_popup_mode", "") or ""),
            "bottom_ad_visible": bool(
                self.bottom_ad_frame is not None and not self.bottom_ad_frame.isHidden()
            ),
            "bottom_ad_link_titles": [
                str(link.get("title") or "") for link in self.bottom_ad_links
            ],
            "bottom_ad_link_count": len(self.bottom_ad_links),
            "mounted_pages": sorted(self.mounted_pages.keys()),
            "mounted_page_types": {
                key: type(widget).__name__
                for key, widget in sorted(self.mounted_pages.items())
            },
            "sample_chrome_visible": {
                "header_actions": bool(getattr(getattr(self, "sample_header_actions", None), "isVisible", lambda: False)()),
                "toolbar": bool(getattr(getattr(self, "sample_toolbar", None), "isVisible", lambda: False)()),
                "detail": bool(getattr(getattr(self, "sample_detail_panel", None), "isVisible", lambda: False)()),
                "log": bool(getattr(getattr(self, "sample_log_panel", None), "isVisible", lambda: False)()),
            },
            "top_context_visible": bool(top_context is not None and top_context.isVisible()),
            "top_context_object": top_context.objectName() if top_context is not None else "",
            "primary_buttons": len(primary_buttons),
            "primary_button_details": [
                {
                    "text": b.text(),
                    "objectName": b.objectName(),
                    "parent": b.parentWidget().objectName() if b.parentWidget() is not None else "",
                }
                for b in primary_buttons
            ],
            "nav_active": self._active_navigation_count(),
            "current_page": current_key,
            "header_title": getattr(getattr(self, "title_label", None), "text", lambda: "")(),
            "current_page_tables": len(current_widget.findChildren(QtWidgets.QTableWidget)) if current_widget is not None else 0,
            "current_page_tabs": len(current_widget.findChildren(QtWidgets.QTabWidget)) if current_widget is not None else 0,
            "current_page_currency_cells": currency_cells,
            "currency_evidence": currency_evidence,
            "micro_evidence": micro_evidence,
            "free_micro_evidence": free_micro_evidence,
            "qq_bot": {
                "mounted": qq_bot_page is not None,
                "account_online": bool(getattr(qq_bot_page, "account_online", False)) if qq_bot_page is not None else False,
                "account": str(qq_account_status.get("account") or ""),
                "current_group": str(getattr(qq_bot_page, "current_group_id", "") or "") if qq_bot_page is not None else "",
                "group_ids": qq_group_ids,
                "plugin_ids": qq_plugin_ids,
                "plugin_names": qq_plugin_names,
                "plugin_descriptions": qq_plugin_descriptions,
                "last_error": str(getattr(qq_runtime, "last_error", "") or "") if qq_runtime is not None else "",
                "embedded_root": str(getattr(qq_runtime, "embedded_root", "") or "") if qq_runtime is not None else "",
                "plugin_root": str(getattr(qq_runtime, "plugin_root", "") or "") if qq_runtime is not None else "",
                "permissions_button_visible": bool(
                    qq_permissions_button is not None and not qq_permissions_button.isHidden()
                ),
                "permissions_button_enabled": bool(
                    qq_permissions_button is not None and qq_permissions_button.isEnabled()
                ),
                "plugin_tab_enabled": bool(
                    isinstance(qq_bot_tabs, QtWidgets.QTabWidget) and qq_bot_tabs.isTabEnabled(1)
                ),
            },
        }

    def _smoke_trigger_click(self, widget: QtWidgets.QWidget, key: str) -> str:
        try:
            self._ensure_active_nav_visible(key)
        except Exception:
            pass
        QtWidgets.QApplication.processEvents()
        try:
            from PySide2 import QtTest  # type: ignore

            QtTest.QTest.mouseClick(
                widget,
                QtCore.Qt.LeftButton,
                QtCore.Qt.NoModifier,
                widget.rect().center(),
            )
            QtWidgets.QApplication.processEvents()
            return "mouse"
        except Exception:
            if key == "overview" and widget is self.account_panel:
                self.set_current_page("overview")
                QtWidgets.QApplication.processEvents()
                return "account-fallback"
            signal = getattr(widget, "clicked", None)
            if signal is None:
                return "missing-signal"
            try:
                signal.emit(key)
                QtWidgets.QApplication.processEvents()
                return "signal"
            except Exception as exc:
                return f"error:{type(exc).__name__}"

    def run_interaction_smoke(self) -> dict[str, object]:
        original_key = self.current_page_key()
        original_account_handler = self.account_requested
        nav_records: list[dict[str, object]] = []
        self.account_requested = lambda: None
        try:
            items: list[tuple[str, QtWidgets.QWidget]] = []
            if self.account_panel is not None:
                items.append(("overview", self.account_panel))
            items.extend((key, item) for key, item in self.nav_items.items() if key != "overview")
            for key, item in items:
                method = self._smoke_trigger_click(item, key)
                current = self.current_page_key()
                active_nav = self._active_navigation_count()
                nav_records.append(
                    {
                        "key": key,
                        "current": current,
                        "ok": current == key,
                        "method": method,
                        "active_nav": active_nav,
                    }
                )
        finally:
            self.account_requested = original_account_handler
            if original_key:
                self.set_current_page(original_key)
                QtWidgets.QApplication.processEvents()
        return {
            "nav": {
                "attempted": len(nav_records),
                "failed": len([r for r in nav_records if not r.get("ok")]),
                "records": nav_records,
            },
            "dock": {
                "attempted": 0,
                "failed": 0,
                "records": [],
            },
        }

    def _active_navigation_count(self) -> int:
        count = len([row for row in self.nav_rows if row.property("panelRole") == "nav-active"])
        if self.current_page_key() == "overview" and self.account_panel is not None and not self.account_panel.isHidden():
            count += 1
        return count

    def current_page_key(self) -> str:
        current = self.stack.currentIndex()
        for key, index in self.pages.items():
            if index == current:
                return key
        return ""

    def current_page_widget(self) -> QtWidgets.QWidget | None:
        key = self.current_page_key()
        return self.page_widgets.get(key)

    def register_page(
        self,
        key: str,
        widget: QtWidgets.QWidget,
        *,
        title: str,
        crumb: str,
        state: str = "● 服务正常",
        state_role: str = "success",
    ) -> int:
        key = str(key or "").strip()
        if not key:
            key = f"page_{len(self.pages) + 1}"
        if key in self.pages:
            old = self.page_widgets.get(key) or self.stack.widget(self.pages[key])
            if old is not None:
                old.hide()
                self.stack.removeWidget(old)
                old.deleteLater()
            if key == "overview":
                self.overview_stat_badges.clear()
                self.overview_stat_captions.clear()
                self.overview_completion_labels = []
                self.overview_next_step_labels = []
                self.overview_validation_labels = []
            self.page_widgets.pop(key, None)
            self._sync_page_indexes()
        index = self.stack.addWidget(widget)
        self.pages[key] = index
        self.page_widgets[key] = widget
        self.page_meta[key] = {
            "title": str(title or key),
            "crumb": str(crumb or title or key),
            "state": str(state or ""),
            "state_role": str(state_role or "muted"),
        }
        self._refresh_overview_metrics()
        return index

    def _sync_page_indexes(self) -> None:
        for page_key, widget in list(self.page_widgets.items()):
            actual = self.stack.indexOf(widget)
            if actual < 0:
                self.pages.pop(page_key, None)
                self.page_widgets.pop(page_key, None)
                continue
            self.pages[page_key] = actual

    def _navigation_settings(self) -> QtCore.QSettings:
        base = str(os.environ.get("XIAMI_TEST_PROFILE_ROOT") or "").strip()
        if not base:
            base = QtCore.QStandardPaths.writableLocation(QtCore.QStandardPaths.AppConfigLocation)
        if not base:
            base = os.path.join(os.path.expanduser("~"), ".xiami-toolbox")
        os.makedirs(base, exist_ok=True)
        return QtCore.QSettings(os.path.join(base, "dark-workbench-navigation.ini"), QtCore.QSettings.IniFormat)

    def _rebuild_sidebar_nav_layout(self) -> None:
        layout = self._sidebar_nav_layout
        if layout is None:
            return
        while layout.count():
            layout.takeAt(0)
        flattened: list[DarkWorkbenchNavItem] = []
        for section_label, rows in self.sidebar_nav_groups:
            base_title = str(section_label.property("sectionBaseTitle") or section_label.text()).strip()
            section_label.setText(f"{base_title}  {len(rows)}")
            layout.addWidget(section_label)
            for row in rows:
                layout.addWidget(row)
                flattened.append(row)
        layout.addStretch(1)
        self.nav_rows = flattened
        self.nav_items = {row.key: row for row in flattened}

    def _restore_sidebar_nav_order(self) -> None:
        try:
            raw = str(self._navigation_settings().value("sidebar/order-v1", "") or "").strip()
            saved = json.loads(raw) if raw else []
        except Exception:
            saved = []
        if not isinstance(saved, list):
            self._rebuild_sidebar_nav_layout()
            return
        by_key = {row.key: row for _, rows in self.sidebar_nav_groups for row in rows}
        assigned = set()
        restored: list[list[DarkWorkbenchNavItem]] = [[] for _ in self.sidebar_nav_groups]
        for group_index, keys in enumerate(saved[: len(restored)]):
            if not isinstance(keys, list):
                continue
            for key in keys:
                normalized = str(key or "").strip()
                row = by_key.get(normalized)
                if row is not None and normalized not in assigned:
                    restored[group_index].append(row)
                    assigned.add(normalized)
        for group_index, (_, rows) in enumerate(self.sidebar_nav_groups):
            for row in rows:
                if row.key not in assigned:
                    restored[group_index].append(row)
                    assigned.add(row.key)
        self.sidebar_nav_groups = [
            (section_label, restored[index])
            for index, (section_label, _rows) in enumerate(self.sidebar_nav_groups)
        ]
        self._rebuild_sidebar_nav_layout()

    def _save_sidebar_nav_order(self) -> None:
        order = [[row.key for row in rows] for _section_label, rows in self.sidebar_nav_groups]
        settings = self._navigation_settings()
        settings.setValue("sidebar/order-v1", json.dumps(order, ensure_ascii=True, separators=(",", ":")))
        settings.sync()

    def _clear_sidebar_nav_hover(self) -> None:
        for row in self.nav_rows:
            if row.property("navDropPosition"):
                row.setProperty("navDropPosition", "")
                row.style().unpolish(row)
                row.style().polish(row)

    def _set_sidebar_nav_hover(self, key: str, position: str) -> None:
        self._clear_sidebar_nav_hover()
        row = self.nav_items.get(str(key or "").strip())
        if row is not None:
            row.setProperty("navDropPosition", str(position or ""))
            row.style().unpolish(row)
            row.style().polish(row)

    def _move_sidebar_nav_item(self, source_key: str, target_key: str, before: bool) -> None:
        source_key = str(source_key or "").strip()
        target_key = str(target_key or "").strip()
        if not source_key or not target_key or source_key == target_key:
            return
        source_row = self.nav_items.get(source_key)
        target_row = self.nav_items.get(target_key)
        if source_row is None or target_row is None:
            return
        source_group = -1
        target_group = -1
        for index, (_label, rows) in enumerate(self.sidebar_nav_groups):
            if source_row in rows:
                source_group = index
            if target_row in rows:
                target_group = index
        if source_group < 0 or target_group < 0:
            return
        self.sidebar_nav_groups[source_group][1].remove(source_row)
        target_rows = self.sidebar_nav_groups[target_group][1]
        target_index = target_rows.index(target_row)
        target_rows.insert(target_index if before else target_index + 1, source_row)
        self._rebuild_sidebar_nav_layout()
        self._save_sidebar_nav_order()
        if self.sidebar_search_edit is not None:
            self._filter_sidebar_nav(self.sidebar_search_edit.text())
        self._configure_shell_tab_order()
        self._ensure_active_nav_visible(self.current_page_key())

    @QtCore.Slot(str)
    def _filter_sidebar_nav(self, text: str) -> None:
        query = str(text or "").strip().lower()
        for section_label, rows in self.sidebar_nav_groups:
            visible_rows = 0
            for row in rows:
                haystack = str(row.property("searchText") or "").lower()
                visible = not query or query in haystack
                row.setProperty("navDragEnabled", not bool(query))
                row.setVisible(visible)
                if visible:
                    visible_rows += 1
            section_label.setVisible(visible_rows > 0)

    @QtCore.Slot(str)
    def set_current_page(self, key: str) -> None:
        key = str(key or "").strip()
        if self._auth_gate_blocks(key):
            self._show_login_required()
            return
        self._set_current_page_unchecked(key)

    def _set_current_page_unchecked(self, key: str) -> None:
        key = str(key or "").strip()
        if key not in self.pages:
            return
        previous_key = self._current_page_key
        self.stack.setCurrentIndex(self.pages[key])
        self._current_page_key = key
        if previous_key != key:
            _write_crash_event("page_changed", "%s->%s" % (previous_key or "none", key))
        meta = self.page_meta.get(key, {})
        if hasattr(self, "crumb_label"):
            self.crumb_label.setText(meta.get("crumb", meta.get("title", key)))
            self.crumb_label.show()
        if hasattr(self, "title_label"):
            self.title_label.setText(meta.get("title", key))
        if self._page_title_row is not None:
            self._page_title_row.setVisible(key not in ("visual_npc", "visual_spawn"))
        if hasattr(self, "state_badge"):
            self.state_badge.clear()
            self.state_badge.hide()
        for nav_key, item in self.nav_items.items():
            item.set_active(nav_key == key)
        self._ensure_active_nav_visible(key)
        QtCore.QTimer.singleShot(0, lambda k=key: self._ensure_active_nav_visible(k))
        QtCore.QTimer.singleShot(50, lambda k=key: self._ensure_active_nav_visible(k))
        for dock_key, item in self.dock_items.items():
            item.set_active(dock_key == key)
        self._sync_top_context(key)

    def set_page_top_context(self, key: str, widget: QtWidgets.QWidget | None) -> None:
        key = str(key or "").strip()
        if not key or self.top_context_layout is None:
            return
        if widget is None:
            old = self.top_context_widgets.pop(key, None)
            if old is not None:
                self.top_context_layout.removeWidget(old)
                old.hide()
            self._sync_top_context(self.current_page_key())
            return
        self._prepare_top_context_widget(widget)
        old = self.top_context_widgets.get(key)
        if old is widget:
            return
        if old is not None:
            self.top_context_layout.removeWidget(old)
            old.hide()
        widget.setParent(self.top_context_box)
        self.top_context_layout.addWidget(widget, 0, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        widget.hide()
        self.top_context_widgets[key] = widget
        self._sync_top_context(self.current_page_key())

    def _prepare_top_context_widget(self, widget: QtWidgets.QWidget) -> None:
        compact_h = 32
        control_h = 28
        widgets = [widget]
        widgets.extend(widget.findChildren(QtWidgets.QWidget))
        for item in widgets:
            item.setProperty("topContextCompact", True)
            layout = item.layout()
            if layout is not None:
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(min(max(layout.spacing(), 0), 4))
            if isinstance(item, (QtWidgets.QLineEdit, QtWidgets.QComboBox, QtWidgets.QPushButton)):
                item_h = 32 if isinstance(item, QtWidgets.QPushButton) and item.property("buttonRole") == "primary" else control_h
                item.setMinimumHeight(item_h)
                item.setMaximumHeight(item_h)
                if isinstance(item, QtWidgets.QPushButton):
                    item.setMinimumWidth(max(item.minimumWidth(), 54))
            elif item is widget or item.objectName().endswith(("Row", "Bar", "Panel")):
                item.setMinimumHeight(compact_h)
                item.setMaximumHeight(compact_h)
            if item is widget:
                item.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)
            style = item.style()
            style.unpolish(item)
            style.polish(item)
            item.update()

    def _sync_top_context(self, key: str) -> None:
        box = getattr(self, "top_context_box", None)
        if box is None:
            return
        active = self.top_context_widgets.get(str(key or "").strip())
        for widget in self.top_context_widgets.values():
            widget.setVisible(widget is active)
        box.setVisible(active is not None)

    def _ensure_active_nav_visible(self, key: str) -> None:
        active_item = self.nav_items.get(str(key or "").strip())
        if active_item is None or self.sidebar_nav_scroll is None:
            return
        if not active_item.isVisible():
            return
        QtWidgets.QApplication.processEvents()
        viewport = self.sidebar_nav_scroll.viewport()
        scroll_bar = self.sidebar_nav_scroll.verticalScrollBar()
        if viewport is None or scroll_bar is None:
            return
        item_top = active_item.mapTo(viewport, QtCore.QPoint(0, 0)).y()
        item_mid = item_top + max(1, active_item.height()) // 2
        target = scroll_bar.value() + item_mid - max(1, viewport.height()) // 2
        target = max(scroll_bar.minimum(), min(scroll_bar.maximum(), target))
        scroll_bar.setValue(target)
        self.sidebar_nav_scroll.ensureWidgetVisible(active_item, 0, 8)

    def mount_page(
        self,
        key: str,
        widget: QtWidgets.QWidget,
        *,
        make_current: bool = True,
        immersive: bool = False,
        keep_primary_parent: str = "",
        title: str = "",
        crumb: str = "",
        state: str = "● 真实页面",
        state_role: str = "success",
    ) -> None:
        key = str(key or "").strip() or f"mounted_{len(self.mounted_pages) + 1}"
        self.register_page(
            key,
            widget,
            title=title or key,
            crumb=crumb or title or key,
            state=state,
            state_role=state_role,
        )
        self.mounted_pages[key] = widget
        self._refresh_overview_metrics()
        self._sync_auth_gate_widgets()
        if immersive:
            self.set_sample_chrome_visible(False)
            self.normalize_mounted_page_actions(widget, keep_parent=keep_primary_parent)
        if make_current:
            self.set_current_page(key)

    def set_sample_chrome_visible(self, visible: bool) -> None:
        for attr in ("sample_header_actions", "sample_toolbar", "sample_detail_panel", "sample_log_panel"):
            widget = getattr(self, attr, None)
            if isinstance(widget, QtWidgets.QWidget):
                widget.setVisible(bool(visible))
        layout = getattr(self, "content_layout", None)
        if isinstance(layout, QtWidgets.QGridLayout):
            layout.setColumnMinimumWidth(1, 330 if visible else 0)
            stack = getattr(self, "stack", None)
            if isinstance(stack, QtWidgets.QStackedWidget):
                layout.addWidget(stack, 2, 0, 1, 1 if visible else 2)

    def normalize_mounted_page_actions(self, widget: QtWidgets.QWidget, *, keep_parent: str = "") -> None:
        primary_buttons = [b for b in widget.findChildren(QtWidgets.QPushButton) if b.property("buttonRole") == "primary"]
        keep_parent = str(keep_parent or "").strip()
        keep_button: QtWidgets.QPushButton | None = None
        if keep_parent:
            for button in primary_buttons:
                parent = button.parentWidget()
                if parent is not None and parent.objectName() == keep_parent:
                    keep_button = button
                    break
        if keep_button is None and primary_buttons:
            keep_button = primary_buttons[0]
        for button in primary_buttons:
            if button is keep_button:
                continue
            button.setProperty("buttonRole", "secondary")
            button.setProperty("darkWorkbenchDemotedPrimary", True)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()

    def _build_ui(self) -> None:
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.setSizeConstraint(QtWidgets.QLayout.SetNoConstraint)
        sidebar = self._build_sidebar()
        self._sidebar_widget = sidebar
        root.addWidget(sidebar, 0)

        right_shell = QtWidgets.QWidget()
        right_shell.setObjectName("darkWorkbenchRightShell")
        right_shell.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Ignored)
        right_layout = QtWidgets.QVBoxLayout(right_shell)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._build_titlebar(), 0)
        workspace = self._build_workspace()
        self._workspace_widget = workspace
        right_layout.addWidget(workspace, 1)
        right_layout.addWidget(self._build_statusbar(), 0)
        root.addWidget(right_shell, 1)

    def _build_titlebar(self) -> QtWidgets.QFrame:
        t = DarkWorkbenchTokens
        bar = dw_panel("titlebar")
        bar.setObjectName("darkWorkbenchProjectBar")
        self._titlebar = bar
        bar.setFixedHeight(t.TITLE_H)
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(8)

        project_box = QtWidgets.QFrame()
        project_box.setObjectName("projectRootBox")
        project_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        project_layout = QtWidgets.QHBoxLayout(project_box)
        project_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.setSpacing(8)
        project_label = QtWidgets.QLabel("项目路径")
        project_label.setObjectName("projectRootLabel")
        project_layout.addWidget(project_label, 0)
        project = dw_input("选择根目录", "project")
        project.setObjectName("projectRootDisplay")
        project.setToolTip("全局工程根目录：点击右侧按钮统一选择，各功能页默认读取这里")
        project.setMinimumWidth(260)
        project.setMaximumWidth(300)
        project_layout.addWidget(project, 1)
        project_btn = dw_button("", "secondary")
        project_btn.setObjectName("projectRootBrowseButton")
        project_btn.setToolTip("选择全局工程根目录")
        project_btn.setIcon(self.style().standardIcon(QtWidgets.QStyle.SP_DirOpenIcon))
        project_btn.setIconSize(QtCore.QSize(16, 16))
        project_btn.setFixedSize(30, 30)
        project_btn.clicked.connect(self._request_project_root)
        project_layout.addWidget(project_btn, 0)
        project_box.setFixedHeight(32)
        self.project_edit = project
        self.project_browse_btn = project_btn
        layout.addWidget(project_box, 1)
        context_box = QtWidgets.QWidget()
        context_box.setObjectName("topContextBox")
        context_box.setFixedHeight(32)
        context_box.setMaximumWidth(620)
        context_box.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        context_layout = QtWidgets.QHBoxLayout(context_box)
        context_layout.setContentsMargins(8, 0, 0, 0)
        context_layout.setSpacing(4)
        self.top_context_box = context_box
        self.top_context_layout = context_layout
        context_box.hide()
        layout.addWidget(context_box, 1)
        layout.addStretch(1)

        self.brand_version_label = dw_label("v--", "muted")
        self.brand_version_label.setObjectName("brandVersionLabel")
        self.brand_version_label.setFixedWidth(96)
        self.brand_version_label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(self.brand_version_label, 0, QtCore.Qt.AlignVCenter)

        update_state = QtWidgets.QLabel("● 已是最新")
        update_state.setObjectName("shellUpdateState")
        update_state.setFixedWidth(132)
        update_state.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(update_state, 0, QtCore.Qt.AlignVCenter)

        separator = QtWidgets.QFrame()
        separator.setObjectName("windowControlSeparator")
        separator.setFrameShape(QtWidgets.QFrame.VLine)
        separator.setFixedWidth(1)
        layout.addWidget(separator)

        for index, (text, tip) in enumerate((("_", "最小化"), ("□", "最大化"), ("×", "关闭"))):
            button = dw_button(text, "icon")
            button.setObjectName(("windowMinimizeButton", "windowMaximizeButton", "windowCloseButton")[index])
            button.setToolTip(tip)
            button.setFixedSize(28, 28)
            if tip == "最小化":
                button.clicked.connect(self.minimize_to_taskbar)
            elif tip == "最大化":
                self._window_max_button = button
                button.clicked.connect(self._toggle_window_maximized)
            elif tip == "关闭":
                button.clicked.connect(self.close)
            layout.addWidget(button)
        return bar

    def _configure_shell_tab_order(self) -> None:
        names = [
            "projectRootBrowseButton",
            "windowMinimizeButton",
            "windowMaximizeButton",
            "windowCloseButton",
            "sidebarSearchField",
        ]
        widgets: list[QtWidgets.QWidget] = []
        for name in names:
            widget = self.findChild(QtWidgets.QWidget, name)
            if widget is not None:
                widgets.append(widget)
        widgets.extend(self.nav_rows)
        if self.account_panel is not None:
            widgets.append(self.account_panel)
        if self._sidebar_collapse_button is not None:
            widgets.append(self._sidebar_collapse_button)
        for first, second in zip(widgets, widgets[1:]):
            QtWidgets.QWidget.setTabOrder(first, second)
        self._shell_tab_focus_order = [widget.objectName() for widget in widgets]

    def _request_global_menu_drop(self, kind: str, payload: str, source: QtWidgets.QWidget) -> None:
        key = "custom1"
        for candidate in ("custom1", "custom2"):
            if not str((self.global_custom_tools.get(candidate) or {}).get("value") or "").strip():
                key = candidate
                break
        self._request_global_tool_drop(key, kind, payload, source)

    def _show_window_help(self) -> None:
        try:
            QtWidgets.QMessageBox.information(self, "帮助", "Dark Workbench：拖动顶部空白区域可移动窗口，双击顶部空白区域可最大化或还原。")
        except Exception:
            pass

    def _sync_window_max_button(self) -> None:
        button = getattr(self, "_window_max_button", None)
        if button is None:
            return
        try:
            button.setText("❐" if self.isMaximized() else "□")
            button.setToolTip("还原" if self.isMaximized() else "最大化")
        except Exception:
            pass

    def _toggle_window_maximized(self) -> None:
        try:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
        except Exception:
            pass
        self._sync_window_max_button()

    def _titlebar_hit_test(self, pos: QtCore.QPoint) -> bool:
        titlebar = getattr(self, "_titlebar", None)
        if titlebar is None:
            return False
        try:
            return bool(titlebar.geometry().contains(pos))
        except Exception:
            return False

    def _titlebar_control_at(self, pos: QtCore.QPoint) -> bool:
        titlebar = getattr(self, "_titlebar", None)
        if titlebar is None:
            return False
        try:
            local_pos = titlebar.mapFrom(self, pos)
            child = titlebar.childAt(local_pos)
            while child is not None:
                if isinstance(child, (QtWidgets.QPushButton, QtWidgets.QLineEdit, QtWidgets.QComboBox)):
                    return True
                if child is titlebar:
                    break
                child = child.parentWidget()
        except Exception:
            return False
        return False

    def mouseDoubleClickEvent(self, event) -> None:
        if event is not None and event.button() == QtCore.Qt.LeftButton and self._titlebar_hit_test(event.pos()) and not self._titlebar_control_at(event.pos()):
            self._toggle_window_maximized()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event) -> None:
        if event is not None and event.button() == QtCore.Qt.LeftButton and self._titlebar_hit_test(event.pos()) and not self._titlebar_control_at(event.pos()):
            self._title_dragging = True
            self._title_drag_start_pos = event.globalPos()
            self._title_drag_start_top_left = self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event is not None and self._title_dragging and (event.buttons() & QtCore.Qt.LeftButton):
            if self.isMaximized():
                self.showNormal()
                self._sync_window_max_button()
                self._title_drag_start_top_left = self.frameGeometry().topLeft()
                self._title_drag_start_pos = event.globalPos()
            delta = event.globalPos() - self._title_drag_start_pos
            self.move(self._title_drag_start_top_left + delta)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._title_dragging = False
        super().mouseReleaseEvent(event)

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event is not None and event.type() == QtCore.QEvent.WindowStateChange:
            self._sync_window_max_button()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "_sidebar_widget"):
            self._apply_shell_metrics()

    def _apply_shell_metrics(self) -> None:
        compact = self.width() < self.SHELL_BREAKPOINT
        mode = "compact" if compact else "wide"
        if self._shell_metrics_applied and mode == self._responsive_mode:
            return
        sidebar_w = 60 if self._sidebar_collapsed else (204 if compact else 224)
        brand_h = 52 if compact else 56
        search_host_h = 52 if compact else 56
        footer_h = 0 if self._sidebar_collapsed else (48 if compact else 52)
        title_h = 52 if compact else 56
        crumb_h = 40 if compact else 42
        status_h = 30 if compact else 32
        content_margin = 12 if compact else 16
        window_button_size = 28

        if self._sidebar_widget is not None:
            self._sidebar_widget.setFixedWidth(sidebar_w)
            self._sidebar_widget.setProperty("sidebarCollapsed", self._sidebar_collapsed)
            self._sidebar_widget.style().unpolish(self._sidebar_widget)
            self._sidebar_widget.style().polish(self._sidebar_widget)
        if self._sidebar_brand is not None:
            self._sidebar_brand.setFixedHeight(brand_h)
        brand_mark = self.findChild(QtWidgets.QLabel, "sidebarBrandMark")
        if brand_mark is not None:
            mark_size = 24 if compact else 28
            brand_mark.setFixedSize(mark_size, mark_size)
        if self._sidebar_search_host is not None:
            self._sidebar_search_host.setFixedHeight(search_host_h)
            search_layout = self._sidebar_search_host.layout()
            if search_layout is not None:
                inset = 10 if compact else 12
                search_layout.setContentsMargins(12, inset, 12, inset)
        if self.sidebar_search_edit is not None:
            self.sidebar_search_edit.setProperty("shellViewport", mode)
            self.sidebar_search_edit.setFixedHeight(32)
            self.sidebar_search_edit.style().unpolish(self.sidebar_search_edit)
            self.sidebar_search_edit.style().polish(self.sidebar_search_edit)
        if self._sidebar_footer is not None:
            self._sidebar_footer.setProperty("shellViewport", mode)
            self._sidebar_footer.setFixedHeight(footer_h)
            self._sidebar_footer.style().unpolish(self._sidebar_footer)
            self._sidebar_footer.style().polish(self._sidebar_footer)
        for section_label, rows in self.sidebar_nav_groups:
            section_label.setFixedHeight(22)
            for row in rows:
                row.setFixedHeight(32)

        if self._titlebar is not None:
            self._titlebar.setFixedHeight(title_h)
            title_layout = self._titlebar.layout()
            if title_layout is not None:
                title_layout.setContentsMargins(12 if compact else 16, 1, 6 if compact else 8, 0)
                title_layout.setSpacing(0)
        if self._page_header is not None:
            self._page_header.setFixedHeight(crumb_h)
            header_layout = self._page_header.layout()
            if header_layout is not None:
                header_layout.setContentsMargins(content_margin, 0, content_margin, 0)
        if self._statusbar_widget is not None:
            self._statusbar_widget.setFixedHeight(status_h)
            status_layout = self._statusbar_widget.layout()
            if status_layout is not None:
                status_layout.setContentsMargins(content_margin, 0, content_margin, 0)
        content_layout = getattr(self, "content_layout", None)
        if content_layout is not None:
            content_layout.setContentsMargins(content_margin, 12, content_margin, 12)
            content_layout.setHorizontalSpacing(12)
            content_layout.setVerticalSpacing(6 if compact else 8)

        project = self.findChild(QtWidgets.QWidget, "projectRootDisplay")
        if project is not None:
            project.setFixedWidth(330 if compact else 300)
        project_label = self.findChild(QtWidgets.QLabel, "projectRootLabel")
        if project_label is not None:
            project_label.setFixedWidth(56 if compact else 64)
        project_box = self.findChild(QtWidgets.QFrame, "projectRootBox")
        if project_box is not None:
            project_box.setFixedWidth(430 if compact else 412)
            project_layout = project_box.layout()
            if project_layout is not None:
                project_layout.setSpacing(6 if compact else 8)
        top_context_box = getattr(self, "top_context_box", None)
        if top_context_box is not None:
            top_context_box.setMinimumWidth(96 if compact else 0)
            top_context_box.setMaximumWidth(160 if compact else 620)
        if self.brand_version_label is not None:
            self.brand_version_label.setFixedWidth(64 if compact else 96)
        update_state = self.findChild(QtWidgets.QLabel, "shellUpdateState")
        if update_state is not None:
            update_state.setFixedWidth(72 if compact else 132)
            update_state.setText("● 最新" if compact else "● 已是最新")
        for name in ("windowMinimizeButton", "windowMaximizeButton", "windowCloseButton"):
            button = self.findChild(QtWidgets.QPushButton, name)
            if button is not None:
                button.setFixedSize(window_button_size, window_button_size)
        self._responsive_mode = mode
        self._shell_metrics_applied = True
        self.setProperty("shellResponsiveMode", mode)
        self.setProperty("sidebarCollapsed", self._sidebar_collapsed)

    def _shell_widget_rect(self, widget: Optional[QtWidgets.QWidget]) -> dict[str, int]:
        if widget is None:
            return {"x": 0, "y": 0, "w": 0, "h": 0}
        point = widget.mapTo(self, QtCore.QPoint(0, 0))
        return {"x": point.x(), "y": point.y(), "w": widget.width(), "h": widget.height()}

    def _activate_snapshot_layouts(self) -> None:
        self.ensurePolished()
        widgets = [
            self,
            self._sidebar_widget,
            self.findChild(QtWidgets.QWidget, "darkWorkbenchRightShell"),
            self._workspace_widget,
            self._page_content,
            self._titlebar,
            self._page_header,
            self._statusbar_widget,
        ]
        for _pass in range(2):
            for widget in widgets:
                if widget is None:
                    continue
                layout = widget.layout()
                if layout is None:
                    continue
                layout.invalidate()
                layout.setGeometry(widget.rect())
                layout.activate()

    def shell_geometry_snapshot(self) -> dict[str, object]:
        self._activate_snapshot_layouts()
        QtWidgets.QApplication.processEvents()
        nav_viewport = self.sidebar_nav_scroll.viewport() if self.sidebar_nav_scroll is not None else None
        complete_rows = True
        row_intersections: list[dict[str, object]] = []
        if nav_viewport is not None:
            viewport_rect = nav_viewport.rect()
            for row in self.nav_rows:
                if not row.isVisible():
                    continue
                top_left = row.mapTo(nav_viewport, QtCore.QPoint(0, 0))
                row_rect = QtCore.QRect(top_left, row.size())
                intersection = row_rect.intersected(viewport_rect)
                row_intersections.append(
                    {
                        "key": row.key,
                        "intersectionHeight": intersection.height() if not intersection.isEmpty() else 0,
                        "rowHeight": row.height(),
                        "complete": bool(intersection.isEmpty() or intersection.height() == row.height()),
                    }
                )
                if not intersection.isEmpty() and intersection.height() != row.height():
                    complete_rows = False
                    break
        rects = {
            "sidebar": self._shell_widget_rect(self._sidebar_widget),
            "sidebar_brand": self._shell_widget_rect(self._sidebar_brand),
            "sidebar_search": self._shell_widget_rect(self.sidebar_search_edit),
            "sidebar_navigation": self._shell_widget_rect(self.sidebar_nav_scroll),
            "sidebar_footer": self._shell_widget_rect(self._sidebar_footer),
            "project_bar": self._shell_widget_rect(self._titlebar),
            "breadcrumb_bar": self._shell_widget_rect(self._page_header),
            "page_content": self._shell_widget_rect(self._page_content),
            "status_bar": self._shell_widget_rect(self._statusbar_widget),
            "page_title": self._shell_widget_rect(self._page_title_row),
        }
        compact = self.width() < self.SHELL_BREAKPOINT
        side_w = 204 if compact else 224
        title_h = 52 if compact else 56
        crumb_h = 40 if compact else 42
        status_h = 30 if compact else 32
        brand_h = 52 if compact else 56
        search_host_h = 52 if compact else 56
        footer_h = 0 if self._sidebar_collapsed else (48 if compact else 52)
        content_margin = 12 if compact else 16
        locked = {
            "sidebar": {"x": 0, "y": 0, "w": side_w, "h": self.height()},
            "sidebar_brand": {"x": 0, "y": 0, "w": side_w, "h": brand_h},
            "sidebar_search": {"x": 12, "y": brand_h + (10 if compact else 12), "w": side_w - 24, "h": 32},
            "sidebar_navigation": {"x": 0, "y": brand_h + search_host_h, "w": side_w, "h": self.height() - brand_h - search_host_h - footer_h},
            "sidebar_footer": {"x": 0, "y": self.height() - footer_h, "w": side_w, "h": footer_h},
            "project_bar": {"x": side_w, "y": 0, "w": self.width() - side_w, "h": title_h},
            "breadcrumb_bar": {"x": side_w, "y": title_h, "w": self.width() - side_w, "h": crumb_h},
            "page_content": {"x": side_w, "y": title_h + crumb_h, "w": self.width() - side_w, "h": self.height() - title_h - crumb_h - status_h},
            "status_bar": {"x": side_w, "y": self.height() - status_h, "w": self.width() - side_w, "h": status_h},
            "page_title": {"x": side_w + content_margin, "y": title_h + crumb_h + 12, "w": self.width() - side_w - content_margin * 2, "h": 30},
        }
        fallback_used = bool(
            not self.isVisible()
            and (
                rects["sidebar"]["w"] != side_w
                or rects["sidebar"]["h"] != self.height()
                or rects["project_bar"]["x"] != side_w
                or rects["page_content"]["w"] != self.width() - side_w
            )
        )
        if fallback_used:
            rects = locked
            complete_rows = True
            row_intersections = []
        content_rect = rects["page_content"]
        content_inner = {
            "x": content_rect["x"] + content_margin,
            "y": content_rect["y"] + 12,
            "w": max(0, content_rect["w"] - content_margin * 2),
            "h": max(0, content_rect["h"] - 24),
        }
        return {
            "mode": self._responsive_mode,
            "viewport": {"x": 0, "y": 0, "w": self.width(), "h": self.height()},
            "sidebar": rects["sidebar"],
            "sidebar_brand": rects["sidebar_brand"],
            "sidebar_search": rects["sidebar_search"],
            "sidebar_navigation": rects["sidebar_navigation"],
            "sidebar_footer": rects["sidebar_footer"],
            "project_bar": rects["project_bar"],
            "breadcrumb_bar": rects["breadcrumb_bar"],
            "page_content": rects["page_content"],
            "content_inner": content_inner,
            "status_bar": rects["status_bar"],
            "page_title": rects["page_title"],
            "brand_asset": self.BRAND_ASSET_RELATIVE.replace(os.sep, "/"),
            "brand_asset_sha256": self.BRAND_ASSET_SHA256,
            "ui_font_families": list(self.font().families()) if hasattr(self.font(), "families") else [self.font().family()],
            "navigation_rows_complete": complete_rows,
            "navigation_row_intersections": row_intersections,
            "pre_show_fallback_used": fallback_used,
        }

    @staticmethod
    def _focus_probe(widget: Optional[QtWidgets.QWidget]) -> dict[str, object]:
        if widget is None:
            return {"objectName": "", "visible": False, "enabled": False, "focusPolicy": 0, "tabFocusEligible": False}
        policy = int(widget.focusPolicy())
        logically_visible = not widget.isHidden()
        return {
            "objectName": widget.objectName(),
            "visible": bool(logically_visible),
            "enabled": bool(widget.isEnabled()),
            "focusPolicy": policy,
            "tabFocusEligible": bool(logically_visible and widget.isEnabled() and policy != int(QtCore.Qt.NoFocus)),
            "accessibleName": str(widget.accessibleName() or ""),
        }

    def eventFilter(self, obj, event) -> bool:
        if obj is getattr(self, "account_panel", None):
            if self._sidebar_collapsed:
                return False
            if event is not None and event.type() == QtCore.QEvent.MouseButtonRelease:
                try:
                    if event.button() == QtCore.Qt.LeftButton:
                        self.set_current_page("overview")
                        self._request_account_center()
                        return True
                except Exception:
                    pass
            if event is not None and event.type() == QtCore.QEvent.KeyPress:
                try:
                    if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Space):
                        self.set_current_page("overview")
                        self._request_account_center()
                        return True
                except Exception:
                    pass
        return super().eventFilter(obj, event)

    def set_project_root_requested_handler(self, handler) -> None:
        self.project_root_requested = handler

    def set_account_requested_handler(self, handler) -> None:
        self.account_requested = handler

    def set_account_logout_requested_handler(self, handler) -> None:
        self.account_logout_requested = handler

    def set_sidebar_collapse_requested_handler(self, handler) -> None:
        self.sidebar_collapse_requested = handler

    def _request_sidebar_collapse(self) -> None:
        self.setProperty("sidebarCollapseRequested", True)
        handler = getattr(self, "sidebar_collapse_requested", None)
        if callable(handler):
            handler()
            return
        self.set_sidebar_collapsed(not self._sidebar_collapsed)

    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        collapsed = bool(collapsed)
        if collapsed == self._sidebar_collapsed and self._shell_metrics_applied:
            return
        self._sidebar_collapsed = collapsed

        brand_name = self.findChild(QtWidgets.QLabel, "sidebarBrandName")
        if brand_name is not None:
            brand_name.setVisible(not collapsed)
        if self._sidebar_search_host is not None:
            self._sidebar_search_host.setVisible(not collapsed)
        if self._sidebar_global_tools_host is not None:
            self._sidebar_global_tools_host.setVisible(not collapsed)

        for section_label, rows in self.sidebar_nav_groups:
            section_label.setVisible(not collapsed)
            for row in rows:
                if row.text_label is not None:
                    row.text_label.setVisible(not collapsed)

        if not collapsed and self.sidebar_search_edit is not None:
            self._filter_sidebar_nav(self.sidebar_search_edit.text())

        account_text = self.findChild(QtWidgets.QWidget, "sidebarAccountText")
        if account_text is not None:
            account_text.setVisible(not collapsed)
        if self.account_avatar_label is not None:
            self.account_avatar_label.setVisible(not collapsed)
        if self._sidebar_footer is not None:
            self._sidebar_footer.setVisible(not collapsed)
            footer_layout = self._sidebar_footer.layout()
            if footer_layout is not None:
                if collapsed:
                    footer_layout.setContentsMargins(15, 2, 15, 2)
                else:
                    footer_layout.setContentsMargins(10, 5, 8, 5)
            self._sidebar_footer.setCursor(QtCore.Qt.ArrowCursor if collapsed else QtCore.Qt.PointingHandCursor)
            self._sidebar_footer.setFocusPolicy(QtCore.Qt.NoFocus if collapsed else QtCore.Qt.StrongFocus)
            if collapsed:
                self._sidebar_footer.setToolTip("使用展开侧栏按钮查看账号状态")
                self._sidebar_footer.setAccessibleName("侧栏已收起")
                self._sidebar_footer.setAccessibleDescription("")
            else:
                title = self.account_name_label.toolTip() if self.account_name_label is not None else ""
                subtitle = self.account_state_label.toolTip() if self.account_state_label is not None else ""
                account_detail = " · ".join(part for part in (title, subtitle) if part)
                self._sidebar_footer.setToolTip("打开账号登录" + ("\n" + account_detail if account_detail else ""))
                self._sidebar_footer.setAccessibleName("账号登录")
                self._sidebar_footer.setAccessibleDescription(account_detail)

        if self._sidebar_collapse_button is not None:
            action = "展开侧栏" if collapsed else "收起侧栏"
            self._sidebar_collapse_button.setText(">" if collapsed else "<")
            self._sidebar_collapse_button.setToolTip(action)
            self._sidebar_collapse_button.setAccessibleName(action)
            self._sidebar_collapse_button.setProperty("sidebarCollapsed", collapsed)
            self._sidebar_collapse_button.style().unpolish(self._sidebar_collapse_button)
            self._sidebar_collapse_button.style().polish(self._sidebar_collapse_button)

        self._shell_metrics_applied = False
        self._apply_shell_metrics()
        if self._workspace_widget is not None:
            self._workspace_widget.updateGeometry()
        self.updateGeometry()

    def set_auth_state(self, state: dict | None = None) -> None:
        data = state if isinstance(state, dict) else {}
        auth_state = str(data.get("state") or "logged_out").strip() or "logged_out"
        became_logged_in = auth_state == "logged_in" and str(getattr(self, "auth_state", "")) != "logged_in"
        title = str(data.get("title") or "").strip()
        subtitle = str(data.get("subtitle") or "").strip()
        avatar = str(data.get("avatar") or "").strip()
        user = str(data.get("user") or "").strip()

        if not title:
            title = "未登录" if auth_state != "logged_in" else (user or "已登录")
        if not subtitle:
            subtitle = "点击登录" if auth_state != "logged_in" else "授权状态已同步"
        if not avatar:
            avatar = "?" if auth_state != "logged_in" else (title[:1].upper() if title else "A")

        self.auth_state = auth_state
        self.auth_user = user
        self.auth_summary = subtitle
        display_subtitle = subtitle
        if auth_state == "logged_in" and "剩余" in display_subtitle:
            display_subtitle = "剩余" + display_subtitle.split("剩余", 1)[1].strip().replace(" ", "")
        if self.account_avatar_label is not None:
            self.account_avatar_label.setText(avatar[:2])
        if self.account_name_label is not None:
            name_text = title if title else ("账号登录" if auth_state != "logged_in" else "已登录")
            self.account_name_label.setText(name_text)
            self.account_name_label.setToolTip(title)
        if self.account_state_label is not None:
            state_prefix = "已登录" if auth_state == "logged_in" else "未登录"
            state_text = f"{state_prefix} · {display_subtitle}" if display_subtitle else state_prefix
            display_state = self.account_state_label.fontMetrics().elidedText(state_text, QtCore.Qt.ElideRight, 118)
            self.account_state_label.setText(display_state)
            self.account_state_label.setToolTip(subtitle)
        if self.account_logout_button is not None:
            logged_in = auth_state == "logged_in"
            self.account_logout_button.setVisible(logged_in)
            self.account_logout_button.setEnabled(logged_in)
        if self.account_panel is not None:
            self.account_panel.setProperty("authState", auth_state)
            detail_parts = [part for part in (title, subtitle) if part]
            account_detail = " · ".join(detail_parts)
            self.account_panel.setToolTip("打开账号登录" + ("\n" + account_detail if account_detail else ""))
            self.account_panel.setAccessibleName("账号登录")
            self.account_panel.setAccessibleDescription(account_detail)
            self.account_panel.style().unpolish(self.account_panel)
            self.account_panel.style().polish(self.account_panel)
            self.account_panel.update()
        self._sync_login_page_visibility()
        self._sync_auth_gate_widgets()
        if became_logged_in:
            next_key = self._first_unlocked_page_key()
            if next_key and next_key != "overview":
                QtCore.QTimer.singleShot(0, lambda key=next_key: self._set_current_page_unchecked(key))

    def set_auth_gate_enabled(self, enabled: bool, bypass: bool = False) -> None:
        self.auth_gate_enabled = bool(enabled)
        self.auth_gate_bypass = bool(bypass)
        self._sync_auth_gate_widgets()

    def _auth_gate_locked(self) -> bool:
        return bool(getattr(self, "auth_gate_enabled", False)) and str(getattr(self, "auth_state", "")) != "logged_in"

    def _auth_gate_blocks(self, key: str = "") -> bool:
        if bool(getattr(self, "auth_gate_bypass", False)):
            return False
        if not self._auth_gate_locked():
            return False
        return str(key or "").strip() != "overview"

    def _show_login_required(self) -> None:
        if "overview" in self.pages:
            self._sync_login_page_visibility(force_visible=True)
            self._set_current_page_unchecked("overview")
            return
        self._request_account_center()

    def _first_unlocked_page_key(self) -> str:
        for row in self.nav_rows:
            key = str(getattr(row, "key", "") or "").strip()
            if key and key != "overview" and key in self.pages:
                return key
        for key in (
            "real_basic",
            "micro",
            "map_settings",
            "search",
            "db",
            "currency",
            "drop",
            "spawn",
            "store",
            "recycle",
            "var_query",
            "script",
            "item",
            "cdk",
            "member",
            "qq_bot",
            "website",
        ):
            if key in self.pages:
                return key
        for key in self.pages.keys():
            if key != "overview":
                return key
        return "overview"

    def _sync_login_page_visibility(self, force_visible: bool = False) -> None:
        item = self.nav_items.get("overview")
        logged_in = str(getattr(self, "auth_state", "") or "") == "logged_in"
        visible = bool(force_visible or not logged_in)
        if item is not None:
            try:
                item.setVisible(visible)
            except Exception:
                pass
        if logged_in and str(getattr(self, "_current_page_key", "") or "") == "overview":
            next_key = self._first_unlocked_page_key()
            if next_key and next_key != "overview":
                QtCore.QTimer.singleShot(0, lambda key=next_key: self._set_current_page_unchecked(key))

    def _sync_auth_gate_widgets(self) -> None:
        locked = self._auth_gate_locked() and not bool(getattr(self, "auth_gate_bypass", False))
        for key, item in list(self.nav_items.items()):
            allow = (not locked) or key == "overview"
            try:
                if item.property("authOriginalToolTip") is None:
                    item.setProperty("authOriginalToolTip", item.toolTip())
                item.setEnabled(allow)
                item.setCursor(QtCore.Qt.PointingHandCursor if allow else QtCore.Qt.ForbiddenCursor)
                item.setToolTip(str(item.property("authOriginalToolTip") or "") if allow else "请先登录后使用该功能")
            except Exception:
                pass
        for item in list(self.dock_items.values()):
            try:
                if item.property("authOriginalToolTip") is None:
                    item.setProperty("authOriginalToolTip", item.toolTip())
                item.setEnabled(not locked)
                item.setCursor(QtCore.Qt.PointingHandCursor if not locked else QtCore.Qt.ForbiddenCursor)
                item.setToolTip(str(item.property("authOriginalToolTip") or "") if not locked else "请先登录后使用该功能")
            except Exception:
                pass
        for button in list(self.global_tool_buttons.values()):
            try:
                if button.property("authOriginalToolTip") is None:
                    button.setProperty("authOriginalToolTip", button.toolTip())
                button.setEnabled(not locked)
                button.setToolTip(str(button.property("authOriginalToolTip") or "") if not locked else "请先登录后使用该功能")
            except Exception:
                pass
        for widget in (self.project_browse_btn, self.sidebar_search_edit):
            try:
                if widget is not None:
                    widget.setEnabled(not locked)
            except Exception:
                pass
        if locked and str(getattr(self, "_current_page_key", "") or "") not in ("", "overview"):
            self._set_current_page_unchecked("overview")

    def set_app_version(self, version: str) -> None:
        text = str(version or "").strip()
        if text and not text.lower().startswith("v"):
            text = f"v{text}"
        self.app_version_text = text
        if self.brand_version_label is not None:
            self.brand_version_label.setText(text or "v--")
            self.brand_version_label.setToolTip(f"工具箱版本 {text}" if text else "工具箱版本")

    def set_global_tool_requested_handler(self, handler) -> None:
        self.global_tool_requested = handler

    def set_global_tool_drop_requested_handler(self, handler) -> None:
        self.global_tool_drop_requested = handler

    def set_global_custom_tools(self, tools: dict | None = None) -> None:
        data = tools if isinstance(tools, dict) else {}
        self.global_custom_tools = {}
        for key in ("custom1", "custom2"):
            item = data.get(key) if isinstance(data.get(key), dict) else {}
            title = str(item.get("title") or "").strip() or key.replace("custom", "快捷")
            kind = str(item.get("kind") or "").strip()
            value = str(item.get("value") or "").strip()
            button = self.global_tool_buttons.get(key)
            if button is None:
                continue
            display = title
            if len(display) > 5:
                display = display[:4] + "…"
            button.setText(display)
            button.setProperty("globalToolConfigured", bool(value))
            if value:
                tip_kind = {"file": "文件", "folder": "目录", "url": "URL", "text": "文本"}.get(kind, "目标")
                button.setToolTip(f"{tip_kind}：{title}\n{value}\n拖入新目标可替换。")
            else:
                button.setToolTip("拖入文件、目录、路径、URL 或文本，点击快速打开")
            button.style().unpolish(button)
            button.style().polish(button)
            action = self.global_tool_actions.get(key)
            if action is not None:
                action.setText(title)
                action.setToolTip(button.toolTip())
            self.global_custom_tools[key] = {"title": title, "kind": kind, "value": value}

    def set_friend_link_requested_handler(self, handler) -> None:
        self.friend_link_requested = handler

    def set_bottom_friend_links(self, links: list[dict] | None = None) -> None:
        normal: list[dict[str, object]] = []
        if isinstance(links, list):
            for raw in links[:4]:
                if not isinstance(raw, dict):
                    continue
                title = str(raw.get("title") or "").strip()
                url = str(raw.get("url") or "").strip()
                if not title and not url:
                    continue
                link: dict[str, object] = {"title": title or "广告位", "url": url}
                for key in ("color_mode", "color", "scroll_interval_ms", "font_family", "font_size"):
                    if key in raw:
                        link[key] = raw.get(key)
                normal.append(link)
        self.bottom_ad_links = normal
        self._refresh_bottom_friend_links()

    def set_bottom_friend_links_style(self, style: dict | None = None) -> None:
        self.bottom_ad_style = dict(style) if isinstance(style, dict) else {}
        self._refresh_bottom_friend_links()

    def _refresh_bottom_friend_links(self) -> None:
        buttons = list(getattr(self, "bottom_ad_buttons", []) or [])
        links = list(getattr(self, "bottom_ad_links", []) or [])
        hint = getattr(self, "bottom_ad_hint_label", None)
        if hint is not None:
            hint.setText("暂无友情链接" if not links else "点击打开友情链接")
            hint.setVisible(not links)
        for index, button in enumerate(buttons):
            link = links[index] if index < len(links) else None
            if not link:
                button.hide()
                button.setText("")
                button.setToolTip("")
                button.setProperty("friendLinkUrl", "")
                button.setStyleSheet("")
                continue
            title = str(link.get("title") or "").strip() or "广告位"
            url = str(link.get("url") or "").strip()
            button.setText(title)
            button.setToolTip(url or "该广告位暂未投放")
            button.setProperty("friendLinkUrl", url)
            self._apply_bottom_friend_link_style(button, link, index)
            button.show()

    @staticmethod
    def _bottom_friend_link_color(value: object) -> str:
        text = str(value or "").strip()
        if len(text) == 7 and text.startswith("#"):
            if all(ch in "0123456789abcdefABCDEF" for ch in text[1:]):
                return text
        return ""

    @staticmethod
    def _bottom_friend_link_int(value: object, default: int, minimum: int, maximum: int) -> int:
        try:
            return max(minimum, min(maximum, int(value)))
        except Exception:
            return default

    @staticmethod
    def _bottom_friend_link_qss_string(value: object) -> str:
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    def _bottom_friend_link_effective_style(self, link: dict, index: int) -> dict[str, object]:
        base = getattr(self, "bottom_ad_style", {}) or {}
        mode = str(link.get("color_mode") or "").strip().lower()
        if mode not in {"default", "solid", "rainbow"}:
            mode = str(base.get("color_mode") or "default").strip().lower()
        if mode not in {"default", "solid", "rainbow"}:
            mode = "default"

        color = self._bottom_friend_link_color(link.get("color"))
        if not color:
            color = self._bottom_friend_link_color(base.get("color"))
        if mode == "rainbow":
            palette = ("#DC2626", "#D97706", "#059669", "#0284C7", "#7C3AED", "#DB2777")
            color = palette[index % len(palette)]
        elif mode == "solid" and not color:
            color = DarkWorkbenchTokens.BRAND

        font_family = str(link.get("font_family") or base.get("font_family") or "").strip()
        font_size = self._bottom_friend_link_int(
            link.get("font_size", base.get("font_size", 0)),
            0,
            8,
            36,
        )
        return {
            "mode": mode,
            "color": color if mode in {"solid", "rainbow"} else "",
            "font_family": font_family[:64],
            "font_size": font_size,
        }

    def _apply_bottom_friend_link_style(self, button: QtWidgets.QPushButton, link: dict, index: int) -> None:
        style = self._bottom_friend_link_effective_style(link, index)
        color = str(style.get("color") or "")
        font_family = str(style.get("font_family") or "")
        font_size = int(style.get("font_size") or 0)
        if not color and not font_family and not font_size:
            button.setStyleSheet("")
            return

        t = DarkWorkbenchTokens
        text_color = color or t.TEXT
        border_color = color or t.LINE
        hover_color = color or "#92400E"
        font_family_rule = ""
        if font_family:
            font_family_rule = f'font-family: "{self._bottom_friend_link_qss_string(font_family)}";'
        font_size_rule = f"font-size: {font_size}px;" if font_size else ""
        button.setStyleSheet(
            f"""
QPushButton {{
    min-height: 22px;
    max-height: 22px;
    padding: 0 14px;
    border-radius: 10px;
    border: 1px solid {border_color};
    background: {t.PANEL};
    color: {text_color};
    font-weight: 800;
    {font_family_rule}
    {font_size_rule}
}}
QPushButton:hover {{
    border-color: {border_color};
    background: #FFF7ED;
    color: {hover_color};
}}
"""
        )
        frame = getattr(self, "bottom_ad_frame", None)
        if frame is not None:
            frame.update()

    def _request_bottom_friend_link(self, button: QtWidgets.QPushButton) -> None:
        url = str(button.property("friendLinkUrl") or "").strip()
        handler = getattr(self, "friend_link_requested", None)
        if callable(handler):
            handler(url)
            return
        if url:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl(url))

    def _request_global_tool(self, key: str, source: QtWidgets.QWidget | None = None) -> None:
        if self._auth_gate_blocks("global-tool"):
            self._show_login_required()
            return
        handler = getattr(self, "global_tool_requested", None)
        if callable(handler):
            try:
                handler(str(key or "").strip(), source)
                return
            except TypeError:
                handler(str(key or "").strip())
                return
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "全局工具", f"执行失败：{exc}")
            return
        QtWidgets.QMessageBox.information(self, "全局工具", "该全局工具尚未接入。")

    def _request_global_tool_drop(
        self,
        key: str,
        kind: str,
        payload: str,
        source: QtWidgets.QWidget | None = None,
    ) -> None:
        if self._auth_gate_blocks("global-tool"):
            self._show_login_required()
            return
        handler = getattr(self, "global_tool_drop_requested", None)
        if callable(handler):
            try:
                handler(str(key or "").strip(), str(kind or "").strip(), str(payload or "").strip(), source)
                return
            except TypeError:
                handler(str(key or "").strip(), str(kind or "").strip(), str(payload or "").strip())
                return
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "快捷工具", f"保存失败：{exc}")
                return
        QtWidgets.QMessageBox.information(self, "快捷工具", "快捷工具保存尚未接入。")

    def _request_account_center(self) -> None:
        handler = getattr(self, "account_requested", None)
        if callable(handler):
            try:
                handler()
                return
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "账号中心", f"打开失败：{exc}")
            return
        QtWidgets.QMessageBox.information(self, "账号中心", "账号中心尚未接入。")

    def _request_account_logout(self) -> None:
        handler = getattr(self, "account_logout_requested", None)
        if callable(handler):
            try:
                handler()
                return
            except Exception as exc:
                QtWidgets.QMessageBox.critical(self, "退出登录", f"退出失败：{exc}")
                return
        self.set_auth_state({"state": "logged_out"})
        self._sync_login_page_visibility(force_visible=True)
        if "overview" in self.pages:
            self._set_current_page_unchecked("overview")

    def _request_project_root(self) -> None:
        if self._auth_gate_blocks("project-root"):
            self._show_login_required()
            return
        handler = getattr(self, "project_root_requested", None)
        if callable(handler):
            try:
                handler()
            except Exception:
                pass

    def set_project_root(self, root: str) -> None:
        text = str(root or "").strip()
        display = "选择根目录"
        if text:
            leaf = text.rstrip("\\/").replace("/", "\\").split("\\")[-1]
            if leaf.lower().startswith(("demo_", "smoke_")):
                display = "选择根目录"
            else:
                display = text
        project = getattr(self, "project_edit", None)
        if isinstance(project, QtWidgets.QLabel):
            project.setText(display)
            project.setToolTip(f"全局工程根目录：{text or '未选择'}")

    def _build_workspace(self) -> QtWidgets.QFrame:
        workspace = dw_panel("workspace")
        workspace.setObjectName("darkWorkbenchWorkspace")
        workspace.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Ignored)
        layout = QtWidgets.QVBoxLayout(workspace)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_page_header())
        layout.addWidget(self._build_content(), 1)
        return workspace

    def _build_sidebar(self) -> QtWidgets.QFrame:
        side = dw_panel("sidebar")
        side.setObjectName("darkWorkbenchSidebar")
        layout = QtWidgets.QVBoxLayout(side)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        brand = dw_panel("sidebar-brand")
        brand.setObjectName("sidebarBrand")
        brand_layout = QtWidgets.QHBoxLayout(brand)
        brand_layout.setContentsMargins(12, 0, 12, 0)
        brand_layout.setSpacing(8)
        mark = QtWidgets.QLabel()
        mark.setObjectName("sidebarBrandMark")
        mark.setAlignment(QtCore.Qt.AlignCenter)
        mark.setScaledContents(True)
        asset_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), self.BRAND_ASSET_RELATIVE)
        pixmap = QtGui.QPixmap(asset_path)
        if not pixmap.isNull():
            mark.setPixmap(pixmap)
            mark.setProperty("brandAssetPath", asset_path)
            mark.setProperty("brandAssetSha256", self.BRAND_ASSET_SHA256)
        else:
            mark.setText("虾")
            mark.setProperty("brandAssetMissing", True)
        brand_layout.addWidget(mark, 0, QtCore.Qt.AlignVCenter)
        brand_name = dw_label("虾米工具箱", "brand")
        brand_name.setObjectName("sidebarBrandName")
        brand_layout.addWidget(brand_name, 1, QtCore.Qt.AlignVCenter)
        collapse_btn = QtWidgets.QPushButton()
        collapse_btn.setObjectName("sidebarCollapseButton")
        collapse_btn.setText("<")
        collapse_btn.setToolTip("收起侧栏")
        collapse_btn.setAccessibleName("收起侧栏")
        collapse_btn.setFocusPolicy(QtCore.Qt.StrongFocus)
        collapse_btn.setFixedSize(26, 26)
        collapse_btn.clicked.connect(self._request_sidebar_collapse)
        self._sidebar_collapse_button = collapse_btn
        brand_layout.addWidget(collapse_btn, 0, QtCore.Qt.AlignVCenter)
        layout.addWidget(brand, 0)
        self._sidebar_brand = brand

        search_host = QtWidgets.QWidget()
        search_host.setObjectName("sidebarSearchHost")
        search_layout = QtWidgets.QVBoxLayout(search_host)
        search_layout.setContentsMargins(12, 12, 12, 12)
        search_layout.setSpacing(0)

        search_field = QtWidgets.QLineEdit()
        search_field.setObjectName("sidebarSearchField")
        search_field.setPlaceholderText("搜索 功能 / 脚本 / 路径")
        search_field.setClearButtonEnabled(True)
        search_field.textChanged.connect(self._filter_sidebar_nav)
        self.sidebar_search_edit = search_field
        search_layout.addWidget(search_field)
        layout.addWidget(search_host, 0)
        self._sidebar_search_host = search_host

        tool_host = QtWidgets.QWidget(side)
        tool_host.setObjectName("sidebarGlobalToolsHost")
        tool_layout = QtWidgets.QVBoxLayout(tool_host)
        tool_layout.setContentsMargins(12, 0, 12, 10)
        tool_layout.setSpacing(4)
        tool_header = QtWidgets.QWidget(tool_host)
        tool_header.setObjectName("sidebarGlobalToolsHeader")
        tool_header_layout = QtWidgets.QHBoxLayout(tool_header)
        tool_header_layout.setContentsMargins(0, 0, 0, 0)
        tool_header_layout.setSpacing(4)
        tool_title = QtWidgets.QLabel("全局工具  4")
        tool_title.setObjectName("sidebarGlobalToolsTitle")
        tool_header_layout.addWidget(tool_title, 1)
        tool_layout.addWidget(tool_header, 0)
        tool_grid = QtWidgets.QGridLayout()
        tool_grid.setContentsMargins(0, 0, 0, 0)
        tool_grid.setHorizontalSpacing(4)
        tool_grid.setVerticalSpacing(4)
        self._sidebar_global_tools_host = tool_host
        self._sidebar_global_tools_header_layout = tool_header_layout
        tooltips = {
            "重载": "打开旧引擎重载项目菜单",
            "更新": "检查工具箱在线更新",
            "快捷1": "拖入文件、目录、路径、URL 或文本，点击快速打开",
            "快捷2": "拖入文件、目录、路径、URL 或文本，点击快速打开",
        }
        tool_keys = {"重载": "reload", "更新": "update", "快捷1": "custom1", "快捷2": "custom2"}
        for index, text in enumerate(["重载", "更新", "快捷1", "快捷2"]):
            key = tool_keys[text]
            if key.startswith("custom"):
                button = DarkWorkbenchDropButton(text, key)
                button.payloadDropped.connect(
                    lambda drop_key, kind, payload, b=button: self._request_global_tool_drop(drop_key, kind, payload, b)
                )
            else:
                button = dw_button(text, "global-tool")
            button.setObjectName("sidebarGlobalToolButton_" + key)
            button.setProperty("globalToolKey", key)
            button.setProperty("globalToolCustom", key.startswith("custom"))
            button.setToolTip(tooltips.get(text, "工程级全局工具"))
            if key == "reload":
                button.setProperty("globalToolMode", "menu")
            button.clicked.connect(lambda _checked=False, k=key, b=button: self._request_global_tool(k, b))
            button.setMinimumHeight(28)
            button.setMaximumHeight(28)
            button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
            tool_grid.addWidget(button, index // 2, index % 2)
            self.global_tool_buttons[key] = button
        tool_layout.addLayout(tool_grid)
        layout.addWidget(tool_host, 0)

        nav = QtWidgets.QScrollArea()
        nav.setObjectName("sidebarNavScroll")
        nav.setWidgetResizable(True)
        nav.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        nav.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.sidebar_nav_scroll = nav
        nav_content = DarkWorkbenchNavContainer()
        nav_content.setObjectName("sidebarNavContent")
        nav_content.navDropped.connect(self._move_sidebar_nav_item)
        nav_content.navHoverChanged.connect(self._set_sidebar_nav_hover)
        nav_content.navHoverCleared.connect(self._clear_sidebar_nav_hover)
        nav_layout = QtWidgets.QVBoxLayout(nav_content)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)
        self._sidebar_nav_content = nav_content
        self._sidebar_nav_layout = nav_layout

        groups = (
            ("基础工具  6", (("real_basic", "BS", "基础设置", ""), ("micro", "MC", "微端配置", ""), ("free_micro", "FM", "免费微端", ""), ("map_settings", "MP", "地图设置", ""), ("search", "SE", "文本搜索", ""), ("compare", "CP", "文件对比", ""))),
            ("版本数据  12", (("db", "DB", "数据库管理", ""), ("visual_npc", "VN", "可视化NPC", ""), ("visual_spawn", "VS", "可视化刷怪", ""), ("spawn", "SP", "刷怪设置", ""), ("currency", "CY", "货币兑换", ""), ("drop", "DR", "爆率管理", ""), ("store", "ST", "存销设置", ""), ("recycle", "RC", "回收生成", ""), ("var_query", "VQ", "变量查询", ""), ("encoding", "EN", "封挂编码", ""), ("script", "SI", "脚本注入", ""), ("item", "IT", "物品注入", ""))),
            ("运营工具  4", (("cdk", "CK", "CDK 管理", ""), ("member", "MB", "会员系统", ""), ("qq_bot", "QB", "QQ机器人", ""), ("website", "WB", "网站管理", ""))),
        )
        for title, rows in groups:
            base_title = str(title).rsplit("  ", 1)[0]
            section_label = dw_label(title, "section")
            section_label.setProperty("sectionBaseTitle", base_title)
            nav_layout.addWidget(section_label)
            group_items: list[DarkWorkbenchNavItem] = []
            for key, icon, text, badge in rows:
                row = DarkWorkbenchNavItem(key, icon, text, badge, key == "micro")
                row.setObjectName("sidebarNavItem_" + key)
                row.setProperty("searchText", f"{key} {icon} {text} {title}")
                row.setAccessibleName(text)
                row.setProperty("navDragEnabled", True)
                row.clicked.connect(self.set_current_page)
                self.nav_rows.append(row)
                self.nav_items[key] = row
                group_items.append(row)
                nav_layout.addWidget(row)
            self.sidebar_nav_groups.append((section_label, group_items))
        self._restore_sidebar_nav_order()
        nav.setWidget(nav_content)
        layout.addWidget(nav, 1)

        account = dw_panel("account")
        account.setObjectName("sidebarAccountPanel")
        self._sidebar_footer = account
        account.setCursor(QtCore.Qt.PointingHandCursor)
        account.setAccessibleName("账号与授权")
        account.setFocusPolicy(QtCore.Qt.StrongFocus)
        account.installEventFilter(self)
        self.account_panel = account
        account_layout = QtWidgets.QHBoxLayout(account)
        account_layout.setContentsMargins(10, 5, 8, 5)
        account_layout.setSpacing(7)
        avatar = QtWidgets.QLabel("?")
        avatar.setAlignment(QtCore.Qt.AlignCenter)
        dw_apply_role(avatar, "labelRole", "avatar")
        avatar.setFixedSize(28, 28)
        self.account_avatar_label = avatar
        account_layout.addWidget(avatar)
        account_text = QtWidgets.QWidget()
        account_text.setObjectName("sidebarAccountText")
        text_box = QtWidgets.QVBoxLayout(account_text)
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(0)
        self.account_name_label = dw_label("未登录", "strong")
        self.account_name_label.setMinimumWidth(0)
        self.account_name_label.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Fixed)
        self.account_state_label = dw_label("点击登录", "muted")
        self.account_state_label.setMinimumWidth(0)
        self.account_state_label.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        text_box.addWidget(self.account_name_label)
        state_row = QtWidgets.QHBoxLayout()
        state_row.setContentsMargins(0, 0, 0, 0)
        state_row.setSpacing(4)
        state_row.addWidget(self.account_state_label, 1)
        logout_btn = dw_button("退出", "ghost")
        logout_btn.setObjectName("accountLogoutButton")
        logout_btn.setFixedSize(40, 24)
        logout_btn.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        logout_btn.setToolTip("退出账号登录")
        logout_btn.hide()
        logout_btn.clicked.connect(self._request_account_logout)
        self.account_logout_button = logout_btn
        state_row.addWidget(logout_btn, 0)
        text_box.addLayout(state_row)
        account_layout.addWidget(account_text, 1)
        layout.addWidget(account)
        self.set_auth_state({"state": "logged_out"})
        return side

    def _build_page_header(self) -> QtWidgets.QFrame:
        t = DarkWorkbenchTokens
        header = dw_panel("page-header")
        header.setObjectName("darkWorkbenchBreadcrumbBar")
        self._page_header = header
        header.setFixedHeight(t.PAGE_HEAD_H)
        layout = QtWidgets.QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(8)

        self.crumb_label = dw_label("基础工具 / 微端配置", "crumb")
        self.crumb_label.setObjectName("shellBreadcrumbLabel")
        layout.addWidget(self.crumb_label, 1, QtCore.Qt.AlignVCenter)

        self.state_badge = dw_badge("", "success")
        self.state_badge.hide()
        layout.addWidget(self.state_badge, 0, QtCore.Qt.AlignVCenter)

        self.sample_header_actions = QtWidgets.QWidget()
        self.sample_header_actions.hide()
        return header

    def _build_content(self) -> QtWidgets.QWidget:
        content = QtWidgets.QWidget()
        content.setObjectName("darkWorkbenchPageContent")
        content.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Ignored)
        self._page_content = content
        layout = QtWidgets.QGridLayout(content)
        self.content_layout = layout
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setHorizontalSpacing(12)
        layout.setVerticalSpacing(8)
        layout.setColumnStretch(0, 1)
        layout.setColumnMinimumWidth(1, 330)

        title_row = QtWidgets.QWidget()
        title_row.setObjectName("shellPageTitleRow")
        title_row.setFixedHeight(30)
        self._page_title_row = title_row
        title_layout = QtWidgets.QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        self.title_label = dw_label("微端配置工作台", "page-title")
        self.title_label.setObjectName("shellPageTitle")
        title_layout.addWidget(self.title_label, 1, QtCore.Qt.AlignVCenter)
        layout.addWidget(title_row, 0, 0, 1, 2)

        self.sample_toolbar = self._build_toolbar()
        layout.addWidget(self.sample_toolbar, 1, 0, 1, 2)

        self.stack = QtWidgets.QStackedWidget()
        self.register_page("overview", DarkWorkbenchPlaceholderPage("账号登录", "登录后解锁全部功能", accent="warn"), title="账号登录", crumb="基础工具 / 账号登录", state="● 加载中", state_role="warn")
        self.register_page("micro", self._build_micro_page(), title="微端配置工作台", crumb="基础工具 / 微端配置", state="● 服务正常", state_role="success")
        self.register_page("overview", self._build_overview_page(), title="账号登录", crumb="基础工具 / 账号登录", state="● 真实入口", state_role="success")
        for key, title, crumb in (
            ("real_basic", "基础设置", "基础工具 / 基础设置"),
            ("free_micro", "免费微端", "基础工具 / 免费微端"),
            ("map_settings", "地图设置", "基础工具 / 地图设置"),
            ("search", "文本搜索", "基础工具 / 文本搜索"),
            ("compare", "文件对比", "基础工具 / 文件对比"),
            ("db", "数据库管理", "版本数据 / 数据库管理"),
            ("visual_npc", "可视化NPC", "版本数据 / 可视化NPC"),
            ("visual_spawn", "可视化刷怪", "版本数据 / 可视化刷怪"),
            ("spawn", "刷怪设置", "版本数据 / 刷怪设置"),
            ("currency", "货币兑换", "版本数据 / 货币兑换"),
            ("drop", "爆率管理", "版本数据 / 爆率管理"),
            ("store", "存销设置", "版本数据 / 存销设置"),
            ("recycle", "回收生成", "版本数据 / 回收生成"),
            ("var_query", "变量查询", "版本数据 / 变量查询"),
            ("encoding", "封挂编码", "版本数据 / 封挂编码"),
            ("script", "脚本注入", "版本数据 / 脚本注入"),
            ("item", "物品注入", "版本数据 / 物品注入"),
            ("cdk", "CDK 管理", "运营工具 / CDK 管理"),
            ("member", "会员系统", "运营工具 / 会员系统"),
            ("qq_bot", "QQ机器人", "运营工具 / QQ机器人"),
            ("website", "网站管理", "运营工具 / 网站管理"),
        ):
            self.register_page(key, DarkWorkbenchPlaceholderPage(title, "页面正在接入", accent="warn"), title=title, crumb=crumb, state="● 加载中", state_role="warn")

        self.stack.setObjectName("darkWorkbenchPageStack")
        layout.addWidget(self.stack, 2, 0, 1, 1)
        self.sample_detail_panel = self._build_detail_panel()
        layout.addWidget(self.sample_detail_panel, 2, 1)
        self.sample_log_panel = self._build_log_panel()
        layout.addWidget(self.sample_log_panel, 3, 0, 1, 2)
        layout.setRowStretch(2, 1)
        return content

    def _build_overview_page(self) -> QtWidgets.QWidget:
        page = QtWidgets.QScrollArea()
        page.setObjectName("overviewPage")
        page.setWidgetResizable(True)
        page.setFrameShape(QtWidgets.QFrame.NoFrame)
        page.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        content = QtWidgets.QWidget()
        content.setObjectName("overviewContent")
        root = QtWidgets.QVBoxLayout(content)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        summary = QtWidgets.QGridLayout()
        summary.setContentsMargins(0, 0, 0, 0)
        summary.setHorizontalSpacing(6)
        summary.setVerticalSpacing(4)
        for i, (stat_key, value, label, role) in enumerate(self._overview_stat_items()):
            stat = self._overview_stat(value, label, role)
            value_label = stat.findChild(QtWidgets.QLabel, "overviewStatValue")
            caption_label = stat.findChild(QtWidgets.QLabel, "overviewStatCaption")
            if value_label is not None:
                self.overview_stat_badges[stat_key] = value_label
            if caption_label is not None:
                self.overview_stat_captions[stat_key] = caption_label
            summary.addWidget(stat, 0, i)
            summary.setColumnStretch(i, 1)
        root.addLayout(summary)

        actions = dw_panel("panel")
        actions.setObjectName("overviewActionPanel")
        action_layout = QtWidgets.QGridLayout(actions)
        action_layout.setContentsMargins(6, 5, 6, 5)
        action_layout.setHorizontalSpacing(4)
        action_layout.setVerticalSpacing(3)
        title = dw_label("继续工作", "strong")
        hint = dw_label("这里只保留最近和高频任务，完整功能目录请使用左侧侧边栏。", "muted")
        hint.setWordWrap(True)
        action_layout.addWidget(title, 0, 0, 1, 5)
        action_layout.addWidget(hint, 1, 0, 1, 5)
        for index, (text, target, role) in enumerate(
            (
                ("微端配置", "micro", "quick"),
                ("数据库管理", "db", "quick"),
                ("刷怪设置", "spawn", "quick"),
                ("变量查询", "var_query", "quick"),
                ("脚本注入", "script", "quick"),
            )
        ):
            button = dw_button(text, role)
            button.setObjectName("overviewQuickButton")
            button.clicked.connect(lambda _checked=False, key=target: self.set_current_page(key))
            action_layout.addWidget(button, 2, index, 1, 1)
            action_layout.setColumnStretch(index, 1)
        root.addWidget(actions)

        grid = QtWidgets.QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        alerts_panel = self._overview_list_panel("工程提醒", self._overview_alert_rows())
        self.overview_completion_labels = alerts_panel.findChildren(QtWidgets.QLabel, "overviewListItem")
        grid.addWidget(alerts_panel, 0, 0)
        activity_panel = self._overview_list_panel("高频功能", self._overview_activity_rows())
        self.overview_next_step_labels = activity_panel.findChildren(QtWidgets.QLabel, "overviewListItem")
        grid.addWidget(activity_panel, 0, 1)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        root.addLayout(grid)
        root.addStretch(1)

        page.setWidget(content)
        self._refresh_overview_metrics()
        return page

    def _overview_alert_rows(self) -> tuple[str, ...]:
        return (
            "选择工程目录后，各功能页会沿用同一版本路径",
            "入口按基础工具、版本数据、运营工具分组",
            "底部 Dock 保留常用功能，便于快速切换",
            "网站管理保留入口，按实际维护需求使用",
        )

    def _overview_activity_rows(self) -> tuple[str, ...]:
        return (
            "数据库管理：连接 SQLite 后维护版本数据",
            "脚本注入：选择模板、预览内容并执行注入",
            "变量查询：扫描脚本变量并查看引用位置",
            "免费微端：采集登录器地址、微端链接和临时密码",
        )

    def _overview_stat_items(self) -> tuple[tuple[str, str, str, str], ...]:
        mounted_count = len(self.mounted_pages)
        return (
            ("nav", str(len(self.nav_items)), "导航入口", "success"),
            ("mounted", str(mounted_count), "已挂载功能页", "success" if mounted_count else "warn"),
            ("pages", str(len(self.page_widgets)), "当前可打开页", "warn"),
            ("alerts", "4", "工程提醒", "info"),
        )

    def _refresh_overview_metrics(self) -> None:
        for stat_key, value, label, role in self._overview_stat_items():
            value_label = self.overview_stat_badges.get(stat_key)
            caption_label = self.overview_stat_captions.get(stat_key)
            try:
                if value_label is not None:
                    value_label.setText(value)
                    dw_apply_role(value_label, "badgeRole", role)
                if caption_label is not None:
                    caption_label.setText(label)
            except RuntimeError:
                self.overview_stat_badges.pop(stat_key, None)
                self.overview_stat_captions.pop(stat_key, None)

        for label_widget, text in zip(self.overview_completion_labels, self._overview_alert_rows()):
            try:
                label_widget.setText(text)
            except RuntimeError:
                pass
        for label_widget, text in zip(self.overview_next_step_labels, self._overview_activity_rows()):
            try:
                label_widget.setText(text)
            except RuntimeError:
                pass

    def _overview_stat(self, value: str, label: str, role: str) -> QtWidgets.QFrame:
        panel = dw_panel("panel")
        panel.setObjectName("overviewStat")
        panel.setMinimumHeight(44)
        panel.setMaximumHeight(54)
        layout = QtWidgets.QHBoxLayout(panel)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(8)
        value_badge = dw_badge(value, role)
        value_badge.setObjectName("overviewStatValue")
        value_badge.setAlignment(QtCore.Qt.AlignCenter)
        value_badge.setMinimumWidth(58)
        value_badge.setMaximumWidth(86)
        layout.addWidget(value_badge, 0, QtCore.Qt.AlignVCenter)
        caption = dw_label(label, "muted")
        caption.setObjectName("overviewStatCaption")
        caption.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        layout.addWidget(caption, 1)
        return panel

    def _overview_list_panel(self, title: str, rows: tuple[str, ...]) -> QtWidgets.QFrame:
        panel = dw_panel("panel")
        panel.setObjectName("overviewListPanel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(9, 5, 9, 5)
        layout.setSpacing(3)
        layout.addWidget(dw_label(title, "strong"))
        for text in rows:
            label = dw_label(text, "normal")
            label.setObjectName("overviewListItem")
            label.setWordWrap(True)
            layout.addWidget(label)
        layout.addStretch(1)
        return panel

    def _build_toolbar(self) -> QtWidgets.QFrame:
        toolbar = dw_panel("toolbar")
        toolbar.setFixedHeight(58)
        layout = QtWidgets.QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        layout.addWidget(dw_input("D:\\MirServer\\Mir200\\Envir\\客户端配置", "path"), 1)
        layout.addWidget(dw_input("全部状态 ▾", "small"))
        layout.addWidget(dw_input("端口排序 ▾", "small"))
        layout.addStretch(1)
        layout.addWidget(dw_button("选择目录", "secondary"))
        layout.addWidget(dw_button("扫描配置", "secondary"))
        return toolbar

    def _build_micro_page(self) -> QtWidgets.QFrame:
        page = dw_panel("panel")
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._panel_head("客户端配置列表", "12 个配置 · 3 个待同步"))
        table = QtWidgets.QTableWidget(4, 5)
        table.setHorizontalHeaderLabels(["名称", "网关地址", "端口", "状态", "操作"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setDefaultSectionSize(40)
        rows = [
            ("热血主区客户端", "127.0.0.1", "7200", "运行中", "编辑 · 停止", "success"),
            ("测试二区客户端", "192.168.1.8", "7210", "待同步", "编辑 · 启动", "warn"),
            ("备用微端配置", "192.168.1.9", "7220", "已停止", "编辑 · 启动", "muted"),
            ("活动测试客户端", "10.0.0.33", "7700", "待同步", "编辑 · 启动", "warn"),
        ]
        for row, (name, host, port, state, action, badge_role) in enumerate(rows):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(name))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(host))
            table.setItem(row, 2, QtWidgets.QTableWidgetItem(port))
            table.setCellWidget(row, 3, dw_badge(state, badge_role))
            table.setItem(row, 4, QtWidgets.QTableWidgetItem(action))
        layout.addWidget(table, 1)
        return page

    def _build_detail_panel(self) -> QtWidgets.QFrame:
        panel = dw_panel("panel")
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._panel_head("配置详情", "热血主区客户端"))
        form = QtWidgets.QWidget()
        form_layout = QtWidgets.QVBoxLayout(form)
        form_layout.setContentsMargins(14, 14, 14, 14)
        form_layout.setSpacing(12)
        for label, value in (("客户端名称", "热血主区客户端"), ("网关地址", "127.0.0.1"), ("端口", "7200")):
            form_layout.addWidget(self._field(label, value))
        form_layout.addWidget(self._switch_row("自动同步资源", True))
        form_layout.addWidget(self._switch_row("启动前备份配置", True))
        layout.addWidget(form)
        preview = QtWidgets.QWidget()
        preview_layout = QtWidgets.QVBoxLayout(preview)
        preview_layout.setContentsMargins(14, 14, 14, 14)
        preview_layout.setSpacing(10)
        preview_layout.addWidget(self._mini_card("配置预览", "当前配置会写入 ClientConfig.ini，并同步更新微端网关端口。"))
        preview_layout.addWidget(self._mini_card("风险提示", "目标端口正在运行，保存后需要重启网关才能完全生效。"))
        preview_layout.addStretch(1)
        layout.addWidget(preview, 1)
        return panel

    def _build_log_panel(self) -> QtWidgets.QFrame:
        t = DarkWorkbenchTokens
        panel = dw_panel("panel")
        panel.setFixedHeight(t.LOG_H)
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._panel_head("执行日志", "实时输出"))
        log = QtWidgets.QPlainTextEdit()
        log.setReadOnly(True)
        log.setPlainText(
            "[14:32:18] 扫描目录 D:\\MirServer\\Mir200\\Envir 完成，发现 12 个客户端配置。\n"
            "[14:32:21] 校验端口 7200：通过，资源目录完整。\n"
            "[14:32:25] 等待用户应用配置，已生成备份计划。"
        )
        dw_apply_role(log, "textRole", "log")
        layout.addWidget(log, 1)
        return panel

    def _field(self, label: str, value: str) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(dw_label(label, "field-label"))
        layout.addWidget(dw_input(value, "normal"))
        return widget

    def _switch_row(self, text: str, checked: bool) -> QtWidgets.QWidget:
        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(dw_label(text, "normal"))
        layout.addStretch(1)
        switch = QtWidgets.QCheckBox()
        switch.setChecked(checked)
        switch.setCursor(QtCore.Qt.PointingHandCursor)
        dw_apply_role(switch, "checkRole", "switch")
        layout.addWidget(switch)
        return widget

    def _mini_card(self, title: str, text: str) -> QtWidgets.QFrame:
        card = dw_panel("mini-card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(7)
        layout.addWidget(dw_label(title, "strong"))
        body = dw_label(text, "muted")
        body.setWordWrap(True)
        layout.addWidget(body)
        return card

    def _panel_head(self, title: str, subtitle: str) -> QtWidgets.QFrame:
        head = dw_panel("panel-head")
        head.setFixedHeight(44)
        layout = QtWidgets.QHBoxLayout(head)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.addWidget(dw_label(title, "strong"))
        layout.addStretch(1)
        layout.addWidget(dw_label(subtitle, "muted"))
        return head

    def _build_statusbar(self) -> QtWidgets.QFrame:
        t = DarkWorkbenchTokens
        bar = dw_panel("statusbar")
        bar.setObjectName("darkWorkbenchStatusBar")
        self._statusbar_widget = bar
        bar.setFixedHeight(t.STATUS_H)
        layout = QtWidgets.QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        task_status = QtWidgets.QLabel("就绪")
        task_status.setObjectName("shellTaskStatus")
        task_status.setAlignment(QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft)
        task_status.setMinimumWidth(120)
        layout.addWidget(task_status, 1)

        count = QtWidgets.QLabel("0 项")
        count.setObjectName("shellStatusCount")
        layout.addWidget(count, 0, QtCore.Qt.AlignVCenter)
        encoding = QtWidgets.QLabel("UTF-8")
        encoding.setObjectName("shellStatusEncoding")
        layout.addWidget(encoding, 0, QtCore.Qt.AlignVCenter)

        button_host = QtWidgets.QWidget()
        button_host.setObjectName("friendLinkBindingHost")
        button_layout = QtWidgets.QHBoxLayout(button_host)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(6)
        ad_hint = QtWidgets.QLabel("暂无友情链接", button_host)
        ad_hint.hide()
        self.bottom_ad_hint_label = ad_hint
        self.bottom_ad_buttons = []
        for index in range(4):
            button = dw_button("", "friend-link")
            button.setObjectName(f"bottomFriendLink{index + 1}")
            button.hide()
            button.clicked.connect(lambda _checked=False, b=button: self._request_bottom_friend_link(b))
            self.bottom_ad_buttons.append(button)
            button_layout.addWidget(button, 0)
        button_layout.addStretch(1)
        button_host.hide()

        self.bottom_ad_frame = bar
        self._refresh_bottom_friend_links()

        return bar

    @staticmethod
    def qss() -> str:
        t = DarkWorkbenchTokens
        return f"""
QWidget {{ background: {t.BG}; color: {t.TEXT}; font-size: 13px; }}
QWidget#darkWorkbenchWindow {{ background: #CBD5E1; border: 1px solid #94A3B8; }}
QLabel {{ background: transparent; }}
QFrame[panelRole="titlebar"] {{ background: {t.CHROME}; border-bottom: 1px solid {t.LINE_SOFT}; }}
QLabel#projectRootLabel {{
color: {t.MUTED}; font-size: 12px; font-weight: 700; padding-left: 2px; padding-right: 2px;
}}
QLabel#brandVersionLabel {{
color: {t.MUTED}; font-size: 11px; font-weight: 650; padding-left: 6px; padding-right: 4px;
}}
QWidget#topContextBox {{ background: transparent; }}
QWidget#topContextBox QWidget[topContextCompact="true"],
QWidget#topContextBox QFrame[topContextCompact="true"] {{
background: transparent;
border: none;
border-radius: 0px;
padding: 0px;
}}
QWidget#topContextBox QLineEdit {{
background: #FFFFFF; min-height: 28px; max-height: 28px;
padding-left: 5px; padding-right: 5px;
}}
        QWidget#topContextBox QPushButton {{
min-width: 54px; min-height: 28px; max-height: 28px;
padding-left: 5px; padding-right: 5px;
}}
        QWidget#topContextBox QComboBox {{
background: #FFFFFF; min-height: 28px; max-height: 28px;
padding-left: 5px; padding-right: 20px;
}}
QWidget#topContextBox QLineEdit {{
min-height: 28px; max-height: 28px;
padding: 0px 18px 0px 5px;
}}
QWidget#topContextBox QFrame#dbConnectionPanel[dbTopContext="true"] {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#topContextBox QWidget#dbFileRow {{
min-height: 28px; max-height: 28px;
}}
QWidget#topContextBox QLabel#dbFieldLabel {{
color: {t.MUTED}; font-size: 12px; font-weight: 800;
min-width: 22px; max-width: 22px; min-height: 28px; max-height: 28px;
}}
QWidget#topContextBox QPushButton[dbConnectionActionRole] {{
min-height: 26px; max-height: 26px; border-radius: 4px;
padding-left: 5px; padding-right: 5px;
}}
        QFrame[panelRole="sidebar"] {{
        background: {t.PANEL_2};
        border-right: 1px solid {t.LINE_SOFT};
        }}
        QFrame[panelRole="workspace"] {{ background: {t.BG}; }}
        QFrame[panelRole="page-header"] {{ background: {t.CHROME}; border-bottom: 1px solid {t.LINE_SOFT}; }}
QFrame[panelRole="statusbar"] {{ background: {t.CHROME}; border-top: 1px solid {t.LINE_SOFT}; }}
QFrame#bottomFriendLinksBar {{
background: {t.CHROME};
border-top: 1px solid {t.LINE_SOFT};
}}
QLabel#bottomAdBadge {{
min-width: 68px;
max-width: 68px;
min-height: 21px;
max-height: 21px;
border-radius: 4px;
border: 1px solid {t.LINE_SOFT};
background: {t.PANEL_2};
color: {t.MUTED};
font-weight: 700;
font-size: 12px;
}}
QLabel#bottomAdHint {{
color: {t.MUTED};
font-size: 12px;
font-weight: 600;
}}
QPushButton[buttonRole="friend-link"] {{
min-height: 22px;
max-height: 22px;
padding: 0 10px;
border-radius: 4px;
border: 1px solid transparent;
background: transparent;
color: {t.MUTED};
font-weight: 700;
}}
QPushButton[buttonRole="friend-link"]:hover {{
border-color: {t.LINE};
background: {t.PANEL_2};
color: {t.TEXT};
}}
QFrame[panelRole="dock-rail"] {{ background: {t.PANEL_2}; border-right: 1px solid {t.LINE_SOFT}; }}
        QFrame[panelRole="dock-strip"] {{
        background: {t.PANEL_2};
        border: 1px solid {t.LINE_SOFT};
        border-top: 1px solid {t.LINE_SOFT};
        border-radius: 0px;
        }}
        QFrame[panelRole="dock-tools"] {{
        background: {t.PANEL};
        border: 1px solid {t.LINE_SOFT};
        border-radius: 13px;
        }}
        QFrame[panelRole="dock-pulse"] {{
        background: {t.PANEL};
        border: 1px solid {t.LINE_SOFT};
        border-radius: 13px;
        }}
        QFrame[panelRole="toolbar"], QFrame[panelRole="panel"], QFrame[panelRole="account"] {{
            background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: {t.RADIUS}px;
        }}
        QFrame[panelRole="account"] {{
        background: {t.PANEL};
        border: 1px solid {t.LINE};
        border-radius: 14px;
        }}
        QFrame#sidebarAccountPanel {{
        border-left: 2px solid {t.BRAND};
        }}
        QFrame[panelRole="panel-head"] {{ background: {t.PANEL}; border-bottom: 1px solid {t.LINE_SOFT}; }}
        QFrame[panelRole="mini-card"] {{ background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 9px; }}
QFrame[panelRole="nav"], QFrame[panelRole="nav-active"] {{
min-height: 24px; max-height: 24px; border-radius: 7px; border: 1px solid transparent;
    background: transparent;
}}
        QFrame[panelRole="nav-active"] {{
        background: #FFF7ED;
        border: 1px solid #FDBA74;
        border-left: 3px solid {t.BRAND};
        }}
QFrame[panelRole="dock"], QFrame[panelRole="dock-active"] {{
min-width: 50px; max-width: 54px; min-height: 24px; max-height: 24px;
    border-radius: 7px; border: 1px solid {t.LINE_SOFT};
    background: {t.PANEL};
}}
        QFrame[panelRole="dock-active"] {{
        border: 1px solid #FDBA74;
        background: #FFF7ED;
        }}
        QFrame#dockTabStatus {{
        min-height: 2px; max-height: 2px; border-radius: 1px;
        background: {t.LINE_SOFT};
        }}
        QFrame#dockTabStatus[stateRole="active"] {{
        background: {t.BRAND};
        }}
QLabel[labelRole="mark"] {{
min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; border-radius: 8px;
        background: {t.BRAND};
        color: #ffffff; font-size: 16px; font-weight: 900;
        }}
QLabel[labelRole="dock-rail-mark"] {{
min-width: 23px; max-width: 23px; min-height: 23px; max-height: 23px; border-radius: 7px;
background: #FFF7ED; color: {t.BRAND}; font-size: 13px; font-weight: 900;
            border: 1px solid #FDBA74;
        }}
QLabel[labelRole="brand"] {{ font-size: 15px; font-weight: 900; color: {t.TEXT}; }}
QLabel[labelRole="page-title"] {{ font-size: 16px; font-weight: 850; color: {t.TEXT}; }}
        QLabel[labelRole="strong"] {{ font-weight: 750; color: {t.TEXT}; }}
QLabel[labelRole="muted"] {{ color: {t.MUTED}; font-size: 12px; }}
QLabel[labelRole="crumb"] {{ color: {t.MUTED}; font-size: 11px; font-weight: 600; }}
QLabel[labelRole="section"] {{ color: {t.MUTED}; font-size: 11px; font-weight: 750; padding-left: 7px; padding-top: 4px; padding-bottom: 1px; }}
        QLabel[labelRole="nav"] {{ color: {t.TEXT}; font-size: 12px; font-weight: 760; }}
        QLabel[labelRole="nav-active"] {{ color: #92400E; font-size: 12px; font-weight: 950; }}
QLabel[labelRole="nav-icon"], QLabel[labelRole="nav-icon-active"], QLabel[labelRole="avatar"] {{
min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px; border-radius: 5px;
    background: #E5E7EB; color: {t.MUTED}; font-size: 10px; font-weight: 900;
}}
QLabel[labelRole="dock-icon"], QLabel[labelRole="dock-icon-active"] {{ min-width: 15px; max-width: 15px; min-height: 15px; max-height: 15px; border-radius: 5px; background: #E5E7EB; color: {t.MUTED}; font-size: 8px; font-weight: 900; }}
QLabel[labelRole="dock-icon-active"] {{ background: #FFF7ED; color: #92400E; border: 1px solid #FDBA74; }}
QLabel[labelRole="dock-title"], QLabel[labelRole="dock-title-active"] {{ color: {t.MUTED}; font-size: 8px; font-weight: 900; }}
QLabel[labelRole="dock-title-active"] {{ color: #92400E; }}
QLabel[labelRole="dock-subtitle"] {{ color: {t.SUBTLE}; font-size: 9px; font-weight: 650; }}
QLabel[labelRole="dock-log-title"] {{ color: {t.TEXT}; font-size: 10px; font-weight: 900; }}
QLabel[labelRole="dock-log"] {{ color: {t.MUTED}; font-size: 10px; font-weight: 800; font-family: Consolas, "Microsoft YaHei UI"; }}
QLabel[labelRole="dock-log-muted"] {{ color: {t.SUBTLE}; font-size: 9px; font-weight: 650; }}
QLabel[labelRole="dock-footer"] {{ color: {t.MUTED}; font-size: 12px; font-weight: 700; }}
QLabel[labelRole="avatar"] {{ min-width: 24px; max-width: 24px; min-height: 24px; max-height: 24px; border-radius: 7px; color: #92400E; background: #FFF7ED; border: 1px solid #FDBA74; }}QLabel[labelRole="nav-icon-active"] {{
color: #92400E;
background: #FFF7ED;
border: 1px solid #FDBA74;
}}
        QLabel[labelRole="field-label"] {{ color: {t.MUTED}; font-size: 12px; font-weight: 700; }}
QLabel[fieldRole] {{
 min-height: 36px; border: 1px solid {t.LINE_SOFT}; border-radius: 9px; background: {t.PANEL_2};
 color: {t.TEXT}; padding-left: 11px; padding-right: 11px;
}}
QLabel#sidebarSearchField {{
 min-height: 37px; border-radius: 10px;
 background: {t.PANEL_2};
 border: 1px solid {t.LINE};
 color: {t.MUTED};
}}
QLineEdit#sidebarSearchField {{
min-height: 28px; border-radius: 6px; padding-left: 8px; padding-right: 7px;
 background: {t.PANEL_2};
 border: 1px solid {t.LINE};
 color: {t.TEXT};
 selection-background-color: #FFF7ED;
 selection-color: #92400E;
}}
QLineEdit#sidebarSearchField:focus {{
 border: 1px solid {t.BRAND};
 background: #FFFFFF;
}}
QFrame#sidebarGlobalTools {{
 border-radius: 6px;
 background: {t.PANEL_2};
 border: 1px solid {t.LINE_SOFT};
}}
QFrame[panelRole="nav"] {{
min-height: 24px; max-height: 24px; border-radius: 6px;
background: transparent;
border: 1px solid transparent;
}}
        QFrame[panelRole="nav"]:hover {{
            background: {t.PANEL_2};
            border-color: {t.LINE_SOFT};
        }}
QFrame[panelRole="nav-active"] {{
min-height: 24px; max-height: 24px; border-radius: 6px;
background: #FFF4E8;
border: 1px solid #FFD7B5;
}}
        QFrame#navActiveIndicator[stateRole="idle"] {{
        min-height: 18px; max-height: 18px; border-radius: 2px;
        background: transparent;
        }}
QFrame#navActiveIndicator[stateRole="active"] {{
min-height: 22px; max-height: 22px; border-radius: 2px;
        background: {t.BRAND};
        }}
        QLabel[fieldRole="search"], QLabel[fieldRole="project"] {{ color: {t.MUTED}; }}
QLabel[fieldRole="project"] {{
    min-height: 30px; border-radius: 6px;
background: {t.PANEL};
border: 1px solid {t.LINE};
color: {t.TEXT};
}}
        QLabel[fieldRole="small"] {{ min-width: 136px; max-width: 136px; }}
        QLabel[badgeRole] {{
        min-height: 20px; border-radius: 10px; padding-left: 7px; padding-right: 7px; font-size: 12px; font-weight: 750;
        background: {t.PANEL_2}; border: 1px solid {t.LINE}; color: {t.MUTED};
        }}
QLabel[badgeRole="success"], QLabel[badgeRole="ok"] {{ color: #166534; border-color: #BBF7D0; background: #DCFCE7; }}
QLabel[badgeRole="warn"] {{ color: #92400E; border-color: #FDE68A; background: #FEF3C7; }}
QLabel[badgeRole="nav"] {{ min-width: 24px; min-height: 20px; font-size: 11px; color: {t.MUTED}; border: none; background: {t.PANEL_2}; }}
QPushButton {{ min-height: 30px; max-height: 30px; border-radius: 4px; padding-left: 12px; padding-right: 12px; border: 1px solid {t.LINE}; background: {t.PANEL}; color: {t.TEXT}; font-size: 13px; font-weight: 600; }}
QPushButton:hover {{ border-color: #AEB7C2; background: #EEF1F4; color: {t.TEXT}; }}
QPushButton:pressed {{ background: #E5E9ED; border-color: #87919D; color: {t.TEXT}; }}
QPushButton[buttonRole="primary"] {{ min-height: 30px; max-height: 30px; color: #FFF9F3; border: 1px solid #C45100; background: {t.BRAND}; font-size: 13px; font-weight: 650; }}
QPushButton[buttonRole="primary"]:hover {{ background: #B94700; border-color: #B94700; color: #FFF9F3; }}
QPushButton[buttonRole="secondary"] {{ background: #FCFDFE; color: {t.TEXT}; border-color: #D4DAE1; font-weight: 600; }}
QPushButton[buttonRole="secondary"]:hover {{ background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2; }}
QPushButton[buttonRole="tertiary"] {{ background: transparent; color: {t.MUTED}; border-color: transparent; font-weight: 600; }}
QPushButton[buttonRole="tertiary"]:hover {{ background: #EEF1F4; color: {t.TEXT}; border-color: transparent; }}
QPushButton[buttonRole="compact"], QPushButton[buttonRole="segmented"] {{ min-height: 26px; max-height: 26px; padding-left: 8px; padding-right: 8px; font-size: 13px; font-weight: 600; }}
QPushButton[buttonRole="danger"] {{ color: #B83A32; border: 1px solid #E5A6A2; background: #FFF0EF; font-weight: 600; }}
QPushButton[buttonRole="danger"]:hover {{ color: #991B1B; border-color: #B42318; background: #FEE2E2; }}
QPushButton[buttonRole="danger"]:pressed {{ color: #7F1D1D; background: #FECACA; border-color: #991B1B; }}
QWidget#topContextBox QPushButton {{
min-height: 28px; max-height: 28px;
border-radius: 4px;
padding-left: 5px; padding-right: 5px;
}}
QPushButton[buttonRole="quick"] {{ min-height: 30px; padding-left: 7px; padding-right: 7px; font-size: 12px; background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; }}
QPushButton[buttonRole="quick"]:hover {{ background: #FFF7ED; color: #92400E; border-color: #FDBA74; }}
QPushButton[buttonRole="global-tool"] {{ min-height: 22px; border-radius: 7px; padding-left: 4px; padding-right: 4px; background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; font-size: 12px; font-weight: 780; }}
QPushButton[buttonRole="global-tool"]:hover {{ background: #FFF7ED; border-color: #FDBA74; color: #92400E; }}QFrame#darkWorkbenchSidebar QPushButton[buttonRole="quick"] {{
        min-height: 36px; border-radius: 9px;
        background: {t.PANEL};
        border: 1px solid {t.LINE};
        color: {t.TEXT};
        }}
        QFrame#darkWorkbenchSidebar QPushButton[buttonRole="quick"]:hover {{
        border-color: #FDBA74;
        background: #FFF7ED;
        }}
QFrame[panelRole="titlebar"] QPushButton[buttonRole="icon"] {{
min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px; padding: 0;
    color: {t.MUTED}; border-radius: 4px; background: {t.PANEL}; border: 1px solid {t.LINE};
}}
        QFrame[panelRole="titlebar"] QPushButton[buttonRole="icon"]:hover {{
            color: #92400E; border-color: #FDBA74; background: #FFF7ED;
        }}
        QFrame[panelRole="titlebar"] QPushButton[buttonRole="icon"]:pressed {{
            color: #92400E; border-color: #D97706; background: #FEF3C7;
        }}
QPushButton[buttonRole="dock-secondary"] {{
min-width: 40px; max-width: 48px; min-height: 18px; max-height: 18px; border-radius: 6px;
color: {t.TEXT}; background: {t.PANEL}; border: 1px solid {t.LINE};
font-size: 10px; font-weight: 850; padding-left: 4px; padding-right: 4px;
}}
QPushButton[buttonRole="dock-primary"] {{
min-width: 52px; max-width: 62px; min-height: 20px; max-height: 20px; border-radius: 7px;
color: #ffffff; border: 1px solid #B45309;
background: {t.BRAND};
font-size: 11px; font-weight: 900; padding-left: 6px; padding-right: 6px;
}}
        QPushButton[buttonRole="dock-secondary"]:hover, QPushButton[buttonRole="dock-primary"]:hover {{
border-color: #FDBA74;
}}
        QFrame#dockActionSeparator {{ color: {t.LINE_SOFT}; background: {t.LINE_SOFT}; max-width: 1px; margin-left: 4px; margin-right: 4px; }}
QFrame#overviewStat {{
background: {t.PANEL};
border: 1px solid {t.LINE_SOFT};
border-radius: 6px;
}}
QFrame#overviewActionPanel QPushButton#overviewQuickButton {{
min-height: 26px; max-height: 26px; border-radius: 4px;
padding-left: 8px; padding-right: 8px; font-size: 13px; font-weight: 600;
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE};
}}
QFrame#overviewActionPanel QPushButton#overviewQuickButton[buttonRole="secondary"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE};
}}
QFrame#overviewActionPanel QPushButton#overviewQuickButton[buttonRole="quick"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE};
}}
QFrame#overviewListPanel QLabel#overviewListItem {{
min-height: 18px; padding: 1px 4px; border-radius: 0;
background: transparent; border: none; border-bottom: 1px solid {t.LINE_SOFT}; color: {t.TEXT};
}}
        QTableWidget {{ background: {t.PANEL}; alternate-background-color: {t.PANEL_2}; border: none; gridline-color: {t.LINE_SOFT}; selection-background-color: #FFF7ED; selection-color: #92400E; color: {t.TEXT}; }}
        QHeaderView::section {{ background: {t.PANEL_2}; color: {t.MUTED}; border: none; border-bottom: 1px solid {t.LINE_SOFT}; padding-left: 10px; font-size: 12px; font-weight: 800; }}
        QTableWidget::item {{ border-bottom: 1px solid {t.LINE_SOFT}; padding-left: 8px; padding-right: 8px; }}
        QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {t.LINE}; background: {t.PANEL_2}; }}
        QCheckBox::indicator:checked {{ background: {t.BRAND}; border-color: {t.BRAND_2}; }}
        QCheckBox[checkRole="switch"]::indicator {{ width: 40px; height: 22px; border-radius: 11px; background: rgba(54, 163, 255, 0.25); border: 1px solid rgba(54, 163, 255, 0.45); }}
QPlainTextEdit {{ border: none; background: {t.PANEL}; color: {t.TEXT}; padding: 8px 12px; font-family: Consolas, "Microsoft YaHei UI"; font-size: 12px; selection-background-color: #FFF7ED; selection-color: #92400E; }}
        QFrame#itemRootBar, QFrame#dropRootBar,
        QFrame#itemTemplatePanel, QFrame#itemEditorPanel,
        QFrame#mapPageHeader,
        QFrame#mapSettingsBar, QFrame#mapListPanel,
        QFrame#dropDetailPanel, QFrame#overallOptFormPanel,
        QFrame#microConfigHeader, QFrame#microConfigListPanel,
        QFrame#microConfigEditorPanel,
        QFrame#dbConnectionPanel, QFrame#dbWorkspacePanel,
        QWidget#dbBottomActionBar,
        QFrame#websiteRootPanel, QFrame#websiteRootBar,
        QFrame#websiteWorkspacePanel, QWidget#websiteToolbar,
        QWidget#websiteSitePanel, QWidget#websiteContentPanel,
        QFrame#websiteVersionPanel, QFrame#websiteQqPanel,
        QFrame#websiteDropPanel, QFrame#websiteOutputPanel,
        QFrame#memberAccountsPanel, QFrame#memberActionsPanel,
        QGroupBox#memberExpiryBox, QGroupBox#memberCoreActionsBox, QGroupBox#memberHelpBox,
        QGroupBox#currencyExchangeBox, QFrame#currencyExchangeBox,
        QWidget#currencyExchangeHeader {{
            background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 8px;
        }}
        QGroupBox#currencyExchangeBox {{
            padding: 10px;
        }}
        QFrame#itemRootBar, QFrame#dropRootBar,
        QFrame#itemTemplatePanel, QFrame#itemEditorPanel,
        QFrame#mapPageHeader,
        QFrame#mapSettingsBar, QFrame#mapListPanel,
        QFrame#microConfigHeader, QFrame#microConfigListPanel,
        QFrame#microConfigEditorPanel,
        QFrame#dbConnectionPanel, QFrame#dbWorkspacePanel,
        QWidget#dbBottomActionBar,
        QFrame#websiteRootPanel, QFrame#websiteRootBar,
        QFrame#websiteWorkspacePanel, QWidget#websiteToolbar,
        QWidget#websiteSitePanel, QWidget#websiteContentPanel,
        QFrame#websiteVersionPanel, QFrame#websiteQqPanel,
        QFrame#websiteDropPanel, QFrame#websiteOutputPanel,
        QFrame#memberAccountsPanel, QFrame#memberActionsPanel {{
            padding: 10px;
        }}
QFrame#mapSettingsBar {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
}}
QFrame#mapListPanel {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
}}
        QFrame#mapPageHeader {{
            background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
        QFrame#basicRootBox, QFrame#quickPathPanel, QFrame#textSearchPanel {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
QFrame#compareFileBox,
QWidget#compareOptionsBar,
QWidget#compareActionBar {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QFrame#compareFileBox {{
background: {t.PANEL}; border-color: {t.LINE_SOFT};
}}
QWidget#compareOptionsBar {{
background: transparent; border: none;
}}
QWidget#compareActionBar {{
background: transparent; border: none;
}}
        QLabel#compareFieldLabel {{
            color: {t.TEXT}; font-weight: 800;
        }}
QLabel#compareStatusLabel {{
color: {t.MUTED}; font-weight: 750;
padding: 5px 10px; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
background: {t.PANEL_2};
}}
QFrame#compareSummaryBar {{
background: transparent; border: none;
}}
QLabel#compareSummaryPill {{
color: {t.MUTED}; font-weight: 700;
padding: 5px 10px; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
background: {t.PANEL};
}}
QLabel#compareSummaryPill[summaryRole="left"],
QLabel#compareSummaryPill[summaryRole="right"] {{
color: {t.TEXT};
}}
QLabel#compareSummaryPill[summaryRole="option"] {{
background: {t.PANEL_2}; color: #92400E;
}}
QLineEdit#comparePathEdit {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
 selection-background-color: #E7EAEE; selection-color: {t.TEXT};
}}
QPushButton#comparePickFileButton {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
font-weight: 750;
}}
QPushButton#comparePickFileButton:hover {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QWidget#compareOptionsBar QCheckBox {{
color: {t.TEXT}; font-weight: 650; spacing: 7px;
}}
QToolButton#compareOptionButton {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-radius: 6px;
font-weight: 750;
}}
QToolButton#compareOptionButton:hover {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QToolButton#compareOptionButton[compareOptionChecked="true"] {{
background: #FFF7ED; color: #92400E; border-color: transparent; font-weight: 750;
}}
QWidget#compareActionBar QPushButton {{
min-height: 28px;
max-height: 28px;
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid transparent; border-radius: 6px;
font-weight: 750;
}}
QWidget#compareActionBar QPushButton:hover {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QWidget#compareActionBar QPushButton[compareActionRole="compare"] {{
min-height: 28px; max-height: 28px; min-width: 64px; max-width: 64px;
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309; font-weight: 850;
}}
QWidget#compareActionBar QPushButton[compareActionRole="previous"],
QWidget#compareActionBar QPushButton[compareActionRole="next"] {{
background: {t.PANEL_2}; color: {t.MUTED};
}}
QWidget#compareActionBar QPushButton[compareActionRole="saveLeft"],
QWidget#compareActionBar QPushButton[compareActionRole="saveRight"] {{
border-color: {t.LINE_SOFT};
}}
QWidget#comparePage QWidget#compareActionBar {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#comparePage QFrame#compareOptionGroup,
QWidget#comparePage QWidget#compareInlineActions,
QWidget#comparePage QFrame[compareActionGroupFrame="true"] {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#comparePage QFrame#compareMergeActions,
QWidget#comparePage QFrame#compareSaveActions {{
border-left: 1px solid {t.LINE_SOFT}; padding-left: 6px; margin-left: 2px;
}}
QWidget#comparePage QToolButton#compareOptionButton {{
min-height: 26px; max-height: 26px; padding: 0 7px; margin: 0px;
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE}; border-radius: 0px; font-weight: 600;
}}
QWidget#comparePage QToolButton#compareOptionButton[segmentPosition="first"] {{
border-top-left-radius: 4px; border-bottom-left-radius: 4px;
}}
QWidget#comparePage QToolButton#compareOptionButton[segmentPosition="middle"],
QWidget#comparePage QToolButton#compareOptionButton[segmentPosition="last"] {{ border-left: none; }}
QWidget#comparePage QToolButton#compareOptionButton[segmentPosition="last"] {{
border-top-right-radius: 4px; border-bottom-right-radius: 4px;
}}
QWidget#comparePage QToolButton#compareOptionButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#comparePage QToolButton#compareOptionButton:checked,
QWidget#comparePage QToolButton#compareOptionButton[compareOptionChecked="true"] {{
background: #E5E9ED; color: {t.TEXT}; border-color: #87919D; font-weight: 600;
}}
QWidget#comparePage QWidget#compareActionBar QPushButton {{
min-height: 26px; max-height: 26px; padding: 0 8px;
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
}}
QWidget#comparePage QWidget#compareActionBar QPushButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#comparePage QFrame#compareFileBox QPushButton[compareActionRole="compare"] {{
min-height: 30px; max-height: 30px; border-radius: 4px; font-weight: 650;
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
}}
QWidget#comparePage QFrame#compareFileBox QPushButton[compareActionRole="compare"]:hover {{
background: #B45309; color: #ffffff; border-color: #92400E;
}}
QFrame#compareEditorPane {{ background: transparent; border: none; }}
QLabel#compareEditorTitle {{
background: transparent; color: {t.MUTED}; border: none; font-weight: 750; padding: 2px 4px;
}}
QLabel#compareEditorTitle[compareSide="left"] {{ color: #B42318; }}
QLabel#compareEditorTitle[compareSide="right"] {{ color: #16803A; }}
QPlainTextEdit#compareTextEditor {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
        QFrame#currencyExchangeBox {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
QFrame#dropRootBar {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
}}
QFrame#dropDetailPanel {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
}}
QFrame#dropRootBar {{
padding: 8px;
}}
QScrollArea#dropTaskGridPanel {{
background: transparent; border: none;
}}
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar:vertical {{
width: 10px; background: transparent;
}}
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar::handle:vertical {{
min-height: 30px; border-radius: 5px; background: #CBD5E1;
}}
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar::handle:vertical:hover {{
background: #FDBA74;
}}
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar::handle:vertical:pressed {{
background: {t.BRAND};
}}
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar::add-line:vertical,
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar::sub-line:vertical {{
height: 0; background: transparent;
}}
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar::add-page:vertical,
QWidget#dropRatePage QScrollArea#dropTaskGridPanel QScrollBar::sub-page:vertical {{
background: transparent;
}}
QWidget#dropRatePage QSplitter#dropWorkspaceSplitter::handle:vertical {{
height: 4px;
background: #EEF2F7;
border: none;
margin: 3px 18px;
}}
        QScrollArea#dropTaskGridPanel QWidget {{
            background: transparent;
        }}
        QGroupBox#dropCallTaskCard,
        QGroupBox#dropOptTaskCard,
        QGroupBox#dropOverallOptTaskCard,
        QGroupBox#dropGroupTaskCard,
        QGroupBox#dropAddTaskCard,
QGroupBox#dropDeleteTaskCard {{
    background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
    margin-top: 12px; padding: 8px 8px 5px 8px;
}}
        QGroupBox#dropCallTaskCard::title,
        QGroupBox#dropOptTaskCard::title,
        QGroupBox#dropOverallOptTaskCard::title,
        QGroupBox#dropGroupTaskCard::title,
        QGroupBox#dropAddTaskCard::title,
        QGroupBox#dropDeleteTaskCard::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            left: 10px;
            top: 2px;
            color: {t.MUTED};
            background: transparent;
border: 1px solid transparent;
border-radius: 0;
padding: 0 6px;
font-weight: 750;
}}
        QFrame#callActionBar,
        QFrame#optActionBar,
        QFrame#groupActionBar,
        QFrame#deleteActionBar,
        QFrame#deletePickBar,
        QFrame#overallOptActionBar,
        QWidget#addMonitemsActions {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px; padding: 4px;
        }}
        QFrame#callActionBar QPushButton,
        QFrame#optActionBar QPushButton,
        QFrame#groupActionBar QPushButton,
        QFrame#deleteActionBar QPushButton,
QFrame#deletePickBar QPushButton,
QFrame#overallOptActionBar QPushButton,
QWidget#addMonitemsActions QPushButton {{
min-height: 28px;
color: {t.TEXT}; background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
font-weight: 750;
}}
        QFrame#callActionBar QPushButton[buttonRole="primary"],
        QFrame#callActionBar QPushButton#primaryButton,
        QFrame#optActionBar QPushButton[buttonRole="primary"],
        QFrame#optActionBar QPushButton#primaryButton,
        QFrame#groupActionBar QPushButton[buttonRole="primary"],
        QFrame#groupActionBar QPushButton#primaryButton,
        QFrame#deleteActionBar QPushButton[buttonRole="primary"],
        QFrame#deleteActionBar QPushButton#primaryButton,
        QFrame#overallOptActionBar QPushButton[buttonRole="primary"],
        QFrame#overallOptActionBar QPushButton#primaryButton,
QWidget#addMonitemsActions QPushButton[buttonRole="primary"],
QWidget#addMonitemsActions QPushButton#primaryButton {{
color: #06111d; background: {t.BRAND}; border-color: {t.BRAND_2};
min-width: 88px;
        }}
        QFrame#callActionBar QPushButton:hover,
        QFrame#optActionBar QPushButton:hover,
        QFrame#groupActionBar QPushButton:hover,
        QFrame#deleteActionBar QPushButton:hover,
        QFrame#deletePickBar QPushButton:hover,
        QFrame#overallOptActionBar QPushButton:hover,
QWidget#addMonitemsActions QPushButton:hover {{
background: #FFF7ED; border-color: #FDBA74; color: #92400E;
        }}
        QFrame#overallOptFormPanel,
        QGroupBox#addMonitemsBox {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
        QLabel#dropOverallHint {{
            color: {t.MUTED}; font-size: 12px; padding: 2px 4px;
        }}
        QLabel#dropDetailTitle {{
            color: {t.TEXT}; font-weight: 800;
        }}
        QLabel#dropDetailHint,
        QLabel#dropDetailMetaValue {{
            color: {t.MUTED};
        }}
        QLabel#dropDetailMetaLabel {{
            color: {t.MUTED}; font-weight: 800;
        }}
QPlainTextEdit#dropDetailLog {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
color: {t.TEXT};
}}
        QPlainTextEdit#dropDeleteTextEditor {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
            color: {t.TEXT}; selection-background-color: #FFF7ED; selection-color: #92400E;
        }}
QProgressBar#dropDetailProgress {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 7px;
min-height: 18px; max-height: 18px; color: {t.MUTED}; font-weight: 750; text-align: center;
}}
QProgressBar#dropDetailProgress::chunk {{
border-radius: 5px; background: #FFF7ED; border: none;
}}
        QLabel#currencyExchangeTitle {{
            color: {t.TEXT}; font-size: 13px; font-weight: 800;
        }}
QWidget#currencyExchangeHeader,
QWidget#currencyExchangeRows,
QWidget#currencyInfoBar {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
}}
QWidget#currencyInfoBar QLabel#currencyInfoText {{
color: {t.MUTED}; font-size: 12px; font-weight: 650;
}}
QWidget#currencyInfoBar QWidget#currencyInfoActions {{
background: transparent; border: 1px solid transparent; border-radius: 7px;
}}
QWidget#currencyExchangeHeader QLabel#currencyPanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; padding-left: 2px; padding-right: 6px; font-weight: 650;
}}
QWidget#currencyExchangeTitleRow,
QFrame#currencyExchangeSummaryBar {{
background: transparent; border: none;
}}
QLabel#currencyExchangeSummaryPill {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 7px;
font-weight: 700; padding: 0 8px;
}}
QLabel#currencyExchangeSummaryPill[summaryRole="map"],
QLabel#currencyExchangeSummaryPill[summaryRole="rules"],
QLabel#currencyExchangeSummaryPill[summaryRole="coord"] {{
color: {t.TEXT};
}}
QLabel#currencyExchangeSummaryPill[summaryRole="npc"] {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
font-weight: 650;
}}
QWidget#currencyInfoBar QPushButton {{
min-height: 24px; max-height: 24px;
}}
        QWidget#currencyExchangeActions {{
            background: transparent; border: none;
        }}
QWidget#currencyExchangeActions QPushButton {{
min-height: 24px; max-height: 24px; min-width: 76px; max-width: 86px;
}}
 QLabel#currencyExchangeFieldLabel {{
 color: {t.MUTED}; font-weight: 800;
 }}
 QLabel#currencyExchangeRowLabel {{
 color: {t.MUTED}; font-size: 11px; font-weight: 650;
 }}
QFrame#currencyExchangeRuleHeader {{
background: {t.PANEL_2}; border: none; border-radius: 6px;
min-height: 24px; max-height: 24px;
}}
        QLabel#currencyExchangeRuleHeaderLabel {{
            color: {t.MUTED}; font-size: 12px; font-weight: 800;
        }}
QFrame#currencyExchangeRuleRow {{
background: {t.PANEL}; border: none; border-radius: 6px;
min-height: 38px;
}}
QFrame#currencyExchangeRuleRow:hover {{
background: #FFF7ED;
}}
        QLabel#currencyExchangeRuleIndex {{
            color: {t.TEXT}; font-weight: 800;
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
        }}
        QWidget#currencyExchangeSideBox {{
            background: transparent; border: none;
        }}
QWidget#currencyExchangeRows QLineEdit#currencyExchangeAmountEdit,
QWidget#currencyExchangeRows QComboBox#currencyExchangeTypeCombo,
QWidget#currencyExchangeRows QLineEdit#currencyExchangeCustomEdit {{
min-height: 32px; max-height: 34px;
}}
QWidget#currencyExchangeRows QComboBox#currencyExchangeTypeCombo {{
padding-right: 22px;
}}
QWidget#currencyExchangeRows QComboBox#currencyExchangeTypeCombo::drop-down {{
width: 20px; border-left: 1px solid {t.LINE_SOFT}; background: {t.PANEL_2};
border-top-right-radius: 5px; border-bottom-right-radius: 5px;
}}
QWidget#currencyExchangeRows QComboBox#currencyExchangeTypeCombo::drop-down:hover {{
background: #FFF7ED; border-left-color: #FDBA74;
}}
QWidget#currencyExchangeRows QComboBox#currencyExchangeTypeCombo::drop-down:pressed {{
background: #FED7AA; border-left-color: {t.BRAND};
}}
QGroupBox#currencyTableBox {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
margin-top: 8px; padding: 14px 8px 8px 8px;
}}
QGroupBox#currencyTableBox::title {{
color: {t.MUTED}; background: transparent; border: none; border-radius: 0px;
padding: 1px 6px; font-weight: 800;
}}
        QLabel#currencyRowTitleLabel {{
            color: {t.TEXT}; font-weight: 800;
        }}
QLabel#currencyCellLabel {{
color: {t.TEXT}; background: transparent;
border: 1px solid transparent; border-radius: 7px;
font-weight: 800; padding: 0 5px;
}}
QLabel#currencyCellLabel[currencyCellRole="accent"] {{
color: #92400E; background: transparent; border-color: transparent;
font-weight: 800;
}}
QLabel#currencyCellLabel[currencyCellRole="display"] {{
color: {t.MUTED}; background: {t.PANEL_2}; border-color: {t.LINE_SOFT}; font-weight: 700;
}}
QWidget#currencyTokenGrid {{
background: transparent; border: 1px solid transparent; border-radius: 8px;
}}
        QWidget#basicSettingsBodyScroll {{
            background: transparent; border: none;
        }}
        QLabel#basicPageTitleRow {{
            color: {t.TEXT};
        }}
        QLabel#pageDesc {{
            color: {t.MUTED};
        }}
        QLabel#basicRootTitle {{
            color: {t.TEXT}; font-size: 13px; font-weight: 800;
        }}
        QFrame#basicRootBox[basicWorkbenchMode="true"] {{
            background: {t.PANEL};
            border-color: {t.LINE_SOFT};
            padding: 8px;
        }}
        QFrame#basicRootBox[basicWorkbenchMode="true"] QLineEdit#basicRootEdit {{
            min-height: 32px;
        }}
        QFrame#basicRootBox[basicWorkbenchMode="true"] QLabel#basicRootStatus {{
            color: {t.MUTED};
            font-size: 12px;
        }}
QFrame#basicRootBox QPushButton#basicRootBrowseButton {{
min-width: 56px; min-height: 30px;
}}
        QTabWidget#basicSettingsTabs::pane {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px; margin-top: 4px;
        }}
QTabWidget#basicSettingsTabs QTabBar::tab {{
min-height: 28px; min-width: 68px; padding: 5px 11px;
            background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 7px;
            margin-right: 6px;
        }}
        QTabWidget#basicSettingsTabs QTabBar::tab:hover {{
            background: #FFF7ED; color: #92400E; border-color: #FDBA74;
        }}
        QTabWidget#basicSettingsTabs QTabBar::tab:selected {{
            background: #FFF7ED; color: #92400E; border-color: {t.BRAND};
        }}
QTableWidget#basicSearchTable {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
        }}
QWidget#basicSearchToolbar {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#basicSearchInputRow {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#basicSearchScopeOptions {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QFrame#basicSearchSummaryBar {{
background: transparent; border: none;
}}
QLabel#basicSearchSummaryPill {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 7px;
font-weight: 700; padding: 0 8px;
}}
QLabel#basicSearchSummaryPill[summaryRole="path"],
QLabel#basicSearchSummaryPill[summaryRole="dedup"] {{
color: {t.TEXT};
}}
QLabel#basicSearchSummaryPill[summaryRole="scope"] {{
background: {t.PANEL_2}; color: {t.TEXT}; border-color: {t.LINE_SOFT};
}}
QWidget#basicSearchScopeOptions QCheckBox[searchScopeOption="true"] {{
color: {t.MUTED}; font-weight: 600; border-radius: 4px; padding: 2px 6px;
}}
QWidget#basicSearchScopeOptions QCheckBox[searchScopeOption="true"]:hover {{
background: {t.PANEL_2}; color: {t.TEXT};
}}
QWidget#basicSearchScopeOptions QCheckBox[searchScopeOption="true"]:checked {{
background: {t.PANEL_2}; color: {t.TEXT}; font-weight: 650;
}}
QWidget#basicSearchScopeOptions QCheckBox[searchScopeOption="true"]::indicator {{
width: 16px; height: 16px; border-radius: 4px; border: 1px solid {t.LINE}; background: {t.PANEL};
}}
QWidget#basicSearchScopeOptions QCheckBox[searchScopeOption="true"]::indicator:checked {{
background: {t.BRAND}; border-color: #B45309;
}}
QStackedWidget#basicSearchResultsStack {{
background: transparent; border: none;
}}
 QFrame#basicSearchEmptyPanel {{
 background: transparent; border: none; border-radius: 0px;
 }}
        QLabel#basicSearchEmptyTitle {{
            color: {t.TEXT}; font-size: 17px; font-weight: 650;
        }}
        QLabel#basicSearchEmptyDetail {{
            color: {t.MUTED}; font-size: 12px;
        }}
        QFrame#basicSearchEmptyPanel[searchState="busy"] QLabel#basicSearchEmptyTitle {{
            color: {t.BRAND_2};
        }}
        QFrame#basicSearchEmptyPanel[searchState="error"] QLabel#basicSearchEmptyTitle {{
            color: #ff8b8b;
        }}
        QLabel#basicSearchPanelTitle,
        QFrame#quickPathPanel QLabel {{
            color: {t.TEXT}; font-size: 13px; font-weight: 800;
        }}
        QScrollArea#quickPathScroll {{
            background: transparent; border: none;
        }}
        QScrollArea#quickPathScroll QWidget {{
            background: transparent;
        }}
QFrame#quickPathPanel QPushButton#quickPathButton {{
min-height: 24px; max-height: 24px; padding-left: 8px; padding-right: 8px; text-align: left;
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-bottom-color: {t.LINE_SOFT}; border-radius: 0px;
}}
QFrame#quickPathPanel QPushButton#quickPathButton:hover {{
background: #FFF7ED; border-color: #FDBA74; color: #92400E; border-radius: 7px;
}}
QLabel#mapPageTitle {{
color: {t.TEXT}; font-size: 14px; font-weight: 800;
}}
        QLabel#mapPageSubtitle {{
            color: {t.MUTED}; font-size: 12px;
        }}
 QScrollArea#mapEditorPanel {{
 background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QScrollArea#mapEditorPanel QScrollBar::handle:vertical {{
background: #CBD5E1; border-radius: 4px; min-height: 28px;
}}
QScrollArea#mapEditorPanel QScrollBar::handle:vertical:hover {{
 background: #CBD5E1;
}}
QScrollArea#mapEditorPanel QScrollBar::add-page:vertical,
QScrollArea#mapEditorPanel QScrollBar::sub-page:vertical {{
background: transparent;
}}
QWidget#mapEditorBody {{
background: {t.PANEL};
}}
        QFrame#mapSectionFrame {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
        }}
QLabel#mapSectionTitle {{
color: {t.TEXT}; font-size: 13px; font-weight: 800;
padding-bottom: 0;
}}
        QWidget#mapSectionBody {{
            background: transparent; border: none;
        }}
        QLabel#mapStatusLabel {{
            color: {t.MUTED}; font-weight: 650;
        }}
QLabel#mapListHint {{
color: {t.MUTED}; font-size: 12px; font-weight: 650; padding: 0 4px;
}}
QFrame#mapListFooter {{
background: transparent; border: none; padding-top: 0px;
}}
 QWidget#mapSettingsPage QWidget#mapListSearchRow {{
 background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QListWidget#mapListWidget {{
background: transparent; border: none; border-radius: 8px;
padding: 2px;
}}
        QListWidget#mapListWidget::item {{
            min-height: 26px; border-radius: 6px; padding-left: 8px; padding-right: 8px;
            color: {t.TEXT};
        }}
QListWidget#mapListWidget::item:hover {{
  background: {t.PANEL_2}; color: {t.TEXT};
}}
QListWidget#mapListWidget::item:selected,
QListWidget#mapListWidget::item:selected:!active,
QListWidget#mapListWidget::item:selected:inactive {{
  background: {t.PANEL_2}; color: {t.TEXT};
}}
        QListWidget#mapListWidget QScrollBar:horizontal {{
            height: 0px;
        }}
        QFrame#memberAccountsPanel, QFrame#memberActionsPanel {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
        QFrame#microConfigHeader {{
            background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
        }}
QLabel#microHeaderLabel {{ color: {t.MUTED}; font-weight: 800; padding: 0 2px; }}
QFrame#microConfigListPanel, QFrame#microConfigEditorPanel {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
}}
QLabel#microCountBadge {{
background: transparent;
border: none;
border-radius: 0px;
color: {t.MUTED};
font-weight: 650;
padding: 0 6px;
}}
QPushButton#microRefreshStatusButton {{
min-height: 22px; max-height: 22px; min-width: 58px; max-width: 58px;
background: {t.PANEL_2};
border: 1px solid {t.LINE};
color: {t.TEXT};
font-weight: 750;
}}
QPushButton#microRefreshStatusButton:hover {{
background: #FFF7ED;
border-color: #FDBA74;
color: #92400E;
}}
        QLabel#pageTitle {{
            color: #e8eff8;
            font-size: 16px;
            font-weight: 800;
        }}
        QWidget#microTemplateActions,
        QScrollArea#microConfigEditorScroll, QWidget#microConfigEditorBody,
        QWidget#microPrimaryActions, QWidget#microToolActions,
        QWidget#microVisibilityActions, QFrame#microConfigForm {{
            background: transparent; border: none;
        }}
QWidget#microPrimaryActions {{
background: {t.PANEL};
border: 1px solid {t.LINE_SOFT};
border-radius: 8px;
padding: 6px;
}}
QFrame#microActionSection {{
background: transparent; border: none; border-radius: 0;
}}
QLabel#microActionSectionLabel {{
background: transparent; border: none; color: #92400E; font-weight: 850; padding: 0 2px;
}}
QWidget#microToolActions, QWidget#microVisibilityActions {{
background: transparent;
border: none;
border-radius: 8px;
padding: 4px 0;
}}
QWidget#microPrimaryActions QPushButton,
QWidget#microToolActions QPushButton,
QWidget#microVisibilityActions QPushButton {{
min-height: 28px;
max-height: 30px;
font-weight: 750;
border: 1px solid {t.LINE_SOFT};
background: {t.PANEL};
color: {t.TEXT};
border-radius: 7px;
}}
QWidget#microToolActions QPushButton:hover,
QWidget#microVisibilityActions QPushButton:hover {{
background: #FFF7ED;
border-color: #FDBA74;
color: #92400E;
}}
QPushButton[microActionTone="primary"] {{
min-height: 32px;
background: {t.BRAND};
border: 1px solid #B45309;
color: #ffffff;
font-weight: 850;
}}
QPushButton[microActionTone="success"] {{
background: #ECFDF3;
border-color: #22C55E;
color: #047857;
}}
QPushButton[microActionTone="danger"] {{
background: #FEF3F2;
color: #B42318;
border-color: #FDA29B;
}}
QFrame#dbConnectionPanel, QFrame#dbWorkspacePanel {{
 background: {t.PANEL};
 border: 1px solid {t.LINE_SOFT};
 border-radius: 6px;
}}
        QFrame#websiteRootPanel {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
            padding: 10px;
        }}
        QFrame#websiteRootBar, QWidget#websiteToolbar {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
            padding: 10px;
        }}
        QFrame#websiteWorkspacePanel,
        QWidget#websiteSitePanel,
        QWidget#websiteContentPanel,
        QFrame#websiteVersionPanel,
        QFrame#websiteQqPanel,
        QFrame#websiteDropPanel,
        QFrame#websiteOutputPanel {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
        QFrame#websiteOutputPanel {{
            padding: 8px 10px;
        }}
QWidget#dbBottomActionBar {{
 background: {t.PANEL};
 border: 1px solid {t.LINE_SOFT};
 border-radius: 10px;
}}
        QLabel#websiteStatusLabel {{
            color: {t.MUTED}; font-weight: 650;
        }}
        QProgressBar#websiteProgress {{
            min-height: 26px; max-height: 26px;
        }}
        QTabWidget#websiteTabs {{
            background: transparent; border: none;
        }}
        QTabWidget#websiteTabs::pane {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
        QLabel#dbStatusLabel {{
            color: #9bdcff; font-weight: 750;
        }}
QLabel#dbWelcomeTitle {{
 color: {t.TEXT};
 font-size: 16px;
 font-weight: 800;
}}
QLabel#dbWelcomeIntro, QLabel#dbWelcomeHint {{
color: {t.MUTED};
}}
QLabel#dbWelcomeCapabilityHeading {{
color: {t.TEXT};
font-weight: 850;
}}
QLabel#dbWelcomeCapabilityTitle {{
color: #92400E;
font-weight: 800;
}}
QLabel#dbWelcomeCapabilityDesc {{
color: {t.MUTED};
font-size: 12px;
font-weight: 650;
}}
QLabel#dbWelcomeStatusPill {{
min-width: 64px;
padding: 5px 10px;
border-radius: 999px;
background: #FFF7ED;
border: 1px solid #FDBA74;
color: {t.MUTED};
font-weight: 650;
}}
QFrame#dbWelcomeCard {{
background: {t.PANEL};
border: 1px solid {t.LINE_SOFT};
border-left: 2px solid {t.BRAND};
border-radius: 10px;
}}
QFrame#dbWelcomeCapabilityPanel {{
background: {t.PANEL};
border: 1px solid {t.LINE_SOFT};
border-radius: 10px;
}}
QWidget#dbWelcomeCapabilityItem {{
background: transparent;
border: none;
}}
QWidget#dbWelcomeTab {{
background: transparent;
}}
QFrame#dbWelcomeCard {{
background: {t.PANEL};
border: 1px solid {t.LINE_SOFT};
border-radius: 10px;
}}
QLabel#dbWelcomeTitle {{
color: {t.TEXT};
font-size: 13px;
font-weight: 850;
}}
QLabel#dbWelcomeIntro {{
color: {t.MUTED};
font-weight: 650;
}}
QLabel#dbWelcomeStatusPill {{
color: #92400E;
background: #FEF3C7;
border: 1px solid #B45309;
border-radius: 6px;
font-weight: 850;
}}
QFrame#dbWelcomeStepsPanel {{
background: {t.PANEL_2};
border: 1px solid {t.LINE_SOFT};
border-radius: 8px;
}}
QLabel#dbWelcomeStep {{
color: {t.MUTED};
font-size: 12px;
font-weight: 650;
}}
QWidget#dbWelcomeActionBar {{
background: transparent;
border: none;
}}
QTabWidget#dbWorkspaceTabs {{
background: transparent; border: none;
}}
QTabWidget#dbWorkspaceTabs::pane {{
 background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 10px;
}}
QTabWidget#dbWorkspaceTabs QTabBar::tab {{
 min-height: 24px; min-width: 68px; padding: 3px 9px;
 background: {t.PANEL_2};
 border: 1px solid {t.LINE_SOFT};
 color: {t.MUTED};
 font-weight: 750;
}}
QTabWidget#dbWorkspaceTabs QTabBar::tab:selected {{
 background: {t.PANEL_2};
 border-color: {t.LINE};
 color: {t.TEXT};
}}
QTableWidget#dbDataTable {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
alternate-background-color: {t.PANEL_2}; color: {t.TEXT};
selection-background-color: #E7EAEE; selection-color: {t.TEXT};
}}
        QTableWidget#dbDataTable::item {{
            color: {t.TEXT};
        }}
QTableWidget#dbDataTable::item:selected {{
background: #E7EAEE; color: {t.TEXT};
}}
QTableWidget#dbDataTable QHeaderView::section {{
background: {t.PANEL_2};
border: none;
border-bottom: 1px solid {t.LINE_SOFT};
color: {t.MUTED};
font-weight: 800;
}}
QPushButton#dbConnectionActionButton,
QPushButton[dbConnectionActionRole],
QWidget#dbBottomActionBar QPushButton {{
min-height: 28px; max-height: 28px; font-weight: 600;
}}
QPushButton#dbWelcomeConnectButton {{
min-width: 76px;
background: {t.BRAND};
border: 1px solid #B45309;
color: #ffffff;
font-weight: 650;
}}
QPushButton#dbWelcomeBrowseButton {{
min-width: 52px;
background: {t.PANEL_2};
border-color: {t.LINE_SOFT};
color: {t.TEXT};
}}
QPushButton#dbTableActionButton {{
min-height: 28px;
padding-left: 9px;
padding-right: 9px;
 background: {t.PANEL};
 border: 1px solid {t.LINE};
 color: {t.TEXT};
 font-weight: 600;
}}
QPushButton#dbTableActionButton:hover {{
 border-color: {t.LINE};
 background: {t.PANEL_2};
}}
QWidget#dbTableActionGroup {{
 background: {t.PANEL_2};
 border: 1px solid {t.LINE_SOFT};
 border-radius: 6px;
 padding: 6px;
}}
QWidget#memberDirectoryBar QPushButton {{
min-height: 28px; max-height: 28px; min-width: 52px; max-width: 56px; font-weight: 700;
}}
QWidget#cdkManagerPage QWidget#cdkDirectoryBar QPushButton,
QWidget#cdkManagerPage QWidget#cdkTypeBar QPushButton {{
 min-height: 26px; max-height: 26px; min-width: 70px; max-width: 70px; font-weight: 600;
}}
QWidget#cdkManagerPage QWidget#cdkQueryBar QPushButton {{
 min-height: 26px; max-height: 26px; font-weight: 600;
}}
        QWidget#itemEditorActions, QFrame#callActionBar,
        QFrame#optActionBar, QFrame#groupActionBar, QFrame#deleteActionBar,
        QFrame#deletePickBar, QFrame#overallOptActionBar,
        QFrame#currencyExchangeHeader {{
            background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
        }}
        QWidget#itemEditorActions QPushButton,
        QFrame#callActionBar QPushButton,
        QFrame#optActionBar QPushButton,
        QFrame#groupActionBar QPushButton,
        QFrame#deleteActionBar QPushButton,
        QFrame#deletePickBar QPushButton,
QFrame#overallOptActionBar QPushButton,
QFrame#currencyExchangeHeader QPushButton,
QGroupBox#memberExpiryBox QPushButton,
QGroupBox#memberCoreActionsBox QPushButton,
QGroupBox#memberHelpBox QPushButton,
QWidget#cdkManagerPage QGroupBox#cdkGenerationBox QPushButton {{
    min-height: 30px; max-height: 30px; font-weight: 650;
}}
        QGroupBox#memberExpiryBox QPushButton,
        QGroupBox#memberCoreActionsBox QPushButton,
        QGroupBox#memberHelpBox QPushButton {{
            min-height: 34px;
        }}
        QWidget#itemEditorActions QPushButton,
        QFrame#itemTemplatePanel QPushButton {{
            min-height: 34px; font-weight: 725;
        }}
        QGroupBox#memberExpiryBox, QGroupBox#memberCoreActionsBox, QGroupBox#memberHelpBox {{
            margin-top: 10px; padding-top: 12px;
        }}
        QGroupBox#memberExpiryBox::title,
        QGroupBox#memberCoreActionsBox::title,
        QGroupBox#memberHelpBox::title {{
            subcontrol-origin: margin; left: 10px; padding: 0 4px;
        }}
        QWidget#itemEditorActions QPushButton[buttonRole="danger"],
        QFrame#callActionBar QPushButton[buttonRole="danger"],
        QFrame#optActionBar QPushButton[buttonRole="danger"],
        QFrame#groupActionBar QPushButton[buttonRole="danger"],
        QFrame#deleteActionBar QPushButton[buttonRole="danger"],
        QFrame#deletePickBar QPushButton[buttonRole="danger"],
QFrame#overallOptActionBar QPushButton[buttonRole="danger"],
QGroupBox#memberCoreActionsBox QPushButton[buttonRole="danger"] {{
background: #FEF3F2; color: #B42318; border-color: #FDA29B;
}}
QTableWidget#itemPreviewTable {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
alternate-background-color: #FAFBFC;
color: {t.TEXT};
gridline-color: {t.LINE_SOFT};
selection-background-color: #FFF7ED;
selection-color: #92400E;
}}
QTableWidget#itemPreviewTable::item {{
padding-left: 8px; padding-right: 8px;
border-bottom: 1px solid {t.LINE_SOFT};
}}
QTableWidget#itemPreviewTable::item:selected {{
background: #FFF7ED; color: #92400E;
}}
QTableWidget#itemPreviewTable QHeaderView::section {{
background: {t.PANEL_2};
color: {t.MUTED};
border: none;
border-bottom: 1px solid {t.LINE};
font-weight: 850;
}}
QWidget#itemEditorActions {{
background: {t.PANEL_2};
border: 1px solid {t.LINE_SOFT};
border-radius: 8px;
padding: 5px;
}}
QWidget#itemEditorActions QPushButton {{
min-height: 28px;
max-height: 28px;
padding-left: 8px;
padding-right: 8px;
border-radius: 7px;
background: {t.PANEL_2};
border: 1px solid {t.LINE_SOFT};
color: {t.MUTED};
font-size: 12px;
font-weight: 700;
}}
QWidget#itemEditorActions QPushButton[itemEditorActionRole="reload"],
QWidget#itemEditorActions QPushButton[itemEditorActionRole="preview"],
QWidget#itemEditorActions QPushButton[itemEditorActionRole="edit"],
QWidget#itemEditorActions QPushButton[itemEditorActionRole="addItem"],
QWidget#itemEditorActions QPushButton[itemEditorActionRole="editItem"],
QWidget#itemEditorActions QPushButton[itemEditorActionRole="importTxt"],
QWidget#itemEditorActions QPushButton[itemEditorActionRole="exportTxt"],
QWidget#itemEditorActions QPushButton[itemEditorActionRole="saveTemplate"] {{
color: {t.MUTED};
}}
QWidget#itemEditorActions QPushButton:hover {{
background: #FFF7ED;
border-color: #FDBA74;
color: #92400E;
}}
QWidget#itemEditorActions QPushButton[buttonRole="primary"] {{
min-height: 30px;
max-height: 30px;
min-width: 96px;
padding-left: 12px;
padding-right: 12px;
            background: {t.BRAND};
 border: 1px solid #B45309;
 color: #ffffff;
            font-weight: 850;
        }}
QWidget#itemEditorActions QPushButton[buttonRole="danger"] {{
background: #FFF7F5;
color: #B42318;
border-color: #FDA29B;
}}
QFrame#itemTemplatePanel QPushButton {{
min-height: 28px;
max-height: 28px;
padding-left: 8px;
padding-right: 8px;
font-size: 12px;
}}
        QListWidget#itemTemplateList {{
            background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 8px;
            outline: none; color: {t.TEXT};
        }}
QListWidget#itemTemplateList::item {{
min-height: 28px; padding: 3px 8px; border-radius: 6px; color: {t.TEXT};
}}
QListWidget#itemTemplateList::item:hover {{
background: #FFF7ED; color: #92400E;
}}
QListWidget#itemTemplateList::item:selected,
QListWidget#itemTemplateList::item:selected:!active {{
background: #FFF7ED; color: #92400E;
}}
        QTableWidget#memberAccountsTable {{
            background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 8px;
            alternate-background-color: {t.PANEL_2}; color: {t.TEXT};
 selection-background-color: #E7EAEE; selection-color: {t.TEXT};
        }}
        QTableWidget#memberAccountsTable::item {{
            color: {t.TEXT};
        }}
        QTableWidget#memberAccountsTable::item:selected {{
 background: #FFF7ED; color: #92400E;
        }}
        QTableWidget#memberAccountsTable QHeaderView::section {{
 color: {t.MUTED};
        }}
        QWidget#cdkManagerPage QTabWidget#cdkRecordsTabs {{
            background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 6px;
        }}
        QWidget#cdkManagerPage QTabWidget#cdkRecordsTabs::pane {{
            border: none;
        }}
QWidget#currencyExchangeHeader {{
padding: 6px;
}}
QWidget#currencyExchangeRows {{
background: {t.PANEL};
border: 1px solid {t.LINE};
border-radius: 8px;
padding: 5px;
}}
        QWidget#currencyExchangeActions {{
            background: transparent;
        }}
QWidget#currencyExchangeActions QPushButton {{
min-height: 28px; max-height: 28px;
}}
        QLabel#currencyExchangeFieldLabel {{
            color: {t.MUTED};
            font-size: 12px;
            font-weight: 650;
        }}
        QLabel#currencyExchangeRowLabel {{
            color: {t.MUTED};
            font-size: 11px;
            font-weight: 600;
        }}
QWidget#currencyExchangeRows QLineEdit,
QWidget#currencyExchangeRows QComboBox {{
min-height: 32px;
}}
        QWidget#currencyExchangeRows QLineEdit#currencyExchangeAmountEdit {{
            min-width: 64px; max-width: 96px;
        }}
        QWidget#currencyExchangeRows QComboBox#currencyExchangeTypeCombo {{
            min-width: 120px; max-width: 180px;
        }}
        QWidget#currencyExchangeRows QLineEdit#currencyExchangeCustomEdit {{
            min-width: 112px; max-width: 172px;
        }}
QPlainTextEdit#dropDetailLog {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
color: {t.MUTED};
}}
QWidget#dropRatePage QLabel#dropDetailMetaLabel {{
color: {t.MUTED}; font-weight: 850;
}}
QWidget#dropRatePage QLabel#dropDetailMetaValue {{
color: {t.MUTED}; font-weight: 650;
}}
QWidget#dropRatePage QLabel#dropPanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px;
padding-left: 2px; padding-right: 6px; font-weight: 650;
}}
QWidget#dropRatePage QLabel#dropDetailStatusBadge[badgeRole="info"] {{
background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; border-radius: 8px;
padding: 1px 8px; font-weight: 760;
}}
QWidget#dropRatePage QLabel#dropDetailStatusBadge[badgeRole="muted"] {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
padding: 1px 8px; font-weight: 760;
}}
QProgressBar#dropDetailProgress {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 7px;
min-height: 18px; max-height: 18px; text-align: center; color: {t.MUTED};
font-weight: 750;
}}
QProgressBar#dropDetailProgress::chunk {{
border-radius: 5px; background: #FFF7ED; border: none;
}}
        QScrollArea {{ background: transparent; border: none; }}
QScrollBar:vertical {{ width: 10px; background: transparent; }}
QScrollBar::handle:vertical {{ min-height: 32px; border-radius: 5px; background: #CBD5E1; }}
QScrollBar::handle:vertical:hover {{ background: #FDBA74; }}
QScrollBar::handle:vertical:pressed {{ background: {t.BRAND}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll QScrollBar:vertical {{
width: 6px; margin: 4px 0 4px 2px; background: transparent;
}}
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll QScrollBar::handle:vertical {{
min-height: 26px; border-radius: 3px; background: {t.LINE};
}}
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll QScrollBar::handle:vertical:hover {{
background: #CBD5E1;
}}
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll QScrollBar::add-line:vertical,
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll QScrollBar::sub-line:vertical {{
height: 0; background: transparent;
}}
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll QScrollBar::add-page:vertical,
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll QScrollBar::sub-page:vertical {{
background: transparent;
}}
QFrame[panelRole="statusbar"] {{ background: {t.CHROME}; border-top: 1px solid {t.LINE_SOFT}; }}
QFrame[panelRole="statusbar"] QFrame[panelRole="dock"],
QFrame[panelRole="statusbar"] QFrame[panelRole="dock-active"] {{
min-height: 26px; max-height: 28px; border-radius: 7px;
}}
QFrame[panelRole="statusbar"] QFrame#dockTabStatus {{
min-height: 2px; max-height: 2px; border-radius: 1px;
}}
QFrame[panelRole="statusbar"] QLabel[labelRole="dock-icon"],
QFrame[panelRole="statusbar"] QLabel[labelRole="dock-icon-active"] {{
min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;
border-radius: 5px; font-size: 8px;
}}
QFrame[panelRole="statusbar"] QLabel[labelRole="dock-title"],
QFrame[panelRole="statusbar"] QLabel[labelRole="dock-title-active"] {{
font-size: 9px; font-weight: 900; min-height: 10px; max-height: 11px;
}}
QFrame[panelRole="statusbar"] QFrame#dockLogDrawer QLabel[labelRole="dock-log-title"] {{
font-size: 10px; min-height: 12px;
}}
QFrame[panelRole="statusbar"] QFrame#dockLogDrawer QLabel[labelRole="dock-log-muted"] {{
font-size: 9px; min-height: 10px;
}}
QFrame#darkWorkbenchSidebar QLineEdit#sidebarSearchField,
        QFrame#darkWorkbenchSidebar QLabel#sidebarSearchField {{
        background: {t.PANEL}; border: 1px solid {t.LINE}; color: {t.TEXT};
        }}
        QFrame#darkWorkbenchSidebar QLineEdit#sidebarSearchField:focus {{
        background: #FFFBEB; border: 1px solid {t.BRAND};
        }}
QFrame#darkWorkbenchSidebar QFrame#sidebarGlobalTools {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel {{
min-height: 44px; max-height: 48px;
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-left: 2px solid {t.BRAND};
border-radius: 6px;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QLabel[labelRole="avatar"] {{
min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px; border-radius: 7px;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QLabel[labelRole="strong"] {{
font-size: 12px; font-weight: 900;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QLabel[labelRole="muted"] {{
font-size: 11px; color: {t.MUTED};
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QPushButton#accountLogoutButton {{
min-width: 18px; max-width: 18px; min-height: 18px; max-height: 18px;
padding: 0px; border-radius: 6px;
background: #FFF4E6; border: 1px solid #FDBA74; color: #9A3412;
font-size: 10px; font-weight: 850;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QPushButton#accountLogoutButton:hover {{
background: #FFE8CC; border-color: #F97316; color: #7C2D12;
}}
QFrame#darkWorkbenchSidebar QPushButton#sidebarGlobalToolButton {{
min-height: 22px; max-height: 22px; padding-left: 4px; padding-right: 4px;
background: {t.PANEL}; border: 1px solid {t.LINE}; color: {t.TEXT};
}}
        QFrame#darkWorkbenchSidebar QPushButton#sidebarGlobalToolButton:hover {{
        background: #FFF7ED; border-color: #FDBA74; color: #92400E;
        }}
        QFrame#darkWorkbenchSidebar QPushButton#sidebarGlobalToolButton[globalToolConfigured="true"] {{
        background: #FFF4E6; border-color: #F59E0B; color: #7C2D12;
        }}
        QFrame#darkWorkbenchSidebar QPushButton#sidebarGlobalToolButton[dropState="hover"] {{
        background: #FEF3C7; border: 1px dashed #D97706; color: #7C2D12;
        }}
QWidget#spawnSettingsPage QGroupBox#spawnBulkToolsBox,
QWidget#spawnSettingsPage QGroupBox#spawnMapToolsBox,
QWidget#spawnSettingsPage QGroupBox#spawnMonsterToolsBox,
QWidget#spawnSettingsPage QGroupBox#spawnScriptToolsBox {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#spawnSettingsPage QFrame#spawnRulesBox {{
background: {t.PANEL_2}; border: none; border-radius: 4px;
}}
QWidget#spawnSettingsPage QWidget#spawnBulkApplyRow {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
}}
QWidget#spawnSettingsPage QWidget#spawnMonsterActionRow {{
background: transparent; border: none; border-radius: 0;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar:vertical {{
width: 10px; background: transparent;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar:horizontal {{
height: 10px; background: transparent;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar::handle:vertical {{
min-height: 30px; border-radius: 5px; background: #CBD5E1;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar::handle:horizontal {{
min-width: 30px; border-radius: 5px; background: #CBD5E1;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar::handle:vertical:hover,
QWidget#spawnSettingsPage QTableWidget QScrollBar::handle:horizontal:hover {{
background: #AEB7C2;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar::handle:vertical:pressed,
QWidget#spawnSettingsPage QTableWidget QScrollBar::handle:horizontal:pressed {{
background: #87919D;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar::add-line:vertical,
QWidget#spawnSettingsPage QTableWidget QScrollBar::sub-line:vertical,
QWidget#spawnSettingsPage QTableWidget QScrollBar::add-line:horizontal,
QWidget#spawnSettingsPage QTableWidget QScrollBar::sub-line:horizontal {{
width: 0; height: 0; background: transparent;
}}
QWidget#spawnSettingsPage QTableWidget QScrollBar::add-page:vertical,
QWidget#spawnSettingsPage QTableWidget QScrollBar::sub-page:vertical,
QWidget#spawnSettingsPage QTableWidget QScrollBar::add-page:horizontal,
QWidget#spawnSettingsPage QTableWidget QScrollBar::sub-page:horizontal {{
background: transparent;
}}
QWidget#spawnSettingsPage QFrame#spawnToolsHeader {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; padding: 3px;
}}
QWidget#spawnSettingsPage QFrame#spawnConditionSummary {{
background: transparent; border: none;
}}
QWidget#spawnSettingsPage QLabel#spawnConditionPill {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT};
border-radius: 4px; padding-left: 5px; padding-right: 5px; font-size: 11px; font-weight: 600;
}}
QWidget#spawnSettingsPage QLabel#spawnConditionPill[summaryRole="operation"] {{
background: #FFF4E8; color: #8B3F08; border-color: #E8B181; font-weight: 650;
}}
QWidget#spawnSettingsPage QLabel#spawnPanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; padding-left: 2px; padding-right: 6px; font-weight: 650;
}}
QWidget#spawnSettingsPage QLabel#spawnPanelBadge[badgeRole="metric"] {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 1px 8px; color: {t.MUTED}; font-weight: 600;
}}
QWidget#scriptInjectPage QFrame#scriptTemplatePanel,
QWidget#scriptInjectPage QFrame#scriptEditorPanel {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
}}
QWidget#scriptInjectPage QFrame#scriptRootBar,
QWidget#scriptInjectPage QFrame#scriptEditorActionRow {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#scriptInjectPage QFrame#scriptEditorExecRow {{
background: {t.PANEL_2}; border: none; border-top: 1px solid {t.LINE_SOFT}; border-radius: 0px;
}}
QWidget#scriptInjectPage QFrame#scriptTemplateActions {{
background: transparent; border: none; border-top: 1px solid {t.LINE_SOFT}; border-radius: 0px;
}}
QWidget#scriptInjectPage QLabel#pageTitle {{
color: {t.TEXT}; font-weight: 800;
}}
QWidget#scriptInjectPage QLabel#pageDesc {{
color: {t.MUTED}; font-weight: 500;
}}
QWidget#scriptInjectPage QLineEdit,
QWidget#scriptInjectPage QPlainTextEdit,
QWidget#scriptInjectPage QListWidget#itemTemplateList,
QWidget#scriptInjectPage QTableWidget#scriptPreviewTable {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
}}
QWidget#scriptInjectPage QListWidget#itemTemplateList {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
}}
QWidget#scriptInjectPage QListWidget#itemTemplateList::item:selected,
QWidget#scriptInjectPage QTableWidget#scriptPreviewTable::item:selected {{
background: #E9EDF2; color: {t.TEXT};
}}
QWidget#scriptInjectPage QTableWidget#scriptPreviewTable QHeaderView::section {{
background: {t.PANEL_2}; color: {t.TEXT}; border: none; border-bottom: 1px solid {t.LINE_SOFT};
}}
QWidget#scriptInjectPage QTableWidget#scriptPreviewTable::item {{
background: {t.PANEL}; color: {t.TEXT};
}}
QWidget#scriptInjectPage QTableWidget#scriptPreviewTable::item:alternate {{
background: {t.PANEL_2}; color: {t.TEXT};
}}
QWidget#scriptInjectPage QLabel#scriptTargetScope {{
color: {t.TEXT}; font-weight: 600;
}}
QWidget#scriptInjectPage QLabel#scriptInjectStatus {{
color: {t.MUTED}; font-weight: 600; padding-left: 8px; padding-right: 8px;
}}
QWidget#storeSettingsPage QFrame#storeWorkspacePanel {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#storeSettingsPage QFrame#storeWorkspaceHeader,
QWidget#storeSettingsPage QFrame#storeGenerateBar {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#storeSettingsPage QGroupBox#storePathParamsBox,
QWidget#storeSettingsPage QGroupBox#storeScriptParamsBox {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#storeSettingsPage QGroupBox#storeScriptParamsBox {{
background: {t.PANEL}; border-color: {t.LINE_SOFT};
}}
QWidget#storeSettingsPage QFrame#storePreviewPanel,
QWidget#storeSettingsPage QFrame#storeFlowPanel {{
background: {t.PANEL_2}; border: none; border-radius: 6px;
}}
QWidget#storeSettingsPage QLabel#storePreviewTitle {{
background: transparent; border: none; color: {t.MUTED}; font-weight: 600;
}}
QWidget#storeSettingsPage QLabel#storePreviewPill {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 1px 8px; color: {t.MUTED}; font-weight: 600;
}}
QWidget#storeSettingsPage QLabel#storePreviewPill[storePreviewRole="primary"] {{
background: {t.PANEL_2}; border-color: {t.LINE_SOFT}; color: {t.TEXT}; font-weight: 600;
}}
QWidget#storeSettingsPage QGroupBox#storePathParamsBox::title,
QWidget#storeSettingsPage QGroupBox#storeScriptParamsBox::title {{
subcontrol-origin: margin; subcontrol-position: top left; left: 8px; padding: 1px 4px;
background: transparent; color: {t.MUTED}; border: none; border-radius: 0; font-weight: 600;
}}
QWidget#storeSettingsPage QSplitter#storeWorkspaceSplitter::handle {{
background: {t.LINE_SOFT}; width: 1px; margin: 6px 6px;
}}
QWidget#storeSettingsPage QLineEdit {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
}}
        QWidget#storeSettingsPage QLineEdit:focus {{
        background: #FFFBEB; border-color: {t.BRAND};
        }}
        QWidget#storeSettingsPage QPushButton {{
        background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
        }}
QWidget#storeSettingsPage QPushButton#storeConfigActionButton,
QFrame#storeGenerateBar QPushButton#storeConfigActionButton {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px; font-weight: 600; padding-left: 6px; padding-right: 6px;
}}
QWidget#storeSettingsPage QPushButton[storeConfigActionRole="browseCommon"],
QFrame#storeGenerateBar QPushButton[storeConfigActionRole="browseCommon"] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; font-weight: 600;
}}
        QWidget#storeSettingsPage QPushButton[storeGenerateActionRole="generate"],
        QWidget#storeSettingsPage QPushButton[buttonRole="primary"] {{
        background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309; font-weight: 650;
        }}
QWidget#storeSettingsPage QPushButton[buttonRole="danger"] {{
background: #FEF3F2; color: #B42318; border: 1px solid #7F1D1D;
}}
QWidget#storeSettingsPage QPushButton[storeConfigActionRole="delete"],
QFrame#storeGenerateBar QPushButton[storeConfigActionRole="delete"] {{
background: #FFF7F5; color: #B42318; border: 1px solid #FCA5A5;
}}
QWidget#storeSettingsPage QProgressBar#storeGenerateProgress {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; text-align: center; min-height: 12px; max-height: 12px;
}}
QWidget#storeSettingsPage QProgressBar#storeGenerateProgress::chunk {{
background: {t.BRAND}; border-radius: 5px;
}}
QWidget#storeSettingsPage QPushButton:hover {{
background: {t.PANEL_2}; color: {t.TEXT}; border-color: {t.LINE};
}}
QWidget#storeSettingsPage QPushButton#storeConfigActionButton:hover,
QFrame#storeGenerateBar QPushButton#storeConfigActionButton:hover {{
background: {t.PANEL_2}; color: {t.TEXT}; border-color: {t.LINE};
}}
QWidget#storeSettingsPage QPushButton[storeGenerateActionRole="generate"]:hover {{
background: #C95F00; color: #ffffff; border-color: #9A4700;
}}
QWidget#storeSettingsPage QPushButton[storeConfigActionRole="delete"]:hover,
QFrame#storeGenerateBar QPushButton[storeConfigActionRole="delete"]:hover {{
background: #FEF3F2; color: #991B1B; border-color: #EF4444;
}}
QWidget#varQueryPage QFrame#varScanPanel,
QWidget#varQueryPage QFrame#varBrowserPanel,
QWidget#varQueryPage QFrame#varDetailPanel {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#varQueryPage QFrame#varScanPanel {{
background: {t.PANEL_2};
}}
QWidget#varQueryPage QFrame#varBrowserHeader {{
background: transparent; border: none; border-bottom: 1px solid {t.LINE_SOFT}; border-radius: 0px; padding: 2px 0 5px 0;
}}
QWidget#varQueryPage QLabel#varPanelBadge {{
background: transparent; color: {t.MUTED}; border: none; padding: 0 2px; font-weight: 700;
}}
QWidget#varQueryPage QGroupBox#varTypeBox,
QWidget#varQueryPage QGroupBox#varUsedBox {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; margin: 0px; padding: 0px;
}}
QWidget#varQueryPage QGroupBox#varTypeBox::title,
QWidget#varQueryPage QGroupBox#varUsedBox::title {{
background: transparent; border: none; padding: 0px;
}}
QWidget#varQueryPage QLabel#varUsedListTitle {{
background: transparent; color: {t.TEXT}; border: none; font-weight: 800; padding: 4px 2px 2px 2px;
}}
QWidget#varQueryPage QTreeWidget#varTypeTree,
QWidget#varQueryPage QTableWidget#varUsedTable {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
alternate-background-color: {t.PANEL_2}; gridline-color: {t.LINE_SOFT}; outline: none;
}}
QWidget#varQueryPage QTreeWidget#varTypeTree::item {{
min-height: 24px; border-left: 3px solid transparent; padding: 0 5px;
}}
QWidget#varQueryPage QTreeWidget#varTypeTree::item:has-children {{
background: {t.PANEL_2}; color: {t.MUTED}; font-weight: 800;
}}
QWidget#varQueryPage QTreeWidget#varTypeTree::item:hover,
QWidget#varQueryPage QTableWidget#varUsedTable::item:hover {{
background: #EEF1F4; color: {t.TEXT};
}}
QWidget#varQueryPage QTreeWidget#varTypeTree::item:selected,
QWidget#varQueryPage QTableWidget#varUsedTable::item:selected {{
background: #E7EAEE; color: {t.TEXT}; border-left: 3px solid #667085; font-weight: 800;
}}
QWidget#varQueryPage QTreeWidget#varTypeTree::branch:hover {{ background: #EEF1F4; }}
QWidget#varQueryPage QTreeWidget#varTypeTree::branch:selected {{ background: #E7EAEE; }}
QWidget#varQueryPage QTreeWidget#varTypeTree:focus,
QWidget#varQueryPage QTableWidget#varUsedTable:focus {{
border: 1px solid #98A2B3;
}}
QWidget#varQueryPage QLabel#varUsedEmptyState {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px dashed {t.LINE}; border-radius: 4px; padding: 12px;
}}
QWidget#varQueryPage QLabel#varScanStatus {{
color: {t.MUTED}; font-weight: 650;
}}
QWidget#varQueryPage QProgressBar#varScanProgress {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; text-align: center; min-height: 12px; max-height: 12px;
}}
QWidget#varQueryPage QProgressBar#varScanProgress::chunk {{
background: {t.BRAND}; border-radius: 5px;
}}
QWidget#varQueryPage QFrame#varDetailSummaryPanel {{
background: transparent; border: none; border-top: 1px solid {t.LINE_SOFT}; border-radius: 0px;
}}
QWidget#varQueryPage QLabel#varDetailSummaryTitle {{
color: {t.MUTED}; font-weight: 750;
}}
QWidget#varQueryPage QLabel#varDetailSummaryValue {{
color: {t.TEXT};
}}
QWidget#varQueryPage QTreeWidget QScrollBar::handle:vertical,
QWidget#varQueryPage QTableWidget QScrollBar::handle:vertical {{
background: #CBD5E1; border-radius: 4px; min-height: 28px;
}}
QWidget#varQueryPage QTreeWidget QScrollBar::handle:vertical:hover,
QWidget#varQueryPage QTableWidget QScrollBar::handle:vertical:hover {{
background: #98A2B3;
}}
QWidget#varQueryPage QTreeWidget QScrollBar::add-page:vertical,
QWidget#varQueryPage QTreeWidget QScrollBar::sub-page:vertical,
QWidget#varQueryPage QTableWidget QScrollBar::add-page:vertical,
QWidget#varQueryPage QTableWidget QScrollBar::sub-page:vertical {{
background: transparent;
}}
QWidget#varQueryPage QTableWidget {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
alternate-background-color: {t.PANEL_2}; gridline-color: {t.LINE_SOFT};
}}
QWidget#varQueryPage QTableWidget#varDetailTable::item:selected {{
background: #E7EAEE; color: {t.TEXT};
}}
QWidget#varQueryPage QTableWidget QHeaderView::section {{
background: {t.PANEL_2}; color: {t.TEXT}; border: none; border-bottom: 1px solid {t.LINE_SOFT};
}}
QWidget#recycleGeneratePage QFrame#recycleTablePanel,
QWidget#recycleGeneratePage QWidget#recycleTableActions,
QWidget#recycleGeneratePage QFrame#recycleScriptActionRow,
QWidget#recycleGeneratePage QWidget#recycleScriptActions {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptHeader {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#recycleGeneratePage QLabel#recyclePanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; padding-left: 2px; padding-right: 6px; font-weight: 650;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptHeader QLabel#recyclePanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; padding: 0px 4px; font-size: 12px; font-weight: 650;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptHeader QLabel#recyclePanelBadge[badgeRole="ready"] {{
background: #EEF1F4; color: {t.TEXT}; border: 1px solid #AEB7C2; border-radius: 4px;
padding: 1px 8px; font-weight: 600;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptHeader QLabel#recyclePanelBadge[badgeRole="warn"] {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 1px 8px; font-weight: 600;
}}
QWidget#recycleGeneratePage QLabel#recyclePanelBadge[badgeRole="metric"] {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 1px 8px; color: {t.MUTED}; font-weight: 600;
}}
QWidget#recycleGeneratePage QLineEdit {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE};
}}
QWidget#recycleGeneratePage QFrame#recycleScriptPanel {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptPanel QPlainTextEdit {{
background: {t.BG}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#recycleGeneratePage QPlainTextEdit#recycleScriptPreviewEdit {{
font-family: Consolas, "Courier New", monospace; font-size: 12px;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptPanel QPlainTextEdit QScrollBar::handle:vertical {{
background: #CBD5E1; border-radius: 4px; min-height: 28px;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptPanel QPlainTextEdit QScrollBar::handle:vertical:hover {{
background: #FDBA74;
}}
QWidget#recycleGeneratePage QFrame#recycleScriptPanel QPlainTextEdit QScrollBar::add-page:vertical,
QWidget#recycleGeneratePage QFrame#recycleScriptPanel QPlainTextEdit QScrollBar::sub-page:vertical {{
background: transparent;
}}
QWidget#recycleGeneratePage QTableWidget {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE};
alternate-background-color: {t.PANEL_2}; gridline-color: {t.LINE_SOFT};
}}
        QWidget#recycleGeneratePage QTableWidget QHeaderView::section {{
        background: {t.PANEL_2}; color: {t.TEXT}; border-bottom: 1px solid {t.LINE_SOFT};
        }}
        QWidget#recycleGeneratePage QTableWidget::item:selected {{
        background: #FFF7ED; color: #92400E;
        }}
        QWidget#recycleGeneratePage QPushButton {{
        background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE};
        }}
QWidget#recycleGeneratePage QWidget#recycleTableActions {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#recycleGeneratePage QPushButton#recycleTableActionButton {{
min-height: 26px; max-height: 26px; background: {t.PANEL}; color: {t.TEXT};
border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600; padding: 0 5px;
}}
QWidget#recycleGeneratePage QPushButton#recycleTableActionButton[recycleTableTone="primary"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE};
}}
QWidget#recycleGeneratePage QPushButton#recycleTableActionButton[recycleTableTone="emphasis"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE};
}}
QWidget#recycleGeneratePage QPushButton#recycleTableActionButton[recycleTableTone="danger"] {{
background: #FFF7F5; color: #B42318; border-color: #FCA5A5;
}}
QWidget#recycleGeneratePage QPushButton#recycleTableActionButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#recycleGeneratePage QPushButton#recycleTableActionButton[recycleTableTone="danger"]:hover {{
background: #FEF3F2; color: #991B1B; border-color: #EF4444;
}}
QWidget#recycleGeneratePage QPushButton[recycleScriptActionRole="generate"] {{
min-width: 70px; max-width: 70px; min-height: 30px; max-height: 30px; padding: 0;
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309; border-radius: 4px; font-weight: 650;
}}
QWidget#recycleGeneratePage QPushButton[recycleScriptActionRole="copy"] {{
min-width: 70px; max-width: 70px; min-height: 26px; max-height: 26px; padding: 0;
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
}}
QWidget#recycleGeneratePage QPushButton[buttonRole="danger"],
QWidget#recycleGeneratePage QPushButton[recycleTableActionRole="deleteRows"] {{
background: #FFF7F5; color: #B42318; border: 1px solid #FCA5A5;
}}
QWidget#recycleGeneratePage QPushButton[buttonRole="danger"]:hover,
QWidget#recycleGeneratePage QPushButton[recycleTableActionRole="deleteRows"]:hover {{
background: #FEF3F2; color: #991B1B; border-color: #EF4444;
}}
QWidget#recycleGeneratePage QPushButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#recycleGeneratePage QPushButton[recycleScriptActionRole="generate"]:hover {{
background: #B45309; color: #ffffff; border-color: #92400E;
}}
QWidget#encodingPage QWidget#encodingPageToolbar,
QWidget#encodingPage QFrame#encodingConversionPanel,
QWidget#encodingPage QFrame#anticheatSettingsPanel {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#encodingPage QWidget#encodingConversionHeader,
QWidget#encodingPage QWidget#anticheatSectionHeader,
QWidget#encodingPage QWidget#anticheatConfigBox {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#encodingPage QLabel#encodingSectionTitle {{
color: {t.TEXT}; font-size: 13px; font-weight: 650;
}}
QWidget#encodingPage QLabel#encodingSectionMeta {{
color: {t.MUTED}; font-size: 12px; font-weight: 650;
}}
QWidget#encodingPage QWidget#encodingFolderRow,
QWidget#encodingPage QWidget#encodingOptionsRow,
QWidget#encodingPage QFrame#encodingSummaryPanel,
QWidget#encodingPage QWidget#encodingProgressRow,
QWidget#encodingPage QWidget#anticheatRootRow {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#encodingPage QLabel#encodingSummaryPill {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
min-height: 20px; max-height: 20px; padding: 0 9px; color: {t.MUTED}; font-weight: 600;
}}
QWidget#encodingPage QLabel#encodingSummaryPill[encodingSummaryRole="count"] {{
background: transparent; border-color: transparent; color: {t.MUTED}; font-weight: 600;
}}
QWidget#encodingPage QWidget#anticheatApplyRow {{
background: transparent; border: none; border-radius: 0px; padding-top: 0px;
}}
QWidget#encodingPage QFrame#anticheatStatusPanel {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#encodingPage QLabel#anticheatStatusTitle {{
color: {t.TEXT}; font-weight: 650;
}}
QWidget#encodingPage QLabel#anticheatStatusLabel {{
color: {t.MUTED}; font-weight: 600;
}}
QWidget#encodingPage QLabel#anticheatStatusValue {{
color: {t.TEXT}; background: transparent; border: none; border-radius: 0px;
padding: 1px 2px; font-weight: 600;
}}
QWidget#encodingPage QScrollArea#anticheatMatrixScroll {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#encodingPage QScrollArea#anticheatMatrixScroll > QWidget,
QWidget#encodingPage QWidget#anticheatMatrix {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#encodingPage QLabel#anticheatMatrixHeader {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
font-weight: 600; padding: 1px 4px;
}}
QWidget#encodingPage QLabel#anticheatMatrixRowLabel {{
color: {t.MUTED}; font-weight: 600; padding-right: 4px;
}}
QWidget#encodingPage QLabel#anticheatNoteLabel {{
color: {t.MUTED}; background: {t.PANEL}; border: none; border-left: 3px solid #FDBA74;
border-radius: 4px; min-height: 34px; max-height: 48px; padding: 4px 6px; font-size: 12px; font-weight: 600;
}}
QWidget#encodingPage QLabel#anticheatComboArrow {{
color: {t.MUTED}; background: transparent; border: none; font-weight: 600;
}}
QWidget#encodingPage QLineEdit,
QWidget#encodingPage QComboBox,
QWidget#encodingPage QListWidget {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#encodingPage QLineEdit#encodingFolderEdit[readOnly="true"] {{
background: {t.PANEL_2}; color: {t.MUTED}; border-color: {t.LINE_SOFT};
}}
QWidget#encodingPage QLineEdit:focus,
QWidget#encodingPage QComboBox:focus {{
border-color: {t.BRAND};
}}
QWidget#encodingPage QComboBox QAbstractItemView {{
 background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #E7EAEE; selection-color: {t.TEXT};
}}
QWidget#encodingPage QComboBox {{
padding-right: 26px;
}}
QWidget#encodingPage QComboBox::drop-down {{
width: 24px; border-left: 1px solid {t.LINE_SOFT}; background: {t.PANEL_2};
border-top-right-radius: 5px; border-bottom-right-radius: 5px;
}}
QWidget#encodingPage QComboBox::drop-down:hover {{
background: {t.PANEL_2}; border-left-color: {t.LINE_SOFT};
}}
QWidget#encodingPage QComboBox::drop-down:pressed {{
background: #E7EAEE; border-left-color: {t.LINE};
}}
QWidget#encodingPage QComboBox#anticheatProcessCombo {{
padding-right: 20px;
}}
QWidget#encodingPage QComboBox#anticheatProcessCombo::drop-down {{
width: 18px; border-left: 1px solid {t.LINE_SOFT}; background: {t.PANEL_2};
}}
QWidget#encodingPage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
min-height: 26px; max-height: 26px; padding: 0 8px;
font-weight: 600;
}}
QWidget#encodingPage QPushButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#encodingPage QPushButton[buttonRole="primary"],
QWidget#encodingPage QPushButton#primaryButton {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
min-height: 30px; max-height: 30px; padding: 0 8px; font-weight: 650;
}}
QWidget#encodingPage QPushButton[anticheatActionRole="apply"] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; font-weight: 600;
min-height: 26px; max-height: 26px; padding: 0 8px; border-radius: 4px;
}}
QWidget#encodingPage QPushButton[buttonRole="primary"]:hover,
QWidget#encodingPage QPushButton#primaryButton:hover {{
background: #B45309; color: #ffffff; border-color: #92400E;
}}
QWidget#encodingPage QPushButton[anticheatActionRole="apply"]:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#encodingPage QProgressBar {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE}; border-radius: 6px; text-align: center;
}}
QWidget#encodingPage QProgressBar::chunk {{
background: {t.BRAND}; border-radius: 5px;
}}
QWidget#freeMicroPage QFrame#freeMicroInputPanel,
QWidget#freeMicroPage QFrame#freeMicroOutputHeader {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#freeMicroPage QWidget#freeMicroSourceModes,
QWidget#freeMicroPage QStackedWidget#freeMicroSourceStack,
QWidget#freeMicroPage QWidget#freeMicroLauncherSource,
QWidget#freeMicroPage QWidget#freeMicroPidSource {{
background: transparent; border: none;
}}
QWidget#freeMicroPage QPushButton#freeMicroLauncherModeButton,
QWidget#freeMicroPage QPushButton#freeMicroPidModeButton {{
min-width: 92px; max-width: 112px; min-height: 26px; max-height: 26px;
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT};
border-radius: 4px; font-weight: 600;
}}
QWidget#freeMicroPage QPushButton#freeMicroLauncherModeButton:checked,
QWidget#freeMicroPage QPushButton#freeMicroPidModeButton:checked {{
background: {t.PANEL}; color: {t.TEXT}; border-color: #87919D; font-weight: 600;
}}
QWidget#freeMicroPage QWidget#freeMicroOutputSection {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; padding: 6px;
}}
QWidget#freeMicroPage QFrame#freeMicroOutputHeader {{
background: transparent; border: none; border-bottom: 1px solid {t.LINE_SOFT}; border-radius: 0;
}}
QWidget#freeMicroPage QFrame#freeMicroSummaryBar {{
background: transparent; border: none; border-radius: 0;
}}
QWidget#freeMicroPage QLabel#freeMicroSummaryPill {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 1px 9px; color: {t.MUTED}; font-weight: 600;
}}
QWidget#freeMicroPage QLabel#freeMicroSummaryPill[freeMicroSummaryState="available"] {{
background: #ECF8F1; border-color: #9DD3B7; color: #1F6B49; font-weight: 600;
}}
QWidget#freeMicroPage QLabel#freeMicroSummaryPill[freeMicroSummaryState="captured"] {{
background: {t.PANEL_2}; border-color: #AEB7C2; color: {t.TEXT}; font-weight: 600;
}}
QWidget#freeMicroPage QLabel#freeMicroSectionLabel {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0;
font-weight: 600; padding: 0 4px 3px 4px;
}}
QWidget#freeMicroPage QLineEdit#freeMicroLauncherEdit,
QWidget#freeMicroPage QLineEdit#freeMicroPidEdit {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#freeMicroPage QLabel#freeMicroSourceStatusLabel,
QWidget#freeMicroPage QLabel#freeMicroMonitorStatusLabel,
QWidget#freeMicroPage QLabel#freeMicroUsageLabel {{
color: {t.MUTED}; font-weight: 600; padding: 1px 2px;
}}
QWidget#freeMicroPage QLabel#freeMicroSourceStatusLabel[freeMicroStatusRole="warning"] {{
color: #9A4A13;
}}
QWidget#freeMicroPage QLabel#freeMicroSourceStatusLabel[freeMicroStatusRole="error"],
QWidget#freeMicroPage QLabel#freeMicroMonitorStatusLabel[freeMicroStatusRole="error"] {{
color: #A5312B;
}}
QWidget#freeMicroPage QLabel#freeMicroMonitorStatusLabel[freeMicroStatusRole="running"] {{
color: #1F6B49;
}}
QWidget#freeMicroPage QLabel#freeMicroLimitBadge,
QWidget#freeMicroPage QLabel#freeMicroUsageBadge {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT};
border-radius: 4px; font-weight: 600; padding: 1px 10px;
}}
QWidget#freeMicroPage QLabel#freeMicroUsageBadge[freeMicroUsageRole="warning"] {{
background: #FFF6E8; color: #9A4A13; border-color: #E4B276;
}}
QWidget#freeMicroPage QPlainTextEdit#freeMicroOutputPanel {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
padding: 8px 10px; font-family: Consolas, "Microsoft YaHei UI"; font-size: 12px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#freeMicroPage QWidget#freeMicroResultActions {{
background: transparent; border: none; border-radius: 0;
}}
QWidget#freeMicroPage QWidget#freeMicroResultActions QPushButton#freeMicroCopyButton,
QWidget#freeMicroPage QWidget#freeMicroResultActions QPushButton#freeMicroClearButton {{
min-height: 26px; max-height: 26px; background: {t.PANEL_2}; color: {t.MUTED};
border: 1px solid {t.LINE_SOFT}; border-radius: 4px; font-weight: 600;
}}
QWidget#freeMicroPage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
}}
QWidget#freeMicroPage QPushButton#freeMicroBrowseButton:hover,
QWidget#freeMicroPage QPushButton#freeMicroCopyButton:hover,
QWidget#freeMicroPage QPushButton#freeMicroClearButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#freeMicroPage QPushButton#freeMicroStartButton,
QWidget#freeMicroPage QPushButton#freeMicroStopButton {{
min-height: 30px; max-height: 30px; border-radius: 4px; font-weight: 650;
}}
QWidget#freeMicroPage QPushButton#freeMicroStartButton[buttonRole="primary"] {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
}}
QWidget#freeMicroPage QPushButton#freeMicroStartButton[buttonRole="primary"]:hover {{
background: #B45309; color: #ffffff; border-color: #92400E;
}}
QWidget#freeMicroPage QPushButton#freeMicroStartButton[buttonRole="secondary"] {{
background: #FCFDFE; color: {t.TEXT}; border: 1px solid #D4DAE1;
}}
QWidget#freeMicroPage QPushButton#freeMicroStopButton[buttonRole="danger"] {{
background: #FFF7F5; color: #B42318; border: 1px solid #FCA5A5;
}}
QWidget#freeMicroPage QPushButton#freeMicroStopButton[buttonRole="danger"]:hover {{
background: #FEF3F2; color: #991B1B; border-color: #EF4444;
}}
QWidget#freeMicroPage QPushButton#freeMicroStartButton:disabled,
QWidget#freeMicroPage QPushButton#freeMicroStopButton:disabled {{
background: {t.PANEL_2}; color: {t.SUBTLE}; border-color: {t.LINE_SOFT};
}}
QWidget#microConfigPage QFrame#microConfigHeader,
QWidget#microConfigPage QFrame#microConfigListPanel,
QWidget#microConfigPage QFrame#microConfigEditorPanel,
QWidget#microConfigPage QWidget#microConfigEditorBody,
QWidget#microConfigPage QWidget#microConfigForm,
QWidget#microConfigPage QWidget#microActionSection {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
}}
QWidget#microConfigPage QWidget#microActionSection {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#microConfigPage QFrame#microSummaryPanel {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#microConfigPage QLabel#microSummaryPill {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
font-weight: 750; padding: 0 8px;
}}
QWidget#microConfigPage QLabel#microSummaryPill[summaryRole="primary"] {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74; font-weight: 850;
}}
QWidget#microConfigPage QLabel#microSummaryPill[summaryRole="ports"],
QWidget#microConfigPage QLabel#microSummaryPill[summaryRole="engine"] {{
color: {t.TEXT};
}}
QWidget#microConfigPage QScrollArea,
QWidget#microConfigPage QScrollArea > QWidget > QWidget {{
background: {t.PANEL}; color: {t.TEXT};
}}
QWidget#microConfigPage QLabel {{
color: {t.TEXT};
}}
QWidget#microConfigPage QLabel#microSectionLabel,
QWidget#microConfigPage QLabel#microActionSectionLabel {{
color: {t.TEXT}; background: transparent; border: none; border-radius: 0;
font-weight: 600; padding: 0 2px;
}}
QWidget#microConfigPage QLineEdit,
QWidget#microConfigPage QComboBox,
QWidget#microConfigPage QSpinBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#microConfigPage QSpinBox {{
padding-right: 8px;
}}
QWidget#microConfigPage QSpinBox::up-button,
QWidget#microConfigPage QSpinBox::down-button {{
width: 0px; border: none; background: transparent;
}}
QWidget#microConfigPage QSpinBox::up-button {{
subcontrol-origin: border; subcontrol-position: top right; border-bottom: 1px solid {t.LINE_SOFT};
border-top-right-radius: 4px;
}}
QWidget#microConfigPage QSpinBox::down-button {{
subcontrol-origin: border; subcontrol-position: bottom right; border-bottom-right-radius: 4px;
}}
QWidget#microConfigPage QSpinBox::up-button:hover,
QWidget#microConfigPage QSpinBox::down-button:hover {{
background: #FFF7ED; border-left-color: #FDBA74;
}}
QWidget#microConfigPage QSpinBox::up-button:pressed,
QWidget#microConfigPage QSpinBox::down-button:pressed {{
background: #FED7AA; border-left-color: {t.BRAND};
}}
QWidget#microConfigPage QComboBox {{
padding-right: 26px;
}}
QWidget#microConfigPage QComboBox::drop-down {{
width: 24px; border-left: 1px solid {t.LINE_SOFT}; background: {t.PANEL_2};
border-top-right-radius: 4px; border-bottom-right-radius: 4px;
}}
QWidget#microConfigPage QComboBox::drop-down:hover {{
background: #FFF7ED; border-left-color: #FDBA74;
}}
QWidget#microConfigPage QComboBox::drop-down:pressed {{
background: #FED7AA; border-left-color: {t.BRAND};
}}
QWidget#microConfigPage QComboBox QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#microConfigPage QLineEdit#microNameEdit[validationState="error"] {{
background: #FFF0EF; color: #7F1D1D; border: 2px solid #B83A32;
}}
QWidget#microConfigPage QTableWidget#microConfigTable {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
alternate-background-color: {t.PANEL}; gridline-color: {t.LINE_SOFT};
selection-background-color: #FFF7ED; selection-color: #92400E;
outline: 0;
}}
QWidget#microConfigPage QTableWidget#microConfigTable::item {{
border: none;
padding-left: 9px;
padding-right: 9px;
}}
QWidget#microConfigPage QTableWidget#microConfigTable::item:selected {{
background: #FFF7ED; color: #92400E; font-weight: 800;
}}
QWidget#microConfigPage QTableWidget#microConfigTable QHeaderView::section {{
background: {t.PANEL_2}; color: {t.MUTED}; border: none; border-bottom: 1px solid {t.LINE_SOFT}; padding: 0 8px; font-weight: 800;
}}
QWidget#microConfigPage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
}}
QWidget#microConfigPage QPushButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#microConfigPage QWidget#microToolActions QPushButton,
QWidget#microConfigPage QWidget#microVisibilityActions QPushButton {{
min-height: 26px; max-height: 26px; background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
}}
QWidget#microConfigPage QWidget#microToolActions QPushButton:hover,
QWidget#microConfigPage QWidget#microVisibilityActions QPushButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#microConfigPage QPushButton[buttonRole="primary"],
QWidget#microConfigPage QPushButton[microActionTone="primary"],
QWidget#microConfigPage QPushButton#createButton {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
font-weight: 650;
}}
QWidget#microConfigPage QPushButton#microRefreshStatusButton {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE};
}}
QWidget#microConfigPage QPushButton#microRefreshStatusButton:hover {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QWidget#microConfigPage QPushButton[microActionTone="success"],
QWidget#microConfigPage QPushButton#startButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; font-weight: 600;
}}
QWidget#microConfigPage QWidget#microPrimaryActions QPushButton {{
min-height: 30px; max-height: 30px; border-radius: 4px;
}}
QWidget#microConfigPage QPushButton[buttonRole="danger"],
QWidget#microConfigPage QPushButton[microActionTone="danger"],
QWidget#microConfigPage QPushButton#deleteButton,
QWidget#microConfigPage QPushButton#deletePatchButton {{
background: #FEF3F2; color: #B42318; border: 1px solid #7F1D1D;
}}
QWidget#microConfigPage QPushButton#microDeletePatchButton {{
background: {t.PANEL}; color: #B42318; border: 1px solid #FCA5A5;
}}
QWidget#microConfigPage QPushButton#microDeletePatchButton:hover {{
background: #FFF7F5; color: #991B1B; border-color: #EF4444;
}}
QWidget#microConfigPage QCheckBox {{
color: {t.TEXT};
}}
QWidget#microConfigPage QCheckBox::indicator {{
background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 4px;
}}
QWidget#microConfigPage QCheckBox::indicator:checked {{
background: {t.BRAND}; border-color: #B45309;
}}
QWidget#itemInjectPage QFrame#itemRootBar,
QWidget#itemInjectPage QFrame#itemTemplatePanel,
QWidget#itemInjectPage QFrame#itemEditorPanel {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#itemInjectPage QLabel#itemSectionTitle {{
color: {t.TEXT}; font-size: 13px; font-weight: 600;
}}
QWidget#itemInjectPage QWidget#itemTemplateHeader,
QWidget#itemInjectPage QFrame#itemEditorModeActions {{
background: transparent; border: none; border-radius: 0px;
}}
QWidget#itemInjectPage QFrame#itemEditorRecordActions,
QWidget#itemInjectPage QFrame#itemEditorFileActions,
QWidget#itemInjectPage QFrame#itemEditorCommitActions {{
background: transparent; border: none; border-left: 1px solid {t.LINE_SOFT};
border-radius: 0px; padding-left: 6px; margin-left: 2px;
}}
QWidget#itemInjectPage QLabel#itemTargetSummary {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
min-height: 26px; max-height: 26px; padding: 0 8px; font-weight: 600;
}}
QWidget#itemInjectPage QLabel#itemInjectStatus {{
color: {t.MUTED}; min-width: 0px; padding: 0 4px; font-weight: 600;
}}
QWidget#itemInjectPage QLineEdit,
QWidget#itemInjectPage QComboBox,
QWidget#itemInjectPage QPlainTextEdit,
QWidget#itemInjectPage QListWidget,
QWidget#itemInjectPage QTableWidget {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#itemInjectPage QComboBox QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#itemInjectPage QListWidget#itemTemplateList::item {{
background: transparent; color: {t.TEXT}; min-height: 26px; padding: 3px 7px; border-radius: 4px;
}}
QWidget#itemInjectPage QListWidget#itemTemplateList::item:hover {{
background: #EEF1F4; color: {t.TEXT};
}}
QWidget#itemInjectPage QListWidget#itemTemplateList::item:selected,
QWidget#itemInjectPage QListWidget#itemTemplateList::item:selected:!active {{
background: #FFF7ED; color: #92400E;
}}
QWidget#itemInjectPage QFrame#itemTemplateActions {{
background: transparent; border: none; border-top: 1px solid {t.LINE_SOFT}; border-radius: 0px;
}}
QWidget#itemInjectPage QLabel#itemSummaryPill {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 1px 8px; color: {t.MUTED}; font-weight: 600;
}}
QWidget#itemInjectPage QLabel#itemSummaryPill[itemSummaryRole="count"],
QWidget#itemInjectPage QLabel#itemSummaryPill[itemSummaryRole="template"] {{
background: {t.PANEL}; color: {t.TEXT};
}}
QWidget#itemInjectPage QLabel#itemSummaryPill[itemSummaryRole="selected"] {{
background: #EEF1F4; border-color: #AEB7C2; color: {t.TEXT}; font-weight: 600;
}}
QWidget#itemInjectPage QTableWidget {{
alternate-background-color: {t.PANEL_2}; gridline-color: {t.LINE_SOFT};
}}
QWidget#itemInjectPage QTableWidget::item:selected {{
background: #FFF7ED; color: #92400E;
}}
QWidget#itemInjectPage QTableWidget QHeaderView::section {{
background: {t.PANEL_2}; color: {t.MUTED}; border: none; border-bottom: 1px solid {t.LINE_SOFT};
}}
QWidget#itemInjectPage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
}}
QWidget#itemInjectPage QFrame#itemTemplatePanel QPushButton[itemTemplateActionRole] {{
min-width: 36px; max-width: 36px; min-height: 26px; max-height: 26px; padding: 0 4px;
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px; font-weight: 600;
}}
QWidget#itemInjectPage QFrame#itemTemplatePanel QPushButton[itemTemplateActionRole="new"] {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; font-weight: 600;
}}
QWidget#itemInjectPage QFrame#itemTemplatePanel QPushButton[itemTemplateActionRole="delete"] {{
min-width: 36px; max-width: 36px; min-height: 26px; max-height: 26px; padding: 0 4px;
background: #FFF7F5; color: #B42318; border-color: #FCA5A5; font-weight: 600;
}}
QWidget#itemInjectPage QListWidget#itemTemplateList {{
background: {t.PANEL}; color: {t.TEXT}; border: none;
}}
QWidget#itemInjectPage QFrame#itemTemplateActions {{
background: transparent; border: none; border-top: 1px solid {t.LINE_SOFT}; border-radius: 0px;
}}
QWidget#itemInjectPage QPushButton#itemDbRefreshButton:hover,
QWidget#itemInjectPage QPushButton[itemTemplateActionRole]:hover,
QWidget#itemInjectPage QWidget#itemEditorActions QPushButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#itemInjectPage QWidget#itemInjectTopActions QPushButton[itemEditorActionRole="inject"] {{
min-height: 30px; max-height: 30px; border-radius: 4px; font-weight: 650;
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
}}
QWidget#itemInjectPage QWidget#itemInjectTopActions QPushButton[itemEditorActionRole="inject"]:hover {{
background: #B45309; color: #ffffff; border-color: #92400E;
}}
QWidget#itemInjectPage QPushButton[buttonRole="danger"],
QWidget#itemInjectPage QPushButton[itemTemplateActionRole="delete"],
QWidget#itemInjectPage QPushButton[itemEditorActionRole="deleteItem"] {{
background: #FFF7F5; color: #B42318; border: 1px solid #FCA5A5;
}}
QWidget#itemInjectPage QFrame#itemRootBar QPushButton#itemDbRefreshButton {{
min-width: 74px; max-width: 74px; min-height: 26px; max-height: 26px;
padding: 0 2px; border-radius: 4px; font-weight: 600;
}}
QWidget#itemInjectPage QWidget#itemEditorActions {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#itemInjectPage QWidget#itemEditorActions QPushButton[itemEditorActionRole] {{
min-height: 26px; max-height: 26px; background: {t.PANEL}; color: {t.TEXT};
border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
}}
QWidget#itemInjectPage QWidget#itemEditorActions QPushButton[itemEditorActionGroup="record"],
QWidget#itemInjectPage QWidget#itemEditorActions QPushButton[itemEditorActionGroup="file"],
QWidget#itemInjectPage QWidget#itemEditorActions QPushButton[itemEditorActionGroup="commit"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE}; font-weight: 600;
}}
QWidget#itemInjectPage QFrame#itemEditorModeActions QPushButton {{
min-height: 26px; max-height: 26px; border-radius: 0px; margin: 0px; font-weight: 600;
}}
QWidget#itemInjectPage QFrame#itemEditorModeActions QPushButton[itemEditorActionRole="preview"] {{
border-top-left-radius: 4px; border-bottom-left-radius: 4px; border-top-right-radius: 0px; border-bottom-right-radius: 0px;
}}
QWidget#itemInjectPage QFrame#itemEditorModeActions QPushButton[itemEditorActionRole="edit"] {{
border-top-left-radius: 0px; border-bottom-left-radius: 0px; border-top-right-radius: 4px; border-bottom-right-radius: 4px; border-left: none;
}}
QWidget#itemInjectPage QFrame#itemEditorModeActions QPushButton:checked {{
background: #E5E9ED; color: {t.TEXT}; border-color: #87919D; font-weight: 600;
}}
QWidget#itemInjectPage QWidget#itemEditorActions QPushButton[itemEditorActionRole="deleteItem"] {{
background: #FFF7F5; color: #B42318; border: 1px solid #FCA5A5; font-weight: 600;
}}
QWidget#itemInjectPage QPushButton[itemTemplateActionRole="delete"] {{
background: #FFF7F5; color: #B42318; border: 1px solid #FCA5A5; font-weight: 600;
}}
QWidget#itemInjectPage QPushButton[buttonRole="danger"]:hover,
QWidget#itemInjectPage QPushButton[itemTemplateActionRole="delete"]:hover,
QWidget#itemInjectPage QPushButton[itemEditorActionRole="deleteItem"]:hover {{
background: #FEF3F2; color: #991B1B; border-color: #EF4444;
}}
QWidget#itemInjectPage QPushButton:disabled {{
background: #EEF1F4; color: #87919D; border-color: {t.LINE_SOFT};
}}
QDialog#itemEntryDialog {{
background: {t.PANEL_2}; color: {t.TEXT};
}}
QDialog#itemEntryDialog QScrollArea,
QDialog#itemEntryDialog QWidget#itemEntryDialogPages {{
background: transparent; border: none;
}}
QDialog#itemEntryDialog QLabel#itemEntryFieldLabel {{
color: {t.MUTED}; font-weight: 700;
}}
QDialog#itemEntryDialog QLineEdit#itemEntryFieldEdit,
QDialog#itemEntryDialog QPlainTextEdit {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 5px;
}}
QDialog#itemEntryDialog QLineEdit#itemEntryFieldEdit:focus,
QDialog#itemEntryDialog QPlainTextEdit:focus {{
border-color: {t.BRAND};
}}
QWidget#mapSettingsPage QFrame#mapPageHeader,
QWidget#mapSettingsPage QFrame#mapSettingsBar,
QWidget#mapSettingsPage QFrame#mapListPanel {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
}}
QWidget#mapSettingsPage QScrollArea#mapEditorPanel,
QWidget#mapSettingsPage QWidget#mapEditorBody {{
background: {t.PANEL}; color: {t.TEXT}; border: none;
}}
QWidget#mapSettingsPage QFrame#mapSectionFrame {{
background: transparent; color: {t.TEXT}; border: none; border-top: 1px solid {t.LINE_SOFT}; border-radius: 0;
}}
QWidget#mapSettingsPage QLabel {{
color: {t.TEXT};
}}
QWidget#mapSettingsPage QLabel#mapHeaderStatus,
QWidget#mapSettingsPage QLabel#mapStatusLabel,
QWidget#mapSettingsPage QLabel#mapListHint {{
color: {t.MUTED};
}}
QWidget#mapSettingsPage QLabel#mapEditStateLabel {{
  background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px; padding: 2px 8px; font-weight: 650;
}}
QWidget#mapSettingsPage QLabel#mapEditStateLabel[stateRole="warning"] {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QWidget#mapSettingsPage QLabel#mapEditStateLabel[stateRole="success"] {{
background: #ECFDF3; color: #166534; border-color: #86EFAC;
}}
QWidget#mapSettingsPage QLabel#mapPanelTitle,
QWidget#mapSettingsPage QLabel#mapSectionTitle {{
  color: {t.TEXT}; font-weight: 650;
}}
QWidget#mapSettingsPage QLabel#mapSectionTitle {{
 background: transparent; color: {t.TEXT}; border: none; border-bottom: 1px solid {t.LINE_SOFT}; border-radius: 0; padding: 0 4px 3px 4px; font-weight: 650;
}}
QWidget#mapSettingsPage QLabel#mapPanelBadge {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-radius: 0; font-weight: 600;
}}
QWidget#mapSettingsPage QFrame#mapEditorSummaryPanel {{
background: transparent; border: none; border-bottom: 1px solid {t.LINE_SOFT}; border-radius: 0;
}}
QWidget#mapSettingsPage QLabel#mapEditorSummaryPill {{
background: transparent; border: none; border-radius: 0;
 padding: 1px 5px; color: {t.MUTED}; font-size: 12px; font-weight: 600;
}}
QWidget#mapSettingsPage QLabel#mapEditorSummaryPill[summaryRole="primary"] {{
 background: transparent; color: {t.TEXT};
}}
QWidget#mapSettingsPage QFrame#mapEditorHeader QLabel#mapPanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; font-weight: 650; padding: 0 4px;
}}
QWidget#mapSettingsPage QFrame#mapListHeader QLabel#mapPanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; font-size: 12px; font-weight: 650; padding: 0 4px;
}}
QWidget#mapSettingsPage QLineEdit,
QWidget#mapSettingsPage QComboBox {{
  background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
  selection-background-color: {t.PANEL_2}; selection-color: {t.TEXT};
}}
QWidget#mapSettingsPage QListWidget {{
  background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
selection-background-color: {t.PANEL_2}; selection-color: {t.TEXT};
}}
QWidget#mapSettingsPage QComboBox QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: {t.PANEL_2}; selection-color: {t.TEXT};
}}
QWidget#mapSettingsPage QListWidget#mapListWidget::item {{
  background: transparent; color: {t.TEXT}; min-height: 26px; padding: 3px 7px; border-radius: 4px; border-bottom: 1px solid {t.LINE_SOFT};
}}
QWidget#mapSettingsPage QListWidget#mapListWidget::item:hover {{
 background: {t.PANEL_2}; color: {t.TEXT};
}}
QWidget#mapSettingsPage QListWidget#mapListWidget::item:selected,
QWidget#mapSettingsPage QListWidget#mapListWidget::item:selected:!active,
QWidget#mapSettingsPage QListWidget#mapListWidget::item:selected:inactive {{
 background: {t.PANEL_2}; color: {t.TEXT};
}}
QWidget#mapSettingsPage QCheckBox {{
color: {t.TEXT};
}}
QWidget#mapSettingsPage QCheckBox::indicator {{
background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 4px;
}}
QWidget#mapSettingsPage QCheckBox::indicator:checked {{
background: {t.PANEL_2}; border-color: {t.BRAND};
}}
QWidget#mapSettingsPage QCheckBox[mapBooleanParam="true"] {{
background: transparent;
border: none;
border-radius: 0;
padding: 2px 6px;
min-height: 28px;
 font-weight: 600;
color: {t.MUTED};
}}
QWidget#mapSettingsPage QCheckBox[mapBooleanParam="true"]:hover {{
 background: {t.PANEL_2};
 color: {t.TEXT};
border-color: transparent;
}}
QWidget#mapSettingsPage QTabWidget#mapParameterTabs::pane {{
  background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 0 4px 4px 4px;
}}
QWidget#mapSettingsPage QScrollArea#mapParameterTabScroll,
QWidget#mapSettingsPage QScrollArea#mapParameterTabScroll QWidget#qt_scrollarea_viewport {{
background: {t.PANEL}; border: none;
}}
QWidget#mapSettingsPage QTabWidget#mapParameterTabs QTabBar::tab {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; padding: 5px 14px; min-height: 26px;
}}
QWidget#mapSettingsPage QTabWidget#mapParameterTabs QTabBar::tab:selected {{
 background: {t.PANEL}; color: {t.TEXT}; border-bottom-color: {t.PANEL}; font-weight: 650;
}}
QWidget#mapSettingsPage QCheckBox[mapBooleanParam="true"]::indicator {{
width: 13px;
height: 13px;
background: {t.PANEL};
border: 1px solid {t.LINE_SOFT};
border-radius: 4px;
}}
QWidget#mapSettingsPage QCheckBox[mapBooleanParam="true"]::indicator:checked {{
 background: {t.PANEL_2};
 border-color: {t.LINE};
}}
QWidget#mapSettingsPage QPushButton {{
  background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
min-height: 28px; padding: 3px 8px;
}}
QWidget#mapSettingsPage QPushButton:hover {{
 background: {t.PANEL_2}; color: {t.TEXT}; border-color: {t.LINE};
}}
QWidget#mapSettingsPage QPushButton[buttonRole="primary"],
QWidget#mapSettingsPage QPushButton#mapSaveButton {{
  background: {t.BRAND}; color: #ffffff; border: 1px solid {t.BRAND};
  min-height: 24px; max-height: 24px;
}}
QWidget#mapSettingsPage QPushButton#mapReloadButton {{
  min-height: 24px; max-height: 24px;
}}
QWidget#mapSettingsPage QPushButton#mapPageHelpButton {{
  min-height: 20px; max-height: 20px;
}}
QWidget#cdkManagerPage QFrame#cdkManagementPanel,
QWidget#cdkManagerPage QFrame#cdkRecordsPanel {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 0;
}}
QWidget#cdkManagerPage QWidget#cdkDirectoryBar,
QWidget#cdkManagerPage QGroupBox#cdkGenerationBox,
QWidget#cdkManagerPage QWidget#cdkRecordsHeader,
QWidget#cdkManagerPage QWidget#cdkQueryBar {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
}}
QWidget#cdkManagerPage QWidget#cdkRecordsHeader {{
background: transparent; border: none; border-bottom: 1px solid {t.LINE_SOFT}; border-radius: 0;
}}
QWidget#cdkManagerPage QFrame#cdkStatsPanel {{
background: transparent; border: none; border-radius: 0;
}}
QWidget#cdkManagerPage QLabel#cdkSummaryPill {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 1px 9px; color: {t.MUTED}; font-weight: 650;
}}
QWidget#cdkManagerPage QLabel#cdkSummaryPill[cdkSummaryRole="unused"],
QWidget#cdkManagerPage QLabel#cdkSummaryPill[cdkSummaryRole="used"] {{
background: {t.PANEL}; border-color: {t.LINE_SOFT}; color: {t.TEXT}; font-weight: 650;
}}
QWidget#cdkManagerPage QWidget#cdkQueryBar {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#cdkManagerPage QWidget#cdkTypeBar,
QWidget#cdkManagerPage QGroupBox#cdkGenerationBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#cdkManagerPage QGroupBox#cdkGenerationBox::title {{
subcontrol-origin: margin; subcontrol-position: top left; left: 4px; padding: 0 6px;
background: transparent; color: {t.MUTED}; font-weight: 600; border-radius: 0;
}}
QWidget#cdkManagerPage QFrame#cdkGenerationSummary {{
background: transparent; border: none;
}}
QWidget#cdkManagerPage QLabel#cdkGenerationSummaryPill {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
font-weight: 600; padding: 0 8px;
}}
QWidget#cdkManagerPage QLabel#cdkGenerationSummaryPill[summaryRole="type"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE_SOFT}; font-weight: 650;
}}
QWidget#cdkManagerPage QLabel#cdkGenerationSummaryPill[summaryRole="length"],
QWidget#cdkManagerPage QLabel#cdkGenerationSummaryPill[summaryRole="count"],
QWidget#cdkManagerPage QLabel#cdkGenerationSummaryPill[summaryRole="charset"] {{
color: {t.MUTED};
}}
QWidget#cdkManagerPage QLabel,
QWidget#cdkManagerPage QLabel#cdkSectionLabel {{
color: {t.TEXT};
}}
QWidget#cdkManagerPage QLabel#cdkSectionLabel {{
color: {t.MUTED}; font-weight: 600;
}}
QWidget#cdkManagerPage QLabel#hintText {{
color: {t.MUTED};
}}
QWidget#cdkManagerPage QLineEdit,
QWidget#cdkManagerPage QComboBox,
QWidget#cdkManagerPage QSpinBox,
QWidget#cdkManagerPage QPlainTextEdit#cdkRecordsEditor {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
selection-background-color: #FFF0E5; selection-color: {t.TEXT};
}}
QWidget#cdkManagerPage QSpinBox::up-button,
QWidget#cdkManagerPage QSpinBox::down-button {{
width: 18px;
background: {t.PANEL_2};
border-left: 1px solid {t.LINE_SOFT};
}}
QWidget#cdkManagerPage QSpinBox::up-button {{
border-top-right-radius: 3px;
}}
QWidget#cdkManagerPage QSpinBox::down-button {{
border-bottom-right-radius: 3px;
}}
QWidget#cdkManagerPage QSpinBox::up-button:hover,
QWidget#cdkManagerPage QSpinBox::down-button:hover {{
background: #EEF1F4;
}}
QWidget#cdkManagerPage QComboBox QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #FFF0E5; selection-color: {t.TEXT};
}}
QWidget#cdkManagerPage QTabWidget#cdkRecordsTabs::pane {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#cdkManagerPage QTabBar::tab {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; padding: 4px 10px;
}}
QWidget#cdkManagerPage QTabBar::tab:selected {{
background: #FFF0E5; color: #A93F00; border-color: {t.LINE}; font-weight: 600;
}}
QWidget#cdkManagerPage QWidget#cdkQueryBar {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#cdkManagerPage QFrame#cdkTypeBar,
QWidget#cdkManagerPage QWidget#cdkTypeBar,
QWidget#cdkManagerPage QGroupBox#cdkGenerationBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#cdkManagerPage QGroupBox#cdkGenerationBox {{
padding-top: 6px;
}}
QWidget#cdkManagerPage QGroupBox#cdkGenerationBox::title {{
subcontrol-origin: margin; subcontrol-position: top left; left: 4px; padding: 0 6px;
background: transparent; color: {t.MUTED}; font-weight: 600; border-radius: 0;
}}
QWidget#cdkManagerPage QWidget#cdkSecondaryQueryActions {{
background: transparent; border: none;
}}
QWidget#cdkManagerPage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
font-weight: 600;
}}
QWidget#cdkManagerPage QPushButton#cdkQueryActionButton[cdkQueryActionRole="query"] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; font-weight: 600;
}}
QWidget#cdkManagerPage QPushButton#cdkTypeActionButton[cdkTypeActionRole="add"] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; font-weight: 600;
}}
QWidget#cdkManagerPage QPushButton#cdkHelpButton,
QWidget#cdkManagerPage QPushButton[cdkRecordsActionRole="help"] {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent;
}}
QWidget#cdkManagerPage QPushButton:hover,
QWidget#cdkManagerPage QPushButton#cdkQueryActionButton[cdkVisualState="secondary-hover"] {{
background: #EEF1F4; color: {t.TEXT}; border-color: #B9C2CC;
}}
QWidget#cdkManagerPage QPushButton[buttonRole="primary"],
QWidget#cdkManagerPage QPushButton#primaryButton,
QWidget#cdkManagerPage QPushButton[cdkGenerationActionRole="generate"] {{
background: #C45100; color: #FFF9F3; border: 1px solid #C45100; font-weight: 650;
}}
QWidget#cdkManagerPage QPushButton[cdkGenerationActionRole="generate"]:hover,
QWidget#cdkManagerPage QPushButton[cdkGenerationActionRole="generate"][cdkVisualState="primary-hover"],
QWidget#cdkManagerPage QPushButton#primaryButton[cdkVisualState="primary-hover"] {{
background: #B94700; color: #FFF9F3; border-color: #B94700;
}}
QWidget#cdkManagerPage QPushButton[cdkGenerationActionRole="generate"]:pressed {{
background: #A93F00; color: #FFF9F3; border-color: #A93F00;
}}
QWidget#cdkManagerPage QPushButton[buttonRole="danger"],
QWidget#cdkManagerPage QPushButton[cdkRecordsActionRole="clearUsed"],
QWidget#cdkManagerPage QPushButton[cdkQueryActionRole="clearUsed"] {{
 background: #FFF0EF; color: #B83A32; border: 1px solid #B83A32; font-weight: 600;
}}
QWidget#cdkManagerPage QPushButton#cdkTypeActionButton[cdkTypeActionRole="delete"] {{
background: #FFF0EF; color: #B83A32; border: 1px solid #B83A32; font-weight: 600;
}}
QWidget#cdkManagerPage QPushButton[buttonRole="danger"]:hover,
QWidget#cdkManagerPage QPushButton[cdkRecordsActionRole="clearUsed"]:hover,
QWidget#cdkManagerPage QPushButton[cdkQueryActionRole="clearUsed"]:hover {{
background: #FCE4E2; color: #9F2F29; border-color: #9F2F29;
}}
QWidget#cdkManagerPage QPushButton#cdkTypeActionButton[cdkTypeActionRole="delete"]:hover {{
background: #FCE4E2; color: #9F2F29; border-color: #9F2F29;
}}
QWidget#cdkManagerPage QPushButton:disabled {{
background: #EEF1F4; color: #87919D; border-color: {t.LINE_SOFT};
}}
QWidget#memberSystemPage QFrame#memberDirectoryBar,
QWidget#memberSystemPage QFrame#memberSummaryBar,
QWidget#memberSystemPage QFrame#memberInlineActionsBar {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
}}
QWidget#memberSystemPage QFrame#memberAccountsPanel,
QWidget#memberSystemPage QFrame#memberActionsPanel {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 0px;
}}
QWidget#memberSystemPage QFrame#memberActionGroup {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 0px;
}}
QWidget#memberSystemPage QGroupBox#memberAccountActionsBox::title,
QWidget#memberSystemPage QGroupBox#memberHelpBox::title {{
background: {t.PANEL}; color: {t.TEXT}; font-weight: 650;
}}
QWidget#memberSystemPage QLabel {{
color: {t.TEXT};
}}
QWidget#memberSystemPage QLabel#memberTimeLabel,
QWidget#memberSystemPage QLabel#errorText {{
color: {t.MUTED};
}}
QWidget#memberSystemPage QLabel#memberTimeLabel[memberInfoRole="clock"] {{
background: transparent; border: none; border-radius: 0px;
padding: 0 6px; color: {t.MUTED}; font-weight: 650;
}}
QWidget#memberSystemPage QLabel#memberSummaryPill {{
background: transparent; border: none; border-radius: 0px;
padding: 0 6px; color: {t.MUTED}; font-weight: 600;
}}
QWidget#memberSystemPage QLabel#memberSummaryPill[memberSummaryRole="total"] {{
color: {t.TEXT};
}}
QWidget#memberSystemPage QLabel#memberSummaryPill[memberSummaryRole="expired"] {{
color: #991B1B; font-weight: 650;
}}
QWidget#memberSystemPage QLabel#memberSummaryPill[memberSummaryRole="selected"] {{
color: {t.TEXT}; font-weight: 600;
}}
QWidget#memberSystemPage QLineEdit,
QWidget#memberSystemPage QSpinBox {{
min-height: 32px; max-height: 32px;
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
selection-background-color: #FFF0E5; selection-color: {t.TEXT};
}}
QWidget#memberSystemPage QSpinBox::up-button,
QWidget#memberSystemPage QSpinBox::down-button {{
width: 18px;
background: {t.PANEL_2};
border-left: 1px solid {t.LINE_SOFT};
}}
QWidget#memberSystemPage QSpinBox::up-button {{
border-top-right-radius: 5px;
}}
QWidget#memberSystemPage QSpinBox::down-button {{
border-bottom-right-radius: 5px;
}}
QWidget#memberSystemPage QSpinBox::up-button:hover,
QWidget#memberSystemPage QSpinBox::down-button:hover {{
background: #EEF1F4;
}}
QWidget#memberSystemPage QTableWidget#memberAccountsTable {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
alternate-background-color: #FAFBFC; gridline-color: {t.LINE_SOFT};
selection-background-color: #F8FAFC; selection-color: {t.TEXT};
}}
QWidget#memberSystemPage QTableWidget#memberAccountsTable::item {{
color: {t.TEXT}; border-bottom: 1px solid {t.LINE_SOFT}; padding-left: 8px; padding-right: 8px;
}}
QWidget#memberSystemPage QTableWidget#memberAccountsTable::item:selected {{
background: #F8FAFC; color: {t.TEXT};
}}
QWidget#memberSystemPage QTableWidget#memberAccountsTable QHeaderView::section {{
background: #F8FAFC; color: {t.MUTED}; border: none; border-bottom: 1px solid {t.LINE_SOFT}; font-weight: 600;
}}
QWidget#memberSystemPage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
}}
QWidget#memberSystemPage QPushButton[memberActionRole] {{
padding: 0px 8px;
border-radius: 4px; font-weight: 600;
}}
QWidget#memberSystemPage QPushButton#memberDataDirActionButton,
QWidget#memberSystemPage QPushButton[memberDensityRole="compact"] {{
min-height: 26px; max-height: 26px;
}}
QWidget#memberSystemPage QPushButton#memberDataDirActionButton,
QWidget#memberSystemPage QPushButton[memberActionRole="autoCheck"],
QWidget#memberSystemPage QPushButton[memberActionRole="addAccount"] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE};
}}
QWidget#memberSystemPage QPushButton[memberActionRole="usageHelp"],
QWidget#memberSystemPage QPushButton[memberActionRole="scriptHelp"] {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent;
}}
QWidget#memberSystemPage QPushButton#memberDataDirActionButton:hover,
QWidget#memberSystemPage QPushButton[memberActionRole="autoCheck"]:hover,
QWidget#memberSystemPage QPushButton[memberActionRole="addAccount"]:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#memberSystemPage QPushButton[memberActionRole="usageHelp"]:hover,
QWidget#memberSystemPage QPushButton[memberActionRole="scriptHelp"]:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: transparent;
}}
QWidget#memberSystemPage QPushButton[buttonRole="primary"],
QWidget#memberSystemPage QPushButton#primaryButton,
QWidget#memberSystemPage QPushButton[memberActionRole="modifyExpiry"] {{
min-height: 30px; max-height: 30px;
background: #C45100; color: #FFF9F3; border: 1px solid #C45100; font-weight: 650;
}}
QWidget#memberSystemPage QPushButton#primaryButton:hover,
QWidget#memberSystemPage QPushButton[memberActionRole="modifyExpiry"]:hover {{
background: #B94700; color: #FFF9F3; border-color: #B94700;
}}
QWidget#memberSystemPage QPushButton#primaryButton:disabled,
QWidget#memberSystemPage QPushButton[memberActionRole="modifyExpiry"]:disabled {{
background: #EEF1F4; color: #87919D; border-color: #D4DAE1;
}}
QWidget#memberSystemPage QPushButton[buttonRole="danger"],
QWidget#memberSystemPage QPushButton[memberActionRole="deleteAccount"] {{
background: #FFF0EF; color: #B83A32; border: 1px solid #E5A6A2;
}}
QWidget#memberSystemPage QPushButton[memberActionRole="deleteAccount"]:hover {{
background: #FEE2E2; color: #991B1B; border-color: #B42318;
}}
QWidget#dbManagerPage QFrame#dbConnectionPanel {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
padding: 2px 4px;
}}
QWidget#dbManagerPage QFrame#dbWorkspacePanel,
QWidget#dbManagerPage QWidget#dbBottomActionBar,
QWidget#dbManagerPage QWidget#dbRootRow,
QWidget#dbManagerPage QWidget#dbFileRow,
QWidget#dbManagerPage QWidget#dbConnectedActionGroup {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 0px;
}}
QWidget#dbManagerPage QWidget#dbTableToolbar {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#dbManagerPage QLabel {{
color: {t.TEXT};
}}
QWidget#dbManagerPage QLabel#dbStatusLabel,
QWidget#dbManagerPage QLabel#dbTableCountLabel {{
color: {t.MUTED};
}}
QWidget#dbManagerPage QLabel#dbStatusLabel,
QFrame#dbConnectionPanel QLabel#dbStatusLabel {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
padding: 0 6px; color: {t.MUTED}; font-size: 12px; font-weight: 760;
}}
QWidget#dbManagerPage QLabel#dbStatusLabel[dbStatusRole="success"] {{
color: #27845A; border-color: #27845A;
}}
QWidget#dbManagerPage QLabel#dbStatusLabel[dbStatusRole="warn"] {{
color: #A95312; border-color: #A95312;
}}
QWidget#dbManagerPage QLabel#dbStatusLabel[dbStatusRole="working"] {{
color: #2563A6; border-color: #2563A6;
}}
QWidget#dbManagerPage QLabel#dbStatusLabel[dbStatusRole="error"] {{
color: #B83A32; border-color: #B83A32;
}}
QWidget#dbManagerPage QLabel#dbTableCountLabel {{
    background: transparent; border: none; border-radius: 0; padding-left: 0; padding-right: 8px; font-size: 12px; font-weight: 650;
}}
QWidget#dbManagerPage QLabel#dbEditHint,
QWidget#dbManagerPage QLabel#dbTablePageLabel {{
background: transparent; border: none; color: {t.MUTED}; font-size: 12px; font-weight: 600;
}}
QWidget#dbManagerPage QWidget#dbTableSearchGroup {{
background: transparent; border: none; border-radius: 0;
}}
QWidget#dbManagerPage QWidget#dbTableResultRow,
QWidget#dbManagerPage QWidget#dbTableEditRow {{
background: transparent; border: none; border-radius: 0;
}}
QWidget#dbManagerPage QWidget#dbTableRowActionGroup,
QWidget#dbManagerPage QWidget#dbTableTransferActionGroup {{
background: transparent; border: none; border-left: 1px solid {t.LINE_SOFT}; border-radius: 0px;
}}
QWidget#dbManagerPage QLineEdit,
QWidget#dbManagerPage QComboBox,
QWidget#dbManagerPage QSpinBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
selection-background-color: #E7EAEE; selection-color: {t.TEXT};
}}
QWidget#dbManagerPage QLineEdit:focus,
QWidget#dbManagerPage QComboBox:focus,
QWidget#dbManagerPage QSpinBox:focus {{
 border: 2px solid {t.LINE};
}}
QWidget#dbManagerPage QComboBox QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #E7EAEE; selection-color: {t.TEXT};
}}
QWidget#dbManagerPage QTabWidget#dbWorkspaceTabs::pane {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#dbManagerPage QTabWidget#dbWorkspaceTabs QTabBar::tab {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; min-height: 24px; min-width: 68px; padding: 3px 9px;
}}
QWidget#dbManagerPage QTabWidget#dbWorkspaceTabs QTabBar::tab:selected {{
 background: {t.PANEL_2}; color: {t.TEXT}; border-color: {t.LINE};
}}
QWidget#dbManagerPage QTableWidget#dbDataTable {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
alternate-background-color: {t.PANEL_2}; gridline-color: {t.LINE_SOFT};
 selection-background-color: #E7EAEE; selection-color: {t.TEXT};
}}
QWidget#dbManagerPage QTableWidget#dbDataTable:focus {{
 border: 2px solid {t.LINE};
}}
QWidget#dbManagerPage QTableWidget#dbDataTable::item {{
color: {t.TEXT}; border-bottom: 1px solid {t.LINE_SOFT};
}}
QWidget#dbManagerPage QTableWidget#dbDataTable::item:selected {{
 background: #E7EAEE; color: {t.TEXT}; border-top: 1px solid {t.LINE}; border-bottom: 1px solid {t.LINE};
}}
QWidget#dbManagerPage QTableWidget#dbDataTable QHeaderView::section {{
background: {t.PANEL_2}; color: {t.MUTED}; border: none; border-bottom: 1px solid {t.LINE_SOFT};
}}
QWidget#dbManagerPage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
}}
QWidget#dbManagerPage QPushButton#dbConnectionActionButton,
QWidget#dbManagerPage QPushButton#primaryButton[dbConnectionActionRole="connect"],
QWidget#dbManagerPage QPushButton#dbTableActionButton,
QWidget#dbManagerPage QPushButton#dbTablePageButton {{
min-height: 26px; max-height: 26px; border-radius: 4px; font-weight: 600;
}}
QWidget#dbManagerPage QPushButton[dbTableActionRole] {{
min-height: 28px; max-height: 28px; min-width: 58px; max-width: 58px; padding-left: 6px; padding-right: 6px; font-weight: 600;
}}
QWidget#dbManagerPage QPushButton[dbTableActionRole="toggleLanguage"] {{
min-width: 64px; max-width: 64px;
}}
QWidget#dbManagerPage QPushButton[dbTableActionRole="search"],
QWidget#dbManagerPage QPushButton[dbTableActionRole="toggleLanguage"],
QWidget#dbManagerPage QPushButton[dbTableActionRole="addRow"],
QWidget#dbManagerPage QPushButton[dbTableActionRole="export"] {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; font-weight: 600;
}}
QWidget#dbManagerPage QPushButton#dbUtilityActionButton {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-radius: 4px;
padding-left: 0px; padding-right: 0px; font-size: 11px; font-weight: 650;
}}
QWidget#dbManagerPage QFrame#dbTableImportSeparator {{
background: {t.LINE_SOFT}; border: none; margin-left: 2px; margin-right: 2px;
}}
QWidget#dbManagerPage QPushButton:hover {{
background: {t.PANEL_2}; color: {t.TEXT}; border-color: {t.LINE};
}}
QWidget#dbManagerPage QPushButton[buttonRole="primary"] {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
}}
QWidget#dbManagerPage QPushButton[dbConnectionActionRole="connect"][dbPrimaryActive="true"]:enabled {{
background: #C45100; color: #FFF9F3; border: 1px solid #C45100;
}}
QWidget#dbManagerPage QPushButton:disabled,
QWidget#dbManagerPage QPushButton[buttonRole="primary"]:disabled,
QWidget#dbManagerPage QPushButton[dbPrimaryActive="false"]:disabled {{
background: #EEF1F4; color: #87919D; border: 1px solid #D4DAE1;
}}
QWidget#dbManagerPage QPushButton:focus {{
 border: 2px solid {t.LINE};
}}
QWidget#dbManagerPage QPushButton[dbTableActionRole="import"] {{
 background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE}; font-weight: 600;
}}
QWidget#dbManagerPage QPushButton[buttonRole="danger"],
QWidget#dbManagerPage QPushButton[dbTableActionRole="deleteRow"] {{
background: #FEF3F2; color: #B42318; border: 1px solid #FDA29B;
}}
QWidget#dbManagerPage QPushButton:disabled,
QWidget#dbManagerPage QPushButton[dbTableActionRole]:disabled,
QWidget#dbManagerPage QPushButton[dbConnectionActionRole]:disabled {{
background: #EEF1F4; color: #87919D; border: 1px solid #D4DAE1;
}}
QWidget#dbManagerPage QWidget#dbWelcomeTab {{
background: transparent; color: {t.TEXT}; border: none;
}}
QWidget#dbManagerPage QFrame#dbWelcomeCard {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 0px;
}}
QWidget#dbManagerPage QLabel#dbWelcomeTitle {{
color: {t.TEXT}; font-size: 16px; font-weight: 800;
}}
QWidget#dbManagerPage QLabel#dbWelcomeIntro,
QWidget#dbManagerPage QLabel#dbWelcomeHint,
QWidget#dbManagerPage QLabel#dbWelcomeStep,
QWidget#dbManagerPage QLabel#dbWelcomeCapabilityDesc {{
color: {t.MUTED};
}}
QWidget#dbManagerPage QLabel#dbWelcomeCapabilityHeading {{
color: {t.TEXT}; font-weight: 850;
}}
QWidget#dbManagerPage QLabel#dbWelcomeCapabilityTitle {{
color: {t.TEXT}; font-weight: 650;
}}
QWidget#dbManagerPage QWidget#dbWelcomeCapabilityItem {{
background: transparent; border: none;
}}
QWidget#dbManagerPage QLabel#dbWelcomeStatusPill {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px; font-weight: 650;
}}
QWidget#dbManagerPage QFrame#dbFilteredEmptyOverlay {{
background: {t.PANEL}; border: none; border-radius: 0px;
}}
QWidget#dbManagerPage QLabel#dbFilteredEmptyIcon {{
min-width: 42px; max-width: 42px; min-height: 42px; max-height: 42px;
background: {t.PANEL_2}; color: #5D6876; border: 1px solid {t.LINE}; border-radius: 6px;
font-family: Consolas; font-size: 18px; font-weight: 700;
}}
QWidget#dbManagerPage QLabel#dbFilteredEmptyTitle {{
color: {t.TEXT}; font-size: 16px; font-weight: 700;
}}
QWidget#dbManagerPage QLabel#dbFilteredEmptyDetail {{
color: {t.MUTED}; font-size: 12px;
}}
QWidget#dbManagerPage QPushButton#dbFilteredEmptyAction {{
min-height: 28px; padding-left: 12px; padding-right: 12px; border-radius: 4px;
}}
QFrame#currencyExchangeBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QGroupBox#currencyTableBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#currencyExchangeHeader,
QWidget#currencyExchangeRows,
QWidget#currencyInfoBar {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 0px;
}}
QWidget#currencyExchangeActions {{
background: transparent; color: {t.TEXT}; border: none;
}}
QWidget#currencyExchangeTitleRow,
QFrame#currencyExchangeSummaryBar {{
background: transparent; border: none;
}}
QLabel#currencyExchangeSummaryPill {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; font-weight: 700;
}}
QLabel#currencyExchangeSummaryPill[summaryRole="map"],
QLabel#currencyExchangeSummaryPill[summaryRole="rules"],
QLabel#currencyExchangeSummaryPill[summaryRole="coord"] {{
color: {t.TEXT};
}}
QLabel#currencyExchangeSummaryPill[summaryRole="npc"] {{
background: #FFF4E8; color: #9A4700; border-color: {t.LINE_SOFT}; font-weight: 650;
}}
QFrame#currencyExchangeRuleHeader {{
background: {t.PANEL_2}; color: {t.TEXT}; border: none; border-radius: 6px;
}}
QFrame#currencyExchangeRuleRow {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 6px;
}}
QFrame#currencyExchangeRuleRow[currencyRuleParity="even"] {{
background: {t.PANEL};
}}
QFrame#currencyExchangeRuleRow[currencyRuleParity="odd"] {{
background: {t.PANEL_2};
}}
QFrame#currencyExchangeSideBox {{
background: transparent; color: {t.TEXT}; border: none; border-radius: 6px;
}}
QGroupBox#currencyTableBox QWidget#currencyInfoBar,
QGroupBox#currencyTableBox QFrame#currencyTableHeader {{
background: {t.PANEL_2}; color: {t.TEXT}; border: none; border-radius: 6px;
}}
QGroupBox#currencyTableBox::title {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px;
font-weight: 800; padding: 1px 6px;
}}
QWidget#currencyTokenGrid {{
background: transparent; color: {t.TEXT}; border: 1px solid transparent; border-radius: 8px;
}}
QLabel#currencyRowTitleLabel {{
color: {t.MUTED}; font-weight: 850;
}}
QGroupBox#currencyTableBox QLabel#currencyCellLabel {{
background: transparent; color: {t.TEXT}; border: 1px solid transparent; border-radius: 7px;
font-weight: 800; padding: 0 5px;
}}
QGroupBox#currencyTableBox QLabel#currencyCellLabel[currencyCellRole="accent"] {{
background: transparent; color: #92400E; border-color: transparent; font-weight: 800;
}}
QGroupBox#currencyTableBox QLabel#currencyCellLabel[currencyCellRole="display"] {{
color: {t.MUTED}; background: {t.PANEL_2}; border-color: {t.LINE_SOFT}; font-weight: 700;
}}
QLabel#currencyPanelTitle,
QLabel#currencyExchangeRuleHeaderLabel,
QLabel#currencyExchangeFieldLabel,
QLabel#currencyExchangeRowLabel,
QLabel#currencyRowTitleLabel,
QLabel#currencyActionLabel {{
color: {t.TEXT};
}}
QLabel#currencyInfoText {{
color: {t.MUTED};
}}
QComboBox#currencyExchangeMapCombo,
QLineEdit#currencyExchangeNpcNameEdit,
QLineEdit#currencyExchangeNpcCoordEdit,
QLineEdit#currencyExchangeAmountEdit,
QLineEdit#currencyExchangeCustomEdit,
QComboBox#currencyExchangeTypeCombo {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QComboBox#currencyExchangeMapCombo QAbstractItemView,
QComboBox#currencyExchangeTypeCombo QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QLabel#currencyExchangeRuleIndex {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; font-weight: 800;
}}
QPushButton[currencyExchangeActionRole],
QPushButton#currencyExchangeGenerateScriptButton,
QPushButton#currencyConsumeButton,
QPushButton#currencyReloadButton,
QPushButton#currencyHelpButton,
QPushButton#currencyReferenceToggleButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
}}
QPushButton[currencyExchangeActionRole]:hover,
QPushButton#currencyExchangeGenerateScriptButton:hover,
QPushButton#currencyConsumeButton:hover,
QPushButton#currencyReloadButton:hover,
QPushButton#currencyHelpButton:hover,
QPushButton#currencyReferenceToggleButton:hover {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QPushButton#primaryButton[currencyExchangeActionRole="write"] {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
}}
QWidget#dropRatePage QFrame#dropRootBar,
QWidget#dropRatePage QFrame#dropDetailPanel,
QWidget#dropRatePage QScrollArea#dropTaskGridPanel,
QWidget#dropRatePage QWidget#dropTaskGridViewport,
QWidget#dropRatePage QWidget#dropTaskGridContent {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#dropRatePage QGroupBox#dropCallTaskCard,
QWidget#dropRatePage QGroupBox#dropOptTaskCard,
QWidget#dropRatePage QGroupBox#dropOverallOptTaskCard,
QWidget#dropRatePage QGroupBox#dropGroupTaskCard,
QWidget#dropRatePage QGroupBox#dropAddTaskCard,
QWidget#dropRatePage QGroupBox#dropDeleteTaskCard {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#dropRatePage QFrame#overallOptFormPanel,
QWidget#dropRatePage QGroupBox#addMonitemsBox,
QWidget#dropRatePage QPlainTextEdit#dropDeleteTextEditor {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
}}
QWidget#dropRatePage QFrame#callActionBar,
QWidget#dropRatePage QFrame#optActionBar,
QWidget#dropRatePage QFrame#groupActionBar,
QWidget#dropRatePage QFrame#deleteActionBar,
QWidget#dropRatePage QFrame#deletePickBar,
QWidget#dropRatePage QFrame#overallOptActionBar {{
background: transparent; border: none; border-radius: 4px;
}}
QWidget#dropRatePage QGroupBox#dropCallTaskCard::title,
QWidget#dropRatePage QGroupBox#dropOptTaskCard::title,
QWidget#dropRatePage QGroupBox#dropOverallOptTaskCard::title,
QWidget#dropRatePage QGroupBox#dropGroupTaskCard::title,
QWidget#dropRatePage QGroupBox#dropAddTaskCard::title,
QWidget#dropRatePage QGroupBox#dropDeleteTaskCard::title {{
subcontrol-origin: margin; subcontrol-position: top left; left: 10px;
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-radius: 0;
font-weight: 750; padding: 1px 6px;
}}
QWidget#dropRatePage QLabel {{
color: {t.TEXT};
}}
QWidget#dropRatePage QFrame#dropDetailHeader {{
background: transparent; border: none; border-radius: 4px; padding: 0 2px;
}}
QWidget#dropRatePage QLabel#dropDetailMetaLabel,
QWidget#dropRatePage QLabel#dropDetailMetaValue {{
color: {t.MUTED};
}}
QWidget#dropRatePage QLabel#dropPanelBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; font-weight: 650;
}}
QWidget#dropRatePage QLabel#dropDetailStatusBadge[badgeRole="info"] {{
background: #EFF6FF; color: #1D4ED8; border: 1px solid #BFDBFE; border-radius: 8px;
padding: 1px 8px; font-weight: 760;
}}
QWidget#dropRatePage QLabel#dropDetailStatusBadge[badgeRole="muted"] {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
padding: 1px 8px; font-weight: 760;
}}
QWidget#dropRatePage QLineEdit,
QWidget#dropRatePage QComboBox,
QWidget#dropRatePage QSpinBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#dropRatePage QComboBox QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#dropRatePage QPlainTextEdit#dropDetailLog {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px;
font-family: Consolas, "Microsoft YaHei UI"; font-size: 12px; padding: 3px 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QWidget#dropRatePage QProgressBar#dropDetailProgress {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 4px; text-align: center;
min-height: 12px; max-height: 12px; font-weight: 750;
}}
QWidget#dropRatePage QProgressBar#dropDetailProgress::chunk {{
background: #FFF7ED; border-radius: 5px; border: none;
}}
QWidget#dropRatePage QPushButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px; font-weight: 600;
}}
QWidget#dropRatePage QPushButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#dropRatePage QPushButton[buttonRole="primary"],
QWidget#dropRatePage QPushButton#primaryButton {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309; border-radius: 4px; font-weight: 650;
}}
QWidget#dropRatePage QFrame#callActionBar QPushButton,
QWidget#dropRatePage QFrame#optActionBar QPushButton,
QWidget#dropRatePage QFrame#groupActionBar QPushButton,
QWidget#dropRatePage QFrame#deleteActionBar QPushButton,
QWidget#dropRatePage QFrame#deletePickBar QPushButton,
QWidget#dropRatePage QFrame#overallOptActionBar QPushButton,
QWidget#dropRatePage QWidget#addMonitemsActions QPushButton {{
min-height: 24px;
max-height: 24px;
border-radius: 4px;
padding: 0 6px;
}}
QWidget#dropRatePage QFrame#overallOptActionBar QPushButton[buttonRole="primary"],
QWidget#dropRatePage QFrame#overallOptActionBar QPushButton#primaryButton {{
min-height: 28px; max-height: 28px; font-weight: 650;
}}
QWidget#dropRatePage QFrame#callActionBar QPushButton[buttonRole="primary"],
QWidget#dropRatePage QFrame#callActionBar QPushButton#primaryButton,
QWidget#dropRatePage QFrame#optActionBar QPushButton[buttonRole="primary"],
QWidget#dropRatePage QFrame#optActionBar QPushButton#primaryButton,
QWidget#dropRatePage QFrame#groupActionBar QPushButton[buttonRole="primary"],
QWidget#dropRatePage QFrame#groupActionBar QPushButton#primaryButton,
QWidget#dropRatePage QFrame#deleteActionBar QPushButton[buttonRole="primary"],
QWidget#dropRatePage QFrame#deleteActionBar QPushButton#primaryButton,
QWidget#dropRatePage QWidget#addMonitemsActions QPushButton[buttonRole="primary"],
QWidget#dropRatePage QWidget#addMonitemsActions QPushButton#primaryButton {{
min-width: 58px;
max-width: 58px;
}}
QWidget#dropRatePage QFrame#overallOptActionBar QPushButton[buttonRole="primary"],
QWidget#dropRatePage QFrame#overallOptActionBar QPushButton#primaryButton {{
min-width: 68px;
max-width: 68px;
}}
QWidget#dropRatePage QPushButton[buttonRole="danger"] {{
background: {t.PANEL}; color: #B42318; border: 1px solid #FCA5A5;
}}
QWidget#dropRatePage QFrame#callActionBar QPushButton[buttonRole="danger"],
QWidget#dropRatePage QFrame#optActionBar QPushButton[buttonRole="danger"],
QWidget#dropRatePage QFrame#groupActionBar QPushButton[buttonRole="danger"],
QWidget#dropRatePage QFrame#deleteActionBar QPushButton[buttonRole="danger"],
QWidget#dropRatePage QWidget#addMonitemsActions QPushButton[buttonRole="danger"] {{
min-width: 58px;
max-width: 58px;
}}
QWidget#dropRatePage QFrame#overallOptActionBar QPushButton[buttonRole="danger"] {{
min-width: 68px;
max-width: 68px;
}}
QWidget#dropRatePage QPushButton[buttonRole="danger"]:hover {{
background: #FFF7F5; color: #991B1B; border-color: #EF4444;
}}
QFrame#textSearchPanel {{
 background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#basicSearchToolbar,
QFrame#basicSearchEmptyPanel {{
 background: transparent; color: {t.TEXT}; border: none; border-radius: 0px;
}}
QWidget#basicSearchInputRow {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#basicSearchScopeOptions {{
background: {t.PANEL_2}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QFrame#basicSearchSummaryBar {{
background: transparent; border: none;
}}
QLabel#basicSearchSummaryPill {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; font-weight: 600;
}}
QLabel#basicSearchSummaryPill[summaryRole="path"],
QLabel#basicSearchSummaryPill[summaryRole="dedup"] {{
color: {t.TEXT};
}}
QLabel#basicSearchSummaryPill[summaryRole="scope"] {{
background: {t.PANEL}; color: #92400E; border-color: {t.LINE_SOFT};
}}
QLabel#basicSearchPanelTitle {{
color: {t.TEXT}; font-weight: 650;
}}
QLabel#basicSearchScopeLabel {{
color: {t.MUTED}; font-weight: 600; padding-right: 4px;
}}
QLabel#basicSearchStatus,
QLabel#basicSearchEmptyDetail {{
color: {t.MUTED};
}}
QLabel#basicSearchCountBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; padding: 0px 4px; font-weight: 650;
}}
QLabel#quickPathCountBadge {{
background: transparent; color: {t.MUTED}; border: none; border-radius: 0px; padding: 0px 2px; min-width: 0px; font-size: 12px; font-weight: 600;
}}
QComboBox#basicSearchModeCombo,
QComboBox#basicSearchTargetCombo,
QComboBox#basicSearchCombo {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QComboBox#basicSearchModeCombo QAbstractItemView,
QComboBox#basicSearchTargetCombo QAbstractItemView,
QComboBox#basicSearchCombo QAbstractItemView {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QTableWidget#basicSearchTable {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
alternate-background-color: {t.PANEL_2}; gridline-color: {t.LINE_SOFT};
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QTableWidget#basicSearchTable::item {{
color: {t.TEXT}; border-bottom: 1px solid {t.LINE_SOFT};
}}
QTableWidget#basicSearchTable::item:selected {{
background: #FFF7ED; color: #92400E;
}}
QTableWidget#basicSearchTable QHeaderView::section {{
background: {t.PANEL_2}; color: {t.MUTED}; border: none; border-bottom: 1px solid {t.LINE_SOFT};
}}
QPushButton#primaryButton[searchActionRole="search"] {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309;
}}
QPushButton#basicSearchClearButton {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid transparent; border-radius: 4px; font-weight: 600;
}}
QPushButton#basicSearchClearButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QFrame#compareFileBox,
QWidget#compareActionBar {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QLabel#compareFieldLabel {{
color: {t.TEXT}; font-weight: 700;
}}
QLabel#compareStatusLabel {{
background: {t.PANEL_2}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; font-weight: 700;
}}
QFrame#compareSummaryBar {{
background: transparent; border: none;
}}
QLabel#compareSummaryPill {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px; font-weight: 700;
}}
QLabel#compareSummaryPill[summaryRole="left"],
QLabel#compareSummaryPill[summaryRole="right"] {{
color: {t.MUTED};
}}
QLabel#compareSummaryPill[summaryRole="option"] {{
background: {t.PANEL_2}; color: #92400E;
}}
QLineEdit#comparePathEdit {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QToolButton#compareOptionButton {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-radius: 6px; font-weight: 750;
}}
QToolButton#compareOptionButton:checked,
QToolButton#compareOptionButton[compareOptionChecked="true"] {{
background: #FFF7ED; color: #92400E; border-color: transparent; font-weight: 750;
}}
QPlainTextEdit#compareTextEditor {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QPushButton#comparePickFileButton,
QWidget#compareActionBar QPushButton {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid transparent; border-radius: 6px; font-weight: 750;
}}
QPushButton#comparePickFileButton:hover,
QWidget#compareActionBar QPushButton:hover {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QWidget#compareActionBar QPushButton[compareActionRole="compare"],
QWidget#compareActionBar QPushButton#primaryButton {{
background: {t.BRAND}; color: #ffffff; border: 1px solid #B45309; font-weight: 850;
}}
QWidget#compareActionBar QPushButton[compareActionRole="previous"],
QWidget#compareActionBar QPushButton[compareActionRole="next"] {{
background: {t.PANEL_2}; color: {t.MUTED};
}}
QWidget#compareActionBar QPushButton[compareActionRole="saveLeft"],
QWidget#compareActionBar QPushButton[compareActionRole="saveRight"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE_SOFT};
}}
QFrame#compareEditorPane {{ background: transparent; border: none; }}
QLabel#compareEditorTitle {{
background: transparent; color: {t.MUTED}; border: none; font-weight: 750; padding: 2px 4px;
}}
QLabel#compareEditorTitle[compareSide="left"] {{ color: #B42318; }}
QLabel#compareEditorTitle[compareSide="right"] {{ color: #16803A; }}
QWidget#basicSettingsPage[compareRouteMode="true"] QFrame#compareFileBox,
QWidget#basicSettingsPage[compareRouteMode="true"] QWidget#compareActionBar,
QWidget#basicSettingsPage[compareRouteMode="true"] QPlainTextEdit#compareTextEditor {{
border-radius: 6px;
}}
QWidget#basicSettingsPage[compareRouteMode="true"] QLineEdit#comparePathEdit,
QWidget#basicSettingsPage[compareRouteMode="true"] QPushButton#comparePickFileButton,
QWidget#basicSettingsPage[compareRouteMode="true"] QToolButton#compareOptionButton,
QWidget#basicSettingsPage[compareRouteMode="true"] QWidget#compareActionBar QPushButton {{
border-radius: 4px;
}}
QFrame#basicRootBox,
QFrame#basicRootBox[basicWorkbenchMode="true"] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QFrame#quickPathPanel {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QLabel#basicRootTitle,
QFrame#quickPathPanel QLabel {{
color: {t.TEXT}; font-weight: 700;
}}
QLabel#basicRootStatus {{
color: {t.MUTED};
}}
QLineEdit#basicRootEdit {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QPushButton#basicRootBrowseButton {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
}}
QFrame#quickPathPanel QPushButton#quickPathButton {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-bottom-color: {t.LINE_SOFT}; border-radius: 0px;
}}
QPushButton#basicRootBrowseButton:hover,
QFrame#quickPathPanel QPushButton#quickPathButton:hover {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74; border-radius: 6px;
}}
QTabWidget#basicSettingsTabs::pane {{
background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 8px; margin-top: 4px;
}}
QTabWidget#basicSettingsTabs QTabBar::tab {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 6px;
padding: 3px 8px; min-height: 22px; min-width: 56px; margin-right: 4px;
}}
QTabWidget#basicSettingsTabs QTabBar::tab:selected {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QFrame#overviewActionPanel QPushButton#overviewQuickButton {{
min-height: 26px; max-height: 26px; border-radius: 4px;
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; font-weight: 600;
}}
QFrame#overviewActionPanel QPushButton#overviewQuickButton:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2; border-radius: 4px;
}}
QFrame#overviewActionPanel QPushButton#overviewQuickButton[buttonRole="secondary"],
QFrame#overviewActionPanel QPushButton#overviewQuickButton[buttonRole="quick"] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE};
}}
QFrame#overviewActionPanel QPushButton#overviewQuickButton[buttonRole="quick"]:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2; border-radius: 4px;
}}
QWidget#xiamiBotPage {{
background: {t.BG}; color: {t.TEXT};
}}
QWidget#xiamiAccountIdentityRow,
QWidget#xiamiAccountStateRow,
QWidget#xiamiPluginContextRow,
QWidget#xiamiPluginActionRow {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#xiamiAccountIdentityRow,
QWidget#xiamiAccountStateRow {{
min-height: 38px; max-height: 38px;
}}
QWidget#xiamiPluginContextRow,
QWidget#xiamiPluginActionRow {{
min-height: 36px; max-height: 36px;
}}
QLabel#xiamiAccountStateLabel,
QLabel#xiamiPluginActionHint,
QLabel#xiamiPluginLockLabel,
QLabel#xiamiPluginFilterCount {{
color: {t.MUTED};
}}
QWidget#xiamiBotPage QTabWidget#xiamiBotTabs::pane {{
background: {t.PANEL}; border: 1px solid {t.LINE_SOFT}; border-radius: 6px;
}}
QWidget#xiamiBotPage QTableWidget,
QWidget#xiamiBotPage QTextBrowser#xiamiPluginDetail {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT};
}}
QWidget#portsActionBar,
QFrame#portsGridBox,
QFrame#runGateBox {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE_SOFT}; border-radius: 8px;
}}
QWidget#portsActionBar {{
background: {t.PANEL_2}; border-color: {t.LINE_SOFT};
}}
QLabel#portsActionLabel {{
color: {t.MUTED}; font-weight: 800;
}}
QFrame#portsSummaryBar {{
background: transparent; border: none;
}}
QLabel#portsSummaryPill {{
background: {t.PANEL}; color: {t.MUTED}; border: 1px solid {t.LINE_SOFT}; border-radius: 7px;
font-weight: 700; padding: 0 8px;
}}
QLabel#portsSummaryPill[summaryRole="game"],
QLabel#portsSummaryPill[summaryRole="gate"],
QLabel#portsSummaryPill[summaryRole="log"] {{
color: {t.TEXT};
}}
QLabel#portsSummaryPill[summaryRole="ip"] {{
background: #FFF7ED; color: #92400E; border-color: #FDBA74;
}}
QLabel#portsSaveScopeLabel {{
color: {t.MUTED}; font-size: 12px; font-weight: 500;
}}
QLabel#portsPanelTitle,
QLabel#portsFieldLabel {{
color: {t.TEXT}; font-weight: 700;
}}
QFrame#portsPanelHeader,
QFrame#runGateHeader {{
background: {t.PANEL_2}; border: none; border-radius: 8px;
}}
QLabel#portsPanelTitle {{
color: {t.TEXT}; font-weight: 700;
}}
QLabel#portsPanelBadge {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-radius: 0; font-weight: 750;
}}
QLineEdit#portsGameNameEdit,
QLineEdit#portsIpEdit,
QLineEdit#portNumberEdit {{
background: {t.PANEL_2}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 7px;
selection-background-color: #FFF7ED; selection-color: #92400E;
}}
QCheckBox#portsLocalhostCheck,
QCheckBox#portsLogEnabledCheck,
QCheckBox#portsAutoSetupCheck,
QCheckBox[portsInlineToggle="true"],
QRadioButton[portsInlineToggle="true"],
QRadioButton {{
color: {t.TEXT};
}}
QCheckBox#portsLocalhostCheck::indicator,
QCheckBox#portsLogEnabledCheck::indicator,
QCheckBox#portsAutoSetupCheck::indicator,
QCheckBox[portsInlineToggle="true"]::indicator,
QRadioButton[portsInlineToggle="true"]::indicator,
QRadioButton::indicator {{
background: {t.PANEL}; border: 1px solid {t.LINE}; border-radius: 4px;
}}
QCheckBox#portsLocalhostCheck::indicator:checked,
QCheckBox#portsLogEnabledCheck::indicator:checked,
QCheckBox#portsAutoSetupCheck::indicator:checked,
QCheckBox[portsInlineToggle="true"]::indicator:checked,
QRadioButton[portsInlineToggle="true"]::indicator:checked {{
background: #FFF7ED; border-color: #FDBA74;
}}
QRadioButton::indicator:checked {{
background: {t.BRAND}; border-color: #B45309;
}}
QPushButton[portActionRole] {{
background: {t.PANEL}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
font-weight: 600;
}}
QPushButton[portActionRole]:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QPushButton[portActionRole][buttonRole="secondary"] {{
background: {t.PANEL}; color: {t.TEXT}; border-color: {t.LINE};
}}
QPushButton[portActionRole][buttonRole="tertiary"] {{
background: transparent; color: {t.MUTED}; border-color: transparent;
}}
QPushButton[portActionRole][buttonRole="tertiary"]:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: transparent;
}}
QPushButton[portActionRole][buttonRole="compact"] {{
background: {t.PANEL_2}; color: {t.MUTED}; border-color: {t.LINE_SOFT};
}}
QPushButton#primaryButton[portActionRole="save"] {{
background: {t.BRAND}; color: #ffffff; border: 1px solid {t.BRAND};
}}
QWidget#topContextBox QFrame[topContextCompact="true"],
QWidget#topContextBox QWidget[topContextCompact="true"] {{
background: transparent;
border: none;
border-radius: 0px;
padding: 0px;
min-height: 32px;
max-height: 32px;
}}
QWidget#topContextBox QPushButton[topContextCompact="true"],
QWidget#topContextBox QLineEdit[topContextCompact="true"],
QWidget#topContextBox QComboBox[topContextCompact="true"] {{
min-height: 28px;
max-height: 28px;
}}
QWidget#topContextBox QPushButton[topContextCompact="true"] {{
background: {t.PANEL};
color: {t.TEXT};
border: 1px solid {t.LINE};
border-radius: 4px;
font-weight: 600;
padding-left: 8px;
padding-right: 8px;
}}
QWidget#topContextBox QPushButton[buttonRole="primary"][topContextCompact="true"] {{
min-height: 30px;
max-height: 30px;
background: {t.BRAND};
color: #ffffff;
border: 1px solid {t.BRAND};
font-weight: 600;
}}
QWidget#topContextBox QPushButton[buttonRole="danger"][topContextCompact="true"] {{
background: #FEF3F2;
color: #B42318;
border: 1px solid #FCA5A5;
}}
QWidget#topContextBox QLineEdit[topContextCompact="true"],
QWidget#topContextBox QComboBox[topContextCompact="true"] {{
background: #FFFFFF;
color: {t.TEXT};
border: 1px solid {t.LINE};
border-radius: 7px;
padding-left: 7px;
padding-right: 7px;
}}
QWidget#darkWorkbenchRightShell,
QFrame#darkWorkbenchWorkspace,
QWidget#darkWorkbenchPageContent {{
background: {t.BG}; border: none;
}}
QFrame#darkWorkbenchSidebar {{
background: {t.CHROME}; border: none;
}}
QFrame#sidebarBrand {{
background: {t.CHROME}; border: none; border-bottom: 1px solid {t.LINE_SOFT};
}}
QLabel#sidebarBrandMark {{
background: transparent; border: none;
}}
QLabel#sidebarBrandName {{
color: {t.TEXT}; font-size: 15px; font-weight: 600;
}}
QWidget#sidebarSearchHost {{ background: {t.CHROME}; border: none; }}
QWidget#sidebarGlobalToolsHost,
QWidget#sidebarGlobalToolsHeader {{ background: {t.CHROME}; border: none; }}
QLabel#sidebarGlobalToolsTitle {{
 color: {t.MUTED}; font-size: 12px; font-weight: 600; border: none;
}}
QFrame#darkWorkbenchSidebar QPushButton[globalToolKey] {{
 min-height: 28px; max-height: 28px; padding: 0 6px;
 background: {t.CHROME}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
 font-size: 12px; font-weight: 600;
}}
QFrame#darkWorkbenchSidebar QPushButton[globalToolKey]:hover,
QFrame#darkWorkbenchSidebar QPushButton[globalToolKey]:focus {{
 background: #FFF7ED; border-color: #FDBA74; color: #92400E;
}}
QFrame#darkWorkbenchSidebar QPushButton[globalToolKey][globalToolConfigured="true"] {{
 background: #FFF4E6; border-color: #F59E0B; color: #7C2D12;
}}
QFrame#darkWorkbenchSidebar QPushButton[globalToolKey][dropState="hover"] {{
 background: #FEF3C7; border: 1px dashed #D97706; color: #7C2D12;
}}
QFrame#darkWorkbenchSidebar QLineEdit#sidebarSearchField {{
min-height: 32px; max-height: 32px; padding: 0 10px;
background: {t.CHROME}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
}}
QFrame#darkWorkbenchSidebar QLineEdit#sidebarSearchField:focus {{
border: 2px solid {t.BRAND}; padding: 0 9px;
}}
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll {{
background: {t.CHROME}; border: none;
}}
QFrame#darkWorkbenchSidebar QScrollArea#sidebarNavScroll > QWidget > QWidget {{
background: {t.CHROME};
}}
QFrame#darkWorkbenchSidebar QLabel[labelRole="section"] {{
min-height: 22px; max-height: 22px; padding: 0 12px;
color: {t.MUTED}; font-size: 12px; font-weight: 600; border: none;
}}
QFrame#darkWorkbenchSidebar QFrame[panelRole="nav"],
QFrame#darkWorkbenchSidebar QFrame[panelRole="nav-active"] {{
min-height: 32px; max-height: 32px; border: none; border-radius: 4px; margin: 0 8px;
}}
QFrame#darkWorkbenchSidebar QFrame[panelRole="nav"] {{ background: transparent; }}
QFrame#darkWorkbenchSidebar QFrame[panelRole="nav"]:hover {{ background: {t.PANEL_2}; }}
QFrame#darkWorkbenchSidebar QFrame[panelRole="nav-active"] {{ background: #FFF0E5; }}
QFrame#darkWorkbenchSidebar QFrame[panelRole="nav"][navDragging="true"],
QFrame#darkWorkbenchSidebar QFrame[panelRole="nav-active"][navDragging="true"] {{
 background: {t.PANEL_2}; border: 1px dashed {t.BRAND};
}}
QFrame#darkWorkbenchSidebar QFrame[navDropPosition="before"] {{
 border-top: 2px solid {t.BRAND};
}}
QFrame#darkWorkbenchSidebar QFrame[navDropPosition="after"] {{
 border-bottom: 2px solid {t.BRAND};
}}
QFrame#darkWorkbenchSidebar QFrame#navActiveIndicator[stateRole="active"] {{
min-width: 3px; max-width: 3px; min-height: 20px; max-height: 20px;
background: {t.BRAND}; border-radius: 1px;
}}
QFrame#darkWorkbenchSidebar QLabel[labelRole="nav"],
QFrame#darkWorkbenchSidebar QLabel[labelRole="nav-active"] {{
font-size: 13px; font-weight: 500; color: {t.TEXT};
}}
QFrame#darkWorkbenchSidebar QLabel[labelRole="nav-active"] {{ color: #A93F00; }}
QFrame#sidebarAccountPanel {{
background: {t.CHROME}; border: none; border-top: 1px solid {t.LINE}; border-radius: 0;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel[shellViewport="compact"] {{
min-height: 48px; max-height: 48px;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel[shellViewport="wide"] {{
min-height: 52px; max-height: 52px;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QLabel[labelRole="avatar"] {{
 min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
 border-radius: 7px; background: #FFF0E5; border: 1px solid #FDBA74;
 color: #A93F00; font-size: 12px; font-weight: 850;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QLabel[labelRole="strong"] {{
 color: {t.TEXT}; font-size: 12px; font-weight: 750;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QLabel[labelRole="muted"] {{
 color: {t.MUTED}; font-size: 10px; font-weight: 500;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QPushButton#accountLogoutButton {{
 min-width: 40px; max-width: 40px; min-height: 24px; max-height: 24px;
 padding: 0; border-radius: 4px; background: #FFF7F5; border: 1px solid #FCA5A5;
 color: #B42318; font-size: 11px; font-weight: 700;
}}
QFrame#darkWorkbenchSidebar QFrame#sidebarAccountPanel QPushButton#accountLogoutButton:hover {{
 background: #FFF0EF; border-color: #F97066; color: #912018;
}}
QFrame#darkWorkbenchSidebar QLineEdit#sidebarSearchField[shellViewport="compact"],
QFrame#darkWorkbenchSidebar QLineEdit#sidebarSearchField[shellViewport="wide"] {{
min-height: 30px; max-height: 30px;
}}
QFrame#darkWorkbenchProjectBar {{
background: {t.CHROME}; border: none; border-bottom: 1px solid {t.LINE};
}}
QFrame#darkWorkbenchProjectBar QLabel#projectRootDisplay {{
min-height: 30px; max-height: 30px; padding: 0 10px;
background: {t.CHROME}; color: {t.TEXT}; border: 1px solid {t.LINE}; border-radius: 4px;
font-family: "Consolas", "Microsoft YaHei UI";
}}
QFrame#darkWorkbenchProjectBar QPushButton#projectRootBrowseButton {{
min-width: 30px; max-width: 30px; min-height: 30px; max-height: 30px;
padding: 0; border-radius: 4px; background: {t.CHROME}; border: 1px solid {t.LINE};
}}
QLabel#brandVersionLabel {{ color: {t.MUTED}; font-size: 12px; font-weight: 500; }}
QLabel#shellUpdateState {{ color: #27845A; font-size: 12px; font-weight: 500; }}
QPushButton#sidebarCollapseButton {{
min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
background: transparent; color: {t.MUTED}; border: 1px solid transparent; border-radius: 4px;
font-size: 18px; font-weight: 500;
}}
QPushButton#sidebarCollapseButton:hover,
QPushButton#sidebarCollapseButton:focus {{
background: {t.PANEL_2}; color: {t.TEXT}; border-color: {t.LINE};
}}
QFrame#darkWorkbenchProjectBar QPushButton[buttonRole="icon"] {{
padding: 0; background: {t.CHROME}; color: {t.MUTED}; border: none; border-radius: 4px;
}}
QFrame#darkWorkbenchProjectBar QPushButton[buttonRole="icon"]:hover {{ background: {t.PANEL_2}; color: {t.TEXT}; }}
QFrame#darkWorkbenchProjectBar QPushButton#windowCloseButton:hover {{ background: #FFF0EF; color: #B83A32; }}
QFrame#windowControlSeparator {{ background: {t.LINE}; border: none; }}
QFrame#darkWorkbenchBreadcrumbBar {{
background: {t.CHROME}; border: none; border-bottom: 1px solid {t.LINE_SOFT};
}}
QLabel#shellBreadcrumbLabel {{ color: {t.MUTED}; font-size: 13px; font-weight: 400; }}
QWidget#shellPageTitleRow {{ background: transparent; border: none; }}
QLabel#shellPageTitle {{
color: {t.TEXT}; font-size: 20px; font-weight: 600; letter-spacing: 0px;
}}
QFrame#darkWorkbenchStatusBar {{
background: {t.CHROME}; border: none; border-top: 1px solid {t.LINE};
}}
QFrame#darkWorkbenchStatusBar QLabel {{ color: {t.MUTED}; font-size: 12px; font-weight: 500; }}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"] {{
background: {t.CHROME}; color: {t.TEXT}; border: 1px solid {t.LINE};
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"]:hover {{
background: #F7F8FA; color: {t.TEXT}; border-color: #B9C2CC;
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"]:pressed {{
background: #EEF1F4; color: {t.TEXT}; border-color: #87919D;
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"]:focus {{
background: {t.CHROME}; color: {t.TEXT}; border: 1px solid #E66A00;
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"]:checked {{
background: #FFF0E5; color: #A93F00; border: 1px solid #E66A00;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"] {{
background: #C45100; color: #FFF9F3; border: 1px solid #C45100;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"]:hover {{
background: #B94700; color: #FFF9F3; border-color: #B94700;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"]:pressed {{
background: #A93F00; color: #FFF9F3; border-color: #A93F00;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"]:focus {{
background: #C45100; color: #FFF9F3; border: 1px solid #E66A00;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"]:checked {{
background: #FFF0E5; color: #A93F00; border: 1px solid #E66A00;
}}
QWidget#darkWorkbenchWindow QWidget[surfaceRole="content"],
QWidget#darkWorkbenchWindow QFrame[surfaceRole="content"] {{
background: #FCFDFE;
}}
QWidget#darkWorkbenchWindow QWidget[surfaceRole="muted"],
QWidget#darkWorkbenchWindow QFrame[surfaceRole="muted"] {{
background: #F7F8FA;
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"] {{
border-radius: 4px;
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"][segmentPosition="first"] {{
border-top-left-radius: 4px; border-bottom-left-radius: 4px;
border-top-right-radius: 0px; border-bottom-right-radius: 0px;
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"][segmentPosition="middle"] {{
border-radius: 0px; border-left: none;
}}
QWidget#darkWorkbenchWindow QPushButton[controlRole="segmented"][segmentPosition="last"] {{
border-top-left-radius: 0px; border-bottom-left-radius: 0px;
border-top-right-radius: 4px; border-bottom-right-radius: 4px;
border-left: none;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="danger"],
QWidget#darkWorkbenchWindow QPushButton[searchActionRole="search"],
QWidget#darkWorkbenchWindow QPushButton[searchActionRole="stop"],
QWidget#darkWorkbenchWindow QPushButton#basicSearchClearButton {{
border-radius: 4px;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="danger"] {{
min-height: 30px;
max-height: 30px;
font-size: 13px;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="compact"] {{
font-weight: 500;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="compact"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="segmented"] {{
min-height: 26px;
max-height: 26px;
border-radius: 4px;
font-size: 13px;
font-weight: 600;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="icon"] {{
min-width: 26px; max-width: 26px; min-height: 26px; max-height: 26px;
padding: 0; font-size: 13px; font-weight: 600;
background: #FCFDFE; color: {t.MUTED}; border: 1px solid {t.LINE};
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"] {{
background: #FCFDFE; color: {t.TEXT}; border: 1px solid #D4DAE1; font-weight: 600;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"] {{
background: transparent; color: {t.MUTED}; border: 1px solid transparent; font-weight: 600;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="compact"],
QWidget#darkWorkbenchWindow QPushButton[buttonRole="segmented"] {{
background: #FCFDFE; color: {t.TEXT}; border: 1px solid #D4DAE1;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="danger"] {{
background: #FFF0EF; color: #B83A32; border: 1px solid #E5A6A2; font-weight: 600;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"]:hover,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"]:hover,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="compact"]:hover,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="segmented"]:hover,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="icon"]:hover {{
background: #EEF1F4; color: {t.TEXT}; border-color: #AEB7C2;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="danger"]:hover {{
background: #FEE2E2; color: #991B1B; border-color: #B42318;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"]:focus,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"]:focus,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"]:focus,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="danger"]:focus,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="compact"]:focus,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="segmented"]:focus,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="icon"]:focus {{
border: 1px solid #E66A00;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"]:pressed {{
background: #A93F00; color: #FFF9F3; border-color: #A93F00;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"]:pressed,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"]:pressed,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="compact"]:pressed,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="segmented"]:pressed,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="icon"]:pressed {{
background: #E5E9ED; color: {t.TEXT}; border-color: #87919D;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="danger"]:pressed {{
background: #FECACA; color: #7F1D1D; border-color: #991B1B;
}}
QWidget#darkWorkbenchWindow QPushButton[buttonRole="primary"]:disabled,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="secondary"]:disabled,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="tertiary"]:disabled,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="danger"]:disabled,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="compact"]:disabled,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="segmented"]:disabled,
QWidget#darkWorkbenchWindow QPushButton[buttonRole="icon"]:disabled {{
background: #F1F3F5; color: #98A2B3; border: 1px solid #E1E5EA;
}}
QWidget#darkWorkbenchWindow QComboBox#basicSearchCombo {{
border-radius: 4px;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand,
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchResultsPanel,
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel {{
border-radius: 6px;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QComboBox#basicSearchCombo,
QWidget#basicSettingsPage[searchRouteMode="true"] QPushButton[searchActionRole="search"],
QWidget#basicSettingsPage[searchRouteMode="true"] QPushButton[searchActionRole="stop"],
QWidget#basicSettingsPage[searchRouteMode="true"] QPushButton#basicSearchClearButton,
QWidget#basicSettingsPage[searchRouteMode="true"] QPushButton#quickPathButton {{
border-radius: 4px;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand,
QWidget#basicSettingsPage[searchRouteMode="true"] QWidget#basicSearchInputRow,
QWidget#basicSettingsPage[searchRouteMode="true"] QWidget#basicSearchScopeOptions,
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchResultsPanel,
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel {{
border-radius: 6px;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QLabel#basicSearchSummaryPill,
QWidget#basicSettingsPage[searchRouteMode="true"] QLabel#basicSearchResultsTitle,
QWidget#basicSettingsPage[searchRouteMode="true"] QLabel#basicSearchPanelTitle,
QWidget#basicSettingsPage[searchRouteMode="true"] QLabel#quickPathPanelTitle {{
font-weight: 600;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand QCheckBox[searchScopeOption="true"],
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand QPushButton[controlRole="segmented"],
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel QPushButton#quickPathCategory {{
font-weight: 600;
border-radius: 4px;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel QPushButton#quickPathCategory {{
min-height: 28px;
max-height: 28px;
min-width: 40px;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand QCheckBox[searchScopeOption="true"]:hover,
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand QPushButton[controlRole="segmented"]:hover,
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel QPushButton#quickPathCategory:hover,
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel QPushButton#quickPathButton:hover {{
background: #EEF1F4;
color: {t.TEXT};
border-color: #AEB7C2;
border-radius: 4px;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand QPushButton[controlRole="segmented"]:checked {{
background: {t.BRAND};
color: #FFF9F3;
border-color: #B94700;
font-weight: 700;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#basicSearchFilterBand QCheckBox#basicSearchDeduplicate:checked {{
background: transparent;
color: {t.TEXT};
border-color: transparent;
font-weight: 600;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel QPushButton#quickPathCategory:checked {{
background: transparent;
color: {t.BRAND};
border-bottom-color: {t.BRAND};
font-weight: 650;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QPushButton#basicSearchClearButton {{
background: transparent;
color: {t.MUTED};
border-color: transparent;
font-weight: 600;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QPushButton#basicSearchClearButton:hover,
QWidget#basicSettingsPage[searchRouteMode="true"] QPushButton#basicSearchClearButton:pressed {{
background: #EEF1F4;
color: {t.TEXT};
border-color: #AEB7C2;
}}
QWidget#basicSettingsPage[searchRouteMode="true"] QFrame#quickPathPanel QPushButton#quickPathButton {{
background: transparent;
color: {t.MUTED};
border-color: transparent;
border-bottom-color: {t.LINE_SOFT};
font-weight: 600;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QFrame#currencyExchangeBox,
QWidget#basicSettingsPage[currencyRouteMode="true"] QGroupBox#currencyTableBox,
QWidget#basicSettingsPage[currencyRouteMode="true"] QWidget#currencyInfoBar {{
border-radius: 6px;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QWidget#currencyExchangeHeader,
QWidget#basicSettingsPage[currencyRouteMode="true"] QWidget#currencyExchangeRows,
QWidget#basicSettingsPage[currencyRouteMode="true"] QWidget#currencyTokenGrid {{
border-radius: 6px;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QFrame#currencyExchangeRuleHeader,
QWidget#basicSettingsPage[currencyRouteMode="true"] QFrame#currencyExchangeRuleRow,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeRuleIndex,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeSummaryPill,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyPanelBadge,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyCellLabel,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyColumnHeaderLabel,
QWidget#basicSettingsPage[currencyRouteMode="true"] QWidget#currencyInfoActions {{
border-radius: 4px;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QFrame#currencyExchangeRuleHeader,
QWidget#basicSettingsPage[currencyRouteMode="true"] QFrame#currencyExchangeRuleRow {{
border-radius: 4px;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeSummaryPill,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyPanelBadge,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeRuleIndex,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyColumnHeaderLabel,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyRowTitleLabel,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyCellLabel {{
font-weight: 600;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeSummaryPill,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeSummaryPill[summaryRole="map"],
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeSummaryPill[summaryRole="npc"],
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeSummaryPill[summaryRole="coord"],
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeSummaryPill[summaryRole="rules"],
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyCellLabel[currencyCellRole="accent"],
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyCellLabel[currencyCellRole="display"],
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyExchangeRuleIndex {{
background: {t.PANEL_2};
color: {t.MUTED};
border-color: {t.LINE_SOFT};
font-weight: 600;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QLabel#currencyPanelBadge {{
background: transparent;
color: {t.MUTED};
border-color: transparent;
font-weight: 600;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QComboBox#currencyExchangeMapCombo,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeNpcNameEdit,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeNpcCoordEdit,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeAmountEdit,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeCustomEdit,
QWidget#basicSettingsPage[currencyRouteMode="true"] QComboBox#currencyExchangeTypeCombo {{
min-height: 32px;
max-height: 32px;
border-radius: 4px;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QComboBox#currencyExchangeMapCombo:focus,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeNpcNameEdit:focus,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeNpcCoordEdit:focus,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeAmountEdit:focus,
QWidget#basicSettingsPage[currencyRouteMode="true"] QLineEdit#currencyExchangeCustomEdit:focus,
QWidget#basicSettingsPage[currencyRouteMode="true"] QComboBox#currencyExchangeTypeCombo:focus {{
border-color: {t.BRAND};
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton[currencyExchangeActionRole],
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyExchangeGenerateScriptButton,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyConsumeButton,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyReloadButton,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyHelpButton,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyReferenceToggleButton {{
min-height: 26px;
max-height: 26px;
background: {t.PANEL};
color: {t.TEXT};
border: 1px solid {t.LINE};
border-radius: 4px;
font-weight: 600;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton[currencyExchangeActionRole]:hover,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyExchangeGenerateScriptButton:hover,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyConsumeButton:hover,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyReloadButton:hover,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyHelpButton:hover,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyReferenceToggleButton:hover {{
background: #EEF1F4;
color: {t.TEXT};
border-color: #AEB7C2;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyHelpButton,
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyReferenceToggleButton {{
background: transparent;
color: {t.MUTED};
border-color: transparent;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#currencyReferenceToggleButton:checked {{
background: {t.PANEL_2};
color: {t.TEXT};
border-color: {t.LINE};
font-weight: 650;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#primaryButton[currencyExchangeActionRole="write"] {{
min-height: 30px;
max-height: 30px;
background: #C45100;
color: #FFF9F3;
border-color: #C45100;
font-weight: 650;
}}
QWidget#basicSettingsPage[currencyRouteMode="true"] QPushButton#primaryButton[currencyExchangeActionRole="write"]:hover {{
background: #B94700;
color: #FFF9F3;
border-color: #B94700;
}}
"""


def prepare_dark_workbench_app(app: QtWidgets.QApplication) -> None:
    app.setStyle("Fusion")
    font = QtGui.QFont()
    if hasattr(font, "setFamilies"):
        font.setFamilies(["Segoe UI", "Microsoft YaHei UI"])
    else:
        font.setFamily("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)








