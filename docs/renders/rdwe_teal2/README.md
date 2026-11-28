# `rdwe_teal2`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_teal2`: Teal Room, Arched Door, the mutation

8 m by 22 m and 5.5 m high: the same teal, cream and brown, narrower, taller and wrong. The rounded cognac sofa along the west wall (you wake
beside it), its bolster arms and cushions. The tall arch in the back wall: no leaf (`DoorLeaf_arch` is an empty), its round top filled in teal,
a cream trim round it, the black corridor beyond. The tall spiky plant in a terracotta pot. Three patches of wallpaper peeled back on the east
wall, the glowing green grid under them (`Grid_Emit`), the paper curling off along the torn edge, and a faint green light from each. The door
to the green grid is a teal door under the same paper, the grid showing through two tears. A flush dome light.

- GLB 0.50 MB, 1808 triangles, 18 draw calls; lightmaps `_0` / `_1` 1536 / 1536 at 48.9 / 81.6 px/m (55 KB / 127 KB).
- Light: the flush dome (600 W), four soft fills down the length, a faint green light off each patch of grid, almost nothing from the arch. Gain 7.5; capped: Carpet_Fleck 1.212, Dome 0.844, Leather 5.449, Paper_Back 1.148, Plant_Leaf 5.906, Terracotta 3.244, Trim_Teal 1.336.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Wall_Teal | 331.2 | 0.301 | 0.686 | 0.903 |
| Carpet_Fleck | 188.2 | 0.070 | 0.151 | 0.970 |
| Ceiling_Teal | 188.2 | 0.157 | 0.240 | 0.284 |
| Leather | 37.5 | 0.017 | 0.850 | 0.972 |
| Trim_Teal | 10.7 | 0.484 | 0.835 | 0.970 |
| Paper_Teal | 4.8 | 0.022 | 0.512 | 0.554 |
| Paper_Back | 3.6 | 0.164 | 0.810 | 0.970 |
| Terracotta | 2.0 | 0.322 | 0.874 | 0.971 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
