# checkpoint_3: dressed and lit (Secret Operations, step 2)

The approach, a white-tiled decontamination tunnel between two doors, the vault with twin guard booths and barriers, and the tier-3 door to the Registrar under its VAULT 3 sign.

Built by `tools/blender/build_secretops_dress.py` around the greybox's layout (`tools/blender/build_secretops_greybox.py`): the layout objects are rebuilt from the same model, so `world/checkpoint_3.json` is the greybox's file, unchanged. The method, the light sets, the removable parts and the sources are in `docs/renders/registrar_hall/README.md` (shared by all 13 scenes).

| File | What it is |
|---|---|
| `world/checkpoint_3.glb` | the art only: 1.40 MB, 5988 triangles, 36 nodes drawn (29 meshes), 29 materials, WebP textures |
| `world/lightmaps/checkpoint_3_0.webp`, `_1.webp` | the normal set (`lightmap`): the shell page and the props page |
| `world/lightmaps/checkpoint_3_2.webp`, `_3.webp` | the alarm set (`lightmap_night`): the same two pages |
| `world/checkpoint_3.json` | the layout, as the greybox wrote it: 49 colliders, 6 doors, 4 cameras, 2 links, 2 zones, 7 spots |
| `blender/scenes/checkpoint_3.blend` | the saved scene (Git LFS): `Art` (Props, Separate, and Arch: one box per shell collider, for the layout check only), `Shell`, `Doors`, `Layout`, the two light collections, `Export` |
| `docs/renders/checkpoint_3/` | `1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg` (normal light), `4_alarm.jpg` (the wide view in the alarm set), `plan.jpg`, `bake.json`, `caps.json` |

![arrival](1_arrival.jpg)
![wide](2_wide.jpg)
![detail](3_detail.jpg)
![alarm](4_alarm.jpg)
![plan](plan.jpg)

## Bake

| Map | Set | Page | Size | px/m | Gain G | Shown gain (caps) |
|---|---|---|---|---|---|---|
| `checkpoint_3_0` | normal | shell | 2048 | 52.0 | 0.29481 | 1.4437 |
| `checkpoint_3_1` | normal | props | 1536 | 48.1 | 0.29481 | 1.4437 |
| `checkpoint_3_2` | alarm | shell | 2048 | 52.0 | 5.33372 | 1.0804 |
| `checkpoint_3_3` | alarm | props | 1536 | 48.1 | 5.33372 | 1.0804 |

Cycles on the rented GPU (GPU), 512 samples, diffuse direct and indirect, OIDN, 8 px margin; 231 s for both sets. Texel = G L / (C + G L) with C = 1.2 and lightmap intensity pi C, G set so the median wall texel shows 0.34 (normal) or 0.26 (alarm) of its light; `caps.json` then scales each set's intensity so the walls show p50 0.3 (normal) or 0.155 (alarm) and caps any material that would pass p90 0.88 or p99 0.97.

## Brightness (`lab_display.py`, as the page shows it)

Normal set:

```
material                m2           map       k    p50    p90    p99     >=1
Wall_Checkpoint      374.6 checkpoint_3_0  5.4426  0.287  0.349  0.407   0.00%
Ceiling_Tile         355.0 checkpoint_3_0  5.4426  0.237  0.270  0.580   0.00%
Floor_Checkpoint     331.2 checkpoint_3_0  5.4426  0.179  0.216  0.243   0.00%
Wall_Tile             40.6 checkpoint_3_0  5.4426  0.418  0.500  0.542   0.00%
Lamp_Housing          31.5 checkpoint_3_1  5.4426  0.668  0.675  0.697   0.00%
Concrete_Prop         27.1 checkpoint_3_1  5.4426  0.070  0.157  0.267   0.00%
Pillar_Paint          20.5 checkpoint_3_1  5.4426  0.289  0.354  0.490   0.00%
Paint_Grey            16.8 checkpoint_3_1  5.4426  0.042  0.071  0.106   0.00%
Door_Frame            15.0 checkpoint_3_1  5.4426  0.109  0.203  0.217   0.00%
Floor_Tile            13.9 checkpoint_3_0  5.4426  0.460  0.507  0.528   0.00%
Laminate              10.2 checkpoint_3_1  5.4426  0.121  0.350  0.363   0.00%
Hazard                 9.3 checkpoint_3_1  5.4426  0.000  0.315  0.373   0.00%
Skirting               8.9 checkpoint_3_1  5.4426  0.017  0.019  0.023   0.00%
Stripe_Red             8.1 checkpoint_3_1  5.4426  0.188  0.220  0.233   0.00%
Steel                  5.6 checkpoint_3_1  5.4426  0.000  0.190  0.219   0.00%
Door_Steel             4.4 checkpoint_3_1  5.4426  0.234  0.279  0.328   0.00%
Door_Keycard           4.4 checkpoint_3_1  5.4426  0.000  0.265  0.273   0.00%
Plastic_Black          3.8 checkpoint_3_1  5.4426  0.001  0.002  0.002   0.00%
Sign_Plate             1.8 checkpoint_3_1  5.4426  0.336  0.428  0.460   0.00%
Notice                 1.0 checkpoint_3_1  5.4426  0.056  0.273  0.285   0.00%
Clock_Face             0.7 checkpoint_3_1  5.4426  0.390  0.478  0.504   0.00%
Cam_Body               0.4 checkpoint_3_1  5.4426  0.092  0.181  0.228   0.00%
Steel_Dark             0.2 checkpoint_3_1  5.4426  0.016  0.028  0.035   0.00%
Plastic_White          0.0 checkpoint_3_1  5.4426  0.038  0.426  0.438   0.00%
```

Alarm set (`lightmap_night`):

```
material                m2           map       k    p50    p90    p99     >=1
Wall_Checkpoint      374.6 checkpoint_3_2  4.0730  0.120  0.295  0.534   0.00%
Ceiling_Tile         355.0 checkpoint_3_2  4.0730  0.107  0.456  0.918   0.29%
Floor_Checkpoint     331.2 checkpoint_3_2  4.0730  0.049  0.109  0.151   0.00%
Wall_Tile             40.6 checkpoint_3_2  4.0730  0.479  0.614  0.919   0.30%
Lamp_Housing          31.5 checkpoint_3_3  4.0730  0.000  0.078  0.488   0.00%
Concrete_Prop         27.1 checkpoint_3_3  4.0730  0.037  0.104  0.212   0.00%
Pillar_Paint          20.5 checkpoint_3_3  4.0730  0.116  0.159  0.179   0.00%
Paint_Grey            16.8 checkpoint_3_3  4.0730  0.001  0.044  0.056   0.00%
Door_Frame            15.0 checkpoint_3_3  4.0730  0.021  0.105  0.174   0.00%
Floor_Tile            13.9 checkpoint_3_2  4.0730  0.510  0.598  0.630   0.00%
Laminate              10.2 checkpoint_3_3  4.0730  0.013  0.110  0.147   0.00%
Hazard                 9.3 checkpoint_3_3  4.0730  0.000  0.196  0.380   0.00%
Skirting               8.9 checkpoint_3_3  4.0730  0.006  0.015  0.020   0.00%
Stripe_Red             8.1 checkpoint_3_3  4.0730  0.117  0.259  0.343   0.00%
Steel                  5.6 checkpoint_3_3  4.0730  0.000  0.080  0.114   0.00%
Door_Steel             4.4 checkpoint_3_3  4.0730  0.097  0.120  0.126   0.00%
Door_Keycard           4.4 checkpoint_3_3  4.0730  0.000  0.152  0.186   0.00%
Plastic_Black          3.8 checkpoint_3_3  4.0730  0.000  0.002  0.003   0.00%
Sign_Plate             1.8 checkpoint_3_3  3.8698  0.494  0.877  0.970   0.00%
Notice                 1.0 checkpoint_3_3  4.0730  0.134  0.636  0.715   0.00%
Clock_Face             0.7 checkpoint_3_3  3.4959  0.007  0.869  0.970   0.00%
Cam_Body               0.4 checkpoint_3_3  4.0730  0.521  0.835  0.883   0.00%
Steel_Dark             0.2 checkpoint_3_3  4.0730  0.039  0.066  0.084   0.00%
Plastic_White          0.0 checkpoint_3_3  4.0730  0.020  0.245  0.261   0.00%
```

## Gates

```
check_layout (Blender): PASS: 54 of 54 checks passed
greybox --check: GATES PASS
layout JSON: IDENTICAL: world/checkpoint_3.json is byte for byte the greybox's
worlddoc: OK world/checkpoint_3.json: 49 colliders, 6 doors, 0 markers, 2 links, 2 zones, 7 spots, 0 errors, 3 warnings
glb_inspect: pass       tris: 5988 triangles, budget 300000 / pass       mb: 1.34 MB, budget 8
privacy: privacy grep: 15 files, 0 with hits
```

