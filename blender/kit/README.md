# The connector kit

The pieces `docs/BLENDER_AREAS.md` ("The connector kit") asks for that the hotel needs, built once so scenes can link them. Each piece is its own
`.blend` here, an art-only GLB under `world/kit/`, one baked lightmap under `world/lightmaps/`, and its own small layout file under `world/kit/`
(`COL_`, `DoorLeaf_`, `Link_`/`Arrive_`, `Spot_`, `Zone_`, `Marker_`, as `tools/blender/export_scene.py` writes them).

| Piece | `.blend` | GLB | Layout | Lightmap | Light |
|---|---|---|---|---|---|
| Elevator car and doors | `elevator.blend` | `world/kit/elevator.glb` | `world/kit/elevator.json` | `world/lightmaps/kit_elevator_0.webp` | night |
| Stair door with a lit hallway | `stair_door.blend` | `world/kit/stair_door.glb` | `world/kit/stair_door.json` | `world/lightmaps/kit_stair_door_0.webp` | night |
| Safe house room | `safe_house.blend` | `world/kit/safe_house.glb` | `world/kit/safe_house.json` | `world/lightmaps/kit_safe_house_0.webp` | soft |
| Painted-sky hall with an EXIT door | `sky_hall.blend` | `world/kit/sky_hall.glb` | `world/kit/sky_hall.json` | `world/lightmaps/kit_sky_hall_0.webp` | sky-lit |

Not built yet (the hotel does not use them): the service corridor and freight lift, the keycard door, the vent duct.

**How they are made.** `tools/blender/build_kit.py --piece all` (stages art, layout, bake, export, render), then `python tools/blender/kit_pack.py`
(the WebP files, and the brightness factors below). `tools/blender/kit_stair_source.py` read the store's stair door out of
`blender/Look_Over_There.blend` once, read-only, into `stair_door_source.json`. Review stills: `docs/renders/kit/<piece>/`.

## The frame and the pivot

Every piece is built in the same frame: game axes (metres, y up; Blender (x, y, z) is game (x, -z, y)), **the origin is the middle of the piece's
door opening, on the floor, on the face of the wall that meets the host scene**. The host is on +z, and the piece lies toward -z. This is the hotel
room layouts' frame (`tools/blender/build_hotel_greybox.py`). The one exception is the store's stair door: its landing is on +z, in front of the
door, and its hallway on -z, behind it.

A placement is `at` (where the origin goes, in the scene) and `yaw` (the piece's turn about y, as three.js's `rotation.y`): a kit point (x, z)
lands at (at.x + x cos yaw + z sin yaw, at.z - x sin yaw + z cos yaw). A door's `closed_yaw_deg` turns with it (add `yaw`).

## How a scene links a piece

1. **The layout.** In the scene's build script, `tools/blender/kit_place.py`:
   `kit_place.place("elevator", suffix="L4", at=(0.0, 4.0, -14.0), yaw_deg=180.0)`. It appends the piece's layout objects as real objects,
   moved and turned, each name given `_<suffix>` (`DoorLeaf_lift` becomes `DoorLeaf_lift_L4`, `COL_Car_Floor` `COL_Car_Floor_L4`), so
   `export_scene.py` writes them into the scene's own `world/<scene>.json`. The scene leaves a hole in its own wall where the piece's door is.
2. **The art.** Either the page draws `world/kit/<piece>.glb` at the same `at` and `yaw` (its lightmap is its own; the coordinator wires
   that), or the scene appends the art too (`art=True`) and bakes it into its own lightmap. A linked copy (Blender's Link, collection `Art`) is
   enough to see the piece in place while building.
3. **What moves.** The GLB's nodes are named so the page can move them: the elevator's `elevator_car` (up and down the shaft; its `COL_Car_*`
   move with it), `LiftLeaf_L` and `LiftLeaf_R` (each slides 0.6 m outward, along its x), and every hinged door's `Leaf_<door>` (origin at the
   hinge, as its `DoorLeaf_<door>` record; the page swings it as any door).

Emissive materials (`Kit_*_Emit`, `Kit_*_Glow`) are exported at strength 1 on a black base colour, so the page shows their colour as it is. None of
them is one of the page's switched names (`Lamp_Emit`, `Window_Lit`, `Emergency_Emit`): the bakes hold their light on, so they stay on.

## The pieces

### Elevator car and doors (the Intern's look)

From the Intern's cab (`games/intern/data/rooms.json` S7_C, `games/intern/src/walk/props.js` and `materials.js`, read-only): diamond-plate floor,
quilted steel walls, a rust ceiling and kick plates, a caged bulb, the 66-button panel with button 41 lit green in a brass bezel, a three-cell
seven-segment floor indicator, a brass scissor gate folded against the jamb, a handrail; and the landing's two ribbed sliding leaves, its frame,
a steel sill, a brass call button with a lit ring and the indicator over the door. Sized to the greybox's atrium shaft.

| | |
|---|---|
| Car | 2.1 m by 2.1 m, 2.4 m high inside; its front at z -0.25, its back at z -2.35 (the shaft's front wall is z -0.2 to 0) |
| Opening | 1.2 m by 2.2 m; two leaves of 0.6 m |
| Nodes | `elevator_car`, `elevator_landing` (one copy per stop), `LiftLeaf_L`, `LiftLeaf_R` |
| Layout | 12 colliders (`COL_Car_*` move with the car; `COL_Landing_*`: the frame and a 1.8 m by 1.2 m landing stone); `DoorLeaf_lift` (hinge x 0.6, `closed_yaw_deg` 180, `kind: elevator`, `leaves`, `slide_m` 0.6); `Link_lift` at (0, 0, 0.6), `Arrive_lift` (0, 0, 1.0) facing +z; `Spot_call_1`, `Spot_panel_1`; `Marker_Landing` |

**Where it goes in the greybox** (it replaces the placeholder car and the `lift` doors):

| Scene | Door | `at` | `yaw` |
|---|---|---|---|
| `atrium` | `lift_L0`, `lift_L4`, `lift_L8`, `lift_L12` (one landing each; one car moves between them) | (0, y, -14) for y = 0, 4, 8, 12 | 180 |
| `floor_1_lower`, `floor_2_lower`, `floor_3` | `lift` (the car parked behind it, replacing the `LiftCar` shell) | (-20, 0, 0) | 90 |

Placed so, the kit's door record lands exactly on the greybox's: hinge (-0.6, y, -14) with `closed_yaw_deg` 0 in the atrium, (-20, 0, -0.6) with -90
on the floors. The arrive points differ a little: the kit's is 1.0 m out from the wall, the greybox's 1.3 m (atrium) and 1.2 m (floors); a scene
that keeps its own `Arrive_` keeps its own.

### Stair door with a lit hallway (the store's)

The store's stair door is in `blender/Look_Over_There.blend`, made by `tools/blender/backrooms_L1_stairdoors.py`. The kit takes the L1 to L2
one (`DoorLeaf_Stair_L1_L2_up` and `Stair_L1_L2_lower_*`), the one that script built without carving anything.

**It could not be separated cleanly, so part of it is rebuilt to match.** Its meshes are one per material, and two of them run the whole stair shaft:
the side walls (`wallHi`) and the ceiling (`ceil`) are single 6.4 m boxes from the door to the far end of the stairs. The kit keeps every other box
exactly as the store has it (the three boxes of the head wall round the 1.1 m by 2.16 m opening, the landing, the light panel's housing and tube,
and the 1.04 m by 2.12 m leaf with its hinge and swing), turned half round so nothing is mirrored, and cuts the side walls and the ceiling at the
top step, 1.6 m in front of the door. The stair flight and the shaft below the landing (`wallLo`) stay the host's. `stair_door_source.json` is the
store's boxes as read. The store's textures are packed in its file with no listed source, so the kit re-makes its look from the CC0 maps below.

The lit hallway is the one the page draws through an open stair door (`index.html`, `buildPassage`): 10 m by 2.4 m, 2.7 m high, a lamp every 3 m,
L1's wall tint (0xd9c36a), a shut door at the far end. Built here so a Blender-first scene can show it as art.

| | |
|---|---|
| Door | opening 1.1 m by 2.16 m, leaf 1.04 m by 2.12 m, hinge (0.52, 0, -0.1), `closed_yaw_deg` 180, `swing_deg` -90 (the store's, turned) |
| Landing | 2.3 m wide inside, 1.6 m deep, 2.7 m high |
| Hallway | z -0.2 to -10.2, 2.4 m wide, 2.7 m high |
| Nodes | `stair_door_landing`, `Leaf_stair`, `stair_door_hallway`, `Leaf_hall_far` |
| Layout | colliders for the landing, the head wall and the hallway; `DoorLeaf_stair` (`kind: stair door`), `DoorLeaf_hall_far`; `Link_stair` (0, 0, 0.6) and `Arrive_stair` (0, 0, 0.95) facing +z; `Link_hall_far`; `Marker_Landing` |

**Where it goes in the greybox:** every stair door between the corridor floors, which today are 0.94 m plain doors (the kit's is the store's 1.1 m):
`stairwell` (x 20, the east end of `floor_1_lower`, `floor_2_lower`, `floor_3`), `stairs_down` (x 20, `floor_1_upper`, `floor_2_upper`),
`stairs_up` and `roof` (x 26.6, y 3.2, the stairwell's top), and the roof bulkhead's `floor_3` door (6, 0, 8). At a corridor's end the corridor is
the landing: place it with `at` (20, 0, 0), `yaw` -90 and leave out the `stair_door_landing` node and its colliders (`COL_Stair_landing_*`,
`COL_Stair_wallHi_*` other than the head wall's, `COL_Stair_ceil_*`); the hallway goes behind the door, where the greybox has its `StairLanding`.
The openings widen from 0.94 m to 1.1 m.

### Safe house room (the roof's)

A 6 m by 5 m room, 2.8 m high, with its 1.0 m doorway in the south wall: the greybox's roof safe house exactly, moved so its doorway is the origin
(a roof point (x, z) is the kit's (x + 8, z + 5.8)). Every spot is where the greybox has it, and each thing stands where the greybox's box is.

| Thing | What | Spot (kit frame) |
|---|---|---|
| Shop counter | a wooden counter with a till and a bell, shelves of goods on the wall behind | `Spot_shop_1` (-1.9, 0, -3.7) facing -z |
| Stash | two plywood crates under a strapped lid | `Spot_stash_1` (2.4, 0, -3.6) facing -z |
| Save point | a writing bureau on the north wall, an open guest ledger, a lamp with a green glass shade (new: the greybox has the spot only) | `Spot_save_1` (1.0, 0, -4.6) facing -z |
| Crafting bench | a heavy bench on two drawer cabinets, a vice, tools on a pegboard | `Spot_craft_1` (1.7, 0, -2.0) facing +x |
| Respawn pad | a round stone pad, its ring glowing teal (walk-through) | `Spot_respawn_1` (0, 0, -2.8) |
| Locker | a two-door steel locker with vents | `Spot_locker_1` (-1.8, 0, -1.2) facing -x |

Also: `Zone_safe_safe_house` (the room), `Marker_Door` (Entrance), 13 colliders, a pendant lamp and a lantern by the door outside. The outside
walls and roof are their own material (`SH_Outside`), so the roof scene can light them in its own bake; the kit's bake lights them only by the
lantern and the night.

**Where it goes in the greybox:** `roof`, `at` (-8, 0, -5.8), `yaw` 0, replacing the `SafeHouse` shell, the `SH_*` boxes, `decor_Respawn_Pad`, the
zone and the six spots (the kit's names are the greybox's, given the suffix).

### Painted-sky hall with an EXIT door

A 10 m hall, 2.4 m wide and 3.0 m high, between two 1.1 m doors: a painted sky above a white wainscot and dado rail, herringbone parquet, a coffered
white ceiling round a painted-sky laylight (the hall's light), white panel doors with brass levers, and a green EXIT sign over the far door. Its
outer faces are left out: it is entered through its doors.

| | |
|---|---|
| Doors | `DoorLeaf_entry` (hinge (-0.52, 0, -0.1), 0 deg) and `DoorLeaf_exit` (hinge (0.52, 0, -10.3), 180 deg), both 1.04 m by 2.12 m, `swing_deg` 90 |
| Links | `entry`: at (0, 0, -0.7), arrive (0, 0, -1.1) facing -z; `exit`: at (0, 0, -9.7), arrive (0, 0, -9.3) facing +z |
| Nodes | `sky_hall`, `Leaf_entry`, `Leaf_exit` |
| Layout | 10 colliders, 2 doors, 2 links, `Marker_Entry` (Entrance), `Marker_Exit` (Exit) |

**Where it goes in the greybox:** nowhere yet. No hotel scene has a hall between worlds; it is for the Going back in chambers and the gates.

## Lightmaps and brightness

One 1024 px page per piece, baked in Cycles on the rented GPU (384 samples, OIDN). Faces never seen (pressed against another surface, or turned
to the void) are dropped before the bake. `kit_pack.py` sets each material's `lightmap_intensity`; the factors below cap the few small materials
next to a lamp, as B1 did.

| Piece | Material | m² | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|---|
| elevator | `Car_Wall_Quilted` | 15.7 | 0.153 | 0.439 | 0.634 |  |
| elevator | `Car_Rust` | 9.2 | 0.033 | 0.260 | 0.969 | 0.5 |
| elevator | `Landing_Leaf` | 5.8 | 0.066 | 0.168 | 0.274 |  |
| elevator | `Car_Floor_Diamond` | 5.4 | 0.080 | 0.113 | 0.270 |  |
| elevator | `Car_Dark` | 2.6 | 0.006 | 0.066 | 0.202 |  |
| elevator | `Landing_Frame` | 2.5 | 0.010 | 0.046 | 0.072 |  |
| elevator | `Landing_Stone` | 2.3 | 0.112 | 0.229 | 0.383 |  |
| elevator | `Brass` | 1.7 | 0.071 | 0.262 | 0.908 | 0.22 |
| elevator | `Steel_Sill` | 0.4 | 0.045 | 0.104 | 0.199 |  |
| elevator | `Button_Grey` | 0.3 | 0.028 | 0.317 | 0.885 | 0.55 |
| stair_door | `Hall_Wall` | 72.2 | 0.158 | 0.331 | 0.459 |  |
| stair_door | `Stair_Wall` | 24.9 | 0.185 | 0.533 | 0.706 |  |
| stair_door | `Hall_Floor` | 24.7 | 0.050 | 0.107 | 0.182 |  |
| stair_door | `Hall_Ceiling` | 24.5 | 0.057 | 0.087 | 0.760 |  |
| stair_door | `Stair_Door` | 9.5 | 0.043 | 0.135 | 0.303 |  |
| stair_door | `Stair_Ceiling` | 5.9 | 0.084 | 0.148 | 0.185 |  |
| stair_door | `Stair_Floor` | 5.9 | 0.184 | 0.225 | 0.245 |  |
| stair_door | `Fixture_Housing` | 1.8 | 0.083 | 0.872 | 0.872 | 0.55 |
| stair_door | `Door_Handle` | 0.0 | 0.130 | 0.672 | 0.959 | 0.75 |
| safe_house | `SH_Outside` | 103.2 | 0.006 | 0.007 | 0.008 |  |
| safe_house | `SH_Wall` | 76.5 | 0.153 | 0.446 | 0.591 |  |
| safe_house | `SH_Ceiling` | 34.6 | 0.106 | 0.142 | 0.372 |  |
| safe_house | `SH_Floor` | 34.6 | 0.237 | 0.451 | 0.723 |  |
| safe_house | `SH_Wood` | 18.7 | 0.012 | 0.268 | 0.512 |  |
| safe_house | `SH_Trim` | 16.4 | 0.002 | 0.250 | 0.462 |  |
| safe_house | `SH_Ply` | 14.8 | 0.003 | 0.483 | 0.707 |  |
| safe_house | `SH_Steel` | 9.5 | 0.015 | 0.243 | 0.390 |  |
| safe_house | `SH_Iron` | 6.7 | 0.000 | 0.162 | 0.606 |  |
| safe_house | `SH_Goods` | 3.9 | 0.041 | 0.412 | 0.761 |  |
| safe_house | `SH_Pad` | 2.4 | 0.048 | 0.519 | 0.952 | 0.68 |
| safe_house | `SH_Cloth` | 0.2 | 0.000 | 0.070 | 0.314 |  |
| safe_house | `SH_Paper` | 0.1 | 0.594 | 0.843 | 0.933 | 0.2 |
| sky_hall | `Sky_Mural` | 51.4 | 0.663 | 0.876 | 0.932 |  |
| sky_hall | `Sky_Trim` | 35.5 | 0.094 | 0.286 | 0.598 |  |
| sky_hall | `Sky_Floor` | 25.4 | 0.225 | 0.305 | 0.380 |  |
| sky_hall | `Sky_Panel` | 24.2 | 0.152 | 0.190 | 0.204 |  |
| sky_hall | `Sky_Door` | 9.5 | 0.001 | 0.169 | 0.260 |  |
| sky_hall | `Door_Handle` | 0.1 | 0.007 | 0.220 | 0.378 |  |

Measured with the brief's `lab_display.py` (displayed = texture x base colour x lightmap x intensity / pi, area-weighted). The main surfaces read: the car's walls p50 0.15, the hallway's walls 0.16, the safe house's walls 0.15, the sky hall's wainscot 0.15 and its mural 0.66, every p90 at or under 0.88 and every p99 under 0.98. The landing's frame and the safe house's outside (`SH_Outside`) are dark on purpose: the night corridor, and a roof at night (the roof's own bake lights that outside). Low p50s on trim and furniture are their undersides and backs.

## Sources and licences

| Map | Used for | Source | Author | Licence |
|---|---|---|---|---|
| `beige_wall_001`: diffuse, 1k | the stair door's walls and ceilings, the hallway, the elevator's corridor (stills only) | https://polyhaven.com/a/beige_wall_001 | Dimitrios Savva (photography), Rico Cilliers (processing) | CC0 1.0 |
| `plastered_wall_04`: diffuse, 1k | the safe house's walls, ceiling and outside; the sky hall's wainscot, trim and doors | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel | CC0 1.0 |
| `old_wood_floor`: diffuse, 1k | the safe house's floor | https://polyhaven.com/a/old_wood_floor | Guillaume Monsergent | CC0 1.0 |
| `dark_wood`: diffuse, 1k | the safe house's furniture and trim, the stair doors | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `herringbone_parquet`: diffuse, 1k | the sky hall's floor | https://polyhaven.com/a/herringbone_parquet | Sergej Majboroda (photography), Jenelle van Heerden (processing) | CC0 1.0 |
| `painted_metal_shutter`: diffuse, 1k | the elevator's leaves, frame, rust and dark steel; the safe house's locker and vice | https://polyhaven.com/a/painted_metal_shutter | Charlotte Baglioni, Dario Barresi, Rico Cilliers | CC0 1.0 |
| `concrete_floor_02`: diffuse, 1k | the elevator's sill and landing stone, the hallway's floor, the respawn pad | https://polyhaven.com/a/concrete_floor_02 | Rob Tuytel | CC0 1.0 |
| `plywood`: diffuse, 1k | the stash crates, the bench's cabinets, the pegboard | https://polyhaven.com/a/plywood | Rob Tuytel | CC0 1.0 |
| `rough_linen`: diffuse, 512 | the stair landing's carpet, the safe house's goods and ledger | https://polyhaven.com/a/rough_linen | colormass, Rico Cilliers | CC0 1.0 |
| Diamond plate, quilted steel, the painted skies, the EXIT sign | the car's floor and walls, the sky hall | drawn by `build_kit.py` (numpy), after the Intern's recipes | this repo | CC0 1.0 |

The nine maps were already in the repo (`blender/textures/apartment/`, `galleries/`, and the mall entrance's branch); they are copied to
`blender/textures/kit/` unchanged. Nothing was downloaded or bought; no Meshy or Higgsfield model is used.
