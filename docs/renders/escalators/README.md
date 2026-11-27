# The hotel's last pieces: `escalators`, `other_stairs`, `clue_room`, `empty_room`

The two connector scenes between the atrium's four galleries and the two floor 3 room layouts, dressed and lit (`docs/BLENDER_AREAS.md`, section 1, step 2), built round the greybox (`claude/blender-hotel-greybox`, draft PR #93) by `tools/blender/build_hotel_stairs.py` in Blender 5.2.1. Liminal: off and empty, but seemingly normal. There are no reference photos; everything follows the written descriptions.

This README covers all four. Each scene's folder (`docs/renders/<scene>/`) holds its three stills, its plan, `bake.json` and `caps.json`.

| File | What it is |
|---|---|
| `world/escalators.glb`, `world/other_stairs.glb` | the halls' art: 1.68 MB / 15 844 triangles / 42 draw calls and 1.76 MB / 12 384 / 31 |
| `world/rooms/clue_room.glb`, `world/rooms/empty_room.glb` | the rooms' art: 1.11 MB / 2 030 triangles / 19 draw calls and 1.04 MB / 906 / 15 |
| `world/lightmaps/<scene>_0.webp`, `_1.webp` | two lightmaps per scene (second UV set): `_0` the shell, `_1` everything in it |
| `world/escalators.json`, `world/other_stairs.json` | the layouts, written by `export_scene.py` from the `.blend`: exactly what the greybox model writes (`build_hotel_greybox.py --preview`); what was added is under "The layout" |
| `world/rooms/clue_room.json`, `world/rooms/empty_room.json` | unchanged, byte for byte the greybox's |
| `blender/scenes/<scene>.blend` | the saved scenes (Git LFS): `Art` (`Props`, and `Arch`: the colliders' grey twins, for the layout check and the plan), `Skin` (the shell as seen), `Doors`, `Layout`, `Lights`, `Bake_Standins`, `Standins`, `Export` |
| `tools/blender/build_hotel_stairs.py` | the re-runnable build (all four scenes) |
| `tools/blender/hotel_stairs_skin.py` | pure Python: the shell as seen and the materials of its faces; `python tools/blender/hotel_stairs_skin.py` prints them |
| `tools/blender/check_layout.py` | floor 1's two extensions copied in (room layouts under `world/rooms/`; a flight's upper steps count as standing) |
| `tools/blender/build_hotel_greybox.py` | the escalators' and the ground flight's added solids (below) |

## What is in it

### `escalators` (6 m by 8.8 m, 15.2 m high)

Three stopped escalators between the atrium's four galleries, dim at night: the ground run from the sub floor to floor 1 (west), floor 1 to floor 2 (middle), floor 2 to floor 3 (east), each 16 steps of 0.3 m by 0.25 m, exactly the greybox's step boxes.

- **One step mesh, repeated.** `Esc_Step` is a single mesh (a grooved aluminium tread with yellow demarcation along both sides and the nosing, a cleated riser), and the 48 steps are linked copies of it in the `.blend`. The GLB merges the props by material, as floor 1 does, so each step gets its own lightmap texels; its triangles are a few dozen a step.
- **Balustrades:** a black handrail on top, ivory enamel side panels with round lamps every 0.9 m along the inner face (`Lamp_Emit`, four of the 36 dead), a brushed-steel skirt beside the steps, champagne cladding outside. The ground run's truss is clad down to the floor; the upper runs' trusses hang clad underneath. Newels run 0.5 m past the end steps, with ribbed steel floor plates and yellow comb plates at both ends and a red stop button on each bottom newel.
- **Landings:** each carries the carpet of the gallery it opens onto (floor 1 the motel's red hex lattice, floor 2 the green carpet with gold fleurons, floor 3 the apartments' tan), a steel nosing on the edge and the floor's name in brass on its fascia, and a guard of black iron balusters with a brass handrail, as the atrium's galleries have. The ground is the sub floor's white 15 cm tile with a white tiled dado and a green top row.
- **Walls:** warm plaster with a steel band at each landing level. At every door: a steel casing, an EXIT sign (`Emergency_Emit`), a caged bulkhead (floor 3's is dead), and the level's name on a plate (SUB FLOOR, FLOOR 1, 2, 3). Half-drum wall lights at each level light the tall walls (one dead); one opal globe hangs high under the ceiling (a second is dead).
- **Doors:** the four doors to the atrium are grey steel with a wired-glass vision panel, a push bar on this side and a lever on the atrium's; one mesh (`Leaf_Esc`), each leaf its own node `DoorLeaf_atrium_L<y>` with its origin at the hinge.

### `other_stairs` (5.2 m by 6 m, 15.2 m high)

A switchback service staircase through the four levels: two flights of eight steps a level about the central spine wall, a half landing between.

- **Painted concrete:** concrete flights with sloped soffits and yellow nosings on every step, painted block walls (off-white over a grey-green dado band at every landing), concrete landings and soffits. The ground flight is solid to the floor.
- **A steel handrail** each side of every flight, on brackets from the wall and the spine.
- **Each landing** (y 0, 4, 8, 12): the level stencilled large beside the door (S, 1, 2, 3, with SUB FLOOR / FLOOR 1 / 2 / 3 under it), an EXIT sign over the door (`Emergency_Emit`), a caged lamp on the east wall (floor 2's is dead), a red hose valve on the fire main. Each half landing has a caged lamp (the top one dead) and a stencilled direction (S > 1, 1 > 2, 2 > 3).
- **The fire main:** a red standpipe up the south-west corner through every level (`decor_`, out of the walker's reach).
- **Doors:** grey-green steel, as the escalators' (`Leaf_Stair`).

### `clue_room` (5 m by 6 m, floor 3)

A hotel room that holds a clue. Faded sage-and-cream striped paper, a worn brown carpet, a dim ceiling dome.
- **The pinboard** (the greybox's `Pinboard`, on the north wall): cork in a dark wood frame, twelve papers pinned on it (lined pages, sticky notes, a hand-drawn corridor plan with one door ringed, a street map with a block circled, newspaper clippings, photographs of an empty corridor and of a numbered door, a calendar with the days crossed out), red string between the pins.
- **The desk** (west wall): two pedestals of drawers, papers spread on it, an open folder, a mug, a pen, a green banker's lamp lit, the chair pushed under it; the window above it with its blind down.
- **The table** in the middle: a hotel plan spread out, stacks of paper, a magnifying glass.
- **The east wall** by the other two clue spots: notes taped up and joined by a string. Papers on the floor.
- No people or figure images: every picture is a place or a thing.

### `empty_room` (6 m by 8 m, floor 3)

Stripped. A bare concrete floor with the carpet's old adhesive in combed arcs and the tack strips left round the edges; a dark stain where the bed stood, the paler ghost of its headboard on the wall, paler patches where two pictures hung and a dresser stood; wallpaper torn away in patches to grey plaster; skirting missing where the bed was. One bare bulb on its cord from a ceiling rose (`Lamp_Emit`). The window on the west wall, its curtains open on black. The greybox's single wooden chair, facing where the bed was.

## How it is built

- **The layout comes from the greybox model.** The build imports `tools/blender/build_hotel_greybox.py`'s model and makes every `COL_` box, `DoorLeaf_`, `Link_`/`Arrive_`, `Marker_` and `Spot_` from it, with the same names and numbers; `export_scene.py` then writes the layout files again, and they are identical to what `build_hotel_greybox.py --preview` writes.
- **The shell is only what can be seen** (`hotel_stairs_skin.py`, the same cut as floor 1's): every face of a greybox box that looks into the air, cut where other boxes meet it. The steps, balustrades, newels, guards and furniture are not shell: their art is the build's own, and each collider has a grey twin in `Art/Arch` for the layout check.
- **The props** are merged by material for export; faces pressed against the shell are dropped. The door leaves are reused meshes, each leaf its own node with its origin at the hinge, so the page swings it by name; one leaf a scene is baked (`BAKE_LEAF`) and the others show its lightmap.
- **The rooms are baked once to fit any door,** as floor 1's are: with their lamps on and the door open onto a stand-in of floor 3's corridor (its carpet, walls, ceiling, a sconce 2 m either side of the door on both walls at 1.85 m, the leaf standing open). The stand-in is never exported. A room's door wall is the corridor's wall, so it draws only its inside face.

## The layout

`world/rooms/clue_room.json` and `world/rooms/empty_room.json` are unchanged. `world/escalators.json` and `world/other_stairs.json` are the greybox model's, with solids **added** in `build_hotel_greybox.py` (no step, link, door, marker or spot moved; every `Step_` box is as it was):

- **escalators** (64 to 192 colliders, `esc_solids()`): each run's two balustrades, one box a step beside the step (`Balustrade_<run>_<W|E>_<nn>`, 0.12 m thick, up to the handrail over the step's far end; for the ground run from the floor, for the upper runs from the truss's underside); the ground run's truss under each step (`Fill_esc_0_4_<nn>`, floor to the step's underside), so its underside is closed and not walked under; the newels, where each balustrade runs 0.5 m on past the end steps onto its floor (`Newel_<run>_<bottom|top>_<W|E>`); the landings' guards over the hall between the newels, 1.05 m high (`Guard_<level>_<k>`). **Why:** in the greybox you could walk off the side of a run, under the ground run, or off a landing into the 15 m hall; the art (solid balustrades, a clad truss, guards) needs colliders under the brief's collision rule.
- **other_stairs** (66 to 73 colliders): the ground flight is solid concrete to the floor (`Fill_st_0_a_<nn>`, floor to each step's underside), so its soffit is not walked into from the nook under the half landing.

`python tools/blender/build_hotel_greybox.py --check .` still passes; `docs/renders/hotel_greybox/README.md` and `CHECKS.txt` carry the new collider counts.

## Light

- **The halls are baked at night** (one set, `lightmap` only). Escalators: 32 lit side lamps of 3 W (Cycles) along the runs, nine wall lights washing the tall walls, three caged bulkheads over the doors, one globe high under the ceiling, the EXIT signs' glow. The other staircase: one caged lamp of 50 W on every landing and half landing (two of the seven dead), the EXIT signs' glow; dim, as a service stair is.
- **The rooms** are baked with their lamps on and the door open onto floor 3's corridor stand-in (above): the clue room's green desk lamp and a dim ceiling dome; the empty room's one bare bulb.
- **Toggled materials:** `Lamp_Emit` (emissive 3) and `Emergency_Emit` (the green EXIT letters, emissive 4). Both are on in the bake. No `Window_Lit`. `Glass_Clear` would have no lightmap (none is used here).
- **Bake:** Cycles on the rented GPU (OptiX), 1024 samples, diffuse direct and indirect, 8 px margin, OIDN. As floor 1: a highlight shoulder above each map's 70th percentile (`SHOULDER`), the white point the map's 99.5th percentile, `lightmap_intensity` pi times it.
- **Pages are fixed** (`PAGES`). The shell's UVs are packed by hand (every shell face is a rectangle); the props are smart-projected and packed.

| Map | Size | Density | WebP |
|---|---|---|---|
| `escalators_0` / `_1` | 2048 / 2048 | 70.3 / 18.0 px/m | 108 KB / 232 KB |
| `other_stairs_0` / `_1` | 2048 / 1024 | 70.6 / 15.1 px/m | 134 KB / 92 KB |
| `clue_room_0` / `_1` | 1024 / 1024 | 80.0 / 77.0 px/m | 29 KB / 98 KB |
| `empty_room_0` / `_1` | 1024 / 1024 | 60.7 / 104.2 px/m | 22 KB / 68 KB |

The halls' prop pages are coarse (15 to 18 px/m: the steps, the balustrades and the flights are a few hundred square metres); one value every 5 to 7 cm suits them at night.

## Brightness (as the page shows it)

Measured with the brief's `lab_display.py` on the packed GLBs (displayed = texture x base colour x lightmap texel x intensity / pi, no tone mapping). From the uncapped GLB, `docs/renders/<scene>/caps.json` sets the factors on each material's `lightmap_intensity`: one **gain** a scene (its big shell surfaces up to p99 0.9 and p90 0.85: 1.513 escalators, 5.114 other_stairs, 4.712 clue_room, 3.75 empty_room), a **lift** for a dark material as the atrium did (a wall up to p50 0.15, a big floor or ceiling up to p50 0.10, a big prop up to p90 0.25; at most 3 x the gain; never the black handrails, iron, voids or decals), and a **cap** (p99 0.97, p90 0.88) on every material. Main surfaces (5 m2 or more), as exported:

| Scene | Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|---|
| escalators | Wall_Hall | 398.4 | 0.252 | 0.650 | 0.848 |
|  | Esc_Clad | 205.7 | 0.009 | 0.250 | 0.382 |
|  | Esc_Panel | 66.1 | 0.002 | 0.471 | 0.660 |
|  | Ceiling_Hall | 52.8 | 0.226 | 0.494 | 0.662 |
|  | Floor_Tile | 52.8 | 0.538 | 0.776 | 0.900 |
|  | Esc_Tread | 38.8 | 0.006 | 0.250 | 0.497 |
|  | Soffit_Plaster | 36.0 | 0.309 | 0.722 | 0.847 |
|  | Wall_Tile | 34.4 | 0.475 | 0.708 | 0.872 |
|  | Esc_Skirt | 31.8 | 0.003 | 0.249 | 0.366 |
|  | Esc_Riser | 27.0 | 0.000 | 0.051 | 0.460 |
|  | Carpet_Apart | 12.0 | 0.262 | 0.336 | 0.401 |
|  | Carpet_Green | 12.0 | 0.080 | 0.147 | 0.549 |
|  | Carpet_Motel | 12.0 | 0.099 | 0.196 | 0.419 |
|  | Trim_Steel | 9.8 | 0.104 | 0.249 | 0.318 |
|  | Fascia_Paint | 7.9 | 0.000 | 0.076 | 0.095 |
|  | Door_Jamb | 5.0 | 0.000 | 0.074 | 0.108 |
| other_stairs | Stair_Paint | 335.6 | 0.215 | 0.591 | 0.898 |
|  | Stair_Step | 180.7 | 0.018 | 0.257 | 0.484 |
|  | Stair_Ceiling | 86.9 | 0.103 | 0.444 | 0.812 |
|  | Stair_Floor | 86.9 | 0.101 | 0.293 | 0.535 |
|  | Stair_Dado | 59.6 | 0.145 | 0.371 | 0.521 |
|  | Nosing_Yellow | 12.4 | 0.000 | 0.383 | 0.467 |
|  | Stair_Edge | 9.0 | 0.000 | 0.133 | 0.263 |
|  | Rail_Steel | 8.4 | 0.021 | 0.192 | 0.292 |
|  | Red_Paint | 5.1 | 0.047 | 0.247 | 0.313 |
|  | Door_Jamb | 5.0 | 0.000 | 0.007 | 0.179 |
| clue_room | Wall_Clue | 58.2 | 0.347 | 0.516 | 0.671 |
|  | Carpet_Clue | 30.0 | 0.119 | 0.172 | 0.210 |
|  | Ceiling_Room | 30.0 | 0.281 | 0.501 | 0.901 |
|  | Wood_Dark | 18.4 | 0.000 | 0.249 | 0.750 |
|  | Wood_Laminate | 6.9 | 0.083 | 0.412 | 0.766 |
| empty_room | Wall_Stripped | 74.8 | 0.303 | 0.487 | 0.643 |
|  | Ceiling_Room | 48.0 | 0.288 | 0.699 | 0.901 |
|  | Floor_Bare | 48.0 | 0.109 | 0.209 | 0.358 |

No material in any scene is over p90 0.9 or p99 0.98; the most clipped is the clue room's paper at 0.7 % of its area. The walls read: p50 0.25 (the hall), 0.21 and 0.145 (the stairwell's paint and its grey-green dado band), 0.35 and 0.30 (the rooms). Props with p50 near 0 (Esc_Clad, Esc_Panel, Esc_Tread, Stair_Step, Wood_Dark) include faces no one sees (the backs of panels, the undersides of treads and of the flights against the walls, under the desk), which the area-weighted sample counts; their p90 is what is seen. The stairwell's concrete needed the largest lifts (up to x15 on the dado band, x14.7 on the steps): its few caged lamps leave most of it far from a lamp.

## Review stills

Cycles, 128 samples adaptive, OIDN, 1920 x 1080 JPEG (comment and APP1 segments stripped), AgX Medium High Contrast, Blender's real lights (the page shows the lightmaps instead).

| Scene | `1_arrival` | `2_wide` | `3_detail` |
|---|---|---|---|
| escalators | the ground arrival (0, 1.6, 3.2) facing north into the hall | from the ground's south-east corner, up at the runs and the landings | the foot of the ground run: comb and floor plates, steps, side lamps, the stop button |
| other_stairs | the ground arrival (0, 1.6, 2) facing north, up the first flight | from floor 1's landing down the east flight to the half landing and its caged lamp | floor 1's landing: the stencilled level by the door |
| clue_room | the door marker (0, 1.6, -0.8), looking in at the pinboard | from the door's corner, high | the pinboard |
| empty_room | the door marker, looking in | from the door's corner, high | the window, its curtains open on black |

`plan.jpg` in each folder is a top-down view with the ceiling off (the walls in the greybox's grey; the halls show each level's top from above).

## Gates

- `check_layout.py` (on each saved `.blend`): **PASS 194 of 194** (escalators), **75 of 75** (other_stairs), **13 of 13** (clue_room), **11 of 11** (empty_room). Every collider is covered (the shell's and the props' colliders by their grey `Arch` twins, whose seen faces are the skin and the props), every tall solid stands on a collider, the markers are clear.
- `python tools/blender/build_hotel_greybox.py --check .`: GATES PASS (47 pairs, 235 step boxes, the highest rise 0.250 m).
- `export_scene.py` writes the same content as `build_hotel_greybox.py --preview` for all four layout files (the rooms' unchanged).
- `node tools/worlddoc.mjs check`: OK, 0 errors on all four (192 / 73 / 11 / 9 colliders; warnings only that the scenes and links are new to the manifest).
- `glb_inspect.py --budget tris=300000,mb=8`: pass on all four (1.60, 1.68, 1.06, 0.99 MB as it counts; 15 844, 12 384, 2 030 and 906 triangles; 42, 31, 19 and 15 draw calls).
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Axes: the marker-cube check (`--stage axes`) passes in every scene.
- Privacy: the GLBs, WebPs, JSON, stills, scripts and `.blend`s (decompressed) hold no user name, local path, session id or e-mail.

## Sources and licences

Every texture file is already in the repo and CC0 (Poly Haven), reused from earlier scenes:

| File | Used for | Source | Licence |
|---|---|---|---|
| `blender/textures/main_floor/wall_paint_diff.jpg` (`painted_plaster_wall`) | the hall's walls, fascias, balustrade panels, door leaves and jambs, the stairwell's block (with generated joints), the wallpapers' plaster | https://polyhaven.com/a/painted_plaster_wall | CC0 1.0 |
| `blender/textures/laboratory/wall_paint_diff.jpg` (`white_plaster_02`) | ceilings and soffits | https://polyhaven.com/a/white_plaster_02 | CC0 1.0 |
| `blender/textures/factory_floor/concrete_floor_diff.jpg` (`hangar_concrete_floor`, lifted to mid grey) | the stairwell's concrete, the empty room's floor | https://polyhaven.com/a/hangar_concrete_floor | CC0 1.0 |
| `blender/textures/apartment/dark_wood_diff_1k.jpg` (`dark_wood`, lifted) | the desk, table, chairs, skirting, casings | https://polyhaven.com/a/dark_wood | CC0 1.0 |
| `blender/textures/apartment/rough_linen_diff_512.jpg` (`rough_linen`) | the empty room's curtains | https://polyhaven.com/a/rough_linen | CC0 1.0 |

Own work, made by the build with numpy from fixed seeds: the escalator tread, riser and floor plates, the white floor and wall tiles, the three landing carpets, the clue room's carpet and wallpaper, the stripped wallpaper, the bare floor's adhesive, the bed's stain and the wall ghosts, the cork, the sixteen papers (notes, plans, a map, clippings, photographs of a corridor and a door, a calendar), the blind, the grilles and the brushed metal. All geometry is own work. Lettering is geometry from Blender's built-in text font. No downloads, no Meshy, no Higgsfield, no purchases.

## Rebuild

```
blender -b --factory-startup --python tools/blender/build_hotel_stairs.py -- --scenes escalators,other_stairs,clue_room,empty_room --stage all --work <dir>
python tools/blender/build_hotel_stairs.py --pack <scene> --work <dir>          # WebP lightmaps, WebP textures -> world/ (rooms -> world/rooms/)
blender -b --factory-startup blender/scenes/<scene>.blend --python tools/blender/build_hotel_stairs.py -- --scenes <scene> --stage reexport --work <dir>   # applies docs/renders/<scene>/caps.json
```

It ran on the rented GPU box through `fw_remote.sh`, one Blender at a time.

## For the coordinator

1. **Manifest:** add `world/escalators.glb` and `world/other_stairs.glb` to their scenes and apply the lightmaps with `applyLightmaps` (every baked material carries `lightmap` and `lightmap_intensity`; one night set). The atrium's `escalators_L<y>` and `stairs_L<y>` doors meet these scenes' `atrium_L<y>` links, as the greybox's `PAIRS` has them.
2. **Rooms:** `world/rooms/clue_room.glb` and `world/rooms/empty_room.glb` load like floor 1's rooms: at a door's (`room_x`, 0, `room_z`) turned `room_yaw_deg`, with their lightmaps. Floor 3's doors point at `apartment` today; `clue_room` and `empty_room` are the other choices for `room_layout`.
3. **Doors:** the halls' leaves are nodes `DoorLeaf_atrium_L<y>` (one mesh a scene, origin at the hinge); their properties are in the JSON. The rooms have no leaf: the corridor's door is the leaf.
4. **Toggled materials:** `Lamp_Emit` (the escalators' side lamps, wall lights, bulkheads and globe; the stairwell's caged lamps; the rooms' dome, desk lamp and bulb) and `Emergency_Emit` (the green EXIT letters). Both are on in the bake; keep them on.
5. **The collider additions** (above): 128 boxes in `escalators`, 7 in `other_stairs`.

