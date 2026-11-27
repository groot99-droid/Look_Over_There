# `gbi_L4_1`: showroom floor

Dressed and lit; how it is built, the light, the materials and the sources: `docs/renders/gbi_dress/README.md`. Gate outputs: `CHECKS.txt` here. Stills: `1_arrival.jpg` (where you arrive, day), `4_night.jpg` (the same view at night), `2_wide.jpg`, `3_detail.jpg`, `plan.jpg` (from above, ceiling hidden, north up).

- GLB gbi_L4_1.glb: 1.02 MB (1023832 bytes), 10380 triangles, 26 primitives (draw calls), 22 materials, 11 images, 24 nodes
- lightmaps: gbi_L4_1_0.webp 276 KB, gbi_L4_1_1.webp 398 KB, gbi_L4_1_2.webp 269 KB, gbi_L4_1_3.webp 428 KB; total 1.37 MB

| Map | Set | Page | Texel density | White point | Seconds | Samples |
|---|---|---|---|---|---|---|
| `gbi_L4_1_0` | day | shell 2048 | 20.0 px/m | 2.1111 | 34 | 512 |
| `gbi_L4_1_1` | day | props 2048 | 18.4 px/m | 3.0965 | 79 | 512 |
| `gbi_L4_1_2` | night | shell 2048 | 20.0 px/m | 0.3024 | 36 | 512 |
| `gbi_L4_1_3` | night | props 2048 | 18.4 px/m | 0.2805 | 54 | 512 |

**Day** (`lightmap`; gain 0.591, walls aimed at p50 0.5)

| Material | m² | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L4` | 2567.4 | 0.019 | 0.023 | 0.025 |  |
| `M_D_floor_L4` | 2336.5 | 0.190 | 0.306 | 0.719 |  |
| `M_D_wall_L4` | 1357.0 | 0.500 | 0.618 | 0.827 |  |
| `M_X_white` | 1184.2 | 0.416 | 0.811 | 0.970 | 0.88 |
| `M_D_trim` | 183.6 | 0.307 | 0.682 | 0.682 |  |
| `M_Fixture_Housing` | 165.3 | 0.872 | 0.880 | 0.880 | 0.78 |
| `M_GBI_furn_L4` | 159.0 | 0.493 | 0.880 | 0.949 | 0.89 |
| `M_X_dark` | 123.9 | 0.000 | 0.018 | 0.034 |  |
| `M_U_blue` | 74.5 | 0.135 | 0.217 | 0.467 |  |
| `M_U_bluepaint` | 29.0 | 0.262 | 0.400 | 0.431 |  |
| `M_GBI_card` | 28.6 | 0.141 | 0.351 | 0.469 |  |
| `M_U_yellow` | 23.5 | 0.214 | 0.506 | 0.587 |  |
| `M_GBI_vent` | 16.2 | 0.183 | 0.274 | 0.301 |  |
| `M_GBI_tape` | 12.5 | 0.667 | 0.880 | 0.919 | 0.96 |
| `M_U_arrow` | 11.5 | 0.000 | 0.853 | 0.970 | 0.79 |
| `M_D_door` | 9.2 | 0.245 | 0.315 | 0.352 |  |
| `M_X_steel` | 2.0 | 0.143 | 0.426 | 0.740 |  |

**Night** (`lightmap_night`; gain 2.5424, walls aimed at p50 0.15)

| Material | m² | p50 | p90 | p99 | cap |
|---|---|---|---|---|---|
| `M_D_ceil_L4` | 2567.4 | 0.008 | 0.012 | 0.018 |  |
| `M_D_floor_L4` | 2336.5 | 0.073 | 0.147 | 0.325 |  |
| `M_D_wall_L4` | 1357.0 | 0.151 | 0.277 | 0.463 |  |
| `M_X_white` | 1184.2 | 0.172 | 0.365 | 0.653 |  |
| `M_D_trim` | 183.6 | 0.096 | 0.343 | 0.380 |  |
| `M_Fixture_Housing` | 165.3 | 0.002 | 0.100 | 0.442 |  |
| `M_GBI_furn_L4` | 159.0 | 0.174 | 0.486 | 0.627 |  |
| `M_X_dark` | 123.9 | 0.000 | 0.009 | 0.017 |  |
| `M_U_blue` | 74.5 | 0.037 | 0.053 | 0.089 |  |
| `M_U_bluepaint` | 29.0 | 0.064 | 0.247 | 0.319 |  |
| `M_GBI_card` | 28.6 | 0.044 | 0.120 | 0.225 |  |
| `M_U_yellow` | 23.5 | 0.066 | 0.143 | 0.207 |  |
| `M_GBI_vent` | 16.2 | 0.026 | 0.049 | 0.054 |  |
| `M_GBI_tape` | 12.5 | 0.103 | 0.420 | 0.451 |  |
| `M_U_arrow` | 11.5 | 0.000 | 0.422 | 0.651 |  |
| `M_D_door` | 9.2 | 0.098 | 0.176 | 0.178 |  |
| `M_X_steel` | 2.0 | 0.044 | 0.233 | 0.354 |  |
