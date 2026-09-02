from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from xiami_core.storage.config import load_config
from xiami_core.storage.paths import CONFIG_FILE, KERNEL_HOME, LOG_HOME, PROJECT_ROOT, XIAMI_HOME, ensure_runtime_dirs


@dataclass(frozen=True)
class DeploymentCheck:
    name: str
    ok: bool
    detail: str
    level: str = "ok"


@dataclass(frozen=True)
class DeploymentSummary:
    ok: bool
    project_root: str
    xiami_home: str
    python: str
    checks: list[DeploymentCheck]
    commands: dict[str, str]


def build_deployment_summary() -> DeploymentSummary:
    ensure_runtime_dirs()
    config = load_config()
    checks = [
        _file_check("no_console_launcher", PROJECT_ROOT / "start_xiami.vbs", "无控制台桌面启动入口"),
        _file_check("start_script", PROJECT_ROOT / "start_xiami.bat", "桌面启动脚本"),
        _file_check("acceptance_script", PROJECT_ROOT / "xiami_acceptance.ps1", "统一验收脚本"),
        _dir_check("core_package", PROJECT_ROOT / "xiami_core", "Xiami Core 包"),
        _dir_check("desktop_package", PROJECT_ROOT / "xiami_app", "Xiami 桌面包"),
        _dir_check("plugin_package", PROJECT_ROOT / "xiami_plugins", "Xiami 插件包"),
        _dir_check("runtime_home", XIAMI_HOME, "运行时目录"),
        _dir_check("kernel_home", KERNEL_HOME, "登录内核目录"),
        _dir_check("log_home", LOG_HOME, "日志目录"),
        _config_check(CONFIG_FILE),
        _kernel_check(config.kernel),
        _plugin_count_check(PROJECT_ROOT / "xiami_plugins"),
        _release_artifact_check(PROJECT_ROOT),
        _update_manifest_check(PROJECT_ROOT),
        _signing_config_check(),
    ]
    commands = {
        "start_desktop": r".\start_xiami.vbs",
        "start_desktop_fallback": r".\start_xiami.bat",
        "quick_acceptance": r".\xiami_acceptance.ps1 -Mode quick",
        "full_acceptance": r".\xiami_acceptance.ps1 -Mode full",
        "real_acceptance": r".\xiami_acceptance.ps1 -Mode real",
        "real_delivery_gate": (
            r".\xiami_acceptance.ps1 -Mode real -ProductGate -LongStability -ExportBundle -Provider "
            r"-StabilityDuration 3600 -StabilityInterval 30"
        ),
        "high_risk_gate": "python -m xiami_core.high_risk_gate_cli --strict",
        "high_risk_next": "python -m xiami_core.high_risk_next_cli",
        "delivery_checklist": "python -m xiami_core.delivery_checklist_cli --provider",
        "progress_report": "python -m xiami_core.progress_report",
        "evidence_bundle": "python -m xiami_core.evidence_bundle_cli",
        "production_gate": "python -m xiami_core.production_gate_cli --strict",
        "release_manifest": (
            "python -m xiami_core.release_manifest_cli --version <version> "
            "--signature-algorithm RSA-SHA256 --signer <signer>"
        ),
        "release_verify": "python -m xiami_core.release_verify_cli --require-signature",
        "release_update": "python -m xiami_core.release_update_cli --current-version <version> --require-signature",
        "recovery_plan": "python -m xiami_core.recovery_plan_cli",
        "stability_readiness": "python -m xiami_core.stability_readiness_cli",
        "stability_suite": "python -m xiami_core.stability_suite_cli --duration 3600 --interval 30 --provider --min-samples 120 --min-duration 3600 --onebot-ratio 0.99 --provider-ratio 0.95",
        "stability_observer": "python -m xiami_core.stability_observer_cli --duration 3600 --interval 30 --provider",
        "stability_resume": "python -m xiami_core.stability_resume_cli --duration 3600 --interval 30 --provider",
        "stability_continue": "python -m xiami_core.stability_continue_cli --duration 3600 --interval 30 --provider",
        "stability_evidence": "python -m xiami_core.stability_evidence_cli --min-samples 120 --min-duration 3600 --onebot-ratio 0.99 --provider --provider-ratio 0.95",
    }
    ok = all(item.ok or item.level == "warning" for item in checks)
    return DeploymentSummary(
        ok=ok,
        project_root=str(PROJECT_ROOT),
        xiami_home=str(XIAMI_HOME),
        python=sys.executable,
        checks=checks,
        commands=commands,
    )


def format_deployment_summary(summary: DeploymentSummary) -> str:
    lines = [
        f"部署状态：{'OK' if summary.ok else '需要处理'}",
        f"项目目录：{summary.project_root}",
        f"运行目录：{summary.xiami_home}",
        f"Python：{summary.python}",
        "",
        "检查项：",
    ]
    for item in summary.checks:
        prefix = "[OK]" if item.ok else ("[WARN]" if item.level == "warning" else "[FAIL]")
        lines.append(f"{prefix} {item.name}: {item.detail}")
    lines.extend(["", "常用命令："])
    for name, command in summary.commands.items():
        lines.append(f"- {name}: {command}")
    return "\n".join(lines)


def deployment_summary_to_dict(summary: DeploymentSummary) -> dict[str, Any]:
    return asdict(summary)


def deployment_summary_json(summary: DeploymentSummary | None = None) -> str:
    return json.dumps(deployment_summary_to_dict(summary or build_deployment_summary()), ensure_ascii=False, indent=2)


def _file_check(name: str, path: Path, label: str) -> DeploymentCheck:
    return DeploymentCheck(name=name, ok=path.is_file(), detail=f"{label}: {path}")


def _dir_check(name: str, path: Path, label: str) -> DeploymentCheck:
    return DeploymentCheck(name=name, ok=path.is_dir(), detail=f"{label}: {path}")


def _config_check(path: Path) -> DeploymentCheck:
    if path.is_file():
        return DeploymentCheck("config_file", True, f"配置文件：{path}")
    return DeploymentCheck("config_file", True, f"配置文件未生成，首次保存设置后创建：{path}", level="warning")


def _kernel_check(kernel) -> DeploymentCheck:
    kind = str(getattr(kernel, "kind", "") or "")
    if kind.lower() == "mock":
        return DeploymentCheck("kernel_config", True, "当前使用 Mock 内核，仅适合 UI/插件验证", level="warning")
    executable = str(getattr(kernel, "executable", "") or "")
    http_url = str(getattr(kernel, "http_url", "") or "")
    ok = bool(executable and http_url)
    detail = f"内核：{kind}，程序：{executable or '未配置'}，OneBot：{http_url or '未配置'}"
    return DeploymentCheck("kernel_config", ok, detail)


def _plugin_count_check(plugin_root: Path) -> DeploymentCheck:
    if not plugin_root.is_dir():
        return DeploymentCheck("plugin_count", False, f"插件目录不存在：{plugin_root}")
    count = sum(1 for path in plugin_root.iterdir() if (path / "plugin.py").is_file())
    return DeploymentCheck("plugin_count", count > 0, f"已发现原生插件：{count} 个")


def _release_artifact_check(project_root: Path) -> DeploymentCheck:
    dist = project_root / "dist"
    candidates = [
        dist / "Xiami.exe",
        dist / "Xiami",
        dist / "Xiami.zip",
        dist / "XiamiSetup.exe",
        dist / "XiamiInstaller.exe",
    ]
    existing = [path for path in candidates if path.exists()]
    if existing:
        names = ", ".join(path.name for path in existing)
        return DeploymentCheck("release_artifact", True, f"发布产物：{names}")
    return DeploymentCheck(
        "release_artifact",
        False,
        f"未发现发布产物，建议输出到：{dist}",
        level="warning",
    )


def _update_manifest_check(project_root: Path) -> DeploymentCheck:
    candidates = [
        project_root / "xiami_update.json",
        project_root / "dist" / "xiami_update.json",
        project_root / "dist" / "latest.json",
    ]
    existing = [path for path in candidates if path.is_file()]
    if existing:
        return DeploymentCheck("update_manifest", True, f"更新清单：{existing[0]}")
    return DeploymentCheck(
        "update_manifest",
        False,
        "未发现自动更新清单：xiami_update.json/latest.json",
        level="warning",
    )


def _signing_config_check() -> DeploymentCheck:
    keys = ("XIAMI_SIGNING_CERT", "XIAMI_SIGNING_CERT_THUMBPRINT", "XIAMI_SIGNTOOL")
    configured = [key for key in keys if os.environ.get(key)]
    if configured:
        return DeploymentCheck("signing_config", True, f"签名配置：{', '.join(configured)}")
    return DeploymentCheck(
        "signing_config",
        False,
        "未配置发布签名环境变量：XIAMI_SIGNING_CERT / XIAMI_SIGNING_CERT_THUMBPRINT / XIAMI_SIGNTOOL",
        level="warning",
    )
