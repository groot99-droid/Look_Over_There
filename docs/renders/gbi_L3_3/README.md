# `gbi_L3_3`: colonnade

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L3_3.glb: 0.64 MB (643336 bytes), 6966 triangles, 15 primitives (draw calls), 14 materials, 5 images, 14 nodes
- lightmaps: gbi_L3_3_0.webp 280 KB, gbi_L3_3_1.webp 189 KB, gbi_L3_3_2.webp 283 KB, gbi_L3_3_3.webp 371 KB; total 1.12 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L3_3_0` | day | shell 2048 | 18.9 px/m | 1.5793 | 107 | 512 |
| `gbi_L3_3_1` | day | props 2048 | 102.8 px/m | 8.9386 | 95 | 512 |
| `gbi_L3_3_2` | night | shell 2048 | 18.9 px/m | 0.2679 | 117 | 512 |
| `gbi_L3_3_3` | night | props 2048 | 102.8 px/m | 0.2277 | 126 | 512 |

**Day** (`lightmap`; gain 0.9106, walls aimed at p50 0.55)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L3` | 2523.8 | 0.492 | 0.560 | 0.586 |  |
| `M_D_floor_L3` | 2521.9 | 0.497 | 0.585 | 0.639 |  |
| `M_D_wall_L3` | 1599.9 | 0.550 | 0.707 | 0.940 |  |
| `M_Fixture_Housing` | 119.4 | 0.872 | 0.880 | 0.880 | 0.17 |
| `M_D_trim` | 49.5 | 0.317 | 0.497 | 0.770 |  |
| `M_D_door` | 4.6 | 0.025 | 0.389 | 0.398 |  |
| `M_X_white` | 2.1 | 0.125 | 0.200 | 0.970 | 0.27 |
| `M_GBI_tape` | 1.0 | 0.022 | 0.845 | 0.900 |  |
| `M_X_steel` | 0.0 | 0.027 | 0.624 | 0.711 |  |

**Night** (`lightmap_night`; gain 4.0541, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L3` | 2523.8 | 0.217 | 0.466 | 0.663 |  |
| `M_D_floor_L3` | 2521.9 | 0.168 | 0.390 | 0.477 |  |
| `M_D_wall_L3` | 1599.9 | 0.151 | 0.484 | 0.729 |  |
| `M_Fixture_Housing` | 119.4 | 0.001 | 0.284 | 0.572 |  |
| `M_D_trim` | 49.5 | 0.133 | 0.262 | 0.431 |  |
| `M_D_door` | 4.6 | 0.016 | 0.171 | 0.192 |  |
| `M_X_white` | 2.1 | 0.621 | 0.808 | 0.877 |  |
| `M_GBI_tape` | 1.0 | 0.000 | 0.004 | 0.006 |  |
| `M_X_steel` | 0.0 | 0.010 | 0.342 | 0.359 |  |
