# The anomaly maze: `maze_01` to `maze_07`

The hotel's seven anomaly maze rooms dressed and lit (`docs/BLENDER_AREAS.md`, section 1, step 2). They are separate scenes off the atrium, each
16 m by 16 m and 3 m high. The route is one way: atrium `maze` → maze_01 → … → maze_07 → atrium `maze_exit`, and the way on opens only once the
room's puzzle is solved. You come in from the atrium or through the elevator's glitch. The photo names (IMG_2988, 2989, 2990, 2910, 2986, 3015,
3036) are labels only; there are no photos, so every room is built from the written brief.

Each room has its own wrongness, built from the hotel's own materials (floor 1's carpet, wallcovering, wood doors, sconces and tiles, plus
the repo's CC0 textures), so it still reads as part of the building:

| Scene | Label | Its wrongness | Its night light |
|---|---|---|---|
| `maze_01` | IMG_2988 | **The corridor of small doors.** Floor 1's motel finish (maroon carpet, two-tone vinyl, chair rail). There is a door in every bay of every wall, each a little too small (0.70 by 1.78 m against the hotel's 0.94 by 2.16), every one numbered 101, with the peephole set too low. | Warm amber drum sconces over every other door (some dead), a motel at 3 a.m. |
| `maze_02` | IMG_2989 | **The dry pool.** White tile from floor to ceiling, a blue band where the water line would be, depth marks (1.2 M, 2.4 M, NO DIVING), black lane targets, steel grab rails and drains. There is no water. | Cold, even, cyan-white ceiling panels, one in every cell. |
| `maze_03` | IMG_2990 | **The wallpaper that repeats.** Floor 2's green carpet and an olive damask paper whose motif repeats every 12 cm (a hotel paper's repeats about every 50 cm). The same print hangs at the same height in every bay, each with a light switch beside it. | Sickly yellow-green ceiling domes, one dead. |
| `maze_04` | IMG_2910 | **The laundry of identical machines.** Built-in front-loaders, three across and two high in every bay: 588 machines, all the same one, all No. 7, each with the same red sock against the glass. | Cold blue-white fluorescent tubes, some dead. |
| `maze_05` | IMG_2986 | **The ballroom with no furniture.** Herringbone parquet, wainscot, gilt rails, tall mirrors and chandeliers, and nothing else. The only trace of the tables is the pale disc where each stood. In the middle room a ring of chair marks surrounds the puzzle spot. | Dim gold chandeliers and candle sconces. |
| `maze_06` | IMG_3015 | **The guest room in a loop.** One room's four walls (the bed wall with its headboard and lamps, the curtained window onto nothing, the door to 214, the TV wall) repeat in the same order round every turn of the maze. | Rose bedside lamps; the ceiling domes are mostly dead. |
| `maze_07` | IMG_3036 | **The stairs that end in a wall.** A stairwell's painted block, handrails along every wall, steel fire doors marked STAIRS L4 (every one of them), EXIT signs whose arrows disagree, and concrete flights hung upside down from the ceiling that climb into the wall. | Red emergency bulkheads; green EXIT signs. |

Every room also has a brass plaque with its number over the way on, and an EXIT sign above it.

This README covers all seven scenes. Each `docs/renders/maze_0k/` holds that room's three stills, its plan, `bake.json` and `caps.json`.

| File | What it is |
|---|---|
| `world/maze_0k.glb` | each room's art (sizes below) |
| `world/lightmaps/maze_0k_0.webp`, `_1.webp` | two lightmaps per room (second UV set): `_0` the shell, `_1` the props and the door leaf |
| `world/maze_0k.json` | the layout, re-written by `export_scene.py` from the dressed `.blend`: **the greybox's, unchanged** (git shows no change) |
| `blender/scenes/maze_0k.blend` | the saved rooms (Git LFS): `Art` (`Props`, and `Arch`: the greybox's boxes in grey, for the layout check and the plan), `Skin` (the shell as seen), `Doors`, `Layout`, `Lights` |
| `tools/blender/build_hotel_mazes.py` | the one re-runnable build for all seven (the seen-shell code is pure Python: `--skin` prints it without Blender) |

| Scene | GLB | Triangles | Meshes (draw calls) | Lightmaps (WebP) |
|---|---|---|---|---|
| `maze_01` | 3.88 MB | 40,980 | 19 | 261 KB + 779 KB |
| `maze_02` | 1.52 MB | 15,897 | 17 | 171 KB + 404 KB |
| `maze_03` | 1.78 MB | 16,860 | 19 | 256 KB + 501 KB |
| `maze_04` | 7.50 MB | 79,658 | 20 | 213 KB + 947 KB |
| `maze_05` | 5.18 MB | 60,716 | 19 | 259 KB + 771 KB |
| `maze_06` | 2.37 MB | 20,814 | 26 | 224 KB + 750 KB |
| `maze_07` | 4.89 MB | 49,267 | 21 | 251 KB + 632 KB |

## How it is built

- **One script for all seven:** `tools/blender/build_hotel_mazes.py`. The rooms share the method, the materials and the meshes: the same
  generated textures (same seeds), the same repo textures, one door-leaf mesh (`Leaf_Maze`, used by both doors in every room), and the same
  part builders (sconce, ceiling dome, framed print, EXIT sign, casings, rails).
  - In each GLB, the props are merged by material.
  - Repetition reuses a builder, so the 588 washers in maze_04 are one washer, built 588 times and merged.
  - `THEME` and `dress_<k>()` are all that differ between rooms.
- **The layout is the greybox's, unchanged.** The build makes every `COL_` box, `DoorLeaf_`, `Link_`/`Arrive_`, `Marker_` and `Spot_` from
  `build_hotel_greybox.py`'s `maze(k)` model, with the same names and numbers.
  - The walls, the one-way doors, the puzzle spot, the links and the arrival points are exactly where the greybox puts them.
  - The puzzle's moving parts stay the page's: the floor at each `Spot_puzzle` is left clear.
  - `export_scene.py` writes all seven layout files again, and git shows no change. The greybox script is untouched.
- **The shell is only what can be seen.** This is floor 1's skin method: every face of a greybox box that looks into the maze's air or into a
  door opening, cut where other boxes meet it. Each wall is cut at its finish line (chair rail, dado, water line, wainscot).
- **The dressing stands off the walls by 4.5 cm at most.** Anything else either hangs above 1.8 m (sconces, chandeliers, the upside-down
  stairs) or is lower than 0.2 m. So no piece needs a collider and the walkable space is the greybox's.
  - The curtains and the floor marks are `decor_` (passable).
  - The dressing slots are the cell edges along each wall face (`bays()`), derived from the same model.
- **Doors:** `DoorLeaf_entry` and `DoorLeaf_way_on` are one mesh, centred on the hinge line as in the greybox. The knob and kick plate are on the
  leaf's local −Y face only. For `entry` that is the atrium's side, because it does not open from the maze. For `way_on` it is the maze's side,
  because it opens when the puzzle is solved. Each leaf is its own node, with its origin at the hinge. The leaves' layout properties
  (`one_way`, …) are in the JSON, not in the GLB's extras.

## Light

- **One night bake per room, each with its own mood** (the table above), as one set: `lightmap` and `lightmap_intensity` only.
  - Each room is lit by its own fittings: sconces, panels, domes, tubes, chandeliers, bedside lamps or bulkheads. The mood is in the colour of
    the baked light.
  - Toggled materials:
    - `Lamp_Emit`: every room's lit fittings, emissive 3, in the room's light colour.
    - `Emergency_Emit`: the EXIT signs, green, emissive 5.

    Both are in the bake as on. `Lamp_Dead` marks the dead fittings. There is no `Window_Lit`.
- **Bake:** Cycles on the rented GPU (OptiX), 1024 samples, diffuse direct and indirect, OIDN. The highlight shoulder and white point are floor 1's.
- **Maps:**
  - `_0` is the shell, on a 2048 page, packed by hand: every skin face is a pixel-aligned rectangle with an 8 px margin.
  - `_1` is the props and the door leaf, on a 2048 page. The props are thousands of small pieces, so they are packed by piece:
    - A thin piece lying flat (a door, a washer's front, a letter) is one island, projected along its thin axis. Its sides become lines and its
      back a point, so they take no texels.
    - Any other piece gets up to six islands, one for each axis its faces turn to.
    - The islands are shelf-packed at the highest density that fits, with a 4 px margin.
  - When one page would give less than 32 px/m, the props are split over two pages by material. None of the seven needed it.
  - Only `DoorLeaf_entry` is baked; `way_on` shows the same lightmap.

| Map | Size | Density | `lightmap_intensity` before the gain | Gain (`caps.json`) |
|---|---|---|---|---|
| `maze_01_0` / `_1` | 2048 / 2048 | 47.6 / 79.7 px/m | 2.801 / 2.99 | 1.6934 |
| `maze_02_0` / `_1` | 2048 / 2048 | 47.8 / 129.9 px/m | 14.867 / 10.259 | 0.3021 |
| `maze_03_0` / `_1` | 2048 / 2048 | 47.8 / 118.6 px/m | 3.824 / 4.465 | 3.5985 |
| `maze_04_0` / `_1` | 2048 / 2048 | 49.0 / 50.0 px/m | 10.693 / 6.534 | 0.4293 |
| `maze_05_0` / `_1` | 2048 / 2048 | 47.2 / 68.2 px/m | 5.259 / 5.265 | 2.474 |
| `maze_06_0` / `_1` | 2048 / 2048 | 50.3 / 82.5 px/m | 2.299 / 1.861 | 2.375 |
| `maze_07_0` / `_1` | 2048 / 2048 | 47.0 / 55.0 px/m | 4.046 / 3.094 | 1.4394 |

## Brightness (as the page shows it)

Measured with `lab_display.py` on the packed GLBs: displayed = texture × base colour × lightmap texel × intensity / π, with no tone mapping.

- Each scene has one **gain** on its lightmap intensities (`caps.json`). It was found from the uncapped GLB, so that the room's big shell
  surfaces reach p99 0.9 (p90 0.85).
- Any material that would pass p99 0.97 or p90 0.88 was capped on its own.

| Scene | Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|---|
| `maze_01` | Wall_Upper | 530.2 | 0.179 | 0.535 | 0.847 |
|  | Leaf_Room | 334.7 | 0.030 | 0.110 | 0.192 |
|  | Carpet_Field | 237.1 | 0.095 | 0.123 | 0.144 |
|  | Ceiling_Popcorn | 237.1 | 0.195 | 0.844 | 0.950 |
|  | Wall_Lower | 226.5 | 0.013 | 0.195 | 0.289 |
| `maze_02` | Tile_Wall | 651.5 | 0.525 | 0.705 | 0.826 |
|  | Tile_Ceiling | 239.5 | 0.335 | 0.545 | 0.950 |
|  | Tile_Floor_Pool | 239.5 | 0.682 | 0.808 | 0.915 |
|  | Steel | 35.7 | 0.132 | 0.199 | 0.230 |
|  | Tile_Band | 34.1 | 0.242 | 0.280 | 0.308 |
| `maze_03` | Paper_Repeat | 523.9 | 0.270 | 0.419 | 0.909 |
|  | Carpet_Green | 237.4 | 0.113 | 0.162 | 0.253 |
|  | Ceiling_Plaster | 237.4 | 0.303 | 0.780 | 0.950 |
|  | Dado_Paint | 223.8 | 0.134 | 0.199 | 0.263 |
|  | Trim_White | 83.6 | 0.264 | 0.853 | 0.959 |
| `maze_04` | Paint_Upper | 411.4 | 0.282 | 0.466 | 0.549 |
|  | Enamel | 331.6 | 0.324 | 0.501 | 0.568 |
|  | Block_Lower | 273.2 | 0.000 | 0.101 | 0.163 |
|  | Ceiling_Tile | 239.4 | 0.207 | 0.265 | 0.950 |
|  | Vinyl_Floor | 239.4 | 0.236 | 0.294 | 0.339 |
| `maze_05` | Plaster_Cream | 513.0 | 0.355 | 0.693 | 0.949 |
|  | Wainscot | 255.7 | 0.041 | 0.086 | 0.139 |
|  | Ceiling_Plaster | 236.6 | 0.447 | 0.769 | 0.882 |
|  | Parquet | 236.6 | 0.317 | 0.452 | 0.610 |
|  | Gilt | 114.9 | 0.373 | 0.793 | 0.969 |
| `maze_06` | Wall_Room | 684.1 | 0.148 | 0.546 | 0.909 |
|  | Carpet_Room | 239.5 | 0.121 | 0.267 | 0.397 |
|  | Ceiling_Popcorn | 239.5 | 0.343 | 0.729 | 0.949 |
|  | Curtain | 68.5 | 0.027 | 0.074 | 0.120 |
|  | Leaf_Room | 58.8 | 0.037 | 0.090 | 0.145 |
| `maze_07` | Block_Upper | 455.8 | 0.334 | 0.744 | 0.950 |
|  | Block_Lower | 302.8 | 0.056 | 0.116 | 0.181 |
|  | Stair_Ceiling | 237.0 | 0.284 | 0.668 | 0.780 |
|  | Stair_Concrete | 237.0 | 0.051 | 0.093 | 0.156 |
|  | Step_Concrete | 218.7 | 0.000 | 0.063 | 0.132 |

No material in any room is over p90 0.9 or p99 0.98 (measured on every baked material, not only these). The walls read: the main wall finish
has p50 0.15 to 0.53 in every room (maze_06's Wall_Room 0.148, a dim room by design). These are dark by design, or by hidden area:
- The lower bands below the rail are darker finishes: maze_01's Wall_Lower, maze_05's Wainscot, maze_07's Block_Lower.
- maze_04's Block_Lower shows p50 0 because most of it is hidden behind the washers.
- maze_01's door leaves are dark wood.
- Prop materials with p50 near 0 count faces no one sees: step sides pressed together, the backs of pieces.


## Review stills

- Cycles, 128 samples adaptive, OIDN, 1920 × 1080 JPEG (comment and APP1 segments stripped), AgX Medium High Contrast, Blender's real lights.
- The three stills:
  - `1_arrival`: at the entry, eye height 1.6 m, looking down the first open passage (the greybox still's direction).
  - `2_wide`: the whole room from above, with the ceiling and everything hung from it left out, exposure +1.3.
  - `3_detail`: the room's wrongness, close up.
- `plan.jpg`: top down, ceiling off, the walls in the greybox's grey, north up.
- The owner sheets are not in the repo.

## Gates

- `blender -b blender/scenes/<scene>.blend --python tools/blender/check_layout.py -- --scene <scene>` (run by the build's check stage):
  **PASS 36/36, 27/27, 41/41, 34/34, 40/40, 34/34, 45/45** (maze_01 to 07).
  Every collider is covered, every tall solid stands on a collider, and the spawn marker is clear. `check_layout.py` is unchanged, since the maze
  scenes are in `world/`.
- `python tools/blender/build_hotel_greybox.py --check .`: **GATES PASS** (47 link pairs, steps, corridors).
- `export_scene.py` writes the same seven layout files: no diff.
- `node tools/worlddoc.mjs check world/maze_0k.json`: **OK, 0 errors** on all seven. There are 3 warnings each, all saying that the scene and its
  links are new to the manifest.
- `glb_inspect.py --budget tris=300000,mb=8`: **pass** on all seven (3.70, 1.45, 1.70, 7.15, 4.94, 2.26, 4.66 MB as it counts; the
  largest is maze_04, at 79 658 triangles).
- `node --test shared/*.test.js`: **297 pass, 0 fail**.
- Axes: the marker-cube check (`--stage axes`) passes in every room.
- Privacy: the GLBs, WebPs, JSON, stills, script and the decompressed `.blend`s hold no user name, local path, session id or e-mail. The JPEGs'
  comment and APP1 segments are stripped.

## Sources and licences

Every texture file is already in the repo and CC0 (Poly Haven), reused from earlier scenes:

| File | Used for | Source | Licence |
|---|---|---|---|
| `blender/textures/main_floor/wall_paint_diff.jpg` (`painted_plaster_wall`) | floor 1's wallcovering (with generated stripes), the stairwell block (with generated joints), the dado, upper and room paint, stair ceiling, fire doors, jambs | https://polyhaven.com/a/painted_plaster_wall | CC0 1.0 |
| `blender/textures/laboratory/wall_paint_diff.jpg` (`white_plaster_02`) | the popcorn ceilings (tinted) | https://polyhaven.com/a/white_plaster_02 | CC0 1.0 |
| `blender/textures/laboratory/floor_vinyl_diff.jpg` (`tiled_floor_001`) | the laundry's floor | https://polyhaven.com/a/tiled_floor_001 | CC0 1.0 |
| `blender/textures/laboratory/ceiling_tile_diff.jpg` (`polystyrene`) | the laundry's ceiling tiles | https://polyhaven.com/a/polystyrene | CC0 1.0 |
| `blender/textures/galleries/herringbone_parquet_diff_1k.jpg` (`herringbone_parquet`) | the ballroom's floor | https://polyhaven.com/a/herringbone_parquet | CC0 1.0 |
| `blender/textures/galleries/plastered_wall_04_diff_1k.jpg` (`plastered_wall_04`) | the ballroom's walls, the plaster ceilings, the white trim, the mirrors' tint | https://polyhaven.com/a/plastered_wall_04 | CC0 1.0 |
| `blender/textures/apartment/dark_wood_diff_1k.jpg` (`dark_wood`) | doors, casings, chair and dado rails, the wainscot | https://polyhaven.com/a/dark_wood | CC0 1.0 |
| `blender/textures/apartment/rough_linen_diff_512.jpg` (`rough_linen`) | the headboards and curtains (tinted) | https://polyhaven.com/a/rough_linen | CC0 1.0 |
| `blender/textures/factory_floor/concrete_floor_diff.jpg` (`hangar_concrete_floor`) | the stairwell's floor and the upside-down flights | https://polyhaven.com/a/hangar_concrete_floor | CC0 1.0 |

**Own work,** made by the build with numpy from fixed seeds (floor 1's generators where shared):

- Floor 1's maroon carpet, room carpet, wallcovering stripes, block joints, white tile and prints.
- The green carpet, the pool tile, the damask that repeats, the ghost marks of the tables, the washer's glass and sock, the water stains, the
  grilles and the brushed metal.

All geometry is own work. Lettering (101, 214, 7, the depth marks, STAIRS L4, EXIT, the plaques) is geometry made from Blender's built-in text
font. Nothing was downloaded: no Meshy, no Higgsfield, no purchases.

## Rebuild

```
blender -b --factory-startup --python tools/blender/build_hotel_mazes.py -- --scenes maze_01,maze_02,maze_03,maze_04,maze_05,maze_06,maze_07 --stage all --work <dir>
python tools/blender/build_hotel_mazes.py --pack <scene> --work <dir>          # WebP lightmaps, WebP textures -> world/
python tools/blender/build_hotel_mazes.py --skin                               # the seen shell and the dressing slots, no Blender
```

- `--stage art|bake|export|reexport|axes|check|render|preview` runs single steps on the saved `.blend`.
- `reexport` is export and check, used to apply `caps.json`; `--caps <dir>` reads `<dir>/<scene>.json` instead.
- `preview` is art and render at low samples, with no bake.
- It ran on the rented GPU box through `fw_remote.sh`, one Blender at a time.

## For the coordinator

1. **Manifest:**
   - Add `world/maze_0k.glb` to each maze scene and apply its lightmaps with `applyLightmaps`. Every baked material carries `lightmap` and
     `lightmap_intensity`; there is no night set.
   - The links are the greybox's: atrium `maze` → `maze_01.entry`, `maze_0k.way_on` → `maze_0(k+1).entry`, and `maze_07.way_on` → atrium
     `maze_exit`, all `one_way`.
2. **Doors:** the leaves are nodes `DoorLeaf_entry` and `DoorLeaf_way_on`. `entry` never opens from inside, and `way_on` opens when the puzzle is
   solved (the code's).
3. **Puzzles:** each room's `Spot_puzzle_1` is clear floor.
   - The odd rooms have it in the middle room. In maze_05 that is the empty dance floor under the big chandelier, ringed by chair marks.
   - The even rooms have it in the cell before the way on.
   - The puzzles' moving parts are the page's.

## Open

- Not seen in the browser: the page's shading and the doors swinging are untested.
- Only one door leaf is baked; the way-on leaf shows the entry leaf's light.
- The mirrors (maze_05) are baked as a dark silvered surface: the page shows no reflection.
