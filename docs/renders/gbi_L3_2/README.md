# `gbi_L3_2`: white gallery

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L3_2.glb: 0.61 MB (605028 bytes), 6448 triangles, 17 primitives (draw calls), 17 materials, 8 images, 16 nodes
- lightmaps: gbi_L3_2_0.webp 245 KB, gbi_L3_2_1.webp 301 KB, gbi_L3_2_2.webp 262 KB, gbi_L3_2_3.webp 367 KB; total 1.17 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L3_2_0` | day | shell 2048 | 20.2 px/m | 1.6179 | 62 | 512 |
| `gbi_L3_2_1` | day | props 2048 | 72.1 px/m | 2.9641 | 91 | 512 |
| `gbi_L3_2_2` | night | shell 2048 | 20.2 px/m | 0.3149 | 98 | 512 |
| `gbi_L3_2_3` | night | props 2048 | 72.1 px/m | 0.2565 | 69 | 512 |

**Day** (`lightmap`; gain 1.0417, walls aimed at p50 0.55)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L3` | 2552.8 | 0.558 | 0.651 | 0.710 |  |
| `M_D_floor_L3` | 2479.8 | 0.585 | 0.684 | 0.749 |  |
| `M_D_wall_L3` | 1076.4 | 0.462 | 0.681 | 0.970 | 0.84 |
| `M_GBI_kit` | 177.5 | 0.379 | 0.632 | 0.970 | 0.81 |
| `M_Fixture_Housing` | 114.1 | 0.880 | 0.880 | 0.880 | 0.46 |
| `M_GBI_canvas` | 37.3 | 0.409 | 0.740 | 0.970 | 0.59 |
| `M_GBI_furn_L3` | 29.2 | 0.611 | 0.826 | 0.970 | 0.77 |
| `M_X_dark` | 9.8 | 0.012 | 0.044 | 0.047 |  |
| `M_D_door` | 4.6 | 0.028 | 0.408 | 0.419 |  |
| `M_GBI_tape` | 4.6 | 0.391 | 0.880 | 0.934 | 0.74 |
| `M_X_white` | 2.0 | 0.180 | 0.292 | 0.970 | 0.35 |
| `M_X_steel` | 0.0 | 0.027 | 0.640 | 0.749 |  |

**Night** (`lightmap_night`; gain 2.1739, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L3` | 2552.8 | 0.149 | 0.262 | 0.420 |  |
| `M_D_floor_L3` | 2479.8 | 0.118 | 0.248 | 0.301 |  |
| `M_D_wall_L3` | 1076.4 | 0.149 | 0.309 | 0.464 |  |
| `M_GBI_kit` | 177.5 | 0.112 | 0.411 | 0.490 |  |
| `M_Fixture_Housing` | 114.1 | 0.001 | 0.266 | 0.346 |  |
| `M_GBI_canvas` | 37.3 | 0.116 | 0.333 | 0.448 |  |
| `M_GBI_furn_L3` | 29.2 | 0.148 | 0.315 | 0.356 |  |
| `M_X_dark` | 9.8 | 0.002 | 0.005 | 0.007 |  |
| `M_D_door` | 4.6 | 0.009 | 0.091 | 0.104 |  |
| `M_GBI_tape` | 4.6 | 0.037 | 0.137 | 0.181 |  |
| `M_X_white` | 2.0 | 0.387 | 0.493 | 0.530 |  |
| `M_X_steel` | 0.0 | 0.007 | 0.159 | 0.165 |  |
