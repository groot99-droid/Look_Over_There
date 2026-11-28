# `gbi_L2_2`: Door grid

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L2_2.glb: 1.01 MB (1010280 bytes), 9300 triangles, 62 primitives (draw calls), 15 materials, 7 images, 38 nodes
- lightmaps: gbi_L2_2_0.webp 254 KB, gbi_L2_2_1.webp 288 KB, gbi_L2_2_2.webp 261 KB, gbi_L2_2_3.webp 337 KB; total 1.14 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L2_2_0` | day | shell 2048 | 17.9 px/m | 1.3886 | 32 | 512 |
| `gbi_L2_2_1` | day | props 2048 | 64.2 px/m | 1.8117 | 108 | 512 |
| `gbi_L2_2_2` | night | shell 2048 | 17.9 px/m | 0.3924 | 47 | 512 |
| `gbi_L2_2_3` | night | props 2048 | 64.2 px/m | 0.299 | 149 | 512 |

**Day** (`lightmap`; gain 5.1136, walls aimed at p50 0.45)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L2` | 2451.5 | 0.139 | 0.198 | 0.267 |  |
| `M_D_floor_L2` | 2408.3 | 0.135 | 0.382 | 0.731 |  |
| `M_D_wall_L2` | 2220.4 | 0.266 | 0.556 | 0.971 | 0.59 |
| `M_GBI_kit` | 211.0 | 0.157 | 0.738 | 0.968 | 0.91 |
| `M_Fixture_Housing` | 207.9 | 0.880 | 0.880 | 0.880 | 0.15 |
| `M_D_door` | 110.4 | 0.394 | 0.780 | 0.969 | 0.50 |
| `M_GBI_card` | 45.4 | 0.265 | 0.833 | 0.969 | 0.35 |
| `M_GBI_vent` | 14.2 | 0.521 | 0.785 | 0.969 | 0.65 |
| `M_X_white` | 2.1 | 0.056 | 0.471 | 0.970 | 0.11 |
| `M_X_steel` | 1.0 | 0.160 | 0.629 | 0.970 | 0.25 |

**Night** (`lightmap_night`; gain 9.375, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L2` | 2451.5 | 0.062 | 0.105 | 0.217 |  |
| `M_D_floor_L2` | 2408.3 | 0.052 | 0.173 | 0.347 |  |
| `M_D_wall_L2` | 2220.4 | 0.146 | 0.498 | 0.969 | 0.99 |
| `M_GBI_kit` | 211.0 | 0.073 | 0.376 | 0.715 |  |
| `M_Fixture_Housing` | 207.9 | 0.018 | 0.882 | 0.882 | 0.51 |
| `M_D_door` | 110.4 | 0.424 | 0.685 | 0.939 |  |
| `M_GBI_card` | 45.4 | 0.234 | 0.748 | 0.969 | 0.99 |
| `M_GBI_vent` | 14.2 | 0.124 | 0.326 | 0.362 |  |
| `M_X_white` | 2.1 | 0.527 | 0.879 | 0.954 | 0.36 |
| `M_X_steel` | 1.0 | 0.156 | 0.659 | 0.971 | 0.56 |
