from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from xiami_core.storage.paths import PROJECT_ROOT


DEFAULT_MANIFEST_NAME = "xiami_update.json"
DEFAULT_PRODUCT = "Xiami"
DEFAULT_CHANNEL = "stable"
DEFAULT_PLATFORM = "windows-x64"
DEFAULT_VERSION = "0.0.0-dev"
RELEASE_ARTIFACT_NAMES = (
    "Xiami.exe",
    "Xiami.zip",
    "XiamiSetup.exe",
    "XiamiInstaller.exe",
)
RELEASE_ARTIFACT_SUFFIXES = (".zip", ".exe", ".msi")


@dataclass(frozen=True)
class ReleaseArtifact:
    name: str
    path: str
    size: int
    sha256: str
    url: str
    signature: str = ""
    signature_url: str = ""
    signature_sha256: str = ""
    signature_algorithm: str = ""
    signer: str = ""


@dataclass(frozen=True)
class ReleaseManifest:
    product: str
    version: str
    channel: str
    platform: str
    created_at: str
    minimum_version: str
    notes: str
    artifacts: list[ReleaseArtifact]

    @property
    def ok(self) -> bool:
        return bool(self.artifacts)


def discover_release_artifacts(dist_dir: Path | str | None = None) -> list[Path]:
    root = Path(dist_dir) if dist_dir is not None else PROJECT_ROOT / "dist"
    if not root.is_dir():
        return []
    preferred = [root / name for name in RELEASE_ARTIFACT_NAMES if (root / name).is_file()]
    if preferred:
        return preferred
    return sorted(
        path
        for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in RELEASE_ARTIFACT_SUFFIXES
    )


def build_release_manifest(
    artifacts: Iterable[Path | str],
    *,
    version: str = DEFAULT_VERSION,
    channel: str = DEFAULT_CHANNEL,
    platform: str = DEFAULT_PLATFORM,
    product: str = DEFAULT_PRODUCT,
    base_url: str = "",
    signature_base_url: str = "",
    signature_suffix: str = ".sig",
    signature_algorithm: str = "",
    signer: str = "",
    minimum_version: str = "",
    notes: str = "",
    created_at: str | None = None,
) -> ReleaseManifest:
    artifact_items: list[ReleaseArtifact] = []
    for artifact in artifacts:
        path = Path(artifact)
        if not path.is_file():
            raise FileNotFoundError(f"release artifact not found: {path}")
        signature_path = _signature_file_for(path, signature_suffix)
        has_signature = signature_path is not None and signature_path.is_file()
        artifact_items.append(
            ReleaseArtifact(
                name=path.name,
                path=str(path),
                size=path.stat().st_size,
                sha256=_sha256_file(path),
                url=_artifact_url(path.name, base_url),
                signature=signature_path.name if has_signature else "",
                signature_url=_artifact_url(signature_path.name, signature_base_url or base_url)
                if has_signature
                else "",
                signature_sha256=_sha256_file(signature_path) if has_signature else "",
                signature_algorithm=signature_algorithm if has_signature else "",
                signer=signer if has_signature else "",
            )
        )
    timestamp = created_at or datetime.now(timezone.utc).isoformat()
    return ReleaseManifest(
        product=product,
        version=version,
        channel=channel,
        platform=platform,
        created_at=timestamp,
        minimum_version=minimum_version,
        notes=notes,
        artifacts=artifact_items,
    )


def release_manifest_to_dict(manifest: ReleaseManifest) -> dict[str, object]:
    return asdict(manifest)


def release_manifest_json(manifest: ReleaseManifest) -> str:
    return json.dumps(release_manifest_to_dict(manifest), ensure_ascii=False, indent=2)


def write_release_manifest(manifest: ReleaseManifest, output: Path | str) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(release_manifest_json(manifest) + "\n", encoding="utf-8")
    return path


def _artifact_url(name: str, base_url: str) -> str:
    base = base_url.strip()
    if not base:
        return name
    return f"{base.rstrip('/')}/{name}"


def _signature_file_for(path: Path, suffix: str) -> Path | None:
    suffix = suffix.strip()
    if not suffix:
        return None
    return path.with_name(f"{path.name}{suffix}")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
