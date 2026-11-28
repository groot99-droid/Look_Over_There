# galleries: the museum hall

The second scene of the Blender plan (`docs/BLENDER.md`, "2. galleries"). A small municipal museum after hours, as the night guard sees it on the 20:00 shift. Built in Blender 5.2.1 from `blender/layout/galleries.json`, baked in full at night (the scene is only ever played at night) and exported as art only. The structure follows the apartment pilot (`docs/renders/apartment/README.md`, `tools/blender/build_apartment.py`).

**Version 2** takes its look from the owner's Chronicle Museum (the Earth world build, `_Museum`), as the owner asked, and is brighter than version 1. The red gallery now has the Chronicle's mouldings and cornice, a panelled dark wood wainscot under a cream dado rail, and salon-grid hangs of empty frames whose style follows the era bay by bay. Picture lights hang over the main frames. Three chandeliers and two door sconces light the hall, the skylights sit in laylight coffers, the door has a Doric pediment surround, the plinths are marble pedestals, and two pairs of benches stand in the aisle. Version 2 kept the layout and the colliders. The one later layout change is the two doorways to the side galleries (below, "Wing"); every gate still passes.

**Version 3 (2026-11-26)** follows the owner's words: "Those warriors and the T. rex should be in the main museum hall instead of those faceless people and the frames on the walls need pictures from the other scenes of the games". Three things changed (section "Version 3" below has the details):

- **Every frame has a picture** (41 of them) of another scene of the game: the review stills of the apartment, laboratory, factory floor, main floor and side galleries, and new renders of the store floors (B1, L1 to L4) and the exterior. The pale ghosts of removed paintings are gone.
- **Fixed exhibits in the GLB:** a T. rex skeleton (6.5 m) on a low marble platform across the north end, and the British redcoat and the Mongol archer on plinths either side of the south door, facing the hall. They are solid: six new colliders (`COL_` boxes in the build, written to `world/galleries.json`).
- **The bake's stand-ins are the six warriors** that will be the moving statues (pharaoh, Viking, terracotta, knight, samurai, Roman, in `MUSEUM.names` order), not the six-box figure. They are still never exported: the page draws and moves the statues.

The layout, the plinths, the doorways and every other collider are unchanged. The side wing (`galleries_wing`) is untouched.

| File | What it is |
|---|---|
| `world/galleries.glb` | the art: 6.53 MB, 103 703 triangles, 25 materials and 29 draw calls (one primitive each, the four door leaves are nodes of their own), 12 WebP textures |
| `world/galleries.json` | the collision file: the code's, except for the two wing doorways (below, "Wing") and the six exhibit boxes ("Version 3") |
| `world/lightmaps/galleries_0.webp` .. `galleries_3.webp` | the baked light, four maps (second UV set, `TEXCOORD_1`) |
| `blender/scenes/galleries.blend` | the saved scene (Git LFS): `Art` (the unmerged pieces), `Export` (merged by material, with the lightmap UVs), `Standins` (the six warriors), `Colliders` (the exhibits' `COL_` boxes), `Lights` |
| `tools/blender/galleries_frames.py` | the picture hang (every frame), read by the build and the atlas maker |
| `tools/blender/make_galleries_paintings.py`, `blender/textures/galleries/paintings_atlas.jpg` / `.json` | the pictures in the frames: one atlas, a rectangle per frame |
| `tools/blender/render_galleries_views.py` | the views of the store floors and the exterior that the atlas uses |
| `tools/blender/prep_galleries_exhibits.py`, `blender/models/galleries/exhibits/` | static copies of the owner's character models (rest pose, no rig, 1K texture): the T. rex, the two door warriors and the six statue stand-ins |
| `tools/blender/build_galleries.py` | the re-runnable build (reads the layout; no hand-copied coordinates) |
| `blender/textures/galleries/` | the four CC0 texture files the build reads (`herringbone_parquet`, `marble_01`, `plastered_wall_04`, `dark_wood`) |
| `blender/models/galleries/ph-chandelier-02/`, `ph-bench/` | the two CC0 Poly Haven models the hall uses (glTF, bin, diffuse map), copied from the Chronicle Museum's `assets/models/` |
| `docs/renders/galleries/` | the three review stills (this file's folder) |

The shared tools are reused unchanged: `tools/blender/check_layout.py`, `tools/blender/pack_scene.py`, `tools/webp_glb.py`, `tools/blender/dump_layout.mjs`.

## What changed in version 2, and why

The owner said "For the museum use inspirations from my museum earth world build". The Chronicle Museum builds its rooms in `web/js/procroom.js` (geometry, mouldings, frames, fixtures, pedestals), `web/js/doors.js` (themed doors), `web/js/matlib.js` (materials) and `build_layout.py` (room styles, the salon packer, fixtures). These are the features carried over, each adapted to this hall's fixed layout and to the page's rules:

| Chronicle Museum feature | Where it is there | Here |
|---|---|---|
| Profile-swept mouldings, mitred at inside corners | `procroom.js` `PROFILES`, `extrudeRun` | the same skirting, dado and picture-rail profiles, and its room cornice scaled from 7 m to this 5 m hall (0.4 m tall, 0.29 m deep), swept along the walls and mitred; a frieze band under the cornice |
| Wall and trim colours | `build_layout.ROOM_STYLE`, `matlib.js` | the Classical Antiquity room's red (`#8b3a2f`), lifted for a night bake; cream painted trim (`#efe6d6`); white ceiling; dark marble skirting (the Grand Hall's) |
| Wainscot | the hall's dado | the dark wood wainscot of version 1, now panelled (bolection rings about 1.25 m apart) under a cream dado rail |
| Salon-grid hang | `build_layout._shelves` / `_vertical` | in each of the four bays of the long walls: a large frame centred at eye height, smaller ones either side, a row above bottom-aligned on a shared line at 2.75 m; the upper row hangs on brass wires from the picture rail |
| Bevelled frames chosen by era | `procroom.js` `frameGeometry`, `build_layout.frame_style` | cushion-moulding profiles swept round each frame. From the door north the bays run through the eras as the Chronicle's rooms do: gilt simple, gilt ornate, dark wood, black lacquer, with the small works in the era's lighter frame (`frame_small`: dark wood, gilt simple, dark wood, thin metal). A grand gilt ornate frame and two gilt simple ones on the north wall, two beside the door |
| Picture lights over large works | `FX picture_light` | brass hoods with lit tubes over every eye-row main frame, the north wall's three and the door's two (13 in all) |
| Chandeliers | `FX chandelier`, Poly Haven `Chandelier_02` in its hall | three `Chandelier_02` (CC0), one over each pair of plinths down the middle, on brass rods from ceiling roses, hanging from 4.15 to 3.30 m |
| Laylights | `FX laylight` (a lit pane in a painted trim frame) | the four skylights keep their moonlit panes and now sit in cream coffers of two stepped bands |
| Sconces by the doors | `FX sconce` | two brass sconces either side of the door at 2.6 m |
| Themed doors | `doors.js` `doric-pediment` | white marble casing, fluted pilasters with gilt capitals, an entablature and a pediment; the EXIT sign sits on the frieze |
| Pedestals | `procroom.js` props: `plinth` (dark marble under a white lip) and `column` | the six plinths are its block pedestals: a white marble base, a dark marble die, a white marble cap. Its column pedestals do not fit: the page hangs each statue's 1.6 m name plate on the plinth's face toward the hall, which needs a flat face, and a round shaft would leave the collider's corners bare |
| Benches | Poly Haven `painted_wooden_bench` in its hall | four, back to back in two pairs in the aisle under the second and third laylights, facing the salon walls |

**The frames stayed empty in version 2** (version 3 hangs pictures in them). `docs/WORLD.md` does not give the paintings a story, but `docs/BLENDER.md` sets the look as "parquet, picture rails and empty frames". Version 1's pale ghosts of removed paintings are still on the walls above the plinths. So no painting images were added, and no image licence comes into it.

**Brighter.** Version 1's stills were too dark at exposure 0. Version 2 adds the three chandeliers (380 W each) and the two sconces (45 W). The picture lights go from 90 to 140 W (280 W on the big north frame), the plinth spots from 950 to 1100 W, the moon from 1.4 to 2.6 W/m², and the night sky through the laylights from 25 to 40. The ceiling, trim and marble are now light, so they carry the light round the room. The stills are still rendered at exposure 0, so they show the level the lightmaps hold.

**Kept from version 1:** the hall shell, the herringbone parquet in its marble border, the gallery spots on their two tracks, the ghosts of removed paintings, the EXIT sign, the closed double door, the stand-in statues for the bake, and every gate. Version 2 made no change to `world/galleries.json`; the wing doorways later did (below).

## Version 3: warriors, the T. rex and pictures (2026-11-26)

The owner asked: "Those warriors and the T. rex should be in the main museum hall instead of those faceless people and the frames on the walls need pictures from the other scenes of the games".

### The pictures

All 41 frames now hold a picture, and the ghost decals (and their `Decal_Ghost` material) are gone. Each canvas is a flat quad 5 mm off the wall, just inside its frame's opening. It runs 1.2 cm under the frame's inner lip on every side, so no wall shows at the edge. All canvases share one matte material, `Canvas_Paintings`, which uses one 2048 x 2048 atlas (`blender/textures/galleries/paintings_atlas.jpg`, 310 px per metre of canvas). Each canvas is its own island on lightmap 1 (`FLAT_UV`), so it bakes with the walls.

- **Sources (33):** the review stills of the built scenes (`docs/renders/<scene>/*.jpg` for apartment, laboratory, factory_floor, main_floor and galleries_wing; 15 stills), and 18 new views of the store floors and the exterior. `tools/blender/render_galleries_views.py` rendered those from `world/B1.glb`, `L1.glb` .. `L4.glb` and `Exterior.glb`: Cycles on the GPU, 128 samples, OIDN, 1024 x 768. The floors are lit by their own emissive fittings and the exterior by a low evening sun. The script first renders about ten candidate views per floor (ray-cast standing places and each floor's security cameras), and the 18 chosen ones are its `VIEWS`: three each of B1, L1, L2, L4 and the exterior, and two of L3 (its open floor is plainer). The source views themselves are not committed; the script makes them again.
- **The hang:** `tools/blender/make_galleries_paintings.py` crops every picture to its frame's opening and packs the atlas. It also writes `paintings_atlas.json` (per frame: the picture, the crop, the UV rectangle). The large works take the best views first (its `HERO` list): the north wall's big frame shows L4's open floor, and the eye-row main frames show L1, factory_floor, B1, main_floor and L2. No picture repeats within a hang (a bay of a long wall, the north wall, the door wall), and the two walls of a bay share none. A picture used twice gets a different crop the second time; 8 of the 33 are used twice. Dark pictures are lifted until their 98th-percentile luminance reaches 0.92 (at most x 1.8), so they read on a wall at night.
- **The hang itself** (bays, salon grid, eras) moved from the build into `tools/blender/galleries_frames.py`, so the build and the atlas read the same frames. The frames did not change. `Frame_Gold` is darker than in version 2 (0.56, 0.36, 0.09 instead of 0.87, 0.56, 0.14): under the picture lights it displayed above 1 in the page.

### The exhibits (in the GLB, solid)

The models are the owner's character models (the characters job's `models/characters/<id>.glb`, rigged, from Higgsfield). `tools/blender/prep_galleries_exhibits.py` makes static copies of them into `blender/models/galleries/exhibits/`. Each copy is in its rest pose with the armature and the bone-shape spheres dropped, is one mesh, and has its texture cut to 1024 px (`<id>.glb` plus `<id>_1k.jpg`). The build reads only these copies, so a later fix to the rigged models needs this step run again.

| Exhibit | Where (game) | Size | Faces |
|---|---|---|---|
| T. rex skeleton (`Exhibit_TRex`) | centred (0, 0.3, -17.6) on a 0.3 m marble platform, x -3.7 to 3.7, z -19.6 to -15.6 | 6.5 m long (scale 0.54 of the real 12 m model), 2.02 m tall | head to the east, turned 15 degrees toward the south (the visitors) |
| British redcoat (`Exhibit_Redcoat`) | on its plinth at (-2.75, 0.6, 4.9), west of the door | 1.75 m (scale 3.83) | the hall (north) |
| Mongol archer (`Exhibit_Mongol`) | on its plinth at (2.75, 0.6, 4.9), east of the door | 1.75 m (scale 3.23) | the hall (north) |

The warrior models are 0.43 to 0.54 m miniatures. In the hall they stand life-size (1.75 m), as the statues they replace do; the side wing keeps its own miniatures at scale 1. The plinths and the platform are built like the hall's plinths: a white marble base, a dark marble die and a white marble cap, 0.9 m square and 0.6 m high for the warriors. Four new gallery spots light them from the two tracks: two 1100 W spots, 44 degrees, on the T. rex, and a 660 W spot on each warrior. The aisle (x -1.5 to 1.5) stays clear down to z = -15. The statues' paths (z = -13, from x = 4.4 to 1.45 and -4.4 to -1.45) stay clear too. The door (reach 1.8 from (0, 5.3)) and the arrival point (0, 4.4) are at least 2.15 m from the warriors' plinths.

**Colliders.** Each exhibit has two `COL_` boxes in the build's `Colliders` collection (never rendered or exported as art): its pedestal, and the figure's own box above it. `--stage export` adds them to `world/galleries.json` through `tools/blender/export_scene.py`, after the hall's 16, in name order (22 colliders now). The exact boxes (game x, y, z):

| Collider | min | max |
|---|---|---|
| `Exhibit_Mongol` | [2.316, 0.6, 4.557] | [3.184, 2.35, 5.243] |
| `Exhibit_Mongol_Plinth` | [2.3, 0.0, 4.45] | [3.2, 0.6, 5.35] |
| `Exhibit_Redcoat` | [-3.044, 0.6, 4.685] | [-2.456, 2.35, 5.115] |
| `Exhibit_Redcoat_Plinth` | [-3.2, 0.0, 4.45] | [-2.3, 0.6, 5.35] |
| `TRex_Platform` | [-3.7, 0.0, -19.6] | [3.7, 0.3, -15.6] |
| `TRex_Skeleton` | [-3.367, 0.3, -18.363] | [3.188, 2.319, -16.81] |

**The matching `shared/museum.js` change (for the coordinator; this branch does not touch `shared/`).** It goes on top of the "Wing" change below. With both applied, `museumDoc()` gives exactly the new `world/galleries.json`:

```diff
@@ MUSEUM
   names: ["THE SWIMMER", "WOMAN WITH A JUG", "THE ORATOR", "BOY AND GOOSE", "THE WATCHER", "UNKNOWN FIGURE"],
+  // the fixed exhibits built into world/galleries.glb (build_galleries.py): solid, never moving; each a pedestal and the figure's box above it
+  exhibits: [
+    {s: "Exhibit_Mongol", min: [2.316, 0.6, 4.557], max: [3.184, 2.35, 5.243]},
+    {s: "Exhibit_Mongol_Plinth", min: [2.3, 0, 4.45], max: [3.2, 0.6, 5.35]},
+    {s: "Exhibit_Redcoat", min: [-3.044, 0.6, 4.685], max: [-2.456, 2.35, 5.115]},
+    {s: "Exhibit_Redcoat_Plinth", min: [-3.2, 0, 4.45], max: [-2.3, 0.6, 5.35]},
+    {s: "TRex_Platform", min: [-3.7, 0, -19.6], max: [3.7, 0.3, -15.6]},
+    {s: "TRex_Skeleton", min: [-3.367, 0.3, -18.363], max: [3.188, 2.319, -16.81]},
+  ],
 };
@@ museumColliders()
   MUSEUM.homes.forEach(([x, z], i) => add("Plinth_" + i, [x - p, 0, z - p], [x + p, 0.6, z + p]));
+  MUSEUM.exhibits.forEach(e => add(e.s, e.min, e.max));
   return c;
```

### The statues' stand-ins

`Standins` now holds the six warriors that are to become the moving statues, in `MUSEUM.names` order on homes 0 to 5: pharaoh, Viking, terracotta, knight, samurai, Roman. They are static copies, 1.75 m tall, turned to face the hall as `placeStatues` turns them. They throw the plinth spots' shadows in the bake and show in the stills; they are never exported. For the page's statues to match the bake's shadows, draw each warrior at the scale it has here, so that it stands 1.75 m tall: pharaoh 4.105, Viking 3.952, terracotta 3.858, knight 3.440, samurai 3.545, Roman 3.483 (redcoat 3.829 and Mongol 3.235 for the exhibits). Each scale is on the model as it loads, with its node transforms.

### Fault notes on the character models (seen from the front, rest pose)

The other job is still fixing these models. From the front the copies look sound, with one exception: the pharaoh's crook is bent and limp, like a rope (its weapon-bending fault). The soles are hidden by the plinths. The T. rex looks clean from the front and the side. When the fixed models land, run `prep_galleries_exhibits.py` again, then the build.

### Displayed level (the page draws baked materials unlit, without tone mapping)

The displayed level of each material, as linear `map x color x lightmap x lightmap_intensity / pi`: 60 000 points sampled by area over the GLB, reading its own textures and the WebP lightmaps (max channel).

| | p50 | p90 | p99 |
|---|---|---|---|
| `Canvas_Paintings` | 0.162 | **0.800** | 2.005 |
| `Exhibit_trex` | 0.040 | **0.227** | 0.424 |
| `Exhibit_warrior_british_redcoat` | 0.024 | **0.142** | 0.550 |
| `Exhibit_warrior_mongol_archer` | 0.010 | **0.092** | 0.359 |
| `Wall_Paint` | 0.039 | 0.079 | 0.250 |
| `Floor_Parquet` / `Floor_Marble` | 0.106 / 0.167 | 0.200 / 0.311 | 0.316 / 0.383 |
| `Ceiling_Paint` | 0.073 | 0.226 | 0.948 |
| `Trim_Paint` | 0.067 | 0.148 | 0.398 |
| `Marble_White` | 0.000 | 0.258 | 0.643 |
| `Frame_Gold` | 0.180 | 0.666 | 1.153 |

Every main surface, the canvases and the exhibits have p90 at or under 1.0. Two fittings materials on lightmap 3 run above 1, as they did in version 2: `Metal_Brass` (p90 2.72) and `Chandelier_Gilt` (p90 12.8). Their texels sit centimetres from the bulbs, so they read as glowing.

## Review stills (Cycles, 128 samples adaptive, OIDN denoise, 1920 x 1080 JPEG, AgX, exposure 0)

| | |
|---|---|
| `1_arrival.jpg` (279 KB) | the arrival point (0, 4.4) at eye height 1.6 m, facing the scene's `face` (north, -z), 75 degrees vertical like the page's camera: the warrior stand-ins, the pictures, the T. rex at the far end |
| `2_wide.jpg` (286 KB) | the whole hall from high in the north-east corner, over the T. rex, toward the door and its two warriors; the Doric doorway to the natural-history hall is on the right wall |
| `3_detail.jpg` (270 KB) | plinth 3 (east side, z -7, the knight stand-in) under its spot, with the salon pictures beside it and the T. rex beyond |

The stills were rendered again on 2026-11-26 for version 3 (Cycles on a rented GPU, 128 adaptive samples). `--stage render` also writes three views for the owner's sheet to the work folder: `5_trex`, `6_wall` and `7_door`.

![arrival](1_arrival.jpg)
![wide](2_wide.jpg)
![detail](3_detail.jpg)

These are Blender renders with Blender's real lights. The six statues in them are the stand-ins (the warriors, `Standins`); the page draws and moves the real ones. The T. rex and the two door warriors are in the GLB. The GLB was checked in node with three.js (below). Nobody has looked at it in a browser yet, so the coordinator's in-game screenshot from the arrival point will be the first look at it under the page's shading.

## Sources and licences

| Asset | Used for | Source | Author | Licence |
|---|---|---|---|---|
| `herringbone_parquet`: diffuse, 1k | the parquet field | https://polyhaven.com/a/herringbone_parquet | Sergej Majboroda (photography), Jenelle van Heerden (processing) | CC0 1.0 |
| `marble_01`: diffuse, 1k | the floor's border; the skirting and the plinth dies (tinted dark); the plinth bases and caps and the door surround (tinted white) | https://polyhaven.com/a/marble_01 | Rob Tuytel | CC0 1.0 |
| `plastered_wall_04`: diffuse, 1k | the walls (red), the ceiling (off-white), the trim, cornice, coffers and tympanum (cream) | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel | CC0 1.0 |
| `dark_wood`: diffuse, 1k | the wainscot and its panels, the door leaves, the dark wood frames | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `Chandelier_02` (glTF 1k: mesh, diffuse map) | the three chandeliers | https://polyhaven.com/a/Chandelier_02 | Kirill Sannikov | CC0 1.0 |
| `painted_wooden_bench` (glTF 1k: mesh, diffuse map) | the four benches | https://polyhaven.com/a/painted_wooden_bench | Kirill Sannikov | CC0 1.0 |
| the owner's character models: `trex`, `warrior_british_redcoat`, `warrior_mongol_archer` (exhibits, in the GLB); `warrior_egyptian_pharaoh`, `_viking_raider`, `_qin_terracotta`, `_medieval_knight`, `_japanese_samurai`, `_roman_legionary` (stand-ins only) | the T. rex skeleton, the two door warriors, the statue stand-ins | the characters job's `models/characters/<id>.glb` (static copies in `blender/models/galleries/exhibits/`) | the owner (Higgsfield models) | the owner's |
| the pictures in the frames (`paintings_atlas.jpg`) | the 41 canvases | the project's own review stills (`docs/renders/<scene>/`) and renders of the project's own `world/` GLBs (`render_galleries_views.py`) | this project | the project's own |

The four textures are unchanged from version 1 (re-saved as JPEG quality 88). The two models were not downloaded again. They were copied from the Chronicle Museum's `assets/models/` (`ph-chandelier-02`, `ph-bench`), where its `fetch_models.py` had fetched them from Poly Haven; the authors come from Poly Haven's public info API. Their glTFs keep only the diffuse map. The page shows a baked material as texture x lightmap, so the normal and ARM maps would go unused. Both models keep their full geometry: 21 514 and 630 triangles. The other files in `blender/models/galleries/` and the `Marble012`, `Metal048A` and `PaintedPlaster017` textures in `blender/textures/galleries/` belong to the wing (below); the hall does not use them. The Chronicle Museum's CC BY-NC "local" scans are not used anywhere.

Everything else is own work, made by `build_galleries.py`. That covers all the geometry (mouldings, frames, door surround, pedestals and the T. rex platform, sconces, coffers, tracks, spots) and the generated images drawn with numpy: the EXIT sign (a pixel font on green) and the wing plaques. No Meshy and no photograph. Version 3 ran its Blender steps (the exhibit copies, the views, the bake, the stills, the layout check) on the project's rented GPU box (Cycles with OptiX).

Tools: Blender 5.2.1 LTS (GPL) with Cycles, OpenImageDenoise (Apache-2.0, through the compositor's Denoise node) and the glTF I/O add-on; Python with numpy (in Blender) and Pillow (the WebP step); three r186 for the load check. The bake and the stills ran on the laptop's CPU (Intel Core Ultra 7 155U); Cycles found no GPU it can use there.

## Budgets (measured)

| | Limit | Measured |
|---|---|---|
| `world/galleries.glb`, lightmaps aside | at most 8 MB | **6.53 MB** (6 530 172 bytes, 6.23 MiB; 7.6 MB from Blender, then `tools/webp_glb.py`: textures 3.1 to 2.0 MB, geometry identical) |
| triangles | at most 300 000 | **103 703** (62 130 of them the three chandeliers; the T. rex 10 940, the redcoat 5 802, the Mongol 6 058; the 41 canvases 82; the four door leaves 192) |
| draw calls, merged by material | at most 250 | **29** (one primitive per material, 25 materials, and the four door-leaf nodes) |
| textures | WebP | **12 images, all `image/webp`** (the four 1k textures, the chandelier's and the bench's 1k diffuse maps, the pictures atlas (2048 px), the T. rex's and the two warriors' 1K maps, the EXIT sign, the doorways' plaques) |
| lightmaps | at most 4, at most 2048 x 2048, 8-bit WebP q90 | **4**: see the table below |

| Lightmap | Size | Density | File | `lightmap_intensity` | What is on it |
|---|---|---|---|---|---|
| `galleries_0` | 896 x 896 | 30.2 px/m | 29 KB | 11.1052 | parquet, marble border, ceiling |
| `galleries_1` | 1536 x 1536 | 34.2 px/m | 107 KB | 8.3673 | walls, wainscot and panels, trim (dado, picture rail, cornice, coffers), skirting, the 41 canvases |
| `galleries_2` | 1792 x 1792 | 36.2 px/m | 214 KB | 6.4692 | white and dark marble (plinths, the T. rex platform, the door surrounds and the reveals), the three frame styles, the door leaves (the four wing leaves too), the benches, the plaques, and the three exhibits (own UVs, each in its square of a strip at the map's right edge: the T. rex 0.30, each warrior 0.15) |
| `galleries_3` | 1152 x 1152 | 29.6 px/m | 62 KB | 81.1316 | dark metal and brass (tracks, spot heads, picture lights, sconces, wires, skylight frames) and the chandeliers (`Chandelier_Gilt`, own UVs in a corner square) |

Bake (version 3, 2026-11-26): Cycles with OptiX on the rented GPU box, 512 samples, diffuse (direct and indirect, no colour), 8 px margin, OIDN denoise. The four maps took 15, 60, 98 and 5 s. The `--stage all` run (art, bake, export, axes check, the stills, the plan and the owner's three views) used `PAGES` None for maps 1 and 2, which found 1536 and 1792 (the smallest pages at 30 px/m or more); those are now fixed in `PAGES`. Map 3 came out at 29.6 px/m on its fixed 1152 page, just under the 30 px/m aim, as before. `glb_inspect.py --budget tris=300000,mb=8`: `pass tris: 103703 triangles`, `pass mb: 6.23 MB` (MiB).

The GLB was checked by reading its glTF JSON directly (the same gates as the wing's). The lightmap page sizes (896, 1536, 1792, 1152) match the WebP files, no stand-in is in it, and the canvases and the three exhibits carry `TEXCOORD_1`:

```
PASS size 6530172 <= 8 MB
PASS no extras outside materials (none)
PASS images 12: all image/webp, EXT_texture_webp used
PASS materials carry only lightmap/lightmap_intensity extras (ok)
PASS 22 materials with a lightmap, every primitive of theirs has TEXCOORD_1; without one: ['Lamp_Emit', 'Sign_Exit', 'Skylight_Glass']
PASS lightmap files ['world/lightmaps/galleries_0.webp', 'world/lightmaps/galleries_1.webp', 'world/lightmaps/galleries_2.webp', 'world/lightmaps/galleries_3.webp'] exist (at most 4)
PASS tris 103703 <= 300000
PASS draw calls 29 <= 250 (primitives)
PASS no stand-in, COL_, Spot_, Link_, Arrive_, Marker_ or Zone_ nodes/meshes/materials (none)
PASS 25 art nodes with identity transforms
PASS 4 door-leaf nodes, each at its hinge: DoorLeaf_wing_e_A, DoorLeaf_wing_e_B, DoorLeaf_wing_w_A, DoorLeaf_wing_w_B
PASS no cameras, no lights
PASS art x/z -6.20..6.20, -20.20..6.20 within the colliders' -6.20..6.20, -20.20..6.20 (local space; leaves aside)
RESULT PASS
```

`node tools/worlddoc.mjs check world/galleries.json`:

```
OK world/galleries.json: 22 colliders, 4 doors, 1 markers, 0 links, 0 zones, 0 spots, 0 errors, 0 warnings
```

A scan of everything this version changes found no user name, local path, e-mail address or session id. It covered the GLB, the WebP files, the JSON, the stills, the scripts, the README, the atlas, the exhibit copies and the `.blend` (zstandard, decompressed and read across frames). The stills, the atlas and the exhibit textures carry no JPEG comment segment.

## The layout check

`blender -b blender/scenes/galleries.blend --python tools/blender/check_layout.py -- --scene galleries` (exit code 0), with the exhibits:

```
layout check: scene galleries, 201 visible meshes, 22 colliders
PASS  COVER  Floor_Museum: 40 mesh(es) cover it (178965 sample points, every one within 5 cm of art)
PASS  COVER  Ceiling_Museum: 15 mesh(es) cover it (99375 sample points, every one within 5 cm of art)
PASS  COVER  Wall_N: 24 mesh(es) cover it (19125 sample points, every one within 5 cm of art)
PASS  COVER  Wall_S: 30 mesh(es) cover it (19125 sample points, every one within 5 cm of art)
PASS  COVER  Wall_W: 49 mesh(es) cover it (23256 sample points, every one within 5 cm of art)
PASS  COVER  Wall_W_N: 38 mesh(es) cover it (14076 sample points, every one within 5 cm of art)
PASS  COVER  Wall_W_Head: 19 mesh(es) cover it (1425 sample points, every one within 5 cm of art)
PASS  COVER  Wall_E: 48 mesh(es) cover it (23256 sample points, every one within 5 cm of art)
PASS  COVER  Wall_E_N: 37 mesh(es) cover it (14076 sample points, every one within 5 cm of art)
PASS  COVER  Wall_E_Head: 18 mesh(es) cover it (1710 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_0: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_1: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_2: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_3: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_4: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_5: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Exhibit_Mongol: 3 mesh(es) cover it (1520 sample points, every one within 5 cm of art)
PASS  COVER  Exhibit_Mongol_Plinth: 6 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Exhibit_Redcoat: 3 mesh(es) cover it (798 sample points, every one within 5 cm of art)
PASS  COVER  Exhibit_Redcoat_Plinth: 6 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  TRex_Platform: 8 mesh(es) cover it (12300 sample points, every one within 5 cm of art)
PASS  COVER  TRex_Skeleton: 4 mesh(es) cover it (25058 sample points, every one within 5 cm of art)
PASS  STRAY  96 tall solid mesh(es), each over a collider; 1 decor_* mesh(es) exempt
PASS  CLEAR  marker Spawn_door (0.00, 4.40): clear within 0.28 m
PASS  CLEAR  constants.arrive (0.00, 4.40): clear within 0.28 m
PASS  CLEAR  door.at (0.00, 5.30): clear within 0.28 m
PASS: 26 of 26 checks passed
Blender 5.2.1 LTS (hash 9e2066aef7ef built 2026-08-25 02:12:34)
exit 0
0
45
outputs copied back:
```

The check works one box per object, so the pieces that run past a doorway (each long wall's wainscot panels, the surrounds' jambs and pilasters, the reveal linings, and the floor slabs) are cut in the `Art` collection into the part south of the doorway, the part north of it (`_N`) and the part above head height (`_Head`) by `split_at_doorways()` (the last step of `--stage art`, or `--stage split` on a saved file). Without the cut, 7 STRAY checks fail on boxes that span the openings. Only `Art` is cut: the `Export` objects, the bake and the GLB are the same either way.

The one exempt piece is `decor_benches`. The canvases lie 5 mm off the walls, inside the walls' colliders widened by 5 cm. Each exhibit figure stands within its pedestal's collider widened by 5 cm. The axes were checked with a marker cube at the arrival point (`--stage axes`): game (0, 0.1, 4.4) is Blender (0, -4.4, 0.1) is glTF (0, 0.1, 4.4).

## Rebuild

From the repo root, with node, Blender 5.2 and Python with Pillow:

```
node tools/blender/dump_layout.mjs galleries                     # writes blender/layout/galleries.json (git ignores that folder)
blender -b --factory-startup --python tools/blender/build_galleries.py -- --stage all --samples 512 --render-samples 128     # art, bake, export, axes check, stills
python tools/blender/pack_scene.py galleries                     # WebP lightmaps and WebP textures -> world/
```

Version 3's inputs, made before the build (each needs running again only when its sources change):

```
blender -b --factory-startup --python tools/blender/prep_galleries_exhibits.py -- --src <folder of the characters' GLBs> [--preview <dir>]   # blender/models/galleries/exhibits/
blender -b --factory-startup --python tools/blender/render_galleries_views.py -- --mode final --out <views dir>                            # the store floors and the exterior
python tools/blender/make_galleries_paintings.py --views <views dir>                                                                      # blender/textures/galleries/paintings_atlas.*
```

`--stage art|bake|export|axes|render` runs one step on the saved `.blend` (`blender -b blender/scenes/galleries.blend --python ... -- --stage bake`). `--device cpu` forces the CPU; a GPU is used when Cycles finds one. The work folder defaults to `farway_galleries` in the system temp folder (`--work <dir>` changes it). The review stills are written straight into `docs/renders/galleries/`; the plan view goes to the work folder.

## What the coordinator does to wire it in

1. Add `world/galleries.glb` to the `galleries` scene's files in `shared/farway.manifest.js` (it lists only `world/galleries.json` today). The collision file is still the code's, plus the two wing doorways and the six exhibit boxes: apply the `shared/museum.js` changes under "Wing" and under "Version 3" with it, or `shared/museum.test.js` fails.
2. Hide the blockout in `museumProps(root)` (`index.html`): the floor and ceiling slabs, the four walls, the door slab and the six plinth slabs. **Keep** what the page owns: the six statue groups (`CITY.mu.figs`, moved by `placeStatues`) and the name plates (`signTexture`). The owner wants the six box statues to become the warriors: pharaoh, Viking, terracotta, knight, samurai, Roman, in `MUSEUM.names` order, each scaled to stand 1.75 m tall (the scales are under "The statues' stand-ins"), so that they match the bake's shadows.
3. **Remove the four night `PointLight`s** that `museumProps` adds. The spots, the picture lights, the chandeliers, the sconces, the moon and the sky are in the lightmaps (`docs/BLENDER.md`, contract 4: in a scene with a model the page adds no lamp of its own). `cityLook` keeps the hemisphere light at 0.5 (`0x9aa8d0`) for the statues and the players.
4. Apply the lightmaps with `applyLightmaps` as for the apartment: every material except the three below carries `lightmap` and `lightmap_intensity` in its extras (four images); each intensity is pi times its image's white point.
5. The materials the page may touch: `Lamp_Emit` (the spot lenses, the picture-light tubes, the chandelier and sconce bulbs; emissive, strength 14; the museum is only played at night, so it can stay on), `Skylight_Glass` (the four frosted panes, transparent, faintly emissive blue), `Sign_Exit` (the EXIT sign, emissive). None carries a lightmap.
6. **Optional, a layout change for the coordinator:** the benches have no collider (the collision file has none), so they are `decor_benches` and passable. Two boxes would make them solid: x -0.62 to 0.62, y 0 to 0.9, z -4.6 to -3.4 and z -10.6 to -9.4.
7. Run every suite one at a time, merge.

## Stand-ins, and what is not exported

- **The statues** (the page draws them): `standin_warrior_0` .. `_5` in `Standins` are the six warriors (static copies, 1.75 m) on the plinths at 0.6 m, turned to face the hall as `placeStatues` turns them. They were in the bake, so each plinth top carries its statue's spot shadow (the only thing lost when one steps off, as the plan accepts), and they show in the stills; they are never exported.
- **The exhibits' colliders**: the six `COL_` boxes in `Colliders`, never rendered; they reach the game only as lines of `world/galleries.json`.
- **The name plates** (the page draws them): nothing is built on the plinth faces toward the hall. The page's plate is 1.6 m wide on a 0.9 m plinth, so it overhangs by 35 cm either side.
- **The arrival marker** `standin_arrival_marker`: a 20 cm cube at the arrival point (the axes check), never rendered or exported.
- **Lights** (`Lights`), used for the bake and the stills and not exported (`export_lights` is off):
  - six 1100 W plinth spots (34 degrees), two 880 W spots on the north frame, two 1100 W spots (44 degrees) on the T. rex and a 660 W spot on each door warrior, on the two ceiling tracks;
  - 13 picture lights (140 W; 280 W on the big north frame);
  - three 380 W chandelier point lights and two 45 W sconces;
  - the moon (a 2.6 W/m² sun from high in the west-south-west), the night sky (the world, seen only through the laylights) and the EXIT sign's glow.

## Things to know

- **Axes and scale:** metres, y up; identity node transforms, so vertices are in game coordinates. The hall's inside is x -6 to 6, z -20 to 6, y 0 to 5 (the colliders' slabs reach 20 cm further).
- **Below head height, art stays within 5 cm of its wall**, because nothing else may stand where no collider is. This is why the frames are at most 4.5 cm deep, the door's columns are 3 to 4.5 cm pilasters (only the entablature and pediment, above 2.8 m, project 13 cm), and the skirting and wainscot panels are one piece per wall. The chandeliers, sconces and picture lights hang above 1.8 m. The benches are the one passable (`decor_*`) piece.
- **Chandelier and exhibit lightmaps:** the chandeliers' 64 500 triangles would make thousands of smart-project islands. So `Chandelier_Gilt` is lightmapped through the model's own UVs, fitted into a 16 % corner square of map 3, and the three chandeliers share those texels; they hang in the same light. The three exhibits are lightmapped the same way (`KEEP_UV_LM`), each through its own Meshy UVs in its own square of a strip down map 2's right edge.
- **Lightmap white points:** each map's white point is its 99.5th percentile texel, capped at 12 x its 90th (`WHITE_CAP`). On the fittings' map the texels beside the bulbs run some 40 x hotter than the rest. Without the cap they would have pushed the other fittings into the bottom 8-bit levels; with it they clip.
- **Lightmap page sizes are fixed** (`PAGES`: 896, 1536, 1792, 1152): the smallest pages that gave at least 30 px/m on the first run, fixed because Blender's island packer is not exactly repeatable.
- **The `.blend`** finds its textures and models by relative path; the two generated images are packed in it. `blender/layout/` is in `.gitignore`: `galleries.json` is rebuilt by `dump_layout.mjs` before every build.
- **Nothing local in the public files:** the build strips custom properties other add-ons leave (some hold user-folder paths) before export and save, keeps only `lightmap` and `lightmap_intensity` on the materials, writes relative paths, unpacks the two models' textures (the glTF importer packs them under their absolute paths; the files are in `blender/models/galleries/`), turns every `use_stamp_*` off and strips the JPEG comment segments Blender writes into the stills. The checks below scan the GLB, the WebP files, the stills, the script and an uncompressed copy of the `.blend`.

## Open

- The hall in the game: the GLB and lightmaps passed the node check but have not been seen under the page's shading.
- The bench colliders (step 6 above) are the coordinator's call.
- Version 3: the six exhibit colliders in `shared/museum.js`, and the statues as warriors in the page (wiring step 2), are the coordinator's. When the characters job's fixed models land, the exhibits and the stand-ins need `prep_galleries_exhibits.py` and the build again.
- The wing doorways: the `shared/museum.js` change ("Wing") and the four manifest links (`docs/renders/galleries_wing/README.md`, wiring step 2) are the coordinator's. Until the links exist an opened leaf shows nothing behind it (the hall scene ends at its own wall), so the page should load the wing rather than let the player walk through.

## Wing

The side galleries are their own scene, `galleries_wing`: a natural-history hall (the T. rex) behind the west wall and a history gallery (the 24 soldiers) behind the east wall. Everything about it, including its links and the night-museum wiring, is in **`docs/renders/galleries_wing/README.md`**. This section covers only the hall's side of the two doorways.

**The doorways.** Both are in the middle bay of the long walls, centred at z = -10, 1.8 m wide, each shut by a pair of 0.896 m leaves:

| Door id | Wall | Style | Leaves (their own GLB nodes, origin at the hinge) | Opening | `Link_` (press F) | `Arrive_` (from the wing) | face |
|---|---|---|---|---|---|---|---|
| `wing_w` | west (x -6) | Doric pediment surround, plaque NATURAL HISTORY | `DoorLeaf_wing_w_A`/`_B`, hinges (-6, 0, -10.9) and (-6, 0, -9.1), 2.6 m | 1.8 x 2.6 m | (-5.3, 0, -10) | (-4.6, 0, -10) | (1, 0) |
| `wing_e` | east (x 6) | round arch with keystone, plaque HISTORY GALLERY | `DoorLeaf_wing_e_A`/`_B`, hinges (6, 0, -10.9) and (6, 0, -9.1), 2.1 m to the springing line under a fixed wooden tympanum | 1.8 x 2.1 m | (5.3, 0, -10) | (4.6, 0, -10) | (-1, 0) |

The surrounds stay within 5 cm of the wall below head height (pilasters and reveal linings), the mouldings and wainscot panels stop at the pilasters, and each doorway has a pair of sconces. The leaves swing 95 degrees into the hall. The `Link_`/`Arrive_` empties sit in the `.blend`'s `Layout` collection and are not written to `world/galleries.json`: that file is the code's (`tools/make_street.mjs` writes it from `shared/museum.js`), and the links go in the manifest.

**What changed in `world/galleries.json`: the two doorways and nothing else.**
- `Wall_W` and `Wall_E` are each cut into three boxes: the piece south of the opening (keeping the name, z -9.1 to 6), the piece north of it (`Wall_W_N`, `Wall_E_N`, z -20 to -10.9) and the head over it (`Wall_W_Head` from y 2.6, `Wall_E_Head` from y 2.1, z -10.9 to -9.1). 12 colliders became 16. Every other collider, the marker and every number in them are unchanged.
- `doors` holds the four closed leaves (`name, level, hinge, width 0.896, height, closed_yaw_deg, swing_deg, state "closed"`).

**The matching `shared/museum.js` change (for the coordinator; this branch does not touch `shared/`).** `origin/main`'s `shared/museum.test.js` checks that `world/galleries.json` is what `museumDoc()` makes, so the new file fails it until this lands. With this diff applied to `origin/main`, `museumDoc()` equals the new file exactly, and `shared/museum.test.js` and `shared/city.test.js` pass:

```diff
@@ MUSEUM
   homes: [[-4.4, -1], [4.4, -1], [-4.4, -7], [4.4, -7], [-4.4, -13], [4.4, -13]],
+  wing: {z: -10, w: 1.8, top: {w: 2.6, e: 2.1}},       // the doorways to galleries_wing: Doric (west, leaves 2.6 m) and arched (east, leaves 2.1 m)
@@ museumColliders()
-  add("Wall_W", [-hx - t, 0, cz - hz], [-hx, h, cz + hz]); add("Wall_E", [hx, 0, cz - hz], [hx + t, h, cz + hz]);
+  // the wing's two doorways (scene galleries_wing): 1.8 m wide at z = -10, each long wall split into the piece south of it, the piece north (_N) and the head (_Head)
+  const side = (s, x0, x1, top) => { const [z0, z1] = [MUSEUM.wing.z - MUSEUM.wing.w / 2, MUSEUM.wing.z + MUSEUM.wing.w / 2];
+    add(s, [x0, 0, z1], [x1, h, cz + hz]); add(s + "_N", [x0, 0, cz - hz], [x1, h, z0]); add(s + "_Head", [x0, top, z0], [x1, h, z1]); };
+  side("Wall_W", -hx - t, -hx, MUSEUM.wing.top.w); side("Wall_E", hx, hx + t, MUSEUM.wing.top.e);
@@ museumDoc
-export const museumDoc = () => ({scene: "galleries", colliders: museumColliders(), doors: [], cameras: [],
+// the wing doorways' four closed leaves (build_galleries.py writes the same): hinge at each jamb, 0.896 m wide, swinging into the hall
+const leaf = (name, x, z, height, yaw, swing) => ({name, level: "galleries", hinge: [x, 0, z], width: 0.896, height, closed_yaw_deg: yaw, swing_deg: swing, state: "closed"});
+export const museumDoors = () => { const {z, w, top} = MUSEUM.wing, [z0, z1] = [z - w / 2, z + w / 2], hx = MUSEUM.half[0];
+  return [leaf("DoorLeaf_wing_e_A", hx, z0, top.e, -90, -95), leaf("DoorLeaf_wing_e_B", hx, z1, top.e, 90, 95),
+          leaf("DoorLeaf_wing_w_A", -hx, z0, top.w, -90, 95), leaf("DoorLeaf_wing_w_B", -hx, z1, top.w, 90, -95)]; };
+export const museumDoc = () => ({scene: "galleries", colliders: museumColliders(), doors: museumDoors(), cameras: [],
```

The page's own blockout walls (`museumProps` in `index.html`) are hidden once the GLB is in (step 2 above), so they need no doorway of their own.
