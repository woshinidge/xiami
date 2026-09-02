from __future__ import annotations

import subprocess
from pathlib import Path

from xiami_core.path_alias import alias_path
from xiami_core.windows_process import hidden_check_output, hidden_run


def terminate_process_tree(pid: int, timeout: float = 5.0) -> None:
    if pid <= 0:
        return
    try:
        hidden_run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return


def terminate_processes_for_workdir(workdir: Path, timeout: float = 5.0) -> None:
    markers = {str(workdir.resolve()).lower(), str(alias_path(workdir)).lower()}
    try:
        output = hidden_check_output(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                (
                    "Get-CimInstance Win32_Process | "
                    "Select-Object ProcessId,ParentProcessId,ExecutablePath,CommandLine | "
                    "ConvertTo-Json -Compress"
                ),
            ],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return
    processes = _parse_process_json(output)
    matched: set[int] = set()
    by_pid = {process["pid"]: process for process in processes if process["pid"]}
    children: dict[int, list[int]] = {}
    for process in processes:
        children.setdefault(process["ppid"], []).append(process["pid"])
    for process in processes:
        haystack = f"{process['command_line']}\n{process['executable_path']}".lower()
        if process["pid"] and any(marker in haystack for marker in markers):
            matched.add(process["pid"])
    for pid in list(matched):
        parent = by_pid.get(by_pid.get(pid, {}).get("ppid", 0), {})
        parent_command = str(parent.get("command_line") or "").lower()
        if parent.get("pid") and "napcat.bat" in parent_command:
            matched.add(parent["pid"])
    for pid in list(matched):
        matched.update(_descendants(pid, children))
    for pid in sorted(matched, reverse=True):
        terminate_process_tree(pid)


def _parse_process_json(output: str) -> list[dict[str, object]]:
    import json

    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        data = [data]
    result: list[dict[str, object]] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        try:
            pid = int(item.get("ProcessId") or 0)
        except (TypeError, ValueError):
            pid = 0
        try:
            ppid = int(item.get("ParentProcessId") or 0)
        except (TypeError, ValueError):
            ppid = 0
        command_line = str(item.get("CommandLine") or "")
        executable_path = str(item.get("ExecutablePath") or "")
        result.append(
            {
                "pid": pid,
                "ppid": ppid,
                "command_line": command_line,
                "executable_path": executable_path,
            }
        )
    return result


def _descendants(pid: int, children: dict[int, list[int]]) -> set[int]:
    result: set[int] = set()
    stack = list(children.get(pid, []))
    while stack:
        child = stack.pop()
        if child in result:
            continue
        result.add(child)
        stack.extend(children.get(child, []))
    return result
