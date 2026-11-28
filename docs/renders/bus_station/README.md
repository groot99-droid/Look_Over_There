# bus_station: dressed and baked (docs/BLENDER_AREAS.md, "4. The Overworld"; step 2)

"Just a ride": a small station in the lot in place of the shelter, dressed in Blender on the greybox's layout
(`claude/blender-overworld-greybox`, draft PR #115), unchanged: `export_scene.py` writes the same `world/bus_station.json` from the dressed
`.blend`. It is a set that stays part of the lot: the greybox's `ATTACH` puts its origin at the lot's (-46, 9.6, 46), yaw 0. Tone: plastic
and pastel, empty but seemingly normal.

| File | What |
|---|---|
| `world/bus_station.glb` | the set only (WebP textures, 0.48 MB, 3,732 triangles, 18 draw calls), merged by material |
| `world/lightmaps/bus_station_0.webp` | the AO bake, 2048 x 2048, 63 px/m, linear grey, on TEXCOORD_1 |
| `blender/scenes/bus_station.blend` | the saved scene (Git LFS): `Art`, `Layout`, `Export`, and `Context` (the lot's asphalt, its bus stop post and its hedge round the set, from the greybox's `ctx_` boxes: in the stills and the bake's rays, never exported) |
| `1_arrival.jpg`, `2_wide.jpg`, `3_detail.jpg` | R2's stills (Cycles, 128 samples): off the bus at the `bus_stop` arrival, 1.6 m up, facing the shelter; the station from the south-west; the timetable and the stop's flag |
| `bake.json`, `CHECKS.txt` | the bake's numbers; every gate's output |

Built by `tools/blender/dress_overworld.py -- --scene bus_station` (one Blender run: art, layout gates, bake, export, stills), then
`python tools/blender/pack_scene.py bus_station --work work/ow_bus_station`. The textures are `tools/blender/overworld_textures.py`'s
(`paving`, `timetable`, `ticket_face`, `bus_flag`, `dest_sign` are new here).

## What is there

- **The platform** (`Platform`, 14 m by 4 m, 0.15 m up): pale lilac-grey 0.5 m paving slabs, a white line along the bay's kerb.
- **The shelter:** three glass walls in aluminium frames (each frame is the solid object over its collider; the pane, `Glass`, is
  see-through, alpha 0.3, not baked), a soft blue roof (`Roof_Blue`), a wooden slatted bench with a backrest. Under the roof: a light strip
  (`Lamp_Emit`, the page's toggle, on from dusk) and a navy destination board, "HALLAM ROW, every 15 min", on two hangers at the front
  (2.13 m over the platform).
- **The timetable** on two posts: buses to Hallam Row every 15 minutes, 06:00 to 17:45, "Just a ride." at the foot.
- **The ticket machine:** coral plastic, a screen, four pastel buttons, a coin slot and a tray.
- **The stop's flag** on its pole: yellow, a bus in a white disc, BUS STOP, HALLAM ROW.
- **The bay,** painted on the lot (decor, 3 to 8 mm up): a yellow box open to the kerb and BUS in block letters, read upright from the
  platform.
- **Small things (decor):** weeds and tiny flowers at the platform's foot, six ticket stubs dropped on it. Nobody is waiting.
- **No ground:** the set ships none. In the game the lot's own asphalt is under it; `Ground_lot` stays a collider only, as the greybox has it.

## Light (docs/BLENDER.md R1, AO-only scenes)

Open air, as the other Overworld scenes: only ambient occlusion is baked. Every baked material carries `aomap`
(`world/lightmaps/bus_station_0.webp`), `aomap_intensity` 1.0 and `aomap_colorspace` `linear`; the page keeps them lit and uses the map as
`aoMap` on UV1. Bake: Cycles AO, 512 samples on the GPU, distance 2.5 m, OIDN, 8 px margin; the glass is hidden from the rays (it is
see-through) and the lot's asphalt (Context) is in the scene for them. Not baked: `Glass`, `Lamp_Emit`, the flowers. Faces that lie on
the ground (the platform's and the paint's undersides) are left out.

## Brightness

Base colour x AO (linear), under a white ambient of 1, before the page's sun (as the other Overworld scenes).

| Material | m2 | p50 | p90 | p99 |
|---|---|---|---|---|
| Paving | 61.2 | 0.569 | 0.633 | 0.668 |
| Roof_Blue | 29.9 | 0.824 | 0.828 | 0.828 |
| Steel | 17.7 | 0.276 | 0.418 | 0.467 |
| Deck | 6.3 | 0.211 | 0.295 | 0.341 |
| Line_Yellow | 4.9 | 0.890 | 0.890 | 0.890 |
| Plastic_Coral | 4.1 | 0.485 | 0.673 | 0.769 |
| Timetable_Print | 3.0 | 0.653 | 0.777 | 0.887 |
| Paint_White | 1.5 | 0.784 | 0.787 | 0.787 |
| Ticket_Face | 1.3 | 0.032 | 0.558 | 0.687 |
| Sign_Dest | 1.2 | 0.042 | 0.081 | 0.898 |
| Sign_Bus | 0.7 | 0.820 | 0.868 | 0.961 |

Sign_Dest is a navy board (dark by design; the letters are its p99). Ticket_Face's low p50 is the face's back, inside the machine.
Sign_Bus has 0.25% of its samples at 1 (the print's edges after compression); p99 0.961.

## Gates (CHECKS.txt has the full output)

- Layout check, run in Blender on the saved scene: 12 of 12 pass (COVER for the nine colliders with art, STRAY, CLEAR for the link's F
  spot and arrival), plus the LOT rule: `Ground_lot` has no art by design (the lot's asphalt), it lies flat at y 0 inside the lot round the set.
- `export_scene.py` writes the same `world/bus_station.json`.
- `build_overworld_greybox.py --check .`: GATES PASS.
- `node tools/worlddoc.mjs check world/bus_station.json`: OK, 0 errors (1 warning: the `bus_stop` link is new to the manifest).
- `glb_inspect --budget tris=300000,mb=8`: pass (3,732 triangles, 0.48 MB).
- `node --test shared/*.test.js`: 297 pass, 0 fail.
- Privacy grep over this scene's files (the `.blend` decompressed): 0 hits. The stills carry no comment or APP1 segment.

## Sources and licences

Everything here was made for this scene: the geometry by `dress_overworld.py`, the textures by `overworld_textures.py` from noise and
drawing (no downloads, no third-party pixels; the lettering uses the system's Arial only to draw pixels, no font file is shipped). No
Meshy, no Higgsfield, no purchases.

## Open

- The coordinator places the GLB in the lot at `ATTACH` (the lot's (-46, 9.6, 46)), removes index.html's own shelter there, and moves the
  lot side of `overworld.bus>city` / `city.bus>overworld` to this scene's `bus_stop` link (the greybox's OUTSIDE notes).
- The glass is `alphaMode` BLEND; the page draws it as any transparent glTF material. The page does not read `aomap` yet.
- No bus is modelled: the ride is the page's.
