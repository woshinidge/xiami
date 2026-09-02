from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from xiami_core.onebot.client import OneBotHttpClient, OneBotResponse
from xiami_core.storage.config import load_config


@dataclass(frozen=True)
class HighRiskProbeItem:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class HighRiskProbeResult:
    ok: bool
    http_url: str
    group_id: str
    items: tuple[HighRiskProbeItem, ...]


def run_high_risk_probe(
    *,
    group_id: str = "",
    member_guard: bool = True,
    moderation_user: str = "",
    moderation_duration: int = 1,
    confirm_moderation: bool = False,
    friend_flag: str = "",
    friend_approve: bool = False,
    join_flag: str = "",
    join_sub_type: str = "add",
    join_approve: bool = False,
    confirm_review: bool = False,
    timeout: float = 3.0,
) -> HighRiskProbeResult:
    config = load_config()
    http_url = config.kernel.http_url.strip()
    group_id = group_id.strip() or config.probe_group_target.strip()
    if not http_url:
        return HighRiskProbeResult(
            ok=False,
            http_url="",
            group_id=group_id,
            items=(HighRiskProbeItem("onebot_http", False, "未配置 OneBot HTTP"),),
        )

    client = OneBotHttpClient(http_url, config.kernel.access_token, timeout=timeout)
    items: list[HighRiskProbeItem] = []
    if member_guard:
        items.append(_probe_member_guard(client, group_id))
    if moderation_user:
        items.append(
            _probe_moderation(
                client,
                group_id,
                moderation_user,
                moderation_duration=max(1, min(int(moderation_duration), 60)),
                confirmed=confirm_moderation,
            )
        )
    if friend_flag:
        items.append(_probe_friend_review(client, friend_flag, approve=friend_approve, confirmed=confirm_review))
    if join_flag:
        items.append(
            _probe_join_review(
                client,
                join_flag,
                sub_type=join_sub_type or "add",
                approve=join_approve,
                confirmed=confirm_review,
            )
        )
    if not items:
        items.append(HighRiskProbeItem("probe_target", False, "未选择可执行探针"))
    return HighRiskProbeResult(ok=all(item.ok for item in items), http_url=http_url, group_id=group_id, items=tuple(items))


def format_high_risk_probe(result: HighRiskProbeResult) -> str:
    passed = sum(1 for item in result.items if item.ok)
    lines = [
        f"高风险探针：{'PASS' if result.ok else 'BLOCKED'}",
        f"OneBot HTTP：{result.http_url or '未配置'}",
        f"测试群：{result.group_id or '未配置'}",
        f"通过：{passed}/{len(result.items)}",
        "",
        "探针结果：",
    ]
    for item in result.items:
        mark = "OK" if item.ok else "待处理"
        lines.append(f"- [{mark}] {item.name}: {item.detail}")
    lines.extend(
        [
            "",
            "说明：默认只发送并撤回一条测试群探针消息；禁言、好友审核、入群审核必须在 CLI 中显式传确认参数。",
            "下一步：运行 python -m xiami_core.high_risk_evidence_cli 查看候选证据。",
        ]
    )
    return "\n".join(lines)


def high_risk_probe_to_dict(result: HighRiskProbeResult) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "http_url": result.http_url,
        "group_id": result.group_id,
        "items": [asdict(item) for item in result.items],
    }


def dumps_high_risk_probe(result: HighRiskProbeResult) -> str:
    return json.dumps(high_risk_probe_to_dict(result), ensure_ascii=False, indent=2)


def _probe_member_guard(client: OneBotHttpClient, group_id: str) -> HighRiskProbeItem:
    if not group_id:
        return HighRiskProbeItem("member_guard_real", False, "未配置测试群，无法发送并撤回探针消息")
    marker = f"Xiami member guard probe {datetime.now().isoformat(timespec='seconds')}"
    send = client.send_group_msg(group_id, marker)
    if not send.ok:
        return HighRiskProbeItem("member_guard_real", False, f"发送探针失败：{send.message}")
    message_id = _message_id(send)
    if not message_id:
        return HighRiskProbeItem("member_guard_real", False, "发送成功但未返回 message_id，无法撤回")
    delete = client.delete_msg(message_id)
    if not delete.ok:
        return HighRiskProbeItem("member_guard_real", False, f"撤回探针失败：{delete.message}")
    return HighRiskProbeItem("member_guard_real", True, f"已发送并撤回测试消息 message_id={message_id}")


def _probe_moderation(
    client: OneBotHttpClient,
    group_id: str,
    user_id: str,
    *,
    moderation_duration: int,
    confirmed: bool,
) -> HighRiskProbeItem:
    if not group_id:
        return HighRiskProbeItem("moderation_real", False, "未配置测试群")
    if not confirmed:
        return HighRiskProbeItem("moderation_real", False, "需要 --confirm-moderation 才会执行禁言/解禁探针")
    ban = client.set_group_ban(group_id, user_id, moderation_duration)
    if not ban.ok:
        return HighRiskProbeItem("moderation_real", False, f"禁言探针失败：{ban.message}")
    unban = client.set_group_ban(group_id, user_id, 0)
    if not unban.ok:
        return HighRiskProbeItem("moderation_real", False, f"已禁言但解禁失败：{unban.message}")
    return HighRiskProbeItem("moderation_real", True, f"已禁言 {moderation_duration}s 并解禁 user_id={user_id}")


def _probe_friend_review(
    client: OneBotHttpClient,
    flag: str,
    *,
    approve: bool,
    confirmed: bool,
) -> HighRiskProbeItem:
    if not confirmed:
        return HighRiskProbeItem("friend_review_real", False, "需要 --confirm-review 才会处理好友申请 flag")
    response = client.set_friend_add_request(flag, approve=approve, remark="Xiami probe")
    if not response.ok:
        return HighRiskProbeItem("friend_review_real", False, f"好友审核 action 失败：{response.message}")
    action = "同意" if approve else "拒绝"
    return HighRiskProbeItem("friend_review_real", True, f"好友申请已{action} flag={flag}")


def _probe_join_review(
    client: OneBotHttpClient,
    flag: str,
    *,
    sub_type: str,
    approve: bool,
    confirmed: bool,
) -> HighRiskProbeItem:
    if not confirmed:
        return HighRiskProbeItem("join_review_real", False, "需要 --confirm-review 才会处理入群申请 flag")
    response = client.set_group_add_request(flag, sub_type=sub_type, approve=approve, reason="Xiami probe")
    if not response.ok:
        return HighRiskProbeItem("join_review_real", False, f"入群审核 action 失败：{response.message}")
    action = "同意" if approve else "拒绝"
    return HighRiskProbeItem("join_review_real", True, f"入群申请已{action} flag={flag} sub_type={sub_type}")


def _message_id(response: OneBotResponse) -> str:
    data = response.data
    if isinstance(data, dict):
        value = data.get("message_id")
        return str(value) if value is not None else ""
    if isinstance(data, int):
        return str(data)
    return ""
