# `gbi_L2_3`: Long loop

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L2_3.glb: 0.89 MB (891732 bytes), 8718 triangles, 23 primitives (draw calls), 15 materials, 6 images, 19 nodes
- lightmaps: gbi_L2_3_0.webp 259 KB, gbi_L2_3_1.webp 341 KB, gbi_L2_3_2.webp 226 KB, gbi_L2_3_3.webp 458 KB; total 1.28 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L2_3_0` | day | shell 2048 | 18.0 px/m | 1.5864 | 42 | 512 |
| `gbi_L2_3_1` | day | props 2048 | 43.6 px/m | 2.1956 | 46 | 512 |
| `gbi_L2_3_2` | night | shell 2048 | 18.0 px/m | 0.578 | 34 | 512 |
| `gbi_L2_3_3` | night | props 2048 | 43.6 px/m | 0.1224 | 50 | 512 |

**Day** (`lightmap`; gain 3.1915, walls aimed at p50 0.45)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_floor_L2` | 2510.9 | 0.105 | 0.281 | 0.529 |  |
| `M_D_ceil_L2` | 2510.1 | 0.107 | 0.175 | 0.219 |  |
| `M_D_wall_L2` | 2507.7 | 0.310 | 0.586 | 0.971 | 0.69 |
| `M_Fixture_Housing` | 275.1 | 0.880 | 0.880 | 0.880 | 0.20 |
| `M_D_door` | 18.4 | 0.396 | 0.651 | 0.971 | 0.70 |
| `M_GBI_furn_L2` | 16.4 | 0.507 | 0.881 | 0.941 | 0.86 |
| `M_GBI_tape` | 15.3 | 0.066 | 0.880 | 0.899 | 0.24 |
| `M_X_dark` | 14.8 | 0.131 | 0.137 | 0.137 |  |
| `M_X_steel` | 10.1 | 0.073 | 0.406 | 0.970 | 0.33 |
| `M_X_white` | 2.1 | 0.059 | 0.193 | 0.970 | 0.16 |

**Night** (`lightmap_night`; gain 7.5, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_floor_L2` | 2510.9 | 0.049 | 0.179 | 0.360 |  |
| `M_D_ceil_L2` | 2510.1 | 0.060 | 0.131 | 0.265 |  |
| `M_D_wall_L2` | 2507.7 | 0.119 | 0.515 | 0.971 | 0.80 |
| `M_Fixture_Housing` | 275.1 | 0.005 | 0.569 | 0.569 |  |
| `M_D_door` | 18.4 | 0.164 | 0.307 | 0.316 |  |
| `M_GBI_furn_L2` | 16.4 | 0.099 | 0.164 | 0.181 |  |
| `M_GBI_tape` | 15.3 | 0.016 | 0.676 | 0.709 |  |
| `M_X_dark` | 14.8 | 0.024 | 0.026 | 0.026 |  |
| `M_X_steel` | 10.1 | 0.075 | 0.437 | 0.570 |  |
| `M_X_white` | 2.1 | 0.677 | 0.826 | 0.872 |  |
