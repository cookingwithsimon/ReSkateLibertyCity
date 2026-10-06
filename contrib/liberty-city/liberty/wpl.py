"""Binary GTA IV placement files (.wpl): https://gtamods.com/wiki/WPL

A 68-byte header of 17 uint32s (version 3, then a count per section), then each
section's records in order. Only INST (section 0, 48 bytes each) matters here.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

HEADER = struct.Struct("<17I")
INST = struct.Struct("<7f2IiIf")
# Record sizes for sections 0..15; the unused ones are always empty.
RECORD_SIZES = (48, 0, 48, 56, 56, 0, 0, 0, 64, 388, 24, 0, 0, 0, 0, 132)


@dataclass(frozen=True)
class Instance:
    position: tuple[float, float, float]
    rotation: tuple[float, float, float, float]  # x, y, z, w as stored
    model_hash: int
    flags: int
    lod_index: int  # index of this instance's LOD parent in the same file, -1 for none


def parse(data: bytes) -> list[Instance]:
    if len(data) < HEADER.size:
        raise ValueError("WPL is shorter than its header")
    version, *counts = HEADER.unpack_from(data)
    if version != 3:
        raise ValueError(f"unsupported WPL version {version}")
    needed = HEADER.size + sum(n * s for n, s in zip(counts, RECORD_SIZES))
    if needed > len(data):
        raise ValueError(f"WPL declares {needed} bytes but has {len(data)}")
    out = []
    for i in range(counts[0]):
        x, y, z, rx, ry, rz, rw, h, flags, lod, _, _ = INST.unpack_from(data, HEADER.size + i * INST.size)
        out.append(Instance((x, y, z), (rx, ry, rz, rw), h, flags, lod))
    return out


def read(path: Path) -> list[Instance]:
    return parse(Path(path).read_bytes())
