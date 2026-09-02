from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MonsterFrameSequence:
    race_img: int
    file_index: int
    frames: tuple[int, ...]
    interval_ms: int


_OFFSET_TABLES: dict[int, tuple[int, ...]] = {
    13: (0, 360, 440, 550),
    17: (0, 350, 920),
    18: (0, 520, 950),
    19: (0, 370, 810, 1250, 1630, 2010, 2390),
    20: (0, 360, 720, 1080, 1440, 1800, 2350, 3060),
    21: (0, 460, 820, 1180, 1540, 1900, 2440, 2570, 2700),
    22: (0, 430, 1290, 1810, 2320, 2920, 3270, 3620),
    23: (0, 340, 680, 1180, 1770, 2610, 2950, 3290, 3750, 4460),
    24: (0, 510, 1090),
    25: (0, 510, 1020, 1370, 1720, 2070, 2740, 3780, 3820, 4170),
    26: (0, 340, 680, 1190, 1930, 2100, 2440, 2540, 3570),
    32: (0, 440, 820, 1360, 2650, 2680, 2790, 2900, 3500, 3930),
    33: (20, 720, 1160, 1770, 1780, 1790, 1840, 2540, 2900),
    35: (0, 810, 1800, 2610, 3420, 4390, 5200, 6170, 6980, 7790),
    70: (0, 360, 720, 0, 350, 780, 1130, 1560, 1910),
    80: (0, 80, 300, 301, 302, 320, 321, 322, 321),
    81: (8760, 9570, 10380, 11030, 12000, 13800, 14770, 15580, 16390, 17360),
    82: (18330, 19300, 20270, 21240, 22050, 22860, 23990, 24800, 25930),
    90: (80, 168, 184, 200, 1770, 1780, 1790),
}


def monster_appearance_offset(appr: int) -> int:
    appr = int(appr)
    if appr < 0:
        return 0
    race_group, position = divmod(appr, 10)
    table = _OFFSET_TABLES.get(race_group)
    if table is not None and position < len(table):
        return table[position]
    if race_group == 0:
        return position * 280
    if race_group == 1:
        return position * 230
    if race_group in {2, 3, 7, 14, 15, 16, 29}:
        return position * 360
    if race_group == 4:
        return 600 if position == 1 else position * 360
    if race_group == 5:
        return position * 430
    if race_group == 6:
        return position * 440
    if race_group == 28:
        return 0
    return position * 360


def monster_file_index(appr: int) -> int:
    """Return the MonXX resource number encoded by the database Appr field."""
    return max(1, int(appr) // 10 + 1)


def monster_frame_sequence(
    race_img: int,
    appr: int,
    display_mode: int,
    direction: int,
) -> MonsterFrameSequence:
    race_img = max(0, int(race_img))
    direction = max(0, min(7, int(direction)))
    display_mode = int(display_mode)
    appr = int(appr)
    offset = monster_appearance_offset(appr)
    file_index = monster_file_index(appr)

    walking = display_mode in {10, 11}
    animated = display_mode in {1, 11}
    action_start = 80 if walking else 0
    frame_count = 6 if walking else 4
    direction_skip = 4 if walking else 6
    interval_ms = 160 if walking else 200
    first_frame = offset + action_start + direction * (frame_count + direction_skip)
    frames = tuple(first_frame + index for index in range(frame_count if animated else 1))
    return MonsterFrameSequence(race_img, file_index, frames, interval_ms)
