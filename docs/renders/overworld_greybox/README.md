# Overworld greybox (docs/BLENDER_AREAS.md, section 4: the Overworld)

Plain grey boxes, to scale, for the Overworld beyond part 1's `parking_lot`: the spawn's table and chairs, the market, the playground, the tree house, the bus station, the road to the forest and the endless hills. There are no reference photos, so each scene is built from its written description. This is for review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.

- Built by `tools/blender/build_overworld_greybox.py` (it follows the hotel's and the mall's greybox builds), which writes `world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plans and the stills. The labels and these sheets come from `tools/blender/overworld_greybox_sheets.py`.
- `python tools/blender/build_overworld_greybox.py --check .` runs the gates on the exported files: every link has its other side (the links that leave this set are listed), every scene is reached from the lot, every step and kerb rises at most 0.27 m with one box a step, every path, aisle and gap is at least 1.6 m wide and clear, each playground piece has its own clear ground, the playground's GLB has every Play_ part as its own node on its pivot, and the hills tile's opposite edges have the same heights.
- `CHECKS.txt`: the gates, `node tools/worlddoc.mjs check` on every file (0 errors; the warnings say a scene or link is new to the manifest, or that an open-air scene is larger than an indoor one should be), `node --test shared/*.test.js`, and the privacy grep.
- `overview.png`: how the scenes join the lot, the street and the forest, and the four skies. For each scene, `<scene>_plan.jpg` (top-down, scale bar, labels, doors, links, spots, clear ground and pivots) and `<scene>_still.jpg` (eye height, 1.55 m).

## Scenes

| Scene | Size | Links (door: where it goes) | Colliders, doors, spots | Mood |
|---|---|---|---|---|
| `table_and_chairs` | a set 3.2 m by 3.2 m in the lot, the table's centre at the lot's (-8, 9.6, 41) | none (Marker_Spawn) | 6 colliders, 0 doors; spots: none | dreamcore, the first thing you see |
| `market` | 64 m by 44 m inside its hedge: five stalls round a square, a buy-back kiosk in the middle, three facades | `lot`: parking_lot (the lot's east edge) | 70 colliders, 0 doors; spots: facade x3, groundskeeper x3, shop x6 | dreamcore, a plastic market square |
| `playground` | 100 m by 76 m inside its hedge: eight pieces of equipment, each on its own clear ground, either side of a path | `lot`: parking_lot (the lot's west edge); `tree_house`: tree_house (the path west) | 91 colliders, 0 doors; spots: facade x2, groundskeeper x3, minigame x8, puzzle x1; moving parts: 10 | dreamcore, too bright |
| `tree_house` | a glade 44 m by 44 m round one big tree; the house 6.5 m by 8 m and a porch on a platform at y 4 | `addon`: the tree house addon (future_addon_treehouse, reserved); `playground`: playground (the path east) | 53 colliders, 2 doors; spots: groundskeeper x1, puzzle x1 | dreamcore, a secret |
| `bus_station` | a set 14 m by 4 m (a 0.15 m platform) with a 3.5 m bus bay, in the lot in place of the shelter | `bus_stop`: Hallam Row (city.street), by bus | 10 colliders, 0 doors; spots: none | dreamcore, a plastic station |
| `road` | 480 m long, an 8 m road between grass verges and hedges, 24 m across; the lot's end at z 0, the forest's at z -480 | `lot`: parking_lot (the gap in its south hedge, by the old signpost); `forest`: forest (dreamcore_forest), arriving at (0, 0, 6) facing north | 56 colliders, 0 doors; spots: facade x2, groundskeeper x4 | dreamcore, a long straight road |
| `endless_hills` | a 200 m by 200 m tile of rolling hills, 4.3 m from the lowest dip to the highest top, that repeats without a seam | `lot`: parking_lot (the stile over its south hedge) | 2502 colliders, 0 doors; spots: facade x1, puzzle x4, toy x12 | dreamcore, eerily beautiful |

## The sets that stay part of the lot

| Set | Attaches to | At (its origin) | Yaw | Its points in the lot's frame |
|---|---|---|---|---|
| `table_and_chairs` | `parking_lot` | (-8, 9.6, 41) | 0 | Marker_Spawn (-8, 9.6, 43.6) |
| `bus_station` | `parking_lot` | (-46, 9.6, 46) | 0 | Link_bus_stop (-46, 9.75, 47.9); Arrive_bus_stop (-46, 9.75, 46.9) |

Each set is its own collection (Art, Layout) in its own file; the coordinator places its GLB and its colliders at that point in the lot (add the point to every position, with no turn), drops the lot's `Ground_lot` stand-in, and removes what index.html draws there today (the table and chairs in overworldProps, the shelter at BUS_LOT.shelter).

## Links

Each pair is one link. Pressing F at one side's `Link_<door>` (or walking through a walk gap) puts you at the other side's `Arrive_<door>`, facing its -Y axis. Every pair has both sides built (the gate checks it).

| From | To | Connector | Note |
|---|---|---|---|
| `playground.tree_house` | `tree_house.playground` | walk | the path west out of the playground, through the gap in its hedge |

Links that leave this set (the coordinator wires the other side; parking_lot, street and forest are part 1's and are not touched here). Lot points are in parking_lot's frame (floor y 9.6):

| Link | Connector | Ids | The other side |
|---|---|---|---|
| `market.lot` | walk | new: overworld.lot>market and overworld.market>lot | parking_lot's east edge, where the asphalt meets the grass (x 62, z 76): F at (61, 9.6, 76), arrive at (59.6, 9.6, 76) facing (-1, 0) |
| `playground.lot` | walk | new: overworld.lot>playground and overworld.playground>lot | parking_lot's west edge, where the asphalt meets the grass (x -62, z 76): F at (-61, 9.6, 76), arrive at (-59.6, 9.6, 76) facing (1, 0) |
| `road.lot` | walk | reused: overworld.lot>forest (the lot's door forest_road, now to the road's start) and forest.road>lot's arrival | parking_lot's south hedge at the old signpost (shared/forest.js FOREST_ROAD_LOT, F at (-30, 95.6)): F at (-30, 9.6, 95.6), arrive at (-30, 9.6, 93) facing (0, -1); a gap is cut in the hedge (x -34 to -26) for the road |
| `road.forest` | walk | reused: overworld.road>forest (planned); forest.road>lot comes back to the road's end | forest (dreamcore_forest, built): you arrive at (0, 0, 6) facing north (0, -1), as today. The forest's signpost back (door road_back, F at (2.6, 0, 8.4)) arrives at the road's forest end, (0, 0, -476) facing (0, 1) |
| `endless_hills.lot` | walk | new: overworld.lot>hills and overworld.hills>lot | parking_lot's south hedge, a stile at x 30 (the old signpost's mirror image): F at (30, 9.6, 95.6), arrive at (30, 9.6, 93) facing (0, -1) |
| `tree_house.addon` | gate | reused: overworld.treehouse>addon (planned) to future_addon_treehouse (reserved) | the tree house addon, not built: the trunk door stays locked; coming back you stand in front of it, facing out |
| `bus_station.bus_stop` | bus | reused: overworld.bus>city and city.bus>overworld (built); only their lot-side points move | street (city, built): the bus arrives at (3.6, 0, 4) facing (0, -1), as today. In parking_lot's frame the station's F is at (-46.0, 9.75, 47.9) and the bus back arrives at (-46.0, 9.75, 46.9) facing (0, -1) (today: F within 3.4 m of (-42.4, 44.2), arrive (-41, 9.6, 43)) |

## The defaults ([DEFAULT] and the table in docs/BLENDER_AREAS.md)

| Scene | The plan says | Kept or built |
|---|---|---|
| table_and_chairs | the spawn: a table and chairs facing the store; it can stay part of the lot; its own collection | Kept as a set that stays part of the lot: its own collection and file (world/table_and_chairs.json) in its own frame, the table's centre at the origin. It attaches at parking_lot's (-8, 9.6, 41), yaw 0, where index.html draws the table today (OW_TABLE), and copies that table: a 0.85 m round top on one leg, four chairs 1.35 m out (pink, mint, yellow, blue), their backs away from the table. Marker_Spawn is 2.6 m south of the table, so lot.L4.front_doors>overworld still arrives at (-8, 9.6, 43.6) facing the store. The page can drop its drawn table for this set's GLB. |
| market | [DEFAULT id] stalls for weapons, gear, food, keycards and cosmetics; Spot_shop per stall | Kept the id. 64 m by 44 m inside a hedge, paved: five stalls 8 m wide (weapons, gear, food on the north side; keycards and cosmetics on the south), each with a back wall and shelves, a counter, a striped awning and a sign, and its Spot_shop_<n> behind the counter facing out (with `stock`). A sixth counter, the buy-back kiosk in the middle (Spot_shop_6, stock buy-back): docs/WORLD.md says the Market is also where lost ammo, consumables and perks are bought back. Four picnic tables, six lamps, three facades on the east side. Reached through a 6 m gap in its west hedge from the lot's east edge. |
| playground | swing, slide, seesaw, merry-go-round, monkey bars, sandbox, spring riders, climbing frame; clear ground round each; moving parts Play_<equipment>_<part> with their pivots | Built: 100 m by 76 m of grass inside a hedge, a path down the middle, four pieces either side, each on a 24 m plot with its clear ground (the dashed rect: the piece and 2 m to 2.5 m round it) on a rubber pad. Moving parts, 10 objects: Play_swing_seat1 and seat2 (pendulum about x, pivot on the top bar at 2.4 m), Play_seesaw_plank (tilt about z, pivot on the fulcrum at 0.6 m), Play_merry_go_round_deck (spin about y), Play_spring_riders_rider1 to rider3 (rock, pivot at the spring's foot), Play_sandbox_digger_seat (spin about y) and Play_sandbox_digger_arm (tilt about x, its `parent` the seat), Play_climbing_frame_wheel (spin about z). Each is one object whose origin is its pivot, with custom properties equipment, part, axis, motion, range_deg and pivot; the moving parts have no collider (the page moves them). The slide and the monkey bars have no moving part. Spot_minigame_<equipment> per piece lists its parts and pays money. |
| tree_house | a puzzle and an entrance to its own addon later (overworld.treehouse>addon) | Built: a 44 m glade in a wild hedge round one big tree. A platform at y 4 round the trunk, up 16 steps of 0.25 m; on it a house 6.5 m by 8 m with the trunk through it, and a porch. The puzzle (Spot_puzzle_1) is a carved board on the house's west wall. The addon's entrance is a small door in the trunk (DoorLeaf_addon, 0.94 m by 1.6 m, closed, `locked`), and its link `addon` is off this set. Reached from the playground's west gap. |
| bus_station | just a ride: a small station in place of the lot's shelter | Kept as a set that stays part of the lot, like the table: its own collection and file, attached at parking_lot's (-46, 9.6, 46), yaw 0, over the shelter index.html draws at (-43.4, 46.4). A 14 m by 4 m platform 0.15 m up, a glass shelter with a bench (its back to the lot), a timetable, a ticket machine, a stop sign and a 3.5 m bus bay on the south side. The bus links keep their ids; only their lot-side points move to the station's Link_bus_stop and Arrive_bus_stop. |
| road | the road to the forest, replacing the signpost walk (overworld.road>forest; you arrive in the forest at (0, 0, 6) facing north) | Built: 480 m [DEFAULT] of straight road, 8 m of asphalt between grass verges and hedges, 24 m across, lamps every 40 m, three benches, two facades. Its frame runs north (-z), as the forest's path does: the lot's end at z 0, the forest's at z -480, behind a wall of pastel trees with a bright gap. You start on it from the lot's old signpost (shared/forest.js FOREST_ROAD_LOT, by the south hedge) and walk 2 minutes to the forest. |
| endless_hills | [DEFAULT] one ground tile of about 200 m by 200 m that repeats without a seam, with Spot_toy for the kickable toys and little puzzles | Kept 200 m by 200 m. The ground is 2500 collision columns 4 m square (Ground_Hills_<i>_<j>) under one smooth surface on a 2 m grid (decor_Hills_Surface, the art); both come from one height function, a sum of cosines that repeats every 200 m and is even about the edges, so the heights and the slopes along opposite edges are the same and the tile repeats without a seam. Heights run 4.3 m from the lowest dip to the highest top; no two neighbouring columns differ by more than 0.26 m, across the seams too. No edge walls: the page repeats the tile and wraps your position. 12 Spot_toy (with `what`, physics kickable), 4 Spot_puzzle, a facade alone on a rise, and the way back: a signpost by the tile's centre, at the same place on every repeat, so it is never more than 140 m away. |
| Also | hedges with Spot_groundskeeper; "more to come" facades that do not open | 11 Spot_groundskeeper on the hedges of the market, the playground, the tree house's glade and the road, each facing its hedge, with `mood` watches or ignores (docs/WORLD.md). 8 facades: three in the market, two in the playground, two along the road, one on the hills; each a front with a fake door, windows and a MORE TO COME sign, solid, and a Spot_facade_<n> in front where the page can swap in a real entrance. |
| Skies | four sky backdrops (clear day, sunset, night, painted), defaults the owner can replace; R3 renders for the dressing step | Listed, not rendered (R3, with dressing): world/backdrops/overworld_clear_day.webp, overworld_sunset.webp, overworld_night.webp and overworld_painted.webp, 4096 by 2048 equirectangular, north in the middle column, shared by every Overworld scene and both sets, and named in the area's manifest entry by the coordinator. The stills here use one plain greybox sky. |

Every [DEFAULT] here, in one list:

- `market` as the scene id (the plan's [DEFAULT id]).
- The hills tile: 200 m by 200 m (the plan's [DEFAULT]), 4 m collision columns, 4.3 m of height.
- The road's length: 480 m, straight.
- The four skies: clear day, sunset, night, painted (the plan's default), and their file names.
- Every size: the market 64 m by 44 m, the playground 100 m by 76 m with 24 m plots, the tree house's glade 44 m and its platform at y 4, the bus station's 14 m platform.
- Where each scene joins the lot (the gaps and the stile), and where the two sets attach.
- The buy-back kiosk as a sixth Spot_shop.
- The two extra moving parts: the sandbox's digger and the climbing frame's wheel.
- The counts: 11 groundskeepers, 8 facades, 12 toys, 6 puzzles.

## Skies (R3, for the dressing step)

| Sky | File | What it is |
|---|---|---|
| Clear day | `world/backdrops/overworld_clear_day.webp` | docs/WORLD.md's 'clear with no clouds': the v0 lot's sky; the default for a first visit. |
| Sunset | `world/backdrops/overworld_sunset.webp` | docs/WORLD.md's 'sunrise and sunset': one warm low sun, rendered for the evening and reused for the morning. |
| Night | `world/backdrops/overworld_night.webp` | docs/WORLD.md's 'a bright starry night'. |
| Painted | `world/backdrops/overworld_painted.webp` | docs/BLENDER_AREAS.md's default; taken as WORLD.md's 'drifting anime clouds', painted, as the sky halls are. |

Each is a 4096 by 2048 equirectangular render, north (game -z) in the middle column, as docs/BLENDER.md's R3 asks. One set of four serves every Overworld scene and both sets; the coordinator names them in the area's manifest entry, and the page switches between them. They are defaults the owner can replace with his own pictures.

Choices the table left open:

- Every scene is its own file with its own frame and its floor at y 0. table_and_chairs and bus_station are sets that stay part of the lot: their frames go into parking_lot's at the points in the attach table, and their `Ground_lot` colliders (no art) stand for the lot's asphalt under them, so each file also passes on its own.
- How the scenes join the lot. Every Overworld scene is open air, so each joins by a walk link (docs/WORLD.md's connectors: walk, as the forest's gap and the signpost walk are): a gap in a hedge, F there (or walking through it), and you arrive 2.6 m inside the other side, facing in. The playground off the lot's west edge, the market off its east edge, the road from the old signpost and the hills from a stile in its south hedge, the tree house off the playground's west end. The lot's sides are listed for the coordinator; the lot is not touched here.
- Link ids. Reused: overworld.bus>city and city.bus>overworld (the station's points), overworld.road>forest (the road's far end), overworld.treehouse>addon (the trunk door), overworld.lot>forest (its door forest_road now leads to the road's start, not the forest) and forest.road>lot (it now arrives at the road's forest end; the coordinator may rename it forest.road>road). New: overworld.lot>market, overworld.market>lot, overworld.lot>playground, overworld.playground>lot, overworld.playground>treehouse, overworld.treehouse>playground, overworld.lot>hills, overworld.hills>lot, overworld.lot>road and overworld.road>lot (or the reused overworld.lot>forest for the first of these).
- Ten minutes. The hub is meant to take about ten minutes to cross end to end. As built, west to east (the tree house, the playground, the lot's asphalt and the market) is about 332 m, 1.4 minutes at the walking pace of 4 m/s; the road is 480 m more (2 minutes) and the hills never end. The lot's own grass already runs to 400 m either way, so the coordinator can stretch the walk by where the lot's gaps go. Open question 1.
- Spot kinds the table does not name: `minigame` (one per playground piece), `puzzle` (the sandbox's buried thing, the tree house's board, the hills' four), `facade`.
- Steps: the tree house's 16, the slide's ladder (6) and chute (7, so it can be walked up), the monkey bars' end steps (3 each) and the climbing frame's (6) are one box a step; the bus platform (0.15 m), the sandbox's boards (0.25 m) and the bases under the merry-go-round and the spring riders are kerbs, one step each.
- The moving parts have no collider; the page moves them and decides what you can stand on. The swing's frame, the seesaw's fulcrum, the merry-go-round's base, the riders' bases and the digger's post are solid.
- Light: one greybox set for the stills, a clear day. The four skies come with dressing (R3).

## Open questions for the owner

1. Ten minutes end to end: as built, the tree house to the market is about 332 m (1.4 minutes' walk), and the road 480 m more. Should the walk be longer: bigger scenes, a longer road, or the lot's gaps further out on its grass?
2. The joins: the playground (and the tree house beyond it) west of the lot, the market east, the road and the hills through the lot's south hedge. Is that the map you want?
3. The table and the bus station stay part of the lot as sets (no scene to load). Should the bus station be a scene of its own instead?
4. The market has a sixth counter, a buy-back kiosk, for lost ammo, consumables and perks (docs/WORLD.md). Keep it, or fold it into the gear stall?
5. The playground: eight pieces in two rows. The slide and the monkey bars have no moving parts; I added a digger in the sandbox and a ship's wheel on the climbing frame so those two have one. Right pieces, and the right mini-games?
6. The endless hills: 4.3 m from dip to top, gentle because each 4 m column may rise at most 0.27 m from the next (2500 columns). Taller hills need smaller columns, so more of them. And the tile is mirror-symmetric, which is how its edges match. Is that all right?
7. The skies: docs/WORLD.md lists clear with no clouds, drifting anime clouds, sunrise and sunset, and a starry night; the default four are clear day, sunset, night and painted. Is 'painted' the anime clouds, and is one render enough for sunrise and sunset?
8. The road: 480 m and straight, running north like the forest's path. Longer, shorter, or with bends?
9. Groundskeepers (11) and facades (8): enough, and in the right places?

## Not done here

- `parking_lot` is untouched (world/parking_lot.json, tools/make_parking_lot.mjs, index.html, shared/city.js, shared/forest.js): its hedge gap for the road, the stile for the hills, its east and west gaps, and the sets' placement are the coordinator's, at the points listed above. The parking-lot backdrop is draft PR #91's.
- The forest is untouched: its signpost back still goes to the lot until the coordinator points forest.road>lot at the road.
- Placeholders: the bus is not modelled (it is a ride); the trunk door stays locked; the facades do not open; the toys are spots, not objects.
- The four skies are listed, not rendered (R3, with dressing). Light: one greybox set.
- The manifest, `index.html`, `shared/` and the tests are untouched. `node tools/worlddoc.mjs check` warns that each scene and link is new; that is expected until the coordinator adds them.
