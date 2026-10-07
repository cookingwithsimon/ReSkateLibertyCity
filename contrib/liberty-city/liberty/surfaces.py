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


# Cutout and alpha shaders also draw solid things with holes in them: railings,
# grates, chain-link and the station's queue rails (og_BS3blk07station01 draws
# them with gta_cutout). Those collide when the texture says what they are;
# foliage stays a card.
SOLID_CUTOUT_TEXTURES = ("rail", "fence", "grate", "grill", "mesh", "msh", "metal", "mtl", "barrier",
                         "gate", "cage", "balcon", "ladder", "stair", "fire_esc", "fireesc", "scaff")
FOLIAGE_TEXTURES = ("leaf", "leaves", "tree", "bush", "ivy", "plant", "hedge", "flower", "grass",
                    "foliage", "branch", "fern", "vine")


def is_solid(shader: str, texture: str | None = None) -> bool:
    """Whether faces with this shader (and diffuse texture) collide."""
    if not any(word in shader for word in NON_SOLID_SHADERS):
        return True
    if texture and ("cutout" in shader or "alpha" in shader) and "decal" not in shader:
        name = texture.lower().rsplit("\\", 1)[-1]
        return any(w in name for w in SOLID_CUTOUT_TEXTURES) and not any(w in name for w in FOLIAGE_TEXTURES)
    return False


def surface_for(texture: str | None) -> str:
    name = (texture or "").lower().rsplit("\\", 1)[-1]
    for words, surface in TEXTURE_SURFACES:
        if any(w in name for w in words):
            return surface
    return "concrete"
