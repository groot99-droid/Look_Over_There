# rdwe_waiting_room: The waiting room: take a number

Right Door, Wrong Exit, Phase C room 24 (the teal wing), dressed and lit (`docs/BLENDER_AREAS.md`, section 7, step 2), round its greybox (`tools/blender/build_rdwe_greybox.py`, `c_waiting_room()`). 14 m by 10 m, 3 m high. The room, from `ROOMS.md`: Psychological puzzle: rows of seats, a ticket machine and a number display; the door opens only when your number comes up, and it counts down when you sit.

An institution's waiting room: mint walls over a darker mint dado, grey vinyl tiles, a tiled ceiling with troffers. Three rows of blue bucket seats on beams face the door under the red NOW SERVING display; a ticket machine with its paper tongue, a water cooler, a plant, a table of old magazines, a closed hatch with a bell, a notice board and a clock that has stopped.

Built in Blender 5.2.1 by `tools/blender/build_rdwe_rooms2.py` (the room's `dress_` function and spec) with the shared kit `tools/blender/rdwe_rooms2_kit.py`, baked on the GPU and graded by `tools/blender/rdwe_rooms2_pack.py`. There are no reference photos: it follows the room's line in `ROOMS.md` and the style of `docs/WORLD.md` (Super Liminal: nearly ordinary, saturated, a little wrong).

| File | What it is |
|---|---|
| `world/rdwe_waiting_room.glb` | the art: 0.54 MB, 3585 triangles, 28 materials, 25 nodes (one mesh per material; the door leaves as their own nodes), 12 WebP textures |
| `world/rdwe_waiting_room.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`: 21 colliders, 2 doors, 2 links, 3 spots; the same as `build_rdwe_greybox.py --preview` writes |
| `world/lightmaps/rdwe_waiting_room_0.webp` | set `main` (`lightmap`): struct page, 2048 px, about 79.7 px/m |
| `world/lightmaps/rdwe_waiting_room_1.webp` | set `main` (`lightmap`): props page, 1024 px, about 64.4 px/m |
| `blender/scenes/rdwe_waiting_room.blend` | the saved scene (Git LFS): `Art` (one object per collider, unmerged), `Doors` (the leaves, origin at the hinge), `Layout` (`COL_` boxes, the empties), `Export` (merged by material, with the lightmap UVs), `Lights_*` (one collection per light set, and `Lights_all`) |
| `docs/renders/rdwe_waiting_room/` | this README and the three review stills |

![arrival](1_arrival.jpg)
![wide](2_wide.jpg)
![detail](3_detail.jpg)

Review stills: Cycles, 96 samples adaptive, OIDN, 1920 x 1080 JPEG, AgX medium high contrast. They are Blender's renders with Blender's lights; the page shows the lightmaps (see Brightness).

## The trick's spots (for the page)

- `Spot_ticket_1` at (5, 2.6), facing (1, 0): take a ticket: your number is the number of rooms left
- `Spot_ticket_2` at (0, -0.75), facing (0, -1): sit: the display counts down while you sit, and stops when you stand
- `Spot_ticket_3` at (3, -3.6), facing (0, -1): the display over the door: NOW SERVING; the door opens on your number

## Doors

- `DoorLeaf_number` (0.86 x 2.04 m): six-panel cream gloss door, no handle. The leaf is built from its look (form, finish, handle), so it is visibly unlike every other door in the set.
- `DoorLeaf_three` (1.12 x 2.1 m): porthole mint paint door, push plate. The leaf is built from its look (form, finish, handle), so it is visibly unlike every other door in the set.

## Light

| Set | Material properties | Maps |
|---|---|---|
| `main` | `lightmap`, `lightmap_intensity` | `rdwe_waiting_room_0`, `rdwe_waiting_room_1` |

Emissive materials (not baked, drawn as they are): `Lamp_Emit`, `Screen_Number`, `Screen_Ticket`. `Lamp_Emit` is every ordinary lamp's glow.

## Sources and licences

| File (`blender/textures/rdwe_rooms2/`) | Source | Licence | Used by |
|---|---|---|---|
| `Metal048A_color_512.jpg` | ambientCG, Metal048A | CC0 | Steel |
| `old_wood_floor_diff_1k.jpg` | Poly Haven, Old Wood Floor | CC0 | Wood_Oak |
| `plastered_wall_04_diff_1k.jpg` | Poly Haven, Plastered Wall 04 | CC0 | Paint_Mint_Dark, Plaster_Mint |

Every other material is a flat colour, or a picture the build generates with numpy (fixed seeds, own work, no licence needed): `Brass`, `Ceiling_Tiles`, `Chrome`, `Door_Cream_Gloss`, `Door_Mint_Paint`, `Frosted`, `Glass_Blue`, `Glass_Door`, `Iron`, `Lamp_Off`, `Paint_Palette`, `Paint_Red`, `Plant_Leaf`, `Plastic_Blue`, `Plastic_White`, `Pot_Clay`, `Screen_Number`, `Screen_Ticket`, `Signs_Wait`, `Trim_Mint`, `Trim_White`, `Vinyl_Grey`.
No Meshy, no Higgsfield, nothing bought.

## Brightness

Graded by `rdwe_rooms2_pack.py`: texel = G L / (C + G L), intensity = pi C (C = 1.15), G set so the shell page's median texel in the reference set is 1.7 (shared G); the page shows texture x base colour x texel x intensity / pi. The tables below are `lab_display.py` on the packed GLB.

```
brightness, set main (`lightmap`): lab_display.py (shown = texel x intensity / pi x base colour)
material                m2           map       k    p50    p90    p99     >=1
Ceiling_Tiles        140.0 rdwe_waiting_room_0  3.6128  0.379  0.439  0.472   0.00%
Plaster_Mint         138.4 rdwe_waiting_room_0  3.6128  0.113  0.200  0.217   0.00%
Vinyl_Grey           133.4 rdwe_waiting_room_0  3.6128  0.165  0.264  0.285   0.00%
Paint_Mint_Dark       50.9 rdwe_waiting_room_0  3.6128  0.119  0.140  0.150   0.00%
Plastic_Blue          34.4 rdwe_waiting_room_1  3.6128  0.553  0.627  0.651   0.00%
Trim_Mint             12.5 rdwe_waiting_room_0  3.6128  0.349  0.386  0.394   0.00%
Door_Cream_Gloss      10.4 rdwe_waiting_room_1  3.6128  0.000  0.637  0.686   0.00%
Wood_Oak              10.4 rdwe_waiting_room_1  3.6128  0.077  0.110  0.177   0.00%
Chrome                 5.9 rdwe_waiting_room_1  3.6128  0.000  0.000  0.000   0.00%
Door_Mint_Paint        5.8 rdwe_waiting_room_1  3.6128  0.002  0.758  0.766   0.00%
Trim_White             5.7 rdwe_waiting_room_1  2.9445  0.855  0.855  0.862   0.00%
Paint_Red              4.7 rdwe_waiting_room_1  3.6128  0.312  0.675  0.715   0.00%
Frosted                3.4 rdwe_waiting_room_1  3.6128  0.772  0.787  0.803   0.00%
Signs_Wait             2.5 rdwe_waiting_room_1  3.6128  0.592  0.650  0.709   0.00%
Iron                   1.9 rdwe_waiting_room_1  3.6128  0.018  0.061  0.091   0.00%
Plastic_White          1.9 rdwe_waiting_room_1  3.6128  0.313  0.770  0.785   0.00%
Lamp_Off               1.5 rdwe_waiting_room_1  3.6128  0.000  0.360  0.380   0.00%
Plant_Leaf             1.0 rdwe_waiting_room_1  3.6128  0.032  0.144  0.173   0.00%
Pot_Clay               1.0 rdwe_waiting_room_1  3.6128  0.207  0.353  0.365   0.00%
Paint_Palette          0.5 rdwe_waiting_room_1  3.6128  0.406  0.771  0.786   0.00%
Glass_Blue             0.4 rdwe_waiting_room_1  3.6128  0.650  0.789  0.812   0.00%
Brass                  0.3 rdwe_waiting_room_1  3.6128  0.000  0.000  0.000   0.00%
Glass_Door             0.2 rdwe_waiting_room_1  3.6128  0.000  0.583  0.583   0.00%
Steel                  0.1 rdwe_waiting_room_1  3.6128  0.000  0.803  0.811   0.00%
```

## Gates

```
## python tools/blender/build_rdwe_greybox.py --check .
GATE links: 54 pairs with both sides built (108 sides, the one-way ones included), 2 that loop on their own room, 5 that leave the set; 115 links in the files, every one accounted for
GATE navigable: 43 of 43 rooms reachable from rdwe_dining; 42 can get back to it (no true exit: the finale's one way out is the ending)
GATE overlaps: 0 interpenetrating collider pairs of 35141 checked (none allowed)
GATE clearances: 344 links, arrivals, spots and spawns clear by 0.28 m with a floor under them; 248 door-front points (0.5 and 1 m in) clear
GATE steps: 56 step boxes in 6 flights, one box a step; the highest rise 0.250 m (at most 0.27 m)
GATE corridors: 14 corridor rects, the narrowest 2.00 m (at least 1.6 m), none blocked
GATE extent: the largest room is 50.4 m across (a store floor, about 52 m, at most)
GATE spots: every room has its trick's spot and the ones it needs; 10 SecCam; agent x6, beacon x1, book x3, buttons x3, cake x1, cart x1, change x3, clock x2, computer x4, dark x3, frame x1, grid x6, hide x12, hum x1, lamp x1, lap x1, locker x3, map x3, monitor x2, moon x2, note x1, notes x1, photo x5, scuff x1, seeker x1, statue x3, switch x4, ticket x3, tin x3, trick x21, tv x3, view x6, watch x1, window x1
GATE doors: 124 door leaves, no two with the same look; 103 exits with one Link_ each, 4 arrival-only, 17 that never open; every exit fixed
GATES PASS

## world/rdwe_waiting_room.json (export_scene.py, from the .blend) against build_rdwe_greybox.py --preview
SAME (to 2.5 mm): 21 colliders, 2 doors, 2 links, 0 zones, 3 spots, 0 markers, 0 cameras

## node tools/worlddoc.mjs check world/rdwe_waiting_room.json
warning: scene rdwe_waiting_room is not in the world manifest yet: a new scene to add
  warning: link number: the manifest has no link from this door yet: a new link to add
  warning: link three: the manifest has no link from this door yet: a new link to add
OK world/rdwe_waiting_room.json: 21 colliders, 2 doors, 0 markers, 2 links, 0 zones, 3 spots, 0 errors, 3 warnings

## tools/blender/check_layout.py (rules COVER, STRAY, CLEAR on the Art collection; run on the box)
layout check: scene rdwe_waiting_room, 49 visible meshes, 21 colliders
PASS  COVER  Beyond_number: 1 mesh(es) cover it (1080 sample points, every one within 5 cm of art)
PASS  COVER  Beyond_three: 1 mesh(es) cover it (1296 sample points, every one within 5 cm of art)
PASS  COVER  Coat_Stand: 2 mesh(es) cover it (475 sample points, every one within 5 cm of art)
PASS  COVER  Counter: 3 mesh(es) cover it (3444 sample points, every one within 5 cm of art)
PASS  COVER  Magazine_Table: 3 mesh(es) cover it (702 sample points, every one within 5 cm of art)
PASS  COVER  Plant: 3 mesh(es) cover it (735 sample points, every one within 5 cm of art)
PASS  COVER  Room_Ceiling: 9 mesh(es) cover it (45675 sample points, every one within 5 cm of art)
PASS  COVER  Room_Floor: 20 mesh(es) cover it (60900 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_E_1: 5 mesh(es) cover it (9393 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_N_1: 5 mesh(es) cover it (9207 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_N_2: 4 mesh(es) cover it (330 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_N_3: 5 mesh(es) cover it (3627 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_S_1: 6 mesh(es) cover it (13485 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_W_1: 5 mesh(es) cover it (4278 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_W_2: 4 mesh(es) cover it (390 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_W_3: 5 mesh(es) cover it (4278 sample points, every one within 5 cm of art)
PASS  COVER  Seats_1: 3 mesh(es) cover it (2196 sample points, every one within 5 cm of art)
PASS  COVER  Seats_2: 3 mesh(es) cover it (2196 sample points, every one within 5 cm of art)
PASS  COVER  Seats_3: 3 mesh(es) cover it (2196 sample points, every one within 5 cm of art)
PASS  COVER  Ticket_Machine: 2 mesh(es) cover it (1215 sample points, every one within 5 cm of art)
PASS  COVER  Water_Cooler: 3 mesh(es) cover it (350 sample points, every one within 5 cm of art)
PASS  STRAY  22 tall solid mesh(es), each over a collider; 22 decor_* mesh(es) exempt
PASS  CLEAR  links.number.arrive (3.00, -3.10): clear within 0.28 m
PASS  CLEAR  links.number.at (3.00, -4.25): clear within 0.28 m
PASS  CLEAR  links.three.arrive (-5.10, 0.00): clear within 0.28 m
PASS  CLEAR  links.three.at (-6.25, 0.00): clear within 0.28 m
PASS  CLEAR  spots.Spot_ticket_1.at (5.00, 2.60): clear within 0.28 m
PASS  CLEAR  spots.Spot_ticket_2.at (0.00, -0.75): clear within 0.28 m
PASS  CLEAR  spots.Spot_ticket_3.at (3.00, -3.60): clear within 0.28 m
PASS: 29 of 29 checks passed

## glb_inspect world/rdwe_waiting_room.glb --budget tris=300000,mb=8
materials  28: Ceiling_Tiles, Chrome, Door_Cream_Gloss, Brass, Door_Mint_Paint, Glass_Door, Steel, Frosted, Glass_Blue, Iron, Lamp_Emit, Lamp_Off, Paint_Mint_Dark, Paint_Palette, Paint_Red, Plant_Leaf, Plaster_Mint, Plastic_Blue, Plastic_White, Pot_Clay, Screen_Number, Screen_Ticket, Signs_Wait, Trim_Mint, Trim_White, Vinyl_Grey, Void_Black, Wood_Oak
textures   12, images: 256x256, 512x512, 1024x1024, 128x128, 1024x1024, 512x512, 1024x1024
bbox       14.55 x 3.05 x 10.55 (x, y up, z), min [-7.55, -0.05, -5.55]
requires   EXT_texture_webp
pass       tris: 3585 triangles, budget 300000
pass       mb: 0.52 MB, budget 8

## node --test shared/*.test.js
tests 297
pass 297
fail 0

## sizes
world/rdwe_waiting_room.glb  0.54 MB
world/rdwe_waiting_room.json  0.00 MB
blender/scenes/rdwe_waiting_room.blend  0.49 MB
world/lightmaps/rdwe_waiting_room_0.webp  0.08 MB
world/lightmaps/rdwe_waiting_room_1.webp  0.08 MB
docs/renders/rdwe_waiting_room/1_arrival.jpg  0.20 MB
docs/renders/rdwe_waiting_room/2_wide.jpg  0.20 MB
docs/renders/rdwe_waiting_room/3_detail.jpg  0.13 MB

## privacy grep (user names, absolute paths, session ids, e-mail; the .blend decompressed)
privacy grep: 9 files, 0 with hits

```

Nothing is wired: the manifest, `games/rdwe/`, `index.html`, `shared/` and the tests are untouched.
