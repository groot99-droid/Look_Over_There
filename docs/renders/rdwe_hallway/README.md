# `rdwe_hallway`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_hallway`: the Hallway, the descent

A corridor 49 m end to end, 3.2 m wide and 4.6 m high: from the lower landing up six carpeted steps (brass nosings) into the long plaid
corridor of doors that do not feel right. The printed plaid is grey-beige with violet and lime threads gone a little too bright; the worn tan
carpet has a lattice of dark diamonds with a pink dot in each; nine surface-mounted twin-tube fluorescents (`Lamp_Emit`: the page flickers
them one at a time); a dark skirting and cornice. At the far end the amber vestibule (its walls amber plaster, its ceiling stacked with light
bars, `Amber_Emit`) over the well of mossy pixel-block stone going down, moss creeping up its sides. Ten doors, each its own: the green baize
door with brass studs back to the dining room, and nine down the corridor (pink laminate flush with a push plate, cherry red louvred, black
lacquer half-glazed with a brass knob: the three that open; and six that never open: sky blue ledged and braced, an oak round-topped door with a
glass knob, studded pink laminate, quilted cherry red with a ring pull, a mirror-faced black door, a sky blue porthole door).

- GLB 1.88 MB, 16884 triangles, 39 draw calls; lightmaps `_0` / `_1` 2048 / 2048 at 59.4 / 51.3 px/m (94 KB / 226 KB).
- Light: nine tube fittings (130 W cool area lights), the amber vestibule (500 W), a green glow in the well, a warm light on the landing. Gain 0.706; capped: Fixture 0.545, Glass_Knob 0.697.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Wall_Plaid | 361.3 | 0.300 | 0.542 | 0.750 |
| Carpet_Tan | 183.7 | 0.323 | 0.436 | 0.551 |
| Ceiling_Hall | 177.8 | 0.083 | 0.128 | 0.599 |
| Wall_Amber | 78.1 | 0.385 | 0.590 | 0.697 |
| Moss_Stone | 54.9 | 0.001 | 0.428 | 0.917 |
| Trim_Hall | 35.0 | 0.070 | 0.105 | 0.128 |
| Leaf_PinkLaminate | 13.2 | 0.001 | 0.736 | 0.843 |
| Leaf_CherryRed | 12.9 | 0.001 | 0.501 | 0.626 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
