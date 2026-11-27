# The mall's back scenes: `construction`, `service_corridor`, `mirror_bathroom`, and `sky_hall_01` to `sky_hall_04`

Three mall scenes dressed and lit (`docs/BLENDER_AREAS.md`, section 3, step 2), built round the mall greybox (`tools/blender/build_mall_greybox.py`, draft PR #110) by `tools/blender/build_mall_back.py` in Blender 5.2.1, and the connector kit's painted-sky hall placed in the four sky hall scenes. The mall is old, abandoned and half refitted; nobody is visible. There are no reference photos: everything follows the written descriptions. Like the atrium (`entrance`), every dressed scene has two light sets on the same lightmap UVs: the day set on `lightmap`, and the emergency set on `lightmap_night` for when the mall locks at 20:00.

This README covers all seven scenes. Each dressed scene's folder (`docs/renders/<scene>/`) holds its three stills, its plan, `bake.json` and `caps.json`.

| File | What it is |
|---|---|
| `world/construction.glb` | 4.57 MB on disk (4.35 MiB), 26 750 triangles, 49 draw calls |
| `world/service_corridor.glb` | 2.79 MB (2.66 MiB), 16 302 triangles, 47 draw calls |
| `world/mirror_bathroom.glb` | 1.64 MB (1.56 MiB), 4 850 triangles, 34 draw calls |
| `world/lightmaps/<scene>_0.webp`, `_1.webp` | the day set (second UV set): `_0` the shell, `_1` everything in it |
| `world/lightmaps/<scene>_2.webp`, `_3.webp` | the emergency set on the same UVs: `_2` the shell, `_3` everything in it |
| `world/<scene>.json` (all seven) | the layouts, written by `export_scene.py` from the `.blend`: the same as the greybox's files (construction's has the greybox's new `Deck_Rail_3` and `Stair_Rail_2`, the deck's and the stair's west rails) |
| `blender/scenes/<scene>.blend` (all seven) | the saved scenes (Git LFS). The dressed ones: `Art` (`Props`, and `Arch`: grey twins of the shell's colliders for the layout check and the plan), `Skin` (the shell as seen), `Doors`, `Layout`, `Lights` (`Lights_Day`, `Lights_Night`), `Standins`, `Export`. The sky halls: `Layout` (the kit's, placed) and the kit's `Art` collection linked from `blender/kit/sky_hall.blend` |
| `tools/blender/build_mall_back.py` | the re-runnable build of all seven |
| `tools/blender/kit_place.py` | the fix from `claude/blender-hotel-floor3-roof` (32ac313): appended objects start from `matrix_basis` |

## What is in it

### `construction` (24 m by 18 m, 6.5 m high)

A unit mid-fit-out behind the books wing's hoarding.

- **Scaffold:** tube-and-clip, galvanised tubes with dark couplers: standards on the greybox's three deck posts and three more against the north wall, ledgers, transoms, knee braces and facade braces, a timber board deck at 3 m (scaffold boards with staggered joints and steel end bands), double guard rails with toe boards along the front, the east end and the west end (`Deck_Rail_3`, over the 1 m gap to the west wall, on a post clipped to the end transom at the stair's head).
- **The site stair:** twelve galvanised treads with yellow nosings on the greybox's steps, stringers, tube handrails on both sides: the `Stair_Rail` box (east) and `Stair_Rail_2` (west, over the 1 m gap to the wall); both boxes run from the floor to 4 m, so they guard the whole flight.
- **Hoarding:** plywood over the south wall to 3 m, the site door (ledged and braced ply, a hasp and padlock, KEEP SHUT), a blue PPE board, UNIT 14 FIT-OUT and NO UNAUTHORISED ACCESS painted on it, an EXIT sign over the door.
- **Walls:** bare grey blockwork. The east wall and the north wall's east end are half tiled in white 150 mm tiles, row by row to a ragged top, combed adhesive past them, loose tiles and boxes of tiles on the floor. A half-built stud partition (the greybox's studs and plates) with one plasterboard sheet.
- **Cable runs** clipped along the west and north walls, a yellow 110 V distribution box, orange cables over the floor to the lamps; a cable tray hung from the soffit; three concrete beams overhead.
- **Lights:** three tripod work lamps (two LED floods each, `Lamp_Emit`, passable `decor_`), one of them up on the deck aimed down into the room; festoon lighting strung between the columns and along the deck (caged bulbs, `Lamp_Emit`). Five twin-spot emergency units (`Emergency_Emit`).
- **Materials and plant:** cement bags stacked on the pallet under the deck and a few loose with a spill; a yellow mini skip full of rubble on `Pallet_2`; an orange cement mixer; a stowed scissor lift; a pallet of plasterboard under a dust sheet; a dust sheet hung from the deck rail, another on the floor; a wheelbarrow, a ladder. Blue chalk setting-out lines with red spray ticks, dust and stains on the slab.
- **The lift pit** (`Zone_hazard_lift_pit`) stays open: yellow edge protection on the greybox's four barrier boxes (posts, top and mid rails, a striped toe board), red and white barrier tape on the outside, DANGER / OPEN LIFT PIT signs on the north and south sides, the slab edge painted in hazard stripes, rubble, a puddle and starter bars in the pit.
- **The sky hall doorway** up on the deck: a raw timber lining and a steel lintel, a DANGER / NO ACCESS BEYOND THIS POINT sign beside it; the leaf is a white panel door like the kit hall's.

### `service_corridor` (46 m by 2 m, 3 m high, and the spur)

The hidden network's back corridor.

- **Painted block:** a grey-green dado to 1.2 m under cream, a grey epoxy floor with yellow walkway lines, black rubber bump rails, steel corner guards at the bin bay and the spur.
- **Overhead:** the greybox's two pipe runs (a green main and a red sprinkler main with drops and heads) on unistrut hangers, a galvanised cable ladder with cables along the south side and up the spur, twelve twin fluorescent battens (`Lamp_Emit`, the one at x 0 dead) and three more in the spur and the bin bay.
- **Doors:** four grey steel staff doors with vision panels, push and kick plates, each with its wing stencilled over it (CINEMA, BOOKS, ENTERTAINMENT, FOOD COURT) and a door number; two fire door sets across the corridor held open flat against the walls; at the west end the fire exit (red double doors with push bars on the greybox's `Fire_Door` box, a FIRE EXIT sign).
- **Bins:** two 1100 litre wheelie bins (green, grey) in their bay with CARDBOARD ONLY / GENERAL WASTE signs and bin bags.
- **The keycard freight lift spur:** a steel portal round the lift gate with a FREIGHT indicator, two steel mesh gate leaves (`network_A`, `network_B`), hazard stripes on the sill, the car beyond (stainless walls, checker plate, a handrail, a ceiling light, a button panel). **The reader** is on the spur's west wall beside the gate at 1.2 m, by `Spot_keycard_1`: black, a dark glass pad, a card slot and a red light that is always on (`Reader_Glow`), a SWIPE KEYCARD label and a FREIGHT LIFT / AUTHORISED STAFF / KEYCARD ONLY board above it.
- **Emergency set:** four bulkheads on the north wall and one in the spur (`Emergency_Emit`), two hanging EXIT signs, extinguishers, call points, a notice board, a sack truck.

### `mirror_bathroom` (10 m by 8 m, 3 m high)

A tiled public restroom.

- White 150 mm wall tile to 2.1 m with a chrome trim and a dark tile skirting, painted above; grey speckled 300 mm floor tile; a lay-in ceiling with six LED panels (`Lamp_Emit`) and two emergency downlights (`Emergency_Emit`); an EXIT sign over the door.
- **The counter:** a solid-surface top and apron on the `Vanity` box, six round vessel basins with chrome taps, soap dispensers between the mirrors.
- **The six mirrors** `Mirror_1` to `Mirror_6` are each their own node in the GLB, the glass only (a quad, its origin at its middle), with the greybox's custom properties as glTF extras: `mirror`, `portal`, `portal_to` (`Mirror_4`: portal 1, portal_to sky_hall_03). The glass is baked as a flat, dark silver surface (`Mirror_Glass`) for the page to swap. The frames are separate (chrome).
- **The tell:** `Mirror_4`'s frame is a darker, older bronze where the others are chrome, a little heavier, its glass set deeper in it, and a hairline crack runs in the tile under it.
- **Stalls:** four cubicles in grey-blue phenolic laminate on chrome legs (the greybox's partitions and pilasters), a chrome headrail, raised doors with an indicator bolt and a coat hook, wall-hung WCs (`decor_`), flush plates, roll holders. A hand dryer, a bin and a wet floor sign (`decor_`).

### `sky_hall_01` to `sky_hall_04`

**The kit's art is the hall: the page draws `world/kit/sky_hall.glb` at (0, 0, 0), yaw 0 in each sky hall scene. There is no copy per scene.** The build places the kit's `sky_hall` in each scene at (0, 0, 0), yaw 0, with `tools/blender/kit_place.py`, as the greybox README says; the `_<suffix>` that `kit_place` adds is taken off again, so the doors, links and markers keep the greybox's ids (`DoorLeaf_entry`, `DoorLeaf_exit`, `entry`, `exit`, `Marker_Entry`, `Marker_Exit`). `kit_place` writes the exit door's turned yaw as -180; the build keeps the greybox's 180 (the same angle). The greybox's mannequin spots in `sky_hall_02` and `sky_hall_04` are added from the greybox model. Each `.blend` links the kit's `Art` collection rather than copying it (90 KB each).

**One light set:** the kit's hall is lit by its own painted-sky laylight at every hour, so it has one lightmap (`world/lightmaps/kit_sky_hall_0.webp`, the kit's) and no night set.

## How it is built

- **The layout comes from the greybox model.** The build imports `build_mall_greybox.py` and makes every `COL_` box, `Zone_` box, `DoorLeaf_`, `Link_`/`Arrive_`, `Marker_` and `Spot_` from it, with the same names and numbers; `export_scene.py` writes the layout files again, and they hold exactly what the greybox's files hold. No collider was added or moved here; the later fixes (the west rails of the deck and the stair, `Deck_Rail_3` and `Stair_Rail_2`) were made in the greybox and the scene re-dressed and re-baked from it.
- **The shell is only what can be seen** (the mazes' and floor 1's method): every face of the room's boxes (walls, floors, ceilings, the columns, the hoarding, the pit's floor) that looks into the air, cut where other boxes meet it, packed by hand on the shell's lightmap page. Every other collider (the scaffold's deck, posts and rails, the steps, the studs, the pallets, the mixer, the scissor lift, the pit's barriers, the bins, the stall partitions and pilasters, the vanity, the fire exit) gets its own art over its box, one object per box, so the layout check's cover rule tests the real art. The steps are art 0.2 m deep each, so the check reads them as steps.
- **The props** are merged by material for export; faces pressed against the shell are dropped. The door leaves are reused meshes, one per kind and size, each leaf its own node with its origin at the hinge; one leaf per mesh is baked and the others show its lightmap. Thin free-standing pieces (leaves, partitions) keep both faces in the lightmap.
- **Two light sets.** `Lights_Day` (the working lights: tripods and festoons; battens; ceiling panels) with `Lamp_Emit` on, and `Lights_Night` (the emergency fittings alone) with `Emergency_Emit` on. Each lightmap page is baked twice on the same UVs; the day maps are `lightmap`, the night maps `lightmap_night`. The EXIT signs' faces (`Sign_Exit`) and the reader's light (`Reader_Glow`) are always lit and are not switched names. The GLB carries `Lamp_Emit` at 3.0 and `Emergency_Emit` at 5.0, the strengths the page switches on.
- **Bake:** Cycles on the rented GPU (OptiX), diffuse direct and indirect, the day set at 512 samples and the night set at 768, OIDN denoise, a soft shoulder, 8-bit PNG then WebP q90 (`--pack`), fixed 2048 pages. Texel density: construction 44 / 43 px/m (shell / props), service_corridor 70 / 44, mirror_bathroom 107 / 120. The twelve bakes took 9 to 127 s each (construction's four, re-baked for the stair rails: 30, 78, 34 and 81 s).
- **Brightness** (`caps.json`, read at export): each set's intensity is scaled so the big shell surfaces reach the targets, then any material still over p99 0.98 or p90 0.9 is capped by itself. The night set is scaled so the shell's brightest emergency pools reach about p99 0.35: dark, the walls p50 0.03 to 0.09, readable near the fittings.
- **Stills:** Cycles 128 samples, AgX, 1920 x 1080, the day set with Blender's real lights; the construction stills at +1.6 EV (the bake is scaled; the real lights are dim). `2_wide` of the corridor and the bathroom is a cutaway (ceiling off). Plans are orthographic, north up.

Run on the box (from a slim copy of the worktree):

    blender -b --factory-startup --python tools/blender/build_mall_back.py -- --scenes construction,service_corridor,mirror_bathroom --stage all --caps caps --samples 512 --night-samples 768 --work work/mall_back
    blender -b --factory-startup --python tools/blender/build_mall_back.py -- --scenes sky_hall_01,sky_hall_02,sky_hall_03,sky_hall_04
    python tools/blender/build_mall_back.py --pack <scene> --work <work dir>

## Brightness (lab_display.py: shown = texture x base colour x lightmap x intensity / pi)

The main surfaces; every material of all three scenes, both sets, is at or under p90 0.9 and p99 0.98 (construction measured again after the stair rails' re-bake: day at most p99 0.973 (`Leaf_White`) and p90 0.764, night at most p99 0.780 and p90 0.685; `Column_Concrete`'s day factor lowered from 13.46 to 13.28 in `caps.json` after the deck rail's re-bake, which brought it from p99 0.983 to 0.970).

| Scene | Set | Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|---|---|
| construction | day | Block_Bare (walls) | 474.5 | 0.154 | 0.434 | 0.886 |
| construction | day | Slab_Concrete | 419.7 | 0.107 | 0.346 | 0.746 |
| construction | day | Soffit_Concrete | 430.5 | 0.092 | 0.261 | 0.554 |
| construction | day | Column_Concrete | 78.0 | 0.166 | 0.497 | 0.970 |
| construction | night | Block_Bare | 474.5 | 0.032 | 0.112 | 0.269 |
| service_corridor | day | Block_Paint (walls) | 212.6 | 0.325 | 0.763 | 0.931 |
| service_corridor | day | Block_Dado (the dark band) | 139.0 | 0.098 | 0.180 | 0.270 |
| service_corridor | day | Floor_Epoxy | 120.6 | 0.044 | 0.082 | 0.141 |
| service_corridor | night | Block_Paint | 212.6 | 0.087 | 0.299 | 0.353 |
| mirror_bathroom | day | Tile_Wall_Bath | 74.5 | 0.252 | 0.505 | 0.788 |
| mirror_bathroom | day | Paint_Bath | 32.6 | 0.209 | 0.476 | 0.735 |
| mirror_bathroom | day | Tile_Floor_Bath | 80.2 | 0.170 | 0.252 | 0.284 |
| mirror_bathroom | night | Tile_Wall_Bath | 74.5 | 0.063 | 0.180 | 0.331 |

The sky hall is the kit's (its brightness is in `blender/kit/README.md`: wainscot p50 0.15, mural 0.66).

## Checks

- `check_layout.py`: construction 64 of 64 (with `Deck_Rail_3` and `Stair_Rail_2`), service_corridor 38 of 38, mirror_bathroom 24 of 24 pass (on `Art`: the props and the shell's grey twins).
- The sky halls: COVER passes for all ten colliders on the kit's linked art; STRAY and CLEAR fail on it because the kit's art is merged by material (one mesh's box spans the whole hall) and its door leaves stand in their openings. This is the kit piece as published (`claude/blender-hotel-kit`), unchanged.
- `build_mall_greybox.py --check . --glb world`: GATES PASS (links, navigable 18 of 18, steps, corridors, mirrors: 6 of 6 `Mirror_<n>` nodes in `world/mirror_bathroom.glb`, the portal Mirror_4).
- `node tools/worlddoc.mjs check`: all seven OK, 0 errors (warnings: new links not yet in the manifest); construction 62 colliders.
- `glb_inspect.py --budget tris=300000,mb=8`: all three pass (construction 26 750 triangles, 4.35 MiB).
- The axes check (a marker cube at the arrival point through the exporter): PASS in all three.
- `node --test shared/*.test.js`: 297 pass.
- Privacy: no user name, path, session id or e-mail in any file, the decompressed `.blend`s included; JPEG comments and APP1 stripped.

## Sources and licences

Every texture is a CC0 Poly Haven texture already in the repo; nothing was downloaded.

| Texture in the repo | Used for | Source | Author | Licence |
|---|---|---|---|---|
| `blender/textures/kit/concrete_floor_02_diff_1k.jpg` | slab, soffit, columns, beams, blockwork (with drawn joints), rubble, the counter | https://polyhaven.com/a/concrete_floor_02 | Rob Tuytel | CC0 1.0 |
| `blender/textures/kit/plywood_diff_1k.jpg` | the hoarding, scaffold boards, the site door, cardboard | https://polyhaven.com/a/plywood | Rob Tuytel | CC0 1.0 |
| `blender/textures/kit/rough_linen_diff_512.jpg` | dust sheets | https://polyhaven.com/a/rough_linen | colormass, Rico Cilliers | CC0 1.0 |
| `blender/textures/kit/painted_metal_shutter_diff_1k.jpg` | steel door leaves, the fire exit | https://polyhaven.com/a/painted_metal_shutter | Charlotte Baglioni, Dario Barresi, Rico Cilliers | CC0 1.0 |
| `blender/textures/factory_floor/concrete_floor_diff.jpg` | the pit, the epoxy floor, adhesive | https://polyhaven.com/a/hangar_concrete_floor | Dimitrios Savva | CC0 1.0 |
| `blender/textures/factory_floor/paint_grime_diff.jpg` | the skip, mixer, scissor lift, rails, bins, couplers, gate | https://polyhaven.com/a/green_metal_rust | Rob Tuytel | CC0 1.0 |
| `blender/textures/factory_floor/wood_diff.jpg` | studs, pallets, cork | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| `blender/textures/main_floor/wall_paint_diff.jpg` | painted block (with drawn joints), frames, pipes | https://polyhaven.com/a/painted_plaster_wall | Amal Kumar | CC0 1.0 |
| `blender/textures/laboratory/wall_paint_diff.jpg` | soffits, plasterboard, bathroom paint, white leaves, partitions, mirror glass | https://polyhaven.com/a/white_plaster_02 | Rob Tuytel | CC0 1.0 |
| `blender/textures/laboratory/ceiling_tile_diff.jpg` | the bathroom's lay-in ceiling | https://polyhaven.com/a/polystyrene | Dimitrios Savva, Dario Barresi | CC0 1.0 |
| `blender/textures/apartment/dark_wood_diff_1k.jpg` | the restroom door | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |

Own work, drawn by the build with numpy from fixed seeds: the blockwork joints, the wall and floor tiles, hazard stripes, barrier tape, checker plate, the cement bag print, brushed steel, dust, stains, the cement spill and the crack. All geometry is the build's own; the text is Blender's built-in font. No Meshy, no Higgsfield, no purchase. Tools: Blender 5.2.1 (GPL) with Cycles, OIDN and the glTF add-on; Python with numpy and Pillow.

## Notes for the coordinator

- The sky halls have no GLB of their own: draw `world/kit/sky_hall.glb` at (0, 0, 0), yaw 0 in each, with its lightmap `kit_sky_hall_0`.
- `Mirror_1` to `Mirror_6` are nodes in `world/mirror_bathroom.glb` with extras `mirror`, `portal`, `portal_to`; swap their material for the portal. `Spot_mirror_<n>` and `Spot_puzzle_1` are in the layout file as before.
- The deck's west edge (x -11, beside the wall) now has a guard rail and its collider, `Deck_Rail_3` (x -11 to -10.9, y 3 to 4, z -9 to -5.2), added in `build_mall_greybox.py` and dressed like the east end; nothing else in the layout moved. The site stair's west side (the same gap) has one too, `Stair_Rail_2` (x -11.05 to -11.0, y 0 to 4, z -5.2 to -1.6), dressed like the east handrail. The east side's `Stair_Rail` box, 1 m tall in the first greybox (y 0 to 1, so it did not stop a walker high on the flight), now runs from the floor to 4 m like the west one; its handrail art already reached 4 m, so only the box changed.
- The construction day set is scaled up a lot (the room has no daylight; tripods and festoons only), so its lightmaps carry most of their range in the darker half.
- Door leaves' outer faces (toward the next scene) are dark: they are lit from this scene only.
