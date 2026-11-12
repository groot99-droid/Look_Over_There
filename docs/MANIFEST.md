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

## Going back in, slice 1 (built)

The area `gbi` holds the chambers. A chamber is a scene with a `chamber: {floor, index, wave: {monsters, kind}, stairsDown?, next?}` field: `floor` and `index` place it in the run (wave number = the floor's position in the mode times `chambersPerFloor`, plus `index`), `wave` is what starts when you step in, and `stairsDown` and `next` name the door and the chamber it leads to. `REGISTRY.chamber(id)` returns that with the wave number and floor height, or null for any other scene. The mode's `startChamber` is where the Overworld's options screen sends you. The mode stays `planned`, so the server keeps answering `soon`; the chambers are page scenes (no `multiplayer`), so no room runs them.

`gbi_L4_4` is the L4 model with the store sealed (like the parking lot), and `gbi_L3_1` is the L3 model. Their world files are made by `node tools/make_chambers.mjs` from `world/L4.json` and `world/L3.json`: the game gates are unlinked, only the stairs-down door of `gbi_L4_4` has a link, and `gbi_L3_1` has none (the way back up is shut, the way down is not built). `worldFromDoc` takes `{floor, art}` for a chamber, so the L4 rule that keeps monsters out of the parking lot still holds. The link `gbi.gbi_L4_4.stairs_down` arrives on L3's floor (6.4); the Original's L4 to L3 link arrives at y 9.6 and falls onto the floor, which this slice leaves as it is.

**Hunger and the grocery (slice 4).** The `grocery` area is built with one scene, `main_floor` (`world/main_floor.json`, made by `tools/make_street.mjs` from `GROCERY` in `shared/city.js`): one hall with four shelf units (one food each), a cart corral by the door and a checkout. `back_of_house` stays planned. Two built `doors` links, solo only: `city.street>grocery` (the street's grocery door; it was a planned link with this id) and `grocery.main_floor>street` (back to the door's front, `GROCERY_FRONT`). The grocery keeps store hours (08:00 to 20:00); at 20:00 you are shown out. The City's clock runs there (`CITY_SCENES`). The rules are in `shared/needs.js` (pure, tested): hunger 0 to 100 starting at 80, draining over 36 game hours awake and at half rate asleep (never below 5 from sleep), warnings at 30 and 10, fainting at 0 (you wake in your apartment at 06:00 with 25); money starting at $20, $10 per finished Intern shift; 2 items in your hands, 8 in a cart; the checkout pays and the food goes to the pantry; leaving with unpaid items puts them back; the fridge in the apartment (a new collider in `world/apartment.json`) feeds you the most filling item you have. The computer has a fifth page, Bank. Hunger and money show under the clock. All of it is in memory: a reload starts again at 80 and $20, like the clock.

**Pay by performance (slice 5).** A shift at the Intern pays by how it went, as `docs/WORLD.md` says. When the game ends it now posts its result with `intern-ending` (`games/intern/src/main.js`): `{ending, conformance, dissonance, friction, early}` from its own state. `enterGame` returns that message to the caller (a few lines in the launcher), and `shiftPay` in `shared/pay.js` (pure, tested, never trusts the message: every field is checked and clamped) turns it into money: a base by ending (ASSIMILATION $20, RETAINED $14, PENDING $8, EXPULSION $4), +$1 per point of conformance above 0, -$1 per point of friction, between $0 and $30; quitting with the game's own bail pays $0; a missing or malformed result is a PENDING shift. The bank page shows the last shift's pay and ending. The numbers are defaults for the owner.

**The other four jobs (slice 6).** Every Hallam Row job now has an application on the shared quiz engine (`QUIZZES` in `shared/application.js`: `trash` for 41, `museum` for 108, `lab` for 214, `factory` for 330), each with two graded rounds and one ungraded intrusive round, and each sets its own flag (`job_trash`, `job_museum`, `job_lab`, `job_factory`, declared in the manifest's `flags`, kept in the browser like `job_intern`). You may hold more than one job; one application at a time still holds. Their job games are not built, so a shift is a stub screen (`STUB_SHIFTS` and `canStartStub` in `shared/pay.js`): accepted and within the job's hours, its street door offers the shift; working it takes the job's hours off the City's clock (4 for the trash depot, the lab and the factory, which start 08:00 to 16:00; 3 for the museum night guard, who starts 20:00 to 21:00 through the shut door and is done before midnight), hunger drains for them, and it pays a flat amount ($10, $14, $12, $16). There is no manifest link for these shifts yet: a stub is a screen, not a place, and the `jobs` area is planned. When a job's game is built, its shift becomes a link like `city.666>intern`.

**Saving the City (slice 7).** "A bed saves and skips the night." F at the apartment's bed saves: by day it only saves; from 20:00 it also sleeps until 06:00 and saves at dawn. The save is one browser key, `city_save` (`shared/save.js`, pure, tested): the clock and day, hunger, money, the fridge, the last pay, and the applications (rejections and acceptances). Not saved: the cart, an application in progress, where you stand, the stalker. At start the page reads it back through `readSave`, which never trusts it: a missing, corrupt or other-version save is ignored (the City starts fresh, as before), numbers are clamped and unknown foods or jobs are dropped. Anything after the last save is lost on a reload. Job flags are still kept the moment an application is accepted. With storage blocked the bed does not claim to save. There is no New Game control yet: clearing the site's data starts over.

**City anomalies (slice 8).** No manifest change: the three anomalies are props of the `street` scene (`shared/anomalies.js`, pure, tested), drawn by the page and absent from `world/street.json`, so they collide with nothing and the world-file check is unchanged. The sign's pass count lives for the page only.

**New Game (slice 9).** New Game, on the apartment computer's SYSTEM page, removes `city_save` and the five job flags (`job_intern`, `job_trash`, `job_museum`, `job_lab`, `job_factory`: `NEW_GAME_KEYS` in `shared/save.js`), so every link that `requires` a job is shut again until you are hired anew. It never removes `original_complete`, which belongs to the Original.

**The stalker follows (slice 10).** No manifest change. Across the `city.tower>apartment` and `city.apartment>street` links the stalker's state is carried (`carryStalker` in `shared/city.js`): kept while it is out at night, reset on any other link or by day.

**The trash route (slice 11).** No manifest change: the trash job's shift is played on the `street` scene itself (`shared/trash.js`, pure, tested), so it needs no link of its own. Leaving `street` by any link ends the shift. The museum, lab and factory shifts are still stubs; each becomes a link (like `city.666>intern`) or a street route when its game is built.

## Gate return (fixed)

The link on `DoorLeaf_Gate_RDW` in `world/L4.json` had no `scene`, and `enterGame` returned with `loadScene(l.scene || S.id)`. After the passage `S.id` is `T`, which has no scene file, so the way back from Right Door, Wrong Exit stayed stuck on the passage (reproduced in `tools/gates_test.mjs`; the Intern's gate was fine because its link has `scene`). Now the link has `"scene": "L4"` and `enterGame` returns to the manifest's `returnTo`. The "That door does not open in a room" toast reads the gate's `soloOnly` flag.

## Commands

```
node tools/manifest.mjs check      # exit 1 on any error
node --test shared/manifest.test.js
```
