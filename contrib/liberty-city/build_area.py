"""Builds a Blender scene of one GTA IV area, ready for ReSkate Studio.

    blender --background --python build_area.py -- <export folders> <area.json> <out.blend> [--no-conjugate]

<export folders> (several joined with ";") is OpenIV's openFormats export (the .odr files and the
subfolders beside them); <area.json> comes from `python -m liberty.select_area`.
Each placed model becomes an object sharing one mesh per model. Its solid faces
collide as an exact triangle mesh with a surface guessed from the texture;
decals, wires, foliage and glass are drawn with no collision. A spawn goes on
the open street nearest the box's centre. Models with no .odr (props in other archives,
or ones packed in .odd dictionaries) are skipped and counted.

GTA IV stores placement rotations as the inverse quaternion, so they are
conjugated; --no-conjugate turns that off if buildings come out turned.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liberty import mesh as ofmesh  # noqa: E402
from liberty import studio, surfaces  # noqa: E402


class Builder:
    def __init__(self, exports: list[Path]):
        self.odrs = {p.stem.lower(): p for e in exports for p in e.rglob("*.odr")}
        self.textures = {p.stem.lower(): p for e in exports for p in e.rglob("*.dds")}
        self.images: dict[Path, bpy.types.Image] = {}
        self.materials: dict[tuple, bpy.types.Material] = {}
        self.models: dict[str, tuple] = {}
        self.missing = Counter()

    def texture(self, odr: Path, token: str | None):
        if not token or token.lower() == "null":  # OpenIV writes "null" for an unset slot
            return None
        path = odr.parent / token.replace("\\", "/")
        if not path.is_file():
            path = self.textures.get(Path(token.replace("\\", "/")).stem.lower())
        if path is None:
            self.missing["texture " + token] += 1
            return None
        if path not in self.images:
            self.images[path] = bpy.data.images.load(str(path), check_existing=True)
        return self.images[path]

    def material(self, odr: Path, shader: ofmesh.Shader):
        key = (shader.name, (shader.diffuse or "").lower())
        if key in self.materials:
            return self.materials[key]
        name = Path((shader.diffuse or shader.name).replace("\\", "/")).stem
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        bsdf.inputs["Roughness"].default_value = 0.8
        image = self.texture(odr, shader.diffuse)
        cutout = not surfaces.is_solid(shader.name)
        if image is not None:
            node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            node.image = image
            mat.node_tree.links.new(node.outputs["Color"], bsdf.inputs["Base Color"])
            if cutout:
                mat.node_tree.links.new(node.outputs["Alpha"], bsdf.inputs["Alpha"])
        studio.set_material(mat, surfaces.surface_for(shader.diffuse), alpha="mask" if cutout else "auto")
        self.materials[key] = mat
        return mat

    def model(self, name: str):
        """(solid mesh or None, non-solid mesh or None) for a model, built once."""
        key = name.lower()
        if key in self.models:
            return self.models[key]
        odr = self.odrs.get(key)
        result = (None, None)
        if odr is None:
            self.missing["model " + name] += 1
        else:
            drawable, parts = ofmesh.read_model(odr)
            groups = {True: [], False: []}
            for part in parts:
                if part.material < len(drawable.shaders):
                    shader = drawable.shaders[part.material]
                    groups[surfaces.is_solid(shader.name)].append((part, self.material(odr, shader)))
            result = (self.mesh(name, groups[True]), self.mesh(name + "_detail", groups[False]))
        self.models[key] = result
        return result

    @staticmethod
    def mesh(name, parts):
        if not parts:
            return None
        verts, normals, uvs, faces, face_mats, slots = [], [], [], [], [], {}
        for part, mat in parts:
            slot = slots.setdefault(mat.name, len(slots))
            base = len(verts)
            verts += part.positions
            normals += part.normals
            uvs += part.uvs
            for tri in part.triangles:
                if max(tri) < len(part.positions) and len(set(tri)) == 3:
                    faces.append(tuple(base + i for i in tri))
                    face_mats.append(slot)
        if not faces:
            return None
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        for mat_name in slots:
            me.materials.append(bpy.data.materials[mat_name])
        me.polygons.foreach_set("material_index", face_mats)
        layer = me.uv_layers.new(name="UVMap")
        loop_uvs = [c for loop in me.loops for c in uvs[loop.vertex_index]]
        layer.data.foreach_set("uv", loop_uvs)
        me.validate(clean_customdata=False)
        me.normals_split_custom_set_from_vertices([Vector(n).normalized() for n in normals])
        me.update()
        return me


def place(area: dict, builder: Builder, conjugate: bool) -> Counter:
    counts = Counter()
    root = bpy.context.scene.collection
    for i, p in enumerate(area["placements"]):
        solid, detail = builder.model(p["model"])
        if solid is None and detail is None:
            counts["skipped"] += 1
            continue
        x, y, z, w = p["rotation"]
        rotation = Quaternion((w, -x, -y, -z) if conjugate else (w, x, y, z))
        for me, collide in ((solid, True), (detail, False)):
            if me is None:
                continue
            obj = bpy.data.objects.new(f"{me.name}.{i}", me)
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = rotation
            obj.location = p["position"]
            root.objects.link(obj)
            studio.set_collision(obj, "triangle_mesh" if collide else "none")
            counts["objects"] += 1
        counts["placed"] += 1
    return counts


def _hits(x: float, y: float) -> list[float]:
    """Heights of every surface straight down at (x, y), top first."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    heights, z = [], 1000.0
    while len(heights) < 64:
        hit, location, *_ = bpy.context.scene.ray_cast(depsgraph, Vector((x, y, z)), Vector((0, 0, -1)))
        if not hit:
            break
        heights.append(location.z)
        z = location.z - 0.01
    return heights


def street_spawn(radius: float = 80.0, step: float = 4.0) -> tuple[float, float, float]:
    """The open spot nearest the centre: open sky above, so on a street or
    plaza rather than inside a building, and within 3 m of street level (the
    10th percentile of top surfaces), since a roof with nothing modelled under
    it is open sky too."""
    points = [(x * step, y * step) for x in range(-int(radius / step), int(radius / step) + 1)
              for y in range(-int(radius / step), int(radius / step) + 1)]
    columns = {p: _hits(*p) for p in points}
    tops = sorted(h[0] for h in columns.values() if h)
    street = tops[len(tops) // 10] if tops else 0.0
    for x, y in sorted(points, key=lambda p: p[0] ** 2 + p[1] ** 2):
        heights = columns[(x, y)]
        if heights and heights[0] - heights[-1] < 0.5 and heights[0] - street < 3.0:
            return x, y, heights[0] + 0.2
    return 0.0, 0.0, (_hits(0.0, 0.0) or [0.0])[-1] + 0.2


def main(argv):
    exports = [Path(p) for p in argv[0].split(";") if p]
    area_file, out = Path(argv[1]), Path(argv[2]).resolve()
    conjugate = "--no-conjugate" not in argv
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        bpy.ops.preferences.addon_enable(module="sk8_map_export")
    except Exception:
        print("Skate Map add-on not enabled; writing plain sk8_* properties instead.")
    area = json.loads(area_file.read_text())
    builder = Builder(exports)
    counts = place(area, builder, conjugate)
    studio.add_spawn(street_spawn())
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    report = {
        "placements": len(area["placements"]), **counts,
        "models": len(builder.models), "materials": len(builder.materials), "images": len(builder.images),
        "missing_top": builder.missing.most_common(25), "missing_total": sum(builder.missing.values()),
    }
    out.with_suffix(".report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
