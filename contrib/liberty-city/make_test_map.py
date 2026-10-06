"""Builds a tiny test map to prove the Studio chain before any GTA IV data.

    blender --background --factory-startup --python make_test_map.py -- <out.blend>

A 40 x 40 m concrete plaza with a 0.4 m ledge, a 1 m box, a 3-step stair set,
a handrail you can grind, and a spawn. Every size is real-world, in metres.
"""
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liberty import studio  # noqa: E402


def material(name, colour, surface):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*colour, 1.0)
    studio.set_material(mat, surface)
    return mat


def box(name, size, location, mat, surface):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = size
    bpy.ops.object.transform_apply(scale=True)
    obj.data.materials.append(mat)
    studio.set_collision(obj, "triangle_mesh", surface)
    return obj


def main(out: Path) -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.preferences.addon_enable(module="sk8_map_export")
    except Exception:
        print("Skate Map add-on not enabled; writing plain sk8_* properties instead.")
    concrete = material("concrete", (0.55, 0.55, 0.52), "concrete")
    metal = material("metal", (0.3, 0.3, 0.32), "metal_rail")

    box("ground", (40, 40, 0.5), (0, 0, -0.25), concrete, "concrete")
    box("ledge", (6, 0.6, 0.4), (-6, 6, 0.2), concrete, "concrete")
    box("manual_pad", (3, 3, 1.0), (8, 8, 0.5), concrete, "concrete")
    for step in range(3):  # 0.17 m risers, 0.3 m treads
        box(f"stair_{step}", (4, 0.3, 0.17 * (step + 1)), (0, -6 + 0.3 * step, 0.085 * (step + 1)), concrete, "concrete")

    curve = bpy.data.curves.new("handrail", "CURVE")
    curve.dimensions = "3D"
    spline = curve.splines.new("POLY")
    spline.points.add(1)
    spline.points[0].co = (2.2, -6.5, 0.9, 1.0)
    spline.points[1].co = (2.2, -5.0, 1.4, 1.0)
    rail = bpy.data.objects.new("handrail", curve)
    bpy.context.scene.collection.objects.link(rail)
    studio.set_grind_curve(rail, radius=0.025)
    # What players see of the rail; the grind curve above is its collision.
    curve_mesh = curve.copy()
    curve_mesh.bevel_depth = 0.025
    tube = bpy.data.objects.new("handrail_tube", curve_mesh)
    bpy.context.scene.collection.objects.link(tube)
    bpy.context.view_layer.objects.active = tube
    tube.select_set(True)
    bpy.ops.object.convert(target="MESH")
    tube.data.materials.append(metal)
    studio.set_collision(tube, "none")

    studio.add_spawn((0, 12, 0.1), yaw_degrees=180)
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    print(f"Wrote {out}")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    main(Path(args[0] if args else "liberty_test.blend").resolve())
