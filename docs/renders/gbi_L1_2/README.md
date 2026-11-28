# `gbi_L1_2`: Cubicle farm

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L1_2.glb: 1.13 MB (1125424 bytes), 11120 triangles, 20 primitives (draw calls), 15 materials, 5 images, 17 nodes
- lightmaps: gbi_L1_2_0.webp 282 KB, gbi_L1_2_1.webp 452 KB, gbi_L1_2_2.webp 290 KB, gbi_L1_2_3.webp 476 KB; total 1.50 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L1_2_0` | day | shell 2048 | 20.4 px/m | 2.1412 | 43 | 512 |
| `gbi_L1_2_1` | day | props 2048 | 28.2 px/m | 2.704 | 49 | 512 |
| `gbi_L1_2_2` | night | shell 2048 | 20.4 px/m | 0.669 | 51 | 512 |
| `gbi_L1_2_3` | night | props 2048 | 28.2 px/m | 0.6094 | 30 | 512 |

**Day** (`lightmap`; gain 0.6696, walls aimed at p50 0.45)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L1` | 2491.6 | 0.321 | 0.411 | 0.439 |  |
| `M_D_floor_L1` | 2468.5 | 0.360 | 0.567 | 0.770 |  |
| `M_D_wall_L1` | 754.4 | 0.450 | 0.612 | 0.880 |  |
| `M_GBI_fabric` | 619.1 | 0.087 | 0.106 | 0.116 |  |
| `M_Fixture_Housing` | 274.1 | 0.880 | 0.880 | 0.880 | 0.78 |
| `M_X_steel` | 163.7 | 0.087 | 0.700 | 0.926 |  |
| `M_GBI_kit` | 103.5 | 0.381 | 0.568 | 0.970 | 0.94 |
| `M_GBI_furn_L1` | 99.1 | 0.024 | 0.161 | 0.167 |  |
| `M_D_door` | 13.8 | 0.263 | 0.312 | 0.369 |  |
| `M_X_white` | 2.0 | 0.212 | 0.356 | 0.970 | 0.62 |

**Night** (`lightmap_night`; gain 1.2931, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L1` | 2491.6 | 0.143 | 0.210 | 0.254 |  |
| `M_D_floor_L1` | 2468.5 | 0.160 | 0.291 | 0.416 |  |
| `M_D_wall_L1` | 754.4 | 0.150 | 0.352 | 0.633 |  |
| `M_GBI_fabric` | 619.1 | 0.031 | 0.065 | 0.080 |  |
| `M_Fixture_Housing` | 274.1 | 0.037 | 0.489 | 0.489 |  |
| `M_X_steel` | 163.7 | 0.030 | 0.301 | 0.415 |  |
| `M_GBI_kit` | 103.5 | 0.173 | 0.249 | 0.510 |  |
| `M_GBI_furn_L1` | 99.1 | 0.008 | 0.043 | 0.049 |  |
| `M_D_door` | 13.8 | 0.074 | 0.166 | 0.232 |  |
| `M_X_white` | 2.0 | 0.368 | 0.628 | 0.749 |  |
