# `gbi_L3_4`: white maze

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L3_4.glb: 0.55 MB (547764 bytes), 5754 triangles, 12 primitives (draw calls), 12 materials, 7 images, 12 nodes
- lightmaps: gbi_L3_4_0.webp 233 KB, gbi_L3_4_1.webp 148 KB, gbi_L3_4_2.webp 236 KB, gbi_L3_4_3.webp 289 KB; total 0.91 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L3_4_0` | day | shell 2048 | 19.2 px/m | 1.5556 | 82 | 512 |
| `gbi_L3_4_1` | day | props 2048 | 134.3 px/m | 8.9292 | 87 | 512 |
| `gbi_L3_4_2` | night | shell 2048 | 19.2 px/m | 0.2921 | 96 | 512 |
| `gbi_L3_4_3` | night | props 2048 | 134.3 px/m | 0.2445 | 71 | 512 |

**Day** (`lightmap`; gain 1.068, walls aimed at p50 0.55)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L3` | 2534.6 | 0.540 | 0.659 | 0.742 |  |
| `M_D_floor_L3` | 2499.1 | 0.568 | 0.670 | 0.732 |  |
| `M_D_wall_L3` | 1703.3 | 0.454 | 0.680 | 0.970 | 0.82 |
| `M_Fixture_Housing` | 114.1 | 0.872 | 0.880 | 0.880 | 0.15 |
| `M_GBI_kit` | 93.0 | 0.359 | 0.754 | 0.970 | 0.88 |
| `M_X_white` | 2.0 | 0.099 | 0.156 | 0.970 | 0.19 |
| `M_GBI_tape` | 0.9 | 0.029 | 0.880 | 0.914 | 0.67 |

**Night** (`lightmap_night`; gain 2.6786, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L3` | 2534.6 | 0.167 | 0.314 | 0.472 |  |
| `M_D_floor_L3` | 2499.1 | 0.131 | 0.284 | 0.344 |  |
| `M_D_wall_L3` | 1703.3 | 0.149 | 0.327 | 0.525 |  |
| `M_Fixture_Housing` | 114.1 | 0.000 | 0.267 | 0.406 |  |
| `M_GBI_kit` | 93.0 | 0.147 | 0.289 | 0.349 |  |
| `M_X_white` | 2.0 | 0.454 | 0.579 | 0.622 |  |
| `M_GBI_tape` | 0.9 | 0.010 | 0.330 | 0.348 |  |
