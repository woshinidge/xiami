from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Literal


Priority = Literal["P0", "P1", "P2"]


FORMAL_PLUGIN_IDS: tuple[str, ...] = (
    "ai_reply",
    "bindings",
    "cards",
    "compat_echo",
    "custom_replies",
    "echo",
    "error_history_case",
    "friend_review",
    "group_settings",
    "help_menu",
    "invites",
    "join_review",
    "knowledge",
    "member_guard",
    "moderation",
    "onebot_tools",
    "permissions",
    "quiz",
)


GLOBAL_PREREQUISITES: tuple[str, ...] = (
    "真实 NapCat/Lagrange 内核已启动，OneBot HTTP 可访问。",
    "Xiami 事件上报地址 http://127.0.0.1:18081/onebot/event 已写入内核配置。",
    "测试 QQ 账号已扫码登录，准备 1 个测试好友和 1 个测试群。",
    "高风险动作验收时，机器人在测试群内具备管理员权限。",
    "涉及 AI/知识库验收时，已准备测试 API Key、测试知识文档和可清理的测试区服。",
)


@dataclass(frozen=True)
class RealSceneCase:
    id: str
    priority: Priority
    area: str
    plugin_ids: tuple[str, ...]
    scene: str
    prerequisites: tuple[str, ...]
    steps: tuple[str, ...]
    expected: tuple[str, ...]
    evidence: tuple[str, ...]
    blockers: tuple[str, ...] = ()


def build_real_scene_cases() -> tuple[RealSceneCase, ...]:
    return (
        RealSceneCase(
            id="RS-P0-001",
            priority="P0",
            area="登录与在线基线",
            plugin_ids=("onebot_tools",),
            scene="真实账号扫码登录后，Xiami 能自动进入 OneBot 在线状态。",
            prerequisites=GLOBAL_PREREQUISITES[:3],
            steps=(
                "启动 Xiami，选择真实 NapCat/Lagrange 内核并点击扫码/登录。",
                "扫码完成后等待 OneBot HTTP 端口在线。",
                "执行 OneBot 状态或刷新登录状态。",
            ),
            expected=(
                "顶部状态显示真实账号、内核 NapCat/Lagrange、连接 online。",
                "状态区能读取 get_login_info 或等价登录信息。",
                "日志中没有重复启动同一账号或反复弹出命令行窗口。",
            ),
            evidence=(
                "账号页截图。",
                "日志页包含 OneBot HTTP Server Start On 127.0.0.1:3000。",
                "xiami_acceptance.ps1 -Mode real 的真实登录 Gate 输出。",
            ),
            blockers=("OneBot 不在线", "二维码无法生成", "重复账号登录冲突"),
        ),
        RealSceneCase(
            id="RS-P0-002",
            priority="P0",
            area="真实收发闭环",
            plugin_ids=("echo", "compat_echo"),
            scene="真实好友和真实群消息能自动进入消息页，并且 Xiami 能分别发送私聊和群聊。",
            prerequisites=GLOBAL_PREREQUISITES[:4],
            steps=(
                "测试好友向机器人发送普通文本和 /echo 文本。",
                "测试群成员向机器人发送普通文本和 /echo 文本。",
                "在消息页分别向好友和测试群发送消息。",
            ),
            expected=(
                "私聊和群聊消息无需手动刷新即可出现在消息页。",
                "好友消息发送成功并返回 message_id。",
                "群消息发送成功并返回 message_id。",
                "Echo/Compat Echo 只在目标会话回复，不串群。",
            ),
            evidence=(
                "消息页截图，包含私聊和群聊接收记录。",
                "日志页包含真实发送成功 message_id。",
                "Xiami 事件 JSONL 或 replay 样本。",
            ),
            blockers=("私聊不进消息页", "群消息失败", "消息只能手动刷新出现"),
        ),
        RealSceneCase(
            id="RS-P0-003",
            priority="P0",
            area="菜单与帮助",
            plugin_ids=("help_menu",),
            scene="用户能在私聊和群聊获取机器人菜单，并且菜单只展示当前启用能力。",
            prerequisites=GLOBAL_PREREQUISITES[:3],
            steps=(
                "私聊发送 菜单、帮助、命令。",
                "群聊发送 机器人菜单 或 功能。",
                "禁用一个测试插件后再次获取菜单。",
            ),
            expected=(
                "菜单文本包含当前核心命令入口。",
                "禁用插件对应入口不再展示。",
                "群聊菜单不泄露后台敏感配置。",
            ),
            evidence=("私聊菜单截图。", "群聊菜单截图。", "插件启停前后的菜单文本。"),
        ),
        RealSceneCase(
            id="RS-P0-004",
            priority="P0",
            area="集中权限",
            plugin_ids=("permissions",),
            scene="主人、全局管理员、本群管理员集中授予和撤销后，权限立即影响受保护命令。",
            prerequisites=GLOBAL_PREREQUISITES[:4],
            steps=(
                "主人添加一个全局管理员和一个本群管理员。",
                "普通成员尝试执行禁言、加黑名单、导入知识等受保护命令。",
                "管理员执行同一命令。",
                "撤销管理员后再次执行。",
            ),
            expected=(
                "普通成员被拒绝且有明确提示。",
                "管理员可执行授权范围内命令。",
                "撤销后权限立即失效。",
                "权限中心能读取主人、全局管理员、本群管理员。",
            ),
            evidence=("权限中心截图。", "普通成员拒绝记录。", "管理员成功记录。"),
            blockers=("权限绕过", "撤销不生效", "跨群权限串扰"),
        ),
        RealSceneCase(
            id="RS-P0-005",
            priority="P0",
            area="分群功能开关",
            plugin_ids=("group_settings",),
            scene="每个群的插件功能独立启停，A 群关闭不会影响 B 群。",
            prerequisites=GLOBAL_PREREQUISITES[:3] + ("准备两个测试群 A/B。",),
            steps=(
                "在 A 群关闭答题或 AI 回复。",
                "A 群触发关闭的功能。",
                "B 群触发同一功能。",
                "重新开启 A 群功能。",
            ),
            expected=(
                "A 群关闭后不响应对应功能或提示已关闭。",
                "B 群仍正常响应。",
                "重新开启后 A 群恢复。",
                "群管页能显示当前群功能开关。",
            ),
            evidence=("A/B 群对比截图。", "群管页本群设置截图。", "后台状态导出 JSON。"),
            blockers=("分群配置不隔离", "开关保存后丢失"),
        ),
        RealSceneCase(
            id="RS-P0-006",
            priority="P0",
            area="高风险群管动作",
            plugin_ids=("member_guard", "moderation"),
            scene="黑白名单、违禁词、禁言、解禁、踢人、撤回策略在真实群内按配置执行。",
            prerequisites=GLOBAL_PREREQUISITES[:4] + ("准备可被操作的测试小号。",),
            steps=(
                "添加本群黑名单、白名单和违禁词。",
                "测试成员发送违禁词、图片/链接/红包等撤回类型样本。",
                "管理员执行禁言、解禁、踢命令。",
                "清理本群黑名单并复测。",
            ),
            expected=(
                "违禁词和撤回类型按群配置处理。",
                "禁言、解禁、踢人成功或明确返回平台拒绝原因。",
                "白名单成员不被误处理。",
                "清理后黑名单不再影响当前群。",
            ),
            evidence=(
                "群管页撤回/风控配置截图。",
                "群内处理结果截图。",
                "OneBot action 返回值或错误码。",
            ),
            blockers=("机器人不是管理员", "高风险动作无证据", "误封白名单成员"),
        ),
        RealSceneCase(
            id="RS-P0-007",
            priority="P0",
            area="账号绑定",
            plugin_ids=("bindings",),
            scene="QQ 与游戏账号/区服账号可绑定、查询、解绑，并支持自定义绑定目录。",
            prerequisites=GLOBAL_PREREQUISITES[:3] + ("准备一个临时绑定数据目录。",),
            steps=(
                "在绑定页选择或输入绑定信息存放目录。",
                "用户发送 绑定 <游戏账号或区服账号>。",
                "用户发送 我的绑定、查询绑定、解绑。",
                "重启 Xiami 后再次读取绑定。",
            ),
            expected=(
                "绑定写入指定目录，不写入错误默认目录。",
                "我的绑定能返回当前账号绑定信息。",
                "解绑后查询为空或明确提示未绑定。",
                "重启后数据仍一致。",
            ),
            evidence=("绑定页目录配置截图。", "绑定文件路径。", "绑定/解绑聊天记录。"),
            blockers=("绑定目录不可配置", "重启丢数据"),
        ),
        RealSceneCase(
            id="RS-P0-008",
            priority="P0",
            area="入群与好友审核",
            plugin_ids=("join_review", "friend_review"),
            scene="入群审核、好友审核、通知人和拒绝理由按规则处理。",
            prerequisites=GLOBAL_PREREQUISITES[:4] + ("准备可申请入群/加好友的测试账号。",),
            steps=(
                "开启入群审核和好友审核。",
                "配置关键词、通知人、拒绝理由和同意备注。",
                "测试账号提交匹配和不匹配的申请。",
                "查看审核记录并重置规则。",
            ),
            expected=(
                "匹配申请按规则通过或拒绝。",
                "通知人收到处理通知。",
                "审核记录可查询。",
                "重置只影响对应审核配置。",
            ),
            evidence=("审核页配置截图。", "申请处理截图。", "审核记录导出。"),
            blockers=("OneBot 未上报 request 事件", "审核规则跨群污染"),
        ),
        RealSceneCase(
            id="RS-P0-009",
            priority="P0",
            area="AI 与知识库",
            plugin_ids=("ai_reply", "knowledge"),
            scene="AI 回复能读取本地知识库、区服索引和会话历史，Provider 异常时不泄露密钥。",
            prerequisites=GLOBAL_PREREQUISITES,
            steps=(
                "导入一份测试知识文档并执行知识搜索。",
                "配置 AI Provider、模型、Base URL 和温度。",
                "私聊和群聊触发 AI 回复。",
                "断开 Provider 或使用错误 Key 触发失败分支。",
            ),
            expected=(
                "知识搜索返回命中来源。",
                "AI 回复能结合知识内容和会话上下文。",
                "Provider 失败时有明确错误提示，不输出 API Key。",
                "群级 AI 开关能独立控制当前群。",
            ),
            evidence=("AI 配置页截图。", "知识搜索结果。", "成功与失败回复记录。"),
            blockers=("Provider 不可用", "密钥泄露", "知识索引为空"),
        ),
        RealSceneCase(
            id="RS-P0-010",
            priority="P0",
            area="重启与留存",
            plugin_ids=FORMAL_PLUGIN_IDS,
            scene="Xiami 和内核重启后，插件配置、分群配置、权限和用户数据不丢失。",
            prerequisites=GLOBAL_PREREQUISITES[:4],
            steps=(
                "保存至少 1 项权限、1 项分群开关、1 条绑定、1 条回答和 1 条知识。",
                "停止 Xiami 和 NapCat/Lagrange。",
                "重新启动 Xiami 并登录同一账号。",
                "读取各插件后台和聊天命令结果。",
            ),
            expected=(
                "所有保存项重启后仍可读取。",
                "不会出现旧进程残留导致重复登录。",
                "消息收发闭环恢复。",
            ),
            evidence=("重启前后配置截图。", "后台状态导出。", "stop/start 日志。"),
            blockers=("停止不彻底", "配置丢失", "重复进程抢端口"),
        ),
        RealSceneCase(
            id="RS-P1-012",
            priority="P1",
            area="邀请积分",
            plugin_ids=("invites",),
            scene="邀请积分启用后，邀请统计、奖励和排行可验证。",
            prerequisites=GLOBAL_PREREQUISITES[:4] + ("测试群允许拉人或有可控入群事件。",),
            steps=(
                "开启邀请积分并设置邀请奖励和留存天数。",
                "测试成员邀请一个小号入群。",
                "查询邀请排行和积分。",
                "移除或退群后检查留存规则。",
            ),
            expected=(
                "邀请人获得配置奖励。",
                "排行包含邀请人。",
                "退群留存规则按配置处理。",
            ),
            evidence=("邀请配置截图。", "入群事件。", "邀请排行记录。"),
        ),
        RealSceneCase(
            id="RS-P1-013",
            priority="P1",
            area="卡密兑换",
            plugin_ids=("cards",),
            scene="卡密生成、导入、兑换、重复兑换拦截和兑换记录可验收。",
            prerequisites=GLOBAL_PREREQUISITES[:3],
            steps=(
                "生成或导入 2 条测试卡密。",
                "普通成员兑换其中 1 条。",
                "同一成员重复兑换同一卡密。",
                "查询卡密记录并清理测试卡密。",
            ),
            expected=(
                "首次兑换成功并发放对应积分或权益。",
                "重复兑换被拒绝。",
                "后台能区分总数和已兑换数。",
            ),
            evidence=("卡密页截图。", "兑换聊天记录。", "卡密数据文件。"),
        ),
        RealSceneCase(
            id="RS-P1-014",
            priority="P1",
            area="自定义回答",
            plugin_ids=("custom_replies",),
            scene="关键词回答、精确回答、删除和列表查询在私聊/群聊正常工作。",
            prerequisites=GLOBAL_PREREQUISITES[:3],
            steps=(
                "添加包含关键词回答和精确回答。",
                "私聊和群聊分别触发。",
                "查询回答列表。",
                "删除回答后再次触发。",
            ),
            expected=(
                "包含匹配和精确匹配规则符合配置。",
                "删除后不再回复。",
                "列表能看到规则摘要。",
            ),
            evidence=("回答页配置截图。", "触发与删除聊天记录。"),
        ),
        RealSceneCase(
            id="RS-P1-015",
            priority="P1",
            area="答题积分",
            plugin_ids=("quiz",),
            scene="题库导入、出题、答题、限时和奖励逻辑可验收。",
            prerequisites=GLOBAL_PREREQUISITES[:3],
            steps=(
                "导入至少 3 道测试题。",
                "开启答题并设置间隔、限时和奖励。",
                "成员答对、答错和超时各一次。",
                "批量删除测试题。",
            ),
            expected=(
                "答对发放奖励。",
                "答错或超时不发放奖励。",
                "同题不会异常重复结算。",
            ),
            evidence=("答题页题库截图。", "答题聊天记录。", "积分变化记录。"),
        ),
        RealSceneCase(
            id="RS-P1-016",
            priority="P1",
            area="OneBot 管理工具",
            plugin_ids=("onebot_tools",),
            scene="常用 OneBot 查询和管理动作在真实环境可用并受权限保护。",
            prerequisites=GLOBAL_PREREQUISITES[:4],
            steps=(
                "查询好友列表、群列表、成员列表和 QQ 资料。",
                "执行戳一戳、群公告、群头衔或精华消息测试动作。",
                "普通成员尝试执行管理动作。",
            ),
            expected=(
                "查询类命令返回结构化结果。",
                "管理动作成功或返回平台拒绝原因。",
                "普通成员无法执行受保护动作。",
            ),
            evidence=("OneBot 工具输出。", "权限拒绝记录。"),
        ),
        RealSceneCase(
            id="RS-P1-017",
            priority="P1",
            area="错误历史",
            plugin_ids=("error_history_case",),
            scene="插件运行异常能被记录、展示和导出，且不阻断其他插件。",
            prerequisites=GLOBAL_PREREQUISITES[:3],
            steps=(
                "触发一个可控插件错误或运行错误历史测试插件。",
                "查看日志页和插件错误历史。",
                "继续触发 Echo 或菜单。",
            ),
            expected=(
                "错误历史包含插件、时间和错误摘要。",
                "其他插件仍可正常响应。",
                "日志不出现乱码替换字符。",
            ),
            evidence=("错误历史截图。", "错误导出文件。", "后续正常命令记录。"),
        ),
        RealSceneCase(
            id="RS-P1-018",
            priority="P1",
            area="知识库管理",
            plugin_ids=("knowledge",),
            scene="本地知识导入、预览、添加、搜索、删除、统计和清空可验收。",
            prerequisites=GLOBAL_PREREQUISITES[:3] + ("准备可删除的测试知识文件。",),
            steps=(
                "导入预览测试文件。",
                "确认后导入并执行知识搜索。",
                "手动添加一条知识并搜索。",
                "删除单条、查看统计、清空测试数据。",
            ),
            expected=(
                "预览不会直接污染正式库。",
                "搜索结果包含标题、来源或片段。",
                "删除和清空只影响测试数据。",
            ),
            evidence=("知识库页截图。", "搜索结果。", "统计输出。"),
        ),
        RealSceneCase(
            id="RS-P2-019",
            priority="P2",
            area="后台导入导出",
            plugin_ids=FORMAL_PLUGIN_IDS,
            scene="后台状态和插件配置可导入导出，用于备份、迁移和回归复现。",
            prerequisites=GLOBAL_PREREQUISITES[:3],
            steps=(
                "导出后台状态和插件包。",
                "修改一项非关键测试配置。",
                "导入先前状态。",
                "运行插件 catalog 和 admin schema smoke。",
            ),
            expected=(
                "导出文件包含插件状态、配置和群级数据摘要。",
                "导入后配置恢复。",
                "导入失败时有 preflight 错误，不破坏当前状态。",
            ),
            evidence=("导出文件路径。", "导入前后配置截图。", "smoke 输出。"),
        ),
        RealSceneCase(
            id="RS-P2-020",
            priority="P2",
            area="长稳运行",
            plugin_ids=FORMAL_PLUGIN_IDS,
            scene="真实环境持续运行 1 小时，私聊、群聊、插件回复和 Provider 可用率满足交付要求。",
            prerequisites=GLOBAL_PREREQUISITES,
            steps=(
                "运行 .\\xiami_acceptance.ps1 -Mode real -ProductGate -LongStability -ExportBundle。",
                "在观察期间混合发送私聊、群聊、菜单、AI 和知识库请求。",
                "导出证据包。",
            ),
            expected=(
                "OneBot 可用率不低于 99%。",
                "Provider 可用率不低于配置阈值。",
                "无旧进程残留、端口冲突、UI 卡死和日志爆量。",
            ),
            evidence=("stability JSONL。", "evidence bundle。", "production gate 输出。"),
            blockers=("长稳样本不足", "可用率不足", "UI 卡顿或日志失控"),
        ),
    )


def real_scene_cases_by_priority(priority: Priority | None = None) -> tuple[RealSceneCase, ...]:
    cases = build_real_scene_cases()
    if priority is None:
        return cases
    return tuple(case for case in cases if case.priority == priority)


def real_scene_case_dicts(cases: tuple[RealSceneCase, ...] | None = None) -> list[dict[str, object]]:
    return [asdict(case) for case in (cases or build_real_scene_cases())]


def format_real_scene_cases_markdown(cases: tuple[RealSceneCase, ...] | None = None) -> str:
    selected = cases or build_real_scene_cases()
    lines = [
        "# Xiami 真实场景验收清单",
        "",
        "此清单用于真实账号、真实群和真实私聊验收；Mock smoke 只负责防止清单结构回退。",
        "",
        "## 全局前置条件",
        "",
    ]
    for item in GLOBAL_PREREQUISITES:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 场景清单",
            "",
        ]
    )
    for case in selected:
        plugins = ", ".join(case.plugin_ids)
        lines.extend(
            [
                f"### {case.id} {case.area} [{case.priority}]",
                "",
                f"- 插件：{plugins}",
                f"- 场景：{case.scene}",
                "- 前置：",
            ]
        )
        lines.extend(f"  - {item}" for item in case.prerequisites)
        lines.append("- 步骤：")
        lines.extend(f"  {index}. {step}" for index, step in enumerate(case.steps, 1))
        lines.append("- 预期：")
        lines.extend(f"  - {item}" for item in case.expected)
        lines.append("- 证据：")
        lines.extend(f"  - {item}" for item in case.evidence)
        if case.blockers:
            lines.append("- 阻断：")
            lines.extend(f"  - {item}" for item in case.blockers)
        lines.append("")
    lines.extend(
        [
            "## 验收判定",
            "",
            "- P0 全部通过：可认为真实登录、真实收发和核心插件闭环达标。",
            "- P1 全部通过：可认为旧插件主要业务功能已完成真实验收。",
            "- P2 全部通过：可进入发布候选和长稳交付阶段。",
        ]
    )
    return "\n".join(lines) + "\n"


def format_real_scene_cases_json(cases: tuple[RealSceneCase, ...] | None = None) -> str:
    payload = {
        "title": "Xiami 真实场景验收清单",
        "formal_plugin_ids": FORMAL_PLUGIN_IDS,
        "global_prerequisites": GLOBAL_PREREQUISITES,
        "cases": real_scene_case_dicts(cases),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def real_scene_summary(cases: tuple[RealSceneCase, ...] | None = None) -> dict[str, object]:
    selected = cases or build_real_scene_cases()
    by_priority = {priority: 0 for priority in ("P0", "P1", "P2")}
    covered_plugins: set[str] = set()
    for case in selected:
        by_priority[case.priority] += 1
        covered_plugins.update(case.plugin_ids)
    return {
        "cases": len(selected),
        "by_priority": by_priority,
        "formal_plugins": len(FORMAL_PLUGIN_IDS),
        "covered_plugins": len(covered_plugins & set(FORMAL_PLUGIN_IDS)),
        "missing_plugins": sorted(set(FORMAL_PLUGIN_IDS) - covered_plugins),
    }
