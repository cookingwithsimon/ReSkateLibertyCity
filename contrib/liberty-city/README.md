# Liberty City converter

Turns GTA IV map data exported from your own copy of the game into a Blender scene that ReSkate Studio
compiles into a custom map. Personal use only: Liberty City belongs to Rockstar, so never commit or
share game files or the built map.

Pipeline: OpenIV export → `select_area` (placements in a box) → Blender scene with Studio's settings
(next) → `reskate_cli compile-map`.

```sh
python -m liberty.select_area <export folder> --box minX minY maxX maxY -o area.json
python -m unittest discover -s tests
```

The export folder holds the `.wpl` (binary, as extracted) and `.ide` files of the area's map archives.
