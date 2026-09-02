from __future__ import annotations

import time

from xiami_core.plugins.cards import CardService, normalize_status
from xiami_core.plugins.compat import on_command, on_regex
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.permissions import PluginPermissionService
from xiami_core.plugins.points import PointsService


PLUGIN_ID = "cards"
PLUGIN_NAME = "卡密兑换"
PLUGIN_VERSION = "0.2.0"
PLUGIN_DESCRIPTION = "提供卡密生成、导入、库存和兑换功能。"
PLUGIN_CONFIG = {"owners": [], "admins": [], "card_cost": 100}
PRIVATE_DELIVERY_RETRY_DELAYS = (0.25, 0.5)
PLUGIN_ADMIN_SCHEMA = [
    {
        "id": "cards",
        "label": "卡密库存",
        "type": "state",
        "state_key": "cards",
        "commands": ["生成卡密", "导入卡密", "卡密库存", "查询卡密", "修改卡密", "重置卡密", "导出卡密", "删除卡密", "清理卡密", "兑换卡密", "卡密价目", "设置兑换积分"],
    },
    {"id": "card_cost", "label": "兑换积分（每张卡密，可按群覆盖）", "type": "config", "config_key": "card_cost"},
    {"id": "used_cards", "label": "卡密兑换记录", "type": "state", "state_key": "cards", "commands": ["卡密库存 已兑换", "查询卡密"], "description": "同卡密库存，used=true 或 sold=true 的条目为已兑换记录。"},
    {"id": "admins", "label": "卡密管理员", "type": "config", "config_key": "admins"},
]

MATCHERS = []


def on_load(ctx) -> None:
    ctx.log("卡密兑换插件已加载")


@on_command("兑换卡密", aliases=("兑换",), only_group=True, description="兑换卡密：花积分买一张库存卡密，私聊发送")
def redeem(event, ctx, session) -> None:
    if not GroupSettingService(ctx).enabled(session.group_id, "cards_enabled"):
        return
    _do_purchase(event, ctx, session.group_id, session.user_id)


# 兼容旧公告里的「兑换卡密100」写法；数字不再代表卡密面额。
@on_regex(
    r"^兑换(?:卡密)?\d+$",
    fullmatch=True,
    only_group=True,
    description="兑换卡密（兼容旧数字后缀）",
)
def redeem_no_space(event, ctx, session) -> None:
    if not GroupSettingService(ctx).enabled(_group_id_of(event), "cards_enabled"):
        return
    group_id = _group_id_of(event)
    user_id = str(getattr(event, "sender", ""))
    _do_purchase(event, ctx, group_id, user_id)


def _group_id_of(event) -> str:
    if str(getattr(event, "message_type", "")) == "group":
        return str(getattr(event, "target", ""))
    return ""


@on_command(
    "积分兑换卡密",
    aliases=("购买卡密", "积分换卡密", "积分买卡密"),
    only_group=True,
    description="积分兑换卡密：花积分换一张卡密，私聊发送",
)
def buy_card(event, ctx, session) -> None:
    if not GroupSettingService(ctx).enabled(session.group_id, "cards_enabled"):
        return
    _do_purchase(event, ctx, session.group_id, session.user_id)


def _do_purchase(event, ctx, group_id: str, user_id: str) -> None:
    service = CardService(ctx)
    points_service = PointsService(ctx)

    if service.stock_count(group_id) <= 0:
        ctx.reply(event, "当前没有可兑换的卡密，请联系管理员补货。")
        return

    price = service.card_cost(group_id)
    balance = points_service.points(group_id, user_id)
    if balance < price:
        ctx.reply(event, f"积分不足：兑换需要 {price} 积分，你当前 {balance} 积分。")
        return

    # 先占货，再扣分，再私聊下发；任一步失败都要把前面的动作退回去。
    code = service.take_from_stock(group_id, user_id)
    if not code:
        ctx.reply(event, "卡密刚好被取完了，请稍后再试。")
        return

    ok, total = points_service.spend_points(group_id, user_id, price)
    if not ok:
        service.return_to_stock(code)
        ctx.reply(event, f"积分不足：兑换需要 {price} 积分。")
        return

    private_text = f"卡密兑换成功：{code}\n消耗 {price} 积分。请在游戏内使用。"
    sent = _send_private_with_retry(ctx, user_id, private_text)
    if not _send_ok(sent):
        # 私聊发不出去（未加好友／临时会话被关）是常见情况，
        # 必须退积分并把卡密退回库存，不能让玩家扣了分拿不到卡密。
        points_service.add_points(group_id, user_id, price)
        service.return_to_stock(code)
        ctx.reply(event, "私聊发送失败，已退回积分。请先加机器人好友或允许临时会话后重试。")
        return

    # 群里只报结果，不贴卡密，避免被他人抢用。
    ctx.reply(event, f"兑换成功，卡密已私聊发送。消耗 {price} 积分，当前积分：{total}。")


def _send_private_with_retry(ctx, user_id: str, text: str):
    sent = ctx.send_private(user_id, text)
    for delay in PRIVATE_DELIVERY_RETRY_DELAYS:
        if _send_ok(sent):
            break
        time.sleep(delay)
        sent = ctx.send_private(user_id, text)
    return sent


@on_command("卡密价目", aliases=("卡密商店", "卡密价格", "卡密兑换列表"), only_group=True, description="查看卡密兑换所需积分与库存")
def card_prices(event, ctx, session) -> None:
    if not GroupSettingService(ctx).enabled(session.group_id, "cards_enabled"):
        return
    service = CardService(ctx)
    ctx.reply(
        event,
        f"卡密兑换：{service.card_cost(session.group_id)} 积分 / 张，当前库存 {service.stock_count(session.group_id)} 张。\n"
        "兑换方式：发送「兑换卡密」",
    )


@on_command(
    "设置兑换积分",
    aliases=("卡密兑换积分", "设置卡密积分", "设置卡密价格"),
    only_group=True,
    description="设置兑换积分 <积分>：兑换一张卡密所需积分，全局统一",
)
def set_card_cost(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    cost = _to_int(session.argument.strip(), 0)
    if cost <= 0:
        ctx.reply(event, "格式：设置兑换积分 <积分>，例如：设置兑换积分 100")
        return
    value = CardService(ctx).set_card_cost(session.group_id, cost)
    ctx.reply(event, f"已设置本群卡密兑换积分：{value} 积分 / 张")


def _send_ok(result) -> bool:
    if result is None:
        return False
    ok = getattr(result, "ok", None)
    return True if ok is None else bool(ok)


@on_command("生成卡密", only_group=True, description="生成卡密 <数量> [备注]")
def generate_cards(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    count, note = _parse_count_note(session.argument)
    service = CardService(ctx)
    codes = service.generate(count, note=note, owner_group_id=session.group_id)
    price = service.card_cost(session.group_id)

    # 卡密一律私聊发给执行命令的管理员，群里只报数量。
    # 明文刷群会被任何看到的人抢先兑换。
    header = (
        f"已生成卡密 {len(codes)} 个"
        f"（玩家兑换需 {price} 积分 / 张）"
        f"{'，备注：' + note if note else ''}"
    )
    sent_all = True
    for index, chunk in enumerate(_chunk(codes, 100)):
        body = "\n".join(chunk)
        prefix = header if index == 0 else f"（续 {index + 1}）"
        if not _send_ok(ctx.send_private(session.user_id, f"{prefix}\n{body}")):
            sent_all = False
            break

    if sent_all:
        ctx.reply(event, f"已生成卡密 {len(codes)} 个（兑换需 {price} 积分 / 张），卡密已私聊发送。")
    else:
        # 卡密已入库，不回滚——用「导出卡密」仍可取回，不必重新生成。
        ctx.reply(
            event,
            f"已生成卡密 {len(codes)} 个，但私聊发送失败。\n"
            "请先加机器人好友或允许临时会话，然后用「导出卡密 未兑换」取回。",
        )


def _chunk(items: list[str], size: int) -> list[list[str]]:
    return [items[i:i + size] for i in range(0, len(items), size)] or [[]]


@on_command("导入卡密", only_group=True, description="导入卡密 <卡密...>")
def import_cards(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    codes_text = session.argument.strip()
    if not codes_text:
        ctx.reply(event, "格式：导入卡密 <卡密...>")
        return
    service = CardService(ctx)
    count = service.add_many(codes_text, owner_group_id=session.group_id)
    if count <= 0:
        ctx.reply(event, "没有识别到有效卡密。格式：导入卡密 <卡密...>")
        return
    ctx.reply(event, f"已导入卡密：{count} 个（兑换需 {service.card_cost(session.group_id)} 积分 / 张）。")


@on_command("卡密库存", aliases=("卡密列表", "库存卡密"), only_group=True, description="查看卡密库存：卡密库存 [全部/未兑换/已兑换] [关键词]")
def list_cards(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    status, query = _parse_inventory_query(session.argument)
    service = CardService(ctx)
    counts = service.counts(session.group_id)
    rows = service.inventory(status, query, limit=12, group_id=session.group_id)
    status_text = {"all": "全部", "unused": "未兑换", "used": "已兑换"}.get(status, "全部")
    summary = (
        f"卡密库存：共 {counts['total']} 个，未兑换 {counts['unused']} 个，已兑换 {counts['used']} 个。\n"
        f"当前查看：{status_text}{f' / {query}' if query else ''}"
    )
    if not rows:
        ctx.reply(event, summary + "\n没有匹配的卡密。")
        return
    # 明细含卡密明文，私聊发送；群里只留统计，避免未兑换的卡密被抢用。
    detail = "\n".join([summary] + [_format_card_line(row) for row in rows])
    if _send_ok(ctx.send_private(session.user_id, detail)):
        ctx.reply(event, summary + f"\n匹配 {len(rows)} 条，明细已私聊发送。")
    else:
        ctx.reply(event, summary + "\n私聊发送失败，请先加机器人好友或允许临时会话后重试。")


@on_command("查询卡密", aliases=("卡密查询",), only_group=True, description="查询单个卡密：查询卡密 <卡密>")
def query_card(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    if not session.argv:
        ctx.reply(event, "用法：查询卡密 <卡密>")
        return
    card = CardService(ctx).card(session.argv[0], group_id=session.group_id)
    if not card:
        ctx.reply(event, "未找到该卡密。")
        return
    if _send_ok(ctx.send_private(session.user_id, "卡密详情：\n" + _format_card_line(card))):
        ctx.reply(event, "卡密详情已私聊发送。")
    else:
        ctx.reply(event, "私聊发送失败，请先加机器人好友或允许临时会话后重试。")


@on_command("删除卡密", aliases=("移除卡密",), only_group=True, description="删除卡密：删除卡密 <卡密...>")
def delete_cards(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    removed = CardService(ctx).delete_many(session.argument, group_id=session.group_id)
    ctx.reply(event, f"已删除卡密：{removed} 个。")


@on_command("修改卡密", aliases=("设置卡密",), only_group=True, description="修改卡密：修改卡密 <卡密> [备注]（兼容旧积分参数）")
def update_card(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    parts = session.argument.split(maxsplit=2)
    if not parts:
        ctx.reply(event, "格式：修改卡密 <卡密> [备注]（兼容旧格式中的积分参数）")
        return
    code = parts[0]
    points = None
    note = None
    if len(parts) >= 2:
        try:
            points = int(parts[1])
            note = parts[2] if len(parts) >= 3 else None
        except (TypeError, ValueError):
            note = " ".join(parts[1:])
    changed = CardService(ctx).update_many(code, points, note, group_id=session.group_id)
    ctx.reply(event, f"已修改卡密：{changed} 个。")


@on_command("重置卡密", aliases=("恢复卡密", "重置兑换"), only_group=True, description="重置卡密：重置卡密 <卡密...>")
def reset_cards(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    changed = CardService(ctx).reset_many(session.argument, group_id=session.group_id)
    ctx.reply(event, f"已重置卡密：{changed} 个。")






@on_command("导出卡密", aliases=("导出库存",), only_group=True, description="导出卡密：导出卡密 [全部/未兑换/已兑换] [关键词]")
def export_cards(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    status, query = _parse_inventory_query(session.argument)
    rows = CardService(ctx).inventory(status, query, limit=50, group_id=session.group_id)
    if not rows:
        ctx.reply(event, "没有可导出的卡密。")
        return
    # 导出内容含卡密明文，同样只私聊发给管理员。
    lines = [f"卡密导出：{len(rows)} 条"]
    lines.extend(_format_card_export_line(row) for row in rows)
    if _send_ok(ctx.send_private(session.user_id, "\n".join(lines))):
        ctx.reply(event, f"卡密导出 {len(rows)} 条，已私聊发送。")
    else:
        ctx.reply(event, "私聊发送失败，请先加机器人好友或允许临时会话后重试。")


@on_command("清理卡密", aliases=("清空卡密",), only_group=True, description="清理卡密：清理卡密 [全部/未兑换/已兑换]")
def clear_cards(event, ctx, session) -> None:
    if not _require_admin(event, ctx, session):
        return
    status = normalize_status(session.argument)
    removed = CardService(ctx).clear(status, group_id=session.group_id)
    label = {"all": "全部卡密", "unused": "未兑换卡密", "used": "已兑换卡密"}.get(status, "卡密")
    ctx.reply(event, f"已清理{label}：{removed} 个。")


def _require_admin(event, ctx, session) -> bool:
    ok, reason = PluginPermissionService(ctx).require_admin(session.user_id, session.group_id)
    if not ok:
        ctx.reply(event, reason)
        return False
    return True


def _parse_count_note(argument: str) -> tuple[int, str]:
    parts = argument.split()
    count = _to_int(parts[0], 1) if len(parts) >= 1 else 1
    note = " ".join(parts[1:]) if len(parts) >= 2 else ""
    return count, note


def _to_int(value: str, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_inventory_query(argument: str) -> tuple[str, str]:
    parts = str(argument or "").split(maxsplit=1)
    if not parts:
        return "all", ""
    status = normalize_status(parts[0])
    if status != "all" or parts[0].strip().lower() in {"all", "全部"}:
        return status, parts[1].strip() if len(parts) > 1 else ""
    return "all", str(argument or "").strip()


def _card_status(card: dict[str, object]) -> str:
    if card.get("sold"):
        return "已兑换"
    if card.get("used"):
        return "已换积分"
    return "未兑换"


def _format_card_line(card: dict[str, object]) -> str:
    code = str(card.get("code") or "")
    note = str(card.get("note") or "")
    tail = []
    user_id = str(card.get("sold_user_id") or card.get("user_id") or "")
    group_id = str(card.get("sold_group_id") or card.get("group_id") or "")
    if user_id:
        tail.append(f"QQ {user_id}")
    if group_id:
        tail.append(f"群 {group_id}")
    if note:
        tail.append(note)
    at = str(card.get("sold_at") or card.get("used_at") or "")
    created_at = str(card.get("created_at") or "")
    if at:
        tail.append(f"兑换时间 {at}")
    elif created_at:
        tail.append(f"创建时间 {created_at}")
    suffix = f" / {' / '.join(tail)}" if tail else ""
    return f"- {code}：{_card_status(card)}{suffix}"


def _format_card_export_line(card: dict[str, object]) -> str:
    return "\t".join(
        [
            str(card.get("code") or ""),
            _card_status(card),
            str(card.get("sold_user_id") or card.get("user_id") or ""),
            str(card.get("sold_group_id") or card.get("group_id") or ""),
            str(card.get("sold_at") or card.get("used_at") or ""),
            str(card.get("created_at") or ""),
            str(card.get("note") or ""),
        ]
    )


MATCHERS.extend([
    redeem, redeem_no_space, buy_card, card_prices, set_card_cost,
    generate_cards, import_cards, list_cards,
    query_card, delete_cards, update_card, reset_cards, export_cards, clear_cards,
])
