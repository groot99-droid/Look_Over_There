# Right Door, Wrong Exit, Phase A: the seven rooms dressed and lit

`docs/BLENDER_AREAS.md`, section 7, step 2. The seven rooms that exist in `games/rdwe/scenes/*.js`, remade larger and psychedelic around the
greybox (`tools/blender/build_rdwe_greybox.py`, `docs/renders/rdwe_greybox/`), in story order: `rdwe_dining`, `rdwe_hallway`, `rdwe_teal`,
`rdwe_teal2`, `rdwe_flooded`, `rdwe_trampoline`, `rdwe_grocery`. Super Liminal, psychedelic: saturated, dreamlike, slightly wrong, and each
room still recognisably itself (its palette, its furniture and its trick from the scene file, at the greybox's 1.2x to 3x scale).

This README covers all seven. Each room's folder (`docs/renders/<scene>/`) holds its three stills, its plan, `bake.json` and `caps.json`.
Nothing is wired: no manifest change, and `games/rdwe/`, `index.html`, `shared/` and the tests are untouched.

| File | What it is |
|---|---|
| `world/<scene>.glb` | the room's art (art only; no colliders) |
| `world/lightmaps/<scene>_0.webp`, `_1.webp` | its lightmaps on UV1 (`TEXCOORD_1`): `_0` the shell, `_1` everything in it. The dining room also has `_2`, `_3`: the alt set |
| `world/<scene>.json` | the layout, written by `export_scene.py` from the dressed `.blend`: identical to the greybox's file |
| `blender/scenes/<scene>.blend` | the saved scenes (Git LFS): `Art` (`Props`, and `Arch`: the shell colliders' grey twins, hidden, for the layout check and the plan), `Skin` (the shell as seen), `Doors` (the leaves), `Layout`, `Lights`, `Lights_Alt` |
| `blender/textures/rdwe/` | the CC0 textures the build reads (below) |
| `tools/blender/build_rdwe_phaseA.py` | the re-runnable build of all seven rooms |

Built so far: `rdwe_dining`, `rdwe_hallway`.

## How it is built

The hotel floors' method (`tools/blender/build_hotel_floor2.py`), made for these rooms.

- **The layout is the greybox's, unchanged.** The build makes every `COL_` box, `DoorLeaf_` (with all its properties, `look` included),
  `Link_`/`Arrive_`, `Marker_`, `Zone_` and `Spot_` from `build_rdwe_greybox.build(<scene>)`; `export_scene.py` then writes `world/<scene>.json`,
  and it is the greybox's file byte for byte (only Git's line endings differ). No collider, door, link, spot or zone moved; the greybox script is
  untouched. The page-trick `Spot_` objects are as they were.
- **The shell as seen** (`Skin`) is made from the greybox's shell boxes (walls, floors, ceilings, steps, landings, the black `Beyond_` boxes past
  every door): each face is cut into pieces of 4 m at most, and a piece is kept when the air in front of it is in the room (`AIR`, the room and its
  stairwell or well, plus every door's opening) and in no other shell box. Of the `Beyond_` boxes only the face toward the door is drawn.
- **Furniture** (the greybox boxes listed in `FURNITURE`: the table, the chairs, the sofas, the plants, the rails, the heaps, the columns, the
  shelving...) is dressed with props that cover the box (the layout check's COVER rule) and stand on it (STRAY). Small things you could walk
  through are `decor_` (cushions, china on the table, the photo frames, the skirting, casings, lamps).
- **Every door is different.** Each leaf is its own mesh, made from its `look`: the form (panelled, six-panel, flush, louvred, half-glazed, ledged
  and braced, round-topped, studded, quilted, mirror-faced, porthole, stable), the finish (each of the 15 finishes is its own saturated leaf
  material: `Leaf_Oak`, `Leaf_PinkLaminate`, `Leaf_CherryRed`...) and the handle (brass knob, glass knob, chrome lever, push plate, ring pull,
  push bar, none). The story doors are built from their words: the front door's six panels and brass knocker, the cream door with no frame and
  no handle (the loop), the black stair door with the hair of light round it (`Glow_Emit` on the reveal), the green baize door with its brass
  studs, the mossy stone door with an iron ring, the square doorway's slab of black (`Void`), the arch (no leaf: `DoorLeaf_arch` is an empty, as
  the layout needs its record), the door under peeled wallpaper (the grid shows through), the back of the arch (teal, round-topped), the picture
  frame whose canvas is the leaf, the red door (`Emergency_Emit`), the marble door with a meander frieze, the padded vent door, the chained glass
  pair, the steel fire door with its push bar, the bronze door with a laurel wreath, the stockroom's rubber flaps with STAFF ONLY. Each leaf is
  its node `DoorLeaf_<door>`, origin at the hinge, as the greybox had it; each is baked into the props map.
- **Export:** the skin as it is (one mesh a material) and the props merged by material (faces pressed against the shell dropped), plus the
  leaves. Repetition (the grocery's 79 shelf runs, the trampoline park's 54 beds) is merged into one mesh a material, which keeps the draw calls
  low.
- **Textures:** CC0 photo textures already in the repo (below) and images generated here with numpy (own work, fixed seeds): the shag carpet,
  the swirl paper, the photos, the round rug, the plaid, the diamond carpet, the mossy pixel stone, the flecked carpet, the glowing grid, the
  tiles, the painted sky, the padded vinyl, the bed weave, the concrete, the speckled vinyl, the brushed metal.

## Light

- **Baked indoors, one set a room** (`lightmap` on UV1), with its lamps on. The dining room also has an **alt set** (`lightmap_night` /
  `lightmap_night_intensity`, maps `_2` and `_3`): the same room with the green lamp on the sideboard off, for the page's lamp-off beat (the
  photo changes when the lamp clicks off). The alt set shares the day set's white point, so it reads as the lamp going off and nothing else.
- **Toggled materials:** `Lamp_Emit` (dome lights, tubes, panels, LED panels, strips), `Emergency_Emit` (the red door and its frame, the red glow,
  the EXIT sign), `Window_Lit` (the teal room's fake window, whose sun never moves). The dining room's green lamp shade is its own
  `Lamp_Emit_Green`, so the page can click it off alone. All are in the bake as on.
- **Unbaked materials** (no lightmap; drawn as their colour): the toggled ones above, `Glow_Emit` (the hair of light round the dark door),
  `Grid_Emit` (the glowing grid), `Amber_Emit` (the hallway's amber bars), `Void` (the black past every door), `Water` (the flooded floor's sheet:
  a transparent, glossy plane 5 cm over the tiles, hidden from the bake so the floor under it is baked as if dry; the page may ripple it), and
  `Glass_Clear`. The trampoline beds are baked like everything else (they are art, merged; the page bounces you, not them).
- **Bake:** Cycles on the rented GPU (OptiX), 768 samples, diffuse direct and indirect, 8 px margin, OIDN, a highlight shoulder (above the map's
  75th percentile, toward 2.5 times it), white point the 99.5th percentile (at most 12 times the 90th). **Pages are fixed** (`PAGES`): 2048 +
  2048, the teal rooms 1536 + 1536. The shell is packed by hand (pixel-aligned rectangles); the props are smart-projected.

## Brightness (as the page shows it)

Measured with `lab_display.py` on the packed GLBs (displayed = texture x base colour x lightmap texel x intensity / pi, no tone mapping). Each
room has one **gain** on its lightmap intensities (`caps.json`), chosen from the uncapped GLB so its main walls reach p50 0.30, and lowered if
a wall would pass p99 0.97 or p90 0.88; any other material that would pass p99 0.97 or p90 0.88 is capped by its own factor. The packed GLB is
capped by `build_rdwe_phaseA.py --caps <scene>` (the same numbers `stage_export` writes from the `.blend` with that `caps.json`).

## Sources and licences

| Texture (Poly Haven, CC0 1.0) | Used for | Source | Author |
|---|---|---|---|
| `plastered_wall_04` (diffuse 1k) | ceilings, the teal walls, the stairwell walls, the amber vestibule | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel |
| `dark_wood` (diffuse 1k) | the maple table, chairs and sideboard, oak leaves, the frames | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers |
| `rough_linen` (diffuse, resized to 512) | linen, sheers, leather, baize | https://polyhaven.com/a/rough_linen | colormass, Rico Cilliers |
| `marble_01` (diffuse 1k) | the marble door | https://polyhaven.com/a/marble_01 | Rob Tuytel |
| `concrete_floor_02` (diffuse 1k) | the stone planter, the stone door | https://polyhaven.com/a/concrete_floor_02 | Rob Tuytel |
| `white_plaster_02` (`wall_paint_diff.jpg`, from `blender/textures/laboratory/`) | trims, painted leaves, the grocery's walls | https://polyhaven.com/a/white_plaster_02 | Rob Tuytel |
| `tiled_floor_001` (`floor_vinyl_diff.jpg`, from `blender/textures/laboratory/`) | (spare) | https://polyhaven.com/a/tiled_floor_001 | Dimitrios Savva, Rob Tuytel |
| `polystyrene` (`ceiling_tile_diff.jpg`, from `blender/textures/laboratory/`) | the grocery's acoustic ceiling | https://polyhaven.com/a/polystyrene | Dimitrios Savva, Dario Barresi |
| `plywood` (diffuse 1k) | the cardboard, the flats | https://polyhaven.com/a/plywood | Rob Tuytel |

Everything else is generated by the build (numpy, fixed seeds) or a flat colour. No Meshy, no Higgsfield, nothing bought.

## The rooms

### `rdwe_dining`: the Dining Room, the anchor

16 m by 20 m, 4.2 m high (3x the old room). Cream walls in a swirl paper whose pink and mint curls seem to turn as you look, a deep green shag,
a pale ceiling with two dome lights in plaster roses that have opened a little too far. The giant round maple table (4.4 m, 1.25 m high) on a
turned pedestal and a cross of splayed feet, laid for four guests who never came (plates, cups and saucers the size of hats, a white runner, a
vase of too-pink flowers), on a round rug of rings. Four arrow-back chairs to match, with cushions. The sideboard on the west wall with its
drawers, brass knobs, a short stack of plates and the green ceramic lamp (`Lamp_Emit_Green`). The photo wall: six frames, dark and gilt, the
family snapshots with every face missing. The good china in four crooked towers against the east wall, folded tablecloths by them, sheer
curtains on a brass rod over a window that is not there. The steep green-carpeted stairwell in the back wall: stringers, a brass handrail on
two brackets, and the black door at the top with a hair of light round it. Doors: the white six-panel front door with its brass knocker, the
pantry's panelled oak door, the cream door with no frame and no handle (the loop), the black stair door.

- GLB 2.62 MB, 25554 triangles, 30 draw calls; lightmaps `_0` / `_1` 2048 / 2048 at 53.8 / 52.2 px/m (109 KB / 517 KB), alt `_2` / `_3` (106 KB / 506 KB).
- Light: two dome lights (900 W area lights) and four soft fills over the room, the green lamp (160 W, off in the alt set), a glow at the top of the stairs and one down the stairwell. Gain 0.42; capped: China 0.398, Flower_Pink 0.329.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Ceiling_Dining | 347.1 | 0.063 | 0.106 | 0.166 |
| Shag_Green | 334.6 | 0.147 | 0.319 | 0.612 |
| Wall_Cream | 300.0 | 0.300 | 0.556 | 0.813 |
| Maple | 89.3 | 0.001 | 0.101 | 0.187 |
| Stair_Wall | 73.2 | 0.007 | 0.041 | 0.079 |
| China | 68.0 | 0.098 | 0.591 | 0.971 |
| Trim_Cream | 45.1 | 0.171 | 0.464 | 0.695 |
| China_Rim | 42.9 | 0.000 | 0.082 | 0.326 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)

The stairwell is dark by design ("the dark, steep stairwell"). The ceiling is dimmer than the walls (lit from below by the down lights, and
tinted by the green carpet). The alt set (the green lamp off) measures within a few hundredths of the day set except round the sideboard.

### `rdwe_hallway`: the Hallway, the descent

A corridor 49 m end to end, 3.2 m wide and 4.6 m high: from the lower landing up six carpeted steps (brass nosings) into the long plaid
corridor of doors that do not feel right. The printed plaid is grey-beige with violet and lime threads gone a little too bright; the worn tan
carpet has a lattice of dark diamonds with a pink dot in each; nine surface-mounted twin-tube fluorescents (`Lamp_Emit`: the page flickers
them one at a time); a dark skirting and cornice. At the far end the amber vestibule (its walls amber plaster, its ceiling stacked with light
bars, `Amber_Emit`) over the well of mossy pixel-block stone going down, moss creeping up its sides. Ten doors, each its own: the green baize
door with brass studs back to the dining room, and nine down the corridor (pink laminate flush with a push plate, cherry red louvred, black
lacquer half-glazed with a brass knob: the three that open; and six that never open: sky blue ledged and braced, an oak round-topped door with a
glass knob, studded pink laminate, quilted cherry red with a ring pull, a mirror-faced black door, a sky blue porthole door).

- GLB 1.88 MB, 16884 triangles, 39 draw calls; lightmaps `_0` / `_1` 2048 / 2048 at 59.4 / 51.3 px/m (94 KB / 226 KB).
- Light: nine tube fittings (130 W cool area lights), the amber vestibule (500 W), a green glow in the well, a warm light on the landing. Gain 0.706; capped: Fixture 0.545, Glass_Knob 0.697.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Wall_Plaid | 361.3 | 0.300 | 0.542 | 0.750 |
| Carpet_Tan | 183.7 | 0.323 | 0.436 | 0.551 |
| Ceiling_Hall | 177.8 | 0.083 | 0.128 | 0.599 |
| Wall_Amber | 78.1 | 0.385 | 0.590 | 0.697 |
| Moss_Stone | 54.9 | 0.001 | 0.428 | 0.917 |
| Trim_Hall | 35.0 | 0.070 | 0.105 | 0.128 |
| Leaf_PinkLaminate | 13.2 | 0.001 | 0.736 | 0.843 |
| Leaf_CherryRed | 12.9 | 0.001 | 0.501 | 0.626 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)

## Review stills

Cycles, 128 samples adaptive, OIDN, 1920 x 1080 JPEG (comment and APP1 segments stripped), AgX Medium High Contrast, Blender's real lights (not
the lightmaps). `plan.jpg` in each folder is a top-down view with the ceiling off.
﻿
## Checks

For each room: `build_rdwe_greybox.py --check .` (GATES PASS), the layout check from the `.blend` (`check_layout.py`: every collider covered,
no stray solid art, the markers clear), the axes check (game (x, y, z) = Blender (x, -z, y) = glTF), `world/<scene>.json` identical to the
greybox's, `node tools/worlddoc.mjs check` (OK, 0 errors; the warnings say the scene and its links are new to the manifest), `glb_inspect`
within 300 000 triangles and 8 MB, the brightness table, `node --test shared/*.test.js` (297 pass), and a privacy grep over every file
committed (the `.blend` is saved uncompressed; its one hit is a chance three-byte match inside binary mesh data, not a path).

`tools/blender/check_layout.py` takes floor 1's STRAY change: art may also sit in a collider at its own height (the upper steps of a flight).

## Notes for the coordinator

- Nothing is wired. The layout files are the greybox's, unchanged, so the manifest work is the greybox's notes.
- The dining room's green lamp is `Lamp_Emit_Green` and its alt set is `lightmap_night` (maps `_2`, `_3`): for the lamp-off beat, dim that
  material and swap the room to the alt maps; the rest of the room barely changes (the domes are on in both).
- Unbaked materials are drawn as their colour: `Void`, `Glow_Emit`, `Grid_Emit`, `Amber_Emit`, `Water` (transparent, 0.28) and the toggled ones.
- `DoorLeaf_arch` in `rdwe_teal2` is an empty (the arch has no leaf); every other leaf is a mesh with its origin at the hinge.
