from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from xiami_core.storage.paths import PROJECT_ROOT


NAPCAT_RELEASE_API = "https://api.github.com/repos/NapNeko/NapCatQQ/releases/latest"


@dataclass(frozen=True)
class DownloadCandidate:
    kind: str
    name: str
    url: str
    size: int


def fetch_napcat_candidates() -> list[DownloadCandidate]:
    request = urllib.request.Request(NAPCAT_RELEASE_API)
    request.add_header("User-Agent", "Xiami")
    with urllib.request.urlopen(request, timeout=10) as response:
        data = json.loads(response.read().decode("utf-8"))
    candidates: list[DownloadCandidate] = []
    for asset in data.get("assets", []):
        name = str(asset.get("name", ""))
        if not name.endswith(".zip"):
            continue
        if "Shell.Windows.OneKey" not in name and "Shell.Windows.Node" not in name:
            continue
        candidates.append(
            DownloadCandidate(
                kind="NapCat",
                name=name,
                url=str(asset.get("browser_download_url", "")),
                size=int(asset.get("size", 0)),
            )
        )
    return sorted(candidates, key=_candidate_priority)


def download_candidate(candidate: DownloadCandidate, target_dir: Path | None = None) -> Path:
    target_dir = target_dir or PROJECT_ROOT / "downloads"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / candidate.name
    if target.exists() and target.stat().st_size == candidate.size:
        return target
    request = urllib.request.Request(candidate.url)
    request.add_header("User-Agent", "Xiami")
    with urllib.request.urlopen(request, timeout=60) as response:
        target.write_bytes(response.read())
    return target


def _candidate_priority(candidate: DownloadCandidate) -> tuple[int, str]:
    if "Node" in candidate.name:
        priority = 0
    elif "OneKey" in candidate.name:
        priority = 1
    else:
        priority = 10
    return priority, candidate.name
