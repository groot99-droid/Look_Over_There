# `rdwe_finale`

Dressed and lit with the other Phase A rooms of Right Door, Wrong Exit: see `docs/renders/rdwe_dining/README.md` (how they are built, light, brightness, sources and licences).

### `rdwe_finale`: the finale, hide and seek (Phase B)

48 m by 44 m, 4.5 m high: a central hall and four wings behind navy partition walls, a neon pink stripe round the outer walls at 1.2 m,
pale speckled vinyl, an acoustic ceiling with rows of fluorescent strips (`Lamp_Emit`).
- **The offices (north-west):** six cubicles of blue fabric on aluminium frames, desks with monitors (`Screen_Emit`); the offices' computer is
  the monitor on the first desk.
- **The house (south-west):** a bed with a pink quilt, a wardrobe, a maple table with a laptop (the house's computer), an orange sofa, a round
  teal rug; lit warmer.
- **The server room (north-east, `Zone_restricted_servers`):** four 12 m rows of dark racks with grilles and green blinking lights
  (`Server_Emit`); the console on the last rack; lit dimmer and blue.
- **The aisles (south-east):** four gondola runs, a till with its screen on the last.
- **The hall:** the cyan fountain (a basin, a spout, a sheet of `Water`); the seeker's spot by it.
- **Cameras:** the ten `SecCam_` empties are unchanged in the layout; each has a white camera on a black arm drawn where it looks from.
  The agents' six vents are grilles over black.
- **Doors:** the grocery's glass sliding pair from the other side, unchained (the way in), and the tall blue double door under a green EXIT
  (`Emergency_Emit_Green`), sealed until every camera is off.

The page-trick spots (`Spot_computer_*`, `Spot_hide_*`, `Spot_agent_*`, `Spot_seeker_1`) are untouched; the screens and the till sit beside
them, never on them.

- GLB 1.99 MB, 14054 triangles, 36 draw calls; lightmaps `_0` / `_1` / `_2` 2048 / 2048 / 2048 at 20.5 / 30.9 / 41.4 px/m (238 KB / 394 KB / 224 KB).
- Light: strip rows over the hall and the wings (520 W area lights, 10 m long; the server room's 300 W and blue, the house's warmer), the green EXIT's glow, a cyan light at the fountain. Gain 0.87; capped: Acoustic_Finale 0.543, Cam_White 0.81, Leaf_Blue 0.727, Strip_Housing 0.479, Stripe_Pink 0.761, Till 0.458, Vinyl_Finale 0.371.

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Acoustic_Finale | 2149.0 | 0.526 | 0.817 | 0.970 |
| Vinyl_Finale | 2149.0 | 0.593 | 0.880 | 0.966 |
| Wall_Navy | 1827.8 | 0.300 | 0.500 | 0.574 |
| Gondola | 642.2 | 0.126 | 0.397 | 0.710 |
| Rack_Grille | 308.6 | 0.001 | 0.007 | 0.009 |
| Rack_Body | 276.8 | 0.000 | 0.050 | 0.078 |
| Strip_Housing | 109.4 | 0.584 | 0.881 | 0.897 |
| Cubicle_Panel | 103.0 | 0.423 | 0.534 | 0.575 |

No material is over p90 0.9 or p99 0.98. (The full table is in the gate output; materials with p50 near 0 count faces no one sees: undersides, backs against walls, the leaves' edges in the reveal.)
