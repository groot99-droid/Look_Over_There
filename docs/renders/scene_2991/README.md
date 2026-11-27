# scene_2991: the soft play and the carousel

Dressed and lit from the mall greybox (`docs/BLENDER_AREAS.md` section 3; the greybox is draft PR #110, `tools/blender/build_mall_greybox.py`). One of the mall's four painted-sky scenes: a dreamlike mall interior under a painted sky. The photo name is a label only; there are no reference photos, so everything follows the greybox's reading of the space and the written descriptions. Built in Blender 5.2.1 by `tools/blender/build_mall_sky.py` (one script for the four scenes, `--scene scene_2991`), baked twice (the day set and the emergency set on the same lightmap UVs) and exported as art only.

| File | What it is |
|---|---|
| `world/scene_2991.glb` | the art: 2.41 MB, 14886 triangles, 27 draw calls (one primitive per material, each door leaf its own node, origin at its hinge), textures WebP |
| `world/scene_2991.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`: the greybox's file, unchanged (the same JSON, key for key) |
| `world/lightmaps/scene_2991_0.webp`, `_1.webp` | the day set (second UV set, `TEXCOORD_1`): the material's `lightmap` |
| `world/lightmaps/scene_2991_2.webp`, `_3.webp` | the emergency set on the same UVs: `lightmap_night` |
| `blender/scenes/scene_2991.blend` | the saved scene (7.8 MB, Git LFS): `Art` (the unmerged pieces), `Doors` (the leaves), `Layout` (the `COL_` boxes and the empties, the greybox's names), `Export` (merged by material, with the lightmap UVs), `Standins`, `Lights_Day`, `Lights_Night`, `Lights_Always` |
| `tools/blender/build_mall_sky.py` | the re-runnable build; it imports the greybox model, so no coordinate of the layout is typed in |
| `blender/textures/mall_sky/` | the CC0 texture files (below), copied from the wings' and the kit's sets |
| `docs/renders/scene_2991/` | the three review stills (this folder) |

The shared tools are reused unchanged: `export_scene.py`, `check_layout.py`, `pack_scene.py`, `tools/webp_glb.py`. The other painted-sky scenes come from the same script, and their READMEs sit beside this one.

## What is in it

**The soft play and the carousel** (a soft-play court 18 m by 14 m, 7 m to the sky, open through a 6 m opening to a carousel hall 14 m by 14 m, 9 m to the sky; off `wing_entertainment` by an unmarked door, on to `sky_hall_04` by the kit's door in the carousel hall's east wall).
- The soft play: pastel rubber safety tiles, padded vinyl panels on the walls, the greybox's frame dressed as a padded climbing frame (posts, two decks, padded steps, a roller, netting on every side and a net enclosure on top), a yellow slide out of its east side, the ball pit's padded rims with a roll on top and the balls a third of the way up (strays on the floor), the parents' slatted benches, the toddlers' mat with its foam shapes, a PARTY ROOM door painted on the south wall (it does not open), SOFT PLAY RULES, BIRTHDAY PARTIES and SORRY ... BALL PIT CLOSED FOR CLEANING notices.
- The carousel: a round timber deck (the greybox's two boxes cut to a circle, the corners filled) with a painted skirt, the centre column painted with skies and mirror panels between gilt bands, eight brass poles, eight horses as generic shapes (a long rounded body, a neck and a head block, a saddle, folded legs as rods; no face), the canopy with a scalloped red-and-cream valance and a border of bulbs, more bulbs under it (`Lamp_Emit`), a brass crown; a dark terrazzo ring on the floor round it; CAROUSEL, TOKENS and 1 TOKEN A RIDE on the walls.

**The sky, as in the kit's painted-sky hall.** The ceiling is the connector kit's painted sky (`painted_sky_pixels` from `tools/blender/build_kit.py` on `claude/blender-hotel-kit`: the same recipe, palette and soft brushed clouds), carried down a quarter-round cove on every side like a trompe-l'oeil vault, with a white moulding at the cove's foot and at the ceiling's edge. Above a moulded cornice the walls are the kit's sky mural (pale at the horizon, deep blue above). So the sky halls and these rooms read as one place. Below the cornice is the mall's own fabric, as in entrance and the wings: terrazzo in a dark border, beige plaster with terrazzo skirting, painted steel shutters under hand-painted signs, emergency fittings, EXIT over the way back to the wing. Faded and empty, a little wrong.

The mannequins are the page's: every `Spot_mannequin_<n>` is left clear (no dressing within 0.45 m that reaches from its floor to head height, the art of the greybox's own standing solids aside: a bench it sits on, the carousel's deck, the escalator's steps), and so is every link's `at` and `arrive` point.

## Light

| Set | Light | Maps | Material property |
|---|---|---|---|
| day | the day's sky light under the vault (a large soft area), the uplights in the cornice troughs, the floods high on the walls, the room's lamps (`Lamp_Emit` on), the painted sky's own glow | `scene_2991_0`, `scene_2991_1` | `lightmap`, `lightmap_intensity` |
| emergency | the emergency heads (`Emergency_Emit` on, `Lamp_Emit` off) and the painted sky's glow: the mall locked from 20:00 | `scene_2991_2`, `scene_2991_3` | `lightmap_night`, `lightmap_night_intensity` |

**The painted sky glows at all hours.** The ceiling, the coves and the walls' top band are `Sky_Glow`: emission only (base colour black), exported at strength 1 so the page shows the painted sky's own colours, unlit and unbaked, day and night. It is not in `ART_TOGGLES` and nothing switches it, so the room never goes fully dark; in the bakes it is a soft light source in both sets.

The toggled materials are entrance's, switched the same way by the clock: `Lamp_Emit` (strength 10) is on by day and off while the mall is locked; `Emergency_Emit` (strength 6) is on only while it is locked. `Sign_Exit` is emissive and always on. `Window_Lit` does not occur. So the mall's `setLightSet(lk ? "night" : "day")`, `artToggle("Emergency_Emit", lk)` and `artToggle("Lamp_Emit", !lk)` need nothing new.

| Map | Set | Holds | Density | Samples, GPU time | WebP |
|---|---|---|---|---|---|
| `scene_2991_0` | day | the shell: floors, walls below the cornice, the sky mural, borders | 45.0 px/m | 512, 33 s | 105 KB |
| `scene_2991_1` | day | everything in the room, and the door leaves | 45.4 px/m | 512, 44 s | 374 KB |
| `scene_2991_2` | night | the shell: floors, walls below the cornice, the sky mural, borders | 45.0 px/m | 768, 39 s | 105 KB |
| `scene_2991_3` | night | everything in the room, and the door leaves | 45.4 px/m | 768, 48 s | 357 KB |

Cycles on the rented GPU (OptiX), diffuse (direct and indirect, no colour), 8 px margin, OIDN. Faces nobody sees get no texels: the outer skin, faces flat on a floor or against a wall or inside another greybox solid, faces looking up from overhead or down from low down.

**Brightness, the hotel lobby's shoulder.** Each map is written as texel = G L / (C + G L) of the bake's light L, and every baked material's intensity is pi C, so the page shows texture x G L where the light is ordinary and rolls off toward texture x C under a lamp, never clipping. Day: G 2.4, C 1.3; emergency: G 3.0, C 1.1.

## Brightness, as the page shows it

Measured with `lab_display.py` (area-weighted samples over each baked material's triangles, the brightest channel; `>=1` is the share that clips). Day (`lightmap`):

```
material                m2           map       k    p50    p90    p99     >=1
Sky_Mural            428.4  scene_2991_0  4.0841  0.529  0.644  0.719   0.00%
Wall_Plaster         305.1  scene_2991_0  4.0841  0.250  0.281  0.296   0.00%
Floor_Rubber         225.2  scene_2991_0  4.0841  0.546  0.736  0.855   0.00%
Padding_Vinyl        200.7  scene_2991_1  4.0841  0.211  0.520  0.798   0.07%
Floor_Terrazzo       172.5  scene_2991_0  4.0841  0.178  0.289  0.426   0.00%
Net_Mesh             131.3  scene_2991_1  4.0841  0.013  0.017  0.019   0.00%
Trim_Paint           107.0  scene_2991_1  4.0841  0.208  0.254  0.279   0.00%
Floor_Border          47.6  scene_2991_0  4.0841  0.083  0.131  0.192   0.00%
Bench_Wood            34.7  scene_2991_1  4.0841  0.078  0.144  0.200   0.00%
Decal_Dust            33.0  scene_2991_0  4.0841  0.203  0.225  0.243   0.00%
Carousel_Paint        22.7  scene_2991_1  4.0841  0.303  0.666  0.779   0.00%
Metal_Dark            13.8  scene_2991_1  4.0841  0.017  0.056  0.067   0.00%
Ball_Pit              13.5  scene_2991_1  4.0841  0.360  0.640  0.838   0.01%
Door_Leaves           11.1  scene_2991_1  4.0841  0.115  0.517  0.582   0.00%
Horse_Enamel          11.0  scene_2991_1  4.0841  0.631  0.842  0.920   0.01%
Sign_Paint             5.5  scene_2991_1  2.9405  0.205  0.847  0.919   0.00%
Poster_Art             3.4  scene_2991_1  4.0841  0.497  0.766  0.857   0.00%
Slide_Plastic          2.9  scene_2991_1  4.0841  0.902  0.968  0.968   0.00%
Plastic_White          1.4  scene_2991_1  4.0841  0.593  0.839  0.894   0.00%
Carousel_Red           1.3  scene_2991_1  4.0841  0.274  0.629  0.648   0.00%
Brass                  1.0  scene_2991_1  4.0841  0.670  0.748  0.871   0.00%
```

Emergency set (`lightmap_night`, the same measure on the night maps):

```
material                m2           map       k    p50    p90    p99     >=1
Sky_Mural            428.4  scene_2991_2  3.4558  0.312  0.341  0.384   0.00%
Wall_Plaster         305.1  scene_2991_2  3.4558  0.097  0.152  0.198   0.00%
Floor_Rubber         225.2  scene_2991_2  3.4558  0.305  0.447  0.558   0.00%
Padding_Vinyl        200.7  scene_2991_3  3.4558  0.088  0.238  0.392   0.00%
Floor_Terrazzo       172.5  scene_2991_2  3.4558  0.085  0.146  0.219   0.00%
Net_Mesh             131.3  scene_2991_3  3.4558  0.004  0.011  0.011   0.00%
Trim_Paint           107.0  scene_2991_3  3.4558  0.106  0.158  0.173   0.00%
Floor_Border          47.6  scene_2991_2  3.4558  0.037  0.063  0.096   0.00%
Bench_Wood            34.7  scene_2991_3  3.4558  0.037  0.072  0.101   0.00%
Decal_Dust            33.0  scene_2991_2  3.4558  0.092  0.118  0.140   0.00%
Carousel_Paint        22.7  scene_2991_3  3.4558  0.082  0.221  0.247   0.00%
Metal_Dark            13.8  scene_2991_3  3.4558  0.006  0.028  0.036   0.00%
Ball_Pit              13.5  scene_2991_3  3.4558  0.199  0.358  0.507   0.00%
Door_Leaves           11.1  scene_2991_3  3.4558  0.077  0.300  0.340   0.00%
Horse_Enamel          11.0  scene_2991_3  3.4558  0.286  0.465  0.530   0.00%
Sign_Paint             5.5  scene_2991_3  3.4558  0.104  0.468  0.549   0.00%
Poster_Art             3.4  scene_2991_3  3.4558  0.241  0.377  0.426   0.00%
Slide_Plastic          2.9  scene_2991_3  3.4558  0.426  0.477  0.495   0.00%
Plastic_White          1.4  scene_2991_3  3.4558  0.329  0.621  0.750   0.00%
Carousel_Red           1.3  scene_2991_3  3.4558  0.074  0.301  0.320   0.00%
Brass                  1.0  scene_2991_3  3.4558  0.218  0.282  0.327   0.00%
```

`Sky_Glow`, `Lamp_Emit`, `Emergency_Emit` and `Sign_Exit` carry no lightmap.

`Net_Mesh` is mostly transparent (its cords are dark); `Sign_Paint` is capped to 0.72 by day (`CAP`), the boards sit under the floods.

## Review stills (Cycles, 128 samples adaptive, OIDN, 1920 x 1080 JPEG, AgX, the day set)

| | |
|---|---|
| `1_arrival.jpg` (320 KB) | from the arrival point by the wing's door at eye height 1.6 m, facing the arrival's `face` |
| `2_wide.jpg` (268 KB) | the whole room |
| `3_detail.jpg` (261 KB) | a closer look |

![arrival](1_arrival.jpg)
![wide](2_wide.jpg)
![detail](3_detail.jpg)

Blender renders with Blender's lights; the page shows the lightmaps instead. A night still, a look up and a plan were rendered for the owner's sheet only.

## Sources and licences

| Texture | Used for | Source | Author (Poly Haven) | Licence |
|---|---|---|---|---|
| `terrazzo_tiles` diffuse, 1k | the floors (light), the borders, steps, skirting and planters (dark) | https://polyhaven.com/a/terrazzo_tiles | Amal Kumar | CC0 1.0 |
| `painted_metal_shutter` diffuse, 1k | the roller shutters | https://polyhaven.com/a/painted_metal_shutter | Charlotte Baglioni, Dario Barresi, Rico Cilliers | CC0 1.0 |
| `beige_wall_001` diffuse, 1k | the walls below the cornice, the gallery's soffit | https://polyhaven.com/a/beige_wall_001 | Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `plastered_wall_04` diffuse, 1k | the white trim, cornices and casings; the house fronts' stucco (tinted) | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel | CC0 1.0 |
| `dark_wood` diffuse, 1k | benches, the bandstand's and the carousel's decks, the kiosk, the trunks | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `rough_linen` diffuse, 512 | the dust sheets over the street's cafe tables | https://polyhaven.com/a/rough_linen | colormass, Rico Cilliers | CC0 1.0 |
| `concrete_floor_02` diffuse, 1k | in the material list of two scenes, unused in the GLB | https://polyhaven.com/a/concrete_floor_02 | Rob Tuytel | CC0 1.0 |

All are Poly Haven files already in the repo's branches (the wings' `blender/textures/mall_wings/` and the kit's `blender/textures/kit/`), copied byte for byte; nothing new was downloaded. Everything else is own work made by `build_mall_sky.py`: all geometry, and the generated pictures drawn with numpy from fixed seeds: the painted skies (the kit's recipe), the sign atlas (entrance's 5 x 7 pixel font, hand-painted), the poster atlas (notices, holiday posters, the directory, the street's shop displays, windows of sky), the door leaves (unmarked, the kit's white panel door, painted house doors), the EXIT sign, the wall dust; and per scene the court's mosaic, awning stripes, cobbles, paving, house windows, bunting, rubber tiles, soft-play padding, netting, the ball pit, the carousel's painted parts, escalator treads. No Meshy, no Higgsfield, no purchase, no photograph.

## Budgets (measured)

| | Limit | Measured |
|---|---|---|
| `world/scene_2991.glb`, lightmaps aside | at most 8 MB | **2.41 MB** (`glb_inspect.py --budget tris=300000,mb=8`: pass) |
| triangles | at most 300 000 | **14886** (pass) |
| draw calls | at most 250 | **27** |
| textures | WebP | all `image/webp` (`tools/webp_glb.py`) |
| lightmaps | at most 4, 2048 x 2048, 8-bit WebP q90 | **4**: two day maps and their two emergency twins |

## Checks

- **Layout check** (`tools/blender/check_layout.py` on the `.blend`'s `Art`, through `--stage check`): PASS: 40 of 40 checks passed (38 colliders covered; STRAY: 61 tall solid mesh(es), each over a collider; 35 decor_* mesh(es) exempt; CLEAR: the spawn and every link point).
- **Mannequins and links clear** (the build's own check, same stage): KEEP PASS: 8 of 8 places clear.
- **Same layout:** `export_scene.py` writes `world/scene_2991.json` from the `.blend`; it equals the greybox's file (compared as JSON). `python tools/blender/build_mall_greybox.py --check .` still prints GATES PASS.
- `node tools/worlddoc.mjs check world/scene_2991.json`: OK world/scene_2991.json: 38 colliders, 2 doors, 1 markers, 2 links, 0 zones, 4 spots, 0 errors, 3 warnings (each says the scene or a link is new to the manifest).
- **Axes** (`--stage axes`): the marker at the arrival point comes out of the exporter where the game expects it (AXES PASS).
- `node --test shared/*.test.js`: 297 tests, 297 pass.
- **Privacy:** the `.blend` (decompressed), the GLB, the layout file, the lightmaps and the stills hold no user name, absolute path, session id or e-mail; the stills' JPEG comment and APP1 segments are stripped; the GLB's extras are only the four lightmap properties and the doors' properties.

## Rebuild

From the repo root, with Blender 5.2 and Python with Pillow:

```
blender -b --python tools/blender/build_mall_sky.py -- --scene scene_2991 --stage art,check --work <work>      # art, layout file, layout check
blender -b blender/scenes/scene_2991.blend --python tools/blender/build_mall_sky.py -- --scene scene_2991 --stage bake,export,axes --samples 512 --work <work>
blender -b blender/scenes/scene_2991.blend --python tools/blender/build_mall_sky.py -- --scene scene_2991 --stage render --work <work>   # --set night for the emergency set
python tools/blender/pack_scene.py scene_2991 --work <work>
```

## What the coordinator does to wire it in

1. Add `world/scene_2991.glb` and `world/scene_2991.json` to the scene's files in the manifest, with the greybox's links (listed in the greybox README).
2. Apply the lightmaps with `applyLightmaps` and the mall's clock toggles, as for entrance. `Sky_Glow` needs nothing: it is an ordinary emissive material.
3. Draw the mannequins at the `Spot_mannequin_<n>` places; swing the door leaves by name (`DoorLeaf_<id>` nodes, origin at the hinge).

## Open

- The page's view of the bake has not been seen in a browser; the first in-game screenshot is the first look at it under the page's shading, and at how the unlit `Sky_Glow` sits beside the baked mural.
- The sky-hall doors' far side is the kit's sky hall (`world/kit/sky_hall.glb`); its sky and this one share the recipe but not the bake.
- The carousel's deck is round in the art; the greybox's colliders are two crossed boxes, so the deck's four rims just outside the boxes are passable art (decor) and the boxes' four corners beyond the circle are invisible 0.3 m steps (the page climbs them).
