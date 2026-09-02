from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from xiami_core.release_manifest import DEFAULT_MANIFEST_NAME
from xiami_core.storage.paths import PROJECT_ROOT


@dataclass(frozen=True)
class ReleaseVerifyItem:
    name: str
    path: str
    ok: bool
    detail: str
    signature: str = ""
    signature_ok: bool = True
    signature_detail: str = ""


@dataclass(frozen=True)
class ReleaseVerifyReport:
    ok: bool
    manifest_path: str
    artifact_root: str
    version: str
    artifact_count: int
    items: list[ReleaseVerifyItem]


def verify_release_manifest(
    manifest_path: Path | str | None = None,
    *,
    artifact_root: Path | str | None = None,
    require_signatures: bool = False,
) -> ReleaseVerifyReport:
    manifest = Path(manifest_path) if manifest_path is not None else PROJECT_ROOT / "dist" / DEFAULT_MANIFEST_NAME
    root = Path(artifact_root) if artifact_root is not None else manifest.parent
    data = _read_manifest(manifest)
    artifacts = data.get("artifacts", [])
    if not isinstance(artifacts, list):
        artifacts = []

    items: list[ReleaseVerifyItem] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            items.append(
                ReleaseVerifyItem(
                    name="<invalid>",
                    path="",
                    ok=False,
                    detail="artifact entry is not an object",
                    signature_ok=not require_signatures,
                    signature_detail="invalid artifact entry",
                )
            )
            continue
        items.append(_verify_artifact(artifact, root, require_signatures=require_signatures))

    ok = bool(items) and all(item.ok and item.signature_ok for item in items)
    return ReleaseVerifyReport(
        ok=ok,
        manifest_path=str(manifest),
        artifact_root=str(root),
        version=str(data.get("version", "")),
        artifact_count=len(items),
        items=items,
    )


def release_verify_to_dict(report: ReleaseVerifyReport) -> dict[str, Any]:
    return asdict(report)


def release_verify_json(report: ReleaseVerifyReport) -> str:
    return json.dumps(release_verify_to_dict(report), ensure_ascii=False, indent=2)


def format_release_verify_report(report: ReleaseVerifyReport) -> str:
    lines = [
        f"发布清单验证：{'OK' if report.ok else 'FAILED'}",
        f"清单：{report.manifest_path}",
        f"产物目录：{report.artifact_root}",
        f"版本：{report.version or '-'}",
        f"产物：{report.artifact_count}",
        "",
        "检查项：",
    ]
    for item in report.items:
        prefix = "[OK]" if item.ok and item.signature_ok else "[FAIL]"
        lines.append(f"{prefix} {item.name}: {item.detail}")
        if item.signature or item.signature_detail:
            signature_prefix = "[OK]" if item.signature_ok else "[FAIL]"
            lines.append(f"  {signature_prefix} 签名：{item.signature_detail}")
    return "\n".join(lines)


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"release manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("release manifest root must be an object")
    return data


def _verify_artifact(
    artifact: dict[str, Any],
    root: Path,
    *,
    require_signatures: bool,
) -> ReleaseVerifyItem:
    name = str(artifact.get("name", "")).strip()
    expected_hash = str(artifact.get("sha256", "")).strip().lower()
    path = _resolve_artifact_path(artifact, root, name)
    if not name:
        return ReleaseVerifyItem(name="<missing>", path=str(path), ok=False, detail="artifact name is empty")
    if not path.is_file():
        return ReleaseVerifyItem(name=name, path=str(path), ok=False, detail=f"artifact file missing: {path}")
    actual_hash = _sha256_file(path)
    if not expected_hash:
        return ReleaseVerifyItem(name=name, path=str(path), ok=False, detail="sha256 missing in manifest")
    if actual_hash != expected_hash:
        return ReleaseVerifyItem(
            name=name,
            path=str(path),
            ok=False,
            detail=f"sha256 mismatch: expected {expected_hash}, actual {actual_hash}",
        )

    signature_name = _signature_name(artifact)
    signature_hash = str(artifact.get("signature_sha256", "")).strip().lower()
    signature_ok = True
    signature_detail = "not required"
    if signature_name or signature_hash:
        signature_path = root / signature_name if signature_name else path.with_name(f"{path.name}.sig")
        signature_ok, signature_detail = _verify_signature(signature_path, signature_hash)
    elif require_signatures:
        signature_ok = False
        signature_detail = "signature metadata missing"

    return ReleaseVerifyItem(
        name=name,
        path=str(path),
        ok=True,
        detail=f"sha256 ok: {actual_hash}",
        signature=signature_name,
        signature_ok=signature_ok,
        signature_detail=signature_detail,
    )


def _resolve_artifact_path(artifact: dict[str, Any], root: Path, name: str) -> Path:
    raw_path = str(artifact.get("path", "")).strip()
    if raw_path:
        manifest_path = Path(raw_path)
        if manifest_path.is_file():
            return manifest_path
    return root / name


def _signature_name(artifact: dict[str, Any]) -> str:
    signature = str(artifact.get("signature", "")).strip()
    if signature:
        return signature
    signature_url = str(artifact.get("signature_url", "")).strip()
    if not signature_url:
        return ""
    return signature_url.rstrip("/").split("/")[-1]


def _verify_signature(path: Path, expected_hash: str) -> tuple[bool, str]:
    if not path.is_file():
        return False, f"signature file missing: {path}"
    if not expected_hash:
        return False, "signature_sha256 missing in manifest"
    actual_hash = _sha256_file(path)
    if actual_hash != expected_hash:
        return False, f"signature sha256 mismatch: expected {expected_hash}, actual {actual_hash}"
    return True, f"{path.name} sha256 ok: {actual_hash}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
