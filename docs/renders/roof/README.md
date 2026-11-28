# roof: the hotel's roof, at night

The roof of the apartment tower (`docs/BLENDER_AREAS.md` section 1: "24 m by 24 m, open sky. The city skyline at night (an R3 backdrop), a `Spot_puzzle` and a safe house from the kit"; `docs/WORLD.md`: "The roof is the upper level: city skyline, a puzzle and a safe house"), dressed and lit in Blender on the greybox's layout, baked by the moon and the city's glow, with its skyline backdrops.

| File | What it is |
|---|---|
| `world/roof.glb` | the art: 2.12 MB, 5 268 triangles, 18 materials, 18 meshes of one primitive each (one per material, and the bulkhead's leaf as its own node), 12 WebP textures |
| `world/roof.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`: 22 colliders, 1 door, 2 markers, 1 link, 1 zone, 7 spots. It is exactly what the greybox model writes (`build_hotel_greybox.py --preview`); what changed in the greybox is under "The layout" |
| `world/lightmaps/roof_0.webp`, `roof_1.webp` | the night bake (second UV set, `TEXCOORD_1`): the roof, parapet, bulkhead and the safe house's outside (2048), the plant and fittings (1024) |
| `world/backdrops/roof_night.webp`, `roof_day.webp` | the skyline backdrops (R3): 4096 x 2048 equirect panoramas from the roof's centre, 704 KB (night) and 494 KB (day), WebP q95 |
| `blender/scenes/roof.blend` | the saved scene (Git LFS): `Art`, `Doors` (the bulkhead's leaf, origin at the hinge), `Layout`, `Kit` (the connector kit's safe house, appended as a stand-in), `Export`, `Lights_Lamps` (with the moon), `Lights_Kit` (the safe house's own lamps) |
| `tools/blender/build_hotel_floor3_roof.py` | the re-runnable build (this scene and floor 3); it imports the greybox model, so no coordinate of the layout is typed in |
| `tools/blender/build_roof_backdrop.py` | the re-runnable backdrop build: the city, the sky, the orientation self-check, the renders, the WebP packing |
| `docs/renders/roof/` | the three review stills (this folder) |

## Review stills (Cycles, 160 samples adaptive, OIDN, 1920 x 1080 JPEG, AgX, the scene's own lights; the night backdrop behind)

| | |
|---|---|
| `1_arrival.jpg` | the arrival point out of the stair bulkhead (`Arrive_floor_3`, 4.8, 8) at eye height, looking west-north-west across the roof to the safe house |
| `2_wide.jpg` | from the south-east corner, by the bulkhead, toward the safe house and the water tank |
| `3_detail.jpg` | the safe house's door (the kit's room inside, lit by its own lamps), the paver path |

## What is in it

- **The roof:** gravel ballast over the slab with eight tar patches, a concrete paver path from the bulkhead's door west and north to the safe house, with a branch to a square of pavers round the puzzle's spot (a tar ring marks it; the page draws the puzzle), four roof drains, four short vent stubs (under 0.2 m).
- **The parapet:** brick, 1.1 m, a tar flashing at its foot, a concrete coping in 1.2 m lengths with a drip on the roof side.
- **The stair bulkhead** (the greybox's box, 4 m by 4 m, 2.8 m): brick walls, a tar roof with a concrete lip, the kit's 1.1 m stair door in its west wall (a green-grey steel leaf, STAIRS on it, in a steel frame), a STAIRS sign; inside (seen when the door opens) a small landing and a flight going down into the dark under a bare bulb. On its roof an aerial mast with three dipoles and a red beacon, and a dish.
- **The water tank:** a timber tank bound with iron hoops under a shallow cone roof, on a steel stand in a cage of four corner posts, with a ladder and an outlet pipe.
- **Two HVAC units:** a packaged unit with corrugated sides, two fans and an electrical box; a condenser with one big fan.
- **The safe house** is the connector kit's (`blender/kit/README.md`): the page draws `world/kit/safe_house.glb` at (-8, 0, -5.8), yaw 0. Its outside walls and roof are this scene's own `SH_Outside` (the kit's material and texture), a skin 1 cm outside the kit's, so this bake lights them; the kit's own darker skin is hidden behind it. An old aerial on its roof.
- **Lights:** three wall packs on the bulkhead (west over the door, south, north), the bulb inside it, the beacon, the safe house's lantern and its interior lamps through the door (the kit's own), the moon and the city's glow.

## Light

| Set | Light | Maps | Material property |
|---|---|---|---|
| night (the only set) | the moon (south-east, bearing 135 degrees, 34 degrees up, 0.3 W/m2, cool), the night sky warmed low down by the city's glow, the wall packs (sodium-warm), the bulkhead's bulb, the beacon, the safe house's lantern and room | `roof_0` (2048), `roof_1` (1024) | `lightmap`, `lightmap_intensity` |

The backdrop's moon is in the same place, so the roof's shadows fall away from it. Baked in Cycles on the GPU, 1024 samples, diffuse direct and indirect, OIDN-denoised: page 0 at 51 px/m (tar 41, the bulkhead's inside 18), page 1 at 44 px/m (iron and dark metal 22). Faces never seen are dropped before the bake (the slab's underside, the parapet's and the bulkhead's outsides below the roof, faces pressed into a collider).

`Lamp_Emit` (the wall packs' lenses, the bulb) is exported at strength 6 and switched by the page; the beacon (`Beacon_Emit`) is its own material and stays on.

There is no day bake: the brief asks for the roof at night. The day backdrop exists for when the roof gets a day set (a sun bake into `lightmap`, the night one moving to `lightmap_night`, as the lobby does).

## Brightness, as the page shows it

As floor 3 (`docs/renders/floor_3/README.md`): texel = G L / (C + G L), `lightmap_intensity` = pi C; here G = 50, C = 1.5 (a moonlit roof needs more lift than a lit corridor). Measured with the brief's `lab_display.py`:

| Material | m2 | Map | `lightmap_intensity` | p50 | p90 | p99 | clipped |
|---|---|---|---|---|---|---|---|
| `Roof_Gravel` | 506.4 | `roof_0` | 4.7124 | 0.068 | 0.141 | 0.235 | 0.00% |
| `Brick` | 124.8 | `roof_0` | 4.7124 | 0.183 | 0.301 | 0.463 | 0.00% |
| `Coping` | 122.4 | `roof_0` | 4.7124 | 0.070 | 0.202 | 0.401 | 0.00% |
| `Roof_Tar` | 109.5 | `roof_0` | 4.7124 | 0.007 | 0.016 | 0.051 | 0.00% |
| `SH_Outside` | 103.9 | `roof_0` | 4.7124 | 0.156 | 0.180 | 0.191 | 0.00% |
| `Stair_Wall` | 80.8 | `roof_0` | 4.7124 | 0.123 | 0.243 | 0.342 | 0.00% |
| `Roof_Pavers` | 48.2 | `roof_0` | 4.7124 | 0.265 | 0.349 | 0.426 | 0.00% |
| `Steel_Paint` | 46.8 | `roof_1` | 4.7124 | 0.013 | 0.140 | 0.187 | 0.00% |
| `HVAC_Sheet` | 38.2 | `roof_1` | 4.7124 | 0.170 | 0.383 | 0.472 | 0.00% |
| `Stair_Concrete` | 28.8 | `roof_0` | 4.7124 | 0.017 | 0.108 | 0.248 | 0.00% |
| `Steel_Galv` | 25.2 | `roof_1` | 4.7124 | 0.000 | 0.210 | 0.245 | 0.00% |
| `Tank_Wood` | 22.2 | `roof_1` | 4.7124 | 0.007 | 0.122 | 0.188 | 0.00% |
| `Iron_Black` | 14.0 | `roof_1` | 4.7124 | 0.050 | 0.070 | 0.071 | 0.00% |
| `Metal_Dark` | 9.9 | `roof_1` | 4.7124 | 0.077 | 0.124 | 0.164 | 0.00% |
| `Doors` | 4.8 | `roof_1` | 4.7124 | 0.105 | 0.365 | 0.594 | 0.00% |
| `Signs` | 0.1 | `roof_1` | 4.7124 | 0.571 | 0.624 | 0.671 | 0.00% |

The walls read: the parapet's brick p50 0.18, the safe house's outside 0.16, the pavers 0.27. The gravel is darker (0.07): a moonlit roof. Every p90 is under 0.40 (the small STAIRS sign 0.62) and every p99 under 0.68; nothing clips. Low p50s are the tar (black), the steel in the tank's shadow, the bulkhead's stair shaft and its steps (lit only by the bulb).

## The skyline backdrops (R3)

- **Where from:** the roof is the top of the street's apartment tower (`shared/city.js`, `BUILDINGS` `tower`: x -28 to -8, z -30 to -8, 38 m high), so the pictures are taken from the tower's middle (-18, -19) at 38 + 1.55 m, in the street's own axes. The roof itself is not in the scene.
- **The street below:** Hallam Row and its eleven buildings are read from `shared/city.js` (the road, the sidewalks, the lamp posts, each building's footprint, height and colour), so the street the player walks is the one under the roof.
- **The city:** blocks of 88 m (72 m of buildings, 16 m of street), lots of 18 to 36 m, about 33 500 buildings out to 4 km. Low streets round the tower (7 to 13 m, below the roof), rising with distance, high-rises scattered in the city, and a downtown of towers up to about 300 m to the north-north-east (about 1.3 km off): from the roof the skyline rises over the parapet to the north. Every building has a window grid (3 m by 3.4 m) and a facade colour; half have a plant room or a setback crown.
- **Night:** a navy sky warmed low down by the city's glow, a few stars, thin clouds lit from below, the moon (bearing 135, 34 degrees up, drawn larger than life). About one window in ten lit (warm and cool; more in the offices; none at street level), the street lamps of Hallam Row, faint lamp lines down the city's streets, a red beacon on every tower over 110 m.
- **Day:** a clear, hazy sky, the sun in the south-south-west (bearing 200, 38 degrees up), the windows dark glass, the city hazing into blue with distance.
- **Orientation:** the picture's middle column faces north (game -z) and its right-hand side faces east (game +x). Before the renders, the self-check (the parking lot's, `tools/blender/build_parking_lot_backdrop.py` on `claude/blender-parking-lot-backdrop`) renders three glowing markers 400 m out (red east, green north, blue south) and checks their columns: `ORIENT columns of the markers on the horizon row: {'red': 192, 'green': 128, 'blue': 0}`, `ORIENT PASS: middle north (-z), right east (+x)`.
- **Render:** Blender 5.2.1, Cycles on the GPU, 96 samples adaptive, OIDN, Standard view transform, 8-bit PNG, then WebP at the best quality under 1 MB (both q95).

### The manifest line (for the coordinator; not wired here)

The roof's scene entry in the hotel area (`shared/farway.manifest.js`, today a stub listing `roof`) gains the backdrop, as the parking lot's does:

```js
{id: "roof", floorY: 0, files: ["world/roof.glb", "world/roof.json"],
 backdrop: {day: "world/backdrops/roof_day.webp", night: "world/backdrops/roof_night.webp"}},
```

The kit's safe house is drawn from `world/kit/safe_house.glb` at (-8, 0, -5.8), yaw 0. The backdrop shows by the clock only where `setBackdrop` is called (the City); until the hotel has a clock the page shows the day picture, so with this night bake the night one should be the roof's default.

## The layout

The layout is the greybox's (`tools/blender/build_hotel_greybox.py`, `roof()`), with the connector kit placed through `tools/blender/kit_place.py`:

- **The safe house** at (-8, 0, -5.8), yaw 0, replacing the greybox's `SafeHouse` shell, the `SH_*` boxes, `decor_Respawn_Pad`, the zone and the six spots: 13 `SH_*_roof` colliders, `Zone_safe_safe_house_roof`, `Marker_Door_roof` (Entrance, inside the door), and the six spots `Spot_shop_1_roof`, `Spot_stash_1_roof`, `Spot_save_1_roof`, `Spot_craft_1_roof`, `Spot_respawn_1_roof`, `Spot_locker_1_roof`, each exactly where the greybox had it (the kit's names, given the suffix, as `blender/kit/README.md` says). The counter, stash and locker colliders are the kit's own sizes (within 2 cm of the greybox's), and the save desk is new.
- **The bulkhead's door** is the kit's stair door at (6, 0, 8), yaw -90, keeping the id `floor_3`: the roof is its landing and the bulkhead stays one solid box, so only the door record comes from the kit (1.04 m by 2.12 m, hinge (6.1, 0, 8.52), `closed_yaw_deg` 90, `swing_deg` -90, `kind: stair door`); the opening in the art is the kit's 1.1 m. It opens into the bulkhead.
- **Unchanged:** the roof's slab, the parapet, the bulkhead, the two HVAC units and the water tank (each piece of art fills its box), the link `floor_3` and the spawn, the puzzle's spot at (0, 0, 0).

## Checks

```
python tools/blender/build_hotel_greybox.py --check .            GATES PASS
export_scene.py (the .blend) == build_hotel_greybox.py --preview   identical
check_layout (Art and the kit's stand-ins)                        PASS: 25 of 25 checks passed
node tools/worlddoc.mjs check world/roof.json                     OK: 22 colliders, 1 doors, 2 markers, 1 links, 1 zones, 7 spots, 0 errors, 1 warnings
                                                                  (warning: link floor_3: the manifest has no link from this door yet)
glb_inspect --budget tris=300000,mb=8                             pass: 5 268 triangles; pass: 2.02 MB (2.12 MB on disk); 18 meshes (18 draw calls)
backdrop orientation self-check                                   ORIENT PASS: middle north (-z), right east (+x)
node --test shared/*.test.js                                      297 pass, 0 fail
```

## Sources and licences

| Map | Used for | Source | Author | Licence |
|---|---|---|---|---|
| `factory_brick`: diffuse, 1k (`blender/textures/factory_floor/brick_diff.jpg`) | the parapet, the bulkhead | https://polyhaven.com/a/factory_brick | Rob Tuytel | CC0 1.0 |
| `concrete_floor_02`: diffuse, 1k (`blender/textures/kit/`) | the coping, the bulkhead's lip and stairs, the dish | https://polyhaven.com/a/concrete_floor_02 | Rob Tuytel | CC0 1.0 |
| `plastered_wall_04`: diffuse, 1k (`blender/textures/kit/`) | the safe house's outside (`SH_Outside`, the kit's tint) | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel | CC0 1.0 |
| `beige_wall_001`: diffuse, 1k (`blender/textures/kit/`) | the bulkhead's stair shaft | https://polyhaven.com/a/beige_wall_001 | Dimitrios Savva (photography), Rico Cilliers (processing) | CC0 1.0 |
| `painted_metal_shutter`: diffuse, 1k (`blender/textures/kit/`) | the steel: the tank's stand, the door frame, galvanised parts | https://polyhaven.com/a/painted_metal_shutter | Charlotte Baglioni, Dario Barresi, Rico Cilliers | CC0 1.0 |
| `corrugated_iron`: diffuse, 1k (`blender/textures/factory_floor/roof_sheet_diff.jpg`) | the HVAC units' sides | https://polyhaven.com/a/corrugated_iron | Dimitrios Savva (photography), Jenelle van Heerden (processing) | CC0 1.0 |
| `dark_wood`: diffuse, 1k (`blender/textures/apartment/`) | the water tank's staves | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |
| The gravel, the tar, the pavers, the door and its plate, the signs | as named | drawn by `build_hotel_floor3_roof.py` (numpy, seeded) | this repo | CC0 1.0 |
| The skyline backdrops | `world/backdrops/roof_*.webp` | made by `build_roof_backdrop.py`: seeded numpy and Blender's own shader nodes; no image, model or HDRI | this repo | CC0 1.0 |

The seven maps were already in the repo and are read where they are; nothing was downloaded or bought, and no Meshy or Higgsfield model is used. The kit's safe house (a stand-in here) is the kit's own, `blender/kit/README.md`.

## Rebuild

```
blender -b --factory-startup --python tools/blender/build_roof_backdrop.py -- --stage backdrops --work work/backdrop --bd-samples 96
python tools/blender/build_roof_backdrop.py --stage pack-backdrops --work work/backdrop
blender -b --factory-startup --python tools/blender/build_hotel_floor3_roof.py -- --scene roof --stage art,bake,export --samples 1024
blender -b blender/scenes/roof.blend --python tools/blender/build_hotel_floor3_roof.py -- --scene roof --stage render --render-samples 160
python tools/blender/pack_scene.py roof --work work/roof
```

The backdrop goes first: the roof's stills show it behind the roof (camera rays only; the bake sees the glow alone). The backdrop's own scene is not saved: it holds nothing the script does not rebuild the same (every random draw is seeded).

## For the coordinator

- **Manifest:** the line above. The link `floor_3` meets floor 3's `roof` (the greybox's PAIRS).
- **The safe house:** draw `world/kit/safe_house.glb` at (-8, 0, -5.8), yaw 0, with its own lightmap (`kit_safe_house_0`). This scene's `SH_Outside` covers its outside 1 cm proud, so nothing in the kit needs hiding; if the page would rather hide the kit's `SH_Outside` on the roof, nothing here changes.
- **The bulkhead's door** is `kind: stair door`; its link takes you down to floor 3, so a lit passage behind it is not needed.

## Open

- No day bake (see "Light").
- The greybox's roof plan and still (`docs/renders/hotel_greybox/`) still show the plain safe-house shell and the 0.94 m door.
