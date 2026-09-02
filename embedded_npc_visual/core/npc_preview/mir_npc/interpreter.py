from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..npc_dialog_core import (
    MerchantBigDlg,
    NpcDialog,
    parse_mov_assignments,
    parse_npc_dialog,
    parse_openmerchantbigdlg,
)
from .envir_loader import envir_file_loader
from .script_simulate import PreviewBundle, SimulateOptions, simulate_preview
from .script_workspace import ScriptWorkspace


def normalize_label(label: str) -> str:
    label = label.strip()
    if not label:
        return "@main"
    if label.startswith("@"):
        return label
    return f"@{label}"


@dataclass
class InterpreterOptions:
    entry_label: str = "@main"
    entry_path: str | None = None
    envir_root: Path | None = None
    skip_goto_labels: frozenset[str] = frozenset()
    follow_call: bool = True
    mock_variables: dict[str, str] = field(default_factory=dict)
    max_goto_hops: int = 48
    merge_adjacent_text: bool = True
    monster_field_loader: Callable[[str, str, str | None], str | None] | None = None

    def to_simulate_options(
        self,
        entry_label: str,
        *,
        say_page_index: int = 1,
        call_loader: Callable[[str], str | None] | None = None,
        on_call_loaded: Callable[[str], None] | None = None,
    ) -> SimulateOptions:
        return SimulateOptions(
            entry_label=normalize_label(entry_label),
            entry_path=self.entry_path,
            skip_goto_labels=self.skip_goto_labels,
            follow_call=self.follow_call,
            mock_variables=dict(self.mock_variables),
            max_goto_hops=self.max_goto_hops,
            call_loader=call_loader,
            on_call_loaded=on_call_loaded,
            say_page_index=say_page_index,
            merge_adjacent_text=self.merge_adjacent_text,
            monster_field_loader=self.monster_field_loader,
        )


@dataclass
class InterpreterResult:
    dialog: NpcDialog
    labels: list[str]
    trace: list[str]
    variables: dict[str, str] = field(default_factory=dict)
    loaded_calls: list[str] = field(default_factory=list)
    bundle: PreviewBundle | None = None


class NpcScriptInterpreter:
    """
    Lightweight NPC script interpreter for preview use.

    It keeps source files separate, follows GOTO/#CALL in memory, applies mov
    variables, and returns a renderable NpcDialog snapshot.
    """

    def __init__(self, source: str = "", *, options: InterpreterOptions | None = None) -> None:
        self.options = options or InterpreterOptions()
        self.source = ""
        self.current_label = normalize_label(self.options.entry_label)
        self.workspace = ScriptWorkspace.from_editor("")
        self.loaded_calls: list[str] = []
        self._call_loader: Callable[[str], str | None] | None = None
        self.command_log: list[str] = []
        self.input_values: dict[int, str] = {}
        self._renderable_label_cache: list[str] | None = None
        self._entry_context_bundle: PreviewBundle | None = None
        if source:
            self.load(source)

    def load(
        self,
        source: str,
        *,
        envir_root: str | Path | None = None,
        entry_label: str | None = None,
        call_loader: Callable[[str], str | None] | None = None,
    ) -> None:
        self.source = source
        self.workspace = ScriptWorkspace.from_editor(source)
        self.loaded_calls = []
        self._call_loader = None
        self._renderable_label_cache = None
        self._entry_context_bundle = None

        if entry_label is not None:
            self.current_label = normalize_label(entry_label)

        root = Path(envir_root) if envir_root is not None else self.options.envir_root
        if self.options.follow_call:
            if call_loader is not None:
                self._call_loader = call_loader
            elif root is not None and root.is_dir():
                self._call_loader = envir_file_loader(root)

    def _record_loaded_call(self, file_path: str) -> None:
        if file_path not in self.loaded_calls:
            self.loaded_calls.append(file_path)

    def labels(self) -> list[str]:
        return self._renderable_labels()

    @staticmethod
    def _dialog_is_renderable(dialog: NpcDialog) -> bool:
        return bool(getattr(dialog, "nodes", None)) or getattr(dialog, "merchant_bigdlg", None) is not None

    def _renderable_labels(self) -> list[str]:
        if self._renderable_label_cache is not None:
            return list(self._renderable_label_cache)

        labels: list[str] = []
        seen: set[str] = set()

        def add_label(label: str) -> None:
            if label not in seen:
                seen.add(label)
                labels.append(label)

        entry_label = normalize_label(self.options.entry_label)
        try:
            bundle = simulate_preview(
                self.workspace,
                self.options.to_simulate_options(
                    entry_label,
                    call_loader=self._call_loader,
                    on_call_loaded=self._record_loaded_call,
                ),
            )
        except BaseException:
            bundle = None

        if bundle is not None:
            if self._dialog_is_renderable(bundle.to_dialog()):
                add_label(entry_label)
            if bundle.final_label:
                add_label(bundle.final_label)

        for label in self._static_renderable_labels():
            add_label(label)

        self._renderable_label_cache = labels
        return list(labels)

    def _static_renderable_labels(self) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()

        def add_label(label: str) -> None:
            if label in seen:
                suffix = 2
                while f"{label}{suffix}" in seen:
                    suffix += 1
                label = f"{label}{suffix}"
            seen.add(label)
            labels.append(label)

        for script in self.workspace.scripts.values():
            for method in script.methods:
                for block in method.iter_methods_depth_first():
                    say_count = sum(1 for section in block.sections if section.has_say)
                    if not say_count and block.preamble_text().strip():
                        say_count = 1
                    for page_index in range(1, say_count + 1):
                        add_label(block.label if page_index == 1 else f"{block.label}{page_index}")
        return labels

    def _virtual_label_map(self) -> dict[str, tuple[str, int]]:
        labels: dict[str, tuple[str, int]] = {}
        seen: set[str] = set()

        def add_label(label: str, base_label: str, page_index: int) -> None:
            if label in seen:
                suffix = 2
                while f"{label}{suffix}" in seen:
                    suffix += 1
                label = f"{label}{suffix}"
            seen.add(label)
            labels[label] = (base_label, page_index)

        for script in self.workspace.scripts.values():
            for method in script.methods:
                for block in method.iter_methods_depth_first():
                    say_count = sum(1 for section in block.sections if section.has_say)
                    if not say_count and block.preamble_text().strip():
                        say_count = 1
                    for page_index in range(1, say_count + 1):
                        label = block.label if page_index == 1 else f"{block.label}{page_index}"
                        add_label(label, block.label, page_index)

        return labels

    def _all_labels(self) -> list[str]:
        labels: list[str] = []
        seen: set[str] = set()
        for script in self.workspace.scripts.values():
            for method in script.methods:
                for block in method.iter_methods_depth_first():
                    if block.label not in seen:
                        seen.add(block.label)
                        labels.append(block.label)
        return labels

    def _first_merchant_bigdlg(self) -> MerchantBigDlg | None:
        for script in self.workspace.scripts.values():
            for method in script.methods:
                for block in method.iter_methods_depth_first():
                    for section in block.sections:
                        for stmt in section.act:
                            if stmt.raw.strip() and stmt.kind.value == "openmerchant":
                                merchant = parse_openmerchantbigdlg([stmt.raw])
                                if merchant is not None:
                                    return merchant
        return None

    def _entry_context_preview(self) -> PreviewBundle | None:
        if self._entry_context_bundle is not None:
            return self._entry_context_bundle
        try:
            self._entry_context_bundle = simulate_preview(
                self.workspace,
                self.options.to_simulate_options(
                    normalize_label(self.options.entry_label),
                    call_loader=self._call_loader,
                    on_call_loaded=self._record_loaded_call,
                ),
            )
        except BaseException:
            self._entry_context_bundle = None
        return self._entry_context_bundle

    def _global_mov_values(self) -> dict[str, str]:
        values: dict[str, str] = {}
        for script in self.workspace.scripts.values():
            for name, value in parse_mov_assignments(script.source).items():
                values.setdefault(name, value)
        return values

    def render(self, entry_label: str | None = None) -> InterpreterResult:
        if entry_label is not None:
            self.current_label = normalize_label(entry_label)

        all_labels = self._all_labels()
        virtual_labels = self._virtual_label_map()
        labels = self._renderable_labels()

        if not all_labels:
            dialog = parse_npc_dialog(self.source)
            labels = [dialog.label] if self._dialog_is_renderable(dialog) else []
            return InterpreterResult(
                dialog=dialog,
                labels=labels,
                trace=["classic parse: no [@label] methods found"],
                loaded_calls=list(self.loaded_calls),
            )

        requested_label = self.current_label
        if labels and requested_label not in labels:
            requested_label = labels[0]
            self.current_label = requested_label

        base_label = requested_label
        say_page_index = 1
        if requested_label in virtual_labels:
            base_label, say_page_index = virtual_labels[requested_label]
        elif requested_label not in all_labels:
            requested_label = labels[0] if labels else all_labels[0]
            base_label, say_page_index = virtual_labels.get(requested_label, (requested_label, 1))
            self.current_label = requested_label

        bundle: PreviewBundle | None = None
        configured_entry_label = normalize_label(self.options.entry_label)
        if say_page_index == 1 and normalize_label(base_label).casefold() != configured_entry_label.casefold():
            entry_bundle = self._entry_context_preview()
            if entry_bundle is not None and normalize_label(entry_bundle.final_label).casefold() == normalize_label(base_label).casefold():
                bundle = entry_bundle

        if bundle is None:
            try:
                bundle = simulate_preview(
                    self.workspace,
                    self.options.to_simulate_options(
                        base_label,
                        say_page_index=say_page_index,
                        call_loader=self._call_loader,
                        on_call_loaded=self._record_loaded_call,
                    ),
                )
            except KeyError as exc:
                dialog = parse_npc_dialog("")
                return InterpreterResult(dialog=dialog, labels=labels, trace=[str(exc)], loaded_calls=list(self.loaded_calls))

        dialog = bundle.to_dialog(global_mov=self._global_mov_values())
        if dialog.merchant_bigdlg is None:
            dialog.merchant_bigdlg = self._first_merchant_bigdlg()
        dialog.label = requested_label if requested_label in virtual_labels else bundle.final_label

        labels = self._renderable_labels()
        return InterpreterResult(
            dialog=dialog,
            labels=labels,
            trace=list(bundle.trace),
            variables=dict(bundle.variables),
            loaded_calls=list(self.loaded_calls),
            bundle=bundle,
        )

    def run_command(self, command: str, *, input_value: str = "") -> InterpreterResult | None:
        command = command.strip()
        if not command:
            return None

        line = command
        if input_value:
            line += f" = {input_value}"
        self.command_log.append(line)

        if command.lower().startswith("@@inputstring"):
            suffix = ""
            for ch in reversed(command):
                if ch.isdigit():
                    suffix = ch + suffix
                else:
                    break
            if suffix:
                if input_value:
                    self.input_values[int(suffix)] = input_value
                return self.render()

        if command.startswith("@"):
            self.current_label = normalize_label(command)
            return self.render()

        return None
