# rdwe_vending_room: The vending room: the machine is the door

Right Door, Wrong Exit, Phase C room 33 (the institution), dressed and lit (`docs/BLENDER_AREAS.md`, section 7, step 2), round its greybox (`tools/blender/build_rdwe_greybox.py`, `c_vending_room()`). 8 m by 8 m, 3 m high. The room, from `ROOMS.md`: Psychological puzzle: a room of vending machines and a door marked EXIT that never opens; the machine in the middle swings open on the grocery's stockroom.

A small navy room of glowing vending machines (snacks, drinks, coffee, a cold cabinet, one of strange things), a bench and a bin, one tube still lit, and a door marked EXIT under a green sign that never opens. The machine in the middle of the north wall is a door.

Built in Blender 5.2.1 by `tools/blender/build_rdwe_rooms2.py` (the room's `dress_` function and spec) with the shared kit `tools/blender/rdwe_rooms2_kit.py`, baked on the GPU and graded by `tools/blender/rdwe_rooms2_pack.py`. There are no reference photos: it follows the room's line in `ROOMS.md` and the style of `docs/WORLD.md` (Super Liminal: nearly ordinary, saturated, a little wrong).

| File | What it is |
|---|---|
| `world/rdwe_vending_room.glb` | the art: 0.94 MB, 5554 triangles, 25 materials, 24 nodes (one mesh per material; the door leaves as their own nodes), 10 WebP textures |
| `world/rdwe_vending_room.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`: 22 colliders, 3 doors, 2 links, 3 spots; the same as `build_rdwe_greybox.py --preview` writes |
| `world/lightmaps/rdwe_vending_room_0.webp` | set `main` (`lightmap`): struct page, 2048 px, about 124.9 px/m |
| `world/lightmaps/rdwe_vending_room_1.webp` | set `main` (`lightmap`): props page, 1024 px, about 81.4 px/m |
| `blender/scenes/rdwe_vending_room.blend` | the saved scene (Git LFS): `Art` (one object per collider, unmerged), `Doors` (the leaves, origin at the hinge), `Layout` (`COL_` boxes, the empties), `Export` (merged by material, with the lightmap UVs), `Lights_*` (one collection per light set, and `Lights_all`) |
| `docs/renders/rdwe_vending_room/` | this README and the three review stills |

![arrival](1_arrival.jpg)
![wide](2_wide.jpg)
![detail](3_detail.jpg)

Review stills: Cycles, 96 samples adaptive, OIDN, 1920 x 1080 JPEG, AgX medium high contrast. They are Blender's renders with Blender's lights; the page shows the lightmaps (see Brightness).

## The trick's spots (for the page)

- `Spot_trick_1` at (0.6, -1), facing (0, -1): the EXIT door is the only one that is not a door
- `Spot_trick_2` at (-2.6, 0), facing (-1, 0): the EXIT door: lit, marked, and it never opens
- `Spot_trick_3` at (0.6, -2.6), facing (0, -1): the middle machine: press the button with no label and it swings open on the stockroom

## Doors

- `DoorLeaf_lift` (0.86 x 2.4 m): quilted birch door, push plate. The leaf is built from its look (form, finish, handle), so it is visibly unlike every other door in the set.
- `DoorLeaf_machine` (1 x 1.9 m): a vending machine's glass front, lit, that swings open. The leaf is built from its look (form, finish, handle), so it is visibly unlike every other door in the set.
- `DoorLeaf_real` (1.12 x 2.1 m): a plain door marked EXIT that never opens never opens. The leaf is built from its look (form, finish, handle), so it is visibly unlike every other door in the set.

## Light

| Set | Material properties | Maps |
|---|---|---|
| `main` | `lightmap`, `lightmap_intensity` | `rdwe_vending_room_0`, `rdwe_vending_room_1` |

Emissive materials (not baked, drawn as they are): `Exit_Sign`, `Lamp_Emit`, `Sign_Exit`, `Vend_Glow`. `Lamp_Emit` is every ordinary lamp's glow.

## Sources and licences

| File (`blender/textures/rdwe_rooms2/`) | Source | Licence | Used by |
|---|---|---|---|
| `Metal048A_color_512.jpg` | ambientCG, Metal048A | CC0 | Steel |
| `plastered_wall_04_diff_1k.jpg` | Poly Haven, Plastered Wall 04 | CC0 | Paint_Navy |
| `plywood_diff_1k.jpg` | Poly Haven, Plywood | CC0 | Door_Birch |

Every other material is a flat colour, or a picture the build generates with numpy (fixed seeds, own work, no licence needed): `Brass`, `Ceiling_Tiles`, `Chrome`, `Door_Exit_Grey`, `Exit_Sign`, `Iron`, `Lamp_Off`, `Paint_Palette`, `Plastic_Blue`, `Sign_Exit`, `Trim_Steel`, `Trim_White`, `Vend_Acid`, `Vend_Body`, `Vend_Cyan`, `Vend_Glow`, `Vend_Panel`, `Vend_Red`, `Vend_Sun`, `Vinyl_Dark`.
No Meshy, no Higgsfield, nothing bought.

## Brightness

Graded by `rdwe_rooms2_pack.py`: texel = G L / (C + G L), intensity = pi C (C = 1.15), G set so the shell page's median texel in the reference set is 1.5 (shared G); the page shows texture x base colour x texel x intensity / pi. The tables below are `lab_display.py` on the packed GLB.

```
brightness, set main (`lightmap`): lab_display.py (shown = texel x intensity / pi x base colour)
material                m2           map       k    p50    p90    p99     >=1
Paint_Navy            83.3 rdwe_vending_room_0  3.6128  0.083  0.112  0.129   0.00%
Ceiling_Tiles         64.0 rdwe_vending_room_0  3.6128  0.326  0.498  0.525   0.00%
Vinyl_Dark            59.6 rdwe_vending_room_0  3.6128  0.065  0.081  0.091   0.00%
Vend_Cyan             11.2 rdwe_vending_room_1  3.6128  0.337  0.639  0.695   0.00%
Door_Birch            11.1 rdwe_vending_room_1  3.6128  0.000  0.159  0.217   0.00%
Vend_Acid              5.7 rdwe_vending_room_1  3.6128  0.264  0.860  0.909   0.00%
Vend_Red               5.7 rdwe_vending_room_1  3.6128  0.065  0.643  0.763   0.00%
Vend_Sun               5.7 rdwe_vending_room_1  3.6128  0.533  0.789  0.860   0.00%
Vend_Body              5.3 rdwe_vending_room_1  3.6128  0.003  0.082  0.118   0.00%
Trim_Steel             5.3 rdwe_vending_room_0  3.6128  0.405  0.527  0.571   0.00%
Door_Exit_Grey         5.0 rdwe_vending_room_1  3.6128  0.106  0.337  0.361   0.00%
Lamp_Off               4.4 rdwe_vending_room_1  3.6128  0.000  0.632  0.638   0.00%
Trim_White             3.8 rdwe_vending_room_1  2.9987  0.001  0.870  0.870   0.00%
Iron                   2.5 rdwe_vending_room_1  3.6128  0.044  0.066  0.092   0.00%
Vend_Panel             2.4 rdwe_vending_room_1  3.6128  0.266  0.472  0.507   0.00%
Chrome                 1.6 rdwe_vending_room_1  3.6128  0.000  0.000  0.000   0.00%
Steel                  1.4 rdwe_vending_room_1  3.6128  0.179  0.689  0.734   0.00%
Plastic_Blue           0.9 rdwe_vending_room_1  3.6128  0.276  0.394  0.440   0.00%
Paint_Palette          0.1 rdwe_vending_room_1  3.6128  0.418  0.645  0.658   0.00%
Brass                  0.0 rdwe_vending_room_1  3.6128  0.001  0.469  0.516   0.00%
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

## world/rdwe_vending_room.json (export_scene.py, from the .blend) against build_rdwe_greybox.py --preview
SAME (to 2.5 mm): 22 colliders, 3 doors, 2 links, 0 zones, 3 spots, 0 markers, 0 cameras

## node tools/worlddoc.mjs check world/rdwe_vending_room.json
warning: scene rdwe_vending_room is not in the world manifest yet: a new scene to add
  warning: link lift: the manifest has no link from this door yet: a new link to add
  warning: link machine: the manifest has no link from this door yet: a new link to add
OK world/rdwe_vending_room.json: 22 colliders, 3 doors, 0 markers, 2 links, 0 zones, 3 spots, 0 errors, 3 warnings

## tools/blender/check_layout.py (rules COVER, STRAY, CLEAR on the Art collection; run on the box)
layout check: scene rdwe_vending_room, 47 visible meshes, 22 colliders
PASS  COVER  Bench: 4 mesh(es) cover it (630 sample points, every one within 5 cm of art)
PASS  COVER  Beyond_lift: 1 mesh(es) cover it (1215 sample points, every one within 5 cm of art)
PASS  COVER  Beyond_machine: 1 mesh(es) cover it (1056 sample points, every one within 5 cm of art)
PASS  COVER  Beyond_real: 1 mesh(es) cover it (1296 sample points, every one within 5 cm of art)
PASS  COVER  Bin: 3 mesh(es) cover it (324 sample points, every one within 5 cm of art)
PASS  COVER  Machine_1: 3 mesh(es) cover it (1980 sample points, every one within 5 cm of art)
PASS  COVER  Machine_2: 3 mesh(es) cover it (1980 sample points, every one within 5 cm of art)
PASS  COVER  Machine_3: 3 mesh(es) cover it (1980 sample points, every one within 5 cm of art)
PASS  COVER  Machine_4: 3 mesh(es) cover it (1980 sample points, every one within 5 cm of art)
PASS  COVER  Machine_5: 3 mesh(es) cover it (1881 sample points, every one within 5 cm of art)
PASS  COVER  Room_Ceiling: 11 mesh(es) cover it (21675 sample points, every one within 5 cm of art)
PASS  COVER  Room_Floor: 15 mesh(es) cover it (28900 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_E_1: 7 mesh(es) cover it (7533 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_N_1: 7 mesh(es) cover it (4092 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_N_2: 4 mesh(es) cover it (432 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_N_3: 6 mesh(es) cover it (2976 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_S_1: 7 mesh(es) cover it (3627 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_S_2: 4 mesh(es) cover it (210 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_S_3: 6 mesh(es) cover it (3627 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_W_1: 5 mesh(es) cover it (3348 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_W_2: 4 mesh(es) cover it (390 sample points, every one within 5 cm of art)
PASS  COVER  Room_Wall_W_3: 5 mesh(es) cover it (3348 sample points, every one within 5 cm of art)
PASS  STRAY  17 tall solid mesh(es), each over a collider; 24 decor_* mesh(es) exempt
PASS  CLEAR  links.lift.arrive (0.00, 2.10): clear within 0.28 m
PASS  CLEAR  links.lift.at (0.00, 3.25): clear within 0.28 m
PASS  CLEAR  links.machine.arrive (0.60, -2.10): clear within 0.28 m
PASS  CLEAR  links.machine.at (0.60, -3.25): clear within 0.28 m
PASS  CLEAR  spots.Spot_trick_1.at (0.60, -1.00): clear within 0.28 m
PASS  CLEAR  spots.Spot_trick_2.at (-2.60, 0.00): clear within 0.28 m
PASS  CLEAR  spots.Spot_trick_3.at (0.60, -2.60): clear within 0.28 m
PASS: 30 of 30 checks passed

## glb_inspect world/rdwe_vending_room.glb --budget tris=300000,mb=8
materials  25: Ceiling_Tiles, Chrome, Brass, Door_Birch, Steel, Iron, Vend_Body, Vend_Glow, Vend_Panel, Door_Exit_Grey, Sign_Exit, Exit_Sign, Lamp_Emit, Lamp_Off, Paint_Navy, Paint_Palette, Plastic_Blue, Trim_Steel, Trim_White, Vend_Acid, Vend_Cyan, Vend_Red, Vend_Sun, Vinyl_Dark, Void_Black
textures   10, images: 256x256, 1024x1024, 512x512, 1024x1024, 1024x1024, 128x128, 256x256
bbox       8.55 x 3.05 x 9.1 (x, y up, z), min [-4.55, -0.05, -4.55]
requires   EXT_texture_webp
pass       tris: 5554 triangles, budget 300000
pass       mb: 0.90 MB, budget 8

## node --test shared/*.test.js
tests 297
pass 297
fail 0

## sizes
world/rdwe_vending_room.glb  0.94 MB
world/rdwe_vending_room.json  0.00 MB
blender/scenes/rdwe_vending_room.blend  0.39 MB
world/lightmaps/rdwe_vending_room_0.webp  0.06 MB
world/lightmaps/rdwe_vending_room_1.webp  0.08 MB
docs/renders/rdwe_vending_room/1_arrival.jpg  0.20 MB
docs/renders/rdwe_vending_room/2_wide.jpg  0.20 MB
docs/renders/rdwe_vending_room/3_detail.jpg  0.12 MB

## privacy grep (user names, absolute paths, session ids, e-mail; the .blend decompressed)
privacy grep: 9 files, 0 with hits

```

Nothing is wired: the manifest, `games/rdwe/`, `index.html`, `shared/` and the tests are untouched.
