"""Writes ReSkate Studio's map settings onto Blender objects (runs inside Blender).

Studio's "Skate Map" add-on (sk8_map_export, 2.20) keeps them in PointerProperty
groups: Object.sk8_object, Material.sk8_material, Object.sk8_grind_curve,
Object.sk8_light. When
the add-on is not enabled the same values go in as the plain ID properties its
importer also reads, so a .blend built headless still compiles.
"""
from __future__ import annotations

import bpy

# Studio's native collision materials used by the converter. The enum ids of
# sk8_object.collision_material are `material_<packed>`, the MaterialDecl's
# packed word (flags | material slot << 6 | property slot << 19), not row numbers.
SURFACES = {
    "default": "material_0032",
    "concrete": "material_0096",
    "asphalt": "material_0160",
    "metal": "material_0352",
    "marble": "material_0480",
    "grass": "material_0608",
    "brick": "material_2016",
    "glass": "material_2144",
    "metal_rail": "material_2976",
    # Metal Rail with the IncludeInSurfaceAnalysis property: grinds as a smooth surface,
    # as the add-on's Round Rail switch does, so many-sided tubes grind too.
    "metal_rail_round": "material_37227424",
    "earth": "material_3488",
    "stairs": "material_47186720",  # Concrete with the Stairs behaviour
}


def set_collision(obj, mode: str = "triangle_mesh", surface: str | None = None) -> None:
    settings = getattr(obj, "sk8_object", None)
    if settings is not None:
        settings.collision_mode = mode
        if surface:
            settings.collision_material = SURFACES[surface]
    else:
        obj["sk8_collision_mode"] = mode


# sk8_material.surface has its own, shorter list; the rest fall back to default.
MATERIAL_SURFACES = {"concrete", "asphalt", "metal", "brick", "glass", "grass", "metal_rail"}


def set_material(mat, surface: str = "default", invisible: bool = False, alpha: str = "auto") -> None:
    """`surface` is a key of SURFACES; `alpha` is auto, opaque, mask or blend."""
    look = surface if surface in MATERIAL_SURFACES else \
        {"earth": "dirt", "metal_rail_round": "metal_rail"}.get(surface, "default")
    settings = getattr(mat, "sk8_material", None)
    if settings is not None:
        settings.surface = look
        settings.invisible = invisible
        settings.alpha = alpha
        if surface in SURFACES:
            settings.collision_material = SURFACES[surface]
    else:
        mat["sk8_surface"] = look
        mat["sk8_material"] = {"invisible": invisible, "alpha": alpha}


def set_grind_curve(obj, radius: float = 0.03) -> None:
    settings = getattr(obj, "sk8_grind_curve", None)
    if settings is not None:
        settings.enabled = True
        settings.radius = radius
    else:
        obj["sk8_grind_curve"] = {"enabled": True, "radius": radius}


# Object.sk8_light.time_of_day flags, as the add-on's light_records sums them.
LIGHT_TIMES = {"morning": 1, "noon": 2, "afternoon": 4, "evening": 8,
               "night": 16, "weatherday": 32, "weathernight": 64}


def set_light(obj, range_m: float, times: set[str]) -> None:
    """A light's native range in metres and the times of day it is on."""
    settings = getattr(obj, "sk8_light", None)
    if settings is not None:
        settings.attenuation_radius = range_m
        settings.time_of_day = set(times)
    else:
        obj["sk8_light_range"] = float(range_m)
        obj["sk8_light_tod"] = sum(LIGHT_TIMES[t] for t in times)


def add_spawn(location, yaw_degrees: float = 0.0):
    """Studio needs exactly one Empty named `spawn`; it faces its +Y turned by `yaw`."""
    from math import radians
    empty = bpy.data.objects.new("spawn", None)
    empty.location = location
    empty.rotation_euler = (0.0, 0.0, radians(yaw_degrees))
    bpy.context.scene.collection.objects.link(empty)
    return empty
