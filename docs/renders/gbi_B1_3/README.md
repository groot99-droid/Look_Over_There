# `gbi_B1_3`: Baths

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_B1_3.glb: 0.71 MB (705052 bytes), 6620 triangles, 25 primitives (draw calls), 16 materials, 6 images, 20 nodes
- lightmaps: gbi_B1_3_0.webp 224 KB, gbi_B1_3_1.webp 150 KB, gbi_B1_3_2.webp 232 KB, gbi_B1_3_3.webp 302 KB; total 0.91 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_B1_3_0` | day | shell 2048 | 19.3 px/m | 1.0592 | 57 | 512 |
| `gbi_B1_3_1` | day | props 2048 | 107.5 px/m | 8.9496 | 56 | 512 |
| `gbi_B1_3_2` | night | shell 2048 | 19.3 px/m | 0.3033 | 40 | 512 |
| `gbi_B1_3_3` | night | props 2048 | 107.5 px/m | 0.2807 | 54 | 512 |

**Day** (`lightmap`; gain 2.7778, walls aimed at p50 0.55)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_B1` | 2506.5 | 0.422 | 0.635 | 0.720 |  |
| `M_D_floor_B1` | 2502.5 | 0.399 | 0.831 | 0.949 |  |
| `M_D_wall_B1` | 1715.0 | 0.311 | 0.668 | 0.969 | 0.57 |
| `M_Fixture_Housing` | 129.0 | 0.872 | 0.880 | 0.880 | 0.06 |
| `M_GBI_kit` | 68.4 | 0.629 | 0.879 | 0.969 | 0.74 |
| `M_D_door` | 23.0 | 0.207 | 0.469 | 0.613 |  |
| `M_GBI_vent` | 14.2 | 0.543 | 0.720 | 0.969 | 0.99 |
| `M_X_white` | 2.2 | 0.082 | 0.166 | 0.970 | 0.13 |
| `M_X_steel` | 0.2 | 0.133 | 0.465 | 0.971 | 0.81 |

**Night** (`lightmap_night`; gain 4.2857, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_B1` | 2506.5 | 0.156 | 0.276 | 0.374 |  |
| `M_D_floor_B1` | 2502.5 | 0.109 | 0.326 | 0.404 |  |
| `M_D_wall_B1` | 1715.0 | 0.152 | 0.462 | 0.750 |  |
| `M_Fixture_Housing` | 129.0 | 0.033 | 0.746 | 0.746 |  |
| `M_GBI_kit` | 68.4 | 0.349 | 0.629 | 0.709 |  |
| `M_D_door` | 23.0 | 0.021 | 0.248 | 0.260 |  |
| `M_GBI_vent` | 14.2 | 0.065 | 0.150 | 0.167 |  |
| `M_X_white` | 2.2 | 0.547 | 0.852 | 0.969 | 0.85 |
| `M_X_steel` | 0.2 | 0.015 | 0.309 | 0.495 |  |
