import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from liberty import ide, select_area, wpl  # noqa: E402
from liberty.hashing import model_hash  # noqa: E402


def make_wpl(instances):
    counts = [len(instances)] + [0] * 15
    body = b"".join(struct.pack("<7f2IiIf", *pos, *rot, h, 0, lod, 0, 0.0) for pos, rot, h, lod in instances)
    return struct.pack("<17I", 3, *counts) + body


IDE = """# test
objs
bm_block01, bm_txd, 150, 0, 0, -10, -10, 0, 10, 10, 20
lod_block01, bm_txd, 1500, 0, 0
end
tobj
end
"""


class Hashing(unittest.TestCase):
    def test_known_value(self):
        # One-at-a-time of "a" (lowercased input).
        self.assertEqual(model_hash("A"), model_hash("a"))
        self.assertEqual(model_hash("a"), 0xCA2E9442)


class Wpl(unittest.TestCase):
    def test_round_trip(self):
        data = make_wpl([((1, 2, 3), (0, 0, 0, 1), 0xDEADBEEF, -1)])
        [inst] = wpl.parse(data)
        self.assertEqual(inst.position, (1.0, 2.0, 3.0))
        self.assertEqual(inst.model_hash, 0xDEADBEEF)
        self.assertEqual(inst.lod_index, -1)

    def test_tcyc_records_are_44_bytes(self):
        counts = [0, 0, 0, 0, 2] + [0] * 11
        data = struct.pack("<17I", 3, *counts) + bytes(88)
        self.assertEqual(wpl.parse(data), [])

    def test_truncated(self):
        with self.assertRaises(ValueError):
            wpl.parse(make_wpl([((0, 0, 0), (0, 0, 0, 1), 1, -1)])[:-4])


class Ide(unittest.TestCase):
    def test_objs(self):
        models = ide.parse(IDE)
        self.assertEqual([m.name for m in models], ["bm_block01", "lod_block01"])
        self.assertFalse(models[0].is_lod)
        self.assertTrue(models[1].is_lod)

    def test_anim_rows_skip_the_animation_dictionary(self):
        models = ide.parse("anim\nTS_ATower_DC9, TS_Building05c_DC9, manhat09, 100, 1536, 0, -37.7, -28.6\nend\n")
        self.assertEqual(len(models), 1)
        self.assertEqual((models[0].name, models[0].txd, models[0].draw_distance, models[0].flags),
                         ("TS_ATower_DC9", "TS_Building05c_DC9", 100.0, 1536))

    def test_lod_names(self):
        def named(n):
            return ide.ModelDef(n, "t", 100, 0)
        for n in ("SuperLOD02", "Tree_LOD_03_MH7", "DM_ScafLOD05_MH7", "LOD_Tudor_03_MH7"):
            self.assertTrue(named(n).is_lod, n)
        for n in ("explode_01_MH12", "CC_AptBase_MH7"):
            self.assertFalse(named(n).is_lod, n)


class SelectArea(unittest.TestCase):
    def test_box_lod_and_recentre(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "t.ide").write_text(IDE)
            (d / "t.wpl").write_bytes(make_wpl([
                ((105, 205, 5), (0, 0, 0, 1), model_hash("bm_block01"), 1),  # kept, points at LOD
                ((105, 205, 5), (0, 0, 0, 1), model_hash("lod_block01"), -1),  # LOD parent
                ((900, 900, 0), (0, 0, 0, 1), model_hash("bm_block01"), -1),  # outside
                ((110, 210, 0), (0, 0, 0, 1), 0x1234, -1),  # unknown model
            ]))
            out = select_area.select(d, (100, 200, 120, 220), lod_parents=True)
        self.assertEqual([p["model"] for p in out["placements"]], ["bm_block01"])
        self.assertEqual(out["placements"][0]["position"], [-5.0, -5.0, 5.0])
        self.assertEqual(out["unknown_models"], ["00001234"])


if __name__ == "__main__":
    unittest.main()
