from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
import os
from pathlib import Path
import re
import threading
import time
from typing import Any

from xiami_core.plugins.context import PluginContext


# 积分账本必须跨插件共用；ctx.get_state/set_state 会按 plugin_id 分命名空间，
# 若各积分插件各写一份，卡密兑换将无法读取其他插件产生的余额。
# 因此积分固定存到一个共享命名空间，与调用方是哪个插件无关。
POINTS_NAMESPACE = "xiami_points_shared"
POINTS_STATE_KEY = "points"
_POINTS_MIGRATED_KEY = "_points_merged_from_plugin_namespaces"

# 历史上可能各自写过积分的插件命名空间，首次读取时合并进共享账本。
_LEGACY_POINTS_NAMESPACES = ("checkin", "cards", "quiz", "invites", "shared", "group_settings")

_STATE_LOCK_FILE = ".xiami-state.lock"
_STATE_LOCK_TIMEOUT_SECONDS = 10.0
_STATE_LOCK_REGISTRY_GUARD = threading.Lock()
_STATE_LOCK_REGISTRY: dict[str, "_ReentrantProcessFileLock"] = {}
_FALLBACK_STATE_LOCK = threading.RLock()


@dataclass(frozen=True)
class CheckinResult:
    ok: bool
    message: str


class _ReentrantProcessFileLock:
    """Thread-reentrant OS lock whose ownership dies with the process handle."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._thread_lock = threading.RLock()
        self._owner_thread: int | None = None
        self._depth = 0
        self._handle = None

    def acquire(self, timeout: float) -> bool:
        wait_seconds = max(0.0, float(timeout))
        deadline = time.monotonic() + wait_seconds
        if not self._thread_lock.acquire(timeout=wait_seconds):
            return False

        thread_id = threading.get_ident()
        if self._owner_thread == thread_id:
            self._depth += 1
            return True

        handle = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle = self.path.open("a+b", buffering=0)
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
                handle.write(b"\0")
            while True:
                try:
                    _try_lock_file(handle)
                    break
                except OSError:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        handle.close()
                        return False
                    time.sleep(min(0.05, remaining))
            self._owner_thread = thread_id
            self._depth = 1
            self._handle = handle
            return True
        except BaseException:
            if handle is not None and not handle.closed:
                handle.close()
            raise
        finally:
            if self._owner_thread != thread_id:
                self._thread_lock.release()

    def release(self) -> None:
        if self._owner_thread != threading.get_ident() or self._depth <= 0:
            raise RuntimeError("state lock released by a non-owner thread")
        self._depth -= 1
        try:
            if self._depth == 0:
                handle = self._handle
                self._handle = None
                self._owner_thread = None
                if handle is not None:
                    try:
                        _unlock_file(handle)
                    finally:
                        handle.close()
        finally:
            self._thread_lock.release()


def _try_lock_file(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _state_lock_path(ctx) -> Path | None:
    store = getattr(ctx, "state_store", None)
    root = getattr(store, "root", None)
    if root is None:
        return None
    return Path(root) / _STATE_LOCK_FILE


def _registered_state_lock(path: Path) -> _ReentrantProcessFileLock:
    key = os.path.normcase(os.path.abspath(os.fspath(path)))
    with _STATE_LOCK_REGISTRY_GUARD:
        lock = _STATE_LOCK_REGISTRY.get(key)
        if lock is None:
            lock = _ReentrantProcessFileLock(path)
            _STATE_LOCK_REGISTRY[key] = lock
        return lock


@contextmanager
def state_transaction(ctx, timeout: float = _STATE_LOCK_TIMEOUT_SECONDS):
    """Serialize state read-modify-write work across threads and processes.

    The small lock file is a stable sentinel, not an ownership record. The OS
    owns the byte-range lock, so a crash releases it without stale-file cleanup.
    """

    path = _state_lock_path(ctx)
    lock = _registered_state_lock(path) if path is not None else _FALLBACK_STATE_LOCK
    wait_seconds = max(0.0, float(timeout))
    if not lock.acquire(timeout=wait_seconds):
        location = str(path) if path is not None else "in-memory state"
        raise TimeoutError(f"timed out waiting for state transaction: {location}")
    try:
        yield
    finally:
        lock.release()


def resolve_display_names(ctx, group_id: str, user_ids) -> dict[str, str]:
    """把 QQ 号换成群名片/昵称，用于排行榜展示。

    只调一次 get_group_member_list（比逐个 get_group_member_info 快且失败点少）。
    取不到就退回 QQ 号——排行榜不能因为取昵称失败而不可用。
    """
    wanted = {str(uid) for uid in (user_ids or [])}
    names: dict[str, str] = {}
    if not wanted:
        return names
    try:
        response = ctx.get_group_member_list(group_id)
        if not ctx.onebot_ok(response):
            return names
        data = ctx.onebot_data(response)
    except Exception:
        return names
    if not isinstance(data, (list, tuple)):
        return names
    for item in data:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("user_id") or item.get("uin") or "").strip()
        if not uid or uid not in wanted:
            continue
        label = ""
        for key in ("card", "nickname", "name", "remark"):
            value = str(item.get(key) or "").strip()
            if value:
                label = value
                break
        if label:
            names[uid] = label
    return names


def format_ranked_name(user_id: str, names: dict[str, str]) -> str:
    label = str(names.get(str(user_id)) or "").strip()
    return f"{label}({user_id})" if label else str(user_id)


class PointsService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def enabled(self, group_id: str) -> bool:
        value = self._settings().get(str(group_id), {}).get("checkin_enabled")
        if value is None:
            return bool(self.ctx.get_config("checkin_enabled", True))
        return bool(value)

    def set_enabled(self, group_id: str, enabled: bool) -> None:
        with state_transaction(self.ctx):
            settings = self._settings()
            settings.setdefault(str(group_id), {})["checkin_enabled"] = bool(enabled)
            self.ctx.set_state("settings", settings)

    def checkin_points(self, group_id: str) -> int:
        return self._group_number(group_id, "checkin_points", int(self.ctx.get_config("checkin_points", 1) or 1))

    def set_checkin_points(self, group_id: str, points: int) -> None:
        with state_transaction(self.ctx):
            settings = self._settings()
            settings.setdefault(str(group_id), {})["checkin_points"] = max(1, int(points))
            self.ctx.set_state("settings", settings)

    def checkin(self, group_id: str, user_id: str) -> CheckinResult:
        group_key = str(group_id or "").strip()
        user_key = str(user_id or "").strip()
        if not group_key or not user_key:
            return CheckinResult(False, "签到信息不完整。")
        with state_transaction(self.ctx):
            if not self.enabled(group_key):
                return CheckinResult(False, "本群签到已关闭。")
            day = self.today()
            key = f"{group_key}:{day}"
            checkins = self._checkins()
            users = {str(item) for item in checkins.get(key, [])}
            if user_key in users:
                return CheckinResult(True, f"今天已经签到过了，当前积分：{self.points(group_key, user_key)}。")
            users.add(user_key)
            checkins[key] = sorted(users)
            self.ctx.set_state("checkins", checkins)
            delta = self.checkin_points(group_key)
            total = self.add_points(group_key, user_key, delta)
            return CheckinResult(True, f"签到成功，积分 +{delta}，当前积分：{total}。")

    @staticmethod
    def today() -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def today_checkin_users(self, group_id: str) -> list[str]:
        return self.checkin_users(group_id, self.today())

    def checkin_users(self, group_id: str, day: str = "") -> list[str]:
        value = self._checkins().get(f"{group_id}:{str(day or self.today()).strip()}", [])
        if not isinstance(value, (list, tuple, set)):
            return []
        return sorted({str(item) for item in value if str(item).strip()})

    def clear_user_checkins(self, group_id: str, user_id: str, day: str = "") -> int:
        group_key = str(group_id or "").strip()
        user_key = str(user_id or "").strip()
        if not group_key or not user_key:
            return 0
        with state_transaction(self.ctx):
            checkins = self._checkins()
            removed = 0
            target_day = str(day or "").strip()
            for key in list(checkins):
                key_text = str(key)
                if not key_text.startswith(f"{group_key}:"):
                    continue
                if target_day and key_text != f"{group_key}:{target_day}":
                    continue
                users_value = checkins.get(key, [])
                if not isinstance(users_value, (list, tuple, set)):
                    continue
                users = {str(item) for item in users_value if str(item).strip()}
                if user_key not in users:
                    continue
                users.discard(user_key)
                removed += 1
                if users:
                    checkins[key] = sorted(users)
                else:
                    checkins.pop(key, None)
            if removed:
                self.ctx.set_state("checkins", checkins)
            return removed

    def clear_checkins(self, group_id: str, day: str = "") -> int:
        group_key = str(group_id or "").strip()
        if not group_key:
            return 0
        with state_transaction(self.ctx):
            checkins = self._checkins()
            target_day = str(day or "").strip()
            if target_day:
                users = checkins.pop(f"{group_key}:{target_day}", [])
                removed = len(users) if isinstance(users, (list, tuple, set)) else 0
            else:
                removed = 0
                for key in list(checkins):
                    if not str(key).startswith(f"{group_key}:"):
                        continue
                    users = checkins.pop(key, [])
                    removed += len(users) if isinstance(users, (list, tuple, set)) else 0
            if removed:
                self.ctx.set_state("checkins", checkins)
            return removed

    def points(self, group_id: str, user_id: str) -> int:
        groups = self._points()
        return int(groups.get(str(group_id), {}).get(str(user_id), 0))

    def group_points(self, group_id: str) -> dict[str, int]:
        return dict(self._points().get(str(group_id), {}))

    def point_group_ids(self) -> list[str]:
        return sorted(self._points())

    def set_points(self, group_id: str, user_id: str, value: int) -> int:
        with state_transaction(self.ctx):
            groups = self._points()
            group_points = groups.setdefault(str(group_id), {})
            total = int(value)
            group_points[str(user_id)] = total
            self._write_points(groups)
            return total

    def import_points(self, group_id: str, text: str) -> int:
        count = 0
        for line in str(text or "").splitlines():
            user_id, value = self.parse_points_line(line)
            if user_id and value is not None:
                self.set_points(group_id, user_id, value)
                count += 1
        return count

    def export_points(self, group_id: str, query: str = "") -> str:
        query_text = str(query or "").strip()
        rows = []
        for user_id, value in self.ranking(group_id, limit=0):
            if query_text and query_text not in user_id:
                continue
            rows.append(f"{user_id}={value}")
        return "\n".join(rows) if rows else "本群暂无积分记录。"

    def add_points(self, group_id: str, user_id: str, delta: int) -> int:
        with state_transaction(self.ctx):
            groups = self._points()
            group_points = groups.setdefault(str(group_id), {})
            total = int(group_points.get(str(user_id), 0)) + int(delta)
            group_points[str(user_id)] = total
            self._write_points(groups)
            return total

    def spend_points(self, group_id: str, user_id: str, amount: int) -> tuple[bool, int]:
        """扣积分，余额不足则整笔失败。返回 (是否成功, 当前积分)。

        add_points 传负数不会校验余额，会把积分扣成负数，所以消费一律走这里。
        """
        cost = int(amount)
        if cost <= 0:
            return False, self.points(group_id, user_id)
        with state_transaction(self.ctx):
            groups = self._points()
            group_points = groups.setdefault(str(group_id), {})
            current = int(group_points.get(str(user_id), 0))
            if current < cost:
                return False, current
            total = current - cost
            group_points[str(user_id)] = total
            self._write_points(groups)
            return True, total

    def delete_points(self, group_id: str, user_id: str) -> bool:
        with state_transaction(self.ctx):
            groups = self._points()
            group = groups.get(str(group_id), {})
            if str(user_id) not in group:
                return False
            del group[str(user_id)]
            if group:
                groups[str(group_id)] = group
            else:
                groups.pop(str(group_id), None)
            self._write_points(groups)
            return True

    def delete_points_many(self, group_id: str, user_ids: str | list[str] | tuple[str, ...] | set[str]) -> int:
        if isinstance(user_ids, str):
            ids = re.findall(r"\d{5,}", user_ids)
        elif isinstance(user_ids, (list, tuple, set)):
            ids = [str(item).strip() for item in user_ids]
        else:
            ids = []
        removed = 0
        for user_id in ids:
            if self.delete_points(group_id, user_id):
                removed += 1
        return removed

    def clear_group_points(self, group_id: str) -> int:
        with state_transaction(self.ctx):
            groups = self._points()
            group = groups.pop(str(group_id), {})
            removed = len(group) if isinstance(group, dict) else 0
            self._write_points(groups)
            return removed

    def ranking(self, group_id: str, limit: int = 10) -> list[tuple[str, int]]:
        group_points = self._points().get(str(group_id), {})
        items = [(str(user_id), int(points)) for user_id, points in group_points.items()]
        ranked = sorted(items, key=lambda item: item[1], reverse=True)
        return ranked[:limit] if int(limit or 0) > 0 else ranked

    def parse_points_line(self, text: str) -> tuple[str, int | None]:
        raw = str(text or "").strip()
        if not raw:
            return "", None
        raw = raw.replace("，", ",").replace("：", ":").replace("＝", "=")
        match = re.search(r"(\d{5,})\s*(?:=|,|:|\s)\s*(-?\d+)", raw)
        if not match:
            return "", None
        return match.group(1), int(match.group(2))

    def _settings(self) -> dict[str, dict[str, Any]]:
        value = self.ctx.get_state("settings", {})
        return value if isinstance(value, dict) else {}

    def _group_number(self, group_id: str, key: str, default: int) -> int:
        try:
            value = self._settings().get(str(group_id), {}).get(key, default)
            return max(1, int(value))
        except (TypeError, ValueError):
            return max(1, int(default))

    def _checkins(self) -> dict[str, list[str]]:
        value = self.ctx.get_state("checkins", {})
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_ledger(value: object) -> dict[str, dict[str, int]]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, dict[str, int]] = {}
        for group_id, users in value.items():
            if not isinstance(users, dict):
                continue
            bucket: dict[str, int] = {}
            for user_id, points in users.items():
                try:
                    bucket[str(user_id)] = int(points)
                except (TypeError, ValueError):
                    continue
            result[str(group_id)] = bucket
        return result

    def _points(self) -> dict[str, dict[str, int]]:
        with state_transaction(self.ctx):
            store = getattr(self.ctx, "state_store", None)
            if store is None:
                return self._normalize_ledger(self.ctx.get_state(POINTS_STATE_KEY, {}))
            self._migrate_legacy_points(store)
            return self._normalize_ledger(store.get(POINTS_NAMESPACE, POINTS_STATE_KEY, {}))

    def _write_points(self, groups: dict[str, dict[str, int]]) -> None:
        with state_transaction(self.ctx):
            store = getattr(self.ctx, "state_store", None)
            if store is None:
                self.ctx.set_state(POINTS_STATE_KEY, groups)
                return
            namespace_state = store.load(POINTS_NAMESPACE)
            if not isinstance(namespace_state, dict):
                namespace_state = {}
            namespace_state[POINTS_STATE_KEY] = groups
            store.save(POINTS_NAMESPACE, namespace_state)
            try:
                self.ctx.state_revision += 1
            except (AttributeError, TypeError):
                pass

    def _migrate_legacy_points(self, store) -> None:
        """把历史上分散在各插件命名空间里的积分合并进共享账本（只做一次）。

        同一玩家可能在多个历史插件下各有余额，
        所以按玩家求和而不是覆盖，避免把已有积分抹掉。
        """
        with state_transaction(self.ctx):
            try:
                namespace_state = store.load(POINTS_NAMESPACE)
            except Exception:
                return
            if not isinstance(namespace_state, dict):
                namespace_state = {}
            if bool(namespace_state.get(_POINTS_MIGRATED_KEY, False)):
                return
            merged = self._normalize_ledger(namespace_state.get(POINTS_STATE_KEY, {}))
            sources = list(_LEGACY_POINTS_NAMESPACES)
            current = str(getattr(self.ctx, "plugin_id", "") or "")
            if current and current not in sources:
                sources.append(current)
            for namespace in sources:
                if namespace == POINTS_NAMESPACE:
                    continue
                try:
                    legacy = self._normalize_ledger(store.get(namespace, POINTS_STATE_KEY, {}))
                except Exception:
                    raise
                for group_id, users in legacy.items():
                    bucket = merged.setdefault(group_id, {})
                    for user_id, value in users.items():
                        bucket[user_id] = int(bucket.get(user_id, 0)) + int(value)
            namespace_state[POINTS_STATE_KEY] = merged
            namespace_state[_POINTS_MIGRATED_KEY] = True
            try:
                # 账本和迁移标记属于同一个 namespace 文件，必须一次原子写入。
                store.save(POINTS_NAMESPACE, namespace_state)
            except Exception:
                # atomic_write_json 可能已提交后才抛错。仅在磁盘上的完整事务
                # 已带迁移标记时接受，否则向上抛出，避免静默丢积分。
                committed = store.load(POINTS_NAMESPACE)
                if not isinstance(committed, dict) or committed.get(_POINTS_MIGRATED_KEY) is not True:
                    raise
