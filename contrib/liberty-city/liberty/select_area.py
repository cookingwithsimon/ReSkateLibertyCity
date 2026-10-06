"""Lists the placements inside a box, resolved to model names.

    python -m liberty.select_area <export folder> --box minX minY maxX maxY [-o area.json]

Reads every placement file under the folder: OpenIV's text .opl, or binary .wpl
as extracted. Models the .ide files mark as low-detail stand-ins, and placements
another one in the same file names as its LOD parent, are left out: the
converter wants the full-detail city. Positions are recentred on the box's
centre, so the map sits near the origin.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ide, opl, wpl
from .hashing import model_hash


def _placements(folder: Path):
    """(file name, [(position, rotation, model hash, lod index)])."""
    for path in sorted(folder.rglob("*.opl")):
        yield path.name, [(p.position, p.rotation, model_hash(p.model), p.lod_index) for p in opl.read(path)]
    for path in sorted(folder.rglob("*.wpl")):
        yield path.name, [(i.position, i.rotation, i.model_hash, i.lod_index) for i in wpl.read(path)]


def select(folder: Path, box: tuple[float, float, float, float]):
    models = ide.read_all(sorted(folder.rglob("*.ide")))
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    placed, unknown = [], set()
    for name, instances in _placements(folder):
        parents = {lod for *_, lod in instances if 0 <= lod < len(instances)}
        for index, (position, rotation, h, _) in enumerate(instances):
            x, y, z = position
            if not (x0 <= x <= x1 and y0 <= y <= y1) or index in parents:
                continue
            model = models.get(h)
            if model is None:
                unknown.add(h)
                continue
            if model.is_lod:
                continue
            placed.append({
                "model": model.name, "txd": model.txd, "source": name,
                "position": [x - cx, y - cy, z], "rotation": list(rotation),
            })
    return {"centre": [cx, cy], "box": list(box), "placements": placed,
            "unknown_hashes": sorted(f"{h:08x}" for h in unknown)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("folder", type=Path)
    ap.add_argument("--box", type=float, nargs=4, required=True, metavar=("MINX", "MINY", "MAXX", "MAXY"))
    ap.add_argument("-o", "--output", type=Path)
    args = ap.parse_args(argv)
    result = select(args.folder, tuple(args.box))
    text = json.dumps(result, indent=1)
    if args.output:
        args.output.write_text(text)
    else:
        sys.stdout.write(text + "\n")
    print(f"{len(result['placements'])} placements, {len(result['unknown_hashes'])} unknown models", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
