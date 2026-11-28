# parking_lot: the Overworld's edge-of-world backdrops

The R3 backdrops for the Overworld's parking lot (`docs/BLENDER.md`, "R3. Edge-of-world backdrops": "`parking_lot` and the Overworld: the endless hills and the town beyond the hedges"). Two 4096 x 2048 equirect panoramas, a clear day and a night with stars, the moon and a few lit town windows. Built and rendered in Blender 5.2.1 (Cycles on the GPU) by a new, fully procedural scene; the store's models are not used or changed.

| File | What it is |
|---|---|
| `world/backdrops/parking_lot_day.webp` | the day panorama: 4096 x 2048, 189 KB (WebP q95) |
| `world/backdrops/parking_lot_night.webp` | the night panorama: 4096 x 2048, 113 KB (WebP q95) |
| `tools/blender/build_parking_lot_backdrop.py` | the re-runnable build: the hills, the town, the sky, the orientation self-check, the renders, the WebP packing, the owner sheet and these stills |
| `docs/renders/parking_lot/1_day_south.jpg`, `2_night_south.jpg` | flat 75-degree views south out of each panorama, past the back hedge to the town (cut from the panoramas, not separate renders) |

## What the pictures show

- **Where from:** the lot's arrival point, the `Spawn` marker in `world/parking_lot.json` (-8, 9.6, 43.6) by the table, at eye height (y 11.2). The asphalt's own middle (0, 62.9) cannot be used: it is inside one of the city set's towers that stand in the lot (`Site_ITN_City`, x -18 to 9, z 52 to 67, 91 m tall). The page draws the picture round the camera wherever the player is, so the point matters only for parallax, and the hills are hundreds of metres out.
- **Playable area hidden:** the backdrop scene never holds the lot. Its extent is read from `world/parking_lot.json` (no coordinate typed by hand): the asphalt (x -62 to 62, z 27.75 to 98), the hedges (the tall one across the back at z 98 to 99.5, 2.6 m high; the low ones at z 54.5 to 56.5) and the lot model's own grass, which reaches about 356 m from the arrival point. The ground of the backdrop is flat at the lot's floor out to there, then rises.
- **The endless hills:** rolling hills in tiers from about 400 m out, patchwork fields with dark hedgerows between them, copses and some 8,000 trees out to 3 km, about 70 farmhouses with barns, and ridge after ridge to 30 km, hazing blue with distance.
- **The town beyond the hedges:** south past the tall back hedge (compass bearing 188 degrees, so a little west of south), on one long slope that faces the lot so its roofs climb in rows above the hedge: about 3,700 houses with gabled roofs and chimneys on a street grid, taller shops and flats in its middle, a church with a spire, a water tower and a silo.
- **Day:** a clear sky, pale at the horizon to blue overhead, the sun high in the south-west (bearing 215 degrees, 52 degrees up).
- **Night:** a deep navy sky with about 3,000 bright and many faint stars, the moon in the south-east (bearing 150 degrees, 26 degrees up, drawn larger than life with a halo), the hills as dark moonlit shapes, a faint warm glow over the town, and a few lit windows (5 per cent in the town, 18 per cent in the farmhouses) and the town's street lamps.
- **The lower half** of each picture is ground (grass, fields), so wherever the lot's own model leaves a gap the page shows ground, not sky.

## Orientation

The picture's middle column faces north (game -z, Blender +Y) and its right-hand side faces east (game +x, Blender +X); the left and right edges are south. A game point (x, y, z) is Blender (x, -z, y). Before the renders, `orientation_test` renders three glowing markers 400 m out (red east, green north, blue south) and checks their columns on the horizon row. Its output on the final run: `ORIENT columns of the markers on the horizon row: {'red': 192, 'green': 128, 'blue': 0}`, `ORIENT PASS: middle north (-z), right east (+x)`.

## How it was built

```
blender -b --factory-startup --python tools/blender/build_parking_lot_backdrop.py -- --stage survey --work <work>
blender -b --factory-startup --python tools/blender/build_parking_lot_backdrop.py -- --stage backdrops --work <work> --bd-samples 128
python tools/blender/build_parking_lot_backdrop.py --stage pack-backdrops --work <work>
python tools/blender/build_parking_lot_backdrop.py --stage sheet --work <work> --out <png>
python tools/blender/build_parking_lot_backdrop.py --stage previews --work <work>
```

- `survey` (optional) imports `world/L4.glb` and `world/Exterior.glb` read-only, hides `Sky_LOT_Exterior`, and renders what the lot's own model covers from the same point as a transparent panorama. It is used only for the owner sheet's "as the page would draw them" row. Nothing is saved.
- `backdrops` builds the scene (numpy noise for the heights, the woods and the town's slope; Blender shader nodes for the fields, the hedgerows, the haze and the sky), runs the orientation self-check, and renders both panoramas: Cycles, 128 samples adaptive, OIDN denoise, Standard view transform, 8-bit PNG.
- `pack-backdrops` writes each PNG as WebP at the best quality that fits in 1 MB (both fit at q95, the highest it tries).
- The build was run on a rented GPU box from a slim copy of the repo holding only the build script, `world/parking_lot.json`, `world/L4.glb` and `world/Exterior.glb` (the 140 MB `blender/Look_Over_There.blend` was not needed and was not sent).
- **The saved scene is not committed.** `backdrops` also saves `blender/scenes/parking_lot_backdrop.blend` (scrubbed: no custom properties, no stamps, no image paths, no remembered folders), 27 MB even with compression, so it is kept out of the commit, as `docs/BLENDER.md` allows for a file this size. Rebuild it with the `backdrops` stage. It holds nothing that the script does not rebuild the same every run (every random draw is seeded), so the script is the source.
- `Look_Over_There.blend` and every `world/*.glb` are untouched.

## Sources and licences

Everything is procedural and made for this build: the terrain, the trees, the houses, the church, the water tower, the silo, the sky, the sun, the moon and the stars come from the script's own seeded numpy noise and Blender's built-in shader nodes (Voronoi, Noise, gradients). No image, texture, HDRI, scan or model from anywhere else is used, so there is nothing to license beyond the repository's own terms. No Poly Haven or ambientCG asset was needed; no Meshy, Higgsfield or other paid generation was used.

## Wiring (for the coordinator; not done here)

1. **The manifest line.** In `shared/farway.manifest.js`, the Overworld's `parking_lot` scene gains `backdrop: {day, night}`:

   ```js
   {id: "parking_lot", floorY: 9.6, files: ["world/L4.glb", "world/Exterior.glb", "world/parking_lot.json"], presence: true,
    backdrop: {day: "world/backdrops/parking_lot_day.webp", night: "world/backdrops/parking_lot_night.webp"}},
   ```

2. **Tests that assert the lot has no backdrop today**, and must gain `backdrop: {day: "world/backdrops/parking_lot_day.webp", night: "world/backdrops/parking_lot_night.webp"}` in the expected value when the line goes in:
   - `shared/manifest.test.js` line 24, inside `assert.deepEqual(REGISTRY.pageScenes, {...})` ("the registry gives the same floors, scenes, ..."): `parking_lot: {glbs: ["world/L4.glb", "world/Exterior.glb"], floor: 9.6}`;
   - `shared/manifest.test.js` line 121 ("the Overworld's parking lot is on the page but never a floor the server runs"): `assert.deepEqual(REGISTRY.pageScenes.parking_lot, {glbs: ["world/L4.glb", "world/Exterior.glb"], floor: 9.6})`.
   
   `gbi_L4_4` loads the same two models; it is not given a backdrop here.
3. **The lot model's sky box hides the backdrop.** `world/Exterior.glb` holds `Sky_LOT_Exterior` (material `M_U_sky`), a 720 m box round the lot that `applySky` in `index.html` lights to 3.5 for `parking_lot`. The page draws the backdrop first, behind everything, so that box covers it completely. With the backdrop on, the page should hide `Sky_LOT_Exterior` in `parking_lot` (for example, `o.visible = !cfg.backdrop` where `applySky` finds it).
4. **Night never shows yet.** `setBackdrop(sky.night ? "night" : "day")` runs only on the City's clock (`inCity()`); outside the City the page keeps the day picture. The lot shows `parking_lot_day.webp` until the Overworld has a clock of its own that calls `setBackdrop("night")`.
5. **From the arrival point the town is behind a tower.** The city set's tower just south of the table (x -18 to 9, z 52 to 67) covers bearings of about 116 to 230 degrees from the arrival point, so the town (bearing 150 to 226 degrees) shows from the back half of the lot and its west side, not from the table. From the table the backdrop shows over the store to the north and across the open ground to the west. This is the lot model as it is; the backdrop was not bent round it.
6. **What else stands in front of it.** The page also draws everything else in `Exterior.glb` from the lot: the store, the city set's towers in and east of the lot (up to about 100 m tall), the Right Door, Wrong Exit house to the west with its cloud and sun spheres, and the lot's grass out to x and z of plus or minus 400. The backdrop shows above and past all of these. The owner sheet's rows "as the page would draw them" show the two together, from the arrival point.
7. **Under the camera.** A thin ring straight down (the nadir, the picture's bottom few rows) is the backdrop's ground ending under the camera; the lot's floor always covers it.
# parking_lot: the lot made an Overworld scene; the house, its balloons and its gate gone

The owner, 2026-11-27: "The parking lot was supposed to be part of the overworld and that house with balloons was supposed to go since it's
been replaced." The lot in front of the store is now its own Overworld scene, built Blender-first like the market, the playground and the
road, with its own GLB, and dressed in their look. The Right Door, Wrong Exit house to the west (its old entrance; the meadow's house door,
`forest.house>rdwe`, replaced it), its balloons and its gate are gone from every scene the page draws.

| File | What |
|---|---|
| `world/parking_lot.glb` | the lot only (WebP textures, 5.48 MB, 114,712 triangles, 43 materials), merged by material |
| `world/parking_lot.json` | the layout: 186 colliders, 6 links, 2 markers, 2 spots; written by `export_scene.py` from the `.blend`, equal to `build_overworld_greybox.py --preview`'s |
| `world/lightmaps/parking_lot_0.webp`, `_1.webp` | the AO bake (2048 each, linear, `TEXCOORD_1`): the ground and the hedges; everything standing |
| `blender/scenes/parking_lot.blend` | the saved scene (Git LFS): `Art`, `Layout` (the `COL_` boxes and empties), `Export` (merged, with the AO UVs) |
| `blender/textures/overworld_lot/` | asphalt, grass, hedge, paving (made by the build, after the road's and the bus station's), the boards' lettering, and `store_signs.png`: the store's own four sign pictures (its logo, PARKING, STOP, the cart sign), copied out of the old `Exterior.glb` |
| `tools/blender/build_overworld_lot.py` | the build: textures, art, layout check, bake, export, stills, before/after, owner sheet |
| `tools/blender/build_overworld_greybox.py` | the layout model gains `parking_lot()`; the lot's four joins become PAIRS; `--check` gains the lot's gate |
| `tools/split_exterior.py` | the store's outside after the rulings (below); `--city` splices the city without its towers |
| `world/city_skyline.glb` | the Intern city's 26 towers as a skyline on the horizon from the bus stop (4.47 MB, 44,112 triangles, no colliders) |
| `tools/blender/build_city_skyline.py` | moves the towers into the skyline and thins the Intern street's tree; `skyline_towers.json` says where each tower went |
| `1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg`, `4_plan.jpg` | the stills (Cycles, 96 samples, the store of `L4.glb` and the two sets in place, the Overworld's clear-day sky) |
| `before_after_arrival.jpg`, `before_after_west.jpg` | the same view before (L4.glb + the old Exterior.glb, as the page draws the lot today) and after |
| `skyline_bus.jpg`, `skyline_doors.jpg` | the skyline from the bus station's platform and from the store's doors: the Overworld (left) and L4 (right) |
| `bake.json`, `brightness.txt`, `CHECKS.txt` | the bake's report, the brightness table, every gate's output |

## The decisions

**The Exterior split: (b), with the lot shared.** The lot's GLB is drawn by all three scenes that showed the lot: the Overworld's
`parking_lot`, the Original's `L4` (you walk out into the lot there, and its Intern gate is out in it) and Going back in's `gbi_L4_4` (the
view out of the glass doors). So the lot looks the same through the glass, on the walk out and in the Overworld. `world/Exterior.glb` keeps
only what `L4` and `gbi_L4_4` still need from it: the Intern's street and gate, the city round it, its road (`Road_ITN`) and the sky box
(`Sky_LOT_Exterior`, which `applySky` lights). `tools/split_exterior.py` (plain Python, re-runnable) dropped the lot, the house (walls, roof,
trim, floor, both balloon materials, flowers, swing, fence, clouds, sun, the "wrong exit", its furniture, `Road_RDW`), the gate box
(`Gate_RDW_wall`, `Gate_RDW_step`, `DoorLeaf_Gate_RDW`) and the cones west of the city: 61 of its 275 nodes stay, each kept primitive's
buffers and every kept image byte for byte (decoded and compared), 4.24 MB -> 1.60 MB. The scene's extras lost `sl_group` (an add-on's
script list with a user folder) and the sites' `origin` (an owner's name). It also edits `world/L4.json` and `world/gbi_L4_4.json`: the
gate's stairwell (19 boxes) and the house's two props go, the stairwell's holes in the ground and the grass are filled, and the south
hedge is cut where the lot's art cuts it. Their doors and markers are left to the coordinator (the manifest test pins the gate).
Option (a), retiring Exterior, would have taken the Intern's gate out of the Original; that was not part of the ruling.

**Draft PR #132 (the Exterior rebake) is superseded.** It baked the old Exterior with the lot and the house in it; the lot is now this
scene (its own AO bake), and the house is gone. The city and the Intern's street that stay in Exterior are unbaked, as on main; #132's
tools could bake them again on the split file.

**The city's towers: a skyline on the horizon from the bus stop** (the owner, 2026-11-27: "The towers should be on the horizon relative to
the bus stop"; this replaces the first take, which left the far city to the skies). The Intern city set's 26 towers stood round the
Intern's street: five on the lot's asphalt (one 91 m tall between the planter rows), one through the store's east end, the rest out east.
`tools/blender/build_city_skyline.py` takes each tower's own faces (its concrete box and its windows, found as the islands of `City_concrete`
and the three window meshes on its footprint) and stands them, as they are, in a skyline:

- **Which way:** the way the bus goes to Hallam Row. The bus station's bay and shelter open south, and the only town the Overworld shows is
  past the back hedge, bearing 188 degrees from the lot (the skies of #117 and the lot backdrop of #91 paint it there). So the skyline is
  south, a little west, centred on bearing 188 from the bus station, 40 degrees wide: the city behind the town, where the bus goes.
- **How far and how big:** two rows on an arc 312 m and 330 m from the bus station (x -205 to 23, z 314 to 386), the tallest in the middle
  of the back row, each tower scaled to 0.35 (the tallest is 32 m now) with its foot 1.5 m under the lawn. From the lot that reads as the
  real towers at about a kilometre. It cannot go further: `L4` and `gbi_L4_4` still draw the store model's sky box (z up to 390), and the
  same skyline must show from them. Nothing of it stands on the asphalt, the store or a join; no colliders (nobody walks out there).
- **Its own file, `world/city_skyline.glb`, shared:** the coordinator adds it to the lot, `L4` and `gbi_L4_4`. One file serves all three,
  the lot's GLB and bake stay as they are, and the skyline can be moved or swapped on its own. The city's own flat-colour materials, the
  lit windows still emissive; unbaked.
- **Exterior.glb** (`split_exterior.py --city`): `City_concrete` keeps only the city's ground slab, and the three window meshes only the
  street blocks' windows (36,264 -> 5,064, 10,968 -> 2,208, 5,076 -> 1,236 triangles); spliced in uncompressed, every other node unchanged.
  `L4.json` and `gbi_L4_4.json` lose the 26 towers' boxes, and the city set's six invisible enclosure walls (`Site_ITN_City`, 1 m thick and
  80 m high round x 60 to 180, z -10 to 125): they walled in the towers, and the west one (x 60 to 61) ran along the lot's east strip,
  across the market's join at (61, 9.6, 76). None of them bounds the Intern street itself (its own blocks, x 88 to 152, do), so none is
  kept. What stays of the city in those files: the street's blocks and walks, and its ground slab (top at 9.58, under the lot's lawn).

**What changes in the Intern's own street:** its 8 trees (`City_tree_small_02`, one mesh) keep a fifth of their leaf cards, each grown 2.2
times about its middle (42,080 -> 8,527 leaf triangles a tree), which brings `Exterior.glb` from 427,468 to 114,932 triangles, under the
300k budget. Nothing else of the street changes: its blocks, its gate, `Road_ITN` and the sky box are as they were. In `L4` and `gbi_L4_4`
the store's east end (x 17.4 to 26.3, z 4.9 to 27.4), where a tower's box and concrete stood inside the store, is open floor now.

## What is there

The lot keeps part 1's frame (its floor at y 9.6; the store of `world/L4.glb` at its north side, facing it) and its playable layout:

- **The asphalt** (x -62 to 62, z 27.75 to 98) in four rows of bays, a line every 2.7 m from x -54 to 54, as part 1's; the zebra crossing to
  the doors, the store's yellow no-parking lines, a low kerb along its north edge. The road's head runs through the gap in the south hedge.
- **The cars:** part 1's, in their bays, made pastel plastic (plum, mint, periwinkle, coral, silver, teal, cream, pink, yellow) and solid
  (part 1's could be walked through): 62. Gone: the two that stood between the table and the store (the store front is in view from the
  table now), the one in the bus station's place and the covered car there; the other covered car moved 1.2 m off the parking post it stood on.
- **The hedges:** part 1's planter row (z 54.5 to 56.5, on a kerb) with a pastel tree where each of its trees stood and a lamp where each of
  its lamps stood; its back hedge (z 98 to 99.5) with the road's gap (x -34 to -26) and the hills' stile (x 29 to 31).
- **Part 1's street furniture where it stood:** the parking, stop and cart posts with the store's own signs, the LOOK OVER THERE pylon
  (its logo both ways), the benches and bins by the doors, the cycle rack, the cart corral; its carts (decor), its old tyres (flower
  planters now), its cones.
- **The old signpost** at the road's head (FOREST_ROAD_LOT.post, (-30, 96.6)), TO THE FOREST, with its collider where index.html puts one.
- **The joins:** an arch over each edge join (MARKET east, PLAYGROUND west, PARKING LOT on their far faces), a paved way out under each,
  the road's gap, the stile with its THE HILLS board.
- **Round the store:** the paved apron, a bed of lawn each side with pastel trees (solid trunks) and shrubs, flowers along the hedges.
- **Lawns** out to 400 m (part 1's grass), the near 20 m baked, the rest not (open ground); invisible edge walls at 400 m.
- Two `Spot_groundskeeper` on the back hedge.

The table and chairs and the bus station (#121) stay sets of their own, as the greybox has them: nothing of the lot stands in their places
(the gate checks it), and the stills show them there.

### Joins and doors (parking_lot's frame)

| Door | F at | Arrive | Facing | The other side |
|---|---|---|---|---|
| `market` | (61, 9.6, 76) | (59.6, 9.6, 76) | (-1, 0) | `market.lot` (its west gap) |
| `playground` | (-61, 9.6, 76) | (-59.6, 9.6, 76) | (1, 0) | `playground.lot` (its east gap) |
| `forest_road` | (-30, 9.6, 95.6) | (-30, 9.6, 93) | (0, -1) | `road.lot` (the road's lot end) |
| `hills` | (30, 9.6, 95.6) | (30, 9.6, 93) | (0, -1) | `endless_hills.lot` (its signpost) |
| `store_doors` | (0, 9.6, 28.6) | (-8, 9.6, 43.6) (the table: `lot.L4.front_doors>overworld`) | (0, -1) | the store (the options screen) |
| `bus_stop` | (-42.4, 9.6, 44.2) | (-41, 9.6, 43) (`city.bus>overworld`) | (0, -1) | Hallam Row; the bus station set's points replace these when it is placed |

The first four are the greybox README's points, unchanged (its `--check` compares them). Markers: `Spawn_table` (-8, 9.6, 43.6), kind
Spawn (the manifest test's), and `Store_doors` (0, 9.6, 28.5), kind Entrance. The store's 55 colliders are copied from `world/L4.json` and
the doors' block from `tools/make_parking_lot.mjs` (now a stub that points here: it would have rebuilt the old file).

## Light (docs/BLENDER.md R1, AO-only)

As every Overworld scene: the baked materials carry `aomap` (`world/lightmaps/parking_lot_<n>.webp`) and `aomap_intensity` 1.0 on the second
UV set; the page keeps them lit (it does not read `aomap` yet). Cycles AO on the rented GPU, 256 samples, OIDN, 8 px margin; the store
(`L4.glb`) and the two sets are in the scene for the rays, never baked or exported.

| Map | What | AO distance | px/m | AO p10 / p50 / p90 |
|---|---|---|---|---|
| `parking_lot_0` | asphalt, paving, the near lawns, the hedges | 1.5 m | 10.5 | 0.40 / 1.00 / 1.00 |
| `parking_lot_1` | everything standing | 0.8 m | 10.9 | 0.01 / 0.41 / 1.00 |

Not baked: the lamp heads (`Lamp_Emit`), the paint, the far lawn, the cars' glass and lamps, the flowers, the carts (hundreds of thin wires).
Map 1's low p50 is the faces nobody sees (under the cars' bodies, inside the crowns' blobs and the planter kerbs).

## Brightness

As the other Overworld scenes: base colour x AO texel (linear), under a white ambient of 1, before the page's sun; area-weighted, max channel.
The asphalt is the road's (p50 0.11), the grass the road's and the bus station's. Every colour is held at or under 0.85; the store's signs
were dimmed to 0.92 so their whites stay under 1 (0.08 % of their texels reach 1, at the letters' edges). `brightness.txt` has the full table.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Grass | 13,857 | 0.552 | 0.588 | 0.617 |
| Asphalt | 8,985 | 0.107 | 0.117 | 0.129 |
| Paving | 2,642 | 0.651 | 0.738 | 0.776 |
| Hedge | 1,293 | 0.207 | 0.262 | 0.301 |
| the nine car colours | 212 to 382 each | 0.24 to 0.49 | 0.50 to 0.85 | 0.50 to 0.85 |
| Leaf_Pink / Mint / Lilac | 549 to 673 | 0.21 to 0.23 | 0.80 to 0.85 | 0.80 to 0.85 |
| Store_Signs | 40.7 | 0.347 | 0.799 | 0.831 |

## Gates (CHECKS.txt has the full output)

- Layout check on the saved scene, in the lot's floor frame (y - 9.6) as for every Overworld scene: **141 of 141 pass** (126 COVER, STRAY,
  14 CLEAR); the store's 56 colliders are left to `L4.glb`, whose art they are.
- `export_scene.py` writes the same `world/parking_lot.json` as `--preview`.
- `build_overworld_greybox.py --check .`: **GATES PASS**, with the new lot gate: the joins at the README's points, the store's colliders as
  `L4.json` has them, the spawn, no house, gate or city collider and nothing standing on the house's plot, the sets' places clear; and its
  corridors (the aisles, the edge joins, the road's gap either side of the signpost, the stile, the way from the table to the doors).
- `node tools/worlddoc.mjs check`: `parking_lot.json`, `L4.json`, `gbi_L4_4.json` OK, **0 errors** (warnings: the lot is over 60 m, its
  market, playground and hills doors are new to the manifest).
- `glb_inspect --budget tris=300000,mb=8`: `parking_lot.glb` pass (114,712 triangles, 5.48 MB); `city_skyline.glb` pass (44,112, 4.47 MB);
  `Exterior.glb` pass (114,932, 2.06 MB; main's was 1,443,500).
- `node --test shared/*.test.js`: 297 of 297 pass; `node tools/manifest.mjs check`: 0 errors, 0 warnings.
- Privacy grep (user names, absolute paths, session ids, e-mails, the render host) over every committed file of this work, the `.blend`
  decompressed, and the owner sheet: 0 hits. No `sl_group` in either GLB. The stills carry no comment or APP1 segment.

## For the coordinator to wire (not done here: `index.html`, `shared/` and the tests are untouched)

1. `shared/farway.manifest.js`, the Overworld's scene: `{id: "parking_lot", floorY: 9.6, files: ["world/L4.glb", "world/parking_lot.glb",
   "world/city_skyline.glb", "world/parking_lot.json"], presence: true, backdrop: {day: "world/backdrops/overworld_clear_day.webp", ...}}`.
   The backdrop is needed now: the sky box stays in `Exterior.glb`, which the lot no longer loads.
2. `L4` and `gbi_L4_4`: `files: ["world/L4.glb", "world/parking_lot.glb", "world/city_skyline.glb", "world/Exterior.glb", ...]` (the lot,
   the skyline, then the Intern's street and the sky box).
3. Drop the gate `gate("DoorLeaf_Gate_RDW", "rdwe", ...)`, and with it, from `world/L4.json` and `world/gbi_L4_4.json`, the door
   `DoorLeaf_Gate_RDW` and the marker `Entrance_RDW_House_1` (their colliders are gone already). **`shared/manifest.test.js` pins the gate and
   must be updated with it**: the gates loop and `soloOnly` asserts (lines 63 to 69), the door-link count (line 47, 10 -> 9), and the
   `pageScenes` `glbs` lists for L4, parking_lot and gbi_L4_4 (lines 23 to 25 and 121). `tools/gates_test.mjs` and
   `tools/games_party_test.mjs` walk to that gate too. Note: that gate was the coop way into Right Door, Wrong Exit (`soloOnly: false`);
   `forest.house>rdwe` is solo only, so rooms lose their way in unless it is made coop.
4. The lot's links: `overworld.lot>market` / `overworld.market>lot`, `overworld.lot>playground` / `overworld.playground>lot`,
   `overworld.lot>hills` / `overworld.hills>lot` (new), and `overworld.lot>forest` (door `forest_road`, now to the road's start), as the
   greybox README lists them; `store_doors` and `bus_stop` are in the file at today's points.
5. `index.html`: `applySky` finds no sky box in the lot (the backdrop replaces it); drop the drawn table (`overworldProps`), the shelter
   (`busStopLotProps`) when the two sets' GLBs go in at the greybox's ATTACH points, and the drawn signpost in `forestRoadLotProps` (this GLB
   has it, and the file its collider at the same place; keep its F logic).

## Open

- The skyline is forced perspective at 312 to 330 m (the sky box bounds it): from high up it reads as a model. If the sky box ever leaves
  L4, the same file can go out to a kilometre at full size.
- `L4.json` keeps part 1's walk-through cars: the lot's new solids (cars, trees, arches, bins, rack, signpost) are walk-through in the
  Original until the coordinator copies their colliders from `parking_lot.json`, if wanted.
- `tools/blender/overworld_greybox_sheets.py` has not been rerun with the lot in the model.

## Sources and licences

Everything here was made for this scene by the build (numpy noise and drawing; the lettering uses the system's sans-serif bold to draw pixels,
no font file is shipped), except the store's four sign pictures, copied unchanged out of the old `world/Exterior.glb` (the game's own). No
Meshy, no Higgsfield, no downloads, no purchases.

## Rebuild

From the repo root (Blender 5.2, Python with numpy and Pillow; `<work>/ctx` may hold the two sets' GLBs, the clear-day backdrop and the old
`Exterior.glb` as `Exterior_before.glb`, for the stills and the before/after only):

    python tools/split_exterior.py
    blender -b --factory-startup --python tools/blender/build_city_skyline.py -- --source <fa23443's Exterior.glb> --layout <fa23443's L4.json> --work <work>
    cp <work>/city/city_skyline_raw.glb world/city_skyline.glb && python tools/split_exterior.py --city <work>/city
    python tools/blender/build_overworld_lot.py --stage textures
    blender -b --factory-startup --python tools/blender/build_overworld_lot.py -- --stage art,bake,export,render --samples 256 --work <work>
    python tools/blender/pack_scene.py parking_lot --work <work>/parking_lot
    blender -b --factory-startup --python tools/blender/build_overworld_lot.py -- --stage compare --work <work>
    python tools/blender/build_overworld_lot.py --stage sheet --work <work> --out <png>
