"""Light sources found in a model's emissive geometry, for models whose GTA IV
lighting is not in a .light: lamp bulbs and tubes (point lights) and large lit
billboards and screens (area lights in front of them).

An island is a connected group of triangles in one part; each gets its centre,
mean normal, area and in-plane extents in model space.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

LAMP_TEXTURES = ("bulb", "lamp", "tube", "neon_white", "ellamp", "flouro", "fluoro", "striplight")
# Lit window grids and night overlays are windows, not signs.
# Lit window grids, night overlays and interior ceilings are not signs: dm_nightemissive01
# alone covers whole tower faces (up to 2,400 m²) in Star Junction.
NOT_SIGNS = ("window", "win_", "nightwin", "emissive_windows", "wins", "glass", "bulb", "lamp", "tube",
             "nightemissive", "emissive_south", "nitelight", "nightlight", "ceilpanel", "ceiling", "inside")


@dataclass
class Island:
    centre: tuple[float, float, float]
    normal: tuple[float, float, float]
    area: float
    width: float  # extent along the plane's first axis
    height: float  # extent along its second axis
    right: tuple[float, float, float]
    up: tuple[float, float, float]
    count: int = 1  # islands merged into this one


def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a):
    n = math.sqrt(_dot(a, a))
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 1.0)


def islands(positions, triangles) -> list[Island]:
    parent = list(range(len(positions)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # Join by vertex index and by coincident position (parts are often split per corner).
    seen = {}
    for i, p in enumerate(positions):
        key = (round(p[0], 3), round(p[1], 3), round(p[2], 3))
        if key in seen:
            parent[find(i)] = find(seen[key])
        else:
            seen[key] = i
    for a, b, c in triangles:
        if max(a, b, c) < len(positions):
            parent[find(b)] = find(a)
            parent[find(c)] = find(a)
    groups: dict[int, list] = {}
    for tri in triangles:
        if max(tri) < len(positions):
            groups.setdefault(find(tri[0]), []).append(tri)
    out = []
    for tris in groups.values():
        area, centre, normal = 0.0, [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        for a, b, c in tris:
            pa, pb, pc = positions[a], positions[b], positions[c]
            n = _cross(_sub(pb, pa), _sub(pc, pa))
            da = 0.5 * math.sqrt(_dot(n, n))
            area += da
            for k in range(3):
                centre[k] += da * (pa[k] + pb[k] + pc[k]) / 3.0
                normal[k] += n[k]
        if area <= 1e-6:
            continue
        centre = tuple(v / area for v in centre)
        nrm = _norm(normal)
        helper = (0.0, 0.0, 1.0) if abs(nrm[2]) < 0.9 else (1.0, 0.0, 0.0)
        right = _norm(_cross(helper, nrm))
        up = _norm(_cross(nrm, right))
        verts = {i for t in tris for i in t}
        xs = [_dot(_sub(positions[i], centre), right) for i in verts]
        ys = [_dot(_sub(positions[i], centre), up) for i in verts]
        out.append(Island(centre, nrm, area, max(xs) - min(xs), max(ys) - min(ys), right, up))
    return out


def merge(found: list[Island], gap: float = 4.0, facing: float = 0.9) -> list[Island]:
    """Signs come in pieces (a neon sign is dozens of letter islands): join islands that
    face the same way and lie within `gap` metres of each other into one panel."""
    groups: list[list[Island]] = []
    for island in sorted(found, key=lambda i: -i.area):
        for group in groups:
            lead = group[0]
            if _dot(lead.normal, island.normal) >= facing and any(
                    math.dist(member.centre, island.centre) <= gap + (member.width + island.width) / 2
                    for member in group):
                group.append(island)
                break
        else:
            groups.append([island])
    out = []
    for group in groups:
        if len(group) == 1:
            out.append(group[0])
            continue
        lead = group[0]
        area = sum(i.area for i in group)
        centre = tuple(sum(i.centre[k] * i.area for i in group) / area for k in range(3))
        xs, ys = [], []
        for i in group:
            offset = _sub(i.centre, centre)
            x, y = _dot(offset, lead.right), _dot(offset, lead.up)
            xs += [x - i.width / 2, x + i.width / 2]
            ys += [y - i.height / 2, y + i.height / 2]
        out.append(Island(centre, lead.normal, area, max(xs) - min(xs), max(ys) - min(ys), lead.right, lead.up,
                          sum(i.count for i in group)))
    return out


def is_lamp(shader: str, texture: str | None) -> bool:
    name = (texture or "").lower().rsplit("\\", 1)[-1]
    return "emissive" in shader and any(w in name for w in LAMP_TEXTURES)


# Billboards and posters drawn with ordinary shaders: Studio has no emissive materials,
# so they only read at night with a light in front of them.
BILLBOARD_TEXTURES = ("billboard", "billb", "bilb", "bllbrd", "bilbrd", "poster", "advert", "hoarding")


def is_sign(shader: str, texture: str | None) -> bool:
    name = (texture or "").lower().rsplit("\\", 1)[-1]
    if not name or any(w in name for w in NOT_SIGNS):
        return False
    return "emissive" in shader or any(w in name for w in BILLBOARD_TEXTURES)
