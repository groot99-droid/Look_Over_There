# `rdwe_teal`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_teal`: Teal Room, Square Door, the glitch

14 m by 18 m, 4 m high (2.5x). The empty clean teal box gone a shade too bright, a cream ceiling, the coarse brown carpet flecked with cream,
black, orange and a few teal threads. The orange angular leather sofa against the back wall left of centre, 5.6 m long: a chamfered shell (an
elongated octagon in side view), three seat cushions, a low back, black feet; F on it is the way on ("just for a minute"). The black square
doorway right of centre: no leaf, a slab of black flush with the wall (`Void`) that swallows the light. The blocky little plant in its stone
planter, pixel leaves. The fake window on the west wall: a painted sky whose sun never moves (`Window_Lit`), a cream frame, mullions and sill,
and a warm low light falling from it across the carpet. A flush dome light. The well's low door: mossy stone-grey, ledged and braced, iron
straps and an iron ring.

- GLB 0.98 MB, 1804 triangles, 19 draw calls; lightmaps `_0` / `_1` 1536 / 1536 at 47.8 / 84.5 px/m (46 KB / 116 KB).
- Light: the flush dome (700 W), four soft fills, the window's low warm sun (260 W area light from the fake window). Gain 4.273; capped: Carpet_Fleck 1.058, Ceiling_Teal 3.003, Dome 0.571, Leather 3.415, Leather_Seam 1.909, Plant_Leaf 2.787, Sill 0.772, Trim_Teal 1.32.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Carpet_Fleck | 265.0 | 0.110 | 0.216 | 0.970 |
| Ceiling_Teal | 265.0 | 0.119 | 0.288 | 0.969 |
| Wall_Teal | 255.9 | 0.291 | 0.499 | 0.968 |
| Leather | 99.8 | 0.000 | 0.777 | 0.970 |
| Trim_Teal | 9.4 | 0.665 | 0.873 | 0.970 |
| Plant_Leaf | 7.7 | 0.095 | 0.714 | 0.969 |
| Leaf_Stone | 6.1 | 0.000 | 0.174 | 0.362 |
| Sill | 5.2 | 0.344 | 0.757 | 0.970 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
