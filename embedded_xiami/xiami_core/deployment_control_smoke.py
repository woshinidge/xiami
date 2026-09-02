from __future__ import annotations

import json
from pathlib import Path

from xiami_core.deployment_control import build_deployment_summary, deployment_summary_json, format_deployment_summary


def main() -> int:
    summary = build_deployment_summary()
    text = format_deployment_summary(summary)
    if "部署状态：" not in text or "quick_acceptance" not in text:
        raise RuntimeError(f"deployment summary text missing expected content: {text}")
    data = json.loads(deployment_summary_json(summary))
    names = {item["name"] for item in data["checks"]}
    expected = {
        "no_console_launcher",
        "start_script",
        "acceptance_script",
        "core_package",
        "desktop_package",
        "plugin_package",
        "plugin_count",
        "release_artifact",
        "update_manifest",
        "signing_config",
    }
    if not expected.issubset(names):
        raise RuntimeError(f"deployment checks missing: {sorted(expected - names)}")
    if data["commands"].get("start_desktop") != r".\start_xiami.vbs":
        raise RuntimeError(f"deployment start command should use no-console launcher: {data['commands']}")
        release_command = data["commands"].get("release_manifest", "")
        if "release_manifest_cli" not in release_command:
            raise RuntimeError(f"deployment release manifest command missing: {data['commands']}")
        if "--signature-algorithm" not in release_command or "--signer" not in release_command:
            raise RuntimeError(f"deployment release signature command missing: {data['commands']}")
        if data["commands"].get("release_verify") != "python -m xiami_core.release_verify_cli --require-signature":
            raise RuntimeError(f"deployment release verify command missing: {data['commands']}")
        if data["commands"].get("release_update") != "python -m xiami_core.release_update_cli --current-version <version> --require-signature":
            raise RuntimeError(f"deployment release update command missing: {data['commands']}")
        if not Path(data["project_root"]).exists():
            raise RuntimeError("deployment project_root does not exist")
    print("deployment control smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
