# `rdwe_grocery`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_grocery`: Grocery Store, the anomaly

50 m by 50 m, 5 m high (1.2x): the stripped store as a maze of empty grey gondola shelving on 10 by 10 aisles of 5 m. Glossy speckled vinyl in
big cream and mint squares (a pink fleck here and there), cream-painted walls, an acoustic tile ceiling with rows of fluorescent strips over the
aisles (`Lamp_Emit`). Each shelf run is a gondola (kick, back panel, five shelves, end panels); the posts between runs are cream end caps, each
with a band of candy colour (pink, lime, cyan) at eye height, the one psychedelic note in a stripped store. In the clearing in the middle, the
red cart, roped off between four chrome stanchions with sagging caution tape. In three dead ends, pyramids of unlabelled tins with one red tin
each, flats of cardboard beside them. Doors: the chained glass sliding pair at the entrance, the grey steel fire exit with its push bar under
the lit EXIT (`Emergency_Emit`), the bronze door with a laurel wreath for a handle (from the god rooms), the stockroom's black rubber flaps
with STAFF ONLY.

- GLB 2.83 MB, 28490 triangles, 34 draw calls; lightmaps `_0` / `_1` / `_2` 2048 / 2048 / 2048 at 21.2 / 33.8 / 11.5 px/m (202 KB / 496 KB / 481 KB).
- Light: the strip rows over the aisles (520 W area lights, 10 m long, one per row segment), the EXIT sign's glow. Gain 0.137.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Gondola | 3235.7 | 0.033 | 0.104 | 0.166 |
| Acoustic | 2540.2 | 0.241 | 0.262 | 0.285 |
| Vinyl_Floor | 2540.2 | 0.395 | 0.498 | 0.546 |
| Gondola_Back | 1204.2 | 0.042 | 0.114 | 0.155 |
| Store_Wall | 995.4 | 0.299 | 0.344 | 0.373 |
| Post_Cream | 550.4 | 0.260 | 0.407 | 0.496 |
| Kick | 359.3 | 0.000 | 0.028 | 0.038 |
| Strip_Housing | 149.5 | 0.266 | 0.539 | 0.548 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
