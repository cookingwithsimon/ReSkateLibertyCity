"""Builds a Blender scene of one GTA IV area, ready for ReSkate Studio.

    blender --background --python build_area.py -- <export folders> <area.json> <out.blend> [--no-conjugate]
        [--no-lights] [--max-lights N] [--light-energy SCALE] [--sign-lights] [--vertex-shading]

<export folders> (several joined with ";") is OpenIV's openFormats export (the .odr files and the
subfolders beside them); <area.json> comes from `python -m liberty.select_area`; its "edge" placements
(just past the box) are built as solid shells only.
Each placed model becomes an object sharing one mesh per model. Its solid faces
collide as an exact triangle mesh with a surface guessed from the texture;
decals, wires, foliage and glass are drawn with no collision. A spawn goes on
the open street nearest the box's centre. Breakable props (.oft fragments) are
built whole from their children. Models with neither (props in other archives,
or ones packed in .odd dictionaries) are skipped and counted.

GTA IV stores placement rotations as the inverse quaternion, so they are
conjugated; --no-conjugate turns that off if buildings come out turned.

Each placed model's GTA IV lights (its .light: street lamps, signs, shop and
window lights) become Blender point and spot lights that the Skate Map add-on
exports, lit in the evening and at night only and without shadows. --max-lights
keeps the longest-reaching ones (default 4000); --no-lights leaves them out.
A light gets 4 W per metre of its range, kept within 16-80 W, times --light-energy (default 1).
Omni lights reach at least 10 m (GTA IV's 6 m ceiling tubes left platforms black);
down-facing spots (street lamps) get at least a 120° cone and 1.5x their reach (20 m at
least). Emissive lamp bulbs and tubes of models with no .light get a soft 40 W point light
per bulb cluster (not scaled by --light-energy).
--sign-lights adds a soft area light in front of each emissive billboard or screen, or
billboard/poster texture, of 6 m² or more (the largest 600), facing out and coloured by
its texture's average.
--vertex-shading is experimental: Studio's procedural bake of it comes out black.
"""
import json
import sys
from collections import Counter
from pathlib import Path

import math

import bpy
from mathutils import Matrix, Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liberty import dds  # noqa: E402
from liberty import emissive  # noqa: E402
from liberty import lights as oflights  # noqa: E402
from liberty import mesh as ofmesh  # noqa: E402
from liberty import studio, surfaces  # noqa: E402

LIGHT_TIMES = {"evening", "night", "weathernight"}
SHADE_ATTRIBUTE = "gta_shade"  # --vertex-shading: GTA IV's baked lighting and occlusion per vertex
MIN_LIGHT_RANGE = 2.0  # metres; tinier ones are coronas and sparkle, not light
# GTA IV's ceiling tubes reach 6 m, which leaves Hove Beach's platform black in Skate.
MIN_OMNI_RANGE = 10.0
MIN_SIGN_AREA = 6.0  # m²: billboards and screens big enough to light the street
LAMP_CLUSTER = 1.5  # m: bulbs closer than this share one light
LAMP_WATTS = 40.0  # per bulb, for bulbs of models with no .light
# Street lamps: GTA IV's down-facing spots leave the road between lamps dark in Skate.
STREET_LAMP_CONE = 120.0  # degrees, at least
STREET_LAMP_REACH = 1.5  # times the GTA range, and at least 20 m
MAX_SIGN_LIGHTS = 600


class Builder:
    def __init__(self, exports: list[Path], vertex_shading: bool = False):
        self.vertex_shading = vertex_shading  # multiply GTA IV's baked vertex colour into the base colour
        self.odrs = {p.stem.lower(): p for e in exports for p in e.rglob("*.oft")}
        self.odrs.update({p.stem.lower(): p for e in exports for p in e.rglob("*.odr")})
        self.textures = {p.stem.lower(): p for e in exports for p in e.rglob("*.dds")}
        self.images: dict[Path, bpy.types.Image] = {}
        self.materials: dict[tuple, bpy.types.Material] = {}
        self.models: dict[str, tuple] = {}
        self.lights: dict[str, list] = {}
        self.emitters: dict[str, list] = {}  # model -> [("lamp"|"sign", Island, image or None)]
        self.average: dict = {}  # image -> mean RGB
        self.opaque: dict[Path, bool] = {}
        self.missing = Counter()
        self.shaders = Counter()  # "solid gta_normal" / "detail gta_glass" -> parts

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
            colour = node.outputs["Color"]
            if self.vertex_shading:
                shade = mat.node_tree.nodes.new("ShaderNodeVertexColor")
                shade.layer_name = SHADE_ATTRIBUTE
                mix = mat.node_tree.nodes.new("ShaderNodeMix")
                mix.data_type, mix.blend_type = "RGBA", "MULTIPLY"
                mix.inputs["Factor"].default_value = 1.0
                # The Mix node keeps float, vector and colour sockets under the same names;
                # by name alone "A" is the float one, which left the colour inputs at black.
                a, b = (next(s for s in mix.inputs if s.name == n and s.type == "RGBA") for n in "AB")
                mat.node_tree.links.new(colour, a)
                mat.node_tree.links.new(shade.outputs["Color"], b)
                colour = next(s for s in mix.outputs if s.type == "RGBA")
            mat.node_tree.links.new(colour, bsdf.inputs["Base Color"])
            if cutout:
                mat.node_tree.links.new(node.outputs["Alpha"], bsdf.inputs["Alpha"])
        # Decals carry soft worn edges in their alpha; a hard mask turns those into speckles.
        alpha = ("blend" if "decal" in shader.name else "mask") if cutout else "auto"
        studio.set_material(mat, surfaces.surface_for(shader.diffuse), alpha=alpha)
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
            read = ofmesh.read_fragment if odr.suffix.lower() == ".oft" else ofmesh.read_model
            drawable, parts = read(odr)
            self.emitters[key] = self.find_emitters(odr, drawable, parts)
            groups = {True: [], False: []}
            for part in parts:
                if part.material < len(drawable.shaders):
                    shader = drawable.shaders[part.material]
                    if "decal" in shader.name:
                        ofmesh.drop_faded(part)
                    solid = surfaces.is_solid(shader.name, shader.diffuse) or self.opaque_part(odr, shader)
                    self.shaders[("solid " if solid else "detail ") + shader.name] += 1
                    groups[solid].append((part, self.material(odr, shader)))
            result = (self.mesh(name, groups[True]), self.mesh(name + "_detail", groups[False]))
        self.models[key] = result
        return result

    def find_emitters(self, odr: Path, drawable, parts) -> list:
        """Lamp islands of models with no .light (so they would cast nothing) and large
        emissive signs and screens."""
        has_lights = any((odr.parent / odr.stem).glob("*.light"))
        out = []
        for part in parts:
            if part.material >= len(drawable.shaders):
                continue
            shader = drawable.shaders[part.material]
            lamp = not has_lights and emissive.is_lamp(shader.name, shader.diffuse)
            sign = emissive.is_sign(shader.name, shader.diffuse)
            if not (lamp or sign):
                continue
            found = emissive.islands(part.positions, part.triangles)
            if lamp:
                # Bulb patterns (fairground rides, sign borders) put dozens of bulbs within
                # a metre; one light per cluster keeps them from stacking into a blow-out,
                # while ceiling lamps a few metres apart keep a light each.
                out += [("lamp", island, None) for island in emissive.merge(found, gap=LAMP_CLUSTER, facing=-1.0)]
                continue
            for island in emissive.merge(found):
                if island.area >= MIN_SIGN_AREA:
                    out.append(("sign", island, self.texture(odr, shader.diffuse)))
        return out

    def average_colour(self, image) -> tuple[float, float, float]:
        """The texture's mean colour, brightest channel scaled to 1."""
        if image is None:
            return (1.0, 1.0, 1.0)
        if image not in self.average:
            small = image.copy()
            small.scale(16, 16)
            px = small.pixels[:]
            bpy.data.images.remove(small)
            n = len(px) // 4
            rgb = [sum(px[c::4]) / max(n, 1) for c in range(3)]
            peak = max(rgb) or 1.0
            self.average[image] = tuple(max(v / peak, 0.05) for v in rgb)
        return self.average[image]

    def opaque_part(self, odr: Path, shader: ofmesh.Shader) -> bool:
        """An alpha or cutout part whose texture has no transparency: solid geometry."""
        if not shader.diffuse or not surfaces.opaque_alpha_is_solid(shader.name, shader.diffuse):
            return False
        path = odr.parent / shader.diffuse.replace("\\", "/")
        if not path.is_file():
            path = self.textures.get(Path(shader.diffuse.replace("\\", "/")).stem.lower())
        if path is None:
            return False
        if path not in self.opaque:
            self.opaque[path] = dds.is_opaque(path)
        return self.opaque[path]

    def model_lights(self, name: str) -> list:
        key = name.lower()
        if key not in self.lights:
            odr = self.odrs.get(key)
            found = oflights.read_for_model(odr) if odr is not None else []
            kept = [light for light in found if light.range >= MIN_LIGHT_RANGE]
            for light in kept:
                if not light.spot:
                    light.range = max(light.range, MIN_OMNI_RANGE)
                elif light.direction[2] < -0.7:  # a street lamp shining down
                    light.falloff = max(light.falloff, STREET_LAMP_CONE)
                    light.range = max(light.range * STREET_LAMP_REACH, 20.0)
            self.lights[key] = kept
        return self.lights[key]

    def mesh(self, name, parts):
        if not parts:
            return None
        verts, normals, uvs, colours, faces, face_mats, slots = [], [], [], [], [], [], {}
        for part, mat in parts:
            slot = slots.setdefault(mat.name, len(slots))
            base = len(verts)
            verts += part.positions
            normals += part.normals
            uvs += part.uvs
            colours += part.colours if len(part.colours) == len(part.positions) else \
                [(1.0, 1.0, 1.0)] * len(part.positions)
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
        if self.vertex_shading:
            shade = me.color_attributes.new(SHADE_ATTRIBUTE, "FLOAT_COLOR", "POINT")
            shade.data.foreach_set("color", [c for rgb in colours for c in (*rgb, 1.0)])
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
        if p.get("edge"):  # past the box: keep building shells only, not their loose details
            if solid is None:
                counts["edge details dropped"] += 1
                continue
            detail = None
        if solid is None:
            counts["detail_only " + p["model"]] += 1
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


def add_lights(area: dict, builder: Builder, conjugate: bool, limit: int, energy: float = 1.0) -> Counter:
    """Every placed model's GTA IV lights as Blender lights, the longest-reaching
    `limit` of them. Edge placements are past the box and bring no lights."""
    wanted = []
    for p in area["placements"]:
        if p.get("edge"):
            continue
        x, y, z, w = p["rotation"]
        rotation = Quaternion((w, -x, -y, -z) if conjugate else (w, x, y, z))
        for light in builder.model_lights(p["model"]):
            wanted.append((light, rotation, Vector(p["position"])))
    wanted.sort(key=lambda row: -row[0].range)
    counts = Counter(lights_found=len(wanted))
    root = bpy.context.scene.collection
    for i, (light, rotation, origin) in enumerate(wanted[:limit]):
        data = bpy.data.lights.new(f"gta_light_{i}", "SPOT" if light.spot else "POINT")
        data.color = light.color
        # 4 W per metre of GTA range, 16-80 W, times --light-energy. The game's own range
        # handles the falloff; scaling watts by range squared (and by _f28) made Hove Beach's
        # long-range sodium lamps (up to 1,800 W) flare, while 25-64 W lights looked right.
        data.energy = energy * min(max(4.0 * light.range, 16.0), 80.0)
        data.shadow_soft_size = 0.1
        data.use_shadow = False
        if light.spot:
            outer = max(light.falloff, 1.0)
            data.spot_size = math.radians(min(outer, 179.0))
            data.spot_blend = max(0.0, min(1.0, 1.0 - light.hotspot / outer))
        obj = bpy.data.objects.new(data.name, data)
        obj.location = origin + rotation @ Vector(light.position)
        direction = rotation @ Vector(light.direction)
        if direction.length > 1e-6:
            obj.rotation_mode = "QUATERNION"
            obj.rotation_quaternion = Vector((0.0, 0.0, -1.0)).rotation_difference(direction.normalized())
        root.objects.link(obj)
        studio.set_light(obj, light.range, LIGHT_TIMES)
        counts["spot" if light.spot else "point"] += 1
    counts["lights_dropped_by_limit"] = max(0, len(wanted) - limit)
    return counts


def add_emitter_lights(area: dict, builder: Builder, conjugate: bool, energy: float, signs: bool) -> Counter:
    """Point lights on lamp bulbs and tubes of models with no .light, and (signs=True)
    a soft area light 0.3 m in front of each large emissive billboard or screen,
    facing out and coloured by its texture; all on in the evening and at night."""
    counts = Counter()
    root = bpy.context.scene.collection
    sign_rows = []
    for p in area["placements"]:
        if p.get("edge"):
            continue
        x, y, z, w = p["rotation"]
        rotation = Quaternion((w, -x, -y, -z) if conjugate else (w, x, y, z))
        origin = Vector(p["position"])
        for kind, island, image in builder.emitters.get(p["model"].lower(), []):
            centre = origin + rotation @ Vector(island.centre)
            normal = (rotation @ Vector(island.normal)).normalized()
            if kind == "lamp":
                data = bpy.data.lights.new(f"gta_lamp_{counts['lamp']}", "POINT")
                data.color = (1.0, 0.95, 0.85)
                # A lamp is often two islands (front and back of the bulb): keep up to two
                # bulbs' worth, so pairs stay as bright while bulb patterns collapse to one.
                # Fixed watts, not scaled by --light-energy: these are guesses, and at 3x
                # they blew out; a wide soft source keeps them from glaring.
                data.energy = LAMP_WATTS * min(island.count, 2)
                data.shadow_soft_size = 0.5
                data.use_shadow = False
                obj = bpy.data.objects.new(data.name, data)
                obj.location = centre + normal * 0.15
                root.objects.link(obj)
                studio.set_light(obj, MIN_OMNI_RANGE, LIGHT_TIMES)
                counts["lamp"] += 1
            elif signs:
                sign_rows.append((island, image, centre, normal, rotation))
    sign_rows.sort(key=lambda row: -row[0].area)
    for island, image, centre, normal, rotation in sign_rows[:MAX_SIGN_LIGHTS]:
        width = min(max(island.width, 0.5), 30.0)
        height = min(max(island.height, 0.5), 30.0)
        data = bpy.data.lights.new(f"gta_sign_{counts['sign']}", "AREA")
        data.shape = "RECTANGLE"
        data.size, data.size_y = width, height
        data.color = builder.average_colour(image)
        data.energy = energy * min(max(20.0 * island.area, 100.0), 3000.0)
        data.use_shadow = False
        obj = bpy.data.objects.new(data.name, data)
        # An area lamp shines down its local -Z: X along the sign's width, Y up it, Z into the wall.
        right = (rotation @ Vector(island.right)).normalized()
        up = (rotation @ Vector(island.up)).normalized()
        frame = Matrix((
            (right.x, up.x, -normal.x, 0.0), (right.y, up.y, -normal.y, 0.0),
            (right.z, up.z, -normal.z, 0.0), (0.0, 0.0, 0.0, 1.0))).normalized()
        frame.translation = centre + normal * 0.3
        obj.matrix_world = frame
        root.objects.link(obj)
        studio.set_light(obj, max(width, height) * 1.5 + 5.0, LIGHT_TIMES)
        counts["sign"] += 1
    counts["signs_dropped_by_limit"] = max(0, len(sign_rows) - MAX_SIGN_LIGHTS)
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
    builder = Builder(exports, vertex_shading="--vertex-shading" in argv)
    counts = place(area, builder, conjugate)
    studio.add_spawn(street_spawn())
    if "--no-lights" not in argv:
        limit = int(argv[argv.index("--max-lights") + 1]) if "--max-lights" in argv else 4000
        energy = float(argv[argv.index("--light-energy") + 1]) if "--light-energy" in argv else 1.0
        counts.update(add_lights(area, builder, conjugate, limit, energy))
        emitted = add_emitter_lights(area, builder, conjugate, energy, "--sign-lights" in argv)
        counts.update({f"{k}_lights" if k in ("lamp", "sign") else k: v for k, v in emitted.items()})
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    detail_only = Counter({k.split(" ", 1)[1]: v for k, v in counts.items() if k.startswith("detail_only ")})
    counts = Counter({k: v for k, v in counts.items() if not k.startswith("detail_only ")})
    report = {
        "placements": len(area["placements"]), **counts,
        "detail_only_total": sum(detail_only.values()), "detail_only_top": detail_only.most_common(40),
        "shaders": builder.shaders.most_common(),
        "models": len(builder.models), "materials": len(builder.materials), "images": len(builder.images),
        "missing_top": builder.missing.most_common(25), "missing_total": sum(builder.missing.values()),
    }
    out.with_suffix(".report.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
