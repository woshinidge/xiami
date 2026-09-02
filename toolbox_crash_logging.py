# -*- coding: utf-8 -*-
from __future__ import annotations

import atexit
import faulthandler
import os
import platform
import sys
import tempfile
import threading
from datetime import datetime


_LOCK = threading.RLock()
_LOG_FP = None
_LOG_PATH = ""
_INSTALLED = False
_ORIGINAL_SYS_EXCEPTHOOK = None
_ORIGINAL_THREAD_EXCEPTHOOK = None
_ORIGINAL_UNRAISABLEHOOK = None


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def _log_directory() -> str:
    base = str(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or "").strip()
    if not base:
        base = tempfile.gettempdir()
    path = os.path.join(base, "XiamiToolbox", "logs")
    os.makedirs(path, exist_ok=True)
    return path


def _archive_unclean_log(path: str) -> None:
    if not os.path.isfile(path):
        return
    try:
        with open(path, "rb") as fp:
            fp.seek(max(0, os.path.getsize(path) - 8192))
            tail = fp.read().decode("utf-8", errors="ignore")
        if " clean_exit " not in tail:
            stamp = datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y%m%d-%H%M%S")
            archived = os.path.join(os.path.dirname(path), "xm_toolbox_crash_%s.log" % stamp)
            suffix = 1
            while os.path.exists(archived):
                archived = os.path.join(
                    os.path.dirname(path), "xm_toolbox_crash_%s_%d.log" % (stamp, suffix)
                )
                suffix += 1
            os.replace(path, archived)
    except Exception:
        return


def _prune_archives(directory: str, keep: int = 8) -> None:
    try:
        paths = [
            os.path.join(directory, name)
            for name in os.listdir(directory)
            if name.startswith("xm_toolbox_crash_") and name.endswith(".log")
        ]
        paths.sort(key=lambda item: os.path.getmtime(item), reverse=True)
        for path in paths[keep:]:
            try:
                os.remove(path)
            except Exception:
                pass
    except Exception:
        pass


def log_path() -> str:
    return _LOG_PATH


def write_event(tag: str, detail: str = "") -> None:
    fp = _LOG_FP
    if fp is None:
        return
    safe_tag = str(tag or "event").replace("\r", " ").replace("\n", " ")
    safe_detail = str(detail or "").replace("\r", " ").replace("\n", "\\n")
    line = "%s %s" % (_timestamp(), safe_tag)
    if safe_detail:
        line += " " + safe_detail
    try:
        with _LOCK:
            fp.write(line + "\n")
            fp.flush()
    except Exception:
        pass


def write_block(tag: str, detail: str) -> None:
    fp = _LOG_FP
    if fp is None:
        return
    try:
        with _LOCK:
            fp.write("%s %s\n%s\n" % (_timestamp(), str(tag or "event"), str(detail or "")))
            fp.flush()
    except Exception:
        pass


def _safe_argv_flags() -> str:
    flags = []
    for value in sys.argv[1:]:
        text = str(value or "")
        if text.startswith("-"):
            flags.append(text.split("=", 1)[0])
    return ",".join(flags)


def _windows_details() -> str:
    if sys.platform != "win32":
        return ""
    try:
        version = sys.getwindowsversion()
        remote = int(bool(__import__("ctypes").windll.user32.GetSystemMetrics(0x1000)))
        return "windows=%d.%d.%d service_pack=%s remote_session=%d" % (
            int(version.major),
            int(version.minor),
            int(version.build),
            str(version.service_pack or "none"),
            remote,
        )
    except Exception as exc:
        return "windows_details_error=%s" % type(exc).__name__


def _bootstrap_excepthook(exc_type, value, tb) -> None:
    try:
        import traceback

        write_block("bootstrap_unhandled", "".join(traceback.format_exception(exc_type, value, tb)))
    except Exception:
        write_event("bootstrap_unhandled", "%s: %s" % (exc_type, value))
    if callable(_ORIGINAL_SYS_EXCEPTHOOK):
        try:
            _ORIGINAL_SYS_EXCEPTHOOK(exc_type, value, tb)
        except Exception:
            pass


def _bootstrap_thread_excepthook(args) -> None:
    try:
        import traceback

        text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        write_block("bootstrap_thread_unhandled", text)
    except Exception:
        write_event("bootstrap_thread_unhandled", "format_failed")
    if callable(_ORIGINAL_THREAD_EXCEPTHOOK):
        try:
            _ORIGINAL_THREAD_EXCEPTHOOK(args)
        except Exception:
            pass


def _bootstrap_unraisablehook(args) -> None:
    try:
        import traceback

        text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        write_block("bootstrap_unraisable", text)
    except Exception:
        write_event("bootstrap_unraisable", "format_failed")
    if callable(_ORIGINAL_UNRAISABLEHOOK):
        try:
            _ORIGINAL_UNRAISABLEHOOK(args)
        except Exception:
            pass


def install_runtime_logging(version: str = "") -> str:
    global _INSTALLED, _LOG_FP, _LOG_PATH
    global _ORIGINAL_SYS_EXCEPTHOOK, _ORIGINAL_THREAD_EXCEPTHOOK, _ORIGINAL_UNRAISABLEHOOK
    if _INSTALLED:
        if version:
            write_event("runtime_version", version)
        return _LOG_PATH
    _INSTALLED = True
    try:
        directory = _log_directory()
        path = os.path.join(directory, "xm_toolbox_crash.log")
        _archive_unclean_log(path)
        _prune_archives(directory)
        _LOG_FP = open(path, "w", encoding="utf-8", errors="backslashreplace", buffering=1)
        _LOG_PATH = path
        os.environ["XM_TOOLBOX_CRASH_LOG"] = path
    except Exception:
        _LOG_FP = None
        _LOG_PATH = ""
        return ""

    write_event("session_start", "version=%s pid=%d" % (version or "unknown", os.getpid()))
    write_event(
        "runtime",
        "python=%s executable=%s frozen=%d arch=%s cpu=%s" % (
            platform.python_version(),
            os.path.basename(sys.executable),
            int(bool(getattr(sys, "frozen", False))),
            platform.machine() or "unknown",
            os.cpu_count() or "unknown",
        ),
    )
    write_event("platform", platform.platform())
    windows = _windows_details()
    if windows:
        write_event("windows", windows)
    write_event(
        "session",
        "name=%s flags=%s cwd=%s" % (
            str(os.environ.get("SESSIONNAME") or "unknown"),
            _safe_argv_flags() or "none",
            os.getcwd(),
        ),
    )
    write_event(
        "qt_environment",
        "QT_OPENGL=%s QT_QPA_PLATFORM=%s QT_QUICK_BACKEND=%s" % (
            str(os.environ.get("QT_OPENGL") or "default"),
            str(os.environ.get("QT_QPA_PLATFORM") or "default"),
            str(os.environ.get("QT_QUICK_BACKEND") or "default"),
        ),
    )
    try:
        faulthandler.enable(file=_LOG_FP, all_threads=True)
        write_event("faulthandler_enabled")
    except Exception as exc:
        write_event("faulthandler_error", repr(exc))

    _ORIGINAL_SYS_EXCEPTHOOK = sys.excepthook
    sys.excepthook = _bootstrap_excepthook
    if hasattr(threading, "excepthook"):
        _ORIGINAL_THREAD_EXCEPTHOOK = threading.excepthook
        threading.excepthook = _bootstrap_thread_excepthook
    if hasattr(sys, "unraisablehook"):
        _ORIGINAL_UNRAISABLEHOOK = sys.unraisablehook
        sys.unraisablehook = _bootstrap_unraisablehook
    atexit.register(lambda: write_event("runtime_atexit"))
    return _LOG_PATH


def mark_clean_exit(code: int = 0) -> None:
    write_event("clean_exit", "code=%d" % int(code))

