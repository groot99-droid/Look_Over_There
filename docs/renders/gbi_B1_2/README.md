# `gbi_B1_2`: Lido

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_B1_2.glb: 0.71 MB (714452 bytes), 6820 triangles, 16 primitives (draw calls), 14 materials, 5 images, 14 nodes
- lightmaps: gbi_B1_2_0.webp 262 KB, gbi_B1_2_1.webp 157 KB, gbi_B1_2_2.webp 270 KB, gbi_B1_2_3.webp 320 KB; total 1.01 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_B1_2_0` | day | shell 2048 | 19.7 px/m | 1.2945 | 38 | 512 |
| `gbi_B1_2_1` | day | props 2048 | 110.2 px/m | 8.9359 | 50 | 512 |
| `gbi_B1_2_2` | night | shell 2048 | 19.7 px/m | 0.3046 | 42 | 512 |
| `gbi_B1_2_3` | night | props 2048 | 110.2 px/m | 0.2488 | 45 | 512 |

**Day** (`lightmap`; gain 1.7241, walls aimed at p50 0.55)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_B1` | 2531.5 | 0.307 | 0.490 | 0.533 |  |
| `M_D_floor_B1` | 2511.4 | 0.417 | 0.607 | 0.689 |  |
| `M_D_wall_B1` | 984.3 | 0.438 | 0.676 | 0.969 | 0.80 |
| `M_Fixture_Housing` | 153.6 | 0.872 | 0.880 | 0.880 | 0.09 |
| `M_GBI_kit` | 49.6 | 0.378 | 0.557 | 0.648 |  |
| `M_D_door` | 9.2 | 0.021 | 0.535 | 0.561 |  |
| `M_X_white` | 2.1 | 0.068 | 0.124 | 0.970 | 0.15 |
| `M_X_steel` | 0.1 | 0.025 | 0.794 | 0.970 | 0.94 |

**Night** (`lightmap_night`; gain 4.2857, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_B1` | 2531.5 | 0.165 | 0.287 | 0.380 |  |
| `M_D_floor_B1` | 2511.4 | 0.090 | 0.318 | 0.400 |  |
| `M_D_wall_B1` | 984.3 | 0.150 | 0.497 | 0.746 |  |
| `M_Fixture_Housing` | 153.6 | 0.002 | 0.661 | 0.661 |  |
| `M_GBI_kit` | 49.6 | 0.142 | 0.355 | 0.600 |  |
| `M_D_door` | 9.2 | 0.014 | 0.244 | 0.255 |  |
| `M_X_white` | 2.1 | 0.600 | 0.863 | 0.972 | 0.96 |
| `M_X_steel` | 0.1 | 0.008 | 0.409 | 0.484 |  |
