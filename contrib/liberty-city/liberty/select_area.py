"""Lists the placements inside a box, resolved to model names.

    python -m liberty.select_area <export folder>... --box minX minY maxX maxY [-o area.json]

Reads every placement file under the folder: OpenIV's text .opl, or binary .wpl
as extracted. Models named as low-detail stand-ins (lod*, slod*) are left out:
the converter wants the full-detail city. Models no .ide in the folder defines
are listed by name, so you know which other archives to export. Positions are recentred on the box's
centre, so the map sits near the origin.

Night-window overlays (NL_*, NW_*) are left out: they only light up at night and
often belong to buildings outside the box. Placements up to --margin metres past
the box are included marked "edge", so build_area can keep the building shells
there (whose fire escapes and windows sit inside the box) and drop the rest.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from . import ide, opl, wpl
from .hashing import model_hash

NIGHT_OVERLAYS = ("nl_", "nw_")


def _files(folders, pattern):
    return sorted(p for f in folders for p in Path(f).rglob(pattern))


def _placements(folders):
    """(file name, [(position, rotation, model hash, lod index, name or None)])."""
    for path in _files(folders, "*.opl"):
        yield path.name, [(p.position, p.rotation, model_hash(p.model), p.lod_index, p.model) for p in opl.read(path)]
    for path in _files(folders, "*.wpl"):
        yield path.name, [(i.position, i.rotation, i.model_hash, i.lod_index, None) for i in wpl.read(path)]


def select(folders, box: tuple[float, float, float, float], lod_parents: bool = False, margin: float = 0.0):
    """`lod_parents` also drops placements another one in the same file names
    as its LOD parent. Off by default: in OpenIV's split stream files the LOD
    index points into another file, so it would drop real buildings."""
    folders = [folders] if isinstance(folders, (str, Path)) else list(folders)
    models = ide.read_all(_files(folders, "*.ide"))
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    placed, unknown, skipped = [], set(), Counter()
    for name, instances in _placements(folders):
        parents = {inst[3] for inst in instances if 0 <= inst[3] < len(instances)} if lod_parents else set()
        for index, (position, rotation, h, _, label) in enumerate(instances):
            x, y, z = position
            if not (x0 - margin <= x <= x1 + margin and y0 - margin <= y <= y1 + margin):
                continue
            edge = not (x0 <= x <= x1 and y0 <= y <= y1)
            if index in parents:
                skipped["lod parent"] += 1
                continue
            model = models.get(h)
            if model is None:
                unknown.add(label or f"{h:08x}")
                skipped["unknown model"] += 1
                continue
            if model.is_lod:
                skipped["lod model"] += 1
                continue
            if model.name.lower().startswith(NIGHT_OVERLAYS):
                skipped["night windows"] += 1
                continue
            placed.append({
                "model": model.name, "txd": model.txd, "source": name,
                "position": [x - cx, y - cy, z], "rotation": list(rotation), "edge": edge,
            })
    return {"centre": [cx, cy], "box": list(box), "placements": placed, "skipped": dict(skipped),
            "unknown_models": sorted(unknown, key=str.lower)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folders", type=Path, nargs="+", help="export folders, e.g. the map area and its prop archives")
    ap.add_argument("--box", type=float, nargs=4, required=True, metavar=("MINX", "MINY", "MAXX", "MAXY"))
    ap.add_argument("-o", "--output", type=Path)
    ap.add_argument("--lod-parents", action="store_true", help="also drop same-file LOD parents")
    ap.add_argument("--margin", type=float, default=60.0, help="metres past the box to look for building shells")
    args = ap.parse_args(argv)
    result = select(args.folders, tuple(args.box), args.lod_parents, args.margin)
    text = json.dumps(result, indent=1)
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text + "\n")
    print(f"{len(result['placements'])} placements, skipped {result['skipped']}, "
          f"{len(result['unknown_models'])} unknown models", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
