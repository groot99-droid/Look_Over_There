# Right Door, Wrong Exit greybox (docs/BLENDER_AREAS.md, section 7, step 1)

Plain boxes, to scale, for the Right Door, Wrong Exit rooms: the seven that exist remade larger and psychedelic (Phase A), the set pieces (Phase B: the finale's hide-and-seek map; the repeating room with the door seen from one angle) and 34 proposed new rooms, one minimal greybox each (Phase C, listed one line a room in `ROOMS.md`). Nothing is dressed and nothing is wired.

- Built by `tools/blender/build_rdwe_greybox.py` on the rented box: it writes `world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plans and the stills. These sheets come from `tools/blender/rdwe_greybox_sheets.py`.
- `python tools/blender/build_rdwe_greybox.py --check .` runs the gates on the committed files: links meet on both sides (or are one way, or loop, or leave the set on purpose), every room is reachable and can get back (no true exit), no colliders overlap, every link, arrival, spot and spawn has clearance and a floor, steps rise at most 0.27 m, corridors are 1.6 m or wider, each room has the spots it needs, every door is different and every exit has its one Link_.
- `CHECKS.txt`: the gates and `node tools/worlddoc.mjs check` on every file.
- `graph.png`: how the rooms connect. For each scene, `<scene>_plan.jpg` (top-down: doors, links, spots and cameras labelled, a scale bar) and `<scene>_still.jpg` (eye height, 1.55 m).

![how the rooms connect](graph.png)

## Rulings (mine, under the owner's "go with your judgment")

1. Ids: `rdwe_<room>` for every scene, so they never clash with the hotel's `dining` (world/dining.json) or the grocery's scenes. The six god rooms keep their own ids (their PRs); the graph reserves `rdwe_nyx` to `rdwe_thanatos` between the trampoline park and the grocery.
2. Count: 7 remakes + 2 set pieces + 34 new rooms + 6 god rooms = 49 rooms, the "about 50" of docs/WORLD.md. Section 7's "about 43 new" is the 2 + 34 + 6 + 1 (the hide-and-seek map counted with its wings).
3. The story stays the spine: dining > hallway > teal > teal2 > flooded > trampoline > (the god rooms) > grocery, with each room's present exit kept. Sleeping, the arch, the grate and the red glow are one way (they were one-way moments in the clips); the green stairs and the well go both ways. The grocery's EXIT is the loop back to the dining room, as in the game today.
4. The finale is entered through the grocery's locked entrance doors once every room is done (the doors behind you in the clip). Its only way out, `win`, opens when every camera is off and leads to grocery.main_floor: the manifest's `rdwe.finale>grocery`, the one ending. That is the only exit from the set besides the Secret Operations door; everywhere else, every room can reach every other (gated).
5. New exits on the remakes, for multi-choice: the dining room's pantry; three of the hallway's side doors (the other six never open); the teal room's black doorway; teal2's peeled wallpaper; a frame in the flooded corridor; a padded vent in the trampoline park; the grocery's stockroom. Each remake also has its present exit unchanged.
6. The red door in the flooded corridor still never opens (it is the lure); the vending room's EXIT door and the hallway's and the hall of doors' wrong doors are leaves with `opens: never`.
7. Every door is different: each leaf carries `look` (a form, a finish and a handle; the story doors have their own words) and a width and height from a small set; the gate fails on two leaves with the same look. Exits that are not doors (the couch, the grate, the red glow, the attic hatch) are a Link_ alone.
8. The repeating room's north door (`again`) arrives through its own south door, so you are back in the same room; the stair loop's top door arrives at the foot of its own stairs. Both are links inside one scene (SELF).
9. The door seen from one angle is a lilac door at the end of a 2 m recess on the repeating room's east wall, hidden behind a free-standing baffle; Spot_view_1 marks the one place it shows from. Its link `secret_ops` is the manifest's `rdwe.repeating_room>secret_ops`.
10. The finale's map is 48 m by 44 m: a hall and four wings (offices, a house, a server room, aisles), Spot_computer x4 (one a wing), ten SecCam_ (the exporter now writes cameras), Spot_hide x12, Spot_agent x6 at the vents (the late swarm), Spot_seeker x1, and the server room as Zone_restricted.
11. Psychedelic in greybox means saturated flat colours per room (cream and shag green, teal, orange, tile white, padded orange, loud pinks and acids for the new rooms) and the remakes at 1.2x to 3x their old size, with distorted key objects (the 4.4 m dining table, the 5.6 m sofa). The look itself is the dressing pass.
12. The trampoline park is built once, 30 m by 50 m; the page still wraps you to make it go on forever. The beds are art with a Zone_trigger over them, so the page can bounce you.

## Scenes

| Scene | Phase | Size | Exits (door: where it goes) | Colliders, doors, spots |
|---|---|---|---|---|
| `rdwe_dining` | A | 16 m by 20 m, 4.2 m high (was 5.4 by 6.4 by 2.45); the stairwell climbs 3 m to the dark door | `house`: the forest house's door, and the Overworld gate (the way in); `pantry`: rdwe_long_table; `loop`: arrival only: the grocery's EXIT door comes back here (the loop); `stairs`: rdwe_hallway (the corridor the stairs never reached) | 52 colliders, 4 doors; spots: lamp x1, photo x3 |
| `rdwe_hallway` | A | a corridor 38 m by 3.2 m, 3.4 m high, from a lower landing up 6 steps; the mossy well goes 2 m down at the far end | `dining`: rdwe_dining (back down the green stairs); `door_a`: rdwe_kids_bedroom; `door_c`: rdwe_door_hall; `door_b`: rdwe_upside_room; `well`: rdwe_teal (down the well, into the teal room) | 65 colliders, 10 doors; spots: hum x1 |
| `rdwe_teal` | A | 14 m by 18 m, 4 m high (was 5.2 by 7.4 by 2.5) | `well`: rdwe_hallway (up the well); `void`: rdwe_void_room; `sleep`: rdwe_teal2 (close your eyes on the couch, just for a minute) | 17 colliders, 2 doors; spots: watch x1, window x1 |
| `rdwe_teal2` | A | 8 m by 22 m, 5.5 m high (was 3.8 by 6.6 by 2.6): narrower and wrong | `arch`: rdwe_flooded (through the arch before it finishes); `grid`: rdwe_green_grid; `sleep`: arrival only: you wake beside the sofa (from rdwe_teal's couch) | 15 colliders, 2 doors; spots: grid x3 |
| `rdwe_flooded` | A | a corridor 50 m by 5 m, 4 m high (was 34 by 3.2 by 2.9), water over the floor | `arch`: arrival only: out of rdwe_teal2's arch; `frame`: rdwe_changing_rooms; `grate`: rdwe_trampoline (the grate gives way: the fall down the shaft) | 21 colliders, 3 doors; spots: frame x1, photo x1 |
| `rdwe_trampoline` | A | 30 m by 50 m, 9 m high (one cell was 14 by 28; the page repeats it) | `gods`: the six god rooms (reserved: Nyx, Selene, Hypnos, Morpheus, Oneiros, Thanatos, built elsewhere); `bounce`: rdwe_crossroads; `vent`: arrival only: you fall out of the vent from rdwe_flooded's grate; `glow`: rdwe_grocery (walk to the red glow: the anomaly) | 18 colliders, 2 doors; spots: beacon x1, scuff x1 |
| `rdwe_grocery` | A | 50 m by 50 m, 5 m high (was 38 by 46 by 4): a maze of shelving, 10 by 10 aisles of 5 m | `entrance`: rdwe_finale (the locked entrance doors open once every room is done); `exit`: rdwe_dining (the loop: you are back at the start); `gods`: arrival only (reserved): the last god room comes out here; `stockroom`: rdwe_vending_room; `glow`: arrival only: from rdwe_trampoline's red glow (the locked doors behind you) | 189 colliders, 4 doors; spots: cart x1, tin x3 |

## How the rooms connect

Each line is a room and its exits (`door > where it goes`). Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. A one-way link's far side is an arrival door that does not open back.

- **dining**: stairs > hallway; loop < grocery (arrival); house > the way in
- **hallway**: dining > dining; well > teal
- **teal**: well > hallway; sleep > teal2 (one way)
- **teal2**: sleep < teal (arrival); arch > flooded (one way)
- **flooded**: arch < teal2 (arrival); grate > trampoline (one way)
- **trampoline**: vent < flooded (arrival); glow > grocery (one way); gods > rdwe_nyx, the first god room; the god rooms' own doors decide their order
- **grocery**: glow < trampoline (arrival); exit > dining (one way); gods > rdwe_thanatos, the last god room, comes out here

### Every link

| From | To | Kind | Note |
|---|---|---|---|
| `rdwe_dining.stairs` | `rdwe_hallway.dining` | stairs | the green stairs up to the corridor they never reached |
| `rdwe_hallway.well` | `rdwe_teal.well` | stairs | down the mossy well into the teal room |
| `rdwe_teal.sleep` | `rdwe_teal2.sleep` | one_way | close your eyes on the couch: you wake in the arched room |
| `rdwe_teal2.arch` | `rdwe_flooded.arch` | one_way | through the arch before it finishes; it seals behind you |
| `rdwe_flooded.grate` | `rdwe_trampoline.vent` | one_way | the grate gives way: the fall down the shaft, out of a vent |
| `rdwe_trampoline.glow` | `rdwe_grocery.glow` | one_way | walk to the red glow: the anomaly |
| `rdwe_grocery.exit` | `rdwe_dining.loop` | one_way | the EXIT closes the loop: you are back in the dining room |

Links inside one room, and links that leave the set:

- `rdwe_dining.house` (doors): the way in: the dreamcore house's door in the meadow, and the gate on L4; they arrive here, facing the stairs. Manifest: built: forest.house>rdwe and the Overworld gate DoorLeaf_Gate_RDW (both arrive in room dining)
- `rdwe_trampoline.gods` (doors): rdwe_nyx, the first god room; the god rooms' own doors decide their order. Manifest: reserved: the six god rooms (chapters H to M, built elsewhere)
- `rdwe_grocery.gods` (doors): rdwe_thanatos, the last god room, comes out here. Manifest: reserved: the arrival from the last god room

## Notes for the coordinator

- Nothing is wired: no manifest change, and `games/rdwe/` is untouched. How a Blender room loads in the RDWE engine is still the coordinator's to design (section 7); these files are in the same format as everything else. The greybox GLBs are in `glb/` here, not in world/.
- `world/rdwe_*.json`: 43 layout files. `node tools/worlddoc.mjs check` gives 0 errors on each; the warnings say a scene or a link is new.
- The manifest's `rdwe.finale>grocery` names `from: {room: "grocery"}`; the greybox puts that ending on `rdwe_finale.win`. The grocery's own way on is `rdwe_grocery.entrance` (to the finale) and `exit` (the loop).
- export_scene.py now writes `SecCam_<nn>` empties to `cameras` in world/L1.json's shape (a separate commit); index.html's aimFeed can read them as they are.
- Door leaves carry `exit` (their link's door id), `look`, and either `opens: never` or `arrival_of: <scene>.<door>` (the arrival side of a one-way link, which does not open back). `opens_when` marks the finale's two locked doors.
- The god rooms' doors are reserved: `rdwe_trampoline.gods` (out) and `rdwe_grocery.gods` (in). Their PRs decide their own order.

## Open questions for the owner

1. Which Phase C rooms should be dressed first? My pick for a first five: the hall of doors, the Ames room, the moon in the window, the mirror room and the elevator lobby (one of each kind of trick). See ROOMS.md.
2. The god rooms: should they sit between the trampoline park and the grocery (as the graph reserves), or hang off one room as a wing?
3. The finale is entered from the grocery's entrance once every room is done. Is "every room" right, or a number of rooms (say 20)?
4. Sleeping, the arch, the grate and the red glow are one way. Should any of them go back (for co-op friends who join late)?
5. The repeating room is reached by lift 3 of the elevator lobby or through the melting library. Deep enough, or should it be further in?
6. The hallway keeps six doors that never open. Should some of them open later (as gates for the room mini-games)?

## Not done here

- Dressing, light baking and review renders (step 2), one room at a time, for the rooms the owner picks.
- The page-side tricks (the arch growing, the moving statue, the lap counter, the moon's scale, the cameras going off) are the coordinator's code; the greybox marks where each goes with a Spot_ and its `what`.
- The Blender-side layout check (`tools/blender/check_layout.py`) needs each scene's .blend; the greybox builds into an empty file per scene and keeps no .blend.
