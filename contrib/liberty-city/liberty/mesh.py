"""OpenIV's text models: .odr (shaders + LOD list) and .mesh (geometry).

.odr: `shadinggroup { Shaders n { <shader>.sps <texture> [params...] } }` then a
`lodgroup` whose `high <count> <path.mesh> <index> <distance>` names the mesh.
.mesh ("Version 11 13"): `Mtl i { Prim 0 { Idx n {...} Verts m {...} } }`, where
Mtl i is the i-th shader. Idx is a triangle list local to its Verts. A vertex
line is ten " / "-separated groups: position, normal, colour RGBA, tangent,
then six UV sets; only UV0 is used.

.oft (fragments: the breakable props such as lamps, signals and bins) carries the
shaders in its `drawable` block and lists `child <path.child>` entries. Each
.child names its own `high 1 <path.mesh> <bone> ...` in that bone's local space;
the bones come from the .skel beside it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

TEXTURE = re.compile(r"\.dds$", re.I)


@dataclass
class Shader:
    name: str  # e.g. gta_normal_spec
    textures: list[str]  # texture tokens in order: a path inside the export, or a bare name

    @property
    def diffuse(self) -> str | None:
        return self.textures[0] if self.textures else None


@dataclass
class Drawable:
    shaders: list[Shader]
    high_mesh: str | None  # path relative to the .odr's folder


@dataclass
class Part:
    material: int
    positions: list[tuple[float, float, float]] = field(default_factory=list)
    normals: list[tuple[float, float, float]] = field(default_factory=list)
    uvs: list[tuple[float, float]] = field(default_factory=list)
    alphas: list[float] = field(default_factory=list)  # vertex colour alpha, 0..1
    triangles: list[tuple[int, int, int]] = field(default_factory=list)


def _is_texture_token(token: str) -> bool:
    # Numbers and semicolon vectors are shader parameters; anything else is a texture.
    if TEXTURE.search(token):
        return True
    try:
        float(token.split(";")[0])
        return False
    except ValueError:
        return True


def parse_odr(text: str) -> Drawable:
    shaders, high, in_shaders = [], None, False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("Shaders"):
            in_shaders = True
            continue
        if in_shaders:
            if line == "{":
                continue
            if line == "}":
                in_shaders = False
                continue
            tokens = line.split()
            if tokens and tokens[0].lower().endswith(".sps"):
                textures = [t for t in tokens[1:] if _is_texture_token(t)]
                shaders.append(Shader(tokens[0][:-4].lower(), textures))
            continue
        if line.startswith("high "):
            tokens = line.split()
            if len(tokens) >= 3 and tokens[1] != "none":
                high = tokens[2]
    return Drawable(shaders, high)


def parse_mesh(text: str) -> list[Part]:
    parts: list[Part] = []
    part = None
    mode = None  # "idx" or "verts" while inside that block
    pending: list[int] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("Mtl "):
            part = Part(int(line.split()[1]))
            parts.append(part)
            mode = None
            continue
        if part is None:
            continue
        if line.startswith("Idx "):
            mode, pending = "idx", []
            continue
        if line.startswith("Verts "):
            mode = "verts"
            continue
        if line == "{":
            continue
        if line == "}":
            if mode == "idx":
                part.triangles.extend(tuple(pending[i:i + 3]) for i in range(0, len(pending) - 2, 3))
            mode = None
            continue
        if mode == "idx":
            pending.extend(int(t) for t in line.split())
        elif mode == "verts":
            groups = [g.split() for g in line.split("/")]
            if len(groups) < 5:
                continue
            part.positions.append(tuple(float(v) for v in groups[0][:3]))
            part.normals.append(tuple(float(v) for v in groups[1][:3]))
            colour = groups[2]
            part.alphas.append(float(colour[3]) / 255.0 if len(colour) >= 4 else 1.0)
            u, v = (float(x) for x in groups[4][:2])
            part.uvs.append((u, 1.0 - v))  # DirectX top-left origin to Blender bottom-left
    return parts


def read_model(odr_path: Path) -> tuple[Drawable, list[Part]]:
    odr_path = Path(odr_path)
    drawable = parse_odr(odr_path.read_text(encoding="latin-1"))
    if not drawable.high_mesh:
        return drawable, []
    mesh_path = odr_path.parent / drawable.high_mesh.replace("\\", "/")
    if not mesh_path.is_file():
        return drawable, []
    return drawable, parse_mesh(mesh_path.read_text(encoding="latin-1"))


def _qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def _rotate(q, v):
    x, y, z, _ = _qmul(_qmul(q, (*v, 0.0)), (-q[0], -q[1], -q[2], q[3]))
    return (x, y, z)


def parse_skel(text: str) -> dict[int, tuple[tuple, tuple]]:
    """{bone index: (offset, quaternion xyzw)} in fragment space, chaining each
    bone's LocalOffset and RotationQuaternion down the hierarchy."""
    bones: dict[int, tuple[tuple, tuple]] = {}
    stack: list[dict] = []  # open bones, innermost last
    depth_of: list[int] = []  # brace depth at which each open bone's block closes
    depth = 0
    for raw in text.splitlines():
        tokens = raw.split()
        if not tokens:
            continue
        key = tokens[0]
        if key == "bone":
            parent = stack[-1] if stack else None
            stack.append({"parent": parent, "offset": (0.0, 0.0, 0.0), "rotation": (0.0, 0.0, 0.0, 1.0)})
            depth_of.append(depth)
        elif stack and key == "Index":
            stack[-1]["index"] = int(tokens[1])
        elif stack and key == "LocalOffset":
            stack[-1]["offset"] = tuple(float(t) for t in tokens[1:4])
        elif stack and key == "RotationQuaternion":
            bone = stack[-1]
            bone["rotation"] = tuple(float(t) for t in tokens[1:5])
            parent = bone["parent"]
            if parent is None:
                offset, rotation = bone["offset"], bone["rotation"]
            else:
                p_off, p_rot = parent["world"]
                offset = tuple(a + b for a, b in zip(p_off, _rotate(p_rot, bone["offset"])))
                rotation = _qmul(p_rot, bone["rotation"])
            bone["world"] = (offset, rotation)
            if "index" in bone:
                bones[bone["index"]] = bone["world"]
        for token in tokens:  # braces may share a line with a keyword
            if token == "{":
                depth += 1
            elif token == "}":
                depth -= 1
                if depth_of and depth == depth_of[-1]:
                    depth_of.pop()
                    stack.pop()
    return bones


def _child_mesh(text: str) -> tuple[str, int] | None:
    for raw in text.splitlines():
        tokens = raw.split()
        if len(tokens) >= 4 and tokens[0] == "high" and tokens[1] != "none":
            return tokens[2], int(tokens[3])
    return None


def read_fragment(oft_path: Path) -> tuple[Drawable, list[Part]]:
    """Every child's high mesh, moved from its bone into fragment space."""
    oft_path = Path(oft_path)
    text = oft_path.read_text(encoding="latin-1")
    drawable = parse_odr(text[text.find("drawable"):] if "drawable" in text else "")
    folder = oft_path.parent
    skels = list((folder / oft_path.stem).glob("*.skel"))
    bones = parse_skel(skels[0].read_text(encoding="latin-1")) if skels else {}
    parts: list[Part] = []
    for raw in text.splitlines():
        tokens = raw.split()
        if len(tokens) < 2 or tokens[0] != "child":
            continue
        child = folder / tokens[1].replace("\\", "/")
        if not child.is_file():
            continue
        found = _child_mesh(child.read_text(encoding="latin-1"))
        if found is None:
            continue
        mesh_path = child.parent / found[0].replace("\\", "/")
        if not mesh_path.is_file():
            continue
        offset, rotation = bones.get(found[1], ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
        for part in parse_mesh(mesh_path.read_text(encoding="latin-1")):
            part.positions = [tuple(o + r for o, r in zip(offset, _rotate(rotation, v))) for v in part.positions]
            part.normals = [_rotate(rotation, n) for n in part.normals]
            parts.append(part)
    return drawable, parts


def drop_faded(part: Part, threshold: float = 0.5) -> Part:
    """Keeps only the triangles whose corners' mean vertex alpha reaches the
    threshold. GTA IV decal shaders fade by vertex alpha, which Studio cannot
    draw, so the faded-out triangles would otherwise show as opaque patches."""
    if part.alphas:
        part.triangles = [t for t in part.triangles
                          if max(t) < len(part.alphas) and sum(part.alphas[i] for i in t) / 3 >= threshold]
    return part
