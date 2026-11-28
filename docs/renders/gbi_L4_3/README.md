# `gbi_L4_3`: stockroom

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L4_3.glb: 1.28 MB (1277612 bytes), 13330 triangles, 24 primitives (draw calls), 23 materials, 10 images, 23 nodes
- lightmaps: gbi_L4_3_0.webp 262 KB, gbi_L4_3_1.webp 556 KB, gbi_L4_3_2.webp 256 KB, gbi_L4_3_3.webp 578 KB; total 1.65 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L4_3_0` | day | shell 2048 | 20.8 px/m | 1.9179 | 32 | 512 |
| `gbi_L4_3_1` | day | props 2048 | 11.7 px/m | 2.7362 | 56 | 512 |
| `gbi_L4_3_2` | night | shell 2048 | 20.8 px/m | 0.2795 | 43 | 512 |
| `gbi_L4_3_3` | night | props 2048 | 11.7 px/m | 0.2524 | 72 | 512 |

**Day** (`lightmap`; gain 0.6667, walls aimed at p50 0.5)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L4` | 2573.5 | 0.017 | 0.021 | 0.040 |  |
| `M_D_floor_L4` | 2508.5 | 0.184 | 0.298 | 0.696 |  |
| `M_D_wall_L4` | 905.5 | 0.500 | 0.633 | 0.696 |  |
| `M_D_trim` | 812.7 | 0.211 | 0.679 | 0.928 |  |
| `M_GBI_furn_L4` | 529.4 | 0.230 | 0.582 | 0.970 | 0.62 |
| `M_GBI_card` | 507.8 | 0.172 | 0.393 | 0.546 |  |
| `M_U_bluepaint` | 284.7 | 0.276 | 0.508 | 0.808 |  |
| `M_GBI_wood` | 219.4 | 0.001 | 0.232 | 0.404 |  |
| `M_Fixture_Housing` | 163.2 | 0.872 | 0.880 | 0.880 | 0.78 |
| `M_GBI_kit` | 103.4 | 0.433 | 0.567 | 0.600 |  |
| `M_GBI_shutter` | 40.5 | 0.287 | 0.380 | 0.423 |  |
| `M_U_yellow` | 35.3 | 0.572 | 0.652 | 0.707 |  |
| `M_U_arrow` | 13.0 | 0.000 | 0.835 | 0.970 | 0.77 |
| `M_X_dark` | 7.8 | 0.013 | 0.027 | 0.028 |  |
| `M_D_door` | 4.6 | 0.022 | 0.265 | 0.276 |  |
| `M_X_white` | 2.2 | 0.432 | 0.626 | 0.970 | 0.78 |
| `M_GBI_tape` | 1.0 | 0.704 | 0.880 | 0.909 | 0.96 |
| `M_X_steel` | 0.0 | 0.000 | 0.005 | 0.378 |  |

**Night** (`lightmap_night`; gain 3.3333, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L4` | 2573.5 | 0.008 | 0.015 | 0.027 |  |
| `M_D_floor_L4` | 2508.5 | 0.075 | 0.176 | 0.388 |  |
| `M_D_wall_L4` | 905.5 | 0.150 | 0.299 | 0.378 |  |
| `M_D_trim` | 812.7 | 0.091 | 0.355 | 0.465 |  |
| `M_GBI_furn_L4` | 529.4 | 0.130 | 0.508 | 0.734 |  |
| `M_GBI_card` | 507.8 | 0.055 | 0.238 | 0.325 |  |
| `M_U_bluepaint` | 284.7 | 0.086 | 0.310 | 0.470 |  |
| `M_GBI_wood` | 219.4 | 0.000 | 0.113 | 0.263 |  |
| `M_Fixture_Housing` | 163.2 | 0.003 | 0.089 | 0.522 |  |
| `M_GBI_kit` | 103.4 | 0.075 | 0.572 | 0.701 |  |
| `M_GBI_shutter` | 40.5 | 0.122 | 0.173 | 0.205 |  |
| `M_U_yellow` | 35.3 | 0.273 | 0.490 | 0.523 |  |
| `M_U_arrow` | 13.0 | 0.000 | 0.240 | 0.707 |  |
| `M_X_dark` | 7.8 | 0.003 | 0.008 | 0.009 |  |
| `M_D_door` | 4.6 | 0.016 | 0.149 | 0.160 |  |
| `M_X_white` | 2.2 | 0.549 | 0.778 | 0.799 |  |
| `M_GBI_tape` | 1.0 | 0.099 | 0.241 | 0.349 |  |
| `M_X_steel` | 0.0 | 0.000 | 0.006 | 0.199 |  |
