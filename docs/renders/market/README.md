# The market (`market`), dressed

The Overworld's market (`docs/BLENDER_AREAS.md` section 4: "Stalls for weapons, gear, food, keycards and cosmetics. `Spot_shop` per stall"), dressed in Blender on the greybox's layout and given an ambient-occlusion bake. Tone: dreamcore, a plastic market square, open and empty, every stall stocked and nobody buying.

| File | What it is |
|---|---|
| `world/market.glb` | the art, art only, merged by material |
| `world/market.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`; equal to `build_overworld_greybox.py --preview`'s (see "The layout") |
| `world/lightmaps/market_0.webp`, `_1.webp` | the AO bake (second UV set, `TEXCOORD_1`, linear): the paving and the hedges (2048), everything standing (2048) |
| `blender/scenes/market.blend` | the saved scene (Git LFS): `Art`, `Play` (empty here), `Layout`, `Export` |
| `blender/textures/overworld_play/` | the textures shared with the playground (generated, own work) |
| `tools/blender/build_overworld_play.py` | the build for the playground and the market (`--scene market`) |
| `docs/renders/market/` | this file, the three review stills, `bake.json` and `brightness.txt` |

## What is in it

- **The square:** grey-cream paving slabs (2 m texture, 1 m slabs with grout) inside the hedge, an arch with a MARKET sign over the west gap (to the lot), its posts standing in the hedge.
- **Five stalls**, each 8 m wide, on the greybox's boxes: timber back and sides, open shelving (two ends, a back panel, four boards), a counter with a timber top, a striped awning (0.5 m stripes in the stall's colour and white) with a scalloped valance hanging at its front, and a sign board with the stall's name (WEAPONS, GEAR, FOOD, KEYCARDS, COSMETICS) from the sign atlas.
- **The goods** (decor_, standing on the shelves' and counters' colliders): toy blasters in dark grey, orange and blue and flat toy swords (weapons); backpacks and helmets, coils of rope (gear); jars, tins, loaves and four crates of fruit on the counter (food); keycards standing in racks in tier colours and a card mat (keycards); bottles and pots in pink, mint and lilac and a mirror (cosmetics).
- **The buy-back kiosk** in the middle: four counters, round posts, a striped green roof and BUY-BACK signs.
- **Four picnic tables** with slatted tops and benches, six lamp posts with round `Lamp_Emit` heads, three "more to come" facades along the east side with MORE TO COME signs.
- **Crates:** six stacks of 0.8 m wooden crates (one or two high) against the back hedges between the stalls, the top ones holding fruit.
- **Flowers** along the hedges.

## Light: ambient occlusion only

As the playground and the other outdoor scenes (`docs/BLENDER.md` R1, AO-only scenes): the baked materials carry `aomap` (`world/lightmaps/market_<n>.webp`) and `aomap_intensity` 1.0 on the second UV set, no `lightmap`; the page keeps them lit by its sun and sky. No day or night set. `Lamp_Emit` at strength 3, switched by the page. Not baked: the lamp heads and the goods and flowers (`Goods_*`).

Baked in Cycles on the rented GPU (`--samples 256`), Cycles' AO bake, OIDN-denoised, 8 px margin, written linear (`bake.json`):

| Map | Size | What | AO distance | px/m | AO p10 / p50 / p90 |
|---|---|---|---|---|---|
| `market_0` | 2048 | the paving and its skirt, the hedges | 1.5 m | 26.8 | 0.31 / 0.99 / 1.00 |
| `market_1` | 2048 | everything standing: stalls, awnings, shelves, counters, kiosk, tables, crates, lamps' posts, facades, signs, the arch | 0.8 m | 19.4 | 0.01 / 0.55 / 1.00 |

## Brightness

Base colour (factor x texture) x AO texel x `aomap_intensity`, area-weighted, max channel: what each material shows under white light of 1. Every colour is held at or under 0.85 per channel.

```
material                m2           map       k    p50    p90    p99     >=1
Paving              3333.6      market_0  1.0000  0.674  0.708  0.721   0.00%
Hedge                965.4      market_0  1.0000  0.257  0.302  0.326   0.00%
Timber               525.6      market_1  1.0000  0.474  0.599  0.623   0.00%
Awning_White         370.6      market_1  1.0000  0.837  0.840  0.840   0.00%
Facade               342.6      market_1  1.0000  0.772  0.787  0.794   0.00%
Shelf_Wood           300.1      market_1  1.0000  0.087  0.283  0.447   0.00%
Counter_Wood         133.9      market_1  1.0000  0.351  0.457  0.490   0.00%
Awning_E              72.7      market_1  1.0000  0.840  0.850  0.850   0.00%
Awning_A              70.4      market_1  1.0000  0.797  0.800  0.800   0.00%
Awning_B              70.4      market_1  1.0000  0.794  0.800  0.800   0.00%
Awning_C              70.4      market_1  1.0000  0.843  0.850  0.850   0.00%
Awning_D              70.4      market_1  1.0000  0.697  0.700  0.700   0.00%
Signs                 53.4      market_1  1.0000  0.784  0.799  0.847   0.06%
Awning_F              48.2      market_1  1.0000  0.640  0.640  0.640   0.00%
Crate_Wood            47.5      market_1  1.0000  0.247  0.550  0.627   0.00%
Steel                 34.8      market_1  1.0000  0.557  0.580  0.580   0.00%
Window                18.4      market_1  1.0000  0.360  0.360  0.360   0.00%
Fake_Door              9.5      market_1  1.0000  0.420  0.420  0.420   0.00%
```

Nothing over 0.85 at p99 (the signs' 0.06 % at 1 are a few texels of the atlas sampled at an edge). The hedges (this scene's walls) read p50 0.26. `Shelf_Wood` reads dark (p50 0.09): the shelving stands under the awning, against the stall's back, between its sides, so its AO is deep; the goods on it are unbaked and read at full colour.

## The layout

`world/market.json` is written by `export_scene.py` from the `.blend` and is equal (parsed) to `build_overworld_greybox.py --preview`'s. It changed from the greybox's on purpose, and only by additions: six crate stacks (`Crates_1` to `Crates_6`, `MARKET_CRATES` in the greybox script) against the back hedges between the stalls, 0.8 m deep, one or two 0.6 m crates high. They are solid, so they need their `COL_` boxes. Nothing moved: 76 colliders (70 before), 1 link, 12 spots; the greybox's gates still pass (no crate is in a corridor).

## Checks

- Layout check (`check_layout.py` on `Art`, the CLEAR points the link's `at` and `arrive`): **PASS, 75 of 75** (70 COVER, 1 STRAY: 67 tall solid meshes each over a collider, 100 decor_ meshes exempt, 2 CLEAR, and the rest).
- `python tools/blender/build_overworld_greybox.py --check . --glb world`: **GATES PASS**.
- `node tools/worlddoc.mjs check world/market.json`: **OK**, 76 colliders, 1 link, 12 spots, 0 errors, 3 warnings (66 m along x; the scene and its link are new to the manifest; as for the greybox).
- `glb_inspect.py world/market.glb --budget tris=300000,mb=8`: **pass**, 74,474 triangles, 3.82 MB (4.01 MB on disk), 33 draw calls (primitives).
- `node --test shared/*.test.js`: 297 of 297 pass.
- Privacy grep over the committed files (the `.blend` decompressed): clean.

## Sources and licences

No third-party asset is used. The textures and the sign atlas (its 5 x 7 pixel font included) are generated by `build_overworld_play.py --stage textures` (numpy), own work; every model is built by the same script.

## Open

- The coordinator wires the manifest; the market's one link is the greybox's.
- The goods are decoration only; the shops' stock is the page's (`Spot_shop` per stall and the kiosk).
