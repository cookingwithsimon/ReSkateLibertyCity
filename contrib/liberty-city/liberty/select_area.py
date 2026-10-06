"""Lists the placements inside a box, resolved to model names.

    python -m liberty.select_area <export folder> --box minX minY maxX maxY [-o area.json]

Reads every .wpl and .ide under the folder. LOD instances (those another
instance points at as its LOD parent, and models the .ide marks as LOD) are
left out: the converter wants the full-detail city. Positions are recentred on
the box's centre, so the map sits near the origin.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import ide, wpl


def select(folder: Path, box: tuple[float, float, float, float]):
    models = ide.read_all(sorted(folder.rglob("*.ide")))
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    placed, unknown = [], set()
    for path in sorted(folder.rglob("*.wpl")):
        instances = wpl.read(path)
        parents = {i.lod_index for i in instances if i.lod_index >= 0}
        for index, inst in enumerate(instances):
            x, y, z = inst.position
            if not (x0 <= x <= x1 and y0 <= y <= y1) or index in parents:
                continue
            model = models.get(inst.model_hash)
            if model is None:
                unknown.add(inst.model_hash)
                continue
            if model.is_lod:
                continue
            placed.append({
                "model": model.name, "txd": model.txd, "source": path.name,
                "position": [x - cx, y - cy, z], "rotation": list(inst.rotation),
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
