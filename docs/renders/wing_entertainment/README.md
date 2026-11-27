# wing_entertainment: a mall concourse

Dressed and lit from the mall greybox (`docs/BLENDER_AREAS.md` section 3; the greybox is draft PR #110, `tools/blender/build_mall_greybox.py`). One of the three concourses off part 1's atrium (`entrance`), built to read as the same building: entrance's terrazzo in a dark border, its beige plaster in two shades, painted steel roller shutters under hand-painted fascia signs, plywood hoardings, tube scaffolding with dust sheets, a glazed skylight strip being repaired (a few broken panes boarded from inside), whitewashed glass; old, abandoned and halfway through a refit nobody finished. Built in Blender 5.2.1 by `tools/blender/build_mall_wings.py` (one script for the three wings, `--scene wing_entertainment`), baked twice (the day set and the emergency set on the same lightmap UVs) and exported as art only. There are no reference photos; everything follows the written descriptions.

| File | What it is |
|---|---|
| `world/wing_entertainment.glb` | the art: 2.89 MB, 25552 triangles, 31 draw calls (one primitive per material, and each door leaf its own node, origin at its hinge), textures WebP |
| `world/wing_entertainment.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`. It is the greybox's file, unchanged (the same JSON, key for key) |
| `world/lightmaps/wing_entertainment_0.webp`, `_1.webp` | the day set (second UV set, `TEXCOORD_1`): the material's `lightmap` |
| `world/lightmaps/wing_entertainment_2.webp`, `_3.webp` | the emergency set on the same UVs: `lightmap_night` |
| `blender/scenes/wing_entertainment.blend` | the saved scene (4.3 MB, Git LFS): `Art` (the unmerged pieces), `Doors` (the seven leaves), `Layout` (the `COL_` boxes and the empties, the greybox's names), `Export` (merged by material, with the lightmap UVs), `Standins` (the arrival marker), `Lights_Day`, `Lights_Night`, `Lights_Always` |
| `tools/blender/build_mall_wings.py` | the re-runnable build; it imports the greybox model, so no coordinate of the layout is typed in |
| `blender/textures/mall_wings/` | entrance's CC0 texture files (below), copied so this build does not depend on the entrance branch |
| `docs/renders/wing_entertainment/` | the three review stills (this folder) |

The shared tools are reused unchanged: `export_scene.py`, `check_layout.py`, `pack_scene.py`, `tools/webp_glb.py`. The other two wings, `wing_books` and `wing_cinema`, come from the same script.

## What is in it

**The entertainment wing** (runs east from the atrium; not turned). Five bays a side:
- North: BOWLING, LASER TAG, **the SOFT PLAY door** (to `scene_2991`): padded vinyl panels in red, yellow, blue and green either side of the door, SOFT PLAY in bright letters on its board, BIRTHDAY PARTIES and SORRY ... CLOSED FOR CLEANING notices; PRIZE COUNTER, KARAOKE boarded over.
- South: **the ARCADE front** (the greybox's CLAW MACHINES bay; its sign reads ARCADE): the shutter painted with a mural (pixel invaders, a grid floor, PLAY, HIGH SCORE), a border of bulbs round the ARCADE board; the unmarked door between two shutters (to `scene_3008`), MINI GOLF, VR ZONE, the STAFF ONLY door.
- The far end: **the food court's entrance**, glass doors in a whitewashed glazed screen under the FOOD COURT sign with its bulbs.
- Blade signs: ENTERTAINMENT, FOOD COURT >. Posters (BOWLING, PRIZES) on the walls. The kiddie rides and claw machines under dust sheets on their bases.

Common to the three wings: the shell is the greybox's 40 m by 14 m, 6 m high hall. A terrazzo field in a dark border with a dark band across the hall at each pair of pilasters, terrazzo skirting; beige plaster to the fascia line and a darker shade above it, a painted band at 4.4 m; painted pilasters with terrazzo plinths. The skylight strip (36 m by 5 m) has a pitched glazed lantern of dirty wired glass with four broken panes boarded from inside. Twenty ceiling downlights either side of it, about a third of them dead. The atrium's glass doors at the near end in a whitewashed glazed screen (the wing is closed off for the works), with an EXIT sign and the wing's name over them and the mall directory beside them. Emergency fittings (twin heads) on every pilaster and over both ends' doors. The greybox's scaffolds are dressed as tube scaffolding (standards on base plates, ledgers, transoms, braces, guard rails, plank decks with toe boards, ties to the wall, a work lamp on the first one) with a dust sheet hung on or thrown over each. Drop cloths, paint tins, plasterboard, cement bags and a cable on the floor, kept off the walking lines.

The mannequins are the page's: every `Spot_mannequin_<n>` is left clear (no dressing within 0.45 m that reaches below head height; the art of the greybox's own solids, such as a sheeted kiddie ride, stays where the greybox put it), and so is every link's `at` and `arrive` point.

## Light

| Set | Light | Maps | Material property |
|---|---|---|---|
| day | the sun (from high in the south-west, the mall's sun as in entrance) and the sky through the skylight strip, the working downlights and the work lamp (`Lamp_Emit` on) | `wing_entertainment_0`, `wing_entertainment_1` | `lightmap`, `lightmap_intensity` |
| emergency | the emergency heads alone (`Emergency_Emit` on, `Lamp_Emit` off, no sky): the mall locked from 20:00 | `wing_entertainment_2`, `wing_entertainment_3` | `lightmap_night`, `lightmap_night_intensity` |

The toggled materials are entrance's, switched the same way by the clock: `Lamp_Emit` (strength 10: the downlights' lenses, the work lamp, the bulbs round the signs, the poster cases' strips) is on by day and off while the mall is locked; `Emergency_Emit` (strength 6: the emergency heads' lenses) is on only while it is locked. `Sign_Exit` (the EXIT sign) is emissive and always on. `Window_Lit` does not occur. So `cityLook`'s `setLightSet(lk ? "night" : "day")`, `artToggle("Emergency_Emit", lk)` and `artToggle("Lamp_Emit", !lk)` for the mall need nothing new.

| Map | Set | Holds | Density | Samples, GPU time | WebP |
|---|---|---|---|---|---|
| `wing_entertainment_0` | day | the shell: floor, walls, ceiling, trim | 37.5 px/m (scaled: Ceiling_Paint 20.6, Decal_Dust 22.5) | 512, 58 s | 191 KB |
| `wing_entertainment_1` | day | everything in it, and the door leaves | 33.6 px/m (scaled: Skylight_Glass 4.0) | 512, 75 s | 387 KB |
| `wing_entertainment_2` | night | the shell: floor, walls, ceiling, trim | 37.5 px/m (scaled: Ceiling_Paint 20.6, Decal_Dust 22.5) | 768, 48 s | 142 KB |
| `wing_entertainment_3` | night | everything in it, and the door leaves | 33.6 px/m (scaled: Skylight_Glass 4.0) | 768, 108 s | 262 KB |

Cycles on the rented GPU (OptiX), diffuse (direct and indirect, no colour), 8 px margin, OIDN. The skylight's panes are hidden while baking so the sun and the sky come in; their own texels are filled flat (bright by day, a dull glow at night). Faces nobody sees get no texels: the shell's outer skin, the joints between wall pieces, the wall behind each bay's front and fascia and behind the pilasters, faces flat against a wall or the floor, faces looking up from above 2.2 m or down from below 0.8 m.

**Brightness, the hotel lobby's shoulder.** Each map is written as texel = G L / (C + G L) of the bake's light L, and every baked material's intensity is pi C, so the page shows texture x G L where the light is ordinary and rolls off toward texture x C in the sun's patch, never clipping. Day: G 5.5, C 1.3; emergency: G 7, C 1.1 (`CURVE` in the build).

## Brightness, as the page shows it

Measured with `lab_display.py` (area-weighted samples over each material's triangles, the brightest channel; `>=1` is the share that clips). Day (`lightmap`):

```
material                m2           map       k    p50    p90    p99     >=1
Floor_Terrazzo       481.3 wing_entertainment_0  4.0841  0.230  0.351  0.506   0.00%
Ceiling_Paint        418.2 wing_entertainment_0  4.0841  0.202  0.244  0.372   0.00%
Metal_Dark           270.6 wing_entertainment_1  4.0841  0.060  0.067  0.068   0.00%
Wall_Plaster         239.0 wing_entertainment_0  4.0841  0.228  0.299  0.373   0.00%
Skylight_Glass       224.5 wing_entertainment_1  2.8903  0.652  0.728  0.728   0.00%
Trim_Paint           177.3 wing_entertainment_0  4.0841  0.435  0.589  0.709   0.00%
Wall_Upper           174.1 wing_entertainment_0  4.0841  0.147  0.185  0.212   0.00%
Floor_Border         106.6 wing_entertainment_0  4.0841  0.091  0.148  0.220   0.00%
Decal_Dust            87.8 wing_entertainment_0  4.0841  0.214  0.251  0.282   0.00%
Cloth_Sheet           85.1 wing_entertainment_1  4.0841  0.376  0.537  0.613   0.00%
Shutter_Metal         82.3 wing_entertainment_1  4.0841  0.142  0.205  0.239   0.00%
Scaffold_Board        65.7 wing_entertainment_1  4.0841  0.056  0.116  0.163   0.00%
Hoarding_Ply          52.2 wing_entertainment_1  4.0841  0.182  0.262  0.331   0.00%
Metal_Steel           43.0 wing_entertainment_1  4.0841  0.182  0.365  0.471   0.00%
Door_Leaves           40.3 wing_entertainment_1  4.0841  0.303  0.457  0.532   0.00%
Sign_Paint            39.2 wing_entertainment_1  4.0841  0.072  0.687  0.902   0.02%
Glass_Whitewash       37.8 wing_entertainment_1  4.0841  0.506  0.696  0.782   0.00%
Decal_Stain           30.9 wing_entertainment_0  4.0841  0.000  0.081  0.086   0.00%
Poster_Art            19.2 wing_entertainment_1  4.0841  0.016  0.670  0.875   0.00%
Padding_Vinyl         15.0 wing_entertainment_1  4.0841  0.322  0.581  0.846   0.00%
Plastic_White          6.1 wing_entertainment_1  4.0841  0.307  0.618  0.800   0.00%
Clutter_Paint          4.0 wing_entertainment_1  4.0841  0.522  0.641  0.653   0.00%
```

Emergency set (`lightmap_night`, the same measure on the night maps):

```
material                m2           map       k    p50    p90    p99     >=1
Floor_Terrazzo       481.3 wing_entertainment_2  3.4558  0.096  0.159  0.237   0.00%
Ceiling_Paint        418.2 wing_entertainment_2  3.4558  0.040  0.046  0.049   0.00%
Metal_Dark           270.6 wing_entertainment_3  3.4558  0.000  0.007  0.022   0.00%
Wall_Plaster         239.0 wing_entertainment_2  3.4558  0.049  0.087  0.166   0.00%
Skylight_Glass       224.5 wing_entertainment_3  1.9635  0.036  0.041  0.043   0.00%
Trim_Paint           177.3 wing_entertainment_2  3.4558  0.076  0.179  0.307   0.00%
Wall_Upper           174.1 wing_entertainment_2  3.4558  0.026  0.032  0.038   0.00%
Floor_Border         106.6 wing_entertainment_2  3.4558  0.011  0.035  0.061   0.00%
Decal_Dust            87.8 wing_entertainment_2  3.4558  0.032  0.082  0.122   0.00%
Cloth_Sheet           85.1 wing_entertainment_3  3.4558  0.091  0.209  0.343   0.00%
Shutter_Metal         82.3 wing_entertainment_3  3.4558  0.038  0.058  0.078   0.00%
Scaffold_Board        65.7 wing_entertainment_3  3.4558  0.012  0.071  0.127   0.00%
Hoarding_Ply          52.2 wing_entertainment_3  3.4558  0.022  0.086  0.125   0.00%
Metal_Steel           43.0 wing_entertainment_3  3.4558  0.039  0.175  0.354   0.00%
Door_Leaves           40.3 wing_entertainment_3  3.4558  0.000  0.151  0.178   0.00%
Sign_Paint            39.2 wing_entertainment_3  3.4558  0.021  0.167  0.401   0.00%
Glass_Whitewash       37.8 wing_entertainment_3  3.4558  0.245  0.274  0.296   0.00%
Decal_Stain           30.9 wing_entertainment_2  3.4558  0.000  0.036  0.039   0.00%
Poster_Art            19.2 wing_entertainment_3  3.4558  0.010  0.242  0.479   0.00%
Padding_Vinyl         15.0 wing_entertainment_3  3.4558  0.062  0.127  0.194   0.00%
Plastic_White          6.1 wing_entertainment_3  3.4558  0.072  0.252  0.756   0.00%
Clutter_Paint          4.0 wing_entertainment_3  3.4558  0.213  0.301  0.323   0.00%
```

By day the main surfaces are well under p90 0.9 and p99 0.98, and the walls read (lower plaster p50 about 0.2, upper about 0.14). Locked, the wing is dark by design, as entrance is: pools of cold light under the emergency heads, the floor between them dim. `Skylight_Glass` is filled flat. `Lamp_Emit`, `Emergency_Emit` and `Sign_Exit` carry no lightmap.

## Review stills (Cycles, 128 samples adaptive, OIDN, 1920 x 1080 JPEG, AgX, exposure 0, the day set)

| | |
|---|---|
| `1_arrival.jpg` (335 KB) | from the arrival point by the atrium's doors at eye height 1.6 m, facing the arrival's `face` (down the wing) |
| `2_wide.jpg` (279 KB) | the whole wing from the far end's corner, looking back to the atrium |
| `3_detail.jpg` (251 KB) | the wing's theme |

![arrival](1_arrival.jpg)
![wide](2_wide.jpg)
![detail](3_detail.jpg)

Blender renders with Blender's lights; the page shows the lightmaps instead. A night still, a second detail and a plan were rendered for the owner's sheet only.

## Sources and licences

| Texture | Used for | Source | Author (Poly Haven) | Licence |
|---|---|---|---|---|
| `terrazzo_tiles` diffuse, 1k | the floor (light) and its border, bands, skirting and plinths (dark) | https://polyhaven.com/a/terrazzo_tiles | Amal Kumar | CC0 1.0 |
| `painted_metal_shutter` diffuse, 1k | the roller shutters | https://polyhaven.com/a/painted_metal_shutter | Charlotte Baglioni, Dario Barresi, Rico Cilliers | CC0 1.0 |
| `plywood` diffuse, 1k | the hoardings, the boarded panes, the scaffold boards and battens | https://polyhaven.com/a/plywood | Rob Tuytel | CC0 1.0 |
| `beige_wall_001` diffuse, 1k | the walls (two shades) and the ceiling | https://polyhaven.com/a/beige_wall_001 | Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `dark_wood` diffuse, 1k | the cinema's kiosk, the dead ficus | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `rough_linen` diffuse, 512 | the dust sheets, drop cloths, cement bags | https://polyhaven.com/a/rough_linen | colormass, Rico Cilliers | CC0 1.0 |
| `concrete_floor_02` diffuse, 1k | in the `.blend`'s material list only (not in the GLB) | https://polyhaven.com/a/concrete_floor_02 | Rob Tuytel | CC0 1.0 |

All seven are entrance's files (`blender/textures/entrance/` on `claude/blender-entrance-v2`), copied byte for byte; nothing new was downloaded. Everything else is own work made by `build_mall_wings.py`: all geometry, and the generated pictures drawn with numpy from fixed seeds: the sign atlas (entrance's 5 x 7 pixel font and hand-painted look, extended with B, J, Q, Z and a few marks), the poster atlas (invented film posters, the bookshop window, the arcade's mural, printed notices, the restroom pictograms, the directory), the door leaves (glass, staff, restroom, unmarked, site), the restroom tiles, the soft-play padding, the EXIT sign, the whitewash, the wired glass, the wall dust and the dried puddles. No Meshy, no Higgsfield, no purchase, no photograph.

## Budgets (measured)

| | Limit | Measured |
|---|---|---|
| `world/wing_entertainment.glb`, lightmaps aside | at most 8 MB | **2.89 MB** (`glb_inspect.py --budget tris=300000,mb=8`: pass) |
| triangles | at most 300 000 | **25552** (pass) |
| draw calls | at most 250 | **31** |
| textures | WebP | all `image/webp` (`tools/webp_glb.py`) |
| lightmaps | at most 4, 2048 x 2048, 8-bit WebP q90 | **4**: two day maps and their two emergency twins |

## Checks

- **Layout check** (`tools/blender/check_layout.py` on the `.blend`'s `Art`, through `--stage check`): PASS: 70 of 70 checks passed (68 colliders covered; STRAY: 108 tall solid meshes, each over a collider, 8 decor_ exempt; CLEAR: the spawn).
- **Mannequins and links clear** (the build's own check, same stage): 13 of 13 places clear.
- **Same layout:** `export_scene.py` writes `world/wing_entertainment.json` from the `.blend`; it equals the greybox model's `--preview` output (compared as JSON). `python tools/blender/build_mall_greybox.py --check .` still prints GATES PASS.
- `node tools/worlddoc.mjs check world/wing_entertainment.json`: OK, 0 errors (the six warnings say the scene and its links are new to the manifest).
- **Axes** (`--stage axes`): the marker at the arrival point comes out of the exporter where the game expects it.
- `node --test shared/*.test.js`: 297 tests, 297 pass.
- **Privacy:** the `.blend` (decompressed), the GLB's JSON, the lightmaps and the stills hold no user name, absolute path, session id or e-mail; the stills' JPEG comment and APP1 segments are stripped; the GLB's extras are only the four lightmap properties.

## Rebuild

From the repo root, with Blender 5.2 and Python with Pillow:

```
blender -b --python tools/blender/build_mall_wings.py -- --scene wing_entertainment --stage art --work <work>      # art, layout file, layout check
blender -b blender/scenes/wing_entertainment.blend --python tools/blender/build_mall_wings.py -- --scene wing_entertainment --stage bake --samples 512 --work <work>
blender -b blender/scenes/wing_entertainment.blend --python tools/blender/build_mall_wings.py -- --scene wing_entertainment --stage export --work <work>
blender -b blender/scenes/wing_entertainment.blend --python tools/blender/build_mall_wings.py -- --scene wing_entertainment --stage render --work <work>   # --set night for the emergency set
python tools/blender/pack_scene.py wing_entertainment --work <work>
```

## What the coordinator does to wire it in

1. Add `world/wing_entertainment.glb` and `world/wing_entertainment.json` to the scene's files in the manifest, with the greybox's links (the atrium's side of each is listed in the greybox README).
2. Apply the lightmaps with `applyLightmaps` and the mall's clock toggles, as for entrance.
3. Draw the mannequins at the `Spot_mannequin_<n>` places; swing the door leaves by name (`DoorLeaf_<id>` nodes, origin at the hinge; the layout file has their hinge, yaw and swing).

## Open

- The page's view of the bake has not been seen in a browser; the first in-game screenshot from the arrival point is the first look at it under the page's shading.
- The doors stay closed in the art; when the page swings a leaf, what is behind it is the page's black background until the link loads the next scene.
- The atrium's side of the link (an opening in entrance's wall) is for the coordinator; entrance was not touched.
