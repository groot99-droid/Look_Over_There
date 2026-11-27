# Going back in, floors L4 to B1: fifteen chambers dressed and lit

All fifteen new chambers of `docs/BLENDER_AREAS.md` section 6, dressed and lit (step 2), each in its floor's own materials from the store's
Blender file: L4 (`gbi_L4_1` showroom floor, `_2` room sets, `_3` stockroom), L3 (`gbi_L3_2` white gallery, `_3` colonnade, `_4` white maze), L2
(`gbi_L2_2` door grid, `_3` long loop, `_4` split halls), L1 (`gbi_L1_2` cubicle farm, `_3` corridor offices, `_4` conference ring) and B1
(`gbi_B1_2` lido, `_3` baths, `_4` the drain). L4 is the store's showroom (terrazzo floor, off-white walls, the dark open ceiling, the store's orange
and blue); L3 its white plaster room; L2 its dark carpet and yellowed wallpaper; L1 its offices; B1 its white-tiled pools. The five safe houses are
the kit's room inside chamber 2 of each floor (not separate scenes). The tone is liminal: everything off and empty, but seemingly normal. Shelves
nearly bare, desks left, the floor arrows still pointing the way, every panel in the ceiling lit by day; at night only the night circuit (one panel
in nine on L4 and L3, one in four on the lower floors, whose rooms are small) and the emergency spots.

Each chamber's folder (`docs/renders/<scene>/`) holds its four stills, its plan, `bake.json` (the bake's own report), `caps.json` (the
brightness factors), `CHECKS.txt` (the gates) and a README with its sizes and brightness tables. This README covers all fifteen.

| File | What it is |
|---|---|
| `world/<scene>.glb` | the chamber's art (no kit pieces: the page draws those from `world/kit/`), with `TEXCOORD_1` and the lightmap extras |
| `world/lightmaps/<scene>_0.webp` .. `_3.webp` | four 2048 px lightmaps per chamber: `_0` shell and `_1` props by day (`lightmap`), `_2` and `_3` the same at night (`lightmap_night`) |
| `world/<scene>.json` | the layout, written by `export_scene.py` from the dressed `.blend`: **identical** to the greybox's (no collider, door, link, zone, marker or spot changed) |
| `blender/scenes/<scene>.blend` | the saved chamber (Git LFS): `Art` (`Props`; `Arch`: the shell's and the kit's colliders' grey twins, for the layout check only), `Skin`, `Doors`, `Layout`, `Hazards`, `Lights`, `Kit` (the kit pieces as stand-ins, never exported), `Export` |
| `tools/blender/build_gbi_dress.py` | the re-runnable build (all fifteen chambers): stages art, bake, export, check, render; `--pack`, `--gain` and `--measure` without Blender |
| `tools/blender/gbi_dress_skin.py` | pure Python: the shell as seen, the kit pieces' hulls and casings; `python tools/blender/gbi_dress_skin.py` prints them |
| `tools/blender/check_layout.py` | gains `--floor <y>`: heights are read from the chamber's floor (9.6 on L4, 6.4 on L3, 3.2 on L2, 0 on L1, -3 on B1), so its STRAY and CLEAR rules bite as on a floor at 0 |

## How it is built

The hotel floors' method (`tools/blender/build_hotel_floor2.py` and its skin module, on their branches), made for the chambers.

- **The layout is the greybox's, untouched.** The art stage makes every `COL_` box, `Zone_` box, `DoorLeaf_`, `Link_`/`Arrive_`, `Marker_` and
  `Spot_` (with every property) from `build_gbi_greybox.build(scene)`, then `export_scene.py` writes `world/<scene>.json`: the same file as the
  greybox's for all fifteen (checked: `git diff` is empty, and the greybox's `--check` model gate still passes).
- **The shell is only what can be seen** (`gbi_dress_skin.py`): the faces of the greybox's floor, ceiling, outer walls, partitions, columns and the
  elevator's shaft that look into the chamber's air, cut where boxes meet, faces hidden under solid furniture dropped. Their materials are the greybox's
  role names: `M_D_floor_<F>`, `M_D_wall_<F>`, `M_D_ceil_<F>`.
- **The connector kit is the kit's.** The page draws `world/kit/<piece>.glb` at each piece's `at` and `yaw` (the coordinator wires it); the build
  appends each piece from `blender/kit/<piece>.blend` only as a stand-in for the bake and the stills (collection `Kit`, never exported). The chamber
  meets them:
  - the shell draws nothing inside a piece's hull (the space its GLB fills: the car and the landing's frame, the hall, the stair door's hallway and
    landing, the safe house);
  - **casings** (`M_GBI_kit`, the floor's wall material under a role name of its own) close the pieces whose GLB has no outside: the painted-sky
    hall's sides, roof and front round its door; the stair door's hallway and the top of its landing; and the safe house, whose own outside
    (`SH_Outside`) is baked near black for a roof at night: the chamber covers it 1 cm out, in its own light;
  - the elevator's shaft (the greybox's `Shaft_*` boxes) is the chamber's wall;
  - the plain doors in the outer wall open onto a short reveal and a wall (`Backing_*`), never onto the void.
- **Door leaves** (the chamber doors in the partitions, the plain doors in the outer wall, the vent grilles) are their own nodes, `DoorLeaf_<door>`,
  origin at the hinge, each with its own mesh, baked where it stands. The kit's doors are drawn by the kit's GLB: their `DoorLeaf_` records are
  empties here.
- **Hazards** (`Hazard_<kind>_<n>`) are their own objects, origin at the start of their travel, every property the greybox gave them in their glTF
  extras, **not baked** (the page moves them): lava a glowing strip (`M_GBI_hazard_lava`, emissive), a chainsaw blade a toothed steel disc on its
  arm (`M_GBI_hazard_blade`), a crushing wall a slab the size of the greybox's (`M_GBI_hazard_crush`: the store's orange on L4, plaster on L3).
- **Materials stay swappable** (Secret Operations reskins these chambers). The shell is the three role materials plus `M_GBI_kit`; the dressing keeps
  the greybox's `M_GBI_furn_<F>`, `M_D_trim`, `M_D_door`, `M_GBI_vent` and `M_GBI_hazard_<kind>`, and adds a few of the store's own (`M_X_white`,
  `M_X_dark`, `M_X_steel`, `M_X_exit`, `M_Fixture_Housing`, `M_U_blue`, `M_U_bluepaint`, `M_U_yellow`, `M_U_arrow`, `M_U_rug_*`) and some of its
  own (`M_GBI_card`, `M_GBI_tape`, `M_GBI_wood`, `M_GBI_textile`, `M_GBI_shutter`, `M_GBI_canvas`, ...). A reskin replaces materials by name; the
  lightmaps hold only light, so they stay valid.

## Light: a day set and a night set

Two sets on the same UVs, as the store floors and the hotel lobby: every baked material carries `lightmap` / `lightmap_intensity` and
`lightmap_night` / `lightmap_night_intensity`.

- **Day:** the store's flush fluorescent panels (1.2 m by 0.6 m, every 4 m on L4, 4.5 m on L3, 3 m on L2 and L1, 4 m on B1, an area light under each; the panel faces are
  `Lamp_Emit`), the night circuit and the EXIT signs.
- **Night (the store shut):** `Lamp_Emit` off; one panel in nine (L4, L3) or four (L2, L1, B1) stays on (the night circuit, `M_GBI_nightlight`, always on); twin-spot
  emergency lights (`Emergency_Emit`, on only at night) beside every way through and every 13 m along the outer walls; the EXIT signs (the store's
  `M_X_exit`, always on, as in the store).
- Both `Lamp_Emit` and `Emergency_Emit` are exported at their full strength; the page switches them.
- **Bake:** Cycles on the rented GPU (OptiX), 512 samples a set, diffuse direct and indirect (no colour), 8 px margin, OIDN, a highlight shoulder
  (light above a map's 80th percentile rolls off toward 2.5 times it), white point at the 99.5th percentile (at most 12 x the 90th). The shell's faces
  are packed by hand on their page (each face its own pixel-aligned island); the props are smart-projected on theirs. Fixed pages: 2048 px each.
- **Brightness** (`docs/renders/<scene>/caps.json`, from `build_gbi_dress.py --gain`): per set one gain brings the walls to a displayed p50 of 0.50
  (L4), 0.55 (L3, B1) or 0.45 (L2, L1) by day and 0.15 at night; any material that would pass p99 0.97 or p90 0.88 gets a lower factor of its own. `--pack` applies
  them to the GLB's extras. The tables below are `lab_display.py`'s (and its night twin's) on the final GLBs.

## Sources and licences

Nothing was downloaded and nothing paid for. Everything is the repo's own or generated here.

| What | Used for | Source | Licence |
|---|---|---|---|
| The store's materials `M_D_floor_L4`, `M_U_wall_L4`, `M_D_ceil_L4`, `M_D_floor_L3`, `M_D_wall_L3`, `M_D_ceil_L3`, `M_X_*`, `M_U_*`, `M_Fixture_Housing` and their textures | the shell (under the greybox's role names) and the fittings | `blender/Look_Over_There.blend` (the store's own file, in the repo), appended by name; normal maps dropped (the page draws baked materials unlit) | the store's |
| `sofa_02` | the room sets' sofas | Poly Haven, https://polyhaven.com/a/sofa_02, as already placed in the store file (`Set_sofa_02`) | CC0 1.0 |
| `coffee_table_round_01` | the room sets' coffee tables | Poly Haven, https://polyhaven.com/a/coffee_table_round_01, in the store file (`Set_coffee_table_round_01`) | CC0 1.0 |
| The connector kit's pieces | bake and still stand-ins only | `blender/kit/*.blend` (its README lists its CC0 maps) | as listed there |
| Hazard tape, lava, cardboard, brushed steel, roller shutter, canvas | `M_GBI_tape`, `M_GBI_hazard_lava`, `M_GBI_card`, `M_GBI_vent` and `M_GBI_hazard_blade`, `M_GBI_shutter`, `M_GBI_canvas` | generated by the build (numpy, fixed seeds) | own work |
| Aisle letters and numbers | the hanging aisle boards | Blender's built-in font (DejaVu Sans), as geometry | the Bitstream Vera / DejaVu free font licence |

Tools: Blender 5.2.1 LTS with Cycles, OIDN and the glTF add-on; Python with numpy and Pillow.

## The chambers

### `gbi_L4_1`: showroom floor (the run's first chamber)
You start by the south wall (`Marker_Arrival`, Spawn). Six double-sided gondolas, 18 m each: a plinth, a pegboard spine, four white shelves a
side, the store's orange on the uprights, end panels and header, nearly empty (a carton here and there). Blue aisle boards (1, 2, A) hang on
wires. The lava band (`Hazard_lava_1`, a glowing strip that advances from the west wall) is crossed on ten display islands (white tops on a dark
kick, a yellow nosing at their edges), the band's two edges taped across the floor. Behind a 3.2 m partition, the bays: a checkout counter in the
store's blue (till, belt, card reader) and two display tables with cartons. The store's blue band with its yellow stripe runs high on the south and
north walls; the store's floor arrows lead from the spawn to the elevator (kit) in the north-west bay; the vent duct on the east wall is shut.

### `gbi_L4_2`: room sets
Mock rooms either side of the aisle, behind 3 m set walls, each back wall painted its own colour (`M_GBI_accent_1`..`5`): five living rooms on
the west (the store's Poly Haven sofa, dark leather, and round coffee table on a rug, a framed print), four bedrooms on the east (a made bed with a headboard and a foot
bench, a framed print over it). Boards B to E hang over the aisle. Two chainsaw slots (dark steel, taped edges) for `Hazard_blade_1` (down the aisle)
and `Hazard_blade_2` (across, in front of the safe house). Arrows from the elevator (kit, south) to the painted-sky hall (kit, north, cased). The
safe house (kit) stands against the north wall, cased.

### `gbi_L4_3`: stockroom
Ten runs of pallet racking, 4 m high: blue uprights in pairs, orange beams at three levels, chipboard decks, a pallet of cartons here and there.
Three pallet stacks, the dock's roller shutter across the north wall, yellow lines along every rack, the cross aisle taped where the two rack ends
close (`Hazard_crush_1`, `_2`: orange rack-end panels). Arrows from the hall door (south-west) to the painted-sky hall (kit, north-east, cased).

### `gbi_L3_2`: white gallery
The store's white plaster room, 3.2 m high, the panels in its ceiling. Six free-standing plaster walls hung with blank canvases (stretched white
cloth, 4 cm proud), five white plinths on a dark shadow-gap base, all empty. The chainsaw slot across the gallery (`Hazard_blade_1`). You arrive
through the stair door from `gbi_L3_1` (kit, its hallway cased; the hallway's top stops 0.3 m under the ceiling) and leave by the plain door in the
north wall, which opens onto a short reveal. The safe house (kit) stands against the west wall, cased.

### `gbi_L3_3`: colonnade
24 square plaster columns with a plinth and a capital, two long plaster walls closing the hall you must walk the length of, its crush zones
taped where the slabs close (`Hazard_crush_1`, `_2`: plaster slabs). In by the plain door in the south wall, out by the elevator (kit) on the north
wall.

### `gbi_L3_4`: white maze
The plaster walls fold the room into one long path; the lava leg (`Hazard_lava_1`) is taped at its west end. In by the elevator (kit, south), out
by the stair door down to `gbi_L2_1` (kit, north, its hallway cased).

### `gbi_L2_2`: door grid
The store's L2 materials (`M_D_floor_L2`, `M_D_wall_L2`, `M_D_ceil_L2`): a grid of small rooms behind plaster walls, a door in every side (each
leaf its own node, closed, open or ajar as the greybox says), stacks of cartons left in a few rooms, the gas row down the middle
(`Hazard_gas_1`, a translucent green cloud, unbaked). In by the stair door from `gbi_L2_1` (kit, cased), out by the painted-sky hall (kit, cased);
the floor's safe house (kit) by the south wall, cased; the vent duct on the east wall, shut.

### `gbi_L2_3`: long loop
Rings inside rings of plaster walls; the core room's table; the chainsaw slots in the north corridor and the ring's south leg (`Hazard_blade_1`,
`_2`). In by the hall door (south), out by the plain door north.

### `gbi_L2_4`: split halls
Three long halls side by side, desks left in them (a top, steel ends, a modesty panel, a dark monitor on some), the middle hall's closing walls
(`Hazard_crush_1`, `_2`). Out by the stair door down to `gbi_L1_1` (kit, cased).

### `gbi_L1_2`: cubicle farm
The store's L1 materials. Twenty-four cubicles of grey fabric panels with aluminium caps round their desks, private offices along the north wall,
the gas aisle (`Hazard_gas_1`). In by the stair door from `gbi_L1_1` (kit), out by the elevator (kit); the floor's safe house (kit) on the east
wall, cased.

### `gbi_L1_3`: corridor offices
Two corridors crossing, offices in every quarter with their desks, the north leg's closing walls (`Hazard_crush_1`, `_2`), the vent duct on the
north wall. In by the elevator (kit), out by the painted-sky hall (kit, cased).

### `gbi_L1_4`: conference ring
A ring corridor round the conference room (its long table), offices outside with desks, a blade in the west leg (`Hazard_blade_1`) and gas
filling the conference room (`Hazard_gas_1`). Out by the stair door down to `gbi_B1_1` (kit, cased).

### `gbi_B1_2`: lido
The store's B1 materials (white tile). A pool under columns, its rim walls the floor's tile, the water the store's own `M_Water` (alpha blended,
unbaked); the tide (`Hazard_tide_1`, a translucent sheet that rises). The floor's safe house (kit) on the west wall, cased.

### `gbi_B1_3`: baths
Bath cells off a tiled corridor, six pools of the store's water, the west bath's tide (`Hazard_tide_1`) and gas down the corridor
(`Hazard_gas_1`); the vent duct on the west wall. Out by the painted-sky hall (kit, cased).

### `gbi_B1_4`: the drain
Wave 20, the run's end: a walkway round a flooding basin (`Hazard_tide_1`), columns, two chainsaw slots (`Hazard_blade_1` across the last dash,
`_2` down the east walkway), the EXIT hall out (kit, cased).

## Checks (each chamber's `CHECKS.txt` has the full output)

- `check_layout.py --collection Art --floor <y>` on each dressed `.blend`: every check passes (COVER, STRAY, CLEAR).
- `build_gbi_greybox.py --check . --glb docs/renders/gbi_greybox/glb`: GATES PASS (the model gate: the 15 layout files exactly as the model says);
  run again with the dressed GLBs in place of their greybox GLBs: every `Hazard_<kind>_<n>` is its own node on its origin, with its extras.
- `export_scene.py` wrote the fifteen layout files: `git diff` against the greybox's commit is empty.
- `node tools/worlddoc.mjs check`: OK, 0 errors (the warnings say the scene and its links are new to the manifest).
- `glb_inspect.py --budget tris=300000,mb=8`: pass for all fifteen.
- `node --test shared/*.test.js`: 297 of 297.
- The privacy grep (the brief's patterns over every committed file, the `.blend` decompressed): no user name, absolute path, session id or
  e-mail. Its case-insensitive drive-letter pattern also matches two random byte runs inside compressed image data (`gbi_L3_3_3.webp`, and the packed
  pictures in `gbi_L4_2.blend` / `gbi_L4_3.blend`); those are not text.

## For the coordinator

- **Wiring** (not done here: the manifest is the coordinator's): each chamber's GLB, its four lightmaps, and the kit pieces' GLBs at the `at` and
  `yaw` in the greybox README's table (the chamber draws no kit art). `Lamp_Emit` off and `Emergency_Emit` on when the page switches to the night
  set (`setLightSet("night")`), as the mall does.
- **L4's ceiling is the store's own dark grey**: it shows at p50 about 0.02 by day. That is the store floor's look (a dark open ceiling over a lit
  showroom), not a bake fault; a reskin or a lighter `M_D_ceil_L4` changes it by name.
- The safe house's own outside (`SH_Outside`, baked near black in the kit) is covered by the chamber's casing 1 cm out; if the page draws the kit
  GLB with its own outside, both are there and the casing is the one seen.
- The stair door's hallway stops 0.3 m under L3's 3.2 m ceiling; the gap above it reads as a shadowed soffit.
