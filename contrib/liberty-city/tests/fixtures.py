"""A tiny made-up export in OpenIV's formats (no game data): one 4 x 4 m slab
with a decal on top, placed twice, plus a placement of a model with no .odr."""
from pathlib import Path

IDE = """objs
test_slab, test_txd, 150, 0, 0, -2, -2, 0, 2, 2, 0.1, 0, 0, 0, 3, null
lod_test_slab, test_txd, 1500, 0, 0, -2, -2, 0, 2, 2, 0.1, 0, 0, 0, 3, null
test_prop, test_txd, 60, 0, 0, -1, -1, 0, 1, 1, 1, 0, 0, 0, 1, null
end
"""

OPL = """# GTA IV Binary Placement File
version 3
inst
10, 20, 1, 0, 0, 0, 1, test_slab, 384, -1, 0, -1
14, 20, 1, 0, 0, 0.7071068, 0.7071068, Test_Slab, 384, 2, 0, -1
14, 20, 1, 0, 0, 0, 1, lod_test_slab, 384, -1, 0, -1
11, 21, 1, 0, 0, 0, 1, test_prop, 384, -1, 0, -1
500, 500, 1, 0, 0, 0, 1, test_slab, 384, -1, 0, -1
end
cars
1, 2, 3, 7, 0, 3, hash:0, -1, -1, -1, -1, 1888, 0, 0
end
"""

ODR = """Version 110 12
shadinggroup
{
\tShaders 2
\t{
\t\tgta_normal.sps test_slab\\test_pavement.dds 30.00000000 0.01000000 1.00000000 test_slab\\test_pavement_n.dds
\t\tgta_decal.sps test_crack 1.00000000;0.00000000;0.00000000
\t}
}
lodgroup
{
\thigh 1 test_slab\\test_slab_high.mesh 0 9999.00000000
\tmed none 9999.00000000
\tlow none 9999.00000000
\tvlow none 9999.00000000
}
"""


def _vert(x, y, z, u, v):
    return (f"{x} {y} {z} / 0.0 0.0 1.0 / 128 128 128 255 / 0.0 0.0 0.0 0.0 / {u} {v}"
            + " / 0.0 0.0" * 5)


def _quad(z):
    return "\n".join(_vert(x, y, z, u, v) for x, y, u, v in ((-2, -2, 0, 1), (2, -2, 1, 1), (2, 2, 1, 0), (-2, 2, 0, 0)))


MESH = f"""Version 11 13
{{
\tSkinned 0
\tBounds 1
\t{{
\t\t0 0 0 3
\t}}
\tMtl 0
\t{{
\t\tPrim 0
\t\t{{
\t\t\tIdx 6
\t\t\t{{
\t\t\t\t0 1 2 0 2 3
\t\t\t}}
\t\t\tVerts 4
\t\t\t{{
{_quad(0.0)}
\t\t\t}}
\t\t}}
\t}}
\tMtl 1
\t{{
\t\tPrim 0
\t\t{{
\t\t\tIdx 6
\t\t\t{{
\t\t\t\t0 1 2 0 2 3
\t\t\t}}
\t\t\tVerts 4
\t\t\t{{
{_quad(0.002)}
\t\t\t}}
\t\t}}
\t}}
}}
"""


def write(root: Path) -> Path:
    (root / "test_slab").mkdir(parents=True)
    (root / "test.ide").write_text(IDE)
    (root / "test_stream0.opl").write_text(OPL)
    (root / "test_slab.odr").write_text(ODR)
    (root / "test_slab" / "test_slab_high.mesh").write_text(MESH)
    return root


OFT = """Version 112 2
fragments
{
\tgroup test_lamp
\t\tchild test_lamp\\base_0.child null
\t\t\tchild test_lamp\\arm_1.child null
}
drawable
{
\tshadinggroup
\t\tShaders 2
\t\t\tgta_spec.sps test_metal 50.00000000 0.40000000 1.00000000;0.00000000;0.00000000 test_metal_s
\t\t\tgta_emissivenight.sps test_bulb 0.00040000 35.00000000
\tskel
\tlodgroup
\t\thigh none 0.00000000
}
"""

SKEL = """Version 107 11
NumBones 2
bone test_lamp {
\tIndex 0
\tLocalOffset 0.0 0.0 0.0
\tRotationQuaternion 0.0 0.0 0.0 1.0
\tChildren 1
\t{
\t\tbone arm
\t\t{
\t\t\tIndex 1
\t\t\tLocalOffset 0.0 0.0 3.0
\t\t\tRotationQuaternion 0.0 0.0 0.7071068 0.7071068
\t\t}
\t}
}
"""


def _child(name, bone):
    return f"""Version 112 2
drawable
{{
\tlodgroup
\t{{
\t\thigh 1 {name}\\{name}_high.mesh {bone} 9999.00000000
\t\tmed none 9999.00000000
\t}}
}}
"""


def write_fragment(root: Path) -> Path:
    folder = root / "test_lamp"
    for name, bone in (("base_0", 0), ("arm_1", 1)):
        (folder / name).mkdir(parents=True)
        (folder / f"{name}.child").write_text(_child(name, bone))
        (folder / name / f"{name}_high.mesh").write_text(MESH)
    (folder / "test_lamp.skel").write_text(SKEL)
    (root / "test_lamp.oft").write_text(OFT)
    return root / "test_lamp.oft"
