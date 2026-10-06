import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from liberty import mesh, opl, select_area, surfaces  # noqa: E402


class Opl(unittest.TestCase):
    def test_inst_only(self):
        rows = opl.parse(fixtures.OPL)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[1].model, "Test_Slab")
        self.assertEqual(rows[1].rotation, (0.0, 0.0, 0.7071068, 0.7071068))
        self.assertEqual(rows[1].lod_index, 2)


class Odr(unittest.TestCase):
    def test_shaders_and_mesh(self):
        d = mesh.parse_odr(fixtures.ODR)
        self.assertEqual([s.name for s in d.shaders], ["gta_normal", "gta_decal"])
        self.assertEqual(d.shaders[0].textures, ["test_slab\\test_pavement.dds", "test_slab\\test_pavement_n.dds"])
        self.assertEqual(d.shaders[1].diffuse, "test_crack")
        self.assertEqual(d.high_mesh, "test_slab\\test_slab_high.mesh")

    def test_mesh(self):
        parts = mesh.parse_mesh(fixtures.MESH)
        self.assertEqual([p.material for p in parts], [0, 1])
        self.assertEqual(parts[0].triangles, [(0, 1, 2), (0, 2, 3)])
        self.assertEqual(parts[0].positions[1], (2.0, -2.0, 0.0))
        self.assertEqual(parts[0].uvs[0], (0.0, 0.0))  # V flipped from 1
        self.assertEqual(parts[1].positions[0][2], 0.002)


class Surfaces(unittest.TestCase):
    def test_rules(self):
        self.assertFalse(surfaces.is_solid("gta_decal"))
        self.assertTrue(surfaces.is_solid("gta_normal_spec"))
        self.assertEqual(surfaces.surface_for("02ground_mh8\\dc_pavement_plainsmall01.dds"), "concrete")
        self.assertEqual(surfaces.surface_for("nj_road_tarmac01"), "asphalt")
        self.assertEqual(surfaces.surface_for("dc_curb_metalsmall02.dds"), "metal")


class SelectFromOpl(unittest.TestCase):
    def test_area(self):
        with tempfile.TemporaryDirectory() as d:
            out = select_area.select(fixtures.write(Path(d)), (0, 10, 30, 30))
        models = [p["model"] for p in out["placements"]]
        # lod_test_slab is a LOD model; 500,500 is outside.
        self.assertEqual(models, ["test_slab", "test_slab", "test_prop"])
        self.assertEqual(out["skipped"], {"lod model": 1})
        self.assertEqual(out["placements"][0]["position"], [-5.0, 0.0, 1.0])


if __name__ == "__main__":
    unittest.main()
