# Farway in Blender: the build and render plans

This plan covers every scene the page loads today. For each one it says what to build in Blender, how to light and render it, and how the result comes back into the game. It is written for the Blender tools session, which has Blender and the GPU, and for the coordinator session, which wires the results into the game and merges them. The owner can stop or reorder any of it.

## What is in scope

| Group | Scenes | Today | This plan |
|---|---|---|---|
| A. The store (already Blender) | B1, L1, L2, L3, L4, Exterior. The parking lot (`parking_lot`) and the two Going back in chambers (`gbi_L4_4`, `gbi_L3_1`) reuse these models | `blender/Look_Over_There.blend` (Git LFS, 140 MB), exported per level by `tools/blender/split_scenes.py` into `world/*.glb`; their collision files came from the same file | Light baking and review renders only, with no change to geometry |
| B. Code blockouts | `apartment`, `main_floor` (grocery), `entrance` (mall), `galleries` (museum), `factory_floor`, `laboratory`, `street`, `forest`, `meadow` | Boxes drawn by `index.html` (`apartmentProps`, `forestProps` and the like) from the layouts in `shared/city.js`, `shared/museum.js`, `shared/factory.js`, `shared/lab.js` and `shared/forest.js`; `world/<id>.json` is written by `tools/make_street.mjs` | A real Blender build of each, plus baking, review renders and edge-of-world backdrops |
| C. Planned | Overworld: `table_and_chairs`, `playground`, `tree_house`, `bus_station`, `road`, `endless_hills`. Also City `bus_stop`, Grocery `back_of_house`, the hotel (10 scenes), `street_of_jobs`, Secret Operations, and the 15 Going back in chambers | Not designed past `docs/WORLD.md` | Not built now. Each gets its own plan once its gameplay layout exists. The edge-of-world backdrop for the Overworld (R3) is the one exception |

## The contract every scene keeps

1. **Gameplay layout is code, and Blender follows it.** In group B, each collider, door spot, station, plinth, shelf, tree trunk and arrival point comes from the scene's shared module. Blender builds the art around those positions. A visible solid must stand where a collider is (within 5 cm), and no collider may be left unseen, except the invisible edge walls named `Edge_*`. If a build needs a layout change (a wall moved, a door widened), it goes to the coordinator as a request, not into the art.
2. **Get the numbers from the exporter.** Run `node tools/blender/dump_layout.mjs [scene]`. It writes `blender/layout/<scene>.json` with:
   - the collision file;
   - the scene's constants;
   - the seeded placements: the forest's 260 trees and path, the meadow's 120 trees and 420 flowers, and the street's buildings, doors and lamps.

   Build scripts read that file. No one copies coordinates by hand.
3. **Axes.** The game uses metres with y up. The glTF exporter's default (+Y up) maps a game point (x, y, z) to Blender (x, −z, y). Each build checks this once with a marker cube at the arrival point.
4. **Things that move or change stay in code.** The Blender file leaves them out, or holds them only as stand-ins for the bakes and renders that are never exported. Each scene below lists them. Anything the page toggles gets its own material, named so the page can find it: lamp heads that light at night (`Lamp_Emit`), lit windows (`Window_Lit`), the mall's emergency lights (`Emergency_Emit`).
5. **The owner's models are not touched.** `models/world/shed.glb`, `models/world/cottage.glb`, the item models and the characters keep their geometry. If they must appear in a bake (shadows, contact AO) or a render, they are linked in as stand-ins and not exported, because the page loads them itself. The owner disliked slimmed models, so nothing of theirs is decimated.
6. **Sources.** Use CC0 textures, HDRIs and scans (Poly Haven, ambientCG) or the author's own work, with each source and its licence listed in the scene's README. Paid generation (Meshy) and GPU rentals need the owner's go-ahead first. The reference photos named in `docs/WORLD.md` are AI-generated: use them as references, not as textures, until the generator's terms are checked.

## The build, per scene (group B)

For every scene:
- **Input:** `blender/layout/<scene>.json`.
- **Output:**
  - `world/<scene>.glb`, the art only;
  - its lightmaps;
  - a re-runnable build script, `tools/blender/build_<scene>.py`, run as `blender -b --python tools/blender/build_<scene>.py`;
  - the saved `blender/scenes/<scene>.blend` (Git LFS takes it automatically: `.gitattributes` has `*.blend`).

### 1. `apartment` (the pilot)
- **Layout:**
  - The room spans x −3 to 3 and z −2.5 to 2.5, and is 2.8 m high.
  - The bed, desk and fridge sit at their boxes in `APARTMENT`.
  - The computer stands at (1.8, −1).
  - A window in the east wall at x = 2.98 spans z −1.4 to 0.6 and y 1 to 2.2. It looks out onto the street, so a backdrop plane sits behind it.
  - The door is in the south wall at (1.5, 2.1).
- **Look:** a small, worn city studio with one ceiling lamp, a desk lamp and city glow through the window.
- **Code keeps:** the computer's screen (the UI opens on F) and the prompts.
- **Light:** full bake. The room is lit the same by day and by night.
- **Why first:** it is the smallest scene and has every part of the pipeline: axes, a lightmap, WebP, the layout check and integration. Nothing else starts until the coordinator has it working in the game.

### 2. `galleries` (the museum)
- **Layout:**
  - The hall spans x −6 to 6 and z −20 to 6, and is 5 m high.
  - Six plinths, 0.45 m high, stand at `MUSEUM.homes`.
  - The door is to the south, at (0, 5.3).
- **Look:** a small municipal museum at night, the shift being 20:00 to 23:00. Dim, with gallery spots on the plinths, parquet, picture rails and empty frames.
- **Code keeps:** the six statues, which step off their plinths, and their name plates.
- **Light:** a full bake at night. Bake the spots with the statues on their plinths as stand-ins; their contact shadow is the only thing lost when they move.

### 3. `laboratory`
- **Layout:**
  - The room spans x −9 to 9 and z −6 to 6, and is 4 m high.
  - Five stations (sink, scale, centrifuge, freezer, log book) stand at `LAB.stations`, each a 1.2 m square.
  - A sealed door in the north wall at (0, −6) reads "B2 · AUTHORISED STAFF ONLY". It is the way toward Secret Operations, so build it as a real-looking door that does not open.
- **Look:** clinical white, strip lights, a steel bench at each station.
- **Code keeps:** the station labels and highlights.
- **Light:** full bake.

### 4. `factory_floor`
- **Layout:**
  - The hall spans x −10 to 10 and z −7 to 7, and is 6 m high.
  - The belt runs from x −8 to 8 at z −3. It is 1.2 m wide with its top at 0.9 m, and a reject chute sits past its east end.
  - Three bins (gears, bolts, springs) stand at (−5, 2.5), (0, 2.5) and (5, 2.5), each 1.2 m square.
- **Look:** an old works hall with sodium high-bays, a painted safety line and a steel truss roof.
- **Code keeps:** the moving parts, and the belt's top surface, which scrolls. Build the belt's frame and rollers only, up to 0.88 m.
- **Light:** full bake.

### 5. `main_floor` (the grocery)
- **Layout:**
  - The store spans x −12 to 12 and z −9 to 9, and is 4 m high.
  - Four shelves (apple, bread, soup, meal) stand at `GROCERY.shelves`.
  - The cart corral is at (−4.5, 7.2) and the checkout at (6.5, 5.6).
  - The door is to the south, at (0, 8.3).
  - The security camera hangs at (0, 3.4, −8.7) on the north wall.
- **Look:** the same room as the end of Right Door, Wrong Exit, a little bigger: tiled floor, fluorescent tubes, a red-cart feel (IMG_3027 is the reference).
- **Code keeps:**
  - The food on the shelves. Its models come later, in lighter versions.
  - The cart.
  - The camera head and its red light. Build only the wall bracket.
- **Light:** full bake by day. The store is shown out at closing, so it is never seen at night.

### 6. `entrance` (the mall atrium)
- **Layout:**
  - The atrium spans x −16 to 16 and z −12 to 12, and is 7 m high.
  - The dry fountain, at x −2.5 to 2.5 and z −4.5 to 0.5, is 0.7 m high.
  - Two benches stand at x ±8.
  - The eight shuttered shopfronts are named in `MALL.shops`.
  - The door is to the south, at (0, 11.3).
- **Look:** old and abandoned, and also mid-build: scaffolding, dust sheets, a skylight. The shop names are painted signs.
- **Code keeps:** nothing moves.
- **Light:** two bakes. Day comes from the skylight; the second set comes from the emergency lights alone, which the page switches to at 20:00 when the doors lock. Give the emergency fittings `Emergency_Emit`.

### 7. `street` (Hallam Row)
- **Layout:**
  - The road spans x −5 to 5 and z −140 to 14; the world reaches x ±60 and z −150 to 30.
  - Each building in `BUILDINGS` has its side, z range, depth, height and colour. The tower is 38 m tall.
  - The doors are at x = ±8, at each building's `door.z`.
  - Lamp posts stand at `LAMP_ZS`, and the bus shelter at (7, 5).
- **Look:** a run-down street of brick and render, shop signs at each address, sidewalks with kerbs and drains.
- **Code keeps:**
  - the PHARMACY sign's letters, which change as you pass;
  - the six pedestrians, the stalker and the window watchers;
  - the trash bins on the route from 41, and the bus.

  Lit windows use `Window_Lit` so the page can switch them by the clock. Make the three watcher windows separate panes:
  - one on the filler block across from the mall;
  - one at 330;
  - one high in the tower.
- **Light:** an AO bake only, because the street has a day clock. The sun, the sky and the lamps stay dynamic, and the lamp heads use `Lamp_Emit`.
- **Backdrops:** both ends of the street (R3).
- **Build last of group B:** it is the largest scene. Merge materials by building to keep the draw calls down.

### 8. `forest`
- **Layout:**
  - The ground spans x −40 to 40 and z −100 to 12.
  - The path winds along `path`, about 8 m wide, and runs straight at both ends.
  - The 260 trees stand at `trees` as [x, z, trunk radius] and must stand exactly there, because their trunks are the colliders. Crowns start above 2.2 m.
  - The signpost back to the lot is at (2.6, 8.4).
  - The bright gap into the meadow is at z −92.
- **Look:** pastel dreamcore, under pink haze. The page keeps the fog (22 to 105 m) and the sky colour `#f4d8ec`.
- **Trees:** build three to five variants and export them with GPU instancing (`EXT_mesh_gpu_instancing`; three.js r160 loads it). Bake their AO into each variant's own texture. Bake the ground's AO with every tree in place.
- **Code keeps:** the signpost's text and the gap's walk-through.
- **Backdrops:** more forest past the edge walls, and a glow at the gap (R3).

### 9. `meadow`
- **Layout:**
  - The ground spans x −45 to 45 and z −84 to 12.
  - 120 trees ring the edge (`trees`).
  - 420 flowers in five colours (`flowers`) can be instanced, and are not solid.
  - The path runs north to the house.
- **Owner's models:** the shed at (−15, −30) and the house at (0, −66), linked as bake stand-ins only. The page draws both itself.
- **Look:** the forest's palette, opening up, with tall grass, a softer haze, and the moonlit cabin as the focal point.
- **Code keeps:** the shed, the house and the door prompts.
- **Light:** AO bake, with the sun dynamic.
- **Backdrops:** R3.

## Light and render plan (every group)

### R1. Lightmaps
- **Where they go:** each mesh gets a second UV set (TEXCOORD_1, lightmap-packed, 8 px margin). The bake goes to separate images under `world/lightmaps/<scene>_<n>.webp`: at most four per scene, each at most 2048², 8-bit WebP q90.
- **How the page finds them:** each material that uses one carries the custom properties `lightmap` (the path) and `lightmap_intensity`. Export with Include → Custom Properties, so these land in glTF `extras`. The coordinator's page code then sets `material.lightMap` with `channel = 1`.
- **Why this way:** it keeps the base textures shareable and lets the page switch a map off (night, the mall's emergency set). Baking light into the base colour would light the scene twice under the page's own lights.
- **Bake settings:** Cycles on the GPU, 512 to 1024 samples, OIDN denoise. Texel density is about 32 px/m indoors and 8 to 12 px/m outdoors.
- **AO-only scenes** (street, meadow; the forest's trees): the same slot holds an AO bake.

### R2. Review renders
- **What:** three stills per scene, 1920×1080:
  - the arrival point at eye height 1.6 m, facing the scene's `face`;
  - a wide view of the whole scene;
  - one detail.
- **Engines:** Eevee for iterations, Cycles for the final set.
- **Where:** saved as JPEG (at most 400 KB each) in `docs/renders/<scene>/`, so the owner can look without opening Blender. After integration, the coordinator adds an in-game screenshot from the same spot to compare.

### R3. Edge-of-world backdrops
`docs/WORLD.md`: "The edge of the world is a fake 2D render of more world that looks real."
- **What:** equirectangular panoramas rendered from each scene's centre with the playable area hidden, 4096×2048 WebP. The page uses them as the scene background, in place of the flat colour.
- **Which scenes:**
  - `parking_lot` and the Overworld: the endless hills and the town beyond the hedges;
  - `forest` and `meadow`;
  - `street`: the city past both ends, a day set and a night set.

### R4. The store's rebake (group A)
- **Do not change geometry.** The store's collision files, doors and cameras came from this geometry.
- **Steps:**
  1. Work on a copy of `Look_Over_There.blend`. Run `git lfs pull` first, because the checkout holds only a pointer.
  2. Add lightmap UVs, bake as in R1, and re-export with `split_scenes.py`. It exports with Draco, and the page has the Draco loader.
  3. Run `tools/blender/verify_world.py`. It must pass unchanged.
- **Check UV1 first:** `world/Exterior.glb` already carries a second UV set. Check what it is used for before overwriting it.
- **The floors' looks:**
  - B1: flooded pools, water transmission kept.
  - L1: the office maze.
  - L2.
  - L3: the white plaster room. Keep it white, with no monsters and soft even light.
  - L4: the showroom and its glass doors.
- **Code keeps:** monsters, pickups, the doors' leaves, the cameras' heads, the L3 fuse box's lever and lamp, the L4 switch and the stair-door panel.
- **Do last:** it touches the main game. Each floor is a separate PR.

## Checks before a scene is handed over

1. **Layout check:** a `tools/blender/check_layout.py` written for the pilot and reused. It compares each visible mesh's world box (in game coordinates) with `world/<scene>.json`:
   - each collider is covered by art, edge walls aside;
   - no solid art taller than 0.2 m stands where there is no collider, except meshes named `decor_*` that you can pass through (flowers, grass, dust sheets);
   - the arrival points and door spots are clear.
2. **Budget:** `studio/pipeline/glb_inspect.py` from Pipelines-Plugin, against these limits:

   | | Limit |
   |---|---|
   | Group-B `.glb`, lightmaps aside | at most 8 MB (the store's floors are 2 to 6.6 MB) |
   | Triangles | at most 300k (instanced trees count once per variant) |
   | Draw calls | at most 250 after merging by material |
   | Textures | WebP, through `python tools/webp_glb.py`, which re-encodes the textures only and asserts the geometry is unchanged |

   If `webp_glb.py` refuses a Draco file, export without Draco.
3. **Renders:** R2's three stills are in `docs/renders/<scene>/`.

## How a scene comes back

- **One scene, one PR:**
  - The PR goes to `groot99-droid/Look_Over_There` on branch `claude/blender-<scene>`, as a draft.
  - It holds:
    - the `.glb`;
    - the lightmaps;
    - the build script;
    - the `.blend`;
    - the renders;
    - a short `docs/renders/<scene>/README.md` with sources and licences, the budget numbers and the layout check's output.
- **What the Blender session leaves alone:** `index.html`, `shared/`, the manifest and the tests.
- **What the coordinator does:**
  1. adds `world/<scene>.glb` to the scene's files in `shared/farway.manifest.js`;
  2. hides the code blockout for it;
  3. applies the lightmaps, the toggled materials and the backdrop;
  4. runs every suite one at a time;
  5. merges.
- **Order:**
  1. the apartment, the pilot, which waits for the coordinator to confirm it works in the game;
  2. galleries, laboratory and factory_floor;
  3. main_floor and entrance;
  4. forest and meadow, with their backdrops;
  5. street, with its backdrops;
  6. the parking-lot backdrop;
  7. the store's rebake, floor by floor (R4).

  After the pilot, the owner sees each scene's renders in its PR and can stop or redirect at any point. Silence means carry on.

## Defaults taken (the owner can overrule them)

- **Lightmaps** are separate images on a second UV set, not baked into the base colour.
- **Day and night:**
  - The street and the meadow bake AO only, with the sun dynamic.
  - The mall bakes two light sets.
  - The museum is baked at night.
  - The grocery is baked by day.
- **The forest** is built from tree variants, because the trunks' places are fixed by its seed; there are no unique trees.
- **Group C** waits for gameplay layouts.
- **Art direction** comes from the text of `docs/WORLD.md`. The owner can send the reference photos it names if they want a closer match.
