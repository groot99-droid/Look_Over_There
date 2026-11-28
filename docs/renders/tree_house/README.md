# tree_house: dressed and baked (docs/BLENDER_AREAS.md, "4. The Overworld"; step 2)

The tree house's glade, dressed in Blender on the greybox's layout (`claude/blender-overworld-greybox`, draft PR #115), unchanged: `export_scene.py`
writes the same `world/tree_house.json` from the dressed `.blend` (the run checks it byte for byte, line endings aside). Tone: dreamcore,
"plastic, like a simulation, and eerily beautiful" (docs/WORLD.md), a secret.

| File | What |
|---|---|
| `world/tree_house.glb` | the art (WebP textures, 1.83 MB, 23,185 triangles, 24 draw calls), merged by material; the two door leaves as their own nodes on their hinges |
| `world/lightmaps/tree_house_0.webp` | the AO bake, 2048 x 2048, 19 px/m, linear grey, on TEXCOORD_1 |
| `blender/scenes/tree_house.blend` | the saved scene (Git LFS): `Art` (one object per greybox box, plus the `decor_` dressing), `Layout` (COL_ boxes, Link_/Arrive_, Spot_), `Export` (what the GLB is made of) |
| `1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg` | R2's stills (Cycles, 128 samples): from the playground gap at 1.6 m, the glade from the south-east, the puzzle board inside the house |
| `bake.json`, `CHECKS.txt` | the bake's numbers; every gate's output |

Built by `tools/blender/dress_overworld.py -- --scene tree_house` (one Blender run: art, layout gates, bake, export, stills), then
`python tools/blender/pack_scene.py tree_house --work work/ow_tree_house`. The textures are `tools/blender/overworld_textures.py`'s.

## What is there

- **The glade:** bright pastel grass, the hedge as one soft rounded hedge per greybox box, seven pastel trees (pink and lilac blob crowns on
  tapered trunks) and flowers (900, four colours) and small mushrooms by the trees; stepping stones from the playground gap to the stairs.
- **The big tree:** a thick trunk through the platform and the house, two layers of mint crown; a deck collar fills the platform's square
  hole round the round trunk.
- **The tree house:** mint vertical boards, a coral shingle gable roof, five windows with white frames (`Window_Lit`), a deck platform on
  four posts, the porch railings (posts and rails filling each greybox rail), 16 deck steps with handrails both sides, and the lantern
  (`Lamp_Emit`) on the north wall.
- **The puzzle (Spot_puzzle_1):** a carved board of nine symbols in three rows on the west wall inside. What they mean is the page's.
- **The trunk door (DoorLeaf_addon):** a plank leaf, closed and locked, as the greybox has it; the house door (DoorLeaf_house) ajar.
  Both leaves keep their greybox properties as node extras.

## Light (docs/BLENDER.md R1, AO-only scenes)

Open air: the page's sun and the four Overworld skies light it, so only ambient occlusion is baked (no day or night lightmap set). Every
baked material carries, in its glTF extras:

- `aomap`: `world/lightmaps/tree_house_0.webp`
- `aomap_intensity`: 1.0
- `aomap_colorspace`: `linear` (the grey is stored as the AO value itself, not sRGB-encoded; three.js reads the red channel)

The page keeps these materials lit and uses the map as `aoMap` on UV1 (channel 1). Bake: Cycles AO, 512 samples on the GPU, distance
2.5 m, OIDN, 8 px margin. Not baked (no `aomap`, no UV1): the flowers and their stems, `Lamp_Emit`, `Window_Lit` and the door leaves
(`Door_Wood`, which the page swings).

Toggled by the page: `Window_Lit` (the house's windows, on at night) and `Lamp_Emit` (the lantern, on from dusk), each exported with its
emissive strength.

## Brightness

The brightness tool for lightmapped scenes measures unlit materials (texel x intensity / pi); these are lit, so the table below is base
colour x AO (linear), what the material shows under a white ambient of 1, before the page's sun adds its share. Everything stays well under
1; the walls (the house's boards) read at p50 0.32, the grass at 0.52.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Grass | 2361.6 | 0.520 | 0.569 | 0.601 |
| Hedge | 895.0 | 0.229 | 0.301 | 0.352 |
| Leaf_Mint | 787.5 | 0.604 | 0.738 | 0.776 |
| Leaf_Pink | 393.3 | 0.812 | 0.863 | 0.896 |
| Deck | 380.0 | 0.310 | 0.483 | 0.517 |
| Leaf_Lilac | 297.5 | 0.812 | 0.863 | 0.896 |
| Siding | 177.3 | 0.317 | 0.585 | 0.601 |
| Bark | 164.7 | 0.195 | 0.260 | 0.301 |
| Shingles | 160.6 | 0.057 | 0.387 | 0.567 |
| Stone | 6.4 | 0.523 | 0.604 | 0.604 |
| Puzzle_Board | 5.1 | 0.012 | 0.183 | 0.211 |
| Trim_White | 3.7 | 0.221 | 0.818 | 0.824 |
| Mushroom_Cap | 1.0 | 0.399 | 0.714 | 0.743 |
| Mushroom_Stem | 0.5 | 0.206 | 0.419 | 0.454 |
| Steel | 0.2 | 0.076 | 0.259 | 0.278 |

Low p50s on Shingles, Puzzle_Board and Steel come from faces nobody sees (the roof's underside on the ceiling slab, the board's back on the
wall, the lantern frame's top): they are fully occluded, and they count in the area.

## Gates (CHECKS.txt has the full output)

- Layout check (`check_layout.py`'s rules, run in Blender on the saved scene): 54 of 54 pass. COVER for all 49 colliders but the edge
  walls, STRAY (25 tall solids each over a collider, 34 `decor_` exempt), CLEAR for both links' F spots and arrivals.
- `export_scene.py` writes the same `world/tree_house.json`.
- `build_overworld_greybox.py --check .`: GATES PASS.
- `node tools/worlddoc.mjs check world/tree_house.json`: OK, 0 errors (2 warnings: the links are new to the manifest).
- `glb_inspect --budget tris=300000,mb=8`: pass (23,185 triangles, 1.83 MB).
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Privacy grep over this scene's files (the `.blend` decompressed): 0 hits. The stills carry no comment or APP1 segment.

## check_layout.py

One change, the same line as on `claude/blender-hotel-floor1`: solid art that sits inside a collider at its own height (a flight's upper
steps) counts as standing on it. Without it the tree house's 16 steps fail STRAY, since only the lowest two start below 0.5 m. The
Overworld scenes have no markers, so the in-Blender run passes each link's `at` and `arrive` to the CLEAR rule as constants.

## Sources and licences

Everything here was made for this scene: the geometry by `dress_overworld.py`, the textures by `overworld_textures.py` from noise and
drawing (no downloads, no third-party pixels; the sign lettering uses the system's Arial only to draw pixels, no font file is shipped).
No Meshy, no Higgsfield, no purchases.

## Open

- The page does not read `aomap` yet (the street, meadow and forest are drawn in code); the coordinator wires it with the scene.
- The trunk is round and its collider square: the corners of the collider stand a little proud of the bark (at most 0.4 m, at the four
  diagonals), as on every tree in the glade.
- Inside, the house is lit only by the page; the stills use the greybox's two room lights.
