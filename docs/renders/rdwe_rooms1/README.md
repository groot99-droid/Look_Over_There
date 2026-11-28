# Right Door, Wrong Exit: rooms 1 to 15, dressed and lit

The first fifteen Phase C rooms (`docs/renders/rdwe_greybox/ROOMS.md`), the house and the halls, dressed and lit in Blender on their greybox layouts (`docs/BLENDER_AREAS.md` section 7, step 2), each baked indoors. Super Liminal, psychedelic: ordinary rooms, built a little too well, in colours a step too far, each with one thing wrong. Rooms 16 to 34 are another job's (its own branch).

| File | What it is |
|---|---|
| `world/<scene>.glb` | the art of the room, art only (budgets below) |
| `world/<scene>.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`: the same as `build_rdwe_greybox.py --preview` writes (checked for every room) |
| `world/lightmaps/<scene>_<n>.webp` | the bake (second UV set, `TEXCOORD_1`): 0 the shell (1536 or 2048), 1 the props and the door leaves (2048), 2 the trick objects (1024, where a room has them) |
| `blender/scenes/<scene>.blend` | the saved scene (Git LFS): `Art` (`Props` and `Arch`, the shell's grey twins for the layout check), `Skin` (the shell as seen), `Doors` (one leaf per door, origin at the hinge, with its layout properties), `Layout` (the `COL_` boxes, zones and empties), `Lights`, `Export` (merged by material, with the lightmap UVs) |
| `tools/blender/build_rdwe_rooms1.py` | the build for all fifteen: the materials, the prop kit, one `dress_<room>()` each, the bake, the export, the stills; it imports the greybox model, so no coordinate of the layout is typed in |
| `tools/blender/build_rdwe_greybox.py` | the fifteen rooms' greybox functions, expanded into full layouts (the first commit; nothing else in the file changed) |
| `docs/renders/<scene>/` | the three review stills (`1_arrival`, `2_wide`, `3_detail`) and `bake.json` (the bake's own report) |
| `docs/renders/rdwe_rooms1/` | this file and `brightness.txt` (every room, every baked material) |

## The greyboxes, expanded

Each Phase C greybox was a shell, its doors and one or two boxes. Each is now a full layout: every piece of furniture is a collider (tagged `f` in the model, so the dressing knows to cover it with a prop), and the spots the trick needs carry a `what`. The links, the door ids, the door looks and the graph are unchanged, and so are the other 28 rooms' layout files (byte for byte); `build_rdwe_greybox.py --check` passes on all 43. Two doors changed size: the tilted hall's far door is 1.8 m high at y 1.5 (the floor climbs to it), with its black backing taken down to the floor; the kitchen's back door is 1.76 m (it was 1.7 m; at 1.76 the lintel sits above head height, which the layout check needs).

## The fifteen rooms

| # | Room | The greybox, expanded (colliders) | Dressed as | The trick's objects |
|---|---|---|---|---|
| 1 | `rdwe_long_table` | the 28 m table in four leaves, each 10 cm wider toward the far end; 14 chairs growing from 0.55 m to 1.3 m toward it; the 3.1 m last chair; two sideboards (37) | swirl wallpaper over a cream dado, green shag, maple and red velvet, a place setting at every chair that grows with it, five brass chandeliers, portraits | the 14 chairs, `Trick_Chair_W_1..7` and `Trick_Chair_E_1..7` (solid; they cover their colliders) |
| 2 | `rdwe_tiny_kitchen` | the east half full size (counters, fridge, table, two chairs); the west half at half scale (knee-high counters, a 1 m fridge, a doll's table and chairs, the 2 m ceiling) (24) | mint tile, a black and white chequer floor (half-size squares in the small half), mint cabinets with marble tops, a red-and-chrome dinette, the same stove and sink at both sizes, two windows | none (the room is static) |
| 3 | `rdwe_birthday_party` | the party table and ten folding chairs, the gift pile, the punch table, an upright piano (26) | pink striped paper, parquet, a pink cloth, the uncut cake with nine candles, plates, party hats and a name card at every place, 14 balloons on strings at the ceiling, pennants and HAPPY BIRTHDAY, fairy lights | none |
| 4 | `rdwe_attic` | knee walls (eaves) along both long walls, open at the stair door; six stacks of photo boxes, a trunk, a dress form, a rocking horse, a leaning mirror (22) | plank walls and floor, a plank roof sloping over the eaves with rafters and purlins, cardboard boxes open on photographs, photographs spilled on the floor, a bare bulb, the gable window, the hatch with its lid up | none |
| 5 | `rdwe_kids_bedroom` | the bed, the toy chest, the desk and its chair, a bookshelf, a nightstand (15) | cloud wallpaper, a lilac carpet, a navy ceiling with 60 glow stars (`Stars_Glow`), the notes with their tally marks under the bed, four posters, toy blocks, a rocket lamp and a bedside lamp, the hatch in the ceiling | none |
| 6 | `rdwe_giant_chair` | the armchair 8.8 m wide and 7 m tall (back, two arms, seat), a stair of 12 giant books with the books stacked under each, the footstool ledge under the high door, the giant lamp's base and pole, the remote, the mug (45) | peach paper with a 0.6 m skirting, rose shag, orange velvet with buttons, the book stair in five cloth colours, a green footstool, a 2.4 m lamp shade, a 4.2 m window with curtains, a giant socket and a giant coin | none (the cushions are climbed, not moved) |
| 7 | `rdwe_upside_room` | the chandelier standing on the floor (13) | the floor is a ceiling (plaster, a ceiling rose, a smoke alarm, the cornice at the floor, lights set in it shining up); the ceiling is a floor (boards, a rug, the skirting at the top); damask walls; pictures hung upside down | the hanging furniture: `decor_Trick_Upside_Table`, `_Chair_1..4`, `_Sofa`, `_Lamp`, `_Shelf`, `_Rug` (passable; you walk under them) |
| 8 | `rdwe_door_hall` | two benches, four console tables between the doors, two plants (53) | plaid paper over a dark dado, the diamond carpet and a red runner with brass edges, lamps on the consoles, eleven pendants, a brass number plate (1 to 12) over every side door | none |
| 9 | `rdwe_stretching_hall` | 19 pairs of fins, 2.4 m apart (50) | white everything; a light strip down the inner edge of every fin, a line of light down the floor and the ceiling, cyan floor dashes every 6 m | none (the page stretches it) |
| 10 | `rdwe_bending_hall` | eight radiators, four corner plants (25) | lilac plaster and a violet core, the same picture on every stretch of wall, a red runner round the lap, sconces | `decor_Trick_Lap_Cover` (a piece of wall over the lap door, for the page to lift on the third lap) and `decor_Trick_Lap_Plaque` (LAP 1) |
| 11 | `rdwe_stair_loop` | the flight filled solid below, a wall along its outer side, the landing rail, a cupboard under the landing, a plant (46) | mint plaster, concrete, timber treads with steel nosings, a black handrail and balusters, the window over the landing, a long pendant, 12 painted on the landing | none |
| 12 | `rdwe_tilted_hall` | six terraces of 0.25 m (filled solid), the walls closing in 0.25 m a side at each, the ceiling a step lower over each; the far door 1.8 m high at y 1.5, its black backing taken down to the floor (36) | peach stripes, the tan carpet, a skirting and a dado on every terrace, one picture each side per terrace and each smaller, a pendant per terrace and each smaller | none |
| 13 | `rdwe_three_doors` | the plinth, two benches, two plants (23) | a white gallery, a marble floor, a coffered ceiling, LEFT, MIDDLE and RIGHT in red, yellow and cyan over the doors with a lamp of each colour, a painted line to each door, the note on the plinth (ONE OF THESE IS RIGHT) | none |
| 14 | `rdwe_painted_door` | two pillars, a bench (15) | pale plaster and a pale chequer floor, a gallery of pictures, the yellow mark on the floor | `decor_Trick_Painted_Door` (the door painted over the end wall and 3 m of the floor, drawn so it is a door from the mark only) and `decor_Trick_Painted_Wall` (the wall over the real door, for the page to take away) |
| 15 | `rdwe_anamorphic_room` | four crates and the tripod at the spot (17) | indigo plaster and an indigo chequer, a camera on the tripod, yellow footprints on the spot | the 18 shards `decor_Trick_Shard_1..18` (`Shard_Glow`, emissive, not baked) and `decor_Trick_Word_Cover` (the wall over the north door) |


## The trick objects

Objects the page may move, turn, hide or rescale for a room's trick are their own objects, named `Trick_<what>` when they are solid (they cover their colliders) and `decor_Trick_<what>` when they are passable, kept whole in the GLB under those names. Their materials are their own copies (`<material>_T`), on their own lightmap page (map 2); maps 0 and 1 (the room) are baked with them hidden, so none of their shadows is baked into the room where they might move. They are baked in their rest pose with the room round them. The shards glow instead (`Shard_Glow`, emissive, not baked).

| Room | Trick objects | For the page |
|---|---|---|
| `rdwe_long_table` | `Trick_Chair_W_1..7`, `Trick_Chair_E_1..7` | the chairs that grow toward the far end (1 is the far end) |
| `rdwe_upside_room` | `decor_Trick_Upside_Table`, `_Chair_1..4`, `_Sofa`, `_Lamp`, `_Shelf`, `_Rug` | the furniture hung from the ceiling (the page may turn it) |
| `rdwe_bending_hall` | `decor_Trick_Lap_Cover`, `decor_Trick_Lap_Plaque` | the piece of wall over the lap door (lift it on the third lap); the plaque that reads LAP 1 |
| `rdwe_painted_door` | `decor_Trick_Painted_Door`, `decor_Trick_Painted_Wall` | the door painted over the end wall and the floor, true only from the mark; the wall over the real door (take both away when the player stands on the mark) |
| `rdwe_anamorphic_room` | `decor_Trick_Shard_1..18`, `decor_Trick_Word_Cover` | the shards (they line up into the north door's outline from `Spot_view_1` only); the wall over the north door |

Not trick objects: the giant chair's book stair and cushions are climbed, not moved, so they are baked with the room; the stretching hall, the stair loop and the tilted hall do their tricks with the player, not the art.

## Doors

Every door leaf is its own mesh, built from its `look` (form, finish and handle, unique across the set: the greybox gate), so no two look alike: panelled, flush, louvred, half-glazed, ledged and braced, round-topped, studded, quilted, mirror-faced, porthole, six-panel and stable doors, in fifteen finishes, with knobs, levers, push plates and ring pulls. The painted door's real leaf is the cream six-panel door its painting shows. The leaves keep their layout properties (`exit`, `look`, `opens`, `shows`), and an architrave round every opening, except the painted door's and the anamorphic room's north door (their covers stand in front).

## Light

Baked indoors on UV1 (`lightmap`), one set: the rooms' light is fixed (none of these tricks switches it). Each room is lit from what is in it: the chandeliers, pendants, sconces, lamps and windows, and soft area lights in the ceilings. `Lamp_Emit` (every lamp, shade and light strip) and `Window_Lit` (the windows) are exported lit, as in the bake, for the page to switch. `Stars_Glow` (the bedroom's glow stars) and `Shard_Glow` (the shards) glow and are not baked; `Void` is the black past every door.

Baked in Cycles on the rented GPU, 384 samples, diffuse direct and indirect, OIDN-denoised, 8 px margin; the shell's faces packed by hand on page 0, the props and leaves smart-packed on page 1, the trick objects on page 2.

## Brightness, as the page shows it

The page draws a baked material unlit, with no tone mapping: texture x base colour x texel x intensity / pi. The bake's light L is written with a shoulder, texel = G L / (C + G L), with `lightmap_intensity` = pi C (C = 1.12), so the page shows about albedo x G L where the light is ordinary and rolls off toward albedo x C near a lamp; with every albedo at 0.85 or less nothing clips. G is set per room from its own bake (1.45 over the median light on the shell, in `bake.json`), so every room reads about equally bright. The raw bake is kept on the box (`--stage encode --gain G` re-writes the maps without baking).

Measured with the brief's `lab_display.py` (area-weighted, max channel) on every room; the full table, every material, is `brightness.txt`. A prop material's low p50 is its hidden faces (the undersides of tables and seats, the faces between stacked books and boxes, the room side of a leaf's back), which a smart-packed page still holds.


| Scene | walls p50 (p90, p99) | floor p50 (p90, p99) | ceiling p50 (p90, p99) | highest p90 / p99 of any material | clipped |
|---|---|---|---|---|---|
| `rdwe_long_table` | 0.49 (0.58, 0.62) `Wall_Cream` | 0.14 (0.29, 0.50) `Floor_Shag` | 0.47 (0.62, 0.85) `Ceil_Plaster` | 0.78 / 0.86 | 0.00% |
| `rdwe_tiny_kitchen` | 0.34 (0.61, 0.74) `Wall_Mint_Tile` | 0.00 (0.65, 0.71) `Floor_Checker` | 0.44 (0.58, 0.67) `Ceil_White` | 0.71 / 0.77 | 0.00% |
| `rdwe_birthday_party` | 0.59 (0.64, 0.68) `Wall_Pink_Stripe` | 0.55 (0.62, 0.67) `Floor_Parquet` | 0.51 (0.56, 0.62) `Ceil_Plaster` | 0.90 / 0.91 | 0.00% |
| `rdwe_attic` | 0.00 (0.51, 0.65) `Wall_Boards` | 0.42 (0.60, 0.74) `Floor_Boards` | 0.24 (0.46, 0.62) `Ceil_Boards` | 0.88 / 0.90 | 0.00% |
| `rdwe_kids_bedroom` | 0.52 (0.64, 0.75) `Wall_Clouds` | 0.49 (0.66, 0.72) `Floor_Carpet_Lilac` | 0.17 (0.20, 0.24) `Ceil_Night` | 0.66 / 0.83 | 0.00% |
| `rdwe_giant_chair` | 0.50 (0.60, 0.80) `Wall_Peach_Paper` | 0.00 (0.36, 0.61) `Floor_Shag_Rose` | 0.51 (0.57, 0.76) `Ceil_Plaster` | 0.65 / 0.80 | 0.00% |
| `rdwe_upside_room` | 0.56 (0.60, 0.64) `Wall_Sun_Damask` | 0.49 (0.54, 0.57) `Floor_Ceiling_Plaster` | 0.43 (0.55, 0.65) `Ceil_Floorboards` | 0.78 / 0.80 | 0.00% |
| `rdwe_door_hall` | 0.27 (0.38, 0.46) `Wall_Plaid` | 0.18 (0.25, 0.29) `Floor_Diamond` | 0.48 (0.59, 0.66) `Ceil_Plaster` | 0.83 / 0.87 | 0.00% |
| `rdwe_stretching_hall` | 0.53 (0.57, 0.58) `Wall_White` | 0.56 (0.60, 0.89) `Floor_White` | 0.52 (0.55, 0.92) `Ceil_White` | 0.61 / 0.92 | 0.00% |
| `rdwe_bending_hall` | 0.41 (0.54, 0.76) `Wall_Lilac` | 0.00 (0.26, 0.29) `Floor_Tan` | 0.40 (0.55, 0.77) `Ceil_Plaster` | 0.68 / 0.77 | 0.00% |
| `rdwe_stair_loop` | 0.51 (0.62, 0.75) `Wall_Mint` | 0.14 (0.16, 0.18) `Floor_Concrete` | 0.50 (0.60, 0.69) `Ceil_White` | 0.69 / 0.85 | 0.00% |
| `rdwe_tilted_hall` | 0.54 (0.61, 0.64) `Wall_Peach_Stripe` | 0.22 (0.27, 0.29) `Floor_Tan` | 0.12 (0.52, 0.71) `Ceil_Prop` | 0.61 / 0.71 | 0.00% |
| `rdwe_three_doors` | 0.53 (0.60, 0.72) `Wall_Gallery` | 0.59 (0.65, 0.67) `Floor_Marble` | 0.50 (0.56, 0.63) `Ceil_White` | 0.89 / 0.92 | 0.00% |
| `rdwe_painted_door` | 0.52 (0.57, 0.58) `Wall_Teal_Cream` | 0.42 (0.58, 0.61) `Floor_Checker_Pale` | 0.49 (0.52, 0.55) `Ceil_White` | 0.76 / 0.78 | 0.00% |
| `rdwe_anamorphic_room` | 0.37 (0.42, 0.46) `Wall_Indigo` | 0.08 (0.38, 0.41) `Floor_Indigo` | 0.14 (0.15, 0.16) `Ceil_Indigo` | 0.82 / 0.83 | 0.00% |

Every main surface is at p90 0.90 or under and p99 0.92 or under; walls read (p50 0.27 to 0.59) except the attic's, whose walls are mostly hidden behind its roof (the plank roof and the gables are what you see; p90 0.51). A floor at p50 0.00 is a floor half under furniture or (the kitchen) a chequer with dark squares. The kids' bedroom's navy ceiling (0.17) is dark on purpose, for the glow stars.

## Budgets (`glb_inspect.py --budget tris=300000,mb=8`: every room passes both)

| Scene | GLB | triangles | draw calls | materials | gain G | px/m (maps) | lightmaps (WebP) | bake |
|---|---|---|---|---|---|---|---|---|
| `rdwe_long_table` | 1.54 MB | 11,738 | 53 | 25 | 3.839 | 62.8 / 51.8 / 48.6 | 80 + 319 + 153 KB | 150 s |
| `rdwe_tiny_kitchen` | 0.62 MB | 5,094 | 27 | 25 | 1.9286 | 111.1 / 83.8 | 52 + 162 KB | 109 s |
| `rdwe_birthday_party` | 1.67 MB | 16,900 | 36 | 35 | 1.7045 | 84.5 / 89.7 | 81 + 319 KB | 236 s |
| `rdwe_attic` | 1.16 MB | 5,980 | 24 | 22 | 6.0378 | 68.8 / 107.8 | 56 + 274 KB | 54 s |
| `rdwe_kids_bedroom` | 0.56 MB | 2,776 | 25 | 24 | 6.3785 | 85.7 / 133.4 | 51 + 194 KB | 114 s |
| `rdwe_giant_chair` | 1.40 MB | 11,890 | 33 | 32 | 1.2793 | 58.6 / 19.5 | 72 + 244 KB | 149 s |
| `rdwe_upside_room` | 0.85 MB | 3,944 | 34 | 23 | 1.1189 | 69.2 / 184.8 / 49.1 | 38 + 158 + 92 KB | 100 s |
| `rdwe_door_hall` | 1.92 MB | 19,202 | 50 | 28 | 6.5251 | 58.2 / 34.9 | 105 + 329 KB | 113 s |
| `rdwe_stretching_hall` | 0.33 MB | 2,032 | 15 | 13 | 1.469 | 60.3 / 327.4 | 96 + 163 KB | 211 s |
| `rdwe_bending_hall` | 0.75 MB | 6,748 | 23 | 22 | 4.7604 | 52.7 / 70.7 / 314.0 | 100 + 418 + 24 KB | 165 s |
| `rdwe_stair_loop` | 1.12 MB | 9,286 | 24 | 23 | 5.3046 | 70.0 / 141.9 | 95 + 310 KB | 187 s |
| `rdwe_tilted_hall` | 0.39 MB | 3,618 | 17 | 17 | 2.8063 | 66.7 / 85.9 | 100 + 180 KB | 136 s |
| `rdwe_three_doors` | 0.71 MB | 5,906 | 30 | 29 | 1.4453 | 68.4 / 103.9 | 50 + 264 KB | 140 s |
| `rdwe_painted_door` | 0.47 MB | 2,970 | 19 | 19 | 3.2716 | 58.2 / 86.8 / 180.7 | 32 + 225 + 77 KB | 49 s |
| `rdwe_anamorphic_room` | 0.53 MB | 2,118 | 35 | 17 | 7.8817 | 71.0 / 119.3 / 409.8 | 54 + 275 + 7 KB | 50 s |

Textures WebP through `tools/webp_glb.py` (geometry asserted unchanged). Draw calls (primitives) 15 to 53.

## Review stills (Cycles, 128 samples adaptive, OIDN, 1920 x 1080 JPEG, AgX, exposure log2(G) - 0.4)

For each room, in `docs/renders/<scene>/`: `1_arrival.jpg` (from where you come in, at eye height), `2_wide.jpg` (the whole room from a high corner) and `3_detail.jpg` (the trick: the far chair, the half-scale end, the cake, the photo boxes, the notes under the bed, the book stair, the hanging table, a wrong door, the fins, the lap door, the foot of the stairs, the terraces, the note, the painted door from beside, the shards from beside the spot). The JPEG comment and APP1 segments are stripped. The build also writes a top-down plan of each room to the work folder (ceiling off), used on the owner's sheets.

## Sources and licences

Textures from Poly Haven (CC0 1.0), the files already in the repo; each is recoloured in the build (its luminance detail times the material's own colour), so one photo serves many materials:

| Texture | Used for | Source | Authors | Licence |
|---|---|---|---|---|
| `blender/textures/apartment/dark_wood_diff_1k.jpg` | the woods (maple, walnut, treads, frames, the wood door leaves) | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `blender/textures/apartment/old_wood_floor_diff_1k.jpg` | the attic's boards, pine, crates | https://polyhaven.com/a/old_wood_floor | Guillaume Monsergent | CC0 1.0 |
| `blender/textures/apartment/beige_wall_001_diff_1k.jpg` | the giant chair's wallpaper | https://polyhaven.com/a/beige_wall_001 | Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `blender/textures/apartment/rough_linen_diff_512.jpg` | velvets, linens, covers, rugs | https://polyhaven.com/a/rough_linen | colormass, Rico Cilliers | CC0 1.0 |
| `blender/textures/galleries/herringbone_parquet_diff_1k.jpg` | the party's parquet | https://polyhaven.com/a/herringbone_parquet | Sergej Majboroda, Jenelle van Heerden | CC0 1.0 |
| `blender/textures/galleries/marble_01_diff_1k.jpg` | marble tops, the plinth, the pillars, the three doors' floor | https://polyhaven.com/a/marble_01 | Rob Tuytel | CC0 1.0 |
| `blender/textures/galleries/plastered_wall_04_diff_1k.jpg` | ceilings and plaster walls | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel | CC0 1.0 |
| `blender/textures/laboratory/wall_paint_diff.jpg` | painted wood, trims, the painted door leaves | https://polyhaven.com/a/white_plaster_02 | Rob Tuytel | CC0 1.0 |
| `blender/textures/laboratory/floor_vinyl_diff.jpg` | the stretching hall's floor | https://polyhaven.com/a/tiled_floor_001 | Dimitrios Savva, Rob Tuytel | CC0 1.0 |

Generated here (numpy, fixed seeds, own work, packed in the `.blend` and the GLB): the swirl and damask papers, the shags, the plaid and the diamond carpet, the mint tile, the chequers, the pink and peach stripes, the cloud paper, the posters, the photographs, the book spines, cardboard, brushed metal, concrete and the painted door's picture. No Meshy, no Higgsfield, nothing bought.

## Checks

```
python tools/blender/build_rdwe_greybox.py --check .                GATES PASS (43 rooms; 124 door leaves, no two alike)
build_rdwe_rooms1.py --stage all (each room)                         CHECK_LAYOUT exit 0, AXES PASS, all fifteen
export_scene.py (each .blend) == build_rdwe_greybox.py --preview    the same layout, all fifteen
node tools/worlddoc.mjs check world/<scene>.json                     0 errors each (warnings: new scene, new links)
glb_inspect.py --budget tris=300000,mb=8                             pass, all fifteen
node --test shared/*.test.js                                         297 pass, 0 fail
privacy grep (the decompressed .blend, GLB, JSON, maps, stills, scripts)   clean
```

The layout check's CLEAR rule works on the plan, so a link up on a ledge, a landing or a terrace (the giant chair's `high`, the stair loop's `top` and `landing`, the tilted hall's `end`) would read as inside the block it stands on; those four are left out of it and are checked in three dimensions by the greybox's `--check` (clear by 0.28 m, with a floor under them).

## Notes for the coordinator

- Nothing is wired: no manifest change, `games/rdwe/`, `index.html`, `shared/` and the tests untouched.
- The trick objects are listed above, by name, with what each is for. They are separate nodes in the GLB with their own materials and their own map; the room is baked without them.
- `Stars_Glow` and `Shard_Glow` are new emissive materials (not baked, not switched): draw them as they are.
- The greybox sheets in `docs/renders/rdwe_greybox/` (the plans, stills, `CHECKS.txt`, the greybox GLBs and the scene table's collider counts) still show these rooms' first, minimal greyboxes; the dressed stills replace them.

## Open

- The six greybox doors whose rooms are built elsewhere are unchanged; rooms 16 to 34 are another branch's.
- Brightness: ceilings far from their lamps read darker than the walls (p50 0.1 to 0.5); walls are all over 0.15.
