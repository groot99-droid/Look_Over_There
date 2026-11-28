# `gbi_L1_3`: Corridor offices

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L1_3.glb: 0.93 MB (928260 bytes), 8770 triangles, 29 primitives (draw calls), 16 materials, 6 images, 23 nodes
- lightmaps: gbi_L1_3_0.webp 304 KB, gbi_L1_3_1.webp 358 KB, gbi_L1_3_2.webp 305 KB, gbi_L1_3_3.webp 422 KB; total 1.39 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L1_3_0` | day | shell 2048 | 18.6 px/m | 2.0668 | 53 | 512 |
| `gbi_L1_3_1` | day | props 2048 | 53.5 px/m | 3.3937 | 52 | 512 |
| `gbi_L1_3_2` | night | shell 2048 | 18.6 px/m | 0.723 | 45 | 512 |
| `gbi_L1_3_3` | night | props 2048 | 53.5 px/m | 0.6217 | 47 | 512 |

**Day** (`lightmap`; gain 0.6608, walls aimed at p50 0.45)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L1` | 2482.9 | 0.341 | 0.434 | 0.487 |  |
| `M_D_floor_L1` | 2477.0 | 0.334 | 0.535 | 0.729 |  |
| `M_D_wall_L1` | 2096.0 | 0.450 | 0.677 | 0.946 |  |
| `M_Fixture_Housing` | 268.7 | 0.880 | 0.880 | 0.880 | 0.63 |
| `M_GBI_furn_L1` | 130.9 | 0.095 | 0.202 | 0.221 |  |
| `M_X_steel` | 79.8 | 0.168 | 0.507 | 0.743 |  |
| `M_GBI_kit` | 63.7 | 0.522 | 0.664 | 0.790 |  |
| `M_D_door` | 27.6 | 0.245 | 0.362 | 0.548 |  |
| `M_GBI_vent` | 14.2 | 0.203 | 0.258 | 0.285 |  |
| `M_X_dark` | 2.4 | 0.018 | 0.030 | 0.040 |  |
| `M_X_white` | 2.2 | 0.225 | 0.396 | 0.970 | 0.68 |

**Night** (`lightmap_night`; gain 1.1278, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L1` | 2482.9 | 0.138 | 0.234 | 0.325 |  |
| `M_D_floor_L1` | 2477.0 | 0.140 | 0.264 | 0.380 |  |
| `M_D_wall_L1` | 2096.0 | 0.150 | 0.396 | 0.602 |  |
| `M_Fixture_Housing` | 268.7 | 0.012 | 0.435 | 0.435 |  |
| `M_GBI_furn_L1` | 130.9 | 0.027 | 0.074 | 0.089 |  |
| `M_X_steel` | 79.8 | 0.064 | 0.253 | 0.362 |  |
| `M_GBI_kit` | 63.7 | 0.220 | 0.416 | 0.545 |  |
| `M_D_door` | 27.6 | 0.118 | 0.185 | 0.224 |  |
| `M_GBI_vent` | 14.2 | 0.045 | 0.084 | 0.092 |  |
| `M_X_dark` | 2.4 | 0.010 | 0.011 | 0.012 |  |
| `M_X_white` | 2.2 | 0.308 | 0.553 | 0.666 |  |
