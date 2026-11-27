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
