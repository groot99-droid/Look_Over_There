# Grocery greybox (docs/BLENDER_AREAS.md, section 2: the grocery, the rest)

Plain grey boxes, to scale, for the four grocery scenes beyond part 1's `main_floor`: `aisles`, `second_floor`, `back_of_house` and `basement`. There are no reference photos, so each scene is built from its written description; IMG_3027 is only a label. This is for review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.

- Built by `tools/blender/build_grocery_greybox.py` (it follows the hotel greybox's build), which writes `world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come from `tools/blender/grocery_greybox_sheets.py`.
- `python tools/blender/build_grocery_greybox.py --check .` runs the gates on the exported files: every link meets its other side (the links that leave this set are listed), every step rises at most 0.27 m, every corridor and aisle is at least 1.6 m wide and clear, and the restricted scenes have cameras.
- `CHECKS.txt`: the gates, `node tools/worlddoc.mjs check` on every file (0 errors; every warning says a scene or link is new to the manifest), `node --test shared/*.test.js`, and the privacy grep.
- `overview.png`: the four scenes round main_floor, to scale, and how they join. For each scene, `<scene>_plan.jpg` (top-down, scale bar, rooms, doors, links, spots and cameras labelled) and `<scene>_still.jpg` (eye height, 1.55 m).

## Scenes

| Scene | Size | Links (door: where it goes) | Colliders, doors, cameras, spots | Mood |
|---|---|---|---|---|
| `aisles` | 48 m by 40 m, 8.5 m high: long gondola aisles, the red-cart clearing, the mezzanine's underside on the west | `main_floor`: main_floor (the opening in its north wall); `stairs_up`: second_floor (stairs); `escalator_up`: second_floor (escalator) | 112 colliders, 2 doors, 0 cameras; zones: 0; spots: camhead x3, cart x11, food x17, monster x3 | open by day, abandoned by night |
| `second_floor` | 30 m by 20 m (20 m east to west, 30 m north to south), 3.2 m high, glazed over the aisles | `stairs_down`: aisles (stairs down); `escalator_down`: aisles (escalator down) | 38 colliders, 2 doors, 0 cameras; zones: 0; spots: camhead x1, cart x1, lookout x1, monster x2 | open by day, abandoned by night |
| `back_of_house` | 30 m by 24 m, 4.5 m high (staff rooms 3 m) | `main_floor`: main_floor (its staff door, east wall); `basement_stairs`: basement (stairs down); `freight_down`: basement (the freight lift); `secret_ops`: secret_ops/service_entry (grocery.backhouse>secret_ops, needs keycard_tier_1) | 65 colliders, 7 doors, 5 cameras; zones: 1; spots: dock x3, food x3, hide x2, keycard x1, locker x4, monitor x1, monster x2 | restricted: staff only |
| `basement` | 30 m by 20 m, 3.7 m high (back_of_house's floor is 4 m above) | `back_of_house`: back_of_house (stairs up); `freight_up`: back_of_house (the freight lift) | 75 colliders, 5 doors, 2 cameras; zones: 1; spots: breaker x1, food x2, hide x2, monster x2 | restricted: cold, humming |

## How it sits round main_floor

All four scenes use `main_floor`'s x and z (shared/city.js: its hall is x -12 to 12, z -9 to 9, walls 0.2 m thick), so the openings meet it exactly. Each scene's floor is at y 0.

- `aisles` lies north of main_floor. Its south wall is main_floor's north wall (z -9.2 to -9.0); its opening is x -1.8 to 1.8, 3 m high, the gap between main_floor's cooler banks (x -9.6 to -2 and 2 to 9.6), under main_floor's camera (x 0, y 3.4).
- `back_of_house` lies east of main_floor. Its west wall is main_floor's east wall (x 12.0 to 12.2); its staff door is main_floor's closed pair (z -6.3 to -4.7, 2.2 m high), now two leaves that open into back_of_house.
- `second_floor` is the mezzanine over aisles' west half (x -24 to -4, z -44.2 to -14.2). In aisles its slab top is at y 5; the stairs (19 steps of 0.263 m) and the escalator (20 of 0.25 m) climb to a landing in front of its glass, x -4 to -0.6, z -24 to -21.2.
- `basement` lies under back_of_house's south 20 m (z -5 to 15); back_of_house's floor is 4 m above it. Its stairwell (15 steps of 0.267 m) stands under back_of_house's stair door, and the freight lift's shaft under back_of_house's (x 37.4 to 41, z 10.2 to 14).

## Links

Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. Every pair has both sides built (the gate checks it).

| From | To | Connector | Note |
|---|---|---|---|
| `aisles.stairs_up` | `second_floor.stairs_down` | stairs | 19 steps of 0.263 m up the mezzanine's front |
| `aisles.escalator_up` | `second_floor.escalator_down` | escalator | an escalator as 20 steps of 0.25 m, beside the stairs |
| `back_of_house.basement_stairs` | `basement.back_of_house` | stairs | the stair door by the office; 15 steps of 0.267 m |
| `back_of_house.freight_down` | `basement.freight_up` | freight_lift | the freight lift, one stop down |

Links that leave this set (the coordinator wires the other side):

- `aisles.main_floor`: main_floor's north wall, the 3.6 m gap between its cooler banks (x -1.8 to 1.8, 3 m high, under its camera). main_floor's side, for the coordinator: F at (0, 0, -8.3), arrive at (0, 0, -7.8) facing (0, 1); its Wall_N (shared/city.js) needs that opening cut
- `back_of_house.main_floor`: main_floor's staff doors on its east wall (z -6.3 to -4.7, 2.2 m). main_floor's side, for the coordinator: F at (11.4, 0, -5.5), arrive at (10.7, 0, -5.5) facing (-1, 0); its Wall_E needs that opening cut
- `back_of_house.secret_ops`: secret_ops/service_entry by the freight lift: the manifest's grocery.backhouse>secret_ops (service_corridor, requires keycard_tier_1); the reader is Spot_keycard_1 by the gate

## The defaults ([DEFAULT] in docs/BLENDER_AREAS.md)

| Scene | Default | Kept or changed |
|---|---|---|
| aisles | 48 m by 40 m; long repeating aisles and the red-cart clearing (IMG_3027) in the middle; an opening from main_floor's north side | Kept: 48 m by 40 m inside, 8.5 m high (the mezzanine stands in its west half). Eleven gondola lines run north to south (1.2 m wide, 2.4 m aisles, red end caps); the clearing is 11.2 m by 10.4 m at the middle, the three gondolas through it broken. The opening is in main_floor's north wall, the 3.6 m gap between its cooler banks, 3 m high, under its camera. |
| second_floor | 30 m by 20 m; a mezzanine with homeware, a closed café and a view down over the aisles; stairs and an escalator from aisles | Kept: 30 m north to south by 20 m east to west, 3.2 m high, over aisles' west half at y 5. The east side is glass over a 1.1 m rail, with the aisles below as art. Homeware in the north half, the café in the south-west (counter shutter down, chairs up on the tables). |
| back_of_house | 30 m by 24 m; racking, a loading dock, a break room, lockers, a manager's office with camera monitors; SecCam; the staff door, a freight lift and a keycard reader | Kept: 30 m by 24 m, 4.5 m high, east of main_floor (its west wall is main_floor's east wall). Four rows of racking, three dock doors (shut), the four staff rooms 3 m high along the south wall, five SecCam_ cameras, a Zone_restricted over all of it. |
| basement | 30 m by 20 m; cold storage, a plant room and pallets; stairs and the freight lift from back_of_house | Kept: 30 m by 20 m, 3.7 m high, under back_of_house's south 20 m (its floor is 4 m below). Two walk-in freezers, the plant room with the breaker board, nine pallet stacks, two SecCam_ cameras, a Zone_restricted. |

Choices the table left open:

- All four scenes use main_floor's x and z, so they fit round it as one building: aisles north, back_of_house east, second_floor over aisles' west half, basement under back_of_house. Each scene's floor is still at y 0.
- The escalator is stairs (one box a step, 0.25 m), as the hotel's escalators are.
- The freight lift serves back_of_house, basement and Secret Operations: in back_of_house its gate has two press-F points, `freight_down` (to the basement) and `secret_ops` (on past the basement, once keycard_tier_1 is swiped at the reader, Spot_keycard_1).
- Camera heads on the shop floors (aisles, second_floor) are `Spot_camhead` (the page draws them, as on main_floor); the restricted scenes have `SecCam_` cameras that go to the file's `cameras` list (a separate exporter commit: SecCam_ empties now export in world/L1.json's shape).
- Spot kinds the table does not name: `food`, `cart`, `camhead`, `monster` (night threats, `when: night`), `hide`, `locker`, `monitor` (the office's camera monitors), `keycard`, `dock` (shut dock doors, a truck later), `breaker` (the store's breakers) and `lookout` (the view down from the mezzanine).
- No `Spot_checkout`: the checkout stays on main_floor (part 1).

## Open questions for the owner

1. Scale: main_floor fills the street's grocery building (24 m by 18 m), but aisles (48 m by 40 m) and back_of_house (30 m by 24 m) behind it are much bigger than that building. Keep it (bigger inside, liminal, as the hotel's atrium), or shrink them?
2. The opening into aisles is the gap between main_floor's coolers, under its camera. main_floor's north wall (shared/city.js) needs that opening cut when the coordinator wires the link. Is that the place, or should it be at one end of the north wall?
3. The staff door is main_floor's existing closed pair on its east wall. Should it open freely by day, or only for staff (a job, or a key)?
4. The freight lift's two press-F points: down to the basement, and on to Secret Operations with keycard_tier_1. Or should the basement need the keycard too, or the stairs be the only way down?
5. Should second_floor's café be enterable behind its counter, or stay shut (shutter down)?
6. The red-cart clearing holds eight red carts in a ring (the page places them). More, fewer, or a different arrangement from the photo?

## Not done here

- `main_floor` is untouched: its north and east walls (shared/city.js, its test holds world/main_floor.json to it) still have no opening; the coordinator cuts them with the links, at the places listed above.
- Placeholders: the freight lift is a car behind a gate (the connector kit's service corridor and freight lift replace it later); the escalator is stairs; the dock doors do not open.
- Light: one greybox set. Part 1's two sets (by day fluorescent and open, by night freezer glow and emergency lights) come with dressing.
- The manifest, `index.html`, `shared/` and the tests are untouched. `node tools/worlddoc.mjs check` warns that each scene and link is new; that is expected until the coordinator adds them.
