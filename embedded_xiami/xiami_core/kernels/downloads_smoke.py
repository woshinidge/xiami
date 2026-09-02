from __future__ import annotations

from xiami_core.kernels.downloads import DownloadCandidate, _candidate_priority


def main() -> int:
    items = [
        DownloadCandidate("NapCat", "NapCat.Shell.Windows.Node.zip", "https://example.invalid/node.zip", 1),
        DownloadCandidate("NapCat", "NapCat.Shell.Windows.OneKey.zip", "https://example.invalid/onekey.zip", 1),
    ]
    ordered = sorted(items, key=_candidate_priority)
    if ordered[0].name != "NapCat.Shell.Windows.Node.zip":
        raise RuntimeError(f"bad priority: {ordered}")
    print("kernel downloads smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
