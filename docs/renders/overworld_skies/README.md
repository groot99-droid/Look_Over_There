# Overworld skies: the four default sky backdrops

`docs/BLENDER_AREAS.md` (the Overworld, "Skies") asks for four default Overworld skies, rendered as R3 backdrops
(`docs/BLENDER.md`, R3), which the owner can replace. They are:

| Sky | File | Look |
|---|---|---|
| Clear day | `world/backdrops/overworld_clear_day.webp` | `docs/WORLD.md`'s "clear with no clouds": pale at the horizon, deep blue overhead, the sun in the south-west, 52 degrees up |
| Sunset | `world/backdrops/overworld_sunset.webp` | One warm low sun in the west-south-west, 11 degrees up, just clear of the ridges; warm toward the sun, violet away from it, a few long thin clouds. Serves for sunrise too |
| Night | `world/backdrops/overworld_night.webp` | A bright starry night: stars, the Milky Way, the moon in the south-east, the town's lit windows and lamps, the store's lit front |
| Painted | `world/backdrops/overworld_painted.webp` | "Drifting anime clouds": a saturated cerulean sky with big cel-shaded cumulus in three flat tones and crisp edges, and high brush-stroke wisps |

Each is a 4096 x 2048 equirectangular WebP, under 1 MB, with no EXIF or XMP chunk. As R3 says, the picture's middle column faces
north (game -z) and its right-hand side faces east (game +x). The coordinator names them in the manifest; this branch does not wire them.

## Method

`tools/blender/build_overworld_skies.py` builds and renders everything:

- **The ground** in the lower half is the parking-lot backdrop's (`tools/blender/build_parking_lot_backdrop.py`, draft PR #91): the same
  seeded height function, fields, copses, farmhouses and the town past the back hedge. It is seen from the same point, the lot's Spawn
  marker at eye height, so the five backdrops agree.
- **The far store** is the one addition. It is a box with the proportions of the lot's store, drawn 2.4 times its size 360 m north of the
  arrival point. The Overworld scenes that do not hold the store's model still see it there. From the lot itself, the store's own model
  covers it.
- **The skies** are world shaders seen by camera rays only: gradients, sun and moon discs, Voronoi stars, a noise Milky Way, and noise
  clouds projected onto a cloud deck. Diffuse light on the ground comes from a sun lamp and a flat ambient colour per sky.
- **Render:** Cycles on the GPU, 128 samples with OpenImageDenoise, Standard view transform, 8-bit PNG. The PNG is packed to WebP with Pillow,
  at the highest quality that fits in 1 MB.
- **Checks:** before every sky's render, an orientation self-check renders three glowing markers (east, north, south) and asserts their
  columns. `--stage check` then checks each WebP for size, bytes and metadata chunks. It also checks that the sun's or moon's disc is in the
  column and row its bearing and elevation give, and not at the mirrored bearings.

Stages (from the repo root):

    blender -b --factory-startup --python tools/blender/build_overworld_skies.py -- --stage skies --work <work> [--only clear_day,night] [--save 0]
    python tools/blender/build_overworld_skies.py --stage pack --work <work> [--only ...]
    python tools/blender/build_overworld_skies.py --stage check [--only ...]
    python tools/blender/build_overworld_skies.py --stage previews --work <work> [--only ...]
    python tools/blender/build_overworld_skies.py --stage sheet --work <work> --out <png>

## Preview stills

There are two flat 75-degree views out of each panorama, as JPEGs with the comment and APP1 segments stripped:

- `clear_day_1_north.jpg`: the far store and the hills to the north.
- `clear_day_2_south.jpg`: the town.
- `sunset_1_west.jpg`: the low sun.
- `sunset_2_north.jpg`.
- `night_1_southeast.jpg`: the moon.
- `night_2_north.jpg`: the Milky Way and the lit store.
- `painted_1_north.jpg`.
- `painted_2_south.jpg`: the sun and the clouds.

## Sources and licences

Everything is procedural: numpy noise for the ground and Blender's own shader nodes for the skies. No image, model, HDRI or texture from
anywhere else is used, so there is nothing to license. Poly Haven and ambientCG were not needed.

## Notes

- The ground below the horizon is plain grass seen from eye height. In the game the scene's own floor covers it.
- The sunset sky also serves for sunrise. Its sun is in the west; a separate sunrise would want the sun in the east.
- The `.blend` (`blender/scenes/overworld_skies.blend`) is not committed. The script rebuilds it.
