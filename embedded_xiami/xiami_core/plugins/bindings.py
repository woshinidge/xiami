from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

from xiami_core.plugins.context import PluginContext


ACCOUNT_RE = re.compile(r"^[\w\u4e00-\u9fff.-]{2,32}$")
BINDING_SCOPE_SEPARATOR = "::"


@dataclass(frozen=True)
class BindingResult:
    ok: bool
    message: str


class BindingService:
    def __init__(self, ctx: PluginContext) -> None:
        self.ctx = ctx

    def storage_dir(self) -> str:
        value = self.ctx.get_config("binding_root", "")
        return str(value).strip()

    def storage_file(self) -> Path | None:
        root = self.storage_dir()
        if not root:
            return None
        return Path(root).expanduser() / "bindings.json"

    def set_storage_dir(self, directory: str) -> BindingResult:
        target = Path(directory).expanduser()
        if not str(directory).strip():
            return BindingResult(False, "绑定目录不能为空。")
        try:
            target.mkdir(parents=True, exist_ok=True)
            if not target.is_dir():
                return BindingResult(False, "绑定目录不是有效文件夹。")
            self.ctx.config["binding_root"] = str(target)
            if not self.storage_file().exists():
                self._write_external_bindings(self._bindings_from_state())
        except OSError as exc:
            return BindingResult(False, f"绑定目录不可用：{exc}")
        return BindingResult(True, f"绑定目录已设置：{target}")

    def bind(self, group_id: str, user_id: str, account: str) -> BindingResult:
        account = account.strip()
        if not ACCOUNT_RE.match(account):
            return BindingResult(False, "账号格式不正确，长度 2-32，可包含中文、字母、数字、点、横线、下划线。")
        data = self._bindings()
        scope = str(group_id).strip()
        if BINDING_SCOPE_SEPARATOR in scope and not self.group_exists(scope):
            return BindingResult(False, "区服未创建，请先在账号绑定后台创建区服后再绑定。")
        group = data.setdefault(scope, {})
        # Account is unique within a group.
        for existing_user, existing_account in list(group.items()):
            if existing_account == account and existing_user != str(user_id):
                del group[existing_user]
        group[str(user_id)] = account
        self._save_bindings(data)
        return BindingResult(True, f"绑定成功：{account}")

    def unbind(self, group_id: str, user_id: str) -> BindingResult:
        data = self._bindings()
        group = data.setdefault(str(group_id), {})
        if str(user_id) in group:
            del group[str(user_id)]
            self._save_bindings(data)
            return BindingResult(True, "解绑成功。")
        return BindingResult(True, "当前没有绑定账号。")

    def query(self, group_id: str, user_id: str) -> BindingResult:
        account = self.account_for_user(group_id, user_id)
        if not account:
            return BindingResult(True, "当前没有绑定账号。")
        return BindingResult(True, f"当前绑定账号：{account}")

    def account_for_user(self, group_id: str, user_id: str) -> str:
        return str(self._bindings().get(str(group_id), {}).get(str(user_id), ""))

    def user_for_account(self, group_id: str, account: str) -> str:
        for user_id, bound_account in self.list_group(group_id).items():
            if bound_account == account:
                return user_id
        return ""

    def list_group(self, group_id: str) -> dict[str, str]:
        group = self._bindings().get(str(group_id), {})
        return dict(group) if isinstance(group, dict) else {}

    def server_list(self, group_id: str = "") -> list[dict[str, str]]:
        group_key = str(group_id or "").strip()
        labels = self.group_labels()
        rows: list[dict[str, str]] = []
        for scope, label in sorted(labels.items(), key=lambda item: self._sort_scope_key(item[0], item[1])):
            scope_text = str(scope or "").strip()
            if not scope_text:
                continue
            current_group, server_name = self._scope_parts(scope_text)
            if group_key and current_group != group_key:
                continue
            rows.append(
                {
                    "scope": scope_text,
                    "group_id": current_group,
                    "server_name": server_name or str(label or "").strip() or scope_text,
                    "label": str(label or "").strip(),
                }
            )
        return rows

    def records(self, group_id: str = "", query: str = "") -> list[dict[str, str]]:
        group_key = str(group_id or "").strip()
        needle = str(query or "").strip().lower()
        labels = self.group_labels()
        data = self._bindings()
        rows: list[dict[str, str]] = []
        scopes = set(str(key) for key in data)
        scopes.update(str(key) for key in labels if str(key).strip())
        for scope in sorted(scopes, key=lambda value: self._sort_scope_key(value, labels.get(value, ""))):
            current_group, server_name = self._scope_parts(scope)
            if group_key and current_group != group_key:
                continue
            label = str(labels.get(scope, "") or "").strip()
            display_server = server_name or label
            group = data.get(scope, {})
            if not isinstance(group, dict) or not group:
                row = {
                    "scope": scope,
                    "group_id": current_group,
                    "server_name": display_server,
                    "user_id": "",
                    "account": "",
                }
                if self._record_matches(row, needle):
                    rows.append(row)
                continue
            for user_id, account in sorted(group.items(), key=lambda item: (str(item[0]), str(item[1]))):
                row = {
                    "scope": scope,
                    "group_id": current_group,
                    "server_name": display_server,
                    "user_id": str(user_id),
                    "account": str(account),
                }
                if self._record_matches(row, needle):
                    rows.append(row)
        return rows

    def export_records(self, group_id: str = "", query: str = "") -> str:
        group_key = str(group_id or "").strip()
        lines: list[str] = []
        for row in self.records(group_key, query):
            user_id = str(row.get("user_id") or "").strip()
            account = str(row.get("account") or "").strip()
            if not user_id or not account:
                continue
            server_name = str(row.get("server_name") or "").strip()
            if group_key:
                lines.append(f"{server_name}|{user_id}|{account}")
            else:
                lines.append(f"{row.get('group_id', '')}|{server_name}|{user_id}|{account}")
        return "\n".join(lines)

    def import_records(self, group_id: str, text: str) -> BindingResult:
        default_group = str(group_id or "").strip()
        imported = 0
        failed: list[str] = []
        for line_no, raw_line in enumerate(str(text or "").splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            lower = line.replace(" ", "").lower()
            if lower in {"区服|qq|账号", "qq群|区服|qq|账号", "区服qq账号", "qq群区服qq账号"}:
                continue
            parsed = self._parse_import_line(line, default_group)
            if parsed is None:
                failed.append(f"第 {line_no} 行格式不正确")
                continue
            current_group, server_name, user_id, account = parsed
            if not re.fullmatch(r"\d{5,}", current_group):
                failed.append(f"第 {line_no} 行QQ群号不正确")
                continue
            if not re.fullmatch(r"[\w\u4e00-\u9fff-]{1,32}", server_name):
                failed.append(f"第 {line_no} 行区服名不正确")
                continue
            if not re.fullmatch(r"\d{5,}", user_id):
                failed.append(f"第 {line_no} 行QQ号不正确")
                continue
            scope = self._binding_scope(current_group, server_name)
            if not self.group_exists(scope):
                failed.append(f"第 {line_no} 行区服未创建：{current_group}/{server_name}")
                continue
            result = self.bind(scope, user_id, account)
            if result.ok:
                imported += 1
            else:
                failed.append(f"第 {line_no} 行{result.message}")
        if imported <= 0 and failed:
            return BindingResult(False, "导入失败：" + "；".join(failed[:5]))
        if failed:
            return BindingResult(False, f"已导入 {imported} 条，失败 {len(failed)} 条：" + "；".join(failed[:5]))
        return BindingResult(True, f"已导入绑定记录：{imported} 条。")

    def delete_binding(self, scope: str, user_id: str) -> BindingResult:
        return self.unbind(str(scope or "").strip(), str(user_id or "").strip())

    def groups(self) -> dict[str, dict[str, str]]:
        return self._bindings()

    def group_labels(self) -> dict[str, str]:
        value = self.ctx.get_state("binding_group_labels", {})
        if not isinstance(value, dict):
            return {}
        return {str(group_id): str(label) for group_id, label in value.items() if str(label).strip()}

    def group_label(self, group_id: str) -> str:
        return self.group_labels().get(str(group_id), "")

    def group_exists(self, group_id: str) -> bool:
        key = str(group_id).strip()
        if not key:
            return False
        # 区服是否可绑定只能以“账号绑定后台 -> 创建区服”产生的
        # binding_group_labels 为准；历史 bindings.json 里残留的绑定记录
        # 不能反向视为已创建区服，否则用户未创建区服仍可继续新增绑定。
        return key in self.group_labels()

    def set_group_label(self, group_id: str, label: str) -> BindingResult:
        group_id = str(group_id).strip()
        label = str(label).strip()
        if not group_id:
            return BindingResult(False, "区服/群号不能为空。")
        labels = self.group_labels()
        if label:
            labels[group_id] = label
        else:
            labels.pop(group_id, None)
        self.ctx.set_state("binding_group_labels", labels)
        return BindingResult(True, f"区服名称已保存：{label or group_id}")

    def delete_group(self, group_id: str, *, remove_bindings: bool = True) -> BindingResult:
        group_id = str(group_id).strip()
        if not group_id:
            return BindingResult(False, "区服/群号不能为空。")
        labels = self.group_labels()
        existed_label = group_id in labels
        labels.pop(group_id, None)
        self.ctx.set_state("binding_group_labels", labels)

        removed_count = 0
        data = self._bindings()
        if remove_bindings and group_id in data:
            group = data.pop(group_id, {})
            removed_count = len(group) if isinstance(group, dict) else 0
            self._save_bindings(data)

        if not existed_label and removed_count <= 0:
            return BindingResult(False, "区服不存在或没有可删除的绑定。")
        if removed_count > 0:
            return BindingResult(True, f"区服已删除，并清理绑定：{removed_count} 个。")
        return BindingResult(True, "区服已删除。")

    def replace_group(self, group_id: str, values: dict[str, str]) -> None:
        data = self._bindings()
        data[str(group_id)] = {str(user): str(account) for user, account in values.items()}
        self._save_bindings(data)

    @staticmethod
    def _binding_scope(group_id: str, server_name: str) -> str:
        return f"{str(group_id).strip()}{BINDING_SCOPE_SEPARATOR}{str(server_name).strip()}"

    @staticmethod
    def _scope_parts(scope: str) -> tuple[str, str]:
        text = str(scope or "").strip()
        if BINDING_SCOPE_SEPARATOR in text:
            group_id, server_name = text.split(BINDING_SCOPE_SEPARATOR, 1)
            return group_id.strip(), server_name.strip()
        return text, ""

    @classmethod
    def _sort_scope_key(cls, scope: str, label: str = "") -> tuple[str, str, str]:
        group_id, server_name = cls._scope_parts(scope)
        return (group_id, server_name or str(label or ""), str(scope or ""))

    @staticmethod
    def _record_matches(row: dict[str, str], needle: str) -> bool:
        if not needle:
            return True
        haystack = " ".join(str(value or "").lower() for value in row.values())
        return needle in haystack

    @staticmethod
    def _parse_import_line(line: str, default_group: str) -> tuple[str, str, str, str] | None:
        if "|" in line:
            parts = [part.strip() for part in line.split("|")]
        else:
            parts = [part.strip() for part in re.split(r"\s+", line) if part.strip()]
        if len(parts) == 3 and default_group:
            server_name, user_id, account = parts
            return default_group, server_name, user_id, account
        if len(parts) >= 4:
            group_id, server_name, user_id = parts[:3]
            account = " ".join(parts[3:]).strip() if "|" not in line else "|".join(parts[3:]).strip()
            return group_id, server_name, user_id, account
        return None

    def _bindings(self) -> dict[str, dict[str, str]]:
        external = self._read_external_bindings()
        if external is not None:
            self.ctx.set_state("bindings", external)
            return external
        return self._bindings_from_state()

    def _save_bindings(self, data: dict[str, dict[str, str]]) -> None:
        self.ctx.set_state("bindings", data)
        self._write_external_bindings(data)

    def _bindings_from_state(self) -> dict[str, dict[str, str]]:
        value = self.ctx.get_state("bindings", {})
        return self._normalize_bindings(value)

    def _read_external_bindings(self) -> dict[str, dict[str, str]] | None:
        path = self.storage_file()
        if path is None or not path.exists():
            return None
        try:
            return self._normalize_bindings(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            return None

    def _write_external_bindings(self, data: dict[str, dict[str, str]]) -> None:
        path = self.storage_file()
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _normalize_bindings(value: Any) -> dict[str, dict[str, str]]:
        if not isinstance(value, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for group_id, group in value.items():
            if not isinstance(group, dict):
                continue
            result[str(group_id)] = {str(user): str(account) for user, account in group.items()}
        return result
