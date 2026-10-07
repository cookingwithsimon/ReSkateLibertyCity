"""--lean: fewer triangles where nobody skates.

On a 600 x 1,000 m Hove Beach, trees, weeds and wall clutter (aircon units, wall
lights, bin bags, box piles) are millions of triangles, and the rim of buildings
just past the box brings its own street furniture. With --lean:

- foliage and wall clutter use GTA IV's own medium-detail mesh where the model
  has one (the game shows that one from a few tens of metres anyway);
- edge placements (past the box) keep only models at least EDGE_MIN_SIZE across,
  the building shells, and drop the fences, bins and lamps around them.

Benches, fences, rails, lamps and everything else you can grind keep full detail.
"""
from __future__ import annotations

import math
from pathlib import Path

from . import mesh

EDGE_MIN_SIZE = 10.0  # metres: smaller edge placements are street furniture, not shells
FOLIAGE_SHADERS = ("tree",)
FOLIAGE_NAMES = ("birch", "elm", "londonp", "weedpatch", "ingame", "bush", "hedge", "ivy")  # trees also by shader
CLUTTER_NAMES = ("cj_aircon", "bm_wall_light", "cj_bin_bag", "box_pile", "bm_skylight", "cj_int_plant")


def use_med(model: str, shaders=()) -> bool:
    """Whether to build this model from its medium-detail mesh."""
    name = model.lower()
    if any(w in name for w in FOLIAGE_NAMES + CLUTTER_NAMES):
        return True
    return any(any(w in s for w in FOLIAGE_SHADERS) for s in shaders)


def keep_edge(size: float) -> bool:
    return size >= EDGE_MIN_SIZE


def wants_med(path: Path, model: str) -> bool:
    """use_med, reading the model's shaders from its .odr or .oft (not its mesh)."""
    text = Path(path).read_text(encoding="latin-1")
    if path.suffix.lower() == ".oft":
        text = text[text.find("drawable"):] if "drawable" in text else ""
    return use_med(model, [s.name for s in mesh.parse_odr(text).shaders])


def size(parts) -> float:
    """The largest extent of a model's parts, in metres."""
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for part in parts:
        for v in part.positions:
            for i in range(3):
                lo[i], hi[i] = min(lo[i], v[i]), max(hi[i], v[i])
    return max(h - l for h, l in zip(hi, lo)) if lo[0] != math.inf else 0.0
