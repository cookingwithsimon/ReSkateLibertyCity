"""Where an area's triangles go, to see what is worth cutting.

    python -m liberty.tri_report <export folder>... --area area.json [--top 40] [--lean] [-o report.json]

Counts each placed model's full-detail triangles (as build_area builds them)
times its placements, split by: inside the box or edge shell, solid (collides)
or detail (drawn only), shader, export folder, and model. Small models are
grouped by size so many tiny props show up as one line. --lean counts what
build_area --lean would build. No Blender needed.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from . import lean as oflean, mesh, surfaces

SIZE_BINS = (1, 2, 5, 10, 20, 50, 1e9)  # metres: the model's largest extent


def _models(folders):
    found = {p.stem.lower(): p for f in folders for p in Path(f).rglob("*.oft")}
    found.update({p.stem.lower(): p for f in folders for p in Path(f).rglob("*.odr")})
    return found


def _measure(path: Path, med: bool = False) -> dict:
    """Triangles per shader, split solid/detail, and the model's size."""
    read = mesh.read_fragment if path.suffix.lower() == ".oft" else mesh.read_model
    drawable, parts = read(path, med)
    out = {"solid": 0, "detail": 0, "shaders": Counter(), "size": 0.0}
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for part in parts:
        if part.material >= len(drawable.shaders):
            continue
        shader = drawable.shaders[part.material]
        if "decal" in shader.name:
            mesh.drop_faded(part)
        tris = sum(1 for t in part.triangles if max(t) < len(part.positions) and len(set(t)) == 3)
        # Cutout parts with an opaque texture also collide in build_area; that needs the
        # .dds, so they count as detail here.
        kind = "solid" if surfaces.is_solid(shader.name, shader.diffuse) else "detail"
        out[kind] += tris
        out["shaders"][shader.name] += tris
        for v in part.positions:
            for i in range(3):
                lo[i], hi[i] = min(lo[i], v[i]), max(hi[i], v[i])
    if lo[0] != math.inf:
        out["size"] = max(h - l for h, l in zip(hi, lo))
    return out


def report(folders, area: dict, top: int = 40, lean: bool = False) -> dict:
    files = _models(folders)
    measured: dict[str, dict] = {}
    by = defaultdict(Counter)
    per_model = Counter()
    uses = Counter()
    for p in area["placements"]:
        key = p["model"].lower()
        if key not in files:
            by["missing"][p["model"]] += 1
            continue
        if key not in measured:
            measured[key] = _measure(files[key], lean and oflean.wants_med(files[key], p["model"]))
        m = measured[key]
        edge = bool(p.get("edge"))
        if edge and not m["solid"]:
            continue  # build_area drops edge placements with nothing solid
        if edge and lean and not oflean.keep_edge(m["size"]):
            continue
        solid, detail = m["solid"], 0 if edge else m["detail"]
        total = solid + detail
        place = "edge" if edge else "inside"
        by["place"][place] += total
        by["kind"]["solid"] += solid
        by["kind"]["detail"] += detail
        by["source"][p.get("source", "?")] += total
        folder = next((str(f) for f in folders if Path(files[key]).is_relative_to(f)), "?")
        by["export folder"][folder] += total
        size_bin = next(b for b in SIZE_BINS if m["size"] <= b)
        by["model size (m, up to)"][str(size_bin if size_bin < 1e9 else "larger")] += total
        scale = 1.0 if not edge else (solid / max(solid + m["detail"], 1))
        for shader, n in m["shaders"].items():
            by["shader"][shader] += n * scale
        per_model[p["model"]] += total
        uses[p["model"]] += 1
    grand = sum(by["place"].values())
    tops = [{"model": name, "triangles": n, "placements": uses[name],
             "each": n // max(uses[name], 1), "size_m": round(measured[name.lower()]["size"], 1)}
            for name, n in per_model.most_common(top)]
    return {
        "triangles": grand,
        "breakdown": {k: dict(sorted(((n, round(v)) for n, v in c.items()), key=lambda kv: -kv[1])[:top])
                      for k, c in by.items()},
        "top_models": tops,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", type=Path, nargs="+")
    ap.add_argument("--area", type=Path, required=True)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument("--lean", action="store_true", help="count what build_area --lean builds")
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args(argv)
    result = report(args.folders, json.loads(args.area.read_text()), args.top, args.lean)
    text = json.dumps(result, indent=1)
    if args.output:
        args.output.write_text(text)
    sys.stdout.write(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
