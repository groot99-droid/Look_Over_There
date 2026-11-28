# `rdwe_trampoline`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_trampoline`: Trampoline Park, the macro-structure

30 m by 50 m, 9 m high (2x; the page still wraps you to make it go on forever). The grid of 54 black woven beds edged in yellow, set in orange
padded frames (pale yellow every other row); padded orange columns with yellow bands; the angled trampoline walls at both edges, a sloped
dark mesh in padded ends; padded orange walls all round; a bare concrete apron under the vent you fall out of (a grille in the ceiling); a dark
steel truss ceiling, beams across every 4.7 m and purlins along, with a lattice of LED panels (`Lamp_Emit`). Far north, the red glow
(`Emergency_Emit`): the anomaly. Doors: a tall white marble door with a brass meander frieze (reserved for the god rooms) and the padded orange
vent door with its slots.
- **The beds** are baked like everything else and merged into one mesh a material (the page bounces you in `Zone_trigger_beds`, not the beds);
  no unbaked material was needed for the park's surfaces.

- GLB 1.36 MB, 14738 triangles, 19 draw calls; lightmaps `_0` / `_1` / `_2` 2048 / 2048 / 2048 at 25.0 / 23.7 / 22.4 px/m (175 KB / 379 KB / 276 KB).
- Light: 33 of the LED panels as 900 W area lights (every other one), the red glow (300 W, red). The walls' gain targets p50 0.45 here (the floor is grey concrete and the beds black, so the room needs it). Gain 0.187; capped: Edge_Yellow 0.151, Pad_Orange 0.17, Pad_Pale 0.177.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Concrete_Apron | 1532.2 | 0.114 | 0.202 | 0.223 |
| Truss_Deck | 1532.2 | 0.004 | 0.005 | 0.006 |
| Pad_Wall | 1444.5 | 0.450 | 0.679 | 0.930 |
| Bed_Weave | 564.6 | 0.014 | 0.019 | 0.023 |
| Truss_Steel | 525.6 | 0.005 | 0.008 | 0.009 |
| Pad_Orange | 299.4 | 0.423 | 0.878 | 0.971 |
| Pad_Pale | 106.8 | 0.618 | 0.880 | 0.921 |
| Edge_Yellow | 97.8 | 0.726 | 0.878 | 0.919 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
