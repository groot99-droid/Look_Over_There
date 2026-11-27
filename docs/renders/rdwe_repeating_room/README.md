# `rdwe_repeating_room`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_repeating_room`: the room that repeats, and the door seen from one angle (Phase B)

12 m by 12 m, 3.2 m high. Lilac paper printed with a lattice of little pink doors, each a hair different; a peach shag; a pale pink
ceiling with one glowing pendant; a cream skirting and cornice. The pink velvet armchair, the side table with its lamp, and on the west wall a
picture of this room with a picture of this room in it. The north door (`again`) and the south door you come back in by (`again_in`) are the
same plain white flush door, a brass number plate on each: 12 going out, 13 coming back in. The lift and the library doors are their own
looks. On the east wall the free-standing baffle, papered like the walls with a cream foot, hides the 2 m recess; at its far end the door seen
from one angle (`secret_ops`) is a flush leaf in the wall's own door paper, with no frame and no handle, so from anywhere but `Spot_view_1` it
is wall. The page-trick spots (`Spot_view_1`, `Spot_change_1` to `_3`) are untouched and nothing is placed on them; the page swaps the
changes.

- GLB 0.77 MB, 3496 triangles, 22 draw calls; lightmaps `_0` / `_1` 1536 / 1536 at 56.8 / 99.5 px/m (52 KB / 119 KB).
- Light: the pendant (260 W), the table lamp (60 W), four soft fills, a faint light in the recess. Gain 1.087; capped: Carpet_Peach 0.847.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Wall_Doors | 190.7 | 0.300 | 0.598 | 0.958 |
| Ceiling_Repeat | 158.2 | 0.193 | 0.262 | 0.341 |
| Carpet_Peach | 153.8 | 0.652 | 0.861 | 0.970 |
| Trim_Repeat | 19.4 | 0.421 | 0.694 | 0.857 |
| Velvet_Pink | 10.3 | 0.114 | 0.252 | 0.290 |
| Leaf_White | 9.9 | 0.074 | 0.723 | 0.788 |
| Leaf_PinkLaminate | 9.1 | 0.000 | 0.660 | 0.732 |
| Leaf_Oak | 9.1 | 0.000 | 0.104 | 0.164 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
