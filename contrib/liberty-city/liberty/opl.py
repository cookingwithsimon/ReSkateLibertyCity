"""OpenIV's text placements (.opl), written for each binary .wpl.

The `inst` section holds one placement per line, the WPL INST record as text:
`x, y, z, qx, qy, qz, qw, ModelName, flags, lodIndex, unknown, unknown`.
Models are named, not hashed. Other sections (cars, mlop...) are ignored.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Placement:
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]  # x, y, z, w as stored
    model: str
    flags: int
    lod_index: int


def parse(text: str) -> list[Placement]:
    out, section = [], None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("version"):
            continue
        if section is None:
            section = line.lower()
            continue
        if line.lower() == "end":
            section = None
            continue
        if section != "inst":
            continue
        cols = [c.strip() for c in line.split(",")]
        if len(cols) < 10:
            continue
        try:
            nums = [float(c) for c in cols[:7]]
            out.append(Placement(tuple(nums[:3]), tuple(nums[3:7]), cols[7], int(float(cols[8])), int(float(cols[9]))))
        except ValueError:
            continue
    return out


def read(path: Path) -> list[Placement]:
    return parse(Path(path).read_text(encoding="latin-1"))
