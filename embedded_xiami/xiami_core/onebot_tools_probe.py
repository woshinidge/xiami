from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from xiami_core.onebot.client import OneBotHttpClient, OneBotResponse
from xiami_core.storage.config import load_config


@dataclass(frozen=True)
class OneBotToolProbeItem:
    name: str
    action: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class OneBotToolsProbeResult:
    ok: bool
    http_url: str
    group_id: str
    items: tuple[OneBotToolProbeItem, ...]


def run_onebot_tools_probe(
    *,
    group_id: str = "",
    timeout: float = 3.0,
) -> OneBotToolsProbeResult:
    config = load_config()
    http_url = config.kernel.http_url.strip()
    group_id = group_id.strip() or config.probe_group_target.strip()
    if not http_url:
        return OneBotToolsProbeResult(
            ok=False,
            http_url="",
            group_id=group_id,
            items=(OneBotToolProbeItem("onebot_http", "config", False, "未配置 OneBot HTTP"),),
        )

    client = OneBotHttpClient(http_url, config.kernel.access_token, timeout=timeout)
    items = [
        _probe("登录信息", "get_login_info", client.get_login_info()),
        _probe("运行状态", "get_status", client.get_status()),
        _probe("版本信息", "get_version_info", client.get_version()),
        _probe("好友列表", "get_friend_list", client.get_friend_list()),
        _probe("群列表", "get_group_list", client.get_group_list()),
    ]
    if group_id:
        items.append(_probe("群资料", "get_group_info", client.get_group_info(group_id)))
    required = [item for item in items if item.action in {"get_login_info", "get_status", "get_friend_list", "get_group_list"}]
    return OneBotToolsProbeResult(
        ok=bool(required) and all(item.ok for item in required),
        http_url=http_url,
        group_id=group_id,
        items=tuple(items),
    )


def format_onebot_tools_probe(result: OneBotToolsProbeResult) -> str:
    passed = sum(1 for item in result.items if item.ok)
    lines = [
        f"OneBot 工具探针：{'PASS' if result.ok else 'BLOCKED'}",
        f"OneBot HTTP：{result.http_url or '未配置'}",
        f"探针群：{result.group_id or '未配置，可跳过群资料'}",
        f"通过：{passed}/{len(result.items)}",
        "",
        "安全动作：",
    ]
    for item in result.items:
        mark = "OK" if item.ok else "待处理"
        lines.append(f"- [{mark}] {item.name} ({item.action})：{item.detail}")
    lines.extend(
        [
            "",
            "说明：该探针只调用只读/低风险 OneBot 工具接口；成功调用会写入 onebot_actions.jsonl，供高风险证据候选读取。",
            "下一步：运行 python -m xiami_core.high_risk_evidence_cli 查看 onebot_tools_real 候选。",
        ]
    )
    return "\n".join(lines)


def onebot_tools_probe_to_dict(result: OneBotToolsProbeResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "http_url": result.http_url,
        "group_id": result.group_id,
        "items": [asdict(item) for item in result.items],
    }


def dumps_onebot_tools_probe(result: OneBotToolsProbeResult) -> str:
    return json.dumps(onebot_tools_probe_to_dict(result), ensure_ascii=False, indent=2)


def _probe(name: str, action: str, response: OneBotResponse) -> OneBotToolProbeItem:
    if response.ok:
        return OneBotToolProbeItem(name=name, action=action, ok=True, detail=_success_detail(response.data))
    return OneBotToolProbeItem(name=name, action=action, ok=False, detail=response.message or "调用失败")


def _success_detail(data: Any) -> str:
    if isinstance(data, list):
        return f"返回 {len(data)} 项"
    if isinstance(data, dict):
        keys = ", ".join(str(key) for key in list(data.keys())[:5])
        return f"返回字段：{keys}" if keys else "返回空对象"
    if data is None:
        return "调用成功"
    return str(data)[:120]
