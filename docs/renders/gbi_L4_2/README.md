# `gbi_L4_2`: room sets

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L4_2.glb: 2.23 MB (2230180 bytes), 33117 triangles, 33 primitives (draw calls), 32 materials, 13 images, 33 nodes
- lightmaps: gbi_L4_2_0.webp 233 KB, gbi_L4_2_1.webp 385 KB, gbi_L4_2_2.webp 234 KB, gbi_L4_2_3.webp 421 KB; total 1.27 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L4_2_0` | day | shell 2048 | 18.8 px/m | 2.3124 | 40 | 512 |
| `gbi_L4_2_1` | day | props 2048 | 33.8 px/m | 2.5698 | 88 | 512 |
| `gbi_L4_2_2` | night | shell 2048 | 18.8 px/m | 0.3204 | 56 | 512 |
| `gbi_L4_2_3` | night | props 2048 | 33.8 px/m | 0.1803 | 123 | 512 |

**Day** (`lightmap`; gain 0.7092, walls aimed at p50 0.5)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L4` | 2567.4 | 0.018 | 0.022 | 0.024 |  |
| `M_D_floor_L4` | 2449.3 | 0.225 | 0.367 | 0.858 |  |
| `M_D_wall_L4` | 1653.8 | 0.487 | 0.678 | 0.970 | 0.97 |
| `M_GBI_kit` | 187.9 | 0.368 | 0.594 | 0.970 | 0.94 |
| `M_Fixture_Housing` | 156.8 | 0.880 | 0.880 | 0.880 | 0.78 |
| `M_GBI_wood` | 66.0 | 0.028 | 0.300 | 0.400 |  |
| `M_GBI_textile` | 61.0 | 0.000 | 0.363 | 0.690 |  |
| `M_GBI_accent_5` | 40.4 | 0.422 | 0.561 | 0.622 |  |
| `M_GBI_accent_1` | 40.0 | 0.231 | 0.279 | 0.303 |  |
| `M_GBI_accent_3` | 40.0 | 0.306 | 0.376 | 0.412 |  |
| `M_GBI_accent_4` | 40.0 | 0.117 | 0.147 | 0.158 |  |
| `M_U_blue` | 38.3 | 0.128 | 0.183 | 0.460 |  |
| `sofa_02` | 34.7 | 0.002 | 0.009 | 0.024 |  |
| `M_U_rug_blue` | 24.9 | 0.334 | 0.464 | 0.475 |  |
| `M_GBI_accent_2` | 20.0 | 0.384 | 0.483 | 0.505 |  |
| `M_GBI_textile_dark` | 19.6 | 0.035 | 0.095 | 0.099 |  |
| `M_U_rug_red` | 17.3 | 0.419 | 0.599 | 0.625 |  |
| `M_U_rug_grey` | 15.1 | 0.356 | 0.474 | 0.495 |  |
| `M_GBI_tape` | 9.7 | 0.027 | 0.880 | 0.898 | 0.86 |
| `coffee_table_round_01` | 9.4 | 0.123 | 0.554 | 0.602 |  |
| `M_X_dark` | 9.3 | 0.038 | 0.038 | 0.038 |  |
| `M_U_arrow` | 8.6 | 0.000 | 0.876 | 0.970 | 0.75 |
| `M_U_yellow` | 6.9 | 0.382 | 0.415 | 0.431 |  |
| `M_GBI_frame` | 5.3 | 0.000 | 0.019 | 0.022 |  |
| `M_GBI_canvas` | 4.1 | 0.716 | 0.801 | 0.843 |  |
| `M_X_white` | 2.4 | 0.335 | 0.633 | 0.970 | 0.69 |
| `M_X_steel` | 0.2 | 0.000 | 0.294 | 0.970 | 0.75 |

**Night** (`lightmap_night`; gain 3.4091, walls aimed at p50 0.15)

| Material | m2 | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L4` | 2567.4 | 0.009 | 0.013 | 0.023 |  |
| `M_D_floor_L4` | 2449.3 | 0.104 | 0.210 | 0.464 |  |
| `M_D_wall_L4` | 1653.8 | 0.150 | 0.374 | 0.752 |  |
| `M_GBI_kit` | 187.9 | 0.246 | 0.530 | 0.839 |  |
| `M_Fixture_Housing` | 156.8 | 0.001 | 0.132 | 0.381 |  |
| `M_GBI_wood` | 66.0 | 0.004 | 0.064 | 0.141 |  |
| `M_GBI_textile` | 61.0 | 0.000 | 0.058 | 0.178 |  |
| `M_GBI_accent_5` | 40.4 | 0.111 | 0.198 | 0.217 |  |
| `M_GBI_accent_1` | 40.0 | 0.066 | 0.120 | 0.125 |  |
| `M_GBI_accent_3` | 40.0 | 0.076 | 0.157 | 0.160 |  |
| `M_GBI_accent_4` | 40.0 | 0.024 | 0.054 | 0.061 |  |
| `M_U_blue` | 38.3 | 0.040 | 0.054 | 0.077 |  |
| `sofa_02` | 34.7 | 0.001 | 0.004 | 0.013 |  |
| `M_U_rug_blue` | 24.9 | 0.056 | 0.207 | 0.225 |  |
| `M_GBI_accent_2` | 20.0 | 0.070 | 0.131 | 0.170 |  |
| `M_GBI_textile_dark` | 19.6 | 0.004 | 0.012 | 0.015 |  |
| `M_U_rug_red` | 17.3 | 0.075 | 0.281 | 0.292 |  |
| `M_U_rug_grey` | 15.1 | 0.047 | 0.206 | 0.223 |  |
| `M_GBI_tape` | 9.7 | 0.011 | 0.371 | 0.385 |  |
| `coffee_table_round_01` | 9.4 | 0.055 | 0.237 | 0.269 |  |
| `M_X_dark` | 9.3 | 0.013 | 0.014 | 0.014 |  |
| `M_U_arrow` | 8.6 | 0.000 | 0.389 | 0.459 |  |
| `M_U_yellow` | 6.9 | 0.128 | 0.163 | 0.174 |  |
| `M_GBI_frame` | 5.3 | 0.000 | 0.005 | 0.009 |  |
| `M_GBI_canvas` | 4.1 | 0.159 | 0.352 | 0.359 |  |
| `M_X_white` | 2.4 | 0.361 | 0.538 | 0.584 |  |
| `M_X_steel` | 0.2 | 0.000 | 0.093 | 0.318 |  |
