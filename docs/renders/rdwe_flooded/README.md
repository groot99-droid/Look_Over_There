# `rdwe_flooded`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_flooded`: Flooded Corridor, the decay

A corridor 50 m by 5 m, 4 m high (1.5x), in one-point perspective. White square tile on every wall, cream tile underfoot with a yellow tactile
strip, a white ceiling with eight square recessed light panels (`Lamp_Emit`) and little vents between them. Down the left, above a steel dado,
the painted sky: a saturated blue, fat cumulus blushing pink, a green hill line and a strip of yellow flowers. Down the right, the empty wooden
frames, shrinking toward the far end; one of them, door-sized, is a door (its canvas the leaf, a painted sky). Steel handrails on brackets both
sides. Three heaps of sodden cardboard boxes and wet paper against the sky, three photographs on the first. The perfect blue blocks the drips
leave, melting on the floor. The grate before the end (soft: the way down). At the end, the red door, lit red and framed in red light
(`Emergency_Emit`): the lure, it never opens. The back of the arch you came through: teal, round-topped, already sealing.
- **Water:** one sheet over the whole floor, 5 cm up, its own unbaked material `Water` (pale blue, glossy, alpha 0.28). It is hidden while
  baking, so the tiles under it carry the light as if dry; the page may ripple it.

- GLB 1.10 MB, 3658 triangles, 26 draw calls; lightmaps `_0` / `_1` 2048 / 2048 at 54.8 / 33.9 px/m (98 KB / 192 KB).
- Light: eight square ceiling panels (300 W cool area lights), the red door's glow (120 W, red). Gain 0.271.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Tile_Wall | 441.5 | 0.300 | 0.550 | 0.787 |
| Ceiling_White | 272.2 | 0.090 | 0.157 | 0.302 |
| Tile_Floor | 272.2 | 0.455 | 0.578 | 0.832 |
| Sky_Paint | 108.0 | 0.421 | 0.635 | 0.684 |
| Cardboard | 74.1 | 0.000 | 0.076 | 0.113 |
| Rail_Steel | 33.5 | 0.148 | 0.226 | 0.281 |
| Cardboard_Light | 31.4 | 0.000 | 0.100 | 0.154 |
| Frame_Wood | 14.0 | 0.042 | 0.079 | 0.115 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
