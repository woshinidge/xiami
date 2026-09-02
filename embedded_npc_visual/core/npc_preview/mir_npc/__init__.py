"""Mir NPC 脚本轻量模拟：引擎配置与运行时。"""

from .envir_loader import envir_file_loader, parse_skip_goto_labels
from .interpreter import InterpreterOptions, InterpreterResult, NpcScriptInterpreter
from .profile import Engine, EngineProfile, get_profile
from .runtime import NpcLightRuntime, NpcRuntimeState
from .script_model import ActKind, CallStmt, MethodBlock, NpcScript, ScriptSection
from .script_parser import parse_npc_script
from .script_render import default_file_loader, resolve_call_graph, script_to_dialog_pages
from .script_simulate import PreviewBundle, SimulateOptions, simulate_preview
from .script_workspace import MethodRef, ScriptWorkspace

__all__ = [
    "ActKind",
    "CallStmt",
    "Engine",
    "EngineProfile",
    "InterpreterOptions",
    "InterpreterResult",
    "MethodBlock",
    "MethodRef",
    "NpcLightRuntime",
    "NpcRuntimeState",
    "NpcScript",
    "NpcScriptInterpreter",
    "PreviewBundle",
    "ScriptSection",
    "ScriptWorkspace",
    "SimulateOptions",
    "default_file_loader",
    "envir_file_loader",
    "get_profile",
    "parse_npc_script",
    "parse_skip_goto_labels",
    "resolve_call_graph",
    "script_to_dialog_pages",
    "simulate_preview",
]
