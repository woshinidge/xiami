from __future__ import annotations

from pathlib import Path
import os
import subprocess
import shutil
import shlex
import sys
import time

from xiami_core.kernels.base import LoginKernel
from xiami_core.kernels.process_tree import terminate_process_tree, terminate_processes_for_workdir
from xiami_core.kernels.process_output import ProcessOutputBuffer
from xiami_core.models import AccountStatus, SendResult
from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.onebot.stats import OneBotActionStats
from xiami_core.path_alias import alias_arg, alias_path
from xiami_core.storage.config import KernelConfig
from xiami_core.storage.paths import KERNEL_HOME, PROJECT_ROOT
from xiami_core.windows_process import hidden_subprocess_kwargs, suppress_system_error_dialogs


class ExternalOneBotKernel(LoginKernel):
    name = "External OneBot"

    def __init__(self, config: KernelConfig | None = None) -> None:
        self.config = config or KernelConfig(kind=self.name)
        self._status = AccountStatus(state="offline", detail="未启动")
        self._process: subprocess.Popen[bytes] | None = None
        self._output = ProcessOutputBuffer()
        self._qr_hint_cache = ""
        self._qr_scan_at = 0.0
        self._start_wall_time = 0.0
        self.action_stats = OneBotActionStats()

    def prepare(self) -> AccountStatus:
        if not self.config.executable:
            self._status = AccountStatus(state="error", detail=f"{self.name} 尚未配置启动程序")
            return self._status
        path = Path(self.config.executable)
        if path.parent != Path(".") and not path.exists():
            self._status = AccountStatus(state="error", detail=f"启动程序不存在：{path}")
            return self._status
        if path.parent == Path(".") and shutil.which(self.config.executable) is None:
            self._status = AccountStatus(state="error", detail=f"启动命令不可用：{self.config.executable}")
            return self._status
        command = _build_command(path, self.config.arguments or [], Path(self.config.working_dir or path.parent))
        compatibility_error = _node_command_compatibility_error(self.name, command)
        if compatibility_error:
            self._status = AccountStatus(state="error", detail=compatibility_error)
            return self._status
        self._status = AccountStatus(state="offline", detail=f"{self.name} 已配置")
        return self._status

    def start_login(self, account: str = "") -> AccountStatus:
        ready = self.prepare()
        if ready.state == "error":
            return ready
        if self._process and self._process.poll() is None:
            self._status = AccountStatus(state="starting", account=account.strip(), detail=f"{self.name} 已在运行")
            return self.status()
        self._reset_qr_cache(remove_files=True)
        self._start_wall_time = time.time()
        executable = Path(self.config.executable)
        cwd = self.config.working_dir or str(executable.parent)
        if self.config.working_dir:
            terminate_processes_for_workdir(Path(self.config.working_dir))
            time.sleep(0.5)
        command = _build_command(executable, self.config.arguments or [], Path(cwd))
        launch_cwd = str(alias_path(cwd))
        try:
            with suppress_system_error_dialogs():
                self._process = subprocess.Popen(
                    command,
                    cwd=launch_cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=_launch_env(command),
                    **hidden_subprocess_kwargs(),
                )
            self._output.attach(self._process)
        except OSError as exc:
            self._status = AccountStatus(state="error", account=account.strip(), detail=f"启动失败：{exc}")
            return self._status
        early_error = self._early_start_failure(command)
        if early_error:
            self._status = AccountStatus(
                state="error",
                account=account.strip(),
                detail=early_error,
                logs=self._output.snapshot(),
                qr_hint="",
            )
            return self._status
        self._status = AccountStatus(
            state="starting",
            account=account.strip(),
            detail=f"{self.name} 已启动，等待 OneBot 连接",
            logs=self._output.snapshot(),
            qr_hint=self._output.qr_hint(),
        )
        return self._status

    def _early_start_failure(self, command: list[str]) -> str:
        if self._process is None:
            return ""
        try:
            exit_code = self._process.wait(timeout=0.8)
        except subprocess.TimeoutExpired:
            return ""
        time.sleep(0.05)
        return _startup_failure_detail(self.name, command, exit_code, self._output.snapshot(80))

    def stop(self) -> AccountStatus:
        if self._process and self._process.poll() is None:
            terminate_process_tree(self._process.pid)
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
        if self.config.working_dir:
            terminate_processes_for_workdir(Path(self.config.working_dir))
        self._reset_qr_cache(remove_files=True)
        self._process = None
        self._status = AccountStatus(state="offline", detail=f"{self.name} 已停止", logs=self._output.snapshot(), qr_hint="")
        return self._status

    def status(self) -> AccountStatus:
        client = self._client(timeout=1.0)
        service_status = client.get_status()
        if service_status.ok and isinstance(service_status.data, dict):
            online = bool(service_status.data.get("online"))
            if online:
                account = self._status.account or _account_from_config(self.config)
                self._status = AccountStatus(
                    state="online",
                    account=account,
                    detail=f"{self.name} OneBot 已连接",
                    logs=self._output.snapshot(),
                    qr_hint=self._discover_qr_hint(),
                )
                return self._status
        login = client.get_login_info()
        if login.ok and isinstance(login.data, dict):
            account = str(login.data.get("user_id") or login.data.get("uin") or self._status.account)
            nickname = str(login.data.get("nickname") or "")
            detail = f"{self.name} OneBot 已连接"
            if nickname:
                detail += f"：{nickname}"
            self._status = AccountStatus(
                state="online",
                account=account,
                detail=detail,
                logs=self._output.snapshot(),
                qr_hint=self._discover_qr_hint(),
            )
            return self._status
        version = client.get_version()
        onebot_ready = version.ok or service_status.ok
        if onebot_ready:
            qr_hint = self._discover_qr_hint()
            self._status = AccountStatus(
                state="starting",
                account=self._status.account,
                detail=f"{self.name} OneBot HTTP 已启动，等待登录信息",
                logs=self._output.snapshot(),
                qr_hint=qr_hint,
            )
            return self._status
        if self._process and self._process.poll() is None:
            qr_hint = self._discover_qr_hint()
            self._status = AccountStatus(
                state="waiting_qr" if qr_hint else "starting",
                account=self._status.account,
                detail=f"{self.name} 已启动，OneBot 未就绪：{login.message}",
                logs=self._output.snapshot(),
                qr_hint=qr_hint,
            )
            return self._status
        if self._process and self._process.poll() is not None and self._status.state in {"starting", "waiting_qr"}:
            exit_code = int(self._process.poll() or 0)
            self._status = AccountStatus(
                state="error",
                account=self._status.account,
                detail=_startup_failure_detail(self.name, _build_command(Path(self.config.executable), self.config.arguments or [], Path(self.config.working_dir or Path(self.config.executable).parent)), exit_code, self._output.snapshot(80)),
                logs=self._output.snapshot(),
                qr_hint="",
            )
            return self._status
        qr_hint = self._discover_qr_hint()
        if qr_hint and self._status.state != "online":
            self._status = AccountStatus(
                state="waiting_qr",
                account=self._status.account,
                detail=f"{self.name} 等待扫码，OneBot 未就绪：{login.message}",
                logs=self._output.snapshot(),
                qr_hint=qr_hint,
            )
            return self._status
        if self._status.state == "waiting_qr":
            self._status = AccountStatus(
                state="starting",
                account=self._status.account,
                detail=f"{self.name} 未发现本次启动生成的二维码，OneBot 不可访问：{login.message}",
                logs=self._output.snapshot(),
                qr_hint="",
            )
            return self._status
        if self._status.state == "starting":
            self._status = AccountStatus(
                state="error",
                account=self._status.account,
                detail=f"{self.name} 未运行或 OneBot 不可访问：{login.message}",
                logs=self._output.snapshot(),
                qr_hint=qr_hint,
            )
        return self._status

    def send_message(self, target: str, text: str, message_type: str = "private") -> SendResult:
        if not target.strip():
            return SendResult(ok=False, detail="缺少发送目标")
        if not text.strip():
            return SendResult(ok=False, detail="缺少发送内容")
        status = self.status()
        if status.state != "online":
            return SendResult(ok=False, detail=f"OneBot 未在线：{status.detail}")
        client = self._client()
        if message_type == "group":
            response = client.send_group_msg(target, text)
        else:
            response = client.send_private_msg(target, text)
        message_id = ""
        if isinstance(response.data, dict):
            message_id = str(response.data.get("message_id") or "")
        if response.ok:
            detail = f"真实发送成功，message_id={message_id}" if message_id else "真实发送成功"
        else:
            detail = f"真实发送失败：{response.message}"
        return SendResult(ok=response.ok, detail=detail, message_id=message_id)

    def _client(self, timeout: float = 2.0) -> OneBotHttpClient:
        return OneBotHttpClient(self.config.http_url, self.config.access_token, timeout=timeout, action_stats=self.action_stats)

    def _discover_qr_hint(self) -> str:
        hint = self._output.qr_hint()
        if hint:
            self._qr_hint_cache = hint
            return hint
        if self._qr_hint_cache and _is_fresh_qr_file(Path(self._qr_hint_cache), self._start_wall_time):
            return self._qr_hint_cache
        workdir = Path(self.config.working_dir or Path(self.config.executable).parent)
        now = time.monotonic()
        if now - self._qr_scan_at < 2.0:
            if self._qr_hint_cache and _is_fresh_qr_file(Path(self._qr_hint_cache), self._start_wall_time):
                return self._qr_hint_cache
            return ""
        self._qr_scan_at = now
        candidates = []
        for fixed in (
            workdir / "napcat" / "cache" / "qrcode.png",
            workdir / "cache" / "qrcode.png",
            workdir / "qrcode.png",
            workdir / "qr-0.png",
            workdir / "qr_code.png",
        ):
            if fixed.is_file():
                candidates.append(fixed)
        files = [path for path in candidates if _is_fresh_qr_file(path, self._start_wall_time)]
        if not files:
            return ""
        latest = max(files, key=lambda path: _safe_mtime(path))
        self._qr_hint_cache = str(latest)
        return self._qr_hint_cache

    def _reset_qr_cache(self, remove_files: bool = False) -> None:
        self._qr_hint_cache = ""
        self._qr_scan_at = 0.0
        if not remove_files:
            return
        workdir = Path(self.config.working_dir or Path(self.config.executable).parent)
        for path in (
            workdir / "napcat" / "cache" / "qrcode.png",
            workdir / "cache" / "qrcode.png",
            workdir / "qrcode.png",
            workdir / "qr-0.png",
            workdir / "qr_code.png",
        ):
            try:
                if path.is_file():
                    path.unlink()
            except OSError:
                continue


def _safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _is_fresh_qr_file(path: Path, start_wall_time: float) -> bool:
    mtime = _safe_mtime(path)
    if not mtime:
        return False
    if start_wall_time and mtime + 0.001 < start_wall_time:
        return False
    return path.is_file()


def _build_command(executable: Path, args: list[str], cwd: Path) -> list[str]:
    launch_executable = alias_path(executable)
    launch_args = [alias_arg(arg) for arg in args]
    suffix = executable.suffix.lower()
    if suffix in {".bat", ".cmd"}:
        direct_command = _direct_command_from_simple_batch(executable, launch_args)
        if direct_command:
            return direct_command
        launch_name = launch_executable.name if launch_executable.parent == alias_path(cwd) else str(launch_executable)
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/s", "/c", "call", launch_name, *launch_args]
    return [str(launch_executable), *launch_args]


def _launch_env(command: list[str]) -> dict[str, str]:
    env = dict(os.environ)
    if _command_uses_node(command):
        # Node 20+/22+ blocks older Windows builds at runtime.  On Server 2012/2012 R2
        # the binary can still be attempted only after this flag; truly missing APIs are
        # handled by the early-start failure path without showing a native loader dialog.
        env.setdefault("NODE_SKIP_PLATFORM_CHECK", "1")
    return env


def _command_uses_node(command: list[str]) -> bool:
    if not command:
        return False
    name = Path(str(command[0])).name.lower()
    return name in {"node.exe", "node"}


def _startup_failure_detail(name: str, command: list[str], exit_code: int, logs: tuple[str, ...]) -> str:
    joined = "\n".join(str(line) for line in logs if str(line).strip())
    lower = joined.lower()
    command_text = " ".join(str(part) for part in command[:4])
    if "provided qq path is invalid" in lower or "registry key or value" in lower:
        return (
            f"{name} 启动失败：当前服务器没有可用的 QQNT 注册表路径，"
            "不能使用依赖 QQ.exe 注册表的 NapCat launcher 脚本。"
            "请在工具箱里重新点击“扫码登录”或“上线”，工具箱会改用内置 NapCat Shell 启动方式。"
            f" 退出码：{exit_code}。"
        )
    if _command_uses_node(command) and (
        not joined
        or "kernel32" in lower
        or "getsystemtimepreciseasfiletime" in lower
        or "platform" in lower
        or "windows" in lower
    ):
        return (
            f"{name} 启动失败：当前扫码内核的 node.exe 与这台服务器系统不兼容。"
            "Windows 7/Server 2008 R2 应改用 NapCat WinBoot 启动方式；"
            "Windows Server 2012/2012 R2 请确认系统更新完整。"
            f" 系统：{_windows_version_text()}；退出码：{exit_code}。"
        )
    detail = f"{name} 启动后已退出，退出码 {exit_code}。"
    if joined:
        detail += f" 输出：{joined[-600:]}"
    else:
        detail += f" 命令：{command_text}"
    return detail


def _windows_version_text() -> str:
    if sys.platform != "win32":
        return sys.platform
    try:
        version = sys.getwindowsversion()
        return f"{version.major}.{version.minor}.{version.build}"
    except Exception:
        return "Windows"


def _windows_version_tuple() -> tuple[int, int, int] | None:
    if sys.platform != "win32":
        return None
    try:
        version = sys.getwindowsversion()
        return int(version.major), int(version.minor), int(version.build)
    except Exception:
        return None


def _kernel32_has(name: str) -> bool:
    if sys.platform != "win32":
        return True
    try:
        import ctypes

        getattr(ctypes.WinDLL("kernel32", use_last_error=True), str(name))
        return True
    except Exception:
        return False


def _direct_command_from_simple_batch(executable: Path, args: list[str]) -> list[str]:
    try:
        lines = executable.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return []
    commands = [
        line.strip()
        for line in lines
        if line.strip() and _is_batch_launch_line(line.strip())
    ]
    if len(commands) != 1:
        return []
    command = _normalize_batch_command(commands[0], executable.parent)
    if not command:
        return []
    try:
        tokens = [token.strip('"') for token in shlex.split(command, posix=False)]
    except ValueError:
        return []
    if not tokens:
        return []
    tokens = [token for token in tokens if token.lower() not in {"%*", "%1", "%2", "%3"}]
    executable_name = _resolve_batch_executable(tokens[0], executable.parent)
    if not executable_name:
        return []
    return [executable_name, *tokens[1:], *args]


def _normalize_batch_command(command: str, base_dir: Path) -> str:
    command = command.lstrip("@").strip()
    lower = command.lower()
    if lower.startswith("call "):
        command = command[5:].strip()
        lower = command.lower()
    if lower.startswith("start "):
        command = command[6:].strip()
    try:
        tokens = [token.strip('"') for token in shlex.split(command, posix=False)]
    except ValueError:
        return ""
    tokens = _normalize_start_tokens(tokens)
    if not tokens:
        return ""
    command = subprocess.list2cmdline(tokens)
    base_prefix = str(base_dir) + os.sep
    return command.replace("%~dp0\\", base_prefix).replace("%~dp0", base_prefix)


def _is_batch_launch_line(line: str) -> bool:
    stripped = line.lstrip("@").strip()
    lower = stripped.lower()
    if lower.startswith(("rem ", "::", "echo ", "@echo")):
        return False
    if lower in {"setlocal", "endlocal"}:
        return False
    if lower.startswith(("cd ", "cd/", "pushd ", "popd")):
        return False
    return True


def _normalize_start_tokens(tokens: list[str]) -> list[str]:
    result = list(tokens)
    if result and result[0] == "":
        result = result[1:]
    while result and result[0].lower() in {"/b", "/wait", "/min", "/max", "/d"}:
        option = result.pop(0).lower()
        if option == "/d" and result:
            result.pop(0)
    if result and result[0] == "":
        result = result[1:]
    return result


def _resolve_batch_executable(token: str, base_dir: Path) -> str:
    clean = token.strip().strip('"')
    if not clean:
        return ""
    if clean.lower() in {"node", "node.exe"}:
        return str(alias_path(_resolve_node_executable(base_dir)))
    candidate = Path(clean)
    if not candidate.is_absolute():
        candidate = base_dir / clean
    if candidate.suffix.lower() not in {".exe", ".com"}:
        return ""
    return str(alias_path(candidate))


def _resolve_node_executable(base_dir: Path) -> Path:
    if _prefer_legacy_windows_node():
        for candidate in _legacy_windows_node_candidates(base_dir):
            if candidate.exists():
                return candidate
    bundled = base_dir / "node.exe"
    if bundled.exists():
        return bundled
    return Path(shutil.which("node") or "node")


def _prefer_legacy_windows_node() -> bool:
    if sys.platform != "win32":
        return False
    try:
        version = sys.getwindowsversion()
        return int(version.major) < 10
    except Exception:
        return False


def _legacy_windows_node_candidates(base_dir: Path) -> list[Path]:
    """Node candidates known to be safer for Server 2012/2012 R2 than Node 20+."""
    env_node = os.environ.get("XIAMI_COMPAT_NODE", "").strip()
    candidates: list[Path] = []
    if env_node:
        candidates.append(Path(env_node))
    candidates.extend(
        [
            base_dir / "node-2012r2" / "node.exe",
            base_dir / "node18" / "node.exe",
            base_dir / "node-v18.20.8-win-x64" / "node.exe",
            KERNEL_HOME / "NapCat.Shell.Windows" / "node-2012r2" / "node.exe",
            KERNEL_HOME / "NapCat.Shell.Windows" / "node18" / "node.exe",
            KERNEL_HOME / "NapCat.Shell.Windows" / "node.exe",
            PROJECT_ROOT / "runtime" / "xiami_v1" / "kernels" / "NapCat.Shell.Windows" / "node.exe",
        ]
    )
    result: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate).lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(candidate)
    return result


def _node_command_compatibility_error(kernel_name: str, command: list[str]) -> str:
    if not _command_uses_node(command) or sys.platform != "win32":
        return ""
    version = _windows_version_tuple()
    if version and version[0] < 6:
        return f"{kernel_name} 无法启动：当前 Windows 版本过低，不支持 QQ 机器人扫码内核。"
    if version and version[0] == 6 and version[1] < 2:
        return (
            f"{kernel_name} 无法启动：当前系统版本为 {_windows_version_text()}，"
            "低于 Windows Server 2012/2012 R2 所需能力。请使用 Windows Server 2012 R2 x64 或更高版本。"
        )
    if not _kernel32_has("GetSystemTimePreciseAsFileTime"):
        return (
            f"{kernel_name} 无法启动：当前系统缺少 KERNEL32.dll!GetSystemTimePreciseAsFileTime，"
            "已停止启动以避免 node.exe 弹窗和界面卡顿。该接口是 Windows Server 2012/2012 R2 运行扫码内核所需能力；"
            "请确认服务器确实为 Windows Server 2012 R2 x64，并补齐系统更新后再扫码登录。"
        )
    return ""


def _hidden_subprocess_kwargs() -> dict[str, object]:
    return hidden_subprocess_kwargs()


class NapCatKernel(ExternalOneBotKernel):
    name = "NapCat"

    def prepare(self) -> AccountStatus:
        status = super().prepare()
        if status.state == "error":
            return status
        executable = Path(self.config.executable)
        workdir = Path(self.config.working_dir or executable.parent)
        if _looks_like_uninitialized_onekey(executable, workdir):
            self._status = AccountStatus(
                state="error",
                detail=(
                    "NapCat OneKey 尚未展开真实 QQNT Shell。Xiami 已阻止启动安装器，"
                    "避免弹出腾讯 QQ 安装向导或关闭电脑上已登录的 QQ。请改用 NapCat Windows Node 包，"
                    "或先在独立目录完成 OneKey 首次初始化后再导入生成的 NapCat.*.Shell。"
                ),
            )
            return self._status
        return status


class LagrangeKernel(ExternalOneBotKernel):
    name = "Lagrange"


def _looks_like_uninitialized_onekey(executable: Path, workdir: Path) -> bool:
    root = workdir.parent if workdir.name.lower() == "bootmain" else workdir
    has_installer = (root / "NapCatInstaller.exe").exists()
    has_shell = any(root.glob("NapCat.*.Shell"))
    if not has_installer or has_shell:
        return False
    name = executable.name.lower()
    return name in {"napcatwinbootmain.exe", "napcat.bat", "napcat.quick.bat", "xiami_napcat_start.bat"}


def _account_from_config(config: KernelConfig) -> str:
    workdir = Path(config.working_dir or Path(config.executable).parent)
    account_dir = workdir / "napcat" / "config"
    if not account_dir.exists():
        return ""
    for path in sorted(account_dir.glob("onebot11_*.json")):
        account = path.stem[len("onebot11_"):]
        if account.isdigit():
            return account
    return ""
