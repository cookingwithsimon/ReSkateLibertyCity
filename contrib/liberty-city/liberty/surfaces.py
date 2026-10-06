"""Which Studio surface (and whether any collision) a GTA IV material gets.

Decided from the shader and texture names, since the render mesh carries no
GTA surface id. Keys of liberty.studio.SURFACES.
"""
from __future__ import annotations

# Shaders whose faces are never solid: decals sit 2 mm above a surface, wires
# and foliage are cards. They are drawn but given no collision. "emissive" is not
# here: emissivenight is the shader on most building walls (lit windows at night).
NON_SOLID_SHADERS = ("decal", "wire", "tree", "glass", "alpha", "cutout", "cloth")

TEXTURE_SURFACES = (
    (("road", "tarmac", "asphalt", "tar_"), "asphalt"),
    (("grass", "lawn", "turf"), "grass"),
    (("dirt", "mud", "soil", "earth"), "earth"),
    (("brick",), "brick"),
    (("marble",), "marble"),
    (("glass", "window", "win_"), "glass"),
    (("rail", "metal", "steel", "iron", "grate", "grill"), "metal"),
)


def is_solid(shader: str) -> bool:
    return not any(word in shader for word in NON_SOLID_SHADERS)


def surface_for(texture: str | None) -> str:
    name = (texture or "").lower().rsplit("\\", 1)[-1]
    for words, surface in TEXTURE_SURFACES:
        if any(w in name for w in words):
            return surface
    return "concrete"
