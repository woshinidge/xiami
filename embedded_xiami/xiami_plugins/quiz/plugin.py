from __future__ import annotations

from xiami_core.plugins.compat import on_command
from xiami_core.plugins.permissions import PluginPermissionService
from xiami_core.plugins.quiz import QuizService


PLUGIN_ID = "quiz"
PLUGIN_NAME = "答题积分"
PLUGIN_VERSION = "0.1.0"
PLUGIN_DESCRIPTION = "提供群内出题、答题和答题积分功能。"
PLUGIN_CONFIG = {
    "owners": [],
    "admins": [],
    "quiz_enabled": True,
    "quiz_reward_points": 1,
    "quiz_interval_seconds": 0,
    "quiz_answer_timeout_seconds": 0,
}
PLUGIN_ADMIN_SCHEMA = [
    {
        "id": "quiz_bank",
        "label": "题库",
        "type": "state",
        "state_key": "quiz_bank",
        "commands": ["加题", "改题", "批量加题", "删题", "启用题", "停用题", "导出题库", "清空题库", "题库"],
    },
    {"id": "quiz_sessions", "label": "答题会话", "type": "state", "state_key": "quiz_sessions", "commands": ["出题", "答题", "清除答题"]},
    {"id": "settings", "label": "答题设置", "type": "state", "state_key": "settings", "commands": ["答题设置", "开启答题", "关闭答题", "设置答题奖励", "设置答题间隔", "设置答题限时"]},
    {"id": "quiz_reward_points", "label": "答题奖励积分", "type": "config", "config_key": "quiz_reward_points"},
    {"id": "quiz_interval_seconds", "label": "发题间隔秒", "type": "config", "config_key": "quiz_interval_seconds"},
    {"id": "quiz_answer_timeout_seconds", "label": "答题限时秒", "type": "config", "config_key": "quiz_answer_timeout_seconds"},
]

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("答题积分插件已加载")


@on_command("出题", only_group=True, description="从本群题库随机出题")
def start_quiz(event, ctx, session) -> None:
    result = QuizService(ctx).start(session.group_id)
    if result.handled and result.message:
        ctx.reply(event, result.message)


@on_command("答题", aliases=("答案",), only_group=True, description="答题 <答案>")
def answer_quiz(event, ctx, session) -> None:
    answer = session.argument.strip()
    if not answer:
        ctx.reply(event, "格式：答题 答案")
        return
    result = QuizService(ctx).answer(session.group_id, session.user_id, answer)
    if result.handled and result.message:
        ctx.reply(event, result.message)


@on_command("加题", aliases=("添加题目",), only_group=True, description="加题 问题=答案；支持 分类:问题=答案、停用:问题=答案")
def add_question(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    service = QuizService(ctx)
    item_data = service.parse_question_entry(session.argument)
    if item_data is None:
        ctx.reply(event, "格式：加题 问题=答案；也支持 分类:问题=答案、停用:问题=答案")
        return
    item = service.add_question(
        session.group_id,
        item_data.question,
        item_data.answer,
        category=item_data.category,
        note=item_data.note,
        enabled=item_data.enabled,
    )
    if item is None:
        ctx.reply(event, "格式：加题 问题=答案")
        return
    suffix = "（停用）" if not item.enabled else ""
    category = f" [{item.category}]" if item.category else ""
    ctx.reply(event, f"已添加题目 #{item.question_id}{category}{suffix}。")


@on_command("改题", aliases=("修改题目",), only_group=True, description="改题 <题目ID> 问题=答案")
def update_question(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    question_id, raw = _split_first_word(session.argument)
    if not question_id or not raw:
        ctx.reply(event, "格式：改题 <题目ID> 问题=答案")
        return
    service = QuizService(ctx)
    item_data = service.parse_question_entry(raw)
    if item_data is None:
        ctx.reply(event, "格式：改题 <题目ID> 问题=答案")
        return
    item = service.update_question(
        session.group_id,
        question_id,
        item_data.question,
        item_data.answer,
        category=item_data.category,
        note=item_data.note,
        enabled=item_data.enabled,
    )
    if item is None:
        ctx.reply(event, f"未找到题目 #{question_id}。")
        return
    ctx.reply(event, f"已修改题目 #{item.question_id}。")


@on_command("删题", aliases=("删除题目",), only_group=True, description="删题 <题目ID...>")
def delete_question(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    question_ids = session.argument.strip()
    if not question_ids:
        ctx.reply(event, "格式：删题 <题目ID...>")
        return
    count = QuizService(ctx).delete_questions(session.group_id, question_ids)
    ctx.reply(event, f"已删除题目：{count} 条。")


@on_command("启用题", aliases=("开启题目",), only_group=True, description="启用题 <题目ID...>")
def enable_questions(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    count = QuizService(ctx).set_question_enabled(session.group_id, session.argument, True)
    ctx.reply(event, f"已启用题目：{count} 条。")


@on_command("停用题", aliases=("关闭题目", "禁用题"), only_group=True, description="停用题 <题目ID...>")
def disable_questions(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    count = QuizService(ctx).set_question_enabled(session.group_id, session.argument, False)
    ctx.reply(event, f"已停用题目：{count} 条。")


@on_command("题库", aliases=("题目列表",), only_group=True, description="查看本群题库；可加关键词筛选")
def list_questions(event, ctx, session) -> None:
    query = session.argument.strip()
    questions = QuizService(ctx).list_questions(session.group_id, query)
    if not questions:
        ctx.reply(event, "本群题库为空。" if not query else f"没有找到匹配“{query}”的题目。")
        return
    title = "本群题库：" if not query else f"本群题库（筛选：{query}）："
    lines = [title]
    for item in questions[:20]:
        status = "启用" if item.enabled else "停用"
        category = f"[{item.category}] " if item.category else ""
        note = f"（{item.note}）" if item.note else ""
        lines.append(f"#{item.question_id} {status} {category}{item.question} = {item.answer}{note}")
    if len(questions) > 20:
        lines.append(f"... 共 {len(questions)} 条，仅显示前 20 条。")
    ctx.reply(event, "\n".join(lines))


@on_command("导出题库", aliases=("导出答题题库",), only_group=True, description="导出题库 [关键词]")
def export_questions(event, ctx, session) -> None:
    query = session.argument.strip()
    text = QuizService(ctx).export_questions(session.group_id, query)
    ctx.reply(event, text)


@on_command("批量加题", aliases=("导入题库", "批量导入题库"), only_group=True, description="批量加题，每行 题目=答案")
def import_questions(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    text = session.argument.strip()
    if not text:
        ctx.reply(event, "格式：批量加题 题目=答案（可换行多题；支持 分类:题目=答案、停用:题目=答案、分类|题目|答案|备注）")
        return
    count = QuizService(ctx).import_questions(session.group_id, text)
    ctx.reply(event, f"已导入题目：{count} 条。")


@on_command("清空题库", aliases=("清空答题题库",), only_group=True, description="清空本群题库")
def clear_questions(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    removed = QuizService(ctx).clear_group(session.group_id)
    ctx.reply(event, f"已清空本群题库：{removed} 条。")


@on_command("清除答题", aliases=("取消出题", "结束答题"), only_group=True, description="清除当前进行中的答题")
def cancel_quiz(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    removed = QuizService(ctx).cancel_current(session.group_id)
    ctx.reply(event, "已清除当前答题。" if removed else "当前没有正在进行的题目。")


@on_command("答题设置", only_group=True, description="查看本群答题设置")
def quiz_settings(event, ctx, session) -> None:
    service = QuizService(ctx)
    questions = service.list_questions(session.group_id)
    enabled_count = service.question_count(session.group_id, enabled_only=True)
    ctx.reply(
        event,
        "\n".join(
            [
                "答题设置：",
                f"状态：{'已开启' if service.enabled(session.group_id) else '已关闭'}",
                f"答题奖励：{service.reward_points(session.group_id)} 积分",
                f"出题间隔：{service.interval_seconds(session.group_id)} 秒",
                f"答题限时：{service.answer_timeout_seconds(session.group_id)} 秒",
                f"题库数量：{len(questions)} 条（启用 {enabled_count} 条）",
            ]
        ),
    )


@on_command("设置答题奖励", aliases=("答题奖励",), only_group=True, description="设置答题奖励 <积分>")
def set_quiz_reward(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    value = _parse_non_negative_int(session.argument, minimum=1)
    if value is None:
        ctx.reply(event, "格式：设置答题奖励 <积分>")
        return
    QuizService(ctx).set_reward_points(session.group_id, value)
    ctx.reply(event, f"已设置本群答题奖励：{value} 积分。")


@on_command("设置答题间隔", aliases=("答题间隔",), only_group=True, description="设置答题间隔 <秒>")
def set_quiz_interval(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    value = _parse_non_negative_int(session.argument, minimum=0)
    if value is None:
        ctx.reply(event, "格式：设置答题间隔 <秒>")
        return
    QuizService(ctx).set_interval_seconds(session.group_id, value)
    ctx.reply(event, f"已设置本群出题间隔：{value} 秒。")


@on_command("设置答题限时", aliases=("答题限时",), only_group=True, description="设置答题限时 <秒，0为不限时>")
def set_quiz_timeout(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    value = _parse_non_negative_int(session.argument, minimum=0)
    if value is None:
        ctx.reply(event, "格式：设置答题限时 <秒，0为不限时>")
        return
    QuizService(ctx).set_answer_timeout_seconds(session.group_id, value)
    ctx.reply(event, f"已设置本群答题限时：{value} 秒。")


@on_command("开启答题", only_group=True, admin_only=True, description="开启本群答题")
def enable_quiz(event, ctx, session) -> None:
    QuizService(ctx).set_enabled(session.group_id, True)
    ctx.reply(event, "本群答题已开启。")


@on_command("关闭答题", only_group=True, admin_only=True, description="关闭本群答题")
def disable_quiz(event, ctx, session) -> None:
    QuizService(ctx).set_enabled(session.group_id, False)
    ctx.reply(event, "本群答题已关闭。")


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


def _parse_non_negative_int(text: str, *, minimum: int):
    try:
        value = int(str(text or "").strip())
    except (TypeError, ValueError):
        return None
    return value if value >= minimum else None


def _split_first_word(text: str) -> tuple[str, str]:
    parts = str(text or "").strip().split(maxsplit=1)
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[1].strip()


MATCHERS.extend([
    start_quiz,
    answer_quiz,
    add_question,
    update_question,
    delete_question,
    enable_questions,
    disable_questions,
    list_questions,
    export_questions,
    import_questions,
    clear_questions,
    cancel_quiz,
    quiz_settings,
    set_quiz_reward,
    set_quiz_interval,
    set_quiz_timeout,
    enable_quiz,
    disable_quiz,
])
