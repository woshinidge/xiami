from __future__ import annotations

from xiami_core.plugins.real_scene_acceptance import (
    FORMAL_PLUGIN_IDS,
    build_real_scene_cases,
    format_real_scene_cases_markdown,
    real_scene_summary,
)


REQUIRED_AREAS = {
    "登录与在线基线",
    "真实收发闭环",
    "集中权限",
    "分群功能开关",
    "高风险群管动作",
    "AI 与知识库",
    "长稳运行",
}


REQUIRED_TERMS = (
    "真实账号",
    "测试好友",
    "测试群",
    "OneBot HTTP",
    "NapCat/Lagrange",
    "私聊",
    "群聊",
    "禁言",
    "踢人",
    "撤回",
    "入群审核",
    "好友审核",
    "Provider",
    "知识库",
    "重启",
)


def main() -> int:
    cases = build_real_scene_cases()
    ids = [case.id for case in cases]
    if len(ids) != len(set(ids)):
        raise RuntimeError("duplicate real-scene case id")
    if not all(case.steps and case.expected and case.evidence for case in cases):
        raise RuntimeError("real-scene case missing steps/expected/evidence")

    summary = real_scene_summary(cases)
    if summary["missing_plugins"]:
        raise RuntimeError(f"missing plugin coverage: {summary['missing_plugins']}")
    if summary["by_priority"]["P0"] < 10:
        raise RuntimeError("P0 real-scene coverage too small")

    areas = {case.area for case in cases}
    missing_areas = REQUIRED_AREAS - areas
    if missing_areas:
        raise RuntimeError(f"missing required areas: {sorted(missing_areas)}")

    rendered = format_real_scene_cases_markdown(cases)
    missing_terms = [term for term in REQUIRED_TERMS if term not in rendered]
    if missing_terms:
        raise RuntimeError(f"missing required real-scene terms: {missing_terms}")

    for plugin_id in FORMAL_PLUGIN_IDS:
        if plugin_id not in rendered:
            raise RuntimeError(f"plugin id not rendered: {plugin_id}")

    print(
        "real scene acceptance smoke ok: "
        f"{summary['cases']} cases, P0={summary['by_priority']['P0']}, "
        f"plugins={summary['covered_plugins']}/{summary['formal_plugins']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
