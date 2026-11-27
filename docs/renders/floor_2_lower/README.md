# Floor 2, green carpet: `floor_2_lower`, `floor_2_upper`, `dining`, `reception`, `key_room`, `green_room`

The hotel's floor 2 dressed and lit (`docs/BLENDER_AREAS.md`, section 1, step 2): the two corridor levels, the three key rooms off them and the room
layout that loads behind their twenty doors. An older, grander floor than the motel, but faded: deep green patterned carpet, a cream panelled
wainscot under a green damask paper, brass sconces with cream shades (two dead a level), heavy panelled doors with brass numbers 201 to 220, a
console table with a celadon vase under a gilt mirror, framed landscapes, exit signs; and the connector kit's elevator and stair doors.

This README covers all six scenes. Each scene's folder (`docs/renders/<scene>/`) holds its three stills, its plan, `bake.json` and `caps.json`.

| File | What it is |
|---|---|
| `world/floor_2_lower.glb`, `world/floor_2_upper.glb` | the corridors' art: 2.77 MB / 29 882 triangles / 101 draw calls, and 2.62 MB / 26 572 / 93 |
| `world/dining.glb`, `world/reception.glb`, `world/key_room.glb` | the key rooms' art: 2.60 MB / 26 110 / 28, 2.23 MB / 16 416 / 28, 2.76 MB / 24 686 / 28 |
| `world/rooms/green_room.glb` | the room layout's art: 0.97 MB / 3 276 triangles / 23 draw calls |
| `world/lightmaps/<scene>_0.webp`, `_1.webp` | two lightmaps per scene (second UV set): `_0` the shell, `_1` everything in it |
| `world/<scene>.json`, `world/rooms/green_room.json` | the layouts, written by `export_scene.py` from the dressed `.blend`: identical to `build_hotel_greybox.py --preview` |
| `blender/scenes/<scene>.blend` | the saved scenes (Git LFS): `Art` (`Props`, and `Arch`: the colliders' grey twins, for the layout check and the plan), `Skin`, `Doors`, `Layout`, `Lights`, `Kit` (the kit elevator's stand-in, never exported), `Bake_Standins`, `Standins` |
| `tools/blender/build_hotel_floor2.py` | the re-runnable build (all six scenes) |
| `tools/blender/hotel_floor2_skin.py` | pure Python: the shell as seen, its faces' materials, the dressing slots; `python tools/blender/hotel_floor2_skin.py` prints them |

## How it is built

Floor 1's method and code (`build_hotel_floor1.py`, `hotel_floor1_skin.py` on `claude/blender-hotel-floor1`), made into floor 2's own script.

- **The layout is the greybox's.** The build makes every `COL_` box, `DoorLeaf_`, `Link_`/`Arrive_`, `Marker_` and `Spot_` from
  `build_hotel_greybox.py`'s model; `export_scene.py` then writes the six layout files, and they are byte for byte what `--preview` writes.
- **What changed in the greybox** (`tools/blender/build_hotel_greybox.py`, re-exported; only floor 2's files change, every link, spot and step
  stays where it was):
  - the stair openings on floor 2 widen from 0.94 m to the kit's 1.1 m (`corridor_floor(..., stair_w=1.1)`: the stairwell door at x 20, the
    stairwell's top door at x 26.6, the upper level's stair door at x 20);
  - **the connector kit's records** (`kit_floor2`, with floor 3's `kit_layout()` helper, as `tools/blender/kit_place.py` places them): on
    `floor_2_lower` the elevator at (-20, 0, 0), yaw 90, replaces the LiftCar shell and the lift door (the door keeps the id `lift`; the kit's own
    Link/Arrive/Marker are left out, the greybox's stay; its 12 colliders and `Spot_call_1_F2`, `Spot_panel_1_F2` come in, the call-button spot
    8 cm off the north wall so a walker can stand there, and the corridor gate's rectangle starts 8 cm in, past the landing frame); the kit's stair
    door record at `stairwell` and `stairs_up` (lower) and `stairs_down` (upper), yaw -90, without the landing (the corridor is the landing) or its
    colliders;
  - new colliders for new solid furniture: a `Console` in one alcove a level (20 cm deep, clear of the hide spot); in `green_room` a `Desk`
    (the writing desk and its chair) and a `Nightstand`; in `key_room` `Key_Cabinets_W`, `Key_Hooks_E` and `Key_Cage` (round the safe).
- **The kit's art.** The page draws `world/kit/elevator.glb` at (-20, 0, 0), yaw 90 (its car moves, its leaves slide): here it is only a
  stand-in in the bake and the stills. The opening is left clean, lined in steel. The stair doors' leaf is the kit's (the store's 1.04 m door and
  its handle), read once from `blender/kit/stair_door.blend` into one mesh with its origin at the hinge (`Leaf_Kit`) that every stair door
  reuses, baked into this scene's lightmap. The kit's lit hallway is not used: the page draws its own passage behind a link door.
- **The shell is only what can be seen**, as on floor 1; the kit's colliders are never drawn (their art is the kit's).
- **Door leaves are reused meshes:** the twenty room doors and the doors to the key rooms are one panelled leaf (`Leaf_Room`: six raised panels
  both sides, a brass kick plate, levers and a deadbolt both sides, a peephole, the fire-escape plan on the room side); the closets another
  (`Leaf_Closet`, cream, panelled); the stair doors the kit's. Each leaf is its node `DoorLeaf_<door>`, origin at the hinge; the brass numbers
  (201 to 220, Blender's built-in font as geometry) are child nodes `DoorNum_<n>` on the lock rail. One leaf of each kind is baked (`BAKE_LEAF`).
  The key rooms' own door (`DoorLeaf_floor_2`) is the same panelled leaf, hinged on the room side.

## Light

- **Everything is baked at night**, one set (`lightmap` only). Corridors: 18 lit brass sconces a level (80 W Cycles each, two dead,
  `Lamp_Dead`), dim opal fittings in the alcoves (the closets' dead), bulkheads in the stairwell and on the upper landing, the EXIT signs.
  Dining: three chandeliers and six sconces. Reception: two chandeliers, eight sconces, the banker's lamp and two side lamps. Key room: **one
  lamp**, a green enamel pendant over the desk. Green room: the ceiling bowl, the bedside lamp and the desk lamp, with the door open onto a
  stand-in of the corridor (sconces 2 m either side), so **one bake fits whichever door** it sits behind. The key rooms' bakes also have a short
  stand-in corridor behind their door (bake only).
- **Toggled materials:** `Lamp_Emit` (shades, chandelier shades, bowls, bulbs; emissive 3) and `Emergency_Emit` (EXIT letters; emissive 5). Both
  are in the bake as on. No `Window_Lit` (the dining room's and the green room's windows look onto darkness). `Glass_Clear` has no lightmap.
- **Bake:** Cycles on the rented GPU (OptiX), 1024 samples, diffuse direct and indirect, 8 px margin, OIDN, a highlight shoulder (above the
  map's 70th percentile, toward 2.5 times it; the key room 35th / 2.0, the dining room 65th / 2.4), white point the 99.5th percentile.
- **Pages are fixed** (`PAGES`): 2048 + 2048 for the corridors and key rooms, 1024 + 1024 for the green room. The shell is packed by hand
  (pixel-aligned rectangles); the props are smart-projected.

| Map | Size | Density (px/m) | `lightmap_intensity` before the gain | WebP |
|---|---|---|---|---|
| `floor_2_lower_0` / `_1` | 2048 / 2048 | 70.3 / 34.8 | 2.789 / 1.922 | 204 KB / 515 KB |
| `floor_2_upper_0` / `_1` | 2048 / 2048 | 80.5 / 35.3 | 3.909 / 1.912 | 169 KB / 513 KB |
| `dining_0` / `_1` | 2048 / 2048 | 88.6 / 44.5 | 2.840 / 1.774 | 112 KB / 601 KB |
| `reception_0` / `_1` | 2048 / 2048 | 89.0 / 31.9 | 3.482 / 1.795 | 106 KB / 430 KB |
| `key_room_0` / `_1` | 2048 / 2048 | 89.0 / 27.6 | 0.359 / 0.072 | 78 KB / 473 KB |
| `green_room_0` / `_1` | 1024 / 1024 | 70.0 / 47.5 | 2.519 / 1.983 | 35 KB / 132 KB |

## Brightness (as the page shows it)

Measured with `lab_display.py` on the packed GLBs (displayed = texture x base colour x lightmap texel x intensity / pi, no tone mapping). Each
scene has one **gain** on its lightmap intensities (`caps.json`), chosen from the uncapped GLB so its walls (`Wall_*`) reach p50 0.16 (at most 6,
8 for the key room): 3.404 (both corridors), 1.29 (dining), 3.019 (reception), 8.0 (key room), 2.162 (green room). Any material that would then
pass p99 0.97 or p90 0.88 is capped by its own factor (the ceilings, the cream trim, the closets' paint). No material in any scene is over p90
0.9 or p99 0.98. Main surfaces:

| Scene | Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|---|
| floor_2_lower | Wall_Green | 144.4 | 0.161 | 0.561 | 0.760 |
| | Ceiling_Plaster | 93.3 | 0.110 | 0.826 | 0.971 |
| | Carpet_Green | 88.0 | 0.085 | 0.179 | 0.500 |
| | Wainscot | 70.3 | 0.306 | 0.594 | 0.729 |
| | Stair_Paint | 67.1 | 0.215 | 0.593 | 0.908 |
| floor_2_upper | Wall_Green | 147.0 | 0.153 | 0.677 | 0.970 |
| | Ceiling_Plaster | 93.3 | 0.080 | 0.785 | 0.969 |
| | Carpet_Green | 88.0 | 0.102 | 0.215 | 0.600 |
| | Wainscot | 72.4 | 0.346 | 0.605 | 0.770 |
| dining | Wall_Hall | 86.3 | 0.161 | 0.323 | 0.479 |
| | Ceiling_Hall | 140.0 | 0.137 | 0.534 | 0.734 |
| | Carpet_Hall | 140.0 | 0.026 | 0.057 | 0.146 |
| | Wainscot | 44.7 | 0.151 | 0.339 | 0.601 |
| reception | Wall_Hall | 94.9 | 0.160 | 0.406 | 0.717 |
| | Ceiling_Hall | 140.0 | 0.151 | 0.603 | 0.970 |
| | Carpet_Hall | 140.0 | 0.065 | 0.140 | 0.349 |
| | Wainscot | 47.1 | 0.215 | 0.405 | 0.969 |
| key_room | Wall_Hall | 94.9 | 0.162 | 0.208 | 0.246 |
| | Ceiling_Hall | 140.0 | 0.246 | 0.363 | 0.480 |
| | Carpet_Hall | 140.0 | 0.028 | 0.062 | 0.154 |
| | Wainscot (dark wood) | 47.1 | 0.062 | 0.114 | 0.158 |
| green_room | Wall_Room | 73.9 | 0.161 | 0.476 | 0.830 |
| | Ceiling_Room | 34.8 | 0.237 | 0.629 | 0.970 |
| | Carpet_Room | 34.8 | 0.037 | 0.062 | 0.122 |

The walls read (p50 0.15 to 0.16 everywhere). The carpets are dark green by design, as is the key room's dark wood panelling; the dark wood
furniture and leaves show p50 near 0 partly because their measured area includes faces no one sees (undersides, backs against walls).

## Review stills

Cycles, 128 samples adaptive, OIDN, 1920 x 1080 JPEG (comment and APP1 segments stripped), AgX Medium High Contrast, exposure 0, Blender's real
lights (not the lightmaps). `plan.jpg` in each folder is a top-down view with the ceilings off.

| Scene | `1_arrival` | `2_wide` | `3_detail` |
|---|---|---|---|
| floor_2_lower | the lift's arrival (-18.8, 1.6, 0) facing east | from the stairwell end looking back west, to the kit's elevator | room 203's door: panels, number, peephole, sconce |
| floor_2_upper | the stair arrival (18.8, 1.6, 0) facing west | from the west end looking east | the console alcove (x 4): table, vase, mirror |
| dining | the door's arrival (0, 1.6, 3.8) | from the south-east corner | a table laid for two |
| reception | the door's arrival | from the south-west corner, by the club chairs | the counter: bell, guest book, banker's lamp |
| key_room | the door's arrival | from the south-west corner | the north wall of numbered hooks |
| green_room | the door marker (0, 1.6, -0.8) | from the door's corner, high | the writing desk |

## Gates

- `blender -b blender/scenes/<scene>.blend --python tools/blender/check_layout.py -- --scene <scene>`: **PASS** 100 of 100 (floor_2_lower),
  66 of 66 (floor_2_upper), 29 of 29 (dining), 14 of 14 (reception), 16 of 16 (key_room), 17 of 17 (green_room).
- `python tools/blender/build_hotel_greybox.py --check .`: GATES PASS (47 pairs, 235 step boxes, highest rise 0.25 m, narrowest corridor 1.6 m).
- `export_scene.py` writes the same six layout files as `build_hotel_greybox.py --preview`.
- `node tools/worlddoc.mjs check`: OK, 0 errors on all six (warnings only: new scenes and new links for the manifest).
- `glb_inspect.py --budget tris=300000,mb=8`: pass on all six.
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Axes: the marker-cube check (`--stage axes`) passes in every scene.
- Privacy: the GLBs, WebPs, JSON, stills, scripts and the decompressed `.blend`s hold no user name, local path, session id or e-mail.

**Other tool changes:** `tools/blender/check_layout.py` takes floor 1's two changes (a room layout's file under `world/rooms/`; a tall piece
inside a collider at its own height counts as standing). `tools/blender/kit_place.py` takes the floor-3 fix (an appended object starts from its
`matrix_basis`; empties used to land on `at`).

## Sources and licences

Every texture file is already in the repo and CC0 (Poly Haven):

| File | Used for | Source | Licence |
|---|---|---|---|
| `blender/textures/main_floor/wall_paint_diff.jpg` (`painted_plaster_wall`) | the wainscot, cream trim, closets, window frames, the bathroom door, stairwell paint | https://polyhaven.com/a/painted_plaster_wall | CC0 1.0 |
| `blender/textures/laboratory/wall_paint_diff.jpg` (`white_plaster_02`) | the ceilings (tinted) | https://polyhaven.com/a/white_plaster_02 | CC0 1.0 |
| `blender/textures/apartment/dark_wood_diff_1k.jpg` (`dark_wood`) | doors, jambs, trim, skirting, all the furniture, the key room's panelling | https://polyhaven.com/a/dark_wood | CC0 1.0 |
| `blender/textures/apartment/rough_linen_diff_512.jpg` (`rough_linen`) | tablecloths, drapes, upholstery, velvet, sheets (tinted) | https://polyhaven.com/a/rough_linen | CC0 1.0 |
| `blender/textures/galleries/marble_01_diff_1k.jpg` (`marble_01`) | the reception counter's top | https://polyhaven.com/a/marble_01 | CC0 1.0 |
| `blender/textures/factory_floor/concrete_floor_diff.jpg` (`hangar_concrete_floor`) | the stairwell's concrete | https://polyhaven.com/a/hangar_concrete_floor | CC0 1.0 |
| `blender/kit/stair_door.blend`, `blender/kit/elevator.blend` | the stair door's leaf (baked here); the elevator's stand-in | the connector kit (`blender/kit/README.md`) | CC0 1.0 |

Own work, made by the build with numpy from fixed seeds: the green carpets (corridor, alcoves, the key rooms' rosette carpet, the green room's
trellis), the damask papers, the striped paper, the stairwell block, the quilted bedspread, the leather grain, the four landscapes, the clock
face, the ledger pages, the fire-escape card, the number-plate atlases (a 3 x 5 digit font), the water stains and the brushed metal. All
geometry is own work. Lettering (room numbers, EXIT, STAIRS, STAFF, DINING ROOM, RECEPTION, KEY ROOM, the floor and direction signs) is geometry
from Blender's built-in text font. No downloads, no Meshy, no Higgsfield, no purchases.

## Rebuild

```
blender -b --factory-startup --python tools/blender/build_hotel_floor2.py -- --scenes floor_2_lower,floor_2_upper,dining,reception,key_room,green_room --stage all --work <dir>
python tools/blender/build_hotel_floor2.py --pack <scene> --work <dir>          # WebP lightmaps, WebP textures -> world/ (green_room -> world/rooms/)
```

`--stage art|preview|layout|size|bake|export|reexport|axes|check|render` run single steps on the saved `.blend` (`preview`: art, the layout file,
the check and the stills; `reexport`: export and check, used to apply `caps.json`; `--caps <dir>` reads `<dir>/<scene>.json`). It ran on the
rented GPU box through `fw_remote.sh`, one Blender at a time.

## For the coordinator

1. **Manifest:** add `world/floor_2_lower.glb`, `world/floor_2_upper.glb`, `world/dining.glb`, `world/reception.glb` and `world/key_room.glb` to
   their scenes; apply the lightmaps with `applyLightmaps` (every baked material carries `lightmap` and `lightmap_intensity`; no night set).
2. **Rooms:** a room door's entry carries `room_layout` (`green_room` for all twenty), `room_x`, `room_z`, `room_yaw_deg`. Load
   `world/rooms/green_room.glb` there, with its lightmaps.
3. **The kit:** on `floor_2_lower` draw `world/kit/elevator.glb` at (-20, 0, 0), yaw 90 (its own lightmap). `DoorLeaf_lift` carries the kit's
   `leaves`, `slide_m` and `car`. The stair doors' leaves are in this scene's GLB (`DoorLeaf_stairwell`, `DoorLeaf_stairs_up`,
   `DoorLeaf_stairs_down`), each a node at its hinge; the kit's hallway is not drawn (the page's passage is).
4. **Doors to the key rooms:** `DoorLeaf_dining`, `DoorLeaf_reception` (lower) and `DoorLeaf_key_room` (upper), with brass plaques over them; the
   key rooms' own `DoorLeaf_floor_2` leaves are in their GLBs.

## Open

- Not seen in the browser: the page's shading, the leaves swinging, a room loading behind a door, the kit's elevator GLB in place.
- Only one leaf per kind is baked; the doors near the corridor ends show the middle door's light.
- The props maps' density is lower than floor 1's (28 to 48 px/m): the panelled wainscot and the furniture are many small islands.
- The key room is lit by one lamp, as asked: its walls reach p50 0.16 only with a gain of 8, and its furniture stays dark.
