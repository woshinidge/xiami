from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Engine(str, Enum):
    GOM = "gom"
    LINGFENG = "lingfeng"


@dataclass(frozen=True)
class EngineProfile:
    engine: Engine
    absolute_coord_prefix: str = "&"
    absolute_coord_tags: frozenset[str] = field(default_factory=frozenset)
    parse_container_ids: bool = False
    if_unknown_defaults_false: bool = True


_PROFILES: dict[Engine, EngineProfile] = {
    Engine.GOM: EngineProfile(
        engine=Engine.GOM,
        absolute_coord_tags=frozenset({"text"}),
        parse_container_ids=False,
    ),
    Engine.LINGFENG: EngineProfile(
        engine=Engine.LINGFENG,
        absolute_coord_tags=frozenset(
            {
                "img",
                "playimg",
                "playimgex",
                "imgex",
                "itemshow",
                "useritem",
                "imgnum",
                "text",
                "inputnum",
                "inputtext",
                "progressbar",
                "looks",
                "dnitems",
                "stateitem",
                "newopui",
                "countdown",
                "imgcountdown",
                "layout",
                "listview",
            }
        ),
        parse_container_ids=True,
    ),
}


def get_profile(engine: Engine | str = Engine.GOM) -> EngineProfile:
    if isinstance(engine, str):
        engine = Engine(engine.lower())
    return _PROFILES[engine]
