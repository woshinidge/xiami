from __future__ import annotations

import socket
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlparse

from xiami_core.kernels.napcat_config import inspect_napcat_onebot_config
from xiami_core.kernels.packages import KernelPackage, discover_kernel_packages
from xiami_core.onebot.client import OneBotHttpClient
from xiami_core.storage.config import AppConfig, KernelConfig, load_config, save_config


@dataclass(frozen=True)
class RuntimeDiagnostic:
    config: AppConfig
    kernel_candidates: tuple[KernelPackage, ...]
    suggested_kernel: KernelConfig | None
    onebot_reachable: bool
    onebot_detail: str
    configured_port_open: bool
    qr_candidates: tuple[Path, ...]
    napcat_config_ok: bool | None
    napcat_config_detail: str


@dataclass(frozen=True)
class SuggestedKernelApplyResult:
    ok: bool
    config: AppConfig
    detail: str


def build_runtime_diagnostic(config: AppConfig | None = None) -> RuntimeDiagnostic:
    current = config or load_config()
    candidates = tuple(discover_kernel_packages())
    suggested = _suggest_kernel(candidates)
    onebot = OneBotHttpClient(current.kernel.http_url, current.kernel.access_token, timeout=1.0)
    version = onebot.get_version()
    status = onebot.get_status()
    onebot_ok = version.ok or status.ok
    onebot_detail = _onebot_detail(version.message, status.message)
    port_open = _is_url_port_open(current.kernel.http_url)
    qr_candidates = _find_qr_candidates(current.kernel, suggested)
    napcat_ok: bool | None = None
    napcat_detail = "非 NapCat 内核或尚未选择真实内核"
    candidate_config = current.kernel if current.kernel.kind.lower() == "napcat" else suggested
    if candidate_config and candidate_config.kind.lower() == "napcat":
        state = inspect_napcat_onebot_config(candidate_config)
        napcat_ok = state.ok
        napcat_detail = (
            f"HTTP={state.http_enabled} EVENT={state.event_enabled} "
            f"files={';'.join(str(path) for path in state.files) if state.files else '未发现'}"
        )
    return RuntimeDiagnostic(
        config=current,
        kernel_candidates=candidates,
        suggested_kernel=suggested,
        onebot_reachable=onebot_ok,
        onebot_detail=onebot_detail,
        configured_port_open=port_open,
        qr_candidates=qr_candidates,
        napcat_config_ok=napcat_ok,
        napcat_config_detail=napcat_detail,
    )


def format_runtime_diagnostic(diagnostic: RuntimeDiagnostic) -> list[str]:
    kernel = diagnostic.config.kernel
    lines = [
        f"- 当前内核配置：{kernel.kind}",
        f"- 启动程序：{kernel.executable or '未配置'}",
        f"- 工作目录：{kernel.working_dir or '未配置'}",
        f"- OneBot HTTP：{kernel.http_url or '未配置'}",
        f"- OneBot 端口：{'已监听' if diagnostic.configured_port_open else '未监听'}",
        f"- OneBot 探测：{'可访问' if diagnostic.onebot_reachable else '不可访问'}；{diagnostic.onebot_detail}",
    ]
    if diagnostic.kernel_candidates:
        lines.append(f"- 已发现内核候选：{len(diagnostic.kernel_candidates)} 个")
        for item in diagnostic.kernel_candidates[:5]:
            lines.append(f"  - {item.kind}: {item.path}")
    else:
        lines.append("- 已发现内核候选：0 个")
    if diagnostic.suggested_kernel:
        suggestion = diagnostic.suggested_kernel
        lines.append(f"- 建议切换真实内核：{suggestion.kind} | {suggestion.executable}")
        if suggestion.working_dir:
            lines.append(f"  工作目录：{suggestion.working_dir}")
    if diagnostic.napcat_config_ok is not None:
        lines.append(f"- NapCat OneBot 配置：{'通过' if diagnostic.napcat_config_ok else '未就绪'}；{diagnostic.napcat_config_detail}")
    if diagnostic.qr_candidates:
        lines.append(f"- 二维码素材：{diagnostic.qr_candidates[-1]}")
    else:
        lines.append("- 二维码素材：未发现")
    return lines


def apply_suggested_kernel_config(config: AppConfig | None = None) -> SuggestedKernelApplyResult:
    current = config or load_config()
    diagnostic = build_runtime_diagnostic(current)
    suggestion = diagnostic.suggested_kernel
    if not suggestion:
        return SuggestedKernelApplyResult(False, current, "未发现可用 NapCat/Lagrange 登录内核")
    suggestion = replace(
        suggestion,
        http_url=current.kernel.http_url or suggestion.http_url,
        access_token=current.kernel.access_token or suggestion.access_token,
    )
    updated = AppConfig(
        kernel=suggestion,
        probe_private_target=current.probe_private_target,
        probe_group_target=current.probe_group_target,
    )
    save_config(updated)
    return SuggestedKernelApplyResult(
        True,
        updated,
        f"已应用建议内核：{suggestion.kind} | {suggestion.executable}",
    )


def _suggest_kernel(candidates: tuple[KernelPackage, ...]) -> KernelConfig | None:
    if not candidates:
        return None
    sorted_candidates = sorted(candidates, key=lambda item: (_candidate_rank(item), str(item.path).lower()))
    first = sorted_candidates[0]
    return _config_from_candidate(first)


def _config_from_candidate(candidate: KernelPackage) -> KernelConfig:
    entry = candidate.path
    executable = str(entry)
    args: list[str] = []
    if entry.suffix.lower() == ".dll":
        executable = "dotnet"
        args = [str(entry)]
    if candidate.kind.lower() == "napcat" and entry.name.lower() == "napcat.bat":
        managed = entry.parent / "xiami_napcat_start.bat"
        if managed.exists():
            executable = str(managed)
    return KernelConfig(
        kind=candidate.kind,
        executable=executable,
        working_dir=str(entry.parent),
        arguments=args,
    )


def _candidate_rank(item: KernelPackage) -> int:
    name = item.path.name.lower()
    if item.kind.lower() == "napcat" and name == "napcat.bat":
        return 0
    if item.kind.lower() == "napcat":
        return 1
    if item.kind.lower() == "lagrange":
        return 2
    return 9


def _find_qr_candidates(config: KernelConfig, suggested: KernelConfig | None) -> tuple[Path, ...]:
    roots: list[Path] = []
    for kernel in (config, suggested):
        if not kernel:
            continue
        workdir = Path(kernel.working_dir or Path(kernel.executable).parent)
        if workdir.exists():
            roots.append(workdir)
    seen: set[Path] = set()
    qrs: list[Path] = []
    for root in roots:
        for name in ("qrcode.png", "qr-0.png", "qr.png"):
            try:
                for path in root.rglob(name):
                    try:
                        resolved = path.resolve()
                        if resolved in seen or not path.is_file():
                            continue
                    except OSError:
                        continue
                    seen.add(resolved)
                    qrs.append(resolved)
            except OSError:
                continue
    existing: list[tuple[float, Path]] = []
    for path in qrs:
        try:
            existing.append((path.stat().st_mtime, path))
        except OSError:
            continue
    return tuple(path for _mtime, path in sorted(existing))


def _onebot_detail(*messages: str) -> str:
    for message in messages:
        if message:
            return message
    return "get_version_info/get_status 无响应"


def _is_url_port_open(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=0.4):
            return True
    except OSError:
        return False
