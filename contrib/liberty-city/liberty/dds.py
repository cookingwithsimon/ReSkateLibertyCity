"""Just enough of a .dds header and DXT1 blocks to tell whether a texture has any
transparency."""
from __future__ import annotations

import struct
from pathlib import Path


def is_opaque(path: Path) -> bool:
    """True for a DXT1 texture none of whose 4x4 blocks uses the transparent
    colour; DXT3/DXT5 and other formats carry real alpha and count as not opaque."""
    data = Path(path).read_bytes()
    if len(data) < 128 or data[84:88] != b"DXT1":
        return False
    height, width = struct.unpack_from("<II", data, 12)
    blocks = max(1, width // 4) * max(1, height // 4)  # the top mip level only
    for i in range(blocks):
        offset = 128 + i * 8
        if offset + 8 > len(data):
            break
        c0, c1, bits = struct.unpack_from("<HHI", data, offset)
        if c0 <= c1 and any((bits >> (2 * k)) & 3 == 3 for k in range(16)):
            return False
    return True
