# The mall's shops you can enter: bookstore, bookstore_desk, cinema_lobby, food_court

`docs/BLENDER_AREAS.md` section 3, step 2 (dress and light), for four of the mall greybox's scenes (`claude/blender-mall-greybox`). The same abandoned, mid-refit mall as part 1's `entrance` (the atrium): its textures are reused, and its two light sets are switched the same way. Built in Blender 5.2.1 by `tools/blender/build_mall_shops.py` on a rented GPU (Cycles, OptiX) and exported as art only.

| Scene | What is in it |
|---|---|
| `bookstore` | A large dusty bookshop: 3.3 m wall shelving on three walls and four double-sided runs (about 6900 books from a generated spine atlas: colours, gilt bands and dashes that read as lettering but spell nothing), category boards, three library ladders hooked on a brass rail, two reading armchairs round a lamp table, a sale table with its dust sheet bunched back (SALE, ALL STOCK MUST GO) and three display tables under sheets, the window displays papered over from inside (CLOSING DOWN), a children's corner (picture-book bins, a low table and stools, a rug, beanbags, bunting), fallen books, a carton, dust |
| `bookstore_desk` | The information desk: an L counter with an old beige CRT terminal and keyboard, a till, order slips on a spike and in a tray, pens, a phone, ORDERS & COLLECTIONS hung over it; the back counter's pigeonholes of slips and the special-order shelves of wrapped parcels and books with slips; a staff noticeboard and the rota; queue posts; a returns trolley under a sheet; the back stock room (packing table with cartons, filing cabinet, steel rack of cartons) behind its STOCK ROOM door |
| `cinema_lobby` | A closed multiplex: patterned carpet (purple pile with confetti), burgundy fabric walls, the box office with its blinds down and a CLOSED card, belt barriers; the concession stand (starred counter, candy cases, popcorn machine, drinks fountain, tills, menu boards) and an upright COLD DRINKS fridge; eight poster cases with made-up films (no real films, no people: MOTH SEASON, COMET MOTEL, LOW TIDE AT FARWAY, THE ORCHARD ENGINE, NINE MILES OF FOG, THE PALE ESCALATOR, SILVER STATIC, DOOR NUMBER FOUR); padded doors to SCREEN 1 and 2 below and 3 and 4 on the balcony, chained shut; the balcony at y 3 with its balustrade and brass rail (NOW SHOWING on its face), the carpeted stair, CONCESSIONS on the balcony's edge |
| `food_court` | Ten shuttered stalls, each with an invented name sign and a menu board (LANTERN NOODLES, ORBIT PIZZA, HARBOUR BURGERS, COMET TACOS, KNOTS, BLUE KIWI, HENHOUSE, TIDE SUSHI, GYRO GARDEN, POLAR SCOOP), its counter in its colour; twenty tables with fixed swivel seats on steel arms; four bins (THANK YOU flaps); the tray return with its rack of trays; the kiddie train under a sheet; a long skylight; drum pendants; trays and cups left on tables, a wet-floor board, a mop bucket |

The made-up names and titles were checked against nothing but memory; if one turns out to be a real brand or film, change its string in `build_mall_shops.py` (`STALLS`, `POSTERS`, `FILMS`) and rerun.

## Files

| File | What it is |
|---|---|
| `world/<scene>.glb` | the art (sizes below), textures as WebP |
| `world/lightmaps/<scene>_0.webp`, `_1.webp` | the day set (`lightmap`, `lightmap_intensity`) |
| `world/lightmaps/<scene>_2.webp`, `_3.webp` | the emergency set, the same UVs (`lightmap_night`, `lightmap_night_intensity`) |
| `world/<scene>.json` | the layout: what `export_scene.py` writes from the `.blend`, the same as the greybox model's file (`--compare`) |
| `blender/scenes/<scene>.blend` | `Art` (unmerged pieces), `Export` (merged by material, lightmap UVs), `Doors`, `Layout` (COL_ boxes and the empties), `Standins`, `Lights_Day`, `Lights_Night`, `Lights_Always` |
| `blender/textures/mall_shops/` | eight CC0 maps (below) |
| `docs/renders/<scene>/1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg` | the review stills, the day set |
| `tools/blender/build_mall_shops.py` | the build; `tools/blender/build_mall_greybox.py` gained the new colliders (see "Layout" below) |

## Light: two sets, switched as `entrance` switches them

- **Day (`lightmap`):** each shop's own fittings, some dead (`Lens_Dead`): lay-in troffers in the bookstore and the desk, a batten in the stock room, ceiling cans and balcony sconces, lit menu boards, poster-case strips and the fridge's light in the cinema, drum pendants plus the sun and the sky through the skylight in the food court. Their glowing parts are `Lamp_Emit`.
- **Night (`lightmap_night`), the mall locked from 20:00:** the emergency fittings alone (twin-spot heads on the walls and round bulkheads on the ceilings, lenses `Emergency_Emit`), and the EXIT signs.
- **The page:** `setLightSet(lk ? "night" : "day")`, `artToggle("Emergency_Emit", lk)` and `artToggle("Lamp_Emit", !lk)`, exactly as for `entrance`. `Sign_Exit` is always on (it is in both sets' light). `Glass_Clear` (the fridge door, the candy cases, the popcorn cabinet, the box office's glass) is transparent and has no lightmap. `Skylight_Glass` (food court) is opaque; its lightmap texels are filled flat (bright by day, a dull glow at night), as `entrance`'s are. `Window_Lit` does not occur.

How a texel is written: the page shows texture x base colour x texel x intensity / pi with no tone mapping. Each texel holds the baked light L through a shoulder, G L / (C + G L), and the intensity is pi C (C = 1.12), so ordinary light shows as G L and the bright patches under lamps roll off instead of clipping. G (the set's exposure) puts the floor's median light at a per-scene target; the emergency set's target is 0.45 of the day's.

## Brightness (`lab_display.py`, as the page shows it: p50 / p90 / p99, area-weighted, the largest materials)

| Material | m2 | Day | Night |
|---|---|---|---|
| **bookstore** | | | |
| Wood_Shelf | 767 | 0.005 / 0.077 / 0.149 | 0.001 / 0.015 / 0.107 |
| Book_Spines | 655 | 0.045 / 0.330 / 0.504 | 0.013 / 0.121 / 0.422 |
| Carpet_Shop | 335 | 0.174 / 0.228 / 0.257 | 0.108 / 0.183 / 0.211 |
| Ceiling_Tile | 335 | 0.255 / 0.355 / 0.920 | 0.104 / 0.164 / 0.196 |
| Shelf_Back | 247 | 0.006 / 0.039 / 0.080 | 0.001 / 0.005 / 0.073 |
| Wall_Paint | 112 | 0.000 / 0.215 / 0.273 | 0.000 / 0.029 / 0.043 |
| Glass_Paper | 38 | 0.199 / 0.229 / 0.354 | 0.029 / 0.089 / 0.149 |
| **bookstore_desk** | | | |
| Wall_Paint | 123 | 0.145 / 0.237 / 0.258 | 0.046 / 0.163 / 0.293 |
| Ceiling_Tile | 104 | 0.253 / 0.330 / 0.912 | 0.160 / 0.294 / 0.479 |
| Carpet_Shop | 96 | 0.155 / 0.219 / 0.253 | 0.088 / 0.220 / 0.273 |
| Wood_Desk | 53 | 0.011 / 0.064 / 0.098 | 0.004 / 0.058 / 0.095 |
| Wall_Lower | 40 | 0.099 / 0.158 / 0.172 | 0.046 / 0.107 / 0.183 |
| Laminate | 22 | 0.101 / 0.589 / 0.651 | 0.041 / 0.453 / 0.565 |
| **cinema_lobby** | | | |
| Carpet_Cinema | 540 | 0.135 / 0.161 / 0.618 | 0.096 / 0.170 / 0.543 |
| Ceiling_Dark | 400 | 0.090 / 0.134 / 0.170 | 0.047 / 0.063 / 0.088 |
| Wall_Fabric | 331 | 0.128 / 0.198 / 0.243 | 0.058 / 0.208 / 0.252 |
| Wall_Paint | 268 | 0.149 / 0.257 / 0.322 | 0.067 / 0.142 / 0.293 |
| Ceiling_Paint (the balcony slab) | 151 | 0.000 / 0.183 / 0.305 | 0.000 / 0.128 / 0.181 |
| **food_court** | | | |
| Ceiling_Paint | 636 | 0.175 / 0.305 / 0.314 | 0.075 / 0.103 / 0.116 |
| Floor_Terrazzo | 548 | 0.173 / 0.279 / 0.416 | 0.128 / 0.228 / 0.352 |
| Wall_Paint | 435 | 0.159 / 0.273 / 0.298 | 0.062 / 0.101 / 0.265 |
| Metal_Steel | 192 | 0.389 / 0.511 / 0.530 | 0.049 / 0.228 / 0.461 |
| Skylight_Glass | 185 | 0.650 / 0.726 / 0.726 | 0.035 / 0.039 / 0.039 |

Every p90 of every material in all four scenes is at or under 0.9 and every p99 under 0.98. Texels at 1 or over: 0.05 % of the bookstore's and 0.03 % of the desk's ceiling tiles (beside the troffers), 0.49 % of the cinema's posters (the strip under each case's lamp) and 0.04 % of its signs; none elsewhere. Walls by day: p50 0.145 (desk), 0.149 and 0.128 (cinema paint and fabric), 0.159 (food court). The bookstore's Wall_Paint p50 is 0 because what is left of it after the faces hidden by the shelving are dropped is mostly the strip behind the papered windows (in their shadow); its seen walls are the shelving and the paper (0.2). The bookstore's shelving and the books in it are dark inside the bays (Wood_Shelf p50 0.005): the light is from overhead troffers; the fronts and tops read (p90 0.08 and 0.33). The cinema's Ceiling_Paint p50 0 is the balcony slab's faces under its carpet.

## Bakes

| Map | Set | Page | Density | Gain G | Samples, GPU time |
|---|---|---|---|---|---|
| bookstore_0 / _2 | day / night | 2048 | 26.9 px/m (the shell, shelving and furniture; ceiling and shelf backs smaller) | 2.17 / 2.65 | 1024 / 2048, 59 s / 78 s |
| bookstore_1 / _3 | day / night | 2048 | 101.9 px/m (the books: one rectangle per shelf row, packed by the build) | 2.17 / 2.65 | 17 s / 30 s |
| bookstore_desk_0 / _2 | day / night | 2048 | 96.4 px/m (the shell) | 2.66 / 5.46 | 49 s / 83 s |
| bookstore_desk_1 / _3 | day / night | 2048 | 105.2 px/m | 2.66 / 5.46 | 47 s / 71 s |
| cinema_lobby_0 / _2 | day / night | 2048 | 44.7 px/m | 14.76 / 12.65 | 55 s / 87 s |
| cinema_lobby_1 / _3 | day / night | 2048 | 47.9 px/m | 14.76 / 12.65 | 36 s / 48 s |
| food_court_0 / _2 | day / night | 2048 | 45.1 px/m | 4.21 / 8.94 | 79 s / 112 s |
| food_court_1 / _3 | day / night | 2048 | 33.4 px/m | 4.21 / 8.94 | 58 s / 102 s |

Diffuse (direct and indirect), 8 px margin, OIDN, fixed 2048 pages. Faces never seen are dropped before the bake: the outer skins, faces flat against a wall, floor or ceiling, faces looking up from over 2.2 m (4.7 m in the cinema, for the balcony) or down from under 0.8 m, the wall behind the bookstore's shelving, the food stalls' insides behind their shutters, the box office's inside.

## Budgets (measured, `glb_inspect.py --budget tris=300000,mb=8`)

| Scene | GLB | Triangles | Draw calls | Lightmaps (WebP) |
|---|---|---|---|---|
| bookstore | 6.97 MB (6.65 MiB) | 66 714 | 25 | 492 + 288 KB day, 369 + 266 KB night |
| bookstore_desk | 1.96 MB | 6 546 | 23 | 83 + 394 KB day, 94 + 326 KB night |
| cinema_lobby | 1.55 MB | 10 106 | 24 | 134 + 283 KB day, 117 + 223 KB night |
| food_court | 2.73 MB | 20 068 | 28 | 108 + 580 KB day, 121 + 534 KB night |

All pass. The bookstore's size is its books' vertices (front, top where it is seen, and a side only where a neighbour is shorter or missing).

## Layout

The layout is the greybox's: `build_mall_shops.py` imports `build_mall_greybox.py` and builds every COL_ box, DoorLeaf_ (each leaf its own mesh, origin at the hinge, with its properties), Link_/Arrive_, Marker_ and Spot_ from its model. `python tools/blender/build_mall_shops.py --compare`: all four `world/<scene>.json` (written by `export_scene.py` from the `.blend`) are the same as the model's.

The dressing asked for solid furniture the greybox did not have, so these colliders were added to `build_mall_greybox.py` (listed in `docs/renders/mall_greybox/README.md`); no collider, door, link, marker, zone, spot or step moved:

- `bookstore`: `Kids_Bins`, `Kids_Table`, `Reading_Chair`, `Reading_Chair_2`, `Reading_Table` (and the `front_aisle` gate rect now ends at z 4.3, with a `desk_door` rect to the INFORMATION door);
- `bookstore_desk`: `Stock_Rack`;
- `cinema_lobby`: `Drinks_Fridge`, `Understair_Cupboard` (the space under the balcony stair was open and the dressing makes it visible);
- `food_court`: `Bin`, `Bin_2`, `Bin_3`, `Bin_4`.

The ladders are stowed upright within 4 cm of the shelves, so they need no collider; the popcorn machine stands on the counter. The fifth balcony door the greybox calls `Screen_5_Door` is dressed as the projection room's (PROJECTION, STAFF ONLY), so the screens are 1 to 4 as the brief asks; its collider and name are unchanged.

## Checks

- **Layout check** (`check_layout.py`'s rules, run by `--stage check` on `Art`, with the links' `at` and `arrive` points added to its CLEAR rule, plus a SPOT rule: no art within 25 cm of a `Spot_mannequin`, from just above where it stands to 1.8 m over it): bookstore 38 of 38, bookstore_desk 25 of 25, cinema_lobby 44 of 44, food_court 123 of 123. The full outputs are in `CHECKS.txt` here.
- **Greybox gates** (`python tools/blender/build_mall_greybox.py --check .`): GATES PASS (22 pairs, 18 of 18 reachable, 72 steps at 0.25 m, 54 corridor rects at least 1.65 m and none blocked, the mirrors).
- **`node tools/worlddoc.mjs check`**: 0 errors on all four (the warnings say each scene and link is new to the manifest).
- **Axes:** a marker cube at each arrival point comes out of the glTF exporter where the game expects it.
- **`node --test shared/*.test.js`**: 297 pass.

## Sources and licences

| Map | Used for | Source | Licence |
|---|---|---|---|
| `terrazzo_tiles` (Poly Haven, Amal Kumar) | the food court's floor and its darker band | https://polyhaven.com/a/terrazzo_tiles | CC0 1.0 |
| `painted_metal_shutter` (Poly Haven) | the stalls' shutters | https://polyhaven.com/a/painted_metal_shutter | CC0 1.0 |
| `plywood` (Poly Haven, Rob Tuytel) | the bookshelves (tinted), the stock room's table, the bins | https://polyhaven.com/a/plywood | CC0 1.0 |
| `concrete_floor_02` (Poly Haven, Rob Tuytel) | the stock room's and the concession's floors | https://polyhaven.com/a/concrete_floor_02 | CC0 1.0 |
| `beige_wall_001` (Poly Haven) | walls and ceilings (tinted) | https://polyhaven.com/a/beige_wall_001 | CC0 1.0 |
| `dark_wood` (Poly Haven) | the desks, the ladders, the tables | https://polyhaven.com/a/dark_wood | CC0 1.0 |
| `rough_linen` (Poly Haven) | dust sheets, the reading chairs, the cinema's fabric walls and padded doors | https://polyhaven.com/a/rough_linen | CC0 1.0 |
| `polystyrene` (Poly Haven), as the laboratory's `ceiling_tile_diff.jpg` | the lay-in ceilings | https://polyhaven.com/a/polystyrene | CC0 1.0 |

The seven `.jpg` maps are copied unchanged from `entrance`'s `blender/textures/entrance/` (part 1, PR #79) and the ceiling tile from `blender/textures/laboratory/`; nothing was downloaded. Everything else is own work, drawn by the build with numpy from fixed seeds (`python tools/blender/build_mall_shops.py --gen <dir>` writes them as PNGs): the two carpets, the wall tiles, the book-spine atlas, the four scenes' sign atlases (signs, menus, the noticeboard, labels), the eight film posters, the door leaves, the brown paper and the whitewash, the wired glass, the dust, the EXIT sign and the colour palette. No Meshy, Higgsfield or purchase.

## Rebuild

From the repo root, Blender 5.2 and Python with numpy and Pillow:

```
blender -b --factory-startup --python tools/blender/build_mall_shops.py -- --scenes bookstore,bookstore_desk,cinema_lobby,food_court --stage all
python tools/blender/build_mall_shops.py --pack <scene>          # WebP lightmaps and textures -> world/
python tools/blender/build_mall_shops.py --compare               # world/<scene>.json against the greybox model
```

The work folder is `work/mall_shops/<scene>/` (not committed). `--stage bake,export,render` reruns from the saved `.blend`; `--gain-day` / `--gain-night` override the exposure. The night still and the plan go to the work folder.

## For the coordinator

1. Add each scene to the manifest with `world/<scene>.glb`, and its links as `world/<scene>.json` has them (the greybox's README lists both sides).
2. Apply the lightmaps with `applyLightmaps` as for `entrance` (both sets on the same UV1), and switch them as `entrance` is switched (see "Light").
3. The page draws the mannequins at the `Spot_mannequin_<n>` places (kept clear) and the puzzle at the desk's till (`Spot_puzzle_1`).
4. Door leaves are separate nodes named `DoorLeaf_<id>`, origin at the hinge.

## Open

- The bookstore's bays are dark inside by day (Wood_Shelf p50 0.005); the books' fronts and the shelves' edges read. More light would mean troffers over the aisles at a lower height or a higher bookstore target (`TARGET` in the build) and a rebake.
- The cinema lobby is dim by design (a closed multiplex); its walls are p50 0.13 to 0.15 by day.
- The review stills are Blender's own lights through AgX at exposure 0, so they are darker than the page will show (the lightmaps carry each scene's gain); the coordinator's in-game look is the first true view.
- The greybox's plans and stills (`docs/renders/mall_greybox/`) predate the new colliders.
