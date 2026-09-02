from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time


EMBEDDED_ROOT = Path(__file__).resolve().parents[2]
if str(EMBEDDED_ROOT) not in sys.path:
    sys.path.insert(0, str(EMBEDDED_ROOT))


from xiami_core.models import SendResult, XiamiMessage
from xiami_core.plugins.cards import CardService
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.group_settings import GroupSettingService
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.points import (
    POINTS_NAMESPACE,
    POINTS_STATE_KEY,
    _POINTS_MIGRATED_KEY,
    PointsService,
    state_transaction,
)
from xiami_core.plugins.state import PluginStateStore
from xiami_plugins.cards.plugin import _do_purchase


_PROCESS_TIMEOUT_SECONDS = 8.0
_LOCK_TIMEOUT_SECONDS = 0.2


def _send_ok(*_args) -> SendResult:
    return SendResult(ok=True)


class _SlowCardService(CardService):
    def _cards(self):
        cards = super()._cards()
        time.sleep(0.05)
        return cards


class _SlowPointsService(PointsService):
    def _points(self):
        groups = super()._points()
        time.sleep(0.05)
        return groups


def _take_from_stock_process(state_root_text, ready, start, result_queue, user_id: str) -> None:
    try:
        ctx = PluginContext(
            send_fn=_send_ok,
            state_store=PluginKVStore(Path(state_root_text)),
            plugin_id="cards",
        )
        ready.set()
        if not start.wait(_PROCESS_TIMEOUT_SECONDS):
            raise RuntimeError("take-from-stock worker start timed out")
        result_queue.put(("take", user_id, _SlowCardService(ctx).take_from_stock("G1", user_id)))
    except BaseException as exc:
        result_queue.put(("error", user_id, f"{type(exc).__name__}: {exc}"))
        raise


def _spend_points_process(state_root_text, ready, start, result_queue, user_id: str) -> None:
    try:
        ctx = PluginContext(
            send_fn=_send_ok,
            state_store=PluginKVStore(Path(state_root_text)),
            plugin_id="cards",
        )
        ready.set()
        if not start.wait(_PROCESS_TIMEOUT_SECONDS):
            raise RuntimeError("spend-points worker start timed out")
        result_queue.put(("spend", user_id, _SlowPointsService(ctx).spend_points("G1", user_id, 100)))
    except BaseException as exc:
        result_queue.put(("error", user_id, f"{type(exc).__name__}: {exc}"))
        raise


def _hold_lock_process(state_root_text, acquired, release) -> None:
    ctx = PluginContext(
        send_fn=_send_ok,
        state_store=PluginKVStore(Path(state_root_text)),
        plugin_id="cards",
    )
    with state_transaction(ctx):
        acquired.set()
        if not release.wait(_PROCESS_TIMEOUT_SECONDS):
            raise RuntimeError("lock holder release timed out")


def _crash_while_holding_lock_process(state_root_text, acquired) -> None:
    ctx = PluginContext(
        send_fn=_send_ok,
        state_store=PluginKVStore(Path(state_root_text)),
        plugin_id="cards",
    )
    with state_transaction(ctx):
        acquired.set()
        time.sleep(0.1)
        # Deliberately skip context-manager cleanup: Windows must release the
        # byte-range lock when this worker process exits.
        os._exit(0)


def _stop_processes(processes) -> None:
    for process in processes:
        if process.is_alive():
            process.terminate()
    for process in processes:
        process.join(timeout=_PROCESS_TIMEOUT_SECONDS)


def _join_process(process, label: str) -> None:
    process.join(timeout=_PROCESS_TIMEOUT_SECONDS)
    if process.is_alive():
        process.terminate()
        process.join(timeout=_PROCESS_TIMEOUT_SECONDS)
        raise RuntimeError(f"{label} process timed out")
    if process.exitcode != 0:
        raise RuntimeError(f"{label} process failed with exit code {process.exitcode}")


def _spawn_pair(worker, state_root: Path, user_ids: tuple[str, str]) -> list[tuple]:
    context = multiprocessing.get_context("spawn")
    ready_events = [context.Event(), context.Event()]
    start = context.Event()
    result_queue = context.Queue()
    processes = [
        context.Process(target=worker, args=(str(state_root), ready_events[index], start, result_queue, user_id))
        for index, user_id in enumerate(user_ids)
    ]
    try:
        for process in processes:
            process.start()
        for index, ready in enumerate(ready_events):
            if not ready.wait(_PROCESS_TIMEOUT_SECONDS):
                raise RuntimeError(f"spawn worker {index} was not ready")
        start.set()
        results = []
        for _ in processes:
            try:
                results.append(result_queue.get(timeout=_PROCESS_TIMEOUT_SECONDS))
            except queue.Empty:
                raise RuntimeError("spawn workers did not return all results")
        for process in processes:
            _join_process(process, "spawn worker")
        errors = [item for item in results if item and item[0] == "error"]
        if errors:
            raise RuntimeError(f"spawn worker errors: {errors}")
        return results
    finally:
        _stop_processes(processes)
        result_queue.close()
        result_queue.join_thread()


class _RaiseAfterSharedSave(PluginKVStore):
    """模拟原子替换已经成功、调用方却收到异常的边界情况。"""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.raise_once = True

    def save(self, plugin_id: str, data: dict) -> None:
        super().save(plugin_id, data)
        if plugin_id == POINTS_NAMESPACE and self.raise_once:
            self.raise_once = False
            raise OSError("simulated post-commit failure")


def _plugin_command_smoke(root: Path) -> None:
    sent: list[tuple[str, str, str]] = []

    def send(target: str, text: str, message_type: str) -> SendResult:
        sent.append((target, text, message_type))
        return SendResult(ok=True)

    source = EMBEDDED_ROOT / "xiami_plugins" / "cards"
    plugin_root = root / "plugins"
    plugin_dir = plugin_root / "cards"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
    (plugin_dir / "plugin_config.json").write_text('{"admins":["10001"],"card_cost":100}', encoding="utf-8")

    state_store = PluginKVStore(root / "state")
    ctx = PluginContext(send_fn=send, state_store=state_store)
    settings = GroupSettingService(ctx)
    for group_id in ("20001", "20002"):
        settings.set_plugin_enabled(group_id, "cards", True)
        settings.set_enabled(group_id, "cards_enabled", True)
    loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
    plugins = loader.load_all()
    if not plugins or plugins[0].error:
        raise RuntimeError(f"cards plugin load failed: {plugins}")
    plugin_ctx = plugins[0].context

    def msg(sender: str, text: str, group_id: str = "20001") -> XiamiMessage:
        return XiamiMessage(message_type="group", sender=sender, target=group_id, text=text)

    loader.dispatch_message(msg("99999", "导入卡密 TEST-Z"))
    loader.dispatch_message(msg("10001", "导入卡密 TEST-A TEST-B TEST-C"))
    loader.dispatch_message(msg("10001", "导入卡密 TEST-D", "20002"))
    CardService(plugin_ctx).add_many("TEST-E TEST-F", owner_group_id="20001")
    PointsService(plugin_ctx).set_points("20001", "10002", 300)

    loader.dispatch_message(msg("10001", "卡密库存 未兑换 TEST"))
    loader.dispatch_message(msg("10002", "兑换"))
    loader.dispatch_message(msg("10002", "兑换卡密"))
    loader.dispatch_message(msg("10002", "兑换卡密100"))
    loader.dispatch_message(msg("99999", "查询卡密 TEST-B"))
    loader.dispatch_message(msg("10001", "查询卡密 TEST-B"))
    loader.dispatch_message(msg("10001", "修改卡密 TEST-B 9 新备注"))
    loader.dispatch_message(msg("10001", "查询卡密 TEST-B"))

    reserved = CardService(plugin_ctx).take_from_stock("20001", "10003")
    if reserved != "TEST-E":
        raise RuntimeError(
            f"unexpected reserved card: {reserved!r}, plugin={plugins[0].id!r}, "
            f"context={plugin_ctx.plugin_id!r}, state={plugin_ctx.get_state('cards', {})!r}, "
            f"files={list((root / 'state').glob('*'))!r}"
        )
    loader.dispatch_message(msg("10001", "重置卡密 TEST-B"))
    loader.dispatch_message(msg("10001", "查询卡密 TEST-B"))
    loader.dispatch_message(msg("10001", "删除卡密 TEST-C"))
    loader.dispatch_message(msg("10001", "查询卡密 TEST-C"))
    loader.dispatch_message(msg("10001", "查询卡密 TEST-D"))

    texts = [item[1] for item in sent]
    required = [
        "权限不足，需要管理员。",
        "已导入卡密：3 个（兑换需 100 积分 / 张）。",
        "兑换成功，卡密已私聊发送。消耗 100 积分，当前积分：100。",
        "已修改卡密：1 个。",
        "已重置卡密：1 个。",
        "已删除卡密：1 个。",
    ]
    for item in required:
        if item not in texts:
            raise RuntimeError(f"missing card reply {item!r}: {texts}")
    for code in ("TEST-A", "TEST-B", "TEST-C"):
        if not any(message_type == "private" and f"卡密兑换成功：{code}" in text for _, text, message_type in sent):
            raise RuntimeError(f"purchase command did not send {code}: {sent}")
    if any("卡密不能为空" in text for text in texts):
        raise RuntimeError(f"purchase command fell back to legacy card redemption: {texts}")
    if not any("卡密详情：" in text and "TEST-B" in text and "新备注" in text for text in texts):
        raise RuntimeError(f"updated card query missing: {texts}")
    if not any("卡密详情：" in text and "TEST-B" in text and "未兑换" in text for text in texts):
        raise RuntimeError(f"reset card query missing: {texts}")
    if texts.count("未找到该卡密。") < 2:
        raise RuntimeError(f"delete/group ownership query did not fail closed: {texts}")
    inventory = [text for _, text, kind in sent if kind == "private" and text.startswith("卡密库存：")]
    if not inventory or "TEST-D" in inventory[0]:
        raise RuntimeError(f"cross-group inventory leak: {inventory}")


def _purchase_delivery_retry_smoke(root: Path) -> None:
    def run_case(name: str, private_results: list[bool]) -> tuple[list[tuple[str, str, str]], PluginContext]:
        sent: list[tuple[str, str, str]] = []

        def send(target: str, text: str, message_type: str) -> SendResult:
            sent.append((target, text, message_type))
            if message_type != "private":
                return SendResult(ok=True)
            index = sum(1 for _, _, kind in sent if kind == "private") - 1
            ok = private_results[min(index, len(private_results) - 1)]
            return SendResult(ok=ok, detail="simulated delivery result")

        ctx = PluginContext(
            send_fn=send,
            state_store=PluginKVStore(root / name),
            plugin_id="cards",
        )
        CardService(ctx).add_many(f"CARD-{name}", owner_group_id="G1")
        PointsService(ctx).set_points("G1", "U1", 100)
        event = XiamiMessage(message_type="group", sender="U1", target="G1", text="兑换")
        _do_purchase(event, ctx, "G1", "U1")
        return sent, ctx

    retry_sent, retry_ctx = run_case("RETRY", [False, True])
    retry_private = [item for item in retry_sent if item[2] == "private"]
    if len(retry_private) != 2 or retry_private[0][1] != retry_private[1][1]:
        raise RuntimeError(f"delivery retry did not resend the same card exactly once: {retry_sent}")
    if PointsService(retry_ctx).points("G1", "U1") != 0 or CardService(retry_ctx).stock_count("G1") != 0:
        raise RuntimeError("successful delivery retry rolled back points or stock")
    if not any("兑换成功，卡密已私聊发送" in text for _, text, kind in retry_sent if kind == "group"):
        raise RuntimeError(f"successful retry did not report success: {retry_sent}")

    failed_sent, failed_ctx = run_case("FAIL", [False, False, False])
    if len([item for item in failed_sent if item[2] == "private"]) != 3:
        raise RuntimeError(f"failed delivery did not stop after three attempts: {failed_sent}")
    if PointsService(failed_ctx).points("G1", "U1") != 100 or CardService(failed_ctx).stock_count("G1") != 1:
        raise RuntimeError("failed delivery did not restore points and stock")
    if not any("私聊发送失败，已退回积分" in text for _, text, kind in failed_sent if kind == "group"):
        raise RuntimeError(f"failed delivery did not report rollback: {failed_sent}")

    success_sent, success_ctx = run_case("SUCCESS", [True])
    if len([item for item in success_sent if item[2] == "private"]) != 1:
        raise RuntimeError(f"successful delivery was sent more than once: {success_sent}")
    if PointsService(success_ctx).points("G1", "U1") != 0 or CardService(success_ctx).stock_count("G1") != 0:
        raise RuntimeError("first-attempt success did not consume points and stock")


def _card_concurrency_smoke(root: Path) -> None:
    ctx = PluginContext(
        send_fn=lambda *_: SendResult(ok=True),
        state_store=PluginKVStore(root / "card-race-state"),
        plugin_id="cards",
    )
    service = _SlowCardService(ctx)
    service.add_many("RACE-CARD", owner_group_id="G1")
    start = threading.Barrier(3)
    results: list[str] = []

    def take(user_id: str) -> None:
        start.wait()
        results.append(service.take_from_stock("G1", user_id))

    threads = [threading.Thread(target=take, args=(f"U{index}",)) for index in range(2)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2)
    if any(thread.is_alive() for thread in threads):
        raise RuntimeError("card concurrency smoke timed out")
    if sorted(results) != ["", "RACE-CARD"]:
        raise RuntimeError(f"same card sold more than once: {results}")


def _points_atomicity_smoke(root: Path) -> None:
    migration_store = _RaiseAfterSharedSave(root / "migration-state")
    migration_store.set("checkin", POINTS_STATE_KEY, {"G1": {"U1": 100}})
    migration_ctx = PluginContext(
        send_fn=lambda *_: SendResult(ok=True),
        state_store=migration_store,
        plugin_id="cards",
    )
    migration_service = PointsService(migration_ctx)
    first = migration_service.points("G1", "U1")
    second = migration_service.points("G1", "U1")
    shared = migration_store.load(POINTS_NAMESPACE)
    if first != 100 or second != 100:
        raise RuntimeError(f"legacy points were merged twice: first={first}, second={second}")
    if shared.get(_POINTS_MIGRATED_KEY) is not True:
        raise RuntimeError(f"migration marker missing from atomic payload: {shared}")

    spend_ctx = PluginContext(
        send_fn=lambda *_: SendResult(ok=True),
        state_store=PluginKVStore(root / "spend-race-state"),
        plugin_id="cards",
    )
    PointsService(spend_ctx).set_points("G1", "U1", 100)
    spend_service = _SlowPointsService(spend_ctx)
    start = threading.Barrier(3)
    results: list[tuple[bool, int]] = []

    def spend() -> None:
        start.wait()
        results.append(spend_service.spend_points("G1", "U1", 100))

    threads = [threading.Thread(target=spend) for _ in range(2)]
    for thread in threads:
        thread.start()
    start.wait()
    for thread in threads:
        thread.join(timeout=2)
    if any(thread.is_alive() for thread in threads):
        raise RuntimeError("points concurrency smoke timed out")
    if sum(1 for ok, _ in results if ok) != 1 or spend_service.points("G1", "U1") != 0:
        raise RuntimeError(f"points spent more than once: {results}")


def _process_concurrency_smoke(root: Path) -> None:
    card_root = root / "take-from-stock"
    card_ctx = PluginContext(send_fn=_send_ok, state_store=PluginKVStore(card_root), plugin_id="cards")
    CardService(card_ctx).add_many("PROCESS-RACE-CARD", owner_group_id="G1")
    card_results = _spawn_pair(_take_from_stock_process, card_root, ("U1", "U2"))
    if sorted(item[2] for item in card_results) != ["", "PROCESS-RACE-CARD"]:
        raise RuntimeError(f"processes sold the same card more than once: {card_results}")

    points_root = root / "spend-points"
    points_ctx = PluginContext(send_fn=_send_ok, state_store=PluginKVStore(points_root), plugin_id="cards")
    PointsService(points_ctx).set_points("G1", "U1", 100)
    spend_results = _spawn_pair(_spend_points_process, points_root, ("U1", "U1"))
    if sum(1 for item in spend_results if item[2][0]) != 1:
        raise RuntimeError(f"processes spent the same balance more than once: {spend_results}")
    if PointsService(points_ctx).points("G1", "U1") != 0:
        raise RuntimeError("process spend did not leave the expected zero balance")

def _state_lock_regression_smoke(root: Path) -> None:
    state_root = root / "state-lock"
    ctx = PluginContext(send_fn=_send_ok, state_store=PluginKVStore(state_root), plugin_id="cards")
    CardService(ctx).add_many("LOCK-ENUM")
    lock_path = state_root / ".xiami-state.lock"
    if not lock_path.is_file() or lock_path.read_bytes() != b"\0":
        raise RuntimeError(f"state lock sentinel is invalid: {lock_path}")

    # The same thread may enter helper methods which acquire the state lock again.
    with state_transaction(ctx):
        with state_transaction(ctx):
            pass
    try:
        with state_transaction(ctx):
            raise ValueError("simulated transaction failure")
    except ValueError:
        pass
    else:
        raise RuntimeError("transaction exception smoke did not raise")
    with state_transaction(ctx, timeout=_LOCK_TIMEOUT_SECONDS):
        pass

    context = multiprocessing.get_context("spawn")
    acquired = context.Event()
    release = context.Event()
    holder = context.Process(target=_hold_lock_process, args=(str(state_root), acquired, release))
    try:
        holder.start()
        if not acquired.wait(_PROCESS_TIMEOUT_SECONDS):
            raise RuntimeError("lock holder did not acquire the state lock")
        try:
            with state_transaction(ctx, timeout=_LOCK_TIMEOUT_SECONDS):
                raise RuntimeError("state lock did not time out while another process held it")
        except TimeoutError:
            pass
        release.set()
        _join_process(holder, "lock holder")
        with state_transaction(ctx, timeout=_LOCK_TIMEOUT_SECONDS):
            pass
    finally:
        _stop_processes([holder])

    crash_acquired = context.Event()
    crashed = context.Process(target=_crash_while_holding_lock_process, args=(str(state_root), crash_acquired))
    try:
        crashed.start()
        if not crash_acquired.wait(_PROCESS_TIMEOUT_SECONDS):
            raise RuntimeError("crash worker did not acquire the state lock")
        _join_process(crashed, "crash lock holder")
        with state_transaction(ctx, timeout=_PROCESS_TIMEOUT_SECONDS):
            pass
    finally:
        _stop_processes([crashed])

    business_json = sorted(state_root.glob("*.json"))
    if not business_json:
        raise RuntimeError("state lock smoke did not produce business JSON")
    if any(path.name == lock_path.name for path in business_json):
        raise RuntimeError(f"lock sentinel leaked into business JSON enumeration: {business_json}")
    for path in business_json:
        json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _plugin_command_smoke(root / "plugin")
        _purchase_delivery_retry_smoke(root / "delivery-retry")
        _card_concurrency_smoke(root / "card-race")
        _points_atomicity_smoke(root / "points")
        _process_concurrency_smoke(root / "process-race")
        _state_lock_regression_smoke(root / "lock-regression")
    print("cards and points regression smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
