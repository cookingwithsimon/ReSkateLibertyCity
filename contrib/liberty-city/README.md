# Liberty City converter

Turns GTA IV map data exported from your own copy of the game into a Blender scene that ReSkate Studio
compiles into a custom map. Personal use only: Liberty City belongs to Rockstar, so never commit or
share game files or the built map.

Pipeline: OpenIV export → `select_area` (placements in a box) → Blender scene with Studio's settings
→ `reskate_cli compile-map`.
(next) → `reskate_cli compile-map`.

```sh
python -m liberty.select_area <export folder> [<props export>...] --box minX minY maxX maxY -o area.json
python -m liberty.tri_report <export folder>... --area area.json -o tris.json   # where the triangles go
python -m unittest discover -s tests
```

The export folder holds the `.wpl` (binary, as extracted) and `.ide` files of the area's map archives.

## Test map

Proves the Studio chain before any GTA IV data: a 40 x 40 m plaza with a ledge, a box, three stairs
and a grindable handrail.

```bat
blender --background --factory-startup --python make_test_map.py -- liberty_test.blend
reskate_cli compile-map "E:\SteamLibrary\steamapps\common\Skate" liberty_test.blend staging --deploy --mod-folder LibertyTest
```
