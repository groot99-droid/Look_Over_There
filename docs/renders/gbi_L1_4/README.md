# `gbi_L1_4`: Conference ring

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L1_4.glb: 0.89 MB (886096 bytes), 8282 triangles, 28 primitives (draw calls), 17 materials, 7 images, 22 nodes
- lightmaps: gbi_L1_4_0.webp 286 KB, gbi_L1_4_1.webp 317 KB, gbi_L1_4_2.webp 295 KB, gbi_L1_4_3.webp 366 KB; total 1.26 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L1_4_0` | day | shell 2048 | 19.2 px/m | 1.9675 | 45 | 512 |
| `gbi_L1_4_1` | day | props 2048 | 51.3 px/m | 3.6195 | 48 | 512 |
| `gbi_L1_4_2` | night | shell 2048 | 19.2 px/m | 0.6872 | 39 | 512 |
| `gbi_L1_4_3` | night | props 2048 | 51.3 px/m | 0.711 | 44 | 512 |

**Day** (`lightmap`; gain 0.7109, walls aimed at p50 0.45)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_floor_L1` | 2500.6 | 0.333 | 0.533 | 0.727 |  |
| `M_D_ceil_L1` | 2499.4 | 0.326 | 0.421 | 0.506 |  |
| `M_D_wall_L1` | 1685.2 | 0.437 | 0.636 | 0.970 | 0.97 |
| `M_Fixture_Housing` | 238.9 | 0.872 | 0.880 | 0.880 | 0.55 |
| `M_GBI_furn_L1` | 195.1 | 0.097 | 0.224 | 0.242 |  |
| `M_X_steel` | 83.7 | 0.144 | 0.518 | 0.624 |  |
| `M_GBI_kit` | 57.4 | 0.069 | 0.371 | 0.428 |  |
| `M_D_door` | 27.6 | 0.229 | 0.340 | 0.575 |  |
| `M_X_dark` | 7.1 | 0.035 | 0.037 | 0.038 |  |
| `M_GBI_tape` | 5.5 | 0.018 | 0.880 | 0.922 | 0.91 |
| `M_X_white` | 2.0 | 0.159 | 0.258 | 0.970 | 0.44 |

**Night** (`lightmap_night`; gain 1.0274, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_floor_L1` | 2500.6 | 0.124 | 0.228 | 0.328 |  |
| `M_D_ceil_L1` | 2499.4 | 0.125 | 0.201 | 0.290 |  |
| `M_D_wall_L1` | 1685.2 | 0.150 | 0.318 | 0.522 |  |
| `M_Fixture_Housing` | 238.9 | 0.050 | 0.453 | 0.453 |  |
| `M_GBI_furn_L1` | 195.1 | 0.027 | 0.081 | 0.094 |  |
| `M_X_steel` | 83.7 | 0.059 | 0.214 | 0.292 |  |
| `M_GBI_kit` | 57.4 | 0.033 | 0.087 | 0.109 |  |
| `M_D_door` | 27.6 | 0.094 | 0.137 | 0.146 |  |
| `M_X_dark` | 7.1 | 0.012 | 0.015 | 0.015 |  |
| `M_GBI_tape` | 5.5 | 0.007 | 0.388 | 0.413 |  |
| `M_X_white` | 2.0 | 0.275 | 0.566 | 0.694 |  |
