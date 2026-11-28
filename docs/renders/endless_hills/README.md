# endless_hills: dressed and baked (docs/BLENDER_AREAS.md, "4. The Overworld"; step 2)

The endless hills' tile, dressed in Blender on the greybox's layout (`claude/blender-overworld-greybox`, draft PR #115), unchanged:
`export_scene.py` writes the same `world/endless_hills.json` (2,502 colliders, 1 link, 17 spots) from the dressed `.blend`. Tone:
dreamcore, eerily beautiful; hills that never get you further away.

| File | What |
|---|---|
| `world/endless_hills.glb` | the art (WebP textures, 5.95 MB, 75,048 triangles, 16 draw calls) |
| `world/lightmaps/endless_hills_0.webp` | AO for the hills' surface: 2048 x 2048, 10.2 px/m, linear grey, TEXCOORD_1 |
| `world/lightmaps/endless_hills_1.webp` | AO for the props: 1024 x 1024, 12.9 px/m |
| `blender/scenes/endless_hills.blend` | the saved scene (Git LFS): `Art`, `Layout`, `Export` |
| `1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg` | from the arrival by the tile's centre at 1.6 m; the tile from the south-east, high; the ring of mushrooms (puzzle 2) |
| `bake.json`, `CHECKS.txt` | the bake's numbers; every gate's output |

Built by `tools/blender/dress_overworld.py -- --scene endless_hills`, packed by `pack_scene.py endless_hills --work work/ow_endless_hills`.

## What is there

- **The hills:** the greybox's own surface (`decor_Hills_Surface`, its 2 m grid, the same heights), in bright pastel grass whose texture
  repeats a whole number of times across the tile (50 times, every 4 m), so the tile still repeats without a seam.
- **Flowers:** about 8,800 in drifts of four colours, all at least 10 m inside the tile's edges, so nothing is cut at a seam; the toys'
  spots (2 m) and the puzzles' (4 m) and the arrival are kept clear.
- **The four puzzles' props** (all `decor_`, passable; what they do is the page's): five stacked stones and three loose ones by puzzle 1;
  a ring of eight pink mushrooms (puzzle 2); a white door frame standing alone (puzzle 3); a hopscotch grid of eight squares painted on
  the grass, following the ground (puzzle 4).
- **The way back:** the greybox's signpost by the tile's centre, its board reading "THE WAY BACK".
- **The facade:** the "more to come" front alone on its rise, pink plaster, a painted fake door and the MORE TO COME sign.
- **The toys:** spots only, as in the greybox; the page makes them (physics, kickable).

## Light (docs/BLENDER.md R1, AO-only scenes)

Only ambient occlusion is baked (Cycles AO, 512 samples, 2.5 m, OIDN, 8 px margin). Each baked material carries `aomap`
(`world/lightmaps/endless_hills_0.webp` or `_1.webp`), `aomap_intensity` 1.0 and `aomap_colorspace` `linear`; the page keeps it lit. The
surface's AO is almost all white (p1 0.90, p50 1.0): the hills are gentle, and nothing stands near an edge, so the AO matches across the
seams too. Not baked: the flowers.

## The layout check and the hills' columns

`check_layout.py`'s COVER rule wants solid art round every collider, but the hills' 2,500 collision columns (`Ground_Hills_<i>_<j>`, from
y -6 up to the ground) sit under one passable surface, as the greybox designed them. The in-Blender gate checks them by their own rule
instead: the surface's vertex at each column's centre must be that column's top. All 2,500 pass within 0.5 mm. The other colliders (the
signpost and the facade) and the link take check_layout's rules: 5 of 5 pass.

## Brightness

Base colour x AO (linear), under a white ambient of 1, before the sun:

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Grass | 40022.5 | 0.539 | 0.578 | 0.604 |
| Plaster_Pink | 131.5 | 0.768 | 0.807 | 0.831 |
| More_To_Come | 7.2 | 0.118 | 0.855 | 0.991 |
| Fake_Door | 6.1 | 0.064 | 0.216 | 0.245 |
| Mushroom_Cap | 6.0 | 0.523 | 0.811 | 0.828 |
| Stone | 4.1 | 0.242 | 0.554 | 0.604 |
| Trim_White | 3.7 | 0.617 | 0.798 | 0.821 |
| Mushroom_Stem | 2.0 | 0.370 | 0.527 | 0.890 |
| Deck | 1.6 | 0.335 | 0.449 | 0.505 |
| Paint_White | 1.3 | 0.636 | 0.787 | 0.787 |
| Sign_Back | 0.9 | 0.526 | 0.583 | 0.600 |

More_To_Come's p99 0.99 (0.44 % of its 7 m2 at 1) is the sign's bright yellow at its brightest texels after WebP; it is small, and the
page's light scales it.

## Gates (CHECKS.txt has the full output)

- In Blender: export EQUALS, HILLS 2,500 of 2,500, layout check 5 of 5.
- `build_overworld_greybox.py --check .`: GATES PASS (it includes the hills tile's seam gate on the layout).
- `node tools/worlddoc.mjs check world/endless_hills.json`: OK, 0 errors (warnings as in the greybox).
- `glb_inspect --budget tris=300000,mb=8`: pass (75,048 triangles, 5.95 MB).
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Privacy grep over this scene's files (the `.blend` decompressed): 0 hits.

## Sources and licences

All made here: geometry by `dress_overworld.py` (the surface is the greybox's), textures by `overworld_textures.py`. No downloads, no
Meshy, no Higgsfield, no purchases.

## Open

- The page does not read `aomap` yet; the coordinator wires it, and the page's tile repeat and wrap are the coordinator's as before.
- The hills are deliberately bare beyond the flowers: the toys, the sky backdrops (PR #117) and the page's sun carry the rest. Taller hills
  or more props would be an owner call (greybox question 6).
- The flowers make most of the GLB's size (5.95 MB of 8); fewer drifts would halve it if size matters on phones.
