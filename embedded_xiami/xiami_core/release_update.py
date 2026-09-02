from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from xiami_core.release_manifest import DEFAULT_MANIFEST_NAME, DEFAULT_PLATFORM, DEFAULT_VERSION
from xiami_core.storage.paths import PROJECT_ROOT


@dataclass(frozen=True)
class ReleaseUpdateDecision:
    ok: bool
    update_available: bool
    status: str
    reason: str
    current_version: str
    release_version: str
    minimum_version: str
    platform: str
    release_platform: str
    artifact_name: str = ""
    artifact_url: str = ""
    artifact_sha256: str = ""
    signature: str = ""
    signature_url: str = ""
    signature_sha256: str = ""


def check_release_update(
    manifest_path: Path | str | None = None,
    *,
    current_version: str = DEFAULT_VERSION,
    platform: str = DEFAULT_PLATFORM,
    require_signature: bool = False,
) -> ReleaseUpdateDecision:
    manifest = Path(manifest_path) if manifest_path is not None else PROJECT_ROOT / "dist" / DEFAULT_MANIFEST_NAME
    data = _read_manifest(manifest)
    release_version = str(data.get("version", "")).strip()
    release_platform = str(data.get("platform", "")).strip()
    minimum_version = str(data.get("minimum_version", "")).strip()
    platform = str(platform or "").strip()
    current_version = str(current_version or "").strip()

    if not release_version:
        return _decision(False, False, "invalid_manifest", "release version missing", current_version, "", minimum_version, platform, release_platform)
    if platform and release_platform and platform != release_platform:
        return _decision(
            False,
            False,
            "platform_mismatch",
            f"manifest platform {release_platform} does not match {platform}",
            current_version,
            release_version,
            minimum_version,
            platform,
            release_platform,
        )
    if minimum_version and compare_versions(current_version, minimum_version) < 0:
        return _decision(
            False,
            False,
            "minimum_version_blocked",
            f"current version {current_version} is below minimum {minimum_version}",
            current_version,
            release_version,
            minimum_version,
            platform,
            release_platform,
        )

    version_delta = compare_versions(release_version, current_version)
    if version_delta == 0:
        return _decision(True, False, "up_to_date", "current version is already latest", current_version, release_version, minimum_version, platform, release_platform)
    if version_delta < 0:
        return _decision(True, False, "older_manifest", "manifest version is older than current version", current_version, release_version, minimum_version, platform, release_platform)

    artifact = _select_artifact(data.get("artifacts", []))
    if artifact is None:
        return _decision(False, False, "no_artifact", "manifest has no artifact", current_version, release_version, minimum_version, platform, release_platform)
    signature = str(artifact.get("signature", "")).strip()
    signature_url = str(artifact.get("signature_url", "")).strip()
    signature_sha256 = str(artifact.get("signature_sha256", "")).strip()
    if require_signature and (not (signature or signature_url) or not signature_sha256):
        return _decision(
            False,
            False,
            "signature_required",
            "release artifact has no complete signature metadata",
            current_version,
            release_version,
            minimum_version,
            platform,
            release_platform,
            artifact,
        )

    return _decision(
        True,
        True,
        "update_available",
        f"update {current_version} -> {release_version}",
        current_version,
        release_version,
        minimum_version,
        platform,
        release_platform,
        artifact,
    )


def compare_versions(left: str, right: str) -> int:
    left_parts = _version_parts(left)
    right_parts = _version_parts(right)
    max_len = max(len(left_parts[0]), len(right_parts[0]), 3)
    left_nums = tuple(left_parts[0] + [0] * (max_len - len(left_parts[0])))
    right_nums = tuple(right_parts[0] + [0] * (max_len - len(right_parts[0])))
    if left_nums != right_nums:
        return 1 if left_nums > right_nums else -1
    if left_parts[1] != right_parts[1]:
        return 1 if left_parts[1] > right_parts[1] else -1
    if left_parts[2] == right_parts[2]:
        return 0
    return 1 if left_parts[2] > right_parts[2] else -1


def release_update_to_dict(decision: ReleaseUpdateDecision) -> dict[str, Any]:
    return asdict(decision)


def release_update_json(decision: ReleaseUpdateDecision) -> str:
    return json.dumps(release_update_to_dict(decision), ensure_ascii=False, indent=2)


def format_release_update_decision(decision: ReleaseUpdateDecision) -> str:
    lines = [
        f"更新检查：{'OK' if decision.ok else 'BLOCKED'}",
        f"状态：{decision.status}",
        f"原因：{decision.reason}",
        f"当前版本：{decision.current_version or '-'}",
        f"发布版本：{decision.release_version or '-'}",
        f"平台：{decision.platform or '-'} / {decision.release_platform or '-'}",
        f"最低版本：{decision.minimum_version or '-'}",
    ]
    if decision.artifact_name:
        lines.extend(
            [
                f"产物：{decision.artifact_name}",
                f"下载：{decision.artifact_url}",
                f"sha256：{decision.artifact_sha256}",
            ]
        )
    if decision.signature or decision.signature_url:
        lines.extend(
            [
                f"签名：{decision.signature or '-'}",
                f"签名地址：{decision.signature_url or '-'}",
                f"签名 sha256：{decision.signature_sha256 or '-'}",
            ]
        )
    return "\n".join(lines)


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"release manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release manifest root must be an object")
    return data


def _select_artifact(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, list):
        return None
    for item in value:
        if isinstance(item, dict) and str(item.get("name", "")).strip() and str(item.get("sha256", "")).strip():
            return item
    return None


def _decision(
    ok: bool,
    update_available: bool,
    status: str,
    reason: str,
    current_version: str,
    release_version: str,
    minimum_version: str,
    platform: str,
    release_platform: str,
    artifact: dict[str, Any] | None = None,
) -> ReleaseUpdateDecision:
    artifact = artifact or {}
    return ReleaseUpdateDecision(
        ok=ok,
        update_available=update_available,
        status=status,
        reason=reason,
        current_version=current_version,
        release_version=release_version,
        minimum_version=minimum_version,
        platform=platform,
        release_platform=release_platform,
        artifact_name=str(artifact.get("name", "")).strip(),
        artifact_url=str(artifact.get("url", "")).strip(),
        artifact_sha256=str(artifact.get("sha256", "")).strip(),
        signature=str(artifact.get("signature", "")).strip(),
        signature_url=str(artifact.get("signature_url", "")).strip(),
        signature_sha256=str(artifact.get("signature_sha256", "")).strip(),
    )


def _version_parts(value: str) -> tuple[list[int], int, str]:
    raw = str(value or "").strip().lower().lstrip("v")
    number_match = re.match(r"(\d+(?:\.\d+)*)", raw)
    if not number_match:
        return [0], 0, raw
    numbers = [int(part) for part in number_match.group(1).split(".")]
    suffix = raw[number_match.end() :].lstrip(".-+")
    stable_rank = 1 if not suffix else 0
    return numbers, stable_rank, suffix
