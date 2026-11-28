# The racetrack (`racetrack`), dressed

The third part of the owner's request ("Along side the playground create a basketball court, a tennis court, and a racetrack"): a small outdoor kart loop, its own scene, reached through the sports courts' south gap (`docs/renders/sports/`). Laid out first in the greybox (`tools/blender/build_overworld_greybox.py`, `racetrack()`), then dressed by `tools/blender/build_overworld_sports.py` with the playground's method and look, and given an ambient-occlusion bake. Tone: liminal, an ordinary kart track on a bright day with nobody at it: the start lights off, the garages shut, the grandstand empty.

| File | What it is |
|---|---|
| `world/racetrack.glb` | the art, art only, merged by material |
| `world/racetrack.json` | the layout, written by `tools/blender/export_scene.py` from the `.blend`; equal (parsed) to `build_overworld_greybox.py --preview`'s |
| `world/lightmaps/racetrack_0.webp`, `_1.webp` | the AO bake (second UV set, linear): the ground, the track, the curbs and the hedges (2048); the concrete, steel, shutters and signs (2048) |
| `blender/scenes/racetrack.blend` | the saved scene (Git LFS): `Art`, `Layout`, `Export` |
| `docs/renders/racetrack/` | this file, the three review stills, `bake.json` and `brightness.txt` |

The textures are the playground's and the courts' (`blender/textures/overworld_play/`, `overworld_sports/`).

## The layout

150 m by 100 m inside its hedge (x -75 to 75, z -50 to 50, floor y 0).

- **The track:** an 8 m asphalt loop of **353 m** (centreline): two 90 m straights (north and south, z -33 and 33), two 30 m short straights (x -63 and 63) and four bends of 18 m radius (centres at (+-45, +-15)). Karts run clockwise seen from above: east along the north straight. White edge lines, a start/finish line of 0.5 m checks at x 6 on the north straight and ten staggered grid slots behind it. **No collider on the track, the curbs, the pit lane or the lines:** they are `decor_`, so the loop can be walked and driven. The `--check` corridors cover all four straights and the pit lane: nothing stands on them.
- **Curbs:** red and white, about 1.2 m a block, on the inside and the outside of every bend, a 5 cm ridge rising from the track's edge.
- **Tyre walls** round the outside of each bend: two rows of stacks (three tyres, 0.78 m) at 26 m and 26.65 m from the bend's centre, 4 m of grass run-off behind the outer curb. 536 stacks in 92 chunks of three columns; each chunk is one collider (`Tyres_<bend>_<nn>`, its box round the stacks) and one colour (red, black, white, black along the bend).
- **Start/finish gantry** at x 6: a steel pillar outside the track and one on the pit wall, a box truss over the track at 5.6 to 6.4 m with FINISH on both faces and five start lights (off: dark red lenses, `Lamp_Red_Off`) facing the grid.
- **Grandstand** outside the north straight (x -30 to -2): eight concrete tiers you can climb from the front (0.27 m each, 0.8 m deep, to 2.16 m; a flight in the greybox's steps gate), 440 blue plastic seats (a white row in the middle), a back wall, side walls and a cantilevered roof on trusses; a 1 m wall between it and the track, a RACETRACK sign on its back.
- **Pit lane** inside the north straight: a 1 m pit wall (red and white panels on the track side) from x -30 to 30, the lane (6 m, x -36 to 36) with its way in after the north-west bend and out before the north-east bend, a yellow box in front of each of six garages (one 48 m building, roller shutters down, PITS over the middle).
- **Also:** three lamp posts north of the track, the hedges round the edge, three `Spot_groundskeeper`.

Link: `sports` at (-38, 0, -50.6) in a 6 m gap in the north hedge (an arch over it reads SPORTS facing in), arriving at (-38, 0, -47.4) facing south-east (0.6, 0.8), toward the grandstand and the gantry; the other side is `sports.racetrack` (the courts' south gap). Spot: `Spot_minigame_racetrack` on the grid behind the line (props equipment, pays, what: "a timed lap: cross the line, go round, cross it again (no kart yet)", `lap_m` 353.1).

## Light: ambient occlusion only

As the playground and the courts: `aomap` and `aomap_intensity` 1.0 on the second UV set, no `lightmap`; the page lights the materials with its sun and sky. Not baked: the lamp heads (`Lamp_Emit`, switched by the page), the start lights, the paint, and the tyres and the seats. Those two are thousands of small UV islands (536 stacks, 440 seats): baked with the rest they took the standing map down to 2.6 px a metre; left out (black rubber and plastic, lit by the page alone) the walls, roof, gantry and garages get 24.7 px a metre.

Baked in Cycles on the rented GPU (`--samples 256`), OIDN-denoised, 8 px margin, linear (`bake.json`):

| Map | Size | What | AO distance | px/m | AO p10 / p50 / p90 |
|---|---|---|---|---|---|
| `racetrack_0` | 2048 | the grass, the track and pit lane, the curbs, the hedges | 1.5 m | 10.1 | 0.04 / 1.00 / 1.00 |
| `racetrack_1` | 2048 | concrete (grandstand, walls, garages), steel (roof, gantry, posts), shutters, signs | 0.8 m | 24.7 | 0.01 / 0.75 / 1.00 |

## Brightness

Base colour (factor x texture) x AO texel x `aomap_intensity` under white light of 1, area-weighted, max channel (the baked materials).

```
material                m2           map       k    p50    p90    p99     >=1
Grass              16170.8   racetrack_0  1.0000  0.526  0.574  0.603   0.00%
Asphalt             3336.3   racetrack_0  1.0000  0.217  0.233  0.250   0.00%
Hedge               2219.2   racetrack_0  1.0000  0.259  0.302  0.327   0.00%
Concrete            1977.0   racetrack_1  1.0000  0.335  0.606  0.621   0.00%
Steel               1253.2   racetrack_1  1.0000  0.580  0.580  0.580   0.00%
Curb_Red             200.4   racetrack_0  1.0000  0.737  0.740  0.740   0.00%
Curb_White           170.4   racetrack_0  1.0000  0.817  0.820  0.820   0.00%
Shutter               82.3   racetrack_1  1.0000  0.476  0.559  0.565   0.00%
Signs                 28.8   racetrack_1  1.0000  0.784  0.799  0.965   0.46%
```

Main surfaces: p90 at most 0.82, p99 at most 0.82 (the signs 0.97); the walls (hedges 0.26, concrete 0.34) read p50 over 0.15. The asphalt is dark on purpose (0.22). The unbaked materials are flat colours at or under 0.85: tyres black 0.05, red 0.72, white 0.80; seats blue and white as the playground's plastic.

## Checks

- Layout check (`check_layout.py`, run inside the art stage on `Art`): **PASS, 121 of 121** (COVER for all 118 colliders but the four edge walls, STRAY, and CLEAR for the link's `at` and `arrive`).
- `python tools/blender/build_overworld_greybox.py --check . --glb world`: **GATES PASS** (steps: the grandstand's 8 tiers at 0.27 m; corridors: the track's straights and the pit lane clear).
- `export_scene.py` writes the same layout as `--preview` (compared parsed: equal).
- `node tools/worlddoc.mjs check world/racetrack.json`: **OK**, 122 colliders, 1 link, 4 spots, 0 errors, 4 warnings (the scene is 152 m by 102 m, over worlddoc's 60 m advice, as the road and the hills are; the scene and its link are new to the manifest).
- `glb_inspect.py world/racetrack.glb --budget tris=300000,mb=8`: **pass**, 95,634 triangles (72k of them tyres), 4.37 MB (4.58 MB on disk), 19 materials, 19 meshes.
- `node --test shared/*.test.js`: 297 of 297 pass.
- Privacy grep over the committed files (the `.blend` decompressed): clean.

## Sources and licences

No third-party asset is used: generated textures (own work) and models built by the scripts from boxes, cylinders and tubes.

## Open

- The coordinator wires the manifest: the scene `racetrack` and its links `overworld.sports>racetrack`, `overworld.racetrack>sports`.
- No karts: the minigame spot is on the grid for a timed lap when the page has one. If karts come, the tyre walls' colliders are boxes round each chunk of stacks (up to about 0.7 m bigger than the stacks at 45 degrees in a bend, all on the grass run-off).
- The scene is large (152 m by 102 m) for one load; it is one open field, so splitting it was not needed for the budget.
