# `gbi_B1_4`: The drain

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_B1_4.glb: 0.74 MB (742072 bytes), 7200 triangles, 18 primitives (draw calls), 17 materials, 7 images, 17 nodes
- lightmaps: gbi_B1_4_0.webp 243 KB, gbi_B1_4_1.webp 308 KB, gbi_B1_4_2.webp 257 KB, gbi_B1_4_3.webp 337 KB; total 1.15 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_B1_4_0` | day | shell 2048 | 20.4 px/m | 1.3451 | 36 | 512 |
| `gbi_B1_4_1` | day | props 2048 | 48.2 px/m | 2.624 | 20 | 512 |
| `gbi_B1_4_2` | night | shell 2048 | 20.4 px/m | 0.4155 | 32 | 512 |
| `gbi_B1_4_3` | night | props 2048 | 48.2 px/m | 0.4688 | 19 | 512 |

**Day** (`lightmap`; gain 1.4946, walls aimed at p50 0.55)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_B1` | 2536.7 | 0.287 | 0.413 | 0.465 |  |
| `M_D_floor_B1` | 2519.5 | 0.455 | 0.581 | 0.650 |  |
| `M_D_wall_B1` | 926.9 | 0.508 | 0.716 | 0.970 | 0.92 |
| `M_Fixture_Housing` | 163.2 | 0.872 | 0.880 | 0.880 | 0.36 |
| `M_GBI_kit` | 68.4 | 0.462 | 0.654 | 0.715 |  |
| `M_GBI_tape` | 15.3 | 0.368 | 0.880 | 0.942 | 0.59 |
| `M_X_dark` | 14.8 | 0.054 | 0.059 | 0.060 |  |
| `M_D_door` | 4.6 | 0.014 | 0.396 | 0.403 |  |
| `M_X_white` | 2.2 | 0.120 | 0.215 | 0.970 | 0.31 |
| `M_X_steel` | 0.0 | 0.024 | 0.449 | 0.741 |  |

**Night** (`lightmap_night`; gain 2.5862, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_B1` | 2536.7 | 0.120 | 0.180 | 0.232 |  |
| `M_D_floor_B1` | 2519.5 | 0.135 | 0.268 | 0.332 |  |
| `M_D_wall_B1` | 926.9 | 0.150 | 0.366 | 0.559 |  |
| `M_Fixture_Housing` | 163.2 | 0.034 | 0.752 | 0.752 |  |
| `M_GBI_kit` | 68.4 | 0.208 | 0.450 | 0.527 |  |
| `M_GBI_tape` | 15.3 | 0.195 | 0.650 | 0.759 |  |
| `M_X_dark` | 14.8 | 0.022 | 0.027 | 0.029 |  |
| `M_D_door` | 4.6 | 0.009 | 0.186 | 0.198 |  |
| `M_X_white` | 2.2 | 0.363 | 0.791 | 0.971 | 0.84 |
| `M_X_steel` | 0.0 | 0.012 | 0.320 | 0.374 |  |
