from __future__ import annotations

from pathlib import Path


def _fallback_table() -> "list[tuple[int, int, int, int]]":
    colors = [(255, 255, 255, 255) for _ in range(256)]
    colors[0] = (0, 0, 0, 255)
    colors[31] = (132, 0, 132, 255)
    colors[32] = (255, 0, 0, 255)
    colors[69] = (239, 105, 0, 255)
    colors[70] = (239, 199, 140, 255)
    colors[96] = (107, 105, 90, 255)
    colors[100] = (206, 190, 123, 255)
    colors[131] = (198, 166, 41, 255)
    colors[151] = (247, 231, 0, 255)
    colors[249] = (255, 0, 0, 255)
    colors[250] = (0, 255, 0, 255)
    colors[251] = (255, 255, 0, 255)
    colors[252] = (0, 0, 255, 255)
    colors[253] = (255, 0, 255, 255)
    colors[254] = (0, 255, 255, 255)
    colors[255] = (255, 255, 255, 255)
    return colors


def _candidate_paths() -> "list[Path]":
    here = Path(__file__).resolve()
    return [
        here.with_name("npc_color_table.csv"),
        here.parents[1] / "npc_preview" / "npc_color_table.csv",
    ]


def load_npc_color_table() -> "tuple[tuple[int, int, int, int], ...]":
    colors = _fallback_table()
    for path in _candidate_paths():
        if not path.is_file():
            continue
        try:
            for raw_line in path.read_text(encoding="utf-8-sig").splitlines()[1:]:
                parts = [part.strip() for part in raw_line.split(",")]
                if len(parts) < 5:
                    continue
                index = int(parts[0])
                r = int(parts[2])
                g = int(parts[3])
                b = int(parts[4])
                if 0 <= index < 256:
                    colors[index] = (r, g, b, 255)
            break
        except (OSError, ValueError):
            continue
    return tuple(colors)


NPC_COLOR_TABLE = load_npc_color_table()
