# PyInstaller runtime hook: start crash logging before importing the GUI entry module.
import os
import sys

from toolbox_crash_logging import install_runtime_logging


def _install_windows_hard_exit():
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return
    try:
        import ctypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        get_current_process = kernel32.GetCurrentProcess
        get_current_process.argtypes = []
        get_current_process.restype = ctypes.c_void_p
        terminate_process = kernel32.TerminateProcess
        terminate_process.argtypes = [ctypes.c_void_p, ctypes.c_uint]
        terminate_process.restype = ctypes.c_int
        original_exit = os._exit

        def _hard_exit(code):
            exit_code = int(code) & 0xFFFFFFFF
            if not terminate_process(get_current_process(), exit_code):
                original_exit(int(code))
            while True:
                pass

        os._exit = _hard_exit
    except Exception:
        pass


install_runtime_logging("frozen-bootstrap")
_install_windows_hard_exit()
