"""OpenIV's text models: .odr (shaders + LOD list) and .mesh (geometry).

.odr: `shadinggroup { Shaders n { <shader>.sps <texture> [params...] } }` then a
`lodgroup` whose `high <count> <path.mesh> <index> <distance>` names the mesh.
.mesh ("Version 11 13"): `Mtl i { Prim 0 { Idx n {...} Verts m {...} } }`, where
Mtl i is the i-th shader. Idx is a triangle list local to its Verts. A vertex
line is ten " / "-separated groups: position, normal, colour RGBA, tangent,
then six UV sets; only UV0 is used.
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
