from __future__ import annotations

from pathlib import Path
import tempfile
import time

from xiami_core.models import SendResult
from xiami_core.plugins.context import PluginContext
from xiami_core.plugins.kv import PluginKVStore
from xiami_core.plugins.loader import PluginLoader
from xiami_core.plugins.quiz import QuizService
from xiami_core.plugins.state import PluginStateStore


def main() -> int:
    def send(_target: str, _text: str, _message_type: str) -> SendResult:
        return SendResult(ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = Path.cwd() / "xiami_plugins" / "quiz"
        plugin_root = root / "plugins"
        plugin_dir = plugin_root / "quiz"
        plugin_dir.mkdir(parents=True)
        (plugin_dir / "plugin.py").write_text((source / "plugin.py").read_text(encoding="utf-8"), encoding="utf-8")
        (plugin_dir / "plugin_config.json").write_text(
            '{"quiz_reward_points":3,"quiz_interval_seconds":0,"quiz_answer_timeout_seconds":0}',
            encoding="utf-8",
        )
        ctx = PluginContext(send_fn=send, state_store=PluginKVStore(root / "state"))
        loader = PluginLoader(plugin_root, ctx, state_store=PluginStateStore(root / "enabled.json"))
        plugins = loader.load_all()
        if not plugins or plugins[0].error or plugins[0].context is None:
            raise RuntimeError(f"quiz plugin load failed: {plugins}")

        service = QuizService(plugins[0].context)
        service.set_enabled("20001", True)
        service.set_reward_points("20001", 9)
        service.set_interval_seconds("20001", 30)
        service.set_answer_timeout_seconds("20001", 1)
        imported = service.import_questions("20001", "常识:Q1=A1\nQ2＝A2\n停用:Q3=A3\n活动|Q4|A4|备注")
        if imported != 4:
            raise RuntimeError(f"wrong imported count: {imported}")
        if service.reward_points("20001") != 9 or service.interval_seconds("20001") != 30:
            raise RuntimeError("quiz settings not saved")
        if service.question_count("20001") != 4 or service.question_count("20001", enabled_only=True) != 3:
            raise RuntimeError("quiz question enabled count wrong")
        updated = service.update_question("20001", "1", "Q1+", "A1+", category="常识", note="已修改")
        if updated is None or updated.question != "Q1+" or updated.note != "已修改":
            raise RuntimeError(f"quiz update failed: {updated}")
        changed = service.set_question_enabled("20001", "3", True)
        if changed != 1 or service.question_count("20001", enabled_only=True) != 4:
            raise RuntimeError("quiz enable failed")
        exported = service.export_questions("20001", "常识")
        if "常识|Q1+|A1+|已修改" not in exported:
            raise RuntimeError(f"quiz export failed: {exported}")

        result = service.start("20001")
        if not result.handled or "题目：" not in result.message:
            raise RuntimeError(f"quiz did not start: {result}")
        blocked = service.start("20001")
        if "出题间隔未到" not in blocked.message:
            raise RuntimeError(f"quiz interval not enforced: {blocked}")
        sessions = plugins[0].context.get_state("quiz_sessions", {})
        sessions["20001"]["started_at"] = time.time() - 2
        plugins[0].context.set_state("quiz_sessions", sessions)
        timeout = service.answer("20001", "10001", str(sessions["20001"]["answer"]))
        if "超时" not in timeout.message:
            raise RuntimeError(f"quiz timeout not enforced: {timeout}")
        service.set_interval_seconds("20001", 0)
        service.start("20001")
        if service.cancel_current("20001") != 1 or service.current_session("20001"):
            raise RuntimeError("quiz cancel failed")
        removed = service.delete_questions("20001", "1 2")
        if removed != 2:
            raise RuntimeError(f"quiz batch delete failed: {removed}")

    print("quiz admin settings smoke ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
