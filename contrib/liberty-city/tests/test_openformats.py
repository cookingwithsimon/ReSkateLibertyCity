import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import fixtures  # noqa: E402
from liberty import lean, mesh, opl, select_area, surfaces, tri_report  # noqa: E402


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
        self.assertEqual(parts[0].alphas[0], 1.0)

    def test_drop_faded(self):
        part = mesh.Part(0, positions=[(0, 0, 0)] * 4, alphas=[1.0, 1.0, 0.0, 0.0],
                         triangles=[(0, 1, 2), (0, 2, 3)])
        self.assertEqual(mesh.drop_faded(part).triangles, [(0, 1, 2)])


class Fragment(unittest.TestCase):
    def test_children_moved_by_bone(self):
        with tempfile.TemporaryDirectory() as tmp:
            drawable, parts = mesh.read_fragment(fixtures.write_fragment(Path(tmp)))
        self.assertEqual([s.name for s in drawable.shaders], ["gta_spec", "gta_emissivenight"])
        self.assertEqual(len(parts), 4)  # two Mtl blocks per child
        self.assertEqual(parts[0].positions[1], (2.0, -2.0, 0.0))  # bone 0 is identity
        x, y, z = parts[2].positions[1]  # (2, -2, 0) turned 90 degrees about Z, raised 3 m
        self.assertAlmostEqual(x, 2.0, 5)
        self.assertAlmostEqual(y, 2.0, 5)
        self.assertAlmostEqual(z, 3.0, 5)


class Surfaces(unittest.TestCase):
    def test_rules(self):
        self.assertFalse(surfaces.is_solid("gta_decal"))
        self.assertTrue(surfaces.is_solid("gta_normal_spec"))
        self.assertTrue(surfaces.is_solid("gta_normal_spec_reflect_emissivenight"))
        self.assertFalse(surfaces.is_solid("gta_normal_reflect_alpha"))

    def test_cutout_railings_collide_but_foliage_does_not(self):
        self.assertTrue(surfaces.is_solid("gta_cutout", r"x\rustedmtl_rail01sl_rustedmtl_rail01a.dds"))
        self.assertTrue(surfaces.is_solid("gta_cutout", "pris_fence2pris_fence2b"))
        self.assertFalse(surfaces.is_solid("gta_cutout", "ag_liveoak_leafag_liveoak_leaf_alpha"))
        self.assertFalse(surfaces.is_solid("gta_alpha", "cistillwglascistillwglas_a"))
        self.assertFalse(surfaces.is_solid("gta_decal", "rail_decal"))

    def test_opaque_alpha_parts_are_solid_unless_overlays(self):
        self.assertTrue(surfaces.opaque_alpha_is_solid("gta_alpha", "cj_green_grenade2"))
        self.assertFalse(surfaces.opaque_alpha_is_solid("gta_emissivenight_alpha", "sprunk01_c"))
        self.assertFalse(surfaces.opaque_alpha_is_solid("gta_alpha", "darkbrownmud256"))
        self.assertFalse(surfaces.opaque_alpha_is_solid("gta_cutout", "ec_barbwire2"))
        self.assertFalse(surfaces.opaque_alpha_is_solid("gta_normal_spec", "anything"))
        self.assertEqual(surfaces.surface_for("cj_green_grenade2"), "metal_rail_round")

    def test_emissive_signs_and_lamps(self):
        from liberty import emissive
        self.assertTrue(emissive.is_sign("gta_emissive", "dc_sprunkad1.dds"))
        self.assertFalse(emissive.is_sign("gta_emissivenight_alpha", "dm_nightemissive01dm_nightemissive01_a"))
        self.assertFalse(emissive.is_sign("gta_normal_spec", "dc_sprunkad1.dds"))
        self.assertTrue(emissive.is_sign("gta_default", "ts_billboard_mh7.dds"))
        self.assertTrue(emissive.is_sign("gta_spec", "cj_poster_4cj_poster_4_a"))
        self.assertTrue(emissive.is_lamp("gta_emissive", "Bx_ellamp_bulb_w"))
        # Two 1 m letters 2 m apart facing the same way merge into one panel.
        quad = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)]
        positions = quad + [(x + 2, y, z) for x, y, z in quad]
        found = emissive.islands(positions, [(0, 1, 2), (0, 2, 3), (4, 5, 6), (4, 6, 7)])
        self.assertEqual(len(found), 2)
        [panel] = emissive.merge(found)
        self.assertAlmostEqual(panel.area, 2.0)
        self.assertAlmostEqual(panel.width, 3.0)

    def test_rails_grind_as_smooth_metal_rail(self):
        self.assertEqual(surfaces.surface_for(r"x\sl_rustedmtl_rail01sl_rustedmtl_rail01a.dds"), "metal_rail_round")
        self.assertEqual(surfaces.surface_for("sl_tainohandrail_01"), "metal_rail_round")
        self.assertEqual(surfaces.surface_for("pris_fence2pris_fence2b"), "concrete")
        self.assertEqual(surfaces.surface_for("bm_grillbm_grill_a"), "metal")
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

    def test_margin_marks_edge(self):
        with tempfile.TemporaryDirectory() as d:
            out = select_area.select(fixtures.write(Path(d)), (0, 10, 12, 30), margin=5)
        self.assertEqual([(p["model"], p["edge"]) for p in out["placements"]],
                         [("test_slab", False), ("test_slab", True), ("test_prop", False)])


class TriReport(unittest.TestCase):
    def test_counts_inside_and_edge(self):
        with tempfile.TemporaryDirectory() as d:
            root = fixtures.write(Path(d))
            inside = select_area.select(root, (0, 10, 30, 30))
            edge = select_area.select(root, (0, 10, 12, 30), margin=5)
            one = tri_report.report([root], inside)
            two = tri_report.report([root], edge)
        slab = one["top_models"][0]
        self.assertEqual((slab["model"], slab["placements"]), ("test_slab", 2))
        self.assertEqual(one["breakdown"]["missing"], {"test_prop": 1})
        self.assertEqual(one["triangles"], 2 * slab["each"])
        # The edge copy keeps its solid slab and loses the decal on top.
        self.assertLess(two["breakdown"]["place"]["edge"], slab["each"])
        self.assertEqual(two["breakdown"]["place"]["edge"], one["breakdown"]["kind"]["solid"] // 2)


class Lean(unittest.TestCase):
    def test_medium_mesh_when_asked_and_present(self):
        with tempfile.TemporaryDirectory() as d:
            root = fixtures.write(Path(d))
            odr = root / "test_slab.odr"
            high = mesh.read_model(odr)[1]
            self.assertEqual(len(mesh.read_model(odr, med=True)[1]), len(high))  # no med mesh: high
            (root / "test_slab" / "test_slab_med.mesh").write_text(fixtures.MESH.split("Mtl 1")[0] + "}\n")
            odr.write_text(fixtures.ODR.replace("med none 9999.00000000", "med 1 test_slab\\test_slab_med.mesh 0 60.0"))
            self.assertEqual(mesh.parse_odr(odr.read_text()).med_mesh, "test_slab\\test_slab_med.mesh")
            self.assertLess(len(mesh.read_model(odr, med=True)[1]), len(high))
            self.assertEqual(len(mesh.read_model(odr)[1]), len(high))

    def test_which_models(self):
        self.assertTrue(lean.use_med("W_Birch_MD_INGAME"))
        self.assertTrue(lean.use_med("CJ_aircon7"))
        self.assertTrue(lean.use_med("anything", ["gta_trees"]))
        for name in ("CJ_GB_bench_3", "CJ_FENCE_16_1", "BM_NYlamp1", "BM_streetlamp", "Fire_Esc_8b"):
            self.assertFalse(lean.use_med(name, ["gta_normal_spec"]), name)

    def test_edge_furniture_dropped(self):
        with tempfile.TemporaryDirectory() as d:
            root = fixtures.write(Path(d))
            edge = select_area.select(root, (0, 10, 12, 30), margin=5)
            full = tri_report.report([root], edge)
            leaner = tri_report.report([root], edge, lean=True)
        self.assertIn("edge", full["breakdown"]["place"])
        self.assertNotIn("edge", leaner["breakdown"]["place"])  # a 4 m slab is not a shell
        self.assertEqual(leaner["triangles"], full["breakdown"]["place"]["inside"])


if __name__ == "__main__":
    unittest.main()
