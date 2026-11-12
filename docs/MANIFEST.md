# The world manifest

One file says which scenes, floors, puzzles, links and modes exist: `shared/farway.manifest.js`. The game page, the server and the tools all read it, so adding a scene is one edit, not six.

```
shared/farway.manifest.js   the data (edit this)
shared/manifest.js          pure functions: check, build the lookups, merge an addon, evaluate a link's requirements
shared/registry.js          builds the lookups once at load; an invalid manifest stops the game and the server at start
tools/manifest.mjs          check | scenes | links | export
shared/manifest.test.js     the tests
```

## What reads it

| Was written out by hand in | Is now |
|---|---|
| `shared/world.js` `FLOORS` (the server accepts only these scenes) | the scenes marked `multiplayer` |
| `index.html` `SCENES` (which files to load, floor height) | `REGISTRY.pageScenes`, from each built scene's `files` |
| `shared/fuses.js` `GATED`, `shared/switches.js` `SWITCH_FLOORS`, `shared/keypad.js` `KEYPAD_FLOORS` | the scenes with that `puzzle` |
| `shared/power.js` `POWER_SOURCES` | the scenes with `powerSource` |
| `shared/loot.js` `LOOT` (lockers and packs per floor) | each scene's `loot` |
| `server/server.js` `MAX_PLAYERS` | `modes.original.players.max` |

`shared/manifest.test.js` holds the old values as a golden test, so a change to any of them has to be deliberate.

## What it does not hold yet

The puzzle rules (how many fuses, the keypad length), monster counts and the alarm length are still in their own `shared/*.js` files. They move in when a second scene needs different numbers.

## Adding things

**A floor or scene.** Add it to an area's `scenes` with its `files`. For a scene the server should run, add `floorY` and `multiplayer: true`, plus a `puzzle` if it has one. `node tools/manifest.mjs check` tells you what is missing. A scene's id is its name everywhere (`world/<id>.json`, the server's messages), and it must be unique across the whole manifest.

**A link.** Add it to `links`. Give it a `connector` from the list at the top of the file, a `status`, and a `requires` list of flags if it needs any. A built link must have both ends in built areas. The door links in `world/*.json` and the built links here must say the same thing: the check compares them, arrival point and all.

**An addon.** An addon is `{areas, links, flags?, connectors?, modes?}`. `mergeAddon(base, addon)` returns a new manifest and refuses to reuse an area, scene, link or mode id, or to add a link between two base areas. Nothing loads addons from disk yet.

## Statuses

`built` is in the game. `planned` is designed. `reserved` holds a place for an addon. Planned and reserved things are listed (`tools/manifest.mjs links`) but never reach the page or the server.

## The Overworld, v0 (built)

`overworld` is a built area with one built scene, `parking_lot` (`floorY` 9.6: the same ground as L4). Its files are the store and lot models (`world/L4.glb`, `world/Exterior.glb`) and `world/parking_lot.json`, which `node tools/make_parking_lot.mjs` makes from `world/L4.json`: every collider the lot already had, plus a solid block across the store's glass doors, no doors and no cameras. The other Overworld scenes (`playground`, `bus_station`, ...) are listed without files, so they are designed but not on the page.

`lot.L4.front_doors>overworld` is built, `soloOnly`, and `requires: ["original_complete"]`. It is not a door in `world/L4.json` (the glass doors are open once the power is on and the player walks out), so the world-file check only compares links whose connector is `stair_door` or `gate`. `parking_lot` is a page scene and not a `multiplayer` scene, so the server never runs it and a room cannot enter it. Its arrival point is the table and chairs, which are built in `index.html` (`overworldProps`) because no model of them exists yet. If the table moves, change `OW_TABLE` in `index.html`, `SPAWN` in `tools/make_parking_lot.mjs` and the link's `arrive` together; `shared/manifest.test.js` checks that the link and the scene's spawn marker agree.

## The City, v0 (built, session 9)

`city` is a built area with one built scene, `street` (`floorY` 0, files: `world/street.json`, so no model). Its layout (buildings, doors, lamps, the two bus stops) and the day clock are in `shared/city.js`, which the page draws from; `node tools/make_street.mjs` writes `world/street.json` (colliders and markers) from the same layout, and `shared/city.test.js` fails if the file is stale. Two built links, both `bus`, `soloOnly`: `overworld.bus>city` (from `parking_lot`, door `bus_stop`, arrival on the east sidewalk) and `city.bus>overworld` (back to the lot's shelter). The street's arrival point is in the link and in `BUS_STREET` in `shared/city.js` (a test compares them); the lot's shelter is `BUS_LOT`. `bus_stop` stays a planned scene and `jobs` a planned area. The street is a page scene, so the server never runs it.

The clock: a game day is 900 real seconds, it starts at 08:00 on day 1, `CITY.t` counts seconds spent on the street (paused elsewhere, in memory only), stores open 08:00 to 20:00, 20:00 to 24:00 is the grace period, 00:00 to 06:00 is where the danger goes (slice 2; `dangerous()` is ready, nothing uses it yet).

**The apartment (slice 2).** `apartment` is a second built scene of `city` (`world/apartment.json`, made by the same `tools/make_street.mjs` from `APARTMENT` in `shared/city.js`): one room with a bed, a desk with the computer, a window that shows the sky of the hour, and a door. Two built links, `doors`, `soloOnly`: `city.tower>apartment` (the tower's door on the street, always open, opens straight into the apartment because the tower's lobby and floors are the planned hotel area) and `city.apartment>street` (back to the tower's front). Arrival points are in the links and in `shared/city.js` (`APARTMENT.arrive`, `TOWER_FRONT`); a test compares them. The City's clock runs in both scenes (`CITY_SCENES`) and waits while the computer is open. The computer has four pages (mail, news, job search, map), written by the pure `computerPages` in `shared/city.js`; job search lists the five Hallam Row jobs and says applications are not open (slice 3). The night danger and the bed are described next. Not built: saving (the bed only skips the night), hunger.

**The night danger.** From 00:00 to 06:00 one stalker walks the street (rules in `shared/city.js`: `stalkerStep`, `stalkerSpawn`, `inView`, tested; drawn and driven in `index.html`). It appears 14 to 28 m up the street, out of sight, about 6 s after midnight or after you step out; it does not move while you look at it (a 38 degree cone either side of where you face, with a clear line), creeps at 5.5 m/s when you do not (faster than a walk at 4, slower than a run at 7.5), cannot be killed (it is not one of the floor's monsters), and if it reaches you (1.5 m) you black out and wake in your apartment at 06:00 on the same day. The apartment is safe, the bus does not run at night, and the tower door stays open. The bed (F by it) sleeps from 20:00 to 06:00 the next morning and says you are not tired by day. Warnings: evening (20:00), midnight, dawn. No permanent death and no penalty in v0. 20:00 to midnight stays the grace period.

**The Intern's job (slice 3).** Applications use one shared quiz engine, `shared/application.js` (pure, tested): a quiz is rounds of items to drag into bins, a graded round answered wrong is a rejection, all graded rounds right is an acceptance, an ungraded round (the intrusive questions) only has to be complete, one application at a time, and a rejection locks that job until the next game day. Only the Intern has a quiz so far (`QUIZZES.intern`: sort tasks, match a form to a day, then "who would notice if you were gone"); the other four Hallam Row jobs say "not hiring yet". You apply from the Job search page of the apartment computer. Acceptance sets the flag `job_intern` (declared in the manifest's `flags`, kept in the browser under its own name like `original_complete`, read by `heldFlags`). The built link `city.666>intern` (from the street's door `w666`, solo only, `requires: ["job_intern"]`, `returnTo` the door's front) is what lets 666 Hallam Row's door start a shift: it runs the existing Intern game through `enterGame` and the game's `intern-ending` brings you back to the door. The clock waits during the shift, and the door is shut after 20:00 like the other stores. Not in this slice: pay, anything to do with how well you did in the game, the other four jobs' quizzes, the accepted flag in a database (the backend is session 5).

## Gate return (fixed)

The link on `DoorLeaf_Gate_RDW` in `world/L4.json` had no `scene`, and `enterGame` returned with `loadScene(l.scene || S.id)`. After the passage `S.id` is `T`, which has no scene file, so the way back from Right Door, Wrong Exit stayed stuck on the passage (reproduced in `tools/gates_test.mjs`; the Intern's gate was fine because its link has `scene`). Now the link has `"scene": "L4"` and `enterGame` returns to the manifest's `returnTo`. The "That door does not open in a room" toast reads the gate's `soloOnly` flag.

## Commands

```
node tools/manifest.mjs check      # exit 1 on any error
node --test shared/manifest.test.js
```
