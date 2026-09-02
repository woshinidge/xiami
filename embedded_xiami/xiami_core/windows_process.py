from __future__ import annotations

from contextlib import contextmanager
import ctypes
import subprocess
import sys
from typing import Any


@contextmanager
def suppress_system_error_dialogs():
    """Suppress native Windows loader/error popups for background helper processes."""
    if sys.platform != "win32":
        yield
        return
    kernel32 = ctypes.windll.kernel32
    sem_fail_critical_errors = 0x0001
    sem_no_gp_fault_error_box = 0x0002
    sem_no_open_file_error_box = 0x8000
    mode = sem_fail_critical_errors | sem_no_gp_fault_error_box | sem_no_open_file_error_box
    previous = kernel32.SetErrorMode(mode)
    old_thread_mode = ctypes.c_uint(0)
    thread_mode_changed = False
    set_thread_error_mode = getattr(kernel32, "SetThreadErrorMode", None)
    if set_thread_error_mode is not None:
        try:
            set_thread_error_mode.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_uint)]
            set_thread_error_mode.restype = ctypes.c_int
            thread_mode_changed = bool(set_thread_error_mode(mode, ctypes.byref(old_thread_mode)))
        except Exception:
            thread_mode_changed = False
    try:
        yield
    finally:
        if thread_mode_changed and set_thread_error_mode is not None:
            try:
                set_thread_error_mode(old_thread_mode.value, None)
            except Exception:
                pass
        try:
            kernel32.SetErrorMode(previous)
        except Exception:
            pass


def hidden_subprocess_kwargs() -> dict[str, object]:
    if sys.platform != "win32":
        return {}

    kwargs: dict[str, object] = {}
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    if creationflags:
        kwargs["creationflags"] = creationflags

    if hasattr(subprocess, "STARTUPINFO"):
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo

    return kwargs


def hidden_run(*popenargs: Any, **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    kwargs.update(hidden_subprocess_kwargs())
    return subprocess.run(*popenargs, **kwargs)


def hidden_check_output(*popenargs: Any, **kwargs: Any) -> Any:
    kwargs.update(hidden_subprocess_kwargs())
    return subprocess.check_output(*popenargs, **kwargs)
