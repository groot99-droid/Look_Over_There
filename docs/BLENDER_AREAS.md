# Farway in Blender, part 2: the planned areas (Blender first)

`docs/BLENDER.md` (part 1) covers the scenes whose layout already exists in code. This part covers every place that so far exists only as a description in `docs/WORLD.md`: the hotel, the rest of the grocery and the mall, the Overworld, the City's extras, the Going back in chambers, Right Door, Wrong Exit and Secret Operations. It comes to about 100 spaces.

For these places Blender is the source of the layout, as it was for the store. The Blender session builds the place, and the walls, doors and spots are exported from the Blender file into the game's format. Part 1's rules on sources, the owner's models, light baking (R1), review renders (R2), backdrops (R3) and budgets all still apply.

**What is settled and what is a default.** Each area's contents come from `docs/WORLD.md`. The sizes, the scene ids that are not yet in the manifest and the room lists below are the coordinator's defaults, marked [DEFAULT], and the owner can change them from the greybox renders.

## How a Blender-first scene is made

1. **Greybox.** Plain boxes, to scale, for every scene of the area at once. Render a top-down plan of each (orthographic, with a scale bar and labels on the rooms and doors) and one eye-height still. These go up as the area's first draft PR, `claude/blender-<area>-greybox`, so the owner sees the whole layout early.
2. **Dress and light.** One scene at a time, with part 1's bake and review renders.
3. **Export.** `world/<scene>.glb` for the art, and `world/<scene>.json` for the layout, written by `tools/blender/export_scene.py` (see below).
4. **Checks and PR.** One draft PR per scene, as in part 1.

The owner looks at each area's greybox PR. Silence means carry on with dressing; a comment redirects.

### The exporter and its names

The store's original exporter is not in the repo, so the first job is to write `tools/blender/export_scene.py`. It must write the format the page already reads (see `world/L1.json`): `scene`, `colliders`, `doors`, `cameras`, `markers`. The new keys `links`, `zones` and `spots` are for the coordinator to wire in; the page ignores keys it does not know. A game point (x, y, z) is Blender (x, −z, y).

| Blender object | Exported as | Notes |
|---|---|---|
| `COL_<name>` box mesh | `colliders`: `{s, min, max}` | Not exported to the `.glb`. See the collision rules below. |
| `DoorLeaf_<name>` | `doors`: `name, level, hinge, width, height, closed_yaw_deg, swing_deg, state` | Origin at the hinge. Leaves are 0.94 m by 2.16 m unless the door is special. Only doors can be shut, trapped or barricaded. |
| `Marker_<name>` empty, property `kind` | `markers` | `Spawn`, `Entrance` or `Exit`. |
| `Link_<door id>` and `Arrive_<door id>` empties | `links`: `{door, at, arrive, face}` | `Link_` is the spot where you press F; `Arrive_` is where you stand after coming through, its −Y axis giving the way you face. The coordinator copies these into the manifest. |
| `SecCam_<nn>` | `cameras` | As in `world/L1.json`. Only restricted areas need them. |
| `Zone_<kind>_<name>` box | `zones` | Kinds: `water`, `safe`, `restricted`, `trigger`, `hazard`. |
| `Spot_<kind>_<n>` empty | `spots` | Kinds are listed per area: `locker`, `shop`, `dealer`, `bed`, `puzzle`, `loot`, `monster`, `npc`, `hide`, `toy` and so on. |
| `decor_<name>` | art only | Things you can walk through. |
| `Lamp_Emit`, `Window_Lit`, `Emergency_Emit` materials | art | Toggled by the page, as in part 1. |

**Collision rules:**
- The page's collision is axis-aligned boxes only. Keep walls on the axes where the design allows. An angled or curved wall is a row of small boxes.
- Stairs are one box per step, with a rise of 0.27 m at most, as on L1. The page climbs steps up to 0.46 m.
- Every visible solid has a `COL_` box, and every `COL_` box has something visible, edge walls aside. The layout check from part 1 runs in this direction here.

### Scale

- **Player:** eye height 1.55 m.
- **Rooms:** ceilings 2.8 to 3.2 m; corridors at least 1.6 m wide.
- **One scene at a time.** The page loads one scene and joins scenes by connectors.
  - A store floor is about 52 m by 50 m. Treat that as the most one indoor scene should be, and split anything larger.
  - Each new scene has its floor at y = 0 unless its brief says otherwise.
- **Repetition is instanced** or reuses one mesh: corridor bays, hotel doors, shelves, server racks.
- **Rooms that load when a door opens** (the hotel) are small files of their own, `world/rooms/<layout>.glb` and `.json`, reused behind many doors.

### The connector kit

Build these once, in `blender/kit/`, and link them into scenes. They are the connectors `docs/WORLD.md` names.

| Piece | Used for |
|---|---|
| Painted-sky hall with an EXIT door | Every hall between worlds |
| Elevator car and doors (the Intern's look) | Hotel floors; the apartment to every level |
| Service corridor and freight lift | The hidden network: grocery back of house, the store's backstage, Secret Operations |
| Keycard door and reader | Secret Operations and the grocery's staff door |
| Vent duct, 0.8 m square | Going back in chambers. Crawling is not in the game yet, so build the ducts and leave them shut. |
| Safe house room | Going back in floors and the hotel roof: a shop counter, a stash, a save point, a crafting bench, a respawn pad and a locker |
| Stair door with a lit hallway | Exists in the store's file; reuse it |

## The areas, in build order

### 1. The hotel (the apartment tower)

About 36 scenes. From the bottom: sub-floor pools, lobby, floor 1 (motel), floor 2 (green carpet), floor 3 (apartments), roof. The atrium is the hub and one elevator serves every floor.

| Scene | Size [DEFAULT] | What is in it | Links |
|---|---|---|---|
| `lobby` | 20 m by 22 m, 6 m high, to fit the tower's footprint on the street (x −28 to −8, z −30 to −8) | Front doors, a reception desk, shops, a deli area under a loft, facade doors that do not open (places for later features). Peaceful. `Spot_dealer` ×3 for the shady dealers, `Spot_shop`, `Spot_puzzle` ×2 | Street front doors (`city.street>hotel_lobby`, the tower's door at z −19). A back door past the deli, then a narrow hall, to the atrium (`hotel.lobby>atrium`) |
| `atrium` | 36 m by 36 m, with four galleries stacked at y 0, 4, 8 and 12 | The hub. Each floor has its own section: one gallery each for the sub floor, floors 1, 2 and 3. The elevator shaft runs through all four. | The elevator to every floor (`hotel.atrium>floors`). A one-way door, and the elevator's glitch, into the maze (`hotel.atrium>maze`) |
| `floor_1_lower`, `floor_1_upper` | A corridor 40 m by 2.2 m with rooms on both sides | The motel. 20 openable doors across the two levels, ten a level, joined by a staircase. The corridor is IMG_2999. Hide spots for the Hello Neighbor game: `Spot_hide` in closets and alcoves. | The elevator; the stairs between the two levels (`hotel.floor_1_stairs`) |
| `floor_2_lower`, `floor_2_upper` | The same shape | Green carpet. 20 doors across two levels. | As floor 1 |
| `dining`, `reception`, `key_room` | About 14 m by 10 m each | Floor 2's hand-built key rooms: the dining room (IMG_2903), the reception (IMG_2984), and IMG_2985, whose redesign is the PNG image | Doors off floor 2 |
| `floor_3` | One corridor, 10 doors, one level | The apartments. Peaceful. Every player gets one; the others hold other players, clues or empty rooms. | The elevator; stairs up to the roof |
| `roof` | 24 m by 24 m, open sky | The city skyline at night (an R3 backdrop), a `Spot_puzzle` and a safe house from the kit | Stairs from floor 3 |
| `sub_pool_01` to `sub_pool_11` | About 20 m by 20 m each | Eleven separate pool scenes, peaceful, each with one `Spot_puzzle`. They match B1's poolrooms (white tile, flooded) but are their own pools. `Zone_water` for the water | The atrium's lowest gallery; underwater toward B1 (`hotel.sub_pools>lot.B1`), a long way with many levels between |
| `maze_01` to `maze_07` | About 16 m by 16 m each | The atrium anomaly maze: one scene per photo (IMG_2988, 2989, 2990, 2910, 2986, 3015, 3036). One-way routes; you leave only by solving. | Entered from the atrium or by an elevator glitch; each has one way on |
| `escalators`, `other_stairs` | Connector-sized | The escalators and the other staircase are separate places | Between the atrium's galleries |
| Room layouts: `motel_a`, `motel_b`, `green_room`, `clue_room`, `empty_room` | 4 m by 6 m to 6 m by 8 m | Fifty rooms come from these few layouts. `motel_a` and `motel_b` are the two rooms in the photos (Room 1 and Room 2). The player's own apartment is part 1's `apartment`. | Loaded behind a corridor door when it opens |

- **Tone:** liminal. The lobby, floor 3, the pools and the roof are peaceful. Floors 1 and 2 are where the neighbor hunts.
- **Code keeps:** the neighbor (a hotel resident, and the stalker), the dealers, the elevator's movement and its glitch, door states, and the puzzles' moving parts.
- **Light:** the lobby gets a day and a night set; the corridors are baked at night; the pools get soft even light.

### 2. The grocery, the rest

`main_floor` is in part 1. `docs/WORLD.md`: three scenes, plus a basement, back of house, staff areas, more aisles and a second floor; open by day and abandoned by night.

| Scene | Size [DEFAULT] | What is in it | Links |
|---|---|---|---|
| `aisles` | 48 m by 40 m | The bigger version of the same room: long aisles that repeat, and the red-cart clearing (IMG_3027) in the middle | An opening from `main_floor`'s north side |
| `second_floor` | 30 m by 20 m | A mezzanine: homeware, a closed café and a view down over the aisles | Stairs and an escalator from `aisles` |
| `back_of_house` (in the manifest) | 30 m by 24 m | Stockroom racking, a loading dock, a staff break room, lockers, and a manager's office with camera monitors. `SecCam` here, since it is restricted. The way to Secret Operations is a staff door, a freight lift and a keycard reader. | A staff door from `main_floor`; the freight lift to `secret_ops/service_entry` (`grocery.backhouse>secret_ops`, which needs `keycard_tier_1`) |
| `basement` | 30 m by 20 m | Cold storage, a plant room and pallets | Stairs and the freight lift from `back_of_house` |

- **Light:** two sets each. By day, fluorescent and open. By night, abandoned: freezer glow and emergency lights only.
- **Code keeps:** food, carts, the checkout, camera heads and night threats.

### 3. The mall

About 18 scenes. `entrance` is in part 1. The mall is old and abandoned and also being built, with nobody visible and scaffolding only. Its themed wings are the bookstore, the cinema and entertainment.

| Scene | What is in it |
|---|---|
| `wing_books`, `wing_cinema`, `wing_entertainment` | The three concourses off the atrium, each about 40 m by 14 m [DEFAULT]. Shuttered fronts, scaffolding, dust sheets |
| `bookstore`, `bookstore_desk`, `cinema_lobby` | The shops you can enter |
| `scene_2909`, `scene_3012` | One scene each from IMG_2909 and IMG_3012 |
| `scene_2991`, `scene_3008` | IMG_2991 with IMG_3014 is one scene; IMG_3008 with IMG_3010 is one scene |
| `mirror_bathroom` | A portal and a puzzle. The mirrors are separate objects named `Mirror_<n>`, so the page can make them portals |
| `food_court`, `construction`, `service_corridor` | [DEFAULT] The food court named on the atrium's shopfronts, a scaffolded zone mid-build, and a back corridor for the hidden network |
| `sky_hall_01` to `sky_hall_04` | Painted-sky hall connectors, from the kit |

- **Mannequins** are monster, set dressing and NPCs. Place `Spot_mannequin` where they stand; the page draws them.
- **Light:** every mall scene gets the day set and the emergency set, because the mall locks you in at 20:00.

### 4. The Overworld

Six scenes and a market. The hub is meant to take ten minutes to cross end to end. Today it is the parking lot, which reuses the store's exterior model at y 9.6.

| Scene | What is in it |
|---|---|
| `table_and_chairs` | The spawn: a table and chairs facing the store. It can stay part of the lot; build the set as its own collection. |
| `market` [DEFAULT id] | Stalls for weapons, gear, food, keycards and cosmetics. `Spot_shop` per stall |
| `playground` | Real equipment, each a mini-game: swing, slide, seesaw, merry-go-round, monkey bars, sandbox, spring riders, climbing frame. Each piece gets clear ground around it. The moving parts are separate objects with their pivots set, named `Play_<equipment>_<part>`, so the page can move them. |
| `tree_house` | A puzzle and an entrance to its own addon later (`overworld.treehouse>addon`) |
| `bus_station` | "Just a ride": a small station in place of the lot's shelter |
| `road` | The road to the forest, replacing the signpost walk (`overworld.road>forest`; you arrive in the forest at (0, 0, 6) facing north) |
| `endless_hills` | Hills that never get you further away: one ground tile of about 200 m by 200 m [DEFAULT] that repeats without a seam, with `Spot_toy` for the kickable toys and little puzzles |

- **Also:** hedges for the groundskeepers (`Spot_groundskeeper`), and "more to come" facades that do not open.
- **The edge** is a 2D render (R3).
- **Skies:** `docs/WORLD.md` speaks of four Overworld skies. Their looks are not written down. As a default, render four sky backdrops (clear day, sunset, night, painted) and let the owner replace them.

### 5. The City's extras

The street is code-first (part 1), so these are kits, not layouts.

- **A street segment kit:** a 40 m length of Hallam Row with two building slots, so the street can grow as addons unlock (`street_of_jobs`).
- **`bus_stop`:** the stop's shelter, bench and sign as one set.
- **A depot yard for 41 Hallam Row** [DEFAULT]: the trash truck's yard and the truck itself, for when the route gets a truck.

### 6. Going back in: 15 chambers and 5 safe houses

Five floors of four chambers, top down: L4, L3, L2, L1, B1. A chamber is as big as an original floor, and the existing floor is one of each four, so 15 are new.

- **Ids:** `gbi_<floor>_<n>`, with n from 1 to 4. `gbi_L4_4` and `gbi_L3_1` exist already, made from L4 and L3. 
- **Which chamber the existing floor is** [DEFAULT]:
  - On L4 it is the 4th, because it has the real stairs down.
  - On L3, L2, L1 and B1 it is the 1st: you come down the stairs into the floor you know, then go deeper.
  - So the 15 new chambers are `gbi_L4_1` to `gbi_L4_3`, and chambers 2 to 4 of L3, L2, L1 and B1.
  - The 4th chamber of L3, L2 and L1 is new, so it needs a stair door from the kit. Its stairs arrive in the next floor's real stairwell.
  - `gbi_B1_4` is wave 20, the run's end, and has no stairs down.
- **Shell:** each chamber fits the store's footprint (x −26.3 to 26.3, z −22.35 to 27.35) at its floor's height: B1 −3, L1 0, L2 3.2, L3 6.4, L4 9.6.
- **Look:** three new layouts per floor in that floor's own materials, taken from the store's Blender file: pools for B1, offices for L1, L2's look, white plaster for L3, showroom for L4.
- **Each chamber has:**
  - one arrival and one way on;
  - `Spot_locker` ×1;
  - `Spot_loot`, `Spot_puzzle` and `Spot_object` (the missing objects);
  - `Spot_monster` for the wave, at least 16 m from the arrival.

  The fourth chamber of a floor has the stairs down.
- **Connections:** any mix of vent crawls, elevators, stairs, doors and painted-sky halls, from the kit.
- **Hazards:** crushing walls, lava floor, high tides, toxic gas and moving chainsaw blades. Build each hazard's moving part as its own object, `Hazard_<kind>_<n>`, with empties marking its travel, and a `Zone_hazard` box. The page moves it.
- **Safe houses:** one per floor, from the kit, with a shop, stash, save, crafting, respawn and a locker.
- **Secret Operations reuses these chambers reskinned,** so keep each chamber's materials easy to swap.

### 7. Right Door, Wrong Exit: about 43 new rooms

This game has its own engine (`games/rdwe/`), and its rooms are built in code today (`games/rdwe/scenes/*.js`). How a Blender room loads there is not designed yet; the coordinator will settle it when the first room arrives. Deliver in the same format as everything else.

- **Phase A: remake the seven rooms that exist,** larger and psychedelic: `dining`, `hallway`, `teal`, `teal2`, `flooded`, `trampoline`, `grocery`. Read each room's scene file for its present layout and look.
- **Phase B: the set pieces:**
  - the finale's hide-and-seek map, with computers to hack (`Spot_computer`) and cameras (`SecCam`);
  - the room that repeats, and a door visible from only one angle, which hide the Secret Operations entrance (`rdwe.repeating_room>secret_ops`).
- **Phase C: about 34 more rooms.** `docs/WORLD.md` gives the style but no room list. It is Super Liminal style:
  - object distortion and off-looking objects;
  - perspective shifting;
  - distorted halls;
  - multi-choice navigation;
  - psychological puzzles;
  - environmental storytelling.

  Propose the list as one line and one greybox per room, and dress only the rooms the owner picks.
- **Rules:** every door is different, and exits are fixed (`Link_` per exit). There is no true exit.

### 8. Secret Operations (Project Never Land)

About 12 scenes and the boss. A shooter that reuses and reskins Look Over There's chamber pools, with unique lab and corridor sections.

| Scene | What is in it |
|---|---|
| `service_entry` (in the manifest) | Where the grocery's freight lift and the Intern's pool dive arrive |
| `hidden_entry` (in the manifest) | The one entrance with no clearance, from the repeating room |
| `b2_entry` [DEFAULT] | Behind the laboratory's sealed "B2 · AUTHORISED STAFF ONLY" door |
| `checkpoint_1` to `checkpoint_3` [DEFAULT] | Keycard checkpoints, one per keycard tier |
| `corridors_a`, `corridors_b`, `labs_a`, `labs_b` [DEFAULT] | The unique lab and corridor sections. They are open-ended, with more than one route. |
| `breaker_room` | The breakers you cut to blind the cameras (`Spot_breaker`) |
| `control_room` | A control room with a single chair, and the cell beside it. The cell is a puzzle room you must solve to leave. |
| `registrar_hall` | The boss arena: a long green server hall with a pink stripe on the walls, the control room and cell at one end, and cameras on every wall |

- **For the boss fight,** build these as separate objects the page can change:
  - server racks, `Rack_<n>`, which get shot;
  - floor panels on a grid, `FloorPanel_<x>_<z>`, which get deleted under you;
  - every camera, `SecCam_<nn>`, which can be smashed.
- **Phase 3** needs a second sky backdrop for the arena, glitched.
- **Agents** are the suit character; the page draws them.

## Checks and delivery

As in part 1, with these differences:
- **The layout file comes from Blender**, so each PR includes `world/<scene>.json`, the top-down plan and the exporter's summary: how many colliders, doors, links, zones and spots.
- **Check the exported file before the PR:** `node tools/worlddoc.mjs check world/<scene>.json`. It must print OK.
  - It checks the file's shape.
  - It checks that every link, spot and spawn is somewhere a walker can stand.
  - It checks the file's doors against the manifest's links.
  - Warnings about a new scene or a new link are expected; include its output in the PR.
- **The layout check runs the other way:** it reads the Blender file and fails on a visible solid with no `COL_` box, a `COL_` box with nothing visible, a `Link_` without its `Arrive_`, or an arrival point inside a collider.
- **The Blender session still leaves `index.html`, `shared/`, the manifest and the tests alone.** The coordinator adds the scene and its links to the manifest, walks it in the browser, writes its test and merges.

## Order

Part 1's list comes first. Then one area at a time, greybox PR first:

1. the hotel, starting with the lobby and the atrium;
2. the grocery's four scenes;
3. the mall;
4. the Overworld;
5. the City's kits;
6. the Going back in chambers and safe houses;
7. Right Door, Wrong Exit;
8. Secret Operations.

## What the owner chose on 2026-11-24: the defaults

- **The reference photos** named above (IMG_2903, 2909, 2910, 2984 to 2991, 2999, 3008, 3010, 3012, 3014, 3015, 3027, 3036, and the PNG redesign) are not in the repo. Build each scene from its description; if the photos arrive later, they correct the look, not the layout.
- **The four Overworld skies** are the defaults: clear day, sunset, night and painted, as R3 backdrops. The owner can replace any of them.
- **Right Door, Wrong Exit:** propose the room list, one line and one greybox per room. The owner picks the rooms to dress from the greyboxes.
- **The apartment's window** stays as built: the glass takes the hour's tint, and the street behind it stays a fixed dusk.

Two things the plan builds for that the game cannot do yet: crawling (vents) and swimming (the pool routes). The art is built; the routes stay shut until the game has them.
