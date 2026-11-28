# `gbi_L2_4`: Split halls

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L2_4.glb: 0.85 MB (846476 bytes), 7744 triangles, 21 primitives (draw calls), 15 materials, 5 images, 18 nodes
- lightmaps: gbi_L2_4_0.webp 174 KB, gbi_L2_4_1.webp 211 KB, gbi_L2_4_2.webp 176 KB, gbi_L2_4_3.webp 353 KB; total 0.91 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L2_4_0` | day | shell 2048 | 20.4 px/m | 1.6747 | 32 | 512 |
| `gbi_L2_4_1` | day | props 2048 | 60.5 px/m | 3.5378 | 36 | 512 |
| `gbi_L2_4_2` | night | shell 2048 | 20.4 px/m | 0.4863 | 33 | 512 |
| `gbi_L2_4_3` | night | props 2048 | 60.5 px/m | 0.1258 | 37 | 512 |

**Day** (`lightmap`; gain 3.1915, walls aimed at p50 0.45)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L2` | 2557.2 | 0.108 | 0.130 | 0.218 |  |
| `M_D_floor_L2` | 2524.3 | 0.125 | 0.326 | 0.600 |  |
| `M_D_wall_L2` | 1086.7 | 0.449 | 0.682 | 0.757 |  |
| `M_Fixture_Housing` | 257.0 | 0.880 | 0.880 | 0.880 | 0.13 |
| `M_GBI_furn_L2` | 94.0 | 0.296 | 0.879 | 0.954 | 0.60 |
| `M_GBI_kit` | 93.0 | 0.379 | 0.723 | 0.861 |  |
| `M_X_steel` | 69.7 | 0.187 | 0.875 | 0.969 | 0.56 |
| `M_D_door` | 13.8 | 0.656 | 0.880 | 0.942 | 0.97 |
| `M_X_dark` | 3.0 | 0.077 | 0.111 | 0.172 |  |
| `M_X_white` | 2.0 | 0.043 | 0.140 | 0.970 | 0.09 |

**Night** (`lightmap_night`; gain 7.8947, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L2` | 2557.2 | 0.055 | 0.081 | 0.166 |  |
| `M_D_floor_L2` | 2524.3 | 0.056 | 0.179 | 0.358 |  |
| `M_D_wall_L2` | 1086.7 | 0.153 | 0.276 | 0.716 |  |
| `M_Fixture_Housing` | 257.0 | 0.007 | 0.616 | 0.616 |  |
| `M_GBI_furn_L2` | 94.0 | 0.139 | 0.239 | 0.246 |  |
| `M_GBI_kit` | 93.0 | 0.129 | 0.615 | 0.967 | 0.90 |
| `M_X_steel` | 69.7 | 0.117 | 0.477 | 0.606 |  |
| `M_D_door` | 13.8 | 0.217 | 0.326 | 0.345 |  |
| `M_X_dark` | 3.0 | 0.022 | 0.027 | 0.029 |  |
| `M_X_white` | 2.0 | 0.698 | 0.882 | 0.922 | 0.98 |
