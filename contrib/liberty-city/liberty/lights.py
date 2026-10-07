"""GTA IV light attributes (.light, beside a model's mesh in OpenIV's export).

`Version 1 10` then one `Attribute i { ... }` block per light, in model space:
Position, Direction (a spot's axis), Color (0-255 RGB), _f28 (intensity, 100 for
most), Range (falloff distance in metres), HotSpot/Falloff (a spot's inner and
outer cone angles in degrees), Type (Omni or Spot) and BoneID (the .skel bone Id
a fragment's light hangs from, 0 for none).
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import mesh


@dataclass
class Light:
    position: tuple[float, float, float]
    direction: tuple[float, float, float]
    color: tuple[float, float, float]  # 0..1
    intensity: float
    range: float
    hotspot: float  # degrees
    falloff: float  # degrees
    spot: bool
    bone_id: int


def parse(text: str) -> list[Light]:
    lights, fields = [], None
    for raw in text.splitlines():
        tokens = raw.split()
        if not tokens:
            continue
        if tokens[0] == "Attribute":
            fields = {}
            continue
        if fields is None:
            continue
        if tokens[0] == "}" and "Type" in fields:
            def vec(name, n=3):
                return tuple(float(v) for v in fields.get(name, ["0"] * n)[:n])
            r, g, b = (float(v) / 255.0 for v in fields.get("Color", ["255"] * 3)[:3])
            lights.append(Light(
                position=vec("Position"), direction=vec("Direction"), color=(r, g, b),
                intensity=float(fields.get("_f28", ["100"])[0]),
                range=float(fields.get("Range", ["10"])[0]),
                hotspot=float(fields.get("HotSpot", ["0"])[0]),
                falloff=float(fields.get("Falloff", ["0"])[0]),
                spot=fields["Type"][0].lower() == "spot",
                bone_id=int(float(fields.get("BoneID", ["0"])[0]))))
            fields = None
            continue
        fields[tokens[0]] = tokens[1:]
    return lights


def read_for_model(model_path: Path) -> list[Light]:
    """The lights of the .odr or .oft at model_path, moved from their bone into
    model space when they hang off a fragment bone. Empty when it has none."""
    model_path = Path(model_path)
    folder = model_path.parent / model_path.stem
    files = list(folder.glob("*.light"))
    if not files:
        return []
    lights = parse(files[0].read_text(encoding="latin-1"))
    if any(light.bone_id for light in lights):
        skels = list(folder.glob("*.skel"))
        bones = mesh.parse_skel(skels[0].read_text(encoding="latin-1"), key_by="id") if skels else {}
        for light in lights:
            if light.bone_id in bones:
                offset, rotation = bones[light.bone_id]
                light.position = tuple(o + r for o, r in zip(offset, mesh._rotate(rotation, light.position)))
                light.direction = mesh._rotate(rotation, light.direction)
    return lights
