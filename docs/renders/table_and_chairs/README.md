# table_and_chairs: dressed and baked (docs/BLENDER_AREAS.md, "4. The Overworld"; step 2)

The spawn: the table and chairs in the parking lot, facing the store, dressed in Blender on the greybox's layout
(`claude/blender-overworld-greybox`, draft PR #115), unchanged: `export_scene.py` writes the same `world/table_and_chairs.json` from the
dressed `.blend`. It is a set that stays part of the lot: the greybox's `ATTACH` puts its origin (the table's centre) at the lot's
(-8, 9.6, 41), yaw 0. Tone: plastic and pastel, empty but seemingly normal.

| File | What |
|---|---|
| `world/table_and_chairs.glb` | the set only (0.27 MB, 4,512 triangles, 9 draw calls, flat colours, no textures), merged by material |
| `world/lightmaps/table_and_chairs_0.webp` | the AO bake, 1024 x 1024, 161 px/m, linear grey, on TEXCOORD_1 |
| `blender/scenes/table_and_chairs.blend` | the saved scene (Git LFS): `Art`, `Layout`, `Export`, and `Context` (the lot and the store's front round the set, from the greybox's `ctx_` boxes: in the stills and the bake's rays, never exported) |
| `1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg` | R2's stills (Cycles, 128 samples): from the spawn at 1.6 m facing the store; the set from the south-east; the table top |
| `bake.json`, `CHECKS.txt` | the bake's numbers; every gate's output |

Built by `tools/blender/dress_overworld.py -- --scene table_and_chairs` (one Blender run: art, layout gates, bake, export, stills), then
`python tools/blender/pack_scene.py table_and_chairs --work work/ow_table_and_chairs` (the GLB has no textures, so it is copied as exported).

## What is there

- **The table:** a round moulded top (0.85 m radius, a rolled rim) on a tapered pedestal and a round foot, in index.html's colours (an
  off-white top, a warm grey leg). The top and the foot are one solid object, `Table`, whose box is the collider's.
- **Four chairs** (`Chair_E`, `_W`, `_S`, `_N`): pink, mint, yellow and blue as index.html draws them, each a seat, a back leaning 3 cm away
  from the table and a round foot on a grey post, the backs away from the table.
- **Added (decor_, passable):** a pink and white parasol through the table's centre (eight panels, its hem 1.96 m up, so you walk under it),
  a paper cup and a napkin holder left on the table. Nobody is here.
- **No ground:** the set ships none. In the game the lot's own asphalt (part 1's `parking_lot`) is under it; `Ground_lot` stays a collider
  only, as the greybox has it.

## Light (docs/BLENDER.md R1, AO-only scenes)

Open air, as the other Overworld scenes: only ambient occlusion is baked. Every baked material carries `aomap`
(`world/lightmaps/table_and_chairs_0.webp`), `aomap_intensity` 1.0 and `aomap_colorspace` `linear`; the page keeps them lit and uses the map
as `aoMap` on UV1. Bake: Cycles AO, 512 samples on the GPU, distance 2.5 m, OIDN, 8 px margin; the lot's asphalt (Context) was in the scene
for the rays, so the feet meet the ground. No `Lamp_Emit` or `Window_Lit` here.

## Brightness

Base colour x AO (linear), under a white ambient of 1, before the page's sun (as the other Overworld scenes). Nothing reaches 0.9.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Plastic_White | 5.8 | 0.289 | 0.479 | 0.619 |
| Parasol_Pink | 3.1 | 0.869 | 0.869 | 0.869 |
| Parasol_White | 3.1 | 0.848 | 0.848 | 0.848 |
| Plastic_Blue | 1.3 | 0.483 | 0.633 | 0.772 |
| Plastic_Mint | 1.3 | 0.390 | 0.508 | 0.610 |
| Plastic_Pink | 1.3 | 0.487 | 0.633 | 0.761 |
| Plastic_Yellow | 1.3 | 0.487 | 0.629 | 0.761 |
| Plastic_Grey | 0.9 | 0.200 | 0.273 | 0.304 |
| Paint_White | 0.1 | 0.290 | 0.359 | 0.401 |

Plastic_White's low p50 is the table's underside and the top's shade under the parasol (the parasol's own faces get the sky's full AO).

## Gates (CHECKS.txt has the full output)

- Layout check, run in Blender on the saved scene: 7 of 7 pass (COVER for the table and the four chairs, STRAY, CLEAR for the spawn),
  plus the LOT rule: `Ground_lot` has no art by design (the lot's asphalt), it lies flat at y 0 inside the lot round the set.
- `export_scene.py` writes the same `world/table_and_chairs.json`.
- `build_overworld_greybox.py --check .`: GATES PASS.
- `node tools/worlddoc.mjs check world/table_and_chairs.json`: OK, 0 errors, 0 warnings.
- `glb_inspect --budget tris=300000,mb=8`: pass (4,512 triangles, 0.27 MB).
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Privacy grep over this scene's files (the `.blend` decompressed): 0 hits. The stills carry no comment or APP1 segment.

## Sources and licences

Everything here was made for this scene by `dress_overworld.py`: flat colours, no textures, no downloads. No Meshy, no Higgsfield, no
purchases.

## Open

- The coordinator places the GLB in the lot at `ATTACH` (the lot's (-8, 9.6, 41)) and drops index.html's own table and chairs
  (`overworldProps`), whose colliders are the same boxes.
- The page does not read `aomap` yet; the coordinator wires it with the scene.
- The parasol is an addition (decor_); drop `decor_Parasol_*` in `extra_table_and_chairs` if the owner wants the bare table back.
