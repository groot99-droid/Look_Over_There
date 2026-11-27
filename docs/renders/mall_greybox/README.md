# Mall greybox (docs/BLENDER_AREAS.md, section 3: the mall)

Plain grey boxes, to scale, for the eighteen mall scenes beyond part 1's `entrance` (the atrium): the three wings, the bookstore and its front desk, the cinema lobby, the four photo scenes, the mirror bathroom, the food court, the construction zone, the service corridor and four sky halls. There are no reference photos, so each scene is built from its written description, and a photo name is only a label. This is for review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.

- Built by `tools/blender/build_mall_greybox.py` (it follows the hotel's and the grocery's greybox builds), which writes `world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come from `tools/blender/mall_greybox_sheets.py`.
- `python tools/blender/build_mall_greybox.py --check .` runs the gates on the exported files: every link meets its other side (the links that leave this set, to entrance and the hidden network, are listed), every scene is reachable from entrance, every step rises at most 0.27 m with one box a step, every corridor, aisle and doorway is at least 1.6 m wide and clear, and the bathroom's GLB has Mirror_1 to Mirror_6 as separate objects with the portal marked.
- `CHECKS.txt`: the gates, `node tools/worlddoc.mjs check` on every file (0 errors; every warning says a scene or link is new to the manifest), `node --test shared/*.test.js`, and the privacy grep.
- `overview.png`: how the scenes join entrance, and the painted-sky loop. For each scene, `<scene>_plan.jpg` (top-down, scale bar, rooms, doors, links, spots and mannequins labelled) and `<scene>_still.jpg` (eye height, 1.55 m).

## Scenes

| Scene | Size | Links (door: where it goes) | Colliders, doors, spots | Mood |
|---|---|---|---|---|
| `wing_books` | 40 m by 14 m, 6 m high: a concourse of shuttered fronts off the atrium | `entrance`: entrance (the atrium); `bookstore`: bookstore; `scene_2909`: scene_2909 (the sky court); `service_corridor`: service_corridor (staff only); `construction`: construction (the site door in the hoarding) | 83 colliders, 7 doors; zones: 0; spots: mannequin x3 | abandoned, mid-build |
| `wing_cinema` | 40 m by 14 m, 6 m high: a concourse of shuttered fronts off the atrium | `entrance`: entrance (the atrium); `mirror_bathroom`: mirror_bathroom (the restrooms); `scene_3012`: scene_3012 (the painted-sky street); `service_corridor`: service_corridor (staff only); `cinema_lobby`: cinema_lobby | 73 colliders, 7 doors; zones: 0; spots: mannequin x3 | abandoned, mid-build |
| `wing_entertainment` | 40 m by 14 m, 6 m high: a concourse of shuttered fronts off the atrium | `entrance`: entrance (the atrium); `scene_2991`: scene_2991 (the soft play and the carousel); `scene_3008`: scene_3008 (the escalator well); `service_corridor`: service_corridor (staff only); `food_court`: food_court | 68 colliders, 7 doors; zones: 0; spots: mannequin x3 | abandoned, mid-build |
| `bookstore` | 20 m by 16 m, 3.6 m high: freestanding bookcases, wall shelves, two window displays | `wing_books`: wing_books (the concourse); `bookstore_desk`: bookstore_desk (the front desk) | 23 colliders, 3 doors; zones: 0; spots: mannequin x4 | abandoned shop |
| `bookstore_desk` | 12 m by 8 m, 3.2 m high: the cash desk, the back counter, the office | `bookstore`: bookstore (the shop floor) | 18 colliders, 2 doors; zones: 0; spots: mannequin x2, puzzle x1 | abandoned shop |
| `cinema_lobby` | 24 m by 16 m, 6 m high: box office, concessions, a balcony at y 3 to screens 3 to 5 | `wing_cinema`: wing_cinema (the concourse) | 33 colliders, 2 doors; zones: 0; spots: mannequin x5 | abandoned, lit by the marquee |
| `scene_2909` | 24 m by 24 m, 8 m high under a painted sky, a court sunk 1 m in the middle | `wing_books`: wing_books (the concourse); `sky_hall_01`: sky_hall_01 (a painted-sky hall) | 41 colliders, 2 doors; zones: 0; spots: mannequin x4 | liminal, painted sky |
| `scene_3012` | 32 m by 12 m, 8 m high: a fake old-town street of house fronts under a painted sky | `wing_cinema`: wing_cinema (the concourse); `sky_hall_01`: sky_hall_01 (back to the sky court); `sky_hall_02`: sky_hall_02 (on to the escalator well) | 46 colliders, 3 doors; zones: 0; spots: mannequin x4 | liminal, painted sky |
| `scene_2991` | 32 m by 14 m: a soft-play court 18 m by 14 m (7 m high, painted sky) open to a carousel hall 14 m by 14 m (9 m high) | `wing_entertainment`: wing_entertainment (the concourse); `sky_hall_04`: sky_hall_04 (back to the construction zone) | 38 colliders, 2 doors; zones: 0; spots: mannequin x4 | liminal, painted sky |
| `scene_3008` | 16 m by 24 m, 9.5 m high under a painted sky: a lower concourse, a gallery at y 4.5, two stopped escalators | `wing_entertainment`: wing_entertainment (the concourse); `sky_hall_02`: sky_hall_02 (back to the painted-sky street); `sky_hall_03`: sky_hall_03 (on to the mirror bathroom) | 62 colliders, 3 doors; zones: 0; spots: mannequin x4 | liminal, painted sky |
| `mirror_bathroom` | 10 m by 8 m, 3 m high: six mirrors over the basins, four stalls | `wing_cinema`: wing_cinema (the concourse); `mirror`: sky_hall_03 (through Mirror_4, once the puzzle is solved) | 22 colliders, 5 doors; zones: 0; spots: mannequin x1, mirror x6, puzzle x1 | a portal and a puzzle |
| `food_court` | 30 m by 24 m, 6 m high: ten shuttered stalls, twenty tables | `wing_entertainment`: wing_entertainment (the concourse); `entrance`: entrance (the atrium's FOOD COURT shopfront); `service_corridor`: service_corridor (the kitchens' door) | 106 colliders, 5 doors; zones: 0; spots: mannequin x5 | abandoned |
| `construction` | 24 m by 18 m, 6.5 m high: a bare shell mid-build, a scaffold deck at y 3, a lift pit | `wing_books`: wing_books (the hoarding at the wing's end); `sky_hall_04`: sky_hall_04 (an unfinished doorway onto a painted sky) | 60 colliders, 2 doors; zones: 1; spots: mannequin x3 | mid-build, nobody here |
| `service_corridor` | a back corridor 46 m by 2 m, 3 m high, and an 10 m spur to the freight lift | `wing_cinema`: wing_cinema (its staff door); `wing_books`: wing_books (its staff door); `wing_entertainment`: wing_entertainment (its staff door); `food_court`: food_court (the kitchens' door); `network`: the hidden network (the freight lift, keycard_tier_1) | 36 colliders, 6 doors; zones: 0; spots: keycard x1, mannequin x2 | back of house, the hidden network |
| `sky_hall_01` | 10 m by 2.4 m, 3.0 m high: the kit's sky hall, an EXIT door at the far end | `entry`: scene_2909 (the sky court's north door); `exit`: scene_3012 (the painted-sky street, east end) | 10 colliders, 2 doors; zones: 0; spots: none | connector, painted sky |
| `sky_hall_02` | 10 m by 2.4 m, 3.0 m high: the kit's sky hall, an EXIT door at the far end | `entry`: scene_3012 (the painted-sky street, east end); `exit`: scene_3008 (the escalator well's gallery) | 10 colliders, 2 doors; zones: 0; spots: mannequin x1 | connector, painted sky |
| `sky_hall_03` | 10 m by 2.4 m, 3.0 m high: the kit's sky hall, an EXIT door at the far end | `entry`: scene_3008 (the escalator well's gallery, east door); `exit`: mirror_bathroom (out of Mirror_4) | 10 colliders, 2 doors; zones: 0; spots: none | connector, painted sky |
| `sky_hall_04` | 10 m by 2.4 m, 3.0 m high: the kit's sky hall, an EXIT door at the far end | `entry`: construction (the doorway off the scaffold deck); `exit`: scene_2991 (the carousel hall's east door) | 10 colliders, 2 doors; zones: 0; spots: mannequin x1 | connector, painted sky |

## Links

Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. Every pair has both sides built (the gate checks it).

| From | To | Connector | Note |
|---|---|---|---|
| `wing_books.bookstore` | `bookstore.wing_books` | doors | the bookstore's doors on the wing's west side |
| `bookstore.bookstore_desk` | `bookstore_desk.bookstore` | doors | the INFORMATION door in the bookstore's east wall |
| `wing_books.construction` | `construction.wing_books` | doors | the site door in the hoarding at the wing's far (north) end |
| `wing_books.scene_2909` | `scene_2909.wing_books` | doors | an unmarked door between two shutters |
| `wing_cinema.cinema_lobby` | `cinema_lobby.wing_cinema` | doors | the cinema's glass doors at the wing's far (west) end |
| `wing_cinema.mirror_bathroom` | `mirror_bathroom.wing_cinema` | doors | the RESTROOMS bay |
| `wing_cinema.scene_3012` | `scene_3012.wing_cinema` | doors | an unmarked door between two shutters |
| `wing_entertainment.food_court` | `food_court.wing_entertainment` | doors | the food court's glass doors at the wing's far (east) end |
| `wing_entertainment.scene_2991` | `scene_2991.wing_entertainment` | doors | an unmarked door between two shutters |
| `wing_entertainment.scene_3008` | `scene_3008.wing_entertainment` | doors | an unmarked door between two shutters |
| `wing_books.service_corridor` | `service_corridor.wing_books` | service | the wing's STAFF ONLY door |
| `wing_cinema.service_corridor` | `service_corridor.wing_cinema` | service | the wing's STAFF ONLY door |
| `wing_entertainment.service_corridor` | `service_corridor.wing_entertainment` | service | the wing's STAFF ONLY door |
| `food_court.service_corridor` | `service_corridor.food_court` | service | the kitchens' door behind the stalls |
| `scene_2909.sky_hall_01` | `sky_hall_01.entry` | sky_hall | the sky court's north door |
| `sky_hall_01.exit` | `scene_3012.sky_hall_01` | sky_hall | out by the EXIT door onto the painted-sky street |
| `scene_3012.sky_hall_02` | `sky_hall_02.entry` | sky_hall | the street's east end, south door |
| `sky_hall_02.exit` | `scene_3008.sky_hall_02` | sky_hall | out by the EXIT door onto the escalator well's gallery |
| `scene_3008.sky_hall_03` | `sky_hall_03.entry` | sky_hall | the gallery's east door |
| `sky_hall_03.exit` | `mirror_bathroom.mirror` | mirror | out by the EXIT door and through Mirror_4 into the bathroom; back the same way once solved |
| `construction.sky_hall_04` | `sky_hall_04.entry` | sky_hall | the unfinished doorway off the scaffold deck (y 3) |
| `sky_hall_04.exit` | `scene_2991.sky_hall_04` | sky_hall | out by the EXIT door into the carousel hall |

Links that leave this set (the coordinator wires the other side; entrance is part 1's, in shared/city.js, and is not touched here):

- `wing_books.entrance`: entrance's north wall, the 3.2 m gap between the PHONES and FOOD COURT shopfronts behind the fountain (x -1.6 to 1.6): a 2.4 m opening x -1.2 to 1.2, 2.6 m high. entrance's side, for the coordinator: F at (0, 0, -11.3), arrive at (0, 0, -10.6) facing (0, 1)
- `wing_cinema.entrance`: entrance's west wall, the 5.2 m gap between the GIFTS and PHOTO shopfronts (z -3.6 to 1.6): a 2.4 m opening z -2.2 to 0.2, 2.6 m high. entrance's side, for the coordinator: F at (-15.3, 0, -1), arrive at (-14.6, 0, -1) facing (1, 0)
- `wing_entertainment.entrance`: entrance's east wall, the 5.2 m gap between the OPTICIAN and TOYS shopfronts (z -3.6 to 1.6): a 2.4 m opening z -2.2 to 0.2, 2.6 m high. entrance's side, for the coordinator: F at (15.3, 0, -1), arrive at (14.6, 0, -1) facing (-1, 0)
- `food_court.entrance`: entrance's FOOD COURT shopfront (north wall, x 1.6 to 6.4): its shutter goes up on a 2.4 m opening x 2.8 to 5.2, 2.6 m high. entrance's side, for the coordinator: F at (4, 0, -11.3), arrive at (4, 0, -10.6) facing (0, 1)
- `service_corridor.network`: the hidden network: the freight lift at the spur's end (the connector kit's service corridor and freight lift, not built yet); keycard_tier_1 at the reader, Spot_keycard_1. Its other end is for Secret Operations' plan

## The defaults ([DEFAULT] in docs/BLENDER_AREAS.md)

| Scene | Default | Kept or changed |
|---|---|---|
| wing_books, wing_cinema, wing_entertainment | about 40 m by 14 m each; shuttered fronts, scaffolding, dust sheets; off the atrium | Kept: 40 m by 14 m, 6 m high, a skylight strip down the middle. Five 8 m bays a side: a shuttered front with its sign, or a door with the shutter rolled up over it. Two or three scaffold runs each (tube posts, plank decks at 2 m and 4 m; the cinema wing's is a bridge over the concourse at 4 m), dust sheets over benches, kiosks, kiddie rides and claw machines, a hung sheet on one scaffold. A pair of 2.4 m glass doors at the atrium end. books runs north from the atrium, cinema west, entertainment east. |
| food_court | the food court named on the atrium's shopfronts | Built: 30 m by 24 m, 6 m high. Ten stalls (six on the north wall, four on the east), counters with their shutters down; twenty tables with benches. Three doors: the atrium's FOOD COURT shopfront (west), the end of the entertainment wing (south), and the kitchens' door to the service corridor (north-east). |
| construction | a scaffolded zone mid-build | Built: 24 m by 18 m, 6.5 m high, a bare concrete shell: a 6 m column grid, beams overhead, a 3 m by 3 m lift pit 1.2 m deep behind barriers (Zone_hazard), half-built stud walls, plasterboard, a cement mixer and a scissor lift, and a scaffold deck along the north wall at 3 m, up a 12-step site stair, with an unfinished doorway onto sky_hall_04. Entered by the site door in the hoarding across the end of the books wing. |
| service_corridor | a back corridor for the hidden network | Built: 46 m by 2 m, 3 m high, concrete, pipes overhead, a bin bay, a shut fire door; staff doors to the three wings and the food court's kitchens; a 10 m spur to a placeholder freight lift whose gate needs keycard_tier_1 (Spot_keycard_1). The lift is the way into the hidden network (off this set). |
| sky_hall_01 to sky_hall_04 | painted-sky hall connectors, from the kit | Kept: the kit's sky_hall (claude/blender-hotel-kit, world/kit/sky_hall.json) as boxes in its own frame and with its names: 10 m by 2.4 m inside, 3.0 m high, the entry door's opening at the origin, the hall toward -z, DoorLeaf_entry and DoorLeaf_exit (1.04 m by 2.12 m in 1.1 m openings, swing 90), Link_/Arrive_ entry and exit, Marker_Entry and Marker_Exit. The kit piece goes in each sky_hall scene at (0, 0, 0), yaw 0, replacing every box; its GLB and lightmap are the kit's. The host scenes' doors onto a sky hall are the kit's 1.1 m openings with a 1.04 m leaf. |

Choices the table left open:

- Every scene is its own file with its own frame and its floor at y 0. The three wings are built along x with the atrium at the west end and then turned (books 90 degrees, cinema 180, entertainment 0), so each plan's north is the mall's north.
- How the wings meet the atrium. entrance's eight shopfronts (shared/city.js MALL.shops, in mallProps' order: SHOES, PHONES, FOOD COURT, CLOSED FOR RENOVATION on the north wall at x -11, -4, 4, 11; GIFTS and PHOTO on the west wall and OPTICIAN and TOYS on the east wall at z -6 and 4) name no wing, so each wing opens in a gap where there is no shopfront, beside the fronts that suit it: books in the north wall's middle gap (between PHONES and FOOD COURT, behind the fountain), cinema in the west wall's gap between GIFTS and PHOTO, entertainment in the east wall's gap between OPTICIAN and TOYS. All eight shopfronts stay.
- The FOOD COURT shopfront opens into food_court (its shutter goes up), so the food court is reached from the atrium as its sign says, and also from the far end of the entertainment wing. CLOSED FOR RENOVATION stays shut: construction is reached through the hoarding at the end of the books wing.
- Shops off their wings: the bookstore off the books wing (its front desk, bookstore_desk, through an INFORMATION door in its east wall), the cinema lobby at the far end of the cinema wing, the mirror bathroom behind the cinema wing's RESTROOMS bay, the food court at the far end of the entertainment wing.
- The photo scenes are painted-sky spaces (docs/WORLD.md: the other painted-sky spaces are hall connectors). With no photos, each is my guess at an abandoned mall space: scene_2909 a sky court, 24 m square under a painted sky, sunk 1 m in the middle round a bandstand, with plastic trees; scene_3012 a painted-sky street, a fake old town of house fronts with balconies, lamp posts and sheeted cafe tables; scene_2991 (with IMG_3014) a soft-play court and, through a 6 m opening, a carousel hall; scene_3008 (with IMG_3010) an escalator well, a lower concourse and a gallery 4.5 m up joined by two stopped escalators. Each opens off a wing through an unmarked door between two shutters: 2909 off books, 3012 off cinema, 2991 and 3008 off entertainment.
- The sky halls join the odd ones into a loop: sky_hall_01 from the sky court (2909) to the painted-sky street (3012); sky_hall_02 from the street to the escalator well's gallery (3008); sky_hall_03 from the gallery to the mirror bathroom, coming out through the portal mirror; sky_hall_04 from the construction zone's scaffold deck to the carousel hall (2991). So the three wings also join behind the shops.
- The mirror bathroom: six mirrors over the basins, each its own object Mirror_1 to Mirror_6 (art only, in the GLB, with custom properties `mirror`, `portal` and `portal_to`). Mirror_4 is the portal [DEFAULT]: the link `mirror` stands in front of it and pairs with sky_hall_03's EXIT door. The exporter does not write mirrors to the layout file, so each also has a Spot_mirror_<n> in front of it (with `mirror` and `portal`), and Spot_puzzle_1 is the puzzle: which mirror is the way through.
- Mannequins: Spot_mannequin_<n> in 16 scenes, each with `role` (dressing, npc or monster, the three docs/WORLD.md gives) and `what` (how it stands); the mix is my default. The page draws them.
- Spot kinds the table does not name: `puzzle` (the bookstore desk's till drawer, the mirror bathroom), `mirror`, and `keycard` (the freight lift's reader).
- The escalators in scene_3008 are stairs (one box a step, 18 steps of 0.25 m), as the hotel's and the grocery's are. The sky court's steps down are rings of boxes, three steps of 0.25 m on each side.
- Light: one greybox set for the stills. The day set and the emergency set (the mall locks you in at 20:00) come with dressing.

## Open questions for the owner

1. The wings open in the gaps between the atrium's shopfronts (books behind the fountain, cinema between GIFTS and PHOTO, entertainment between OPTICIAN and TOYS), so all eight fronts stay. Or should a wing go through a shopfront instead (the cinema through PHOTO, entertainment through TOYS)?
2. The atrium's FOOD COURT shopfront opens into the food court, which is also at the end of the entertainment wing. Keep both ways in? And should CLOSED FOR RENOVATION open into the construction zone too (now only the books wing's hoarding does)?
3. Scale: each wing is 40 m long off a 32 m by 24 m atrium, bigger inside than the building on the street, as the hotel and the grocery are. Keep it, or shorten the wings?
4. The photo scenes are my guesses (2909 a sunken sky court, 3012 a painted-sky street, 2991 with 3014 a soft play and a carousel, 3008 with 3010 an escalator well). Do they match the photos? If not, a line on what each photo shows is enough to rebuild them.
5. The sky-hall loop runs sky court, street, escalator well, mirror bathroom, with construction to the carousel on its own. Is that the order you want, and should the mirror's way be one way (out of the mirror only)?
6. The mirror puzzle: six mirrors, Mirror_4 the way through. How many mirrors, which one, and what gives it away (a reflection that is wrong, one that is right)?
7. Mannequins: 49 spots, each marked dressing, npc or monster. Too many or too few, and is the mix right?
8. At night the mall locks you in. Should the service corridor's freight lift (the hidden network, keycard_tier_1) be a way out, or locked too?

## Not done here

- `entrance` is untouched: its north, west and east walls (shared/city.js MALL; its test holds world/entrance.json to it) still have no openings, and its FOOD COURT shutter is still down. The coordinator cuts them with the links, at the places listed above.
- The kit's sky hall is not linked in: the sky_hall scenes are its plain-box stand-ins, in its frame and with its names.
- Placeholders: the freight lift is a car behind a gate (the kit's service corridor and freight lift replace it later); the escalators are stairs; the house fronts' doors, the screens' doors and the stalls do not open.
- Light: one greybox set. The day and emergency sets come with dressing, one scene at a time.
- The manifest, `index.html`, `shared/` and the tests are untouched. `node tools/worlddoc.mjs check` warns that each scene and link is new; that is expected until the coordinator adds them.
