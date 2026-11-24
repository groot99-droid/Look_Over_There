# galleries: the museum hall

The second scene of the Blender plan (`docs/BLENDER.md`, "2. galleries"). A small municipal museum after hours, as the night guard sees it on the 20:00 shift: a long red gallery with a herringbone parquet in a marble border, dark wainscot, a brass picture rail and empty gilded frames, six dark plinths under warm gallery spots, moonlight falling through four skylights, and paler patches on the wall where paintings were taken down. Built in Blender 5.2.1 from `blender/layout/galleries.json`, baked in full at night (the scene is only ever played at night) and exported as art only. The structure follows the apartment pilot (`docs/renders/apartment/README.md`, `tools/blender/build_apartment.py`).

| File | What it is |
|---|---|
| `world/galleries.glb` | the art: 0.92 MB, 5184 triangles, 15 draw calls, textures as WebP |
| `world/lightmaps/galleries_0.webp` .. `galleries_3.webp` | the baked light, four maps (second UV set, `TEXCOORD_1`) |
| `blender/scenes/galleries.blend` | the saved scene (0.31 MB, Git LFS): `Art` (the unmerged pieces), `Export` (merged by material, with the lightmap UVs), `Standins`, `Lights` |
| `tools/blender/build_galleries.py` | the re-runnable build (reads the layout; no hand-copied coordinates) |
| `blender/textures/galleries/` | the four CC0 texture files the build reads |
| `docs/renders/galleries/` | the three review stills (this file's folder) |

The shared tools are reused unchanged: `tools/blender/check_layout.py`, `tools/blender/pack_scene.py`, `tools/webp_glb.py`, `tools/blender/dump_layout.mjs`.

## Review stills (Cycles, 128 samples adaptive, OIDN denoise, 1920 x 1080 JPEG, AgX, exposure 0)

| | |
|---|---|
| `1_arrival.jpg` (126 KB) | the arrival point (0, 4.4) at eye height 1.6 m, facing the scene's `face` (north, -z), 75 degrees vertical like the page's camera |
| `2_wide.jpg` (122 KB) | the whole hall from high in the south-east corner, inside the room |
| `3_detail.jpg` (128 KB) | plinth 3 (east side, z -7) under its spot, the plinth beyond and the empty frames over the wainscot |

![arrival](1_arrival.jpg)
![wide](2_wide.jpg)
![detail](3_detail.jpg)

These are Blender renders with Blender's real lights, at exposure 0 as the pilot's, so they show the light level the lightmaps hold. The statues in them are the hidden stand-ins (the blockout's six-box figure, `Standins`): the page draws the real ones. The GLB was loaded with three.js r186 in node (below); it was not looked at in a browser, so the coordinator's in-game screenshot from the arrival point is the first look at it under the page's shading.

## Sources and licences

| Material | Used for | Source | Author (Poly Haven) | Licence |
|---|---|---|---|---|
| `herringbone_parquet`: diffuse, 1k | the parquet field | https://polyhaven.com/a/herringbone_parquet | Sergej Majboroda (photography), Jenelle van Heerden (processing) | CC0 1.0 |
| `marble_01`: diffuse, 1k | the floor's border | https://polyhaven.com/a/marble_01 | Rob Tuytel | CC0 1.0 |
| `plastered_wall_04`: diffuse, 1k | the walls (tinted red), the ceiling (tinted off-white), the plinths (tinted dark grey) | https://polyhaven.com/a/plastered_wall_04 | Rob Tuytel | CC0 1.0 |
| `dark_wood`: diffuse, 1k | wainscot, skirting, dado rail, the door | https://polyhaven.com/a/dark_wood | Dario Barresi, Dimitrios Savva, Rico Cilliers | CC0 1.0 |

**3 of the 8 allowed Poly Haven downloads were used** (`herringbone_parquet`, `marble_01`, `plastered_wall_04`: 1k JPEG maps from `https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/...`, with a generic client name and no other data sent; the parquet's 1k roughness map was also fetched and then not used). `dark_wood` came from a local cache of earlier Poly Haven downloads, as in the pilot. All were re-saved as JPEG quality 88 into `blender/textures/galleries/`. The tints are multiplied in the material (a Multiply node the exporter writes as `baseColorFactor`), so one plaster image serves three materials. Authors come from Poly Haven's public info API.

Everything else is own work, made by `build_galleries.py`: all geometry, and two generated images drawn with numpy from fixed seeds (the EXIT sign, a pixel font on green; the pale "ghost" of a removed painting with a dusty rim). No Meshy, no paid service, no photograph, no remote GPU.

Tools: Blender 5.2.1 LTS (GPL) with Cycles, OpenImageDenoise (Apache-2.0, through the compositor's Denoise node) and the glTF I/O add-on; Python with numpy (in Blender) and Pillow (the WebP step); three r186 for the load check. The bake and the stills ran on the laptop's CPU (Intel Core Ultra 7 155U, 14 threads): Cycles found no GPU it can use there.

## Budgets (measured)

| | Limit | Measured |
|---|---|---|
| `world/galleries.glb`, lightmaps aside | at most 8 MB | **0.92 MB** (921952 bytes; 1.07 MB from Blender, then `tools/webp_glb.py`: textures 0.70 to 0.55 MB, geometry bytes asserted identical) |
| triangles | at most 300 000 | **5184** (`glb_inspect.py`: 5184 drawn) |
| draw calls, merged by material | at most 250 | **15** (one primitive per material, 15 materials) |
| textures | WebP | **6 images, all `image/webp`** (four 1024 x 1024, the ghost decal 256 x 256, the EXIT sign 256 x 96) |
| lightmaps | at most 4, at most 2048 x 2048, 8-bit WebP q90 | **4**: see the table below |

| Lightmap | Size | Density | File | `lightmap_intensity` | What is on it |
|---|---|---|---|---|---|
| `galleries_0` | 896 x 896 | 30.2 px/m | 25 KB | 2.8036 | parquet, marble border, ceiling |
| `galleries_1` | 1152 x 1152 | 32.0 px/m | 68 KB | 4.1741 | walls, wainscot, skirting, dado, cornice, the ghost decals |
| `galleries_2` | 768 x 768 | 35.5 px/m | 32 KB | 33.7595 | plinths, frames, the door |
| `galleries_3` | 1152 x 1152 | 36.3 px/m | 44 KB | 42.1574 | dark metal and brass: tracks, spot heads, picture lights, picture rail, wires, skylight frames, plinth toes |

Bake: Cycles on the CPU, 512 samples, diffuse (direct and indirect, no colour), 8 px margin, OIDN denoise; the four maps took 225, 216, 35 and 30 s. The whole `--stage all` run (art, bake, export, axes check, the three stills and the plan at 128 adaptive samples) took 1074 s, about 18 minutes, from an empty work folder. `glb_inspect.py --budget tris=300000,mb=8` says `pass tris`, `pass mb`.

Why four maps: each map's white point is its 99.5th percentile texel, and the metal fittings sit centimetres from the lights, so their texels run some 10 to 40 times hotter than the room's. On one map with the walls they would have crushed the walls into the bottom few 8-bit levels; on their own map (and with their own intensity) neither suffers.

The three.js check (node, three r186 from a local `node_modules`; node cannot decode images, so the GLB's images are taken out of the JSON before three parses it and their types are read from the JSON):

```
three r186; world/galleries.glb (0.92 MB)
PASS 6 images, all image/webp: image/webp
PASS 15 meshes (draw calls), 15 materials; textured materials: Ceiling_Paint, Decal_Ghost, Door_Wood, Floor_Marble, Floor_Parquet, Plinth_Paint, Wainscot_Wood, Wall_Paint
PASS 5184 triangles
PASS Ceiling_Paint: lightmap world/lightmaps/galleries_0.webp x2.8036, uv1 108 verts
PASS Decal_Ghost: lightmap world/lightmaps/galleries_1.webp x4.1741, uv1 24 verts
PASS Door_Wood: lightmap world/lightmaps/galleries_2.webp x33.7595, uv1 200 verts
PASS Floor_Marble: lightmap world/lightmaps/galleries_0.webp x2.8036, uv1 16 verts
PASS Floor_Parquet: lightmap world/lightmaps/galleries_0.webp x2.8036, uv1 4 verts
PASS Frame_Gold: lightmap world/lightmaps/galleries_2.webp x33.7595, uv1 880 verts
PASS Lamp_Emit: no lightmap (emissive, toggled by the page clock)
PASS Metal_Brass: lightmap world/lightmaps/galleries_3.webp x42.1574, uv1 2838 verts
PASS Metal_Dark: lightmap world/lightmaps/galleries_3.webp x42.1574, uv1 2486 verts
PASS Plinth_Paint: lightmap world/lightmaps/galleries_2.webp x33.7595, uv1 288 verts
PASS Sign_Exit: no lightmap (emissive)
PASS Skylight_Glass: no lightmap (transparent, faintly emissive)
PASS Trim_Paint: lightmap world/lightmaps/galleries_1.webp x4.1741, uv1 144 verts
PASS Wainscot_Wood: lightmap world/lightmaps/galleries_1.webp x4.1741, uv1 132 verts
PASS Wall_Paint: lightmap world/lightmaps/galleries_1.webp x4.1741, uv1 16 verts
PASS world/lightmaps/galleries_0.webp exists (25 KB), used by 3 meshes
PASS world/lightmaps/galleries_1.webp exists (68 KB), used by 4 meshes
PASS world/lightmaps/galleries_2.webp exists (32 KB), used by 3 meshes
PASS world/lightmaps/galleries_3.webp exists (44 KB), used by 2 meshes
PASS 4 lightmap image(s), at most four
PASS material Lamp_Emit present
PASS no statue, stand-in or name-plate material in the GLB
PASS no statue or stand-in mesh in the GLB
INFO collision bounds (-6.20, -1.00, -20.20) .. (6.20, 5.20, 6.20)
INFO art bounds (-6.20, 0.00, -20.20) .. (6.20, 5.20, 6.20)
PASS art lies inside the collision bounds (+5 cm)
PASS art x/z span equals the colliders' x/z span (within 5 cm)
PASS hall height: floor top 0.00 (collider 0), ceiling underside 5.00 (collider 5)
PASS every mesh has an identity transform (vertices in game coordinates)
PASS: all checks
```

## The layout check

`blender -b blender/scenes/galleries.blend --python tools/blender/check_layout.py -- --scene galleries` (exit code 0):

```
layout check: scene galleries, 57 visible meshes, 12 colliders
PASS  COVER  Floor_Museum: 16 mesh(es) cover it (178965 sample points, every one within 5 cm of art)
PASS  COVER  Ceiling_Museum: 9 mesh(es) cover it (99375 sample points, every one within 5 cm of art)
PASS  COVER  Wall_N: 15 mesh(es) cover it (19125 sample points, every one within 5 cm of art)
PASS  COVER  Wall_S: 20 mesh(es) cover it (19125 sample points, every one within 5 cm of art)
PASS  COVER  Wall_W: 21 mesh(es) cover it (39933 sample points, every one within 5 cm of art)
PASS  COVER  Wall_E: 21 mesh(es) cover it (39933 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_0: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_1: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_2: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_3: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_4: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  COVER  Plinth_5: 5 mesh(es) cover it (700 sample points, every one within 5 cm of art)
PASS  STRAY  28 tall solid mesh(es), each over a collider; 0 decor_* mesh(es) exempt
PASS  CLEAR  marker Spawn_door (0.00, 4.40): clear within 0.28 m
PASS  CLEAR  constants.arrive (0.00, 4.40): clear within 0.28 m
PASS  CLEAR  door.at (0.00, 5.30): clear within 0.28 m
PASS: 16 of 16 checks passed
```

There is no passable (`decor_*`) piece: everything that reaches below head height is a collider's art or lies within 5 cm of a wall (the frames are 4.5 cm deep, the door's leaves 3.5 to 4.5 cm). The axes were checked with a marker cube at the arrival point (`--stage axes`): game (0, 0.1, 4.4) is Blender (0, -4.4, 0.1) is glTF (0, 0.1, 4.4).

## Rebuild

From the repo root, with node, Blender 5.2 and Python with Pillow:

```
node tools/blender/dump_layout.mjs galleries                     # writes blender/layout/galleries.json (git ignores that folder)
blender -b --python tools/blender/build_galleries.py -- --stage all --samples 512 --render-samples 128     # art, bake, export, axes check, stills
python tools/blender/pack_scene.py galleries                     # WebP lightmaps and WebP textures -> world/
```

`--stage art|bake|export|axes|render` run one step on the saved `.blend` (`blender -b blender/scenes/galleries.blend --python ... -- --stage bake`). `--device cpu` forces the CPU; a GPU is used when Cycles finds one. The work folder defaults to the system temp folder's `farway_galleries` (`--work <dir>` changes it). The review stills are written straight into `docs/renders/galleries/`; the plan view goes to the work folder.

## What the coordinator does to wire it in

1. Add `world/galleries.glb` to the `galleries` scene's files in `shared/farway.manifest.js` (it lists only `world/galleries.json` today). The collision file is untouched and still the code's.
2. Hide the blockout in `museumProps(root)` (`index.html`): the floor and ceiling slabs, the four walls, the door slab and the six plinth slabs. **Keep** what the page owns: the six statue groups (`CITY.mu.figs`, moved by `placeStatues`) and the name plates (`signTexture`).
3. **Remove the four night `PointLight`s** that `museumProps` adds. The spots, the picture lights, the moon and the sky are in the lightmaps (`docs/BLENDER.md`, contract 4: in a scene with a model the page adds no lamp of its own). `cityLook` keeps the hemisphere light at 0.5 (`0x9aa8d0`) for the statues and the players; that is what lights the statues, and it does not touch the baked materials.
4. Apply the lightmaps with `applyLightmaps` as for the apartment: 12 materials carry `lightmap` and `lightmap_intensity` in their extras (four images); the intensities are pi times each image's white point.
5. The materials the page may touch: `Lamp_Emit` (the spot lenses and the picture-light tubes, emissive, strength 14; the museum is only played at night, so it can stay on), `Skylight_Glass` (the four frosted panes, transparent, faintly emissive blue), `Sign_Exit` (the EXIT sign over the door, emissive). None carries a lightmap. `Window_Lit` and `Emergency_Emit` do not occur in this scene.
6. Run every suite one at a time, merge.

## Stand-ins, and what is not exported

- **The statues** (the page draws them): `standin_statues` in `Standins` is the blockout's six-box figure on each plinth at 0.6 m, turned to face the hall as `placeStatues` turns them. It was in the bake, so each plinth top carries its statue's spot shadow (the only thing lost when one steps off, as the plan accepts), and it shows in the stills; it is never exported.
- **The name plates** (the page draws them): nothing is built on the plinth faces toward the hall. Note that the page's plate is 1.6 m wide on a 0.9 m plinth, so it overhangs the plinth by 35 cm either side.
- **The arrival marker** `standin_arrival_marker`: a 20 cm cube at the arrival point (the axes check), never rendered or exported.
- **Lights** (`Lights`): six 950 W plinth spots (34 degrees) and two 750 W spots on the north frame, all on the two ceiling tracks; thirteen picture lights (90 W, the big north frame 180 W); the moon (a 1.4 W/m2 sun from high in the west-south-west); the night sky (the world, seen only through the skylights); the EXIT sign's glow. Used for the bake and the stills, not exported (`export_lights` is off).
- **Not in the GLB:** the statues, the name plates, the door as a mechanism (the double door is a closed leaf pair in its architrave; the page's prompt at `door.at` is unchanged).

## Things to know

- **Axes and scale:** metres, y up; identity node transforms, so vertices are in game coordinates. The hall's inside is x -6 to 6, z -20 to 6, y 0 to 5 (the colliders' slabs reach 20 cm further, and so do the floor's border and the art's bounds).
- **Plinth height:** `docs/BLENDER.md` says the plinths are 0.45 m high; the code's `MUSEUM.plinth` is 0.45 as the half-width, and the colliders and the statues stand on 0.6 m. The build follows the code: 0.9 m square, 0.6 m high.
- **What sits where (derived from the layout, not typed in):** the four skylights and the long walls' frames sit in the bays halfway between the plinth rows and one bay past each end (z -16, -10, -4, 2); the two tracks run 3.4 m in from the long walls; the door is 2.4 x 2.6 m on `door.at`'s x, as the blockout drew it.
- **Skin:** the walls, floor and ceiling keep only the faces that look into the hall, and every other piece drops the faces that lie flat against a wall, the floor or the ceiling (never seen, and each would be one more lightmap island). The skylight openings are 20 cm deep, inside the ceiling collider.
- **The `.blend`** finds its textures by relative path (`//../textures/galleries/`); the two generated images are packed in it.
- **`blender/layout/` is in `.gitignore`**, as for the pilot: `galleries.json` is not committed and is rebuilt from the code by `node tools/blender/dump_layout.mjs galleries` before every build (the output is byte-identical from run to run). Add it with `git add -f` only if the coordinator wants the snapshot in the repo.
- **Nothing local in the public files:** the build strips every custom property other add-ons put on the scene, the world and the other data (some hold paths of the user folder) before it exports with `export_extras` and before it saves, keeps only `lightmap` and `lightmap_intensity` on the materials, blanks Blender's fixed path buffers before writing the relative texture paths and `//` for the render output, and turns every `use_stamp_*` off so the JPEG stills carry no `Blender:File` metadata. The checks scan the GLB, the WebP files, the stills, the script and an uncompressed copy of the `.blend` for the user name and local paths.
- **Lightmap page sizes are fixed** (`PAGES` in the build: 896, 1152, 768, 1152), because Blender's island packer is not exactly repeatable and map 3 used to land on 1024 or 1152 from run to run. The intensities are each map's 99.5th percentile texel, so a rebuild moves maps 0 to 2 by a few per cent at most; map 3 (the metal fittings, whose brightest texels are a few hot spots) moved by about 20 % between two clean rebuilds (42.16 here, 34.96 in the check's rebuild). Each GLB carries the intensity that matches its own lightmaps, so this only matters when comparing builds.

## Open

- The light level: dim, as the plan asks ("a small municipal museum at night ... dim"), with the middle of the aisle lit only by the moon squares and the sky. If it reads too dark in the game, the cheapest lift is the moon and the sky (`MOON_W`, `WORLD_STRENGTH` in the build) and a rebake (about 10 minutes for the bake stage on this laptop's CPU).
- The page's name plates (1.6 m wide) overhang the 0.9 m plinths; a plate of about 0.8 m would sit on the plinth's face.
