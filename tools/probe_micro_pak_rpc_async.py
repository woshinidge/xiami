# -*- coding: utf-8 -*-
"""Focused lifecycle probe for the micro-client PAK RPC worker."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")

import toolbox_core_rpc as core_rpc  # noqa: E402
import 工具箱_qt as toolbox  # noqa: E402
from PySide2 import QtCore, QtWidgets  # noqa: E402


def _fill(page, template: Path, legend: Path, pak: Path, name: str) -> None:
    page._form_lock = True
    try:
        page.name_edit.setText(name)
        page.pak_edit.setText(str(pak))
        page.ip_edit.setText("127.0.0.1")
        page.server_port_spin.setValue(7000)
        page.list_port_spin.setValue(7100)
        page.legend_dir_edit.setText(str(legend))
        page.patch_dir_edit.setText("PatchA")
        page.micro_tpl_dir_edit.setText(str(template))
        page.password_edit.setText("V8M2")
        page.no_cache_chk.setChecked(False)
        page.micro_port_spin.setValue(7200)
        index = page.engine_combo.findText("GEE LF V8 GXX")
        page.engine_combo.setCurrentIndex(index if index >= 0 else 0)
    finally:
        page._form_lock = False
    page._on_form_changed()


def main() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    qt_messages = []
    old_qt_handler = QtCore.qInstallMessageHandler(
        lambda _kind, _context, message: qt_messages.append(str(message))
    )
    old_encrypt = toolbox.encrypt_micro_pak_passwords
    old_root = toolbox._MicroClientConfigPage._get_micro_configs_root_dir
    old_question = QtWidgets.QMessageBox.question
    old_warning = QtWidgets.QMessageBox.warning
    old_information = QtWidgets.QMessageBox.information
    old_env = {key: os.environ.get(key) for key in ("LOCALAPPDATA", "APPDATA")}
    checks = {}
    details = {}
    page = None
    try:
        with tempfile.TemporaryDirectory(prefix="xiami-rpc-async-") as temp_text:
            temp = Path(temp_text)
            local = temp / "local"
            roaming = temp / "roaming"
            micro_root = temp / "micro-root"
            template = temp / "template"
            legend = temp / "legend"
            for path in (local, roaming, micro_root, template, legend):
                path.mkdir(parents=True, exist_ok=True)
            (template / "template.bin").write_bytes(b"template")
            pak = temp / "pak.txt"
            pak.write_bytes((r"D:\Old\PatchA\Data\a.pak|password" + "\r\n").encode("gbk"))
            os.environ["LOCALAPPDATA"] = str(local)
            os.environ["APPDATA"] = str(roaming)
            toolbox._MicroClientConfigPage._get_micro_configs_root_dir = staticmethod(
                lambda: str(micro_root)
            )
            messages = []
            QtWidgets.QMessageBox.question = staticmethod(
                lambda *_args, **_kwargs: QtWidgets.QMessageBox.Yes
            )
            QtWidgets.QMessageBox.warning = staticmethod(
                lambda _parent, title, text, *_args, **_kwargs: messages.append(
                    ("warning", str(title), str(text))
                ) or QtWidgets.QMessageBox.Ok
            )
            QtWidgets.QMessageBox.information = staticmethod(
                lambda _parent, title, text, *_args, **_kwargs: messages.append(
                    ("information", str(title), str(text))
                ) or QtWidgets.QMessageBox.Ok
            )

            page = toolbox._MicroClientConfigPage(lambda: {})
            page._status_timer.stop()
            page._status_scan_timer.stop()
            page._defer_style_timer.stop()
            page.show()
            app.processEvents()

            main_thread = threading.get_ident()
            worker_threads = []
            heartbeat = {"ticks": 0, "disabled": False, "status": "", "duplicate": False}

            def slow_success(*, session, passwords, client_version, allow_local_http=False):
                worker_threads.append(threading.get_ident())
                time.sleep(0.18)
                return ["AA" * (len(value.encode("gbk")) + 1) for value in passwords]

            toolbox.encrypt_micro_pak_passwords = slow_success
            timer = QtCore.QTimer()
            timer.setInterval(10)

            def observe() -> None:
                heartbeat["ticks"] += 1
                heartbeat["disabled"] = heartbeat["disabled"] or not page.create_btn.isEnabled()
                dialog = page._pak_rpc_dialog
                if dialog is not None:
                    heartbeat["status"] = str(dialog.status_label.text())
                if not heartbeat["duplicate"] and page._pak_rpc_thread is not None:
                    try:
                        page._run_micro_pak_rpc(["duplicate"])
                    except RuntimeError:
                        heartbeat["duplicate"] = True

            timer.timeout.connect(observe)
            timer.start()
            result = page._run_micro_pak_rpc(["password"])
            timer.stop()
            checks["rpc_runs_off_main_thread"] = bool(worker_threads) and all(
                value != main_thread for value in worker_threads
            )
            checks["ui_heartbeat_and_progress_visible"] = (
                heartbeat["ticks"] >= 3
                and heartbeat["disabled"]
                and "PAK" in heartbeat["status"]
            )
            checks["duplicate_submit_blocked"] = heartbeat["duplicate"]
            checks["success_result_and_cleanup"] = (
                len(result) == 1
                and page.create_btn.isEnabled()
                and page._pak_rpc_thread is None
                and page._pak_rpc_worker is None
            )
            details["heartbeat"] = heartbeat

            class DeletedThreadWrapper:
                def isRunning(self):
                    raise RuntimeError("Internal C++ object already deleted")

                def deleteLater(self):
                    raise RuntimeError("Internal C++ object already deleted")

            page._pak_rpc_thread = DeletedThreadWrapper()
            page._pak_rpc_worker = object()
            page.create_btn.setEnabled(False)
            page._on_pak_rpc_thread_finished()
            checks["deleted_qthread_wrapper_cleans_refs"] = (
                page._pak_rpc_thread is None
                and page._pak_rpc_worker is None
                and page.create_btn.isEnabled()
            )

            late_cancel_dialog = toolbox._MicroPakRpcProgressDialog(page)
            late_cancel_dialog.mark_cancel_requested()
            late_cancel_dialog.finish({"ok": True, "encoded": ["AA"]})
            checks["late_cancel_overrides_success_payload"] = (
                late_cancel_dialog.result == {"ok": False, "cancelled": True}
            )
            late_cancel_dialog.deleteLater()

            class BlockingThread:
                def __init__(self):
                    self.running = True
                    self.wait_calls = []

                def quit(self):
                    return None

                def wait(self, *args):
                    self.wait_calls.append(args)
                    if not args:
                        self.running = False
                    return not self.running

                def isRunning(self):
                    return self.running

                def deleteLater(self):
                    return None

            class StoppableWorker:
                def __init__(self):
                    self.stopped = False

                def request_stop(self):
                    self.stopped = True

            blocking_thread = BlockingThread()
            blocking_worker = StoppableWorker()
            page._pak_rpc_thread = blocking_thread
            page._pak_rpc_worker = blocking_worker
            page._on_app_about_to_quit()
            checks["about_to_quit_waits_for_worker"] = (
                blocking_worker.stopped
                and blocking_thread.wait_calls == [(35000,), ()]
                and page._pak_rpc_thread is None
                and page._pak_rpc_worker is None
            )
            page._closing = False

            class IgnoredCloseEvent:
                def __init__(self):
                    self.ignored = False

                def ignore(self):
                    self.ignored = True

            original_stop_rpc = page._stop_micro_pak_rpc
            close_event = IgnoredCloseEvent()
            page._status_timer.start(1000)
            page._stop_micro_pak_rpc = lambda *_args, **_kwargs: False
            try:
                page.closeEvent(close_event)
                checks["rejected_close_restores_active_timers"] = (
                    close_event.ignored
                    and not page._closing
                    and page._status_timer.isActive()
                )
            finally:
                page._status_timer.stop()
                page._stop_micro_pak_rpc = original_stop_rpc

            toolbox.encrypt_micro_pak_passwords = slow_success
            QtCore.QTimer.singleShot(
                30,
                lambda: page._pak_rpc_dialog._request_cancel()
                if page._pak_rpc_dialog is not None
                else None,
            )
            cancelled = False
            try:
                page._run_micro_pak_rpc(["password"])
            except toolbox._MicroPakRpcCancelled:
                cancelled = True
            checks["cancel_is_transaction_free_and_cleans_thread"] = (
                cancelled
                and page._pak_rpc_thread is None
                and page._pak_rpc_worker is None
                and page.create_btn.isEnabled()
            )

            def slow_failure(**_kwargs):
                time.sleep(0.12)
                raise core_rpc.CoreRpcTransportError(
                    "network unavailable after cancel",
                    code="network_error",
                    retryable=True,
                )

            toolbox.encrypt_micro_pak_passwords = slow_failure
            QtCore.QTimer.singleShot(
                30,
                lambda: page._pak_rpc_dialog._request_cancel()
                if page._pak_rpc_dialog is not None
                else None,
            )
            cancel_overrode_error = False
            try:
                page._run_micro_pak_rpc(["password"])
            except toolbox._MicroPakRpcCancelled:
                cancel_overrode_error = True
            checks["cancel_overrides_rpc_error"] = (
                cancel_overrode_error
                and page._pak_rpc_thread is None
                and page._pak_rpc_worker is None
                and page.create_btn.isEnabled()
            )

            target = micro_root / "异步失败"
            target.mkdir()
            marker = target / "keep.bin"
            marker.write_bytes(b"do-not-replace")
            _fill(page, template, legend, pak, "异步失败")

            def network_failure(**_kwargs):
                raise core_rpc.CoreRpcTransportError(
                    "network unavailable",
                    code="network_error",
                    retryable=True,
                )

            toolbox.encrypt_micro_pak_passwords = network_failure
            page._create_or_update()
            residues = sorted(
                path.name
                for path in micro_root.iterdir()
                if ".xiami-stage-" in path.name or ".xiami-backup-" in path.name
            )
            warning_text = "\n".join(text for kind, _title, text in messages if kind == "warning")
            checks["network_failure_is_explicit"] = (
                "network_error" in warning_text and "目标目录未发生替换" in warning_text
            )
            checks["network_failure_does_not_replace_target"] = (
                marker.read_bytes() == b"do-not-replace" and not residues
            )
            details["network_warning"] = warning_text

            toolbox.encrypt_micro_pak_passwords = slow_success
            page._closing = False
            QtCore.QTimer.singleShot(30, page.close)
            close_cancelled = False
            try:
                page._run_micro_pak_rpc(["password"])
            except toolbox._MicroPakRpcCancelled:
                close_cancelled = True
            app.processEvents()
            checks["page_close_is_worker_safe"] = (
                close_cancelled
                and page._pak_rpc_thread is None
                and page._pak_rpc_worker is None
                and not any("QThread: Destroyed" in value for value in qt_messages)
            )
    finally:
        if page is not None:
            page._stop_micro_pak_rpc(35000, close_dialog=True)
            page.deleteLater()
            app.processEvents()
        toolbox.encrypt_micro_pak_passwords = old_encrypt
        toolbox._MicroClientConfigPage._get_micro_configs_root_dir = old_root
        QtWidgets.QMessageBox.question = old_question
        QtWidgets.QMessageBox.warning = old_warning
        QtWidgets.QMessageBox.information = old_information
        QtCore.qInstallMessageHandler(old_qt_handler)
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    payload = {
        "passed": all(checks.values()),
        "checks": checks,
        "details": details,
        "qt_messages": qt_messages,
    }
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
