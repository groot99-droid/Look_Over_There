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

## Going back in, slice 1 (built)

The area `gbi` holds the chambers. A chamber is a scene with a `chamber: {floor, index, wave: {monsters, kind}, stairsDown?, next?}` field: `floor` and `index` place it in the run (wave number = the floor's position in the mode times `chambersPerFloor`, plus `index`), `wave` is what starts when you step in, and `stairsDown` and `next` name the door and the chamber it leads to. `REGISTRY.chamber(id)` returns that with the wave number and floor height, or null for any other scene. The mode's `startChamber` is where the Overworld's options screen sends you. The mode stays `planned`, so the server keeps answering `soon`; the chambers are page scenes (no `multiplayer`), so no room runs them.

`gbi_L4_4` is the L4 model with the store sealed (like the parking lot), and `gbi_L3_1` is the L3 model. Their world files are made by `node tools/make_chambers.mjs` from `world/L4.json` and `world/L3.json`: the game gates are unlinked, only the stairs-down door of `gbi_L4_4` has a link, and `gbi_L3_1` has none (the way back up is shut, the way down is not built). `worldFromDoc` takes `{floor, art}` for a chamber, so the L4 rule that keeps monsters out of the parking lot still holds. The link `gbi.gbi_L4_4.stairs_down` arrives on L3's floor (6.4); the Original's L4 to L3 link arrives at y 9.6 and falls onto the floor, which this slice leaves as it is.

## Gate return (fixed)

The link on `DoorLeaf_Gate_RDW` in `world/L4.json` had no `scene`, and `enterGame` returned with `loadScene(l.scene || S.id)`. After the passage `S.id` is `T`, which has no scene file, so the way back from Right Door, Wrong Exit stayed stuck on the passage (reproduced in `tools/gates_test.mjs`; the Intern's gate was fine because its link has `scene`). Now the link has `"scene": "L4"` and `enterGame` returns to the manifest's `returnTo`. The "That door does not open in a room" toast reads the gate's `soloOnly` flag.

## Commands

```
node tools/manifest.mjs check      # exit 1 on any error
node --test shared/manifest.test.js
```
