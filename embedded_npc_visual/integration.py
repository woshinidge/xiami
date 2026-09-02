from __future__ import annotations

import os
import re
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PySide2 import QtCore, QtWidgets

from embedded_npc_visual.ui_qt.npc_visual_support import NpcToolContext
from embedded_npc_visual.ui_qt.npc_visual_v2_page import NpcVisualV2Page


@dataclass(frozen=True)
class QuickNpcEntry:
    index: int
    map_path: str
    map_code: str
    map_name: str
    npc_name: str
    coord: str
    script_path: str
    script_candidates: tuple[str, ...]
    raw_line: str


class _AsyncDispatcher(QtCore.QObject):
    completed = QtCore.Signal(int, object, object)

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="npc-visual")
        self._closed = False
        self._lock = threading.Lock()
        self._next_task_id = 0
        self._callbacks: dict[
            int, tuple[Callable[[object], None], Callable[[BaseException], None]]
        ] = {}
        self.completed.connect(self._deliver)

    def submit(
        self,
        work: Callable[[], object],
        success: Callable[[object], None],
        failed: Callable[[BaseException], None],
    ) -> None:
        if self._closed:
            failed(RuntimeError("NPC 可视化任务调度器已关闭"))
            return
        with self._lock:
            self._next_task_id += 1
            task_id = self._next_task_id
            self._callbacks[task_id] = (success, failed)
        future = self._executor.submit(work)
        future.add_done_callback(
            lambda completed, current_task_id=task_id: self._collect(
                current_task_id, completed
            )
        )

    def _collect(
        self,
        task_id: int,
        future: Future,
    ) -> None:
        try:
            result = future.result()
        except BaseException as exc:
            self.completed.emit(task_id, None, exc)
        else:
            self.completed.emit(task_id, result, None)

    @QtCore.Slot(int, object, object)
    def _deliver(self, task_id: int, result: object, error: object) -> None:
        with self._lock:
            callbacks = self._callbacks.pop(task_id, None)
        if callbacks is None:
            return
        success, failed = callbacks
        callback = failed if error is not None else success
        payload = error if error is not None else result
        if callable(callback):
            callback(payload)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        with self._lock:
            callbacks = list(self._callbacks.values())
            self._callbacks.clear()
        error = RuntimeError("NPC 可视化任务调度器已关闭")
        for _success, failed in callbacks:
            failed(error)
        self._executor.shutdown(wait=False)


class XiamiNpcVisualHost(QtCore.QObject):
    def __init__(self, toolbox_context: object, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.toolbox_context = toolbox_context
        self.page: NpcVisualV2Page | None = None
        self.dispatcher = _AsyncDispatcher(self)
        settings_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "XiamiToolbox"
        settings_dir.mkdir(parents=True, exist_ok=True)
        self.settings = QtCore.QSettings(str(settings_dir / "npc_visual.ini"), QtCore.QSettings.IniFormat)
        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    def build_page(self, parent: QtWidgets.QWidget | None = None) -> NpcVisualV2Page:
        self.page = NpcVisualV2Page(parent, self.tool_context())
        return self.page

    def tool_context(self) -> NpcToolContext:
        return NpcToolContext(
            get_version_path=self.get_version_path,
            get_login_folder=self.get_login_folder,
            choose_version=self.choose_version,
            load_npcs=self.load_npcs,
            read_text_file=self.read_text_file,
            run_async=self.dispatcher.submit,
            get_database_path=self.get_database_path,
            get_engine_family=self.get_engine_family,
            get_patch_folder=self.get_patch_folder,
            get_client_folder=self.get_client_folder,
            choose_patch_folder=self.choose_patch_folder,
            get_session=self.get_session,
        )

    def get_session(self) -> dict | None:
        for name in ("get_native_session", "get_session"):
            getter = getattr(self.toolbox_context, name, None)
            if not callable(getter):
                continue
            session = getter()
            if isinstance(session, dict):
                result = dict(session)
                epoch_getter = getattr(self.toolbox_context, "get_session_epoch", None)
                if callable(epoch_getter):
                    try:
                        result["_auth_epoch"] = int(epoch_getter())
                    except (TypeError, ValueError):
                        pass
                return result
        return None

    def get_version_path(self) -> str:
        getter = getattr(self.toolbox_context, "get_root_dir", None)
        value = str(getter() or "").strip() if callable(getter) else ""
        return os.path.normpath(value) if value and os.path.isdir(value) else ""

    def choose_version(self) -> None:
        chooser = getattr(self.toolbox_context, "choose_project_root", None)
        if callable(chooser):
            chooser(self.page)

    def get_login_folder(self) -> str:
        version = self.get_version_path()
        if not version:
            return ""
        for relative in ("登录器", "Login", "login"):
            candidate = os.path.join(version, relative)
            if os.path.isdir(candidate):
                return os.path.normpath(candidate)
        try:
            children = [child for child in Path(version).iterdir() if child.is_dir()]
            for child in children:
                if (child / "pak.txt").is_file():
                    return os.path.normpath(str(child))
            for child in children:
                if child.is_dir() and (child / "Config.ini").is_file():
                    return os.path.normpath(str(child))
        except OSError:
            pass
        return ""

    def get_client_folder(self) -> str:
        """Only the client the user actually picked.

        get_patch_folder falls back to a root-derived 补丁文件夹, which must not
        be mistaken for an explicit client choice: doing so ties the project-root
        selection to the client selection.
        """
        configured = str(
            self.settings.value("paths/client", "")
            or self.settings.value("paths/patch", "")
            or ""
        ).strip()
        if configured and os.path.isdir(configured):
            return os.path.normpath(configured)
        return ""

    def get_patch_folder(self) -> str:
        configured = str(
            self.settings.value("paths/client", "")
            or self.settings.value("paths/patch", "")
            or ""
        ).strip()
        if configured and os.path.isdir(configured):
            return os.path.normpath(configured)
        login = self.get_login_folder()
        for relative in ("补丁文件夹", "Patch", "patch"):
            candidate = os.path.join(login, relative) if login else ""
            if candidate and os.path.isdir(candidate):
                return os.path.normpath(candidate)
        return ""

    def choose_patch_folder(self) -> None:
        initial = self.get_patch_folder() or self.get_login_folder() or self.get_version_path()
        selected = QtWidgets.QFileDialog.getExistingDirectory(
            self.page, "选择游戏客户端目录", initial
        )
        if not selected:
            return
        normalized = os.path.normpath(selected)
        self.settings.setValue("paths/client", normalized)
        self.settings.setValue("paths/patch", normalized)
        self.settings.sync()

    def get_database_path(self) -> str:
        version = self.get_version_path()
        if not version:
            return ""
        for relative in (("Mud2", "DB"), ("mud2", "db"), ("DB",)):
            candidate = os.path.join(version, *relative)
            if os.path.isdir(candidate):
                return os.path.normpath(candidate)
        return ""

    def get_engine_family(self) -> str:
        version = self.get_version_path()
        m2_path = os.path.join(version, "Mir200", "M2Server.exe") if version else ""
        try:
            size = os.path.getsize(m2_path)
        except OSError:
            return "lf"
        return "gom" if size < 10 * 1024 * 1024 or size == 7437312 else "lf"

    @staticmethod
    def read_text_file(path: str) -> tuple[str, str]:
        data = Path(path).read_bytes()
        for encoding in ("utf-8-sig", "gb18030", "cp936"):
            try:
                return data.decode(encoding), encoding
            except UnicodeDecodeError:
                continue
        return data.decode("gb18030", errors="replace"), "gb18030"

    def load_npcs(self) -> list[QuickNpcEntry]:
        merchant = self._merchant_file()
        if not merchant:
            return []
        text, _encoding = self.read_text_file(merchant)
        return self._parse_merchant(text)

    def _merchant_file(self) -> str:
        version = self.get_version_path()
        envir = Path(version) / "Mir200" / "Envir" if version else None
        if envir is None or not envir.is_dir():
            return ""
        for name in ("MerChant.txt", "Merchant.txt", "MERCHANT.TXT", "MerChant.TXT"):
            candidate = envir / name
            if candidate.is_file():
                return str(candidate)
        try:
            return str(next(path for path in envir.iterdir() if path.name.casefold() == "merchant.txt"))
        except (OSError, StopIteration):
            return ""

    def _parse_merchant(self, text: str) -> list[QuickNpcEntry]:
        version = self.get_version_path()
        map_names = self._load_map_names()
        entries: list[QuickNpcEntry] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith(";"):
                continue
            parts = re.split(r"\s+", line)
            if len(parts) < 5:
                continue
            map_path, map_code, x_value, y_value, npc_name = parts[:5]
            map_parts = [part for part in re.split(r"[\\/]+", map_path.strip()) if part]
            market_def = os.path.join(version, "Mir200", "Envir", "Market_Def")
            script_dir = os.path.join(market_def, map_parts[0]) if map_parts else market_def
            candidates = self._script_candidates(script_dir, map_path, map_code)
            script_path = candidates[0] if candidates else os.path.join(script_dir, f"{npc_name}.txt")
            entries.append(
                QuickNpcEntry(
                    index=len(entries) + 1,
                    map_path=map_path,
                    map_code=map_code,
                    map_name=map_names.get(self._normalize_map_code(map_code), map_path),
                    npc_name=npc_name,
                    coord=f"{x_value} {y_value}",
                    script_path=os.path.normpath(script_path),
                    script_candidates=candidates,
                    raw_line=raw_line,
                )
            )
        return entries

    def _load_map_names(self) -> dict[str, str]:
        version = self.get_version_path()
        path = Path(version) / "Mir200" / "Envir" / "MapInfo.txt" if version else None
        if path is None or not path.is_file():
            return {}
        try:
            text, _encoding = self.read_text_file(str(path))
        except OSError:
            return {}
        result: dict[str, str] = {}
        for line in text.splitlines():
            match = re.match(r"^\s*\[([^\]]+)\]", line)
            if not match:
                continue
            header_match = re.match(r"^(\S+)\s+(.+)$", match.group(1).strip())
            if not header_match:
                continue
            codes, display_name = header_match.groups()
            for code in codes.split("|"):
                normalized = self._normalize_map_code(code)
                if normalized and normalized not in result:
                    result[normalized] = display_name.strip()
        return result

    @staticmethod
    def _normalize_map_code(value: str) -> str:
        code = str(value or "").strip()
        if code.upper().startswith("N") and code[1:].isdigit():
            return code[1:].zfill(4)
        if code.isdigit():
            return code.zfill(4) if len(code) > 1 else code
        return code.upper()

    @staticmethod
    def _script_candidates(script_dir: str, map_path: str, map_code: str) -> tuple[str, ...]:
        parts = [part for part in re.split(r"[\\/]+", map_path.strip()) if part]
        if not parts:
            return ()
        code = str(map_code or "").strip()
        match = re.fullmatch(r"([A-Za-z])(\d+)", code)
        if match:
            prefix, digits = match.groups()
            codes = [f"{prefix.upper()}{digits}", f"{prefix.upper()}{digits[-2:].zfill(2)}"]
        else:
            codes = [code] if code else []
        if not codes:
            return (os.path.normpath(os.path.join(script_dir, f"{parts[-1]}.txt")),)
        return tuple(
            dict.fromkeys(
                os.path.normpath(os.path.join(script_dir, f"{parts[-1]}-{candidate}.txt"))
                for candidate in codes
            )
        )

    def shutdown(self) -> None:
        self.dispatcher.shutdown()


__all__ = ["QuickNpcEntry", "XiamiNpcVisualHost"]
