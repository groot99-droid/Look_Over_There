# road: dressed and baked (docs/BLENDER_AREAS.md, "4. The Overworld"; step 2)

The road to the forest, dressed in Blender on the greybox's layout (`claude/blender-overworld-greybox`, draft PR #115), unchanged:
`export_scene.py` writes the same `world/road.json` from the dressed `.blend`. Tone: dreamcore, a long straight road.

| File | What |
|---|---|
| `world/road.glb` | the art (WebP textures, 2.94 MB, 32,079 triangles, 25 draw calls), merged by material |
| `world/lightmaps/road_0.webp` | AO for the ground (Grass, Asphalt): 2048 x 2048, 9.8 px/m, linear grey, TEXCOORD_1 |
| `world/lightmaps/road_1.webp` | AO for everything else baked: 2048 x 2048, 11.1 px/m |
| `blender/scenes/road.blend` | the saved scene (Git LFS): `Art`, `Layout`, `Export` |
| `1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg` | from the lot gap's arrival at 1.6 m looking north; the road from above at 180 m; the forest end with the bright gap and the signpost back |
| `bake.json`, `CHECKS.txt` | the bake's numbers; every gate's output |

Built by `tools/blender/dress_overworld.py -- --scene road`, packed by `python tools/blender/pack_scene.py road --work work/ow_road`.

## What is there

- **The road:** 8 m of blue-grey asphalt, a dashed yellow centre line (3 m dashes every 9 m), white edge lines, 8 cm concrete kerbs.
- **The verges:** pale bright grass with 2,800 little flowers in clumps (four colours), and the hedges as soft rounded boxes, one per
  greybox length.
- **Lamps:** a pastel steel pole and a round head every 40 m, the glowing disc under it `Lamp_Emit` (on from dusk).
- **Three benches** (slats and legs inside each greybox bench), **two signposts** ("TO THE FOREST" at the lot end, "BACK TO THE LOT" at
  the forest end), **two "more to come" facades** on the east side (pink and blue plaster, a painted fake door, `Window_Lit` windows, the
  MORE TO COME sign).
- **The forest end:** four big pastel trees (pink and lilac blob crowns) either side of the gap, and the gap's glow (`Gap_Glow`, a soft
  emissive pink, always on; not one of the page's toggled materials). The page or the forest's backdrop may replace it.

## Light (docs/BLENDER.md R1, AO-only scenes)

As for the tree house: only ambient occlusion is baked (Cycles AO, 512 samples, 2.5 m, OIDN, 8 px margin), and each baked material carries
`aomap` (`world/lightmaps/road_0.webp` or `road_1.webp`), `aomap_intensity` 1.0 and `aomap_colorspace` `linear`. The page keeps them lit.
The ground has a page of its own: a 480 m road is one long strip, so the merged meshes are cut into 40 m pieces before the unwrap
(`chop()`), which lets the islands pack at the outdoor density. Not baked: the flowers, `Lamp_Emit`, `Window_Lit`, `Gap_Glow`.

## Brightness

Base colour x AO (linear), what each lit material shows under a white ambient of 1 before the sun (see the tree house's README for why the
lightmap tool's formula does not apply):

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Grass | 13916.4 | 0.427 | 0.560 | 0.597 |
| Asphalt | 7739.8 | 0.087 | 0.105 | 0.114 |
| Hedge | 4537.4 | 0.225 | 0.301 | 0.352 |
| Concrete | 637.6 | 0.446 | 0.565 | 0.597 |
| Paint_White | 239.6 | 0.000 | 0.781 | 0.781 |
| Leaf_Lilac | 207.1 | 0.744 | 0.852 | 0.889 |
| Bark | 206.0 | 0.222 | 0.279 | 0.314 |
| Leaf_Pink | 203.4 | 0.758 | 0.852 | 0.889 |
| Plaster_Blue | 122.7 | 0.831 | 0.863 | 0.880 |
| Plaster_Pink | 122.7 | 0.768 | 0.807 | 0.831 |
| Line_Yellow | 40.2 | 0.000 | 0.890 | 0.890 |
| Steel | 33.6 | 0.487 | 0.507 | 0.507 |
| More_To_Come | 14.4 | 0.000 | 0.855 | 0.930 |
| Deck | 13.3 | 0.256 | 0.487 | 0.521 |
| Fake_Door | 12.2 | 0.057 | 0.217 | 0.246 |
| Sign_Forest | 2.4 | 0.564 | 0.599 | 0.617 |
| Sign_Lot | 2.4 | 0.564 | 0.601 | 0.617 |

The asphalt is meant dark (p50 0.09); the hedges, the "walls" here, read at 0.23. p50 0 on the painted lines, the sign and the fake doors
is their undersides and backs, which sit on the ground or against the facade and are fully occluded. More_To_Come's 0.21 % at 1 is a few
texels of the sign's lettering edge after WebP; the page's light scales it further.

## Gates (CHECKS.txt has the full output)

- Layout check (run in Blender on the saved scene): 57 of 57 pass (COVER for all 52 colliders but the edge walls, STRAY, CLEAR for both
  links' F spots and arrivals).
- `export_scene.py` writes the same `world/road.json`.
- `build_overworld_greybox.py --check .`: GATES PASS.
- `node tools/worlddoc.mjs check world/road.json`: OK, 0 errors (warnings: the scene is 485 m long, and the links are new).
- `glb_inspect --budget tris=300000,mb=8`: pass (32,079 triangles, 2.94 MB).
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Privacy grep over this scene's files (the `.blend` decompressed): 0 hits.

## Sources and licences

All made here: geometry by `dress_overworld.py`, textures by `overworld_textures.py` (noise and drawing; no downloads). No Meshy, no
Higgsfield, no purchases.

## Open

- The page does not read `aomap` yet; the coordinator wires it.
- The gap's glow is a flat emissive panel, as the greybox's; the forest's own glow (code) or a backdrop may serve better.
- The signs read the same way from both sides, so on the back of each the arrow points the other way along the road.
