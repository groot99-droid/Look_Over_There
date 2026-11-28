# Hotel greybox (docs/BLENDER_AREAS.md, section 1, step 1)

Plain grey boxes, to scale, for every scene of the apartment tower: 31 scenes and 5 room layouts. There are no reference photos, so every scene is built from its written description, and a photo name in the table is only a label. This is for review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.

- Built by `tools/blender/build_hotel_greybox.py`, which writes `world/<scene>.json` (the room layouts go to `world/rooms/<layout>.json`) through `tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come from `tools/blender/hotel_greybox_sheets.py`.
- `python tools/blender/build_hotel_greybox.py --check .` runs the gates on the exported files: every link meets its other side, every step rises at most 0.27 m, every corridor is at least 1.6 m wide and clear.
- `CHECKS.txt`: the gates and `node tools/worlddoc.mjs check` on every file (0 errors; every warning says a scene or link is new to the manifest).
- `overview.png`: how the scenes join. For each scene, `<scene>_plan.jpg` (top-down, scale bar, rooms, doors and links labelled) and `<scene>_still.jpg` (eye height, 1.55 m).

## Scenes

| Scene | Size | Links (door: where it goes) | Colliders, doors, spots | Mood |
|---|---|---|---|---|
| `lobby` (world/) | 20 m by 22 m, 6 m high (the tower's footprint on the street: x -28 to -8, z -30 to -8) | `street`: city.street (the tower door); `back_hall`: atrium (narrow hall) | 44 colliders, 3 doors; spots: dealer x3, facade x3, npc x1, puzzle x2, shop x3 | peaceful |
| `atrium` (world/) | 36 m by 36 m, 16 m high, four galleries at y 0, 4, 8 and 12, the narrow hall from the lobby 10 m by 1.6 m | `pool_01`: sub_pool_01; `pool_02`: sub_pool_02; `pool_03`: sub_pool_03; `pool_04`: sub_pool_04; `pool_05`: sub_pool_05; `pool_06`: sub_pool_06; `pool_07`: sub_pool_07; `pool_08`: sub_pool_08; `pool_09`: sub_pool_09; `pool_10`: sub_pool_10; `pool_11`: sub_pool_11; `maze`: maze_01 (one way); `maze_exit`: out of maze_07; `stairs_L0`: other_stairs (sub floor); `escalators_L0`: escalators (sub floor); `stairs_L4`: other_stairs (floor 1); `escalators_L4`: escalators (floor 1); `stairs_L8`: other_stairs (floor 2); `escalators_L8`: escalators (floor 2); `stairs_L12`: other_stairs (floor 3); `escalators_L12`: escalators (floor 3); `lift_L0`: the elevator's ground stop; `lift_L4`: floor_1_lower; `lift_L8`: floor_2_lower; `lift_L12`: floor_3; `lobby`: lobby (back door) | 93 colliders, 26 doors; spots: none | the hub |
| `floor_1_lower` (world/) | a corridor 40 m by 2.2 m, 2.8 m high, with rooms on both sides | `lift`: atrium (floor 1 gallery); `stairs_up`: floor_1_upper | 86 colliders, 15 doors; spots: hide x4 | the neighbour hunts |
| `floor_1_upper` (world/) | a corridor 40 m by 2.2 m, 2.8 m high, with rooms on both sides | `stairs_down`: floor_1_lower | 61 colliders, 13 doors; spots: hide x4 | the neighbour hunts |
| `floor_2_lower` (world/) | a corridor 40 m by 2.2 m, 2.8 m high, with rooms on both sides | `dining`: dining; `reception`: reception; `lift`: atrium (floor 2 gallery); `stairs_up`: floor_2_upper | 90 colliders, 17 doors; spots: hide x4 | the neighbour hunts |
| `floor_2_upper` (world/) | a corridor 40 m by 2.2 m, 2.8 m high, with rooms on both sides | `key_room`: key_room; `stairs_down`: floor_2_lower | 63 colliders, 14 doors; spots: hide x4 | the neighbour hunts |
| `dining` (world/) | 14 m by 10 m, 3 m high | `floor_2`: floor_2 corridor | 27 colliders, 1 doors; spots: clue x1, hide x1 | the neighbour's floor |
| `reception` (world/) | 14 m by 10 m, 3 m high | `floor_2`: floor_2 corridor | 12 colliders, 1 doors; spots: clue x1, hide x1, npc x1 | the neighbour's floor |
| `key_room` (world/) | 14 m by 10 m, 3 m high | `floor_2`: floor_2 corridor | 11 colliders, 1 doors; spots: key x1, puzzle x1 | the neighbour's floor |
| `floor_3` (world/) | a corridor 40 m by 2.2 m, 2.8 m high, with rooms on both sides | `lift`: atrium (floor 3 gallery); `roof`: roof | 72 colliders, 13 doors; spots: hide x2 | peaceful |
| `roof` (world/) | 24 m by 24 m, open sky | `floor_3`: floor_3 (stairs down) | 21 colliders, 1 doors; spots: craft x1, locker x1, puzzle x1, respawn x1, save x1, shop x1, stash x1 | peaceful |
| `sub_pool_01` (world/) | 20 m by 20 m, 3.2 m high, a 12 m by 12 m pool | `under_next`: sub_pool_02 (underwater); `atrium`: atrium (sub floor gallery) | 21 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_02` (world/) | 20 m by 20 m, 4 m high, a 7 m by 13 m pool | `under_prev`: sub_pool_01 (underwater); `under_next`: sub_pool_03 (underwater); `atrium`: atrium (sub floor gallery) | 31 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_03` (world/) | 20 m by 20 m, 3.2 m high, a 7 m by 13 m pool | `under_prev`: sub_pool_02 (underwater); `under_next`: sub_pool_04 (underwater); `atrium`: atrium (sub floor gallery) | 21 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_04` (world/) | 20 m by 20 m, 4 m high, a 14 m by 9 m pool | `under_prev`: sub_pool_03 (underwater); `under_next`: sub_pool_05 (underwater); `atrium`: atrium (sub floor gallery) | 29 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_05` (world/) | 20 m by 20 m, 3.2 m high, a 8 m by 15 m pool | `under_prev`: sub_pool_04 (underwater); `under_next`: sub_pool_06 (underwater); `atrium`: atrium (sub floor gallery) | 21 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_06` (world/) | 20 m by 20 m, 4 m high, a 16 m by 8 m pool | `under_prev`: sub_pool_05 (underwater); `under_next`: sub_pool_07 (underwater); `atrium`: atrium (sub floor gallery) | 29 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_07` (world/) | 20 m by 20 m, 3.2 m high, a 11 m by 14 m pool | `under_prev`: sub_pool_06 (underwater); `under_next`: sub_pool_08 (underwater); `atrium`: atrium (sub floor gallery) | 21 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_08` (world/) | 20 m by 20 m, 4 m high, a 11 m by 11 m pool | `under_prev`: sub_pool_07 (underwater); `under_next`: sub_pool_09 (underwater); `atrium`: atrium (sub floor gallery) | 28 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_09` (world/) | 20 m by 20 m, 3.2 m high, a 18 m by 9 m pool | `under_prev`: sub_pool_08 (underwater); `under_next`: sub_pool_10 (underwater); `atrium`: atrium (sub floor gallery) | 21 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_10` (world/) | 20 m by 20 m, 4 m high, a 10 m by 14 m pool | `under_prev`: sub_pool_09 (underwater); `under_next`: sub_pool_11 (underwater); `atrium`: atrium (sub floor gallery) | 28 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `sub_pool_11` (world/) | 20 m by 20 m, 3.2 m high, a 14 m by 14 m pool | `under_prev`: sub_pool_10 (underwater); `under_b1`: lot.B1 (underwater, the long way); `atrium`: atrium (sub floor gallery) | 21 colliders, 1 doors; spots: puzzle x1 | peaceful, flooded |
| `maze_01` (world/) | 16 m by 16 m, 3 m high, 8 by 8 cells of 2.00 m | `entry`: from the atrium (or the elevator's glitch); `way_on`: maze_02 | 34 colliders, 2 doors; spots: puzzle x1 | hostile, one way |
| `maze_02` (world/) | 16 m by 16 m, 3 m high, 7 by 7 cells of 2.29 m | `entry`: from maze_01; `way_on`: maze_03 | 25 colliders, 2 doors; spots: puzzle x1 | hostile, one way |
| `maze_03` (world/) | 16 m by 16 m, 3 m high, 8 by 8 cells of 2.00 m | `entry`: from maze_02; `way_on`: maze_04 | 39 colliders, 2 doors; spots: puzzle x1 | hostile, one way |
| `maze_04` (world/) | 16 m by 16 m, 3 m high, 7 by 7 cells of 2.29 m | `entry`: from maze_03; `way_on`: maze_05 | 32 colliders, 2 doors; spots: puzzle x1 | hostile, one way |
| `maze_05` (world/) | 16 m by 16 m, 3 m high, 8 by 8 cells of 2.00 m | `entry`: from maze_04; `way_on`: maze_06 | 38 colliders, 2 doors; spots: puzzle x1 | hostile, one way |
| `maze_06` (world/) | 16 m by 16 m, 3 m high, 7 by 7 cells of 2.29 m | `entry`: from maze_05; `way_on`: maze_07 | 32 colliders, 2 doors; spots: puzzle x1 | hostile, one way |
| `maze_07` (world/) | 16 m by 16 m, 3 m high, 8 by 8 cells of 2.00 m | `entry`: from maze_06; `way_on`: atrium (maze exit) | 43 colliders, 2 doors; spots: puzzle x1 | hostile, one way |
| `escalators` (world/) | 6 m by 8.8 m, 15.2 m high: three escalator runs between the galleries | `atrium_L0`: atrium (sub floor gallery); `atrium_L4`: atrium (floor 1 gallery); `atrium_L8`: atrium (floor 2 gallery); `atrium_L12`: atrium (floor 3 gallery) | 64 colliders, 4 doors; spots: none | connector |
| `other_stairs` (world/) | 5.2 m by 6 m, 15.2 m high: a switchback, two flights a level, a half landing between | `atrium_L0`: atrium (sub floor gallery); `atrium_L4`: atrium (floor 1 gallery); `atrium_L8`: atrium (floor 2 gallery); `atrium_L12`: atrium (floor 3 gallery) | 66 colliders, 4 doors; spots: none | connector |
| `motel_a` (world/rooms/) | 4 m by 6 m, 2.8 m high | none: loaded behind a corridor door | 14 colliders, 0 doors; spots: bed x1, hide x1 | room |
| `motel_b` (world/rooms/) | 5 m by 6 m, 2.8 m high | none: loaded behind a corridor door | 15 colliders, 0 doors; spots: bed x2, hide x1 | room |
| `green_room` (world/rooms/) | 5 m by 7 m, 2.8 m high | none: loaded behind a corridor door | 13 colliders, 0 doors; spots: bed x1, hide x1 | room |
| `clue_room` (world/rooms/) | 5 m by 6 m, 2.8 m high | none: loaded behind a corridor door | 11 colliders, 0 doors; spots: clue x3, puzzle x1 | room |
| `empty_room` (world/rooms/) | 6 m by 8 m, 2.8 m high | none: loaded behind a corridor door | 9 colliders, 0 doors; spots: none | room |

## Links between scenes

Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. Every pair has both sides built (the gate checks it).

| From | To | Connector | Note |
|---|---|---|---|
| `lobby.back_hall` | `atrium.lobby` | doors | the back door past the deli, then the narrow hall (the manifest's hotel.lobby>atrium) |
| `atrium.lift_L4` | `floor_1_lower.lift` | elevator | the elevator to floor 1 (hotel.atrium>floors) |
| `atrium.lift_L8` | `floor_2_lower.lift` | elevator | the elevator to floor 2 |
| `atrium.lift_L12` | `floor_3.lift` | elevator | the elevator to floor 3 |
| `floor_1_lower.stairs_up` | `floor_1_upper.stairs_down` | stairs | hotel.floor_1_stairs |
| `floor_2_lower.stairs_up` | `floor_2_upper.stairs_down` | stairs | floor 2's stairs |
| `floor_2_lower.dining` | `dining.floor_2` | doors |  |
| `floor_2_lower.reception` | `reception.floor_2` | doors |  |
| `floor_2_upper.key_room` | `key_room.floor_2` | doors |  |
| `floor_3.roof` | `roof.floor_3` | stairs | stairs up to the roof |
| `atrium.maze` | `maze_01.entry` | one_way | hotel.atrium>maze: one way in (and the elevator's glitch) |
| `maze_01.way_on` | `maze_02.entry` | one_way | one way, once solved |
| `maze_02.way_on` | `maze_03.entry` | one_way | one way, once solved |
| `maze_03.way_on` | `maze_04.entry` | one_way | one way, once solved |
| `maze_04.way_on` | `maze_05.entry` | one_way | one way, once solved |
| `maze_05.way_on` | `maze_06.entry` | one_way | one way, once solved |
| `maze_06.way_on` | `maze_07.entry` | one_way | one way, once solved |
| `maze_07.way_on` | `atrium.maze_exit` | one_way | out of the maze, once solved |
| `atrium.pool_01` | `sub_pool_01.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_02` | `sub_pool_02.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_03` | `sub_pool_03.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_04` | `sub_pool_04.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_05` | `sub_pool_05.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_06` | `sub_pool_06.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_07` | `sub_pool_07.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_08` | `sub_pool_08.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_09` | `sub_pool_09.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_10` | `sub_pool_10.atrium` | doors | the sub-floor gallery's pool doors |
| `atrium.pool_11` | `sub_pool_11.atrium` | doors | the sub-floor gallery's pool doors |
| `sub_pool_01.under_next` | `sub_pool_02.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_02.under_next` | `sub_pool_03.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_03.under_next` | `sub_pool_04.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_04.under_next` | `sub_pool_05.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_05.under_next` | `sub_pool_06.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_06.under_next` | `sub_pool_07.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_07.under_next` | `sub_pool_08.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_08.under_next` | `sub_pool_09.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_09.under_next` | `sub_pool_10.under_prev` | pool_route | underwater; shut until swimming exists |
| `sub_pool_10.under_next` | `sub_pool_11.under_prev` | pool_route | underwater; shut until swimming exists |
| `atrium.escalators_L0` | `escalators.atrium_L0` | escalator |  |
| `atrium.escalators_L4` | `escalators.atrium_L4` | escalator |  |
| `atrium.escalators_L8` | `escalators.atrium_L8` | escalator |  |
| `atrium.escalators_L12` | `escalators.atrium_L12` | escalator |  |
| `atrium.stairs_L0` | `other_stairs.atrium_L0` | stairs |  |
| `atrium.stairs_L4` | `other_stairs.atrium_L4` | stairs |  |
| `atrium.stairs_L8` | `other_stairs.atrium_L8` | stairs |  |
| `atrium.stairs_L12` | `other_stairs.atrium_L12` | stairs |  |

Links that leave the hotel, or stay inside one scene:

- `lobby.street`: city.street, the tower's door (x -8, z -19): the street is built by code (shared/city.js); the manifest's city.street>hotel_lobby
- `sub_pool_11.under_b1`: lot.B1's pools, underwater, the long way (hotel.sub_pools>lot.B1); B1 is part 1's scene and is not touched
- `atrium.lift_L0`: the elevator's ground stop: the car moves between the atrium's four stops (code); no other scene

## Room layouts behind the corridor doors

A corridor door's `DoorLeaf_room_<n>` carries `room` (its number), `room_layout`, and where the room's frame goes: `room_x`, `room_z` (the frame's origin, the middle of the doorway on the corridor's face of the wall) and `room_yaw_deg` (three's rotation.y; 0 on the north side, 180 on the south). In `world/rooms/<layout>.json` the room lies toward -z from that origin; its door wall is the corridor's wall, so the two overlap exactly. The exporter now keeps a door's custom properties (a separate commit).

## The defaults ([DEFAULT] in docs/BLENDER_AREAS.md)

| Scene | Default | Kept or changed |
|---|---|---|
| lobby | 20 m by 22 m, 6 m high, on the tower's footprint (x -28 to -8, z -30 to -8) | Kept. The walls stand inside the footprint, so the floor is 19.6 m by 21.6 m. The front doors are a 1.8 m pair at z -19 (the street's door size). |
| atrium | 36 m by 36 m, galleries at y 0, 4, 8 and 12 | Kept, 16 m high. The galleries are 4 m deep on all four sides. The narrow hall from the lobby (10 m by 1.6 m) is built into this scene, on its east side. |
| floor_1/2 lower and upper | a corridor 40 m by 2.2 m, rooms both sides, 10 doors a level | Kept: 2.8 m high, doors every 8 m. The lower levels add a 6.4 m stairwell at the east end (the scene is 47 m long); the upper levels a 1.4 m landing. |
| dining, reception, key_room | about 14 m by 10 m | Kept: 14 m by 10 m, 3 m high. |
| floor_3 | one corridor, 10 doors, one level | Kept, the same corridor as floors 1 and 2, with the stairwell up to the roof. |
| roof | 24 m by 24 m, open sky | Kept: a 1.1 m parapet, the stair bulkhead and the kit's safe house as a 6 m by 5 m room. |
| sub_pool_01 to 11 | about 20 m by 20 m | Kept, 3.2 m (odd) or 4 m (even) high; each pool differs in size and place, 1.2 m shallow and 2.4 m deep. |
| maze_01 to 07 | about 16 m by 16 m | Kept, 3 m high: 8 by 8 cells of 2 m (odd) or 7 by 7 of 2.29 m (even); the odd ones have a 4 m room in the middle. |
| escalators, other_stairs | connector-sized | 6 m by 8.8 m and 5.2 m by 6 m, both 15.2 m high, reaching all four galleries. |
| room layouts | 4 m by 6 m to 6 m by 8 m | motel_a 4 x 6, motel_b 5 x 6, green_room 5 x 7, clue_room 5 x 6, empty_room 6 x 8 (all 2.8 m high). |

Choices the table left open:

- The atrium has a second maze door, `maze_exit` on its east wall, where you come out after solving maze_07 (the table names only the way in).
- The elevator stops at the atrium's four galleries. Floors 1 and 2 have it on their lower level only; their upper levels are reached by the stairs.
- Spot kinds the table does not name: `npc` (the receptionists), `clue` and `key` (the key rooms, clue_room), `facade` (the lobby's three facade doors, places for later features), and the safe house's `stash`, `save`, `craft`, `respawn` and `locker`.
- The manifest's hotel stub lists `sub_pools` and `anomaly_maze`; the greybox uses `sub_pool_01` to `11` and `maze_01` to `07`, as docs/BLENDER_AREAS.md does.

## Open questions for the owner

1. Scale: the lobby fills the tower's 20 m by 22 m footprint, but the atrium behind it is 36 m by 36 m, bigger than the tower. Keep it (bigger inside, liminal), or shrink it to about 20 m?
2. The atrium's ground floor is the sub-floor gallery (y 0), and the lobby's hall comes in there. Fine, or should the lobby's hall arrive between the sub floor and floor 1?
3. Floors 1 and 2: should the elevator also stop on their upper levels? Now it stops on the lower levels only.
4. The anomaly maze is one fixed chain, maze_01 to maze_07 and then out. Or should each maze lead back to the atrium, with the elevator's glitch picking one?
5. Rooms: floor 1 alternates motel_a and motel_b, floor 2 is all green_room, floor 3's doors point at part 1's apartment, with clue_room and empty_room as the other choices. Is that the mix you want?
6. The pools: each has a shallow and a deep end, with steps down; the odd ones also have 12 cm of water over the whole floor. Is that the flooded look you want?
7. The key rooms: dining and reception open off floor 2's lower level, the key room off its upper level. Is that right?

## Not done here

- Placeholders: the elevator is a shaft with a box for a car, and each corridor has a closed lift car behind its lift door; the connector kit replaces them later. The escalators are stairs (one box a step).
- The roof's skyline is an R3 backdrop, still to render. Swimming is not in the game, so the pools' underwater links stay shut.
- The manifest, `index.html`, `shared/` and the tests are untouched. `node tools/worlddoc.mjs check` warns that each scene and link is new; that is expected until the coordinator adds them.
