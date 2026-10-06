"""Plain-text GTA IV model definitions (.ide): the `objs` and `tobj` sections.

Each row starts `name, texture dictionary, draw distance, flags...`; the rest
(bounds, and the drawable dictionary for models packed in a .wdd) varies, so it
is kept raw.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .hashing import model_hash

SECTIONS = {"objs", "tobj"}


@dataclass(frozen=True)
class ModelDef:
    name: str
    txd: str
    draw_distance: float
    flags: int
    extra: tuple[str, ...] = field(default=())

    @property
    def is_lod(self) -> bool:
        # Low-detail stand-ins are named for it; big buildings legitimately
        # have long draw distances, so distance alone is no sign.
        return self.name.lower().startswith(("lod", "slod"))


def parse(text: str) -> list[ModelDef]:
    out, section = [], None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        word = line.lower()
        if section is None:
            section = word if word in SECTIONS or word.isalpha() else None
            continue
        if word == "end":
            section = None
            continue
        if section not in SECTIONS:
            continue
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 4:
            continue
        try:
            out.append(ModelDef(cols[0], cols[1], float(cols[2]), int(float(cols[3])), tuple(cols[4:])))
        except ValueError:
            continue
    return out


def read_all(paths) -> dict[int, ModelDef]:
    """Every model in `paths`, by model hash (what a .wpl refers to; hash the
    lowercase name to look up an .opl's named placement)."""
    models = {}
    for p in paths:
        for m in parse(Path(p).read_text(encoding="latin-1")):
            models[model_hash(m.name)] = m
    return models
