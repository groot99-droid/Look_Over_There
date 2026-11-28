# floor_3: the hotel's apartment floor

Floor 3 of the apartment tower (`docs/BLENDER_AREAS.md` section 1; `docs/WORLD.md`, "Hotel tower": "10 doors on one level. Peaceful. Every player gets an apartment"), dressed and lit in Blender on the greybox's layout, baked at night as the hotel's corridors are.

| File | What it is |
|---|---|
| `world/floor_3.glb` | the art: 1.85 MB, 9 644 triangles, 19 materials, 30 meshes of one primitive each (one per material, and the 12 door leaves as their own nodes), 13 WebP textures |
| `world/floor_3.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`: 79 colliders, 13 doors, 1 marker, 2 links, 4 spots. It is exactly what the greybox model writes (`build_hotel_greybox.py --preview`); what changed in the greybox is under "The layout" |
| `world/lightmaps/floor_3_0.webp`, `floor_3_1.webp` | the night bake (second UV set, `TEXCOORD_1`): the shell (2048), the doors and fittings (1024) |
| `blender/scenes/floor_3.blend` | the saved scene (Git LFS): `Art` (the unmerged pieces), `Doors` (the twelve leaves, origin at the hinge), `Layout` (the `COL_` boxes and the empties), `Kit` (the connector kit's elevator, appended as a stand-in), `Export` (merged by material, with the lightmap UVs), `Lights_Lamps`, `Lights_Kit` |
| `tools/blender/build_hotel_floor3_roof.py` | the re-runnable build (this scene and the roof); it imports the greybox model, so no coordinate of the layout is typed in |
| `docs/renders/floor_3/` | the three review stills (this folder) |

The build reads textures already in the repo (below); nothing was downloaded.

## Review stills (Cycles, 160 samples adaptive, OIDN, 1920 x 1080 JPEG, AgX, the scene's own lamps)

| | |
|---|---|
| `1_arrival.jpg` | the arrival point out of the lift (`Arrive_lift`, -18.8, 0) at eye height, facing east down the corridor |
| `2_wide.jpg` | from the stair door at the east end, looking back west toward the lift |
| `3_detail.jpg` | a bay on the north side: a print between two sconces, a radiator, and the lift's landing at the end |

## What is in it

- **The corridor** (40 m by 2.2 m, 2.8 m high): an oak floor with a wine-red runner down the middle (cream and gold border, a small lozenge every 0.65 m) held by brass rods at each end; a sage gloss wainscot to the chair rail at 0.95 m, faded grey-blue paper above it (pairs of cream stripes, a small sprig), cream skirting, rail and cornice; a plaster ceiling with three smoke detectors.
- **Ten apartment doors** (301 to 305 north, 306 to 310 south, `room_layout: apartment`): deep green panelled leaves with a brass number plate, a letter flap, a peephole, a knob and a kick plate, in cream casings. Welcome mats at seven of them (coir, red, green, grey, blue, brown); 303, 305 and 308 have none.
- **Light:** eighteen single-arm brass sconces with linen shades at 1.85 m (`Lamp_Emit`), two to each bay and two at each end, and a small flush light in each alcove ceiling. Nothing else is lit: pools of warm light between the doors, darker in between.
- **Framed prints** (made here, below): a lighthouse at dusk, hills under a moon, a lake with a jetty, reeds; four in the bays and one in each alcove. Cast-iron column radiators under two of them and in the north alcove.
- **The lift** (west end) is the connector kit's elevator: the page draws `world/kit/elevator.glb` there; this scene has the plaques beside it (FLOOR 3, 301 - 310).
- **The stair door** (east end) under a lit EXIT sign (`Exit_Emit`, its own green picture, not one of the page's switched materials); a ROOF plate on the door. Behind it the stairwell: painted walls, thirteen concrete steps up to the landing, a steel handrail, a bulkhead lamp on the ceiling and one over the roof door, a ROOF sign, a FLOOR 3 sign by the bottom door.

## Light

| Set | Light | Maps | Material property |
|---|---|---|---|
| night (the only set) | every sconce and alcove light, the stairwell's two lamps, the exit sign's glow, the kit car's own bulb behind its closed doors | `floor_3_0` (2048: floors, walls, ceilings, trim, the stairwell), `floor_3_1` (1024: the twelve leaves, radiators, frames, prints, mats, signs, brass) | `lightmap`, `lightmap_intensity` |

`Lamp_Emit` is exported at strength 6 (on, as in the bake); the page switches it as it does in part 1. Baked in Cycles on the GPU, 768 samples, diffuse direct and indirect, OIDN-denoised: page 0 in 33 s at 52 px/m (the ceiling 29, trim and stair concrete 42), page 1 in 20 s at 55 px/m (brass, metal and the palette 22). Faces never seen are dropped before the bake (a face whose points 1 cm in front of it are all inside a collider or outside the corridor, the alcoves, the stairwell and the lift: the walls' backs toward the rooms, the slabs' undersides, the ceiling's top).

## Brightness, as the page shows it

The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L is written with a shoulder, texel = G L / (C + G L), and `lightmap_intensity` = pi C, so the page shows about texture x G L where the light is ordinary and rolls off toward texture x C beside a lamp, never clipping. Here G = 26, C = 1.5; four small materials beside the lamps are capped (`lightmap_intensity` x 0.7 for Signs and Brass, 0.75 for Paint_Palette, 0.85 for Prints). The raw bake is kept in the work folder, and `--stage encode --gain G` re-writes the maps without baking again.

Measured with the brief's `lab_display.py` (displayed = texture x base colour x lightmap x intensity / pi, area-weighted, the max channel):

| Material | m2 | Map | `lightmap_intensity` | p50 | p90 | p99 | clipped |
|---|---|---|---|---|---|---|---|
| `Wall_Paper` | 155.3 | `floor_3_0` | 4.7124 | 0.204 | 0.329 | 0.585 | 0.00% |
| `Ceiling_Plaster` | 125.1 | `floor_3_0` | 4.7124 | 0.264 | 0.349 | 0.388 | 0.00% |
| `Stair_Wall` | 104.0 | `floor_3_0` | 4.7124 | 0.359 | 0.427 | 0.459 | 0.00% |
| `Wall_Wainscot` | 75.3 | `floor_3_0` | 4.7124 | 0.159 | 0.196 | 0.210 | 0.00% |
| `Trim_Paint` | 65.5 | `floor_3_0` | 4.7124 | 0.153 | 0.285 | 0.333 | 0.00% |
| `Floor_Oak` | 60.8 | `floor_3_0` | 4.7124 | 0.068 | 0.107 | 0.167 | 0.00% |
| `Stair_Concrete` | 57.8 | `floor_3_0` | 4.7124 | 0.000 | 0.193 | 0.410 | 0.00% |
| `Doors` | 54.5 | `floor_3_1` | 4.7124 | 0.009 | 0.100 | 0.392 | 0.00% |
| `Floor_Runner` | 49.5 | `floor_3_0` | 4.7124 | 0.100 | 0.118 | 0.534 | 0.00% |
| `Radiator_Paint` | 7.9 | `floor_3_1` | 4.7124 | 0.039 | 0.202 | 0.288 | 0.00% |
| `Frame_Wood` | 3.1 | `floor_3_1` | 4.7124 | 0.001 | 0.106 | 0.184 | 0.00% |
| `Paint_Palette` | 2.4 | `floor_3_1` | 3.5343 | 0.032 | 0.189 | 0.725 | 0.00% |
| `Prints` | 1.9 | `floor_3_1` | 4.0055 | 0.112 | 0.380 | 0.546 | 0.00% |
| `Steel_Paint` | 0.9 | `floor_3_1` | 4.7124 | 0.098 | 0.173 | 0.206 | 0.00% |
| `Brass` | 0.8 | `floor_3_1` | 3.2987 | 0.030 | 0.651 | 0.651 | 0.00% |
| `Metal_Dark` | 0.5 | `floor_3_1` | 4.7124 | 0.067 | 0.074 | 0.074 | 0.00% |
| `Signs` | 0.2 | `floor_3_1` | 3.2987 | 0.285 | 0.661 | 0.707 | 0.00% |

The walls read: the paper's p50 is 0.20 and the wainscot's 0.16, the ceiling 0.26, the stairwell's walls 0.36. Every p90 is at or under 0.66 and every p99 under 0.73; nothing clips. Low p50s are the room side of each leaf (it faces into the apartment, unlit by this bake), the undersides of the stair flight and the floor under it, and the dark green paint of the doors.

## The layout

The layout is the greybox's (`tools/blender/build_hotel_greybox.py`, `_f3`), with the connector kit placed as `blender/kit/README.md` says, through `tools/blender/kit_place.py`:

- **The elevator** at (-20, 0, 0), yaw 90. The kit's car (parked here; the page moves it) and landing replace the greybox's `LiftCar` shell and plain lift door: 8 `Car_*_F3` and 4 `Landing_*_F3` colliders, the kit's door record (hinge (-20, 0, -0.6), `closed_yaw_deg` -90, `kind: elevator`, `leaves`, `slide_m`, `car`) keeping the id `lift`, so it still meets the link `lift`; the spots `Spot_call_1_F3` and `Spot_panel_1_F3`. The kit's own `Link_`, `Arrive_` and `Marker_Landing` are left out: the greybox's link (`Link_lift` (-19.4, 0, 0), `Arrive_lift` (-18.8, 0, 0)) and spawn stay.
- **The stair door** at both stair doors, `stairwell` (20, 0, 0) and `roof` (26.6, 3.2, 0), yaw -90. The corridor and the top landing are the landings, and the stairwell itself is behind the first, so the kit's landing node and its hallway are left out and only its door record is used: 1.04 m by 2.12 m, hinge 0.52 m off the middle, `closed_yaw_deg` 90, `swing_deg` -90, `kind: stair door`. The two openings widen from 0.94 m to the kit's 1.1 m (`Corridor_Wall_E_*` and `Stairwell_Wall_E_*` are rebuilt round 1.1 m holes). The leaves are this scene's own (the kit's size and hinge, a green-grey steel door with a wired-glass panel), in this GLB.
- **Two small changes, and why:** the corridor gate's clear rectangle starts 8 cm in from the west wall, because the kit landing's frame stands 6 cm proud of it; and the kit's call-button spot moves 8 cm toward the corridor's middle (to (-19.55, 0, -0.80)), because where the kit put it, 0.22 m from the north wall (the kit's landing was drawn for the atrium's wider galleries), `tools/worlddoc.mjs` finds it inside a walker's 0.28 m of `Corridor_Wall_N_1`.
- **Unchanged:** every other collider, the ten room doors and their `room_*` properties, both links, the spawn, the two alcoves' hide spots, the thirteen steps (`Step_floor_3_up_*`) and the landing.

`tools/blender/kit_place.py` gets a one-line fix: an appended object is in no scene yet, so its `matrix_world` reads as identity, and an empty placed only by its location (a door record, a spot) landed on `at`. It now starts from the object's `matrix_basis`.

## Checks

```
python tools/blender/build_hotel_greybox.py --check .            GATES PASS (links 47 pairs; steps: highest rise 0.250 m; corridors: narrowest 1.60 m, none blocked)
export_scene.py (the .blend) == build_hotel_greybox.py --preview   identical
check_layout (Art and the kit's stand-ins)                        PASS: 81 of 81 checks passed
node tools/worlddoc.mjs check world/floor_3.json                  OK: 79 colliders, 13 doors, 1 markers, 2 links, 0 zones, 4 spots, 0 errors, 2 warnings
                                                                  (warnings: links lift, roof: the manifest has no link from this door yet)
glb_inspect --budget tris=300000,mb=8                             pass: 9 644 triangles; pass: 1.85 MB (1.94 MB on disk); 30 meshes (30 draw calls)
node --test shared/*.test.js                                      297 pass, 0 fail
```

## Sources and licences

| Map | Used for | Source | Author | Licence |
|---|---|---|---|---|
| `old_wood_floor`: diffuse, 1k (`blender/textures/apartment/`) | the oak floor | https://polyhaven.com/a/old_wood_floor | Guillaume Monsergent | CC0 1.0 |
| `plastered_wall_04`: diffuse, 1k (`blender/textures/galleries/`) | the wainscot, the ceiling, the trim (each tinted) | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel | CC0 1.0 |
| `beige_wall_001`: diffuse, 1k (`blender/textures/apartment/`) | the stairwell's walls | https://polyhaven.com/a/beige_wall_001 | Dimitrios Savva (photography), Rico Cilliers (processing) | CC0 1.0 |
| `dark_wood`: diffuse, 1k (`blender/textures/apartment/`) | the picture frames | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `concrete_floor_02`: diffuse, 1k (`blender/textures/kit/`) | the stairs | https://polyhaven.com/a/concrete_floor_02 | Rob Tuytel | CC0 1.0 |
| `painted_metal_shutter`: diffuse, 1k (`blender/textures/kit/`) | the radiators, the handrail | https://polyhaven.com/a/painted_metal_shutter | Charlotte Baglioni, Dario Barresi, Rico Cilliers | CC0 1.0 |
| The runner, the wallpaper, the doors and their number plates, the prints, the signs, the exit sign, the mats' palette | as named | drawn by `build_hotel_floor3_roof.py` (numpy, seeded) | this repo | CC0 1.0 |

The six maps were already in the repo and are read where they are; nothing was downloaded or bought, and no Meshy or Higgsfield model is used. The kit's elevator (a stand-in here) is the kit's own, `blender/kit/README.md`.

## Rebuild

```
blender -b --factory-startup --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage art,bake,export --samples 768
blender -b blender/scenes/floor_3.blend --python tools/blender/build_hotel_floor3_roof.py -- --scene floor_3 --stage render --render-samples 160
python tools/blender/pack_scene.py floor_3 --work work/floor_3
```

`art` also writes `world/floor_3.json` and runs the layout check. Run on the rented GPU box from a slim copy of the repo (the build script, the greybox model, `export_scene.py`, `check_layout.py`, `kit_place.py`, `blender/kit/`, the six textures, `world/kit/*.json`).

## For the coordinator

- **Manifest:** a hotel scene `{id: "floor_3", floorY: 0, files: ["world/floor_3.glb", "world/floor_3.json"]}`, with the kit's elevator drawn from `world/kit/elevator.glb` at (-20, 0, 0), yaw 90 (its own lightmap `kit_elevator_0`). The stair doors' leaves are in this GLB: do not place `world/kit/stair_door.glb` here.
- **Links:** `lift` (the atrium's `lift_L12`) and `roof` (the roof's `floor_3`), as in the greybox's PAIRS. The stair door `stairwell` has no link: it opens onto this scene's own stairwell. If the page draws its lit passage (`buildPassage`) behind every door of `kind: stair door`, it should not behind this one.
- **Rooms:** each room door keeps `room_layout: apartment`, `room_x`, `room_z`, `room_yaw_deg`; the room is part 1's `apartment`.

## Open

- The room side of the ten leaves is dark in the bake (nothing lights the apartments here); when a door opens, the apartment's own lighting is the page's.
- The greybox's floor-3 plan and still (`docs/renders/hotel_greybox/`) still show the plain lift box and the 0.94 m stair doors.
