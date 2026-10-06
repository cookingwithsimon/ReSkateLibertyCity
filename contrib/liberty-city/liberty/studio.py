"""Writes ReSkate Studio's map settings onto Blender objects (runs inside Blender).

Studio's "Skate Map" add-on (sk8_map_export, 2.20) keeps them in PointerProperty
groups: Object.sk8_object, Material.sk8_material, Object.sk8_grind_curve. When
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


def set_material(mat, surface: str = "default", invisible: bool = False) -> None:
    settings = getattr(mat, "sk8_material", None)
    if settings is not None:
        settings.surface = surface
        settings.invisible = invisible
    else:
        mat["sk8_surface"] = surface
        mat["sk8_material"] = {"invisible": invisible}


def set_grind_curve(obj, radius: float = 0.03) -> None:
    settings = getattr(obj, "sk8_grind_curve", None)
    if settings is not None:
        settings.enabled = True
        settings.radius = radius
    else:
        obj["sk8_grind_curve"] = {"enabled": True, "radius": radius}


def add_spawn(location, yaw_degrees: float = 0.0):
    """Studio needs exactly one Empty named `spawn`; it faces its +Y turned by `yaw`."""
    from math import radians
    empty = bpy.data.objects.new("spawn", None)
    empty.location = location
    empty.rotation_euler = (0.0, 0.0, radians(yaw_degrees))
    bpy.context.scene.collection.objects.link(empty)
    return empty
