# Floor 1, the motel: `floor_1_lower`, `floor_1_upper`, `motel_a`, `motel_b`

The hotel's floor 1 dressed and lit (`docs/BLENDER_AREAS.md`, section 1, step 2): the two corridor levels and the two room layouts that load behind
their doors. A cheap, tired motel at night: a worn maroon carpet runner with a navy border and a gold diamond lattice, two-tone vinyl wallcovering
with a wood chair rail, wood-look room doors with brass numbers and peepholes, drum-shade wall sconces (two of them dead), a water-stained popcorn
ceiling, a built-in ice machine, a fire extinguisher cabinet, louvred staff closets, framed prints, and a red EXIT sign at the stairwell.

This README covers all four scenes. Each scene's folder (`docs/renders/<scene>/`) holds its three stills, its plan, `bake.json` and `caps.json`.

| File | What it is |
|---|---|
| `world/floor_1_lower.glb`, `world/floor_1_upper.glb` | the corridors' art: 2.33 MB / 13 240 triangles / 90 draw calls, and 2.25 MB / 11 900 / 86 (re-baked with the connector kit placed) |
| `world/rooms/motel_a.glb`, `world/rooms/motel_b.glb` | the rooms' art: 0.95 MB / 1 354 triangles / 26 draw calls, and 0.84 MB / 1 642 / 21 |
| `world/lightmaps/<scene>_0.webp`, `_1.webp` | two lightmaps per scene (second UV set): `_0` the shell, `_1` everything in it |
| `world/<scene>.json`, `world/rooms/<layout>.json` | the layout, re-written by `export_scene.py` from the dressed `.blend`: **byte for byte the greybox's** |
| `blender/scenes/<scene>.blend` | the saved scenes (Git LFS): `Art` (`Props`, and `Arch`: the greybox's boxes in grey, for the layout check and the plan), `Skin` (the shell as seen), `Doors` (the leaves and their numbers), `Layout`, `Lights` (with the kit elevator's lamps), `Bake_Standins` (with the kit elevator's art, lower level), `Standins` |
| `tools/blender/build_hotel_floor1.py` | the re-runnable build (all four scenes) |
| `tools/blender/hotel_floor1_skin.py` | pure Python: the shell as seen, the materials of its faces, the dressing slots; `python tools/blender/hotel_floor1_skin.py` prints them |
| `tools/blender/check_layout.py` | two small extensions (below) |

## How it is built

- **The layout is the greybox's.** The build imports `tools/blender/build_hotel_greybox.py`'s model and makes every `COL_` box, `DoorLeaf_`,
  `Link_`/`Arrive_`, `Marker_` and `Spot_` from it, with the same names and numbers. `export_scene.py` then writes the four layout files again, and
  they are identical to the greybox's `--preview` (the rooms' are unchanged in git; the corridors' changed only by the kit, below).
- **The connector kit** (`blender/kit/README.md`) is placed in the greybox's model (`_f1`, with floor 3's `kit_layout()`), as
  `tools/blender/kit_place.py` places it:
  - **The elevator** (lower level) at (-20, 0, 0), yaw 90. The kit's car (parked here; the page moves it) and landing replace the greybox's
    `LiftCar` shell and plain lift door: 8 `Car_*_F1` and 4 `Landing_*_F1` colliders; the kit's door record lands exactly on `DoorLeaf_lift`
    (hinge (-20, 0, -0.6), `closed_yaw_deg` -90) and keeps the id `lift`, now with `kind: elevator`, `leaves`, `slide_m` and `car`; the spots
    `Spot_call_1_F1` and `Spot_panel_1_F1`. The kit's own `Link_`, `Arrive_` and `Marker_Landing` are left out: the greybox's `Link_lift`
    (-19.4, 0, 0), `Arrive_lift` (-18.8, 0, 0) and spawn stay. This scene draws nothing inside the wall's opening (the kit's landing lines it);
    the kit's art and lamps are appended as bake and still stand-ins only (`Bake_Standins`), never in this GLB.
  - **The stair door** at every stair door, yaw -90, without the `stair_door_landing` node (the corridor, the stairwell's top landing and the
    upper landing are the landings): `stairwell` (20, 0, 0) and `stairs_up` (26.6, 3.2, 0) on the lower level, `stairs_down` (20, 0, 0) on the
    upper. Only the kit's door record is used: 1.04 m by 2.12 m, hinge 0.52 m off the middle (x 20.1 / 26.7, z 0.52), `closed_yaw_deg` 90,
    `swing_deg` -90, `kind: stair door`. The ids stay the greybox's, so every link still meets. The openings widen from 0.94 m to the kit's
    1.1 m (`Corridor_Wall_E_*` and `Stairwell_Wall_E_*` rebuilt round 1.1 m holes in `build_hotel_greybox.py`). The leaves are this scene's own
    `Leaf_Fire` at the kit's size and hinge, in this GLB.
  - **Two small changes, and why** (as on floor 3): the corridor gate's clear rectangle starts 8 cm in from the west wall, because the kit
    landing's frame stands 6 cm proud of it; and the call-button spot moves 8 cm toward the corridor's middle (to (-19.55, 0, -0.80)), because
    the kit's spot is inside a walker's 0.28 m of the north wall in a 2.2 m corridor.
  - `place_kit()` checks that every layout object `kit_place.py` brings lands where the model has it (the door records, colliders and spots),
    then removes the kit's copies. `kit_place.py` has floor 3's one-line fix (appended objects start from `matrix_basis`).
- **The shell is only what can be seen** (`hotel_floor1_skin.py`): every face of a greybox box that looks into the air (the corridor, the door
  openings, the alcoves and closets, the lift car, the stairwell above its steps, a room's parts), cut where other boxes meet it. Walls' backs, slab
  undersides and faces pressed together are never drawn; a door opening needs no cutting, as there is no box behind it. This matters for the rooms:
  a room's door wall is the corridor's wall, so the room draws only its inside face and the corridor its own face and the reveals, and the two
  never fight when a room loads behind a door. The corridor's walls are cut at the chair rail (0.9 m) into the lower and upper finish.
- **The props** are built round the boxes and merged by material for export; faces pressed against the shell are dropped. Pieces set into a
  wall (ice machine, extinguisher cabinet, windows) sit inside the wall's thickness and are cut out of the shell.
- **Door leaves are reused meshes.** Within each corridor GLB the ten room doors are one mesh (`Leaf_Room`: wood-look laminate, brass kick plate,
  knobs and deadbolt both sides, a peephole, the fire-escape plan on the room side), the two closets another (`Leaf_Closet`, louvred), the stair
  doors a third (`Leaf_Fire`, steel with a vision panel). Each leaf is its own node named `DoorLeaf_<door>`, origin at the hinge, exactly as its
  layout entry, so the page swings it by name. The **brass numbers** (101 to 120, Blender's built-in text font as geometry) are small child nodes
  `DoorNum_<n>` of their leaf, so they swing with it. One leaf of each kind is baked (`BAKE_LEAF`: room 103 / 113, closet 4, the corridor-side stair
  door) and the others show its lightmap; that fits because every door has a sconce 2 m to either side. For the baked room leaf's back face, a
  stand-in room behind it (bake only) gives it a room's light instead of the void.

## Light

- **The corridors are baked at night** (one set, `lightmap` only): 18 lit sconces of 60 W (Cycles) inside open drum shades, so they throw a scallop
  up the wall and onto the ceiling and a pool down; two sconces are dead (`Lamp_Dead`, no light). Dim opal fittings in the alcoves (the closets'
  are dead), two bulkheads in the stairwell, one on the upper landing, and the EXIT signs' glow.
- **The rooms** are baked with the bedside lamp and the ceiling dome on (and motel_a's bathroom light), with the door open onto a stand-in of the
  corridor outside it: its carpet, walls, ceiling and the same sconces 2 m either side of the door, and the leaf standing open. Every corridor door,
  north or south, lower or upper, has that same surround, and the south rooms are the same rooms turned half round, so **one bake fits whichever
  door a room sits behind**. The stand-in is never exported.
- **Toggled materials:** `Lamp_Emit` (the sconce shades, the alcove fittings, the bulkheads, the rooms' lamp shade, dome and bathroom light;
  emissive 3) and `Emergency_Emit` (the EXIT signs' letters; emissive 5, red). The lift's indicator and call button are now the kit's. Both are in the bake as on: if the
  page switches them off, the baked light stays. No `Window_Lit`. `Glass_Clear` (the extinguisher cabinet's glazing) has no lightmap.
- **Bake:** Cycles on the rented GPU (OptiX), 1024 samples, diffuse direct and indirect, 8 px margin, OIDN. A highlight shoulder rolls the light
  above each map's 70th percentile off toward 2.5 times it (`SHOULDER`), so the sconce scallops and the lamp pools stay soft instead of clipping;
  the white point is the map's 99.5th percentile, and `lightmap_intensity` is pi times it.
- **Pages are fixed** (`PAGES`): the corridors 2048 + 2048, the rooms 1024 + 1024. The shell's UVs are packed by hand (every shell face is a
  rectangle, so each is a pixel-aligned island, shelf-packed at the highest density that fits): 70.6 px/m (lower), 79.6 (upper), 75 (rooms). The
  props are smart-projected and packed: 121, 130, 81 and 73 px/m. A rectangle packed on its side now gets its UVs on its side too (`rect_uv`
  wrote a rotated face's two extents swapped, so a tall face could run into the next row; fixed for the kit re-bake, with an assertion).

| Map | Size | Density | `lightmap_intensity` before the gain | WebP |
|---|---|---|---|---|
| `floor_1_lower_0` / `_1` | 2048 / 2048 | 70.6 / 120.8 px/m | 2.952 / 2.370 | 222 KB / 644 KB |
| `floor_1_upper_0` / `_1` | 2048 / 2048 | 79.6 / 130.1 px/m | 3.884 / 2.610 | 199 KB / 655 KB |
| `motel_a_0` / `_1` | 1024 / 1024 | 75.0 / 81.0 px/m | 4.249 / 3.371 | 31 KB / 107 KB |
| `motel_b_0` / `_1` | 1024 / 1024 | 75.2 / 72.9 px/m | 2.804 / 2.680 | 37 KB / 104 KB |

## Brightness (as the page shows it)

Measured with `lab_display.py` on the packed GLBs (displayed = texture x base colour x lightmap texel x intensity / pi, no tone mapping). Each
scene has one **gain** on its lightmap intensities (`caps.json`), found from the uncapped GLB so the big shell surfaces reach p99 0.9 (p90 0.85):
1.51 (lower), 1.178 (upper) after the kit re-bake (held by the popcorn ceiling's p99), 1.0 (motel_a, held by the bathroom tiles), 1.579 (motel_b). The same file would cap any material over p99 0.97 or
p90 0.88; after the shoulder none was, so every factor is the gain. Main surfaces:

| Scene | Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|---|
| floor_1_lower | Wall_Upper | 149.9 | 0.215 | 0.640 | 0.815 |
| | Ceiling_Popcorn | 93.3 | 0.175 | 0.790 | 0.900 |
| | Carpet_Runner | 88.0 | 0.103 | 0.145 | 0.290 |
| | Wall_Lower | 67.6 | 0.115 | 0.151 | 0.196 |
| | Stair_Paint | 67.1 | 0.108 | 0.302 | 0.469 |
| floor_1_upper | Wall_Upper | 151.5 | 0.182 | 0.613 | 0.821 |
| | Ceiling_Popcorn | 93.3 | 0.151 | 0.783 | 0.900 |
| | Carpet_Runner | 88.0 | 0.092 | 0.130 | 0.258 |
| | Wall_Lower | 68.7 | 0.095 | 0.131 | 0.164 |
| | Stair_Paint | 16.7 | 0.171 | 0.366 | 0.462 |
| motel_a | Wall_Room | 52.2 | 0.201 | 0.378 | 0.637 |
| | Ceiling_Room | 23.7 | 0.247 | 0.615 | 0.848 |
| | Carpet_Room | 20.3 | 0.091 | 0.153 | 0.215 |
| | Tile_Wall | 18.8 | 0.471 | 0.805 | 0.933 |
| motel_b | Wall_Room | 67.4 | 0.245 | 0.401 | 0.485 |
| | Ceiling_Room | 29.8 | 0.274 | 0.601 | 0.900 |
| | Carpet_Room | 29.8 | 0.119 | 0.219 | 0.320 |

No material in any scene is over p90 0.9 or p99 0.98; the most clipped is motel_a's Tile_Wall at 0.06 % of its area. The walls read (p50 0.20 to
0.25) except the corridors' darker lower band below the chair rail (0.10 to 0.13), which is a darker finish on purpose. Carpets are dark by
design. The corridors' end walls now take the upper finish above the chair rail (the skin's finish split read the wrong axis as the height
on x-facing walls, so they were all `Wall_Lower`; fixed for the re-bake), hence the moved areas. The closets' paint (17.7 m2 a level) reads 0:
the closets are shut and their lights dead, so no light reaches them in the bake (the earlier non-zero reading came from the packing overlap
above). Some prop materials show p50 0 (Wood_Laminate, Linen_White, Window_Frame) because their measured area includes faces no one sees
(under the beds' spreads, inside the window recesses).

## Review stills

Cycles, 128 samples adaptive, OIDN, 1920 x 1080 JPEG (comment and APP1 segments stripped), AgX Medium High Contrast, exposure 0, Blender's real lights.

| Scene | `1_arrival` | `2_wide` | `3_detail` |
|---|---|---|---|
| floor_1_lower | the lift's arrival (-18.8, 1.6, 0) facing east, down the corridor | from the stairwell end looking back west | room 103's door: number, peephole, sconce, a closet beyond |
| floor_1_upper | the stair arrival (18.8, 1.6, 0) facing west | from the west end looking east | the alcove at x 12 (a hide spot) |
| motel_a | the room's door marker (0, 1.6, -0.8), looking in | from the door's corner, high | the nightstand, lamp and bed head |
| motel_b | the door marker, looking in | from the door's corner, high | the nightstand between the twin beds, the curtained window |

`plan.jpg` in each folder is a top-down view with the ceilings off (walls in the greybox's grey). The owner sheets (stills, plan and numbers) are
not in the repo.

## Gates

- `blender -b blender/scenes/<scene>.blend --python tools/blender/check_layout.py -- --scene <scene>`: **PASS 95 of 95** (lower, with the kit),
  **63 of 63** (upper), **16 of 16** (motel_a), **17 of 17** (motel_b). Every collider is covered (the shell's boxes by the grey `Arch` twins, whose seen faces
  are the skin; the furniture's by the furniture itself), every tall solid stands on a collider, the markers are clear.
- `python tools/blender/build_hotel_greybox.py --check .`: GATES PASS.
- `export_scene.py` writes the same four layout files as the greybox's `--preview` (the same JSON content; the corridors' changed in git only
  by the kit).
- `node tools/worlddoc.mjs check`: OK, 0 errors on all four (warnings only that the links and room scenes are new to the manifest).
- `glb_inspect.py --budget tris=300000,mb=8`: pass on all four (2.22, 2.15, 0.91, 0.80 MB as it counts).
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Axes: the marker-cube check (`--stage axes`) passes in every scene.
- Privacy: the GLBs, WebPs, JSON, stills, scripts and `.blend`s hold no user name, local path, session id or e-mail.

**`check_layout.py` changes:** it finds a room layout's file under `world/rooms/` when `world/<scene>.json` does not exist; and a tall piece that
sits inside a collider at its own height also counts as standing on it (the flight's upper steps start above 0.5 m, so the check did not count
them as standing). `check_layout_test.py` still passes unchanged.

## Sources and licences

Every texture file is already in the repo and CC0 (Poly Haven), reused from earlier scenes:

| File | Used for | Source | Licence |
|---|---|---|---|
| `blender/textures/main_floor/wall_paint_diff.jpg` (`painted_plaster_wall`, Amal Kumar) | the wallcovering's base (with generated stripes), closets, lift lining, stair ceiling, fire door, room walls | https://polyhaven.com/a/painted_plaster_wall | CC0 1.0 |
| `blender/textures/laboratory/wall_paint_diff.jpg` (`white_plaster_02`, Rob Tuytel) | the popcorn ceilings (tinted) | https://polyhaven.com/a/white_plaster_02 | CC0 1.0 |
| `blender/textures/apartment/dark_wood_diff_1k.jpg` (`dark_wood`) | room doors, jambs, chair rail, casings, furniture laminate, the bathroom door | https://polyhaven.com/a/dark_wood | CC0 1.0 |
| `blender/textures/apartment/rough_linen_diff_512.jpg` (`rough_linen`) | sheets, pillows, curtains (tinted) | https://polyhaven.com/a/rough_linen | CC0 1.0 |
| `blender/textures/main_floor/floor_tiles_diff.jpg` (`floor_tiles_06`, Rob Tuytel) | motel_a's bathroom floor | https://polyhaven.com/a/floor_tiles_06 | CC0 1.0 |
| `blender/textures/factory_floor/concrete_floor_diff.jpg` (`hangar_concrete_floor`, Dimitrios Savva, lifted to mid grey) | the stairwell's concrete | https://polyhaven.com/a/hangar_concrete_floor | CC0 1.0 |

Own work, made by the build with numpy from fixed seeds: the carpet runner, the alcove carpet, the rooms' carpet, the floral bedspread, the
wallcovering's stripes, the stairwell's block joints, the bathroom wall tiles, the water stains (ceiling and floor), the four prints, the
fire-escape plan card, the grilles and the brushed metal. All geometry is own work. Lettering (room numbers, EXIT, ICE, FIRE, STAFF, STAIRS, the
floor and direction signs) is geometry made from Blender's built-in text font. No downloads, no Meshy, no Higgsfield, no purchases.

## Rebuild

```
blender -b --factory-startup --python tools/blender/build_hotel_floor1.py -- --scenes floor_1_lower,floor_1_upper,motel_a,motel_b --stage all --work <dir>
python tools/blender/build_hotel_floor1.py --pack <scene> --work <dir>          # WebP lightmaps, WebP textures -> world/ (rooms -> world/rooms/)
```

`--stage art|size|bake|export|reexport|axes|check|render` run single steps on the saved `.blend`; `reexport` is export and check (used to apply
`caps.json`; `--caps <dir>` reads `<dir>/<scene>.json` instead). `--only <still>` renders one still. It ran on the rented GPU box through
`fw_remote.sh`, one Blender at a time.

## For the coordinator

1. **Manifest:** add `world/floor_1_lower.glb` and `world/floor_1_upper.glb` to their scenes; apply the lightmaps with `applyLightmaps` (every
   baked material carries `lightmap` and `lightmap_intensity`; no night set).
2. **Rooms:** a room door's layout entry carries `room_layout`, `room_x`, `room_z`, `room_yaw_deg`. Load `world/rooms/<room_layout>.glb` at
   (`room_x`, 0, `room_z`) turned `room_yaw_deg`, with its lightmaps. Its door wall overlaps the corridor's exactly and draws only the room side.
3. **Doors:** leaves are nodes `DoorLeaf_<door>`; the numbers `DoorNum_<n>` are their children. The leaves' layout properties are in the JSON, not
   the GLB's extras.
4. **The lift (floor_1_lower):** the connector kit's elevator: draw `world/kit/elevator.glb` at (-20, 0, 0), yaw 90 (its own lightmap
   `kit_elevator_0`; its car `elevator_car` and leaves `LiftLeaf_L`/`LiftLeaf_R` move as `blender/kit/README.md` says). This GLB draws nothing
   inside the west wall's opening (the kit's landing lines it). `DoorLeaf_lift` carries the kit's `leaves`, `slide_m` and `car`.
5. **The stair doors** (`stairwell`, `stairs_up`, `stairs_down`) are 1.1 m openings with this GLB's own `Leaf_Fire` leaves at the kit's size and
   hinge: do not place `world/kit/stair_door.glb` here. They open onto this scene's own stairwell and landing; if the page draws its lit passage
   (`buildPassage`) behind every door of `kind: stair door`, it should not behind these.

## Open

- Not seen in the browser: the page's shading, the leaves swinging and a room loading behind a door are untested.
- The elevator is seen in the stills only from the far end (`2_wide`); no still frames it close.
- Only one leaf per kind is baked: the doors next to the corridor's ends and the stairwell's top door show the middle door's light.
- The room leaves' backs carry light from a stand-in room in the corridor bake, not from the real room behind each door.
