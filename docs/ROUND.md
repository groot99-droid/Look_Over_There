# The round: requirements

A **round** is one play-through of a **mode** by a **room** of 1 to 10 players: from the ready-up to the results. This file says what a round must do for Farway.

- **BUILT**: it is in the game now and a test covers it (`tools/mp_test.mjs`, `tools/stairs_test.mjs`, `server/*.test.js`, `shared/*.test.js`).
- **CHANGE**: it exists and must change.
- **NEW**: nothing exists yet.
- **OPEN**: it needs a decision from the owner first. The question is in the "Decisions" list.

Modes live in the world manifest (`shared/farway.manifest.js`, `modes`): `original` is built, `going_back_in` is planned. A mode names its area, its floors in order, its room size and how a round finishes. Docs: `docs/MANIFEST.md`, `docs/GAMEPLAY.md`, `docs/SESSIONS.md` (who builds what).

## Round states

```
join (room code) -> LOBBY (pick a character, ready up)
  -> everyone ready -> COUNTDOWN 10 s -> PLAYING (stages, floor by floor)
  -> everyone still in the room is out -> RESULTS -> [Play again] or [Walk out to the Overworld]
A player who joins during PLAYING skips the lobby and spawns with the group. A round runs until the room empties.
```

## A. The round today and what it needs

| ID | Requirement | Status | How we know |
|---|---|---|---|
| RND-1 | A room is joined by code. It holds `modes.<mode>.players.max` players (10), each with their own colour, and refuses more with `{t:"full"}`. | BUILT | `server/server.test.js` fills a room |
| RND-2 | Lobby: pick one of five characters, ready up. When everyone is ready a 10 s countdown starts, then the round starts for the room. Someone who joins mid-round skips the lobby. | BUILT | `tools/mp_test.mjs` |
| RND-3 | The stages are the mode's floors, in order. A gated floor's stair door stays locked until its puzzle is solved: fuses (B1), switches (L1), a keypad (L2). L3 has none. L4 needs power. | BUILT | `shared/*.test.js`, `tools/stairs_test.mjs` |
| RND-4 | On L4 the store's glass doors open when the power is on, then a 60 s alarm runs. Walking out onto the parking lot is your finish. | BUILT | `shared/finish.test.js`, `shared/power.test.js` |
| RND-5 | The round ends when everyone still in the room is out. Place is the order you left in. Someone who leaves the room does not hold it up. Solo ends the moment you walk out. | BUILT | `shared/finish.test.js` |
| RND-6 | A caught player is downed, not dead. A teammate revives them in 4 s. After 45 s they wake at the stairs they came up. Solo: die, wait 3 s, respawn somewhere random. | BUILT | `server/playerstate.test.js` |
| RND-7 | The server owns each player's HP, rounds, beacons, cloak and down state. A client sends intents and cannot give itself anything. | BUILT | `server/playerstate.test.js` |
| RND-8 | Monsters run on the server at 20 Hz, one simulation per room and floor that has a player. Snapshots go out at 10 Hz. | BUILT | `server/floors.test.js` |
| RND-9 | A round must never name a floor that is not a multiplayer scene of the manifest. | BUILT (session 1) | `shared/manifest.test.js`, `server/server.test.js` |

## B. What Farway adds

### Modes and parties

| ID | Requirement | Status | How we know |
|---|---|---|---|
| RND-10 | A client joins with a `mode`. The server reads the mode's floors, room size and finish from the manifest, and a room keeps one mode for its life. | BUILT | `server/server.test.js`: `original` takes its floors, cap and finish from the manifest; `going_back_in` is refused with `{t:"refused",reason:"soon"}`, an unknown mode with `unknown_mode`. |
| RND-11 | The room size comes only from the manifest (10). The server refuses to start if it has fewer player colours than the size. | BUILT | `server/server.js` throws at start if colours are short; `server/floors.test.js` simulates a full room. |
| RND-12 | A party is a room (the same mode and the same code). Where you are is separate from who you party with: ten players can split across floors, chambers and games in any number of groups, and each player can join or leave a place at any time. A player can jump to a friend. | PART BUILT: the party key is mode plus code, and `{t:"goto",to:id}` returns a friend's place and spot: a floor, or a page scene the manifest marks `presence` (the parking lot, Hallam Row, the apartment), refused with the missing flag if you may not enter it. In the page, P lists the party with where each player is and a Go button (session 17; `tools/world_mp_test.mjs`). Rooms cannot enter chambers, games or the City's other interiors yet. | Ten clients in one party stand in three different places, and a late joiner goes to a friend's place. |
| RND-13 | The server can list open rooms for a mode: code, mode, players, phase, floor furthest along. | BUILT | `GET /rooms?mode=original` returns only open, non-full rooms. |
| RND-14 | Until RND-15 lands the two game gates are solo only. A manifest link marks this with `soloOnly`, and the page reads the flag instead of hard-coding it. | CHANGE | A test asserts the toast comes from the manifest flag. |
| RND-15 | Co-op inside a game (Right Door, Wrong Exit, the Intern) is optional, never required. A player may enter a game alone or with friends, and friends can pop in at any time. Each game runs one instance per party, and the players inside it see each other. A game's gate stops being solo only once the game supports this. | BUILT, all four slices (section D): the manifest and server hold game places (`coop` areas, `REGISTRY.gamePlaces`, `goto` through them, a player in a game does not hold the finish), and Right Door, Wrong Exit is coop: a room can enter it, the players of one room of the game see each other, and `tools/games_party_test.mjs` has two clients enter, meet and leave. The Intern is coop too (slice 4): its gate is no longer `soloOnly`, the players of one stage see each other where they stand in the same room of the building, and `tools/intern_party_test.mjs` has two clients enter, meet, leave and join each other at a later stage | Two clients enter each game separately and meet in one instance. |

### Results, deaths and ranking

| ID | Requirement | Status | How we know |
|---|---|---|---|
| RND-20 | The server counts per player: downs, **deaths** (a down nobody revived: the 45 s ran out, or any down in solo play), **revives given**, shots, shots that hit, beacons thrown, cloak seconds, time on each floor. Today it keeps none of these. | BUILT, except cloak seconds (not counted yet) | `server/playerstate.test.js` covers each counter. |
| RND-21 | At the end the server builds one **run record**: `{roomCode, mode, startedAt, endedAt, floors: [{scene, ms}], players: [{name, char, place, ms, downs, deaths, revives, shots, score}]}`. Only the server writes it. For now it goes to the server log as one JSON line without names; a database comes with session 5. | BUILT (the record has no names; solo play has no server, so it is not logged) | A test plays a fake round and checks the record. |
| RND-22 | The results screen shows place, time, deaths, revives and score, your best time on this browser, and a welcome to Farway the first time you finish the Original. | BUILT (shows place, time, deaths, revives, score, best; the browser check is `tools/results_test.mjs`, solo only) | A browser test finishes a solo round and reads the screen. |
| RND-23 | Finishing the Original for the first time sets the flag `original_complete`. It is stored on this device first and moves to the account when accounts exist. | BUILT (stored on this browser only) | The flag survives a reload. |
| RND-24 | After the results the player can walk out to the Overworld. The link `lot.L4.front_doors>overworld` requires `original_complete`. | BUILT, solo and in a room (the walk out is offered on the results screen once the flag is held; `tools/overworld_test.mjs`). In a room the lot is a `presence` scene: the server relays who is there and where and runs nothing, and it lets a player in only with the flag, which it knows for itself once that player has finished a round in the room (`server/presence.test.js`, `tools/world_mp_test.mjs`) | `tools/manifest.mjs links` shows it open once the flag is held. |
| RND-25 | Ranking is online and counts runs from the whole game. Boards are kept apart by mode and by group size: solo, 2 to 4, 5 to 10. Whether a board ranks by time or by score is open. | NEW | `docs/BACKEND.md`; Decision 1 (time or score) |
| RND-26 | A run time is accepted only from a run record the server made. A client cannot send a time. | NEW | A test posts a made-up time and it is refused. |
| RND-27 | Revives count toward a player's total score and deaths count against it. Formula: 1000, plus 150 per revive, minus 100 per death, minus 1 per 5 s of round time, never below 0. A board ranks by score, the faster time breaking a tie; the results screen keeps the order players walked out in, with each score beside it. | BUILT and confirmed 2026-11-24 (the owner left it to the coordinator): `SCORE` and `rankBoard` in `shared/finish.js`. No online board exists yet | A test scores a made-up run; another ranks a board. |

### Safety and load

| ID | Requirement | Status | How we know |
|---|---|---|---|
| RND-30 | A finish is accepted only from L4 with the power on. | BUILT | `server/server.test.js` |
| RND-31 | The server rejects puzzle claims that the floor's state does not allow (a fuse you are not near, a wrong code, a switch already on). | BUILT | `shared/*.test.js` |
| RND-32 | The server tick averages under 5 ms with a full room. It measured 0.31 ms with 8 bots. Measure again at 10. | BUILT at 8, CHANGE at 10 | `node tools/bots.mjs 8` prints the tick time. |
| RND-33 | Each socket has a message budget (a burst of 240, 90 a second, a kick past 600). | BUILT | `server/server.test.js` |

## C. Going back in (partly built: each requirement's status is in the table)

A 20-wave run: 5 floors, 4 chambers each, top down: L4, L3, L2, L1, B1. A chamber is as big as an original floor.

| ID | Requirement | Status | How we know |
|---|---|---|---|
| GBI-1 | The mode `going_back_in` lists its floors top down, `chambersPerFloor: 4` and `waves: 20`. Version 1 has 4 chambers per floor, so no randomness yet. The existing floor is one of the four: the 4th on L4 (it has the real stairs down) and the 1st on L3, L2, L1 and B1 (the stairs from above arrive in its real stairwell) [MY CALL for L2, L1 and B1]. The manifest allows one chamber per floor and index. | PART BUILT: the mode has these and a `startChamber`; 2 of the 20 chambers exist | Manifest check, `shared/manifest.test.js`. |
| GBI-2 | A chamber is a scene of the manifest. The 4th chamber on each floor has the stairs down. Chambers join with a mix of vent crawls, elevators, stairs, doors and painted-sky halls. | PART BUILT: two chambers, joined by stairs, alone and in a room. The walk to the bottom floor is not built. | `tools/gbi_test.mjs` walks from the Overworld through the stairs; `tools/gbi_mp_test.mjs` takes them with two players. |
| GBI-3 | The wave starts when the players enter the chamber. The rest is quiet time: objects to find, puzzles, loot, defences to build. A chamber is cleared when its objectives are done. | PART BUILT: the wave starts on entry (alone; in a room, once, when the first player steps in). Cleared by kill count only; the other objectives are not built. | `shared/gbi.test.js`, `tools/gbi_test.mjs`, `server/gbi.test.js` |
| GBI-4 | Unkillable threats are environmental (crushing walls, lava floor, high tides, toxic gas, chainsaw blades). Special entities come later. | NEW | One hazard per chamber type. |
| GBI-5 | Doors can be closed, trapped or barricaded, and nothing else. Players can crawl into vents. Monsters never use vents. | PART BUILT, solo only: a chained supply cage in every chamber and a chained door where one is safe to chain (session 26, `shared/barricade.js`); only the rebar shear opens them. Vents are not built. | `shared/barricade.test.js`, `tools/shear_test.mjs` |
| GBI-6 | A safe house on every floor holds a shop, a stash, a save, crafting and a respawn point. | NEW | |
| GBI-7 | A locker (one per safe house and one per chamber) shows your loadout and lets you change it. After you die it returns your weapons and gear for free. It does not return ammo, consumables or perks. Those are bought back at the Market or a safe house. In the game it is called the **Lost and Found** (decided 2026-11-24); the one-time loot lockers on B1 keep the name "locker". | PART BUILT: one per chamber, alone and in a room (each player's loadout is kept by the server); no safe house, no Market | `tools/gbi2_test.mjs` dies and checks what the locker returns; `server/gbi.test.js`, `tools/gbi_mp_test.mjs` |
| GBI-8 | Lethal weapons come from the arsenal (ten weapons, three consumables). Each needs its own ammo rule. The ray, the cloak and the beacon stay non-lethal. Q and E (LB and RB) are consumable slots. | PART BUILT: five weapons (the hunting crossbow; the pneumatic bolt driver, stun baton, moth jelly dart and propane flamethrower from sessions 19 to 22, solo only), the two-weapon carry cap, and the Q/E slots with the three consumables. Not built: the rocket launcher, laser dissector, rebar shear, frequency horn and gravity gauntlet (rules proposed in `docs/ITEMS.md`). | `shared/crossbow.test.js`, `shared/driver.test.js`, `shared/baton.test.js`, `shared/dart.test.js`, `shared/flame.test.js`, `shared/loadout.test.js`, `shared/consumables.test.js`, `tools/gbi2_test.mjs`, `tools/gbi3_test.mjs`, `tools/driver_test.mjs`, `tools/baton_test.mjs`, `tools/dart_test.mjs`, `tools/flame_test.mjs` |
| GBI-9 | Money comes from clearing chambers and from kills and revives. Level comes from achievements. Money and items are shared with the rest of the game. Progress is its own save. | NEW | |
| GBI-10 | Per-run score goes to an online leaderboard, with personal and overall bests. | NEW | `docs/BACKEND.md` |
| GBI-11 | The 20 waves stay 20 when floors are added, by sampling. | NEW | |

### Session 8 plan: Going back in, in slices (solo only)

| Slice | GBI items | Status |
|---|---|---|
| 1 | GBI-1 (the mode names its first chamber), GBI-2 (two chambers as manifest scenes, stairs down between them), GBI-3 (the wave starts on entry) | BUILT, solo only: `tools/gbi_test.mjs`, `shared/gbi.test.js` |
| 2 | GBI-7 (the loadout locker), GBI-8 for one weapon: the hunting crossbow with its own ammo rule | BUILT, solo only: `shared/crossbow.test.js`, `shared/loadout.test.js`, `tools/gbi2_test.mjs`. The Q/E consumable slots are NOT built (they still say empty) |
| 3 | GBI-8's consumable slots: Q and E, with the flash-vial, the land mine and the tripwire | BUILT, solo only: `shared/consumables.test.js`, `tools/gbi3_test.mjs` |
| 4 | GBI-8: the pneumatic bolt driver (`docs/ITEMS.md` 4.1), the first weapon that hurts instead of killing: monsters get health (`hp` in `world/monsters.json`, `MonsterSim.hurt`) | BUILT, solo only: `shared/driver.test.js`, `shared/monsters.test.js`, `tools/driver_test.mjs`. Key 5 holds it; the locker panel has a fourth gear row, so the E slot's key moved from 4 to 5 |
| 5 | GBI-8: the stun baton (`docs/ITEMS.md` 4.4), and the arsenal's two-weapon carry cap with weapon slots on keys 4 and 5 | BUILT, solo only: `shared/baton.test.js`, `shared/loadout.test.js`, `tools/baton_test.mjs`. The baton starts in the locker (you carry two arsenal weapons at most); the locker's E-slot key is now 6 |
| 6 | GBI-8: the moth jelly dart (`docs/ITEMS.md` 4.9) and the Slowed and Jellied statuses | BUILT, solo only: `shared/dart.test.js`, `shared/monsters.test.js`, `tools/dart_test.mjs`. It starts in the locker with the baton (two weapons at most); the locker's E-slot key is now 7 |
| 7 | GBI-8: the propane flamethrower (`docs/ITEMS.md` 4.3) and the Burning status | BUILT, solo only: `shared/flame.test.js`, `shared/monsters.test.js`, `tools/flame_test.mjs`. It starts in the locker (two weapons at most); the locker's E-slot key is now 8 |
| 8 | GBI-8: the frequency horn (`docs/ITEMS.md` 4.8) and the knockback and `shove` it needs | BUILT, solo only: `shared/horn.test.js`, `shared/cone.test.js`, `tools/horn_test.mjs`. It starts in the locker (two weapons at most); the locker's E-slot key is now 9 |
| 9 | GBI-8: the almond water rocket launcher (`docs/ITEMS.md` 4.5) and `shared/flight.js`, the projectile shared with the dart | BUILT, solo only: `shared/rocket.test.js`, `tools/rocket_test.mjs`. It starts in the locker with one rocket (two weapons at most); the locker's E-slot key is now 0 (the tenth row) |
| 10 | GBI-8: the laser pointer dissector (`docs/ITEMS.md` 4.6) | BUILT, solo only: `shared/laser.test.js`, `tools/laser_test.mjs`. It starts in the locker (two weapons at most); the locker's E-slot swap is now the E key |
| 11 | GBI-8: the hydraulic rebar shear (`docs/ITEMS.md` 4.7, the owner's design: four fresh cuts, then worn) and GBI-5's barricades | BUILT, solo only: `shared/shear.test.js`, `shared/barricade.test.js`, `tools/shear_test.mjs`. It starts in the locker (two weapons at most); it is the eleventh locker row, which has no number key (click it) |
| left | GBI-8's last weapon (the gravity gauntlet), GBI-4 hazards, GBI-5 vents and the other barricades, GBI-6 safe house, GBI-9 to GBI-11, and rooms running the mode (the server still answers `{t:"refused",reason:"soon"}`) | NEW |

What slice 1 does: from the Overworld's store-doors options screen, "Going back in" loads `gbi_L4_4` (the 4th chamber of L4, which is the L4 model with the store sealed) as wave 4 of 20, and the wave (3 monsters, 16 m or more from you) starts as you land. Its stairs-down door leads to `gbi_L3_1` (the L3 model; wave 5, its own 3 monsters). That chamber's way down and the 14 other chambers are not built. The chamber's wave number is its floor's place in the mode times four plus its index. The stairs are open from the start: there are no clear rules yet (objects, puzzles, kill count, timer), so "cleared" is not checked. Death is the solo rule (respawn at a random spot in the same chamber).

What a room needed to run the mode is done (session 16, below): the chamber scenes are `multiplayer` scenes the server's floor sims run, the server starts each wave, the mode's `status` is `built`, and the lobby's "GOING BACK IN" button is enabled.

### Session 16: Going back in in a room

A room joined with mode `going_back_in` (party key `going_back_in:CODE`, up to 10) starts everyone together in the mode's `startChamber`. The round has no end yet (no finish, no run record, no score): it lasts until the room empties.

| Slice | What | Status |
|---|---|---|
| 1 | The server runs each chamber as a floor (`server/floorsim.js`, `chamber`). The wave (`shared/gbi.js`, the same plan as alone) starts once, when the first player steps in, at least 16 m from them; everyone in the chamber is told its monsters (`wave`: each as `[wid, x, z]`), and follows the same snapshots. A chamber is kept for the life of the room and stands still while nobody is in it. The stairs-down door leads to the next chamber. | BUILT: `server/gbi.test.js` (ten clients, one wave), `tools/gbi_mp_test.mjs` (two pages) |
| 2 | The server owns the crossbow (`bolt`: bolts, the reload, the kill), each kill is for the life of the room (`kill`, by `wid`), the wave is cleared when all its monsters are dead, and the locker's loadout is each player's own (`gear`; the `me` message carries `carry` and `bolts`). | BUILT: the same two files |
| 3 | The Q and E consumables: the server counts them (`me.kit`), a flash-vial stuns where it lands (`use` slot 0, `flash`), a land mine or a tripwire is set where the server has you, shown to everyone (`trap`), and goes off on the server (`sprung`, then `kill`). The E slot's choice is made at the locker (`gear` with `a: "e"`). | BUILT: the same two files |

What the server owns in a room: where the wave starts and its monsters, health, the ray's rounds, the bolts, the loadout, the consumables, kills, traps and the cleared flag. What stays on the page: drawing, the locker's place (seeded from the scene, so the same for everyone; the server does not check you stand at it, as it does not for ammo packs), the first guess of a bolt's beam, and where a flash-vial lands (the server only checks it is within the throw).

Death in a room: you are downed first and a teammate can lift you (nothing is lost). If nobody does within the down time, that is a death: you get up at a random spot in the same chamber, your gear is in the locker, and your rounds, bolts, beacons and consumables are gone (`docs/WORLD.md`, "Death in Going back in").

Not built: waves that scale with the party (every wave is the manifest's count, 3; a suggestion is in the PR), a finish, score and run record for the mode, the 18 other chambers, the Market and safe houses.

**Slice 2 rules (defaults the owner may change).**
- *Crossbow:* its own ammo, bolts, not rounds. One per shot, at most 6 carried, 4 at the start (the Market does not exist, so the crossbow starts in your hands), +2 from each ammo pack you pick up while you carry it, 1.8 s reload between shots. A bolt that hits kills the monster for good (the ray still only banishes). A shot makes half the ray's noise. Key 4 holds it.
- *Locker:* one per chamber, placed like a pack, opened with the action button (X / E). A panel lists the ray, the cloak and the crossbow: carry one or leave it in the locker (keys 1 to 3, a click, or D-pad and A). The game pauses while it is open.
- *Death:* all your gear goes to the locker, and ray rounds, bolts and beacons are gone. Walk to a locker and take the gear back for free; the ammo does not come back. A beacon is counted as charges, so it is lost like ammo (the doc lists it as gear; say if you want the device kept).
- *Kills:* a kill is counted, and killing every monster of the wave clears it (toast). That is the only clear rule so far.
- *Name:* the **Lost and Found** on screen (the panel, the prompt and the toasts), settled 2026-11-24. The code still calls it the station and the loadout locker, and these docs say "the locker".

**Slice 3 rules (defaults the owner may change).** The doc names the three consumables but not which slot holds what, nor their numbers.
- *Q (support): the phosphor-core flash-vial.* Thrown up to 6 m ahead (it stops at a wall); every monster within 6 m of where it lands is stunned for 6 s. It kills nothing. Max 3, start 2.
- *E (combat / objective): the almond water land mine or the nail-bomb tripwire, chosen at the locker (key 4, or the E row with D-pad and A).* The mine is set down where you stand, arms after 1.5 s, and kills the one monster that comes within 1.2 m. Max 3, start 2. The tripwire arms after 0.5 s; a monster within 2 m sets it off and every monster within 3 m dies; the blast is loud, so monsters within 25 m go and look. Max 2, start 1. Both count as kills toward the wave. A trap is yours to walk into too: nothing here hurts the player (monsters are the only target in v1).
- *Refills:* each ammo pack adds one flash-vial and one of the E item, up to the cap. The Market does not exist yet, so there is no other source.
- *Death:* all consumables are gone and the locker does not return them (docs/WORLD.md). Traps already set stay until a monster springs them, and are cleared when you change chamber.
- *Controls:* Q and RB-side E are as `docs/GAMEPLAY.md` says (LB / Q support, RB / E combat). `tools/controls_test.mjs` still passes. In the Original the slots stay empty.

## D. Co-op inside the games (design note, session 11)

Status: **built, slices 1 to 4.** Written first, as `docs/SESSIONS.md` asks, so the owner can change a default before it is built. Everything marked *Default* is what the build will do unless told otherwise.

**What exists.** A room is a party of up to 10 (RND-12). A player's place is separate from the party. Since session 17 a place can be a *presence scene*: the server relays position snapshots between the players whose `scene` string is the same and runs no rules there (`presencePlace`, `presenceSnap` in `server/server.js`; `REGISTRY.presence` and `REGISTRY.canReach` in `shared/registry.js`). The two games are solo only today: `soloOnly` on their gate links, and the page refuses the door in a room. Each game draws itself in its own renderer, hidden behind the page's: Right Door, Wrong Exit (`games/rdwe/walk.js`, a chain of rooms walked one after another, `enterGame` can start the chain at any room) and the Intern (`games/intern/`, an iframe with its own three.js, nine spine stages S0 to S8).

**The idea.** A game room is just one more presence scene. Nothing about the game's own rules moves to the server.

1. **A place inside a game.** `rdwe:<room>` (`rdwe:dining`, `rdwe:teal`, ...) and `intern:<stage>` (`intern:S3`). The manifest lists them as the `places` of the game's area, each with `presence: true`; `REGISTRY.canReach` reaches a game place through the gate link (once its `soloOnly` is dropped) and, from there, any place of the same game. The server accepts a player's place only if `canReach` says so, as it does for the parking lot.
2. **One instance per party, game and place.** The party is the room, so the instance is "this room's players whose place is `rdwe:teal`". The server already broadcasts a snapshot only to players with the same place string, so two players in `rdwe:teal` see each other and a third in `rdwe:hallway` does not. No instance object is created or destroyed.
3. **Who is in it.** Whoever's place string matches. A player may enter alone (nobody else is in the place) or with friends (they walk through the gate, or "go to a friend" in a game: `goto` returns the friend's place and the page calls `enterGame` at that room). Friends can arrive and leave at any time, because arriving is changing a place string.
4. **What is shared.** Presence and positions only: where each player is, which way they face, crouching, moving. Each player's puzzles, pickups, ending and progress through the chain stay their own page's state. *Default for version 1, as in session 11's brief.* Shared puzzle state comes later and is a separate decision per game.
5. **Leaving.** A player who finishes or quits a game goes back to L4 at the gate's arrival point (the fix of session 2); their place changes to `L4`, and the others in the game see them vanish. Nothing in the others' game ends, because nothing else was shared. A player who disconnects is removed from their place as for any floor.
6. **How the others are drawn.** Each game draws other players in its own scene, not the page's:
   - Right Door, Wrong Exit: the page hands `walk.start` a list of peers (position, yaw, colour) that it updates from the room's snapshots, and the walk draws a plain figure for each in the walker's scale (`RDWE_SCALE`, so a player is the same size to everyone). Its own position goes out through the page's existing state message, with the game's place as the `scene`.
   - The Intern: the page and the iframe talk by `postMessage`, as they already do for `intern-ending`. The page posts peers into the iframe and the iframe posts its player's position out; the iframe draws figures in its own scene (scaled by `INTERN_SCALE`).
7. **Soundless and harmless.** Other players are shown but have no collision, cannot touch or hurt anyone and make no game-affecting noise. *Default.* (Footsteps heard in the Intern's drone would change a game built around silence; revisit with the owner.)
8. **The round outside.** A player inside a game is not on a floor, so the Original's finish must decide what to do with them. *Default:* a player in a game does not block the round: the finish waits for the players on floors, and a player still inside a game when it ends is not ranked, and gets the results on their return. Alternative, if the owner prefers: they count as present and the round waits. Chosen so that one player in a long game cannot hold a room hostage.
9. **Room size and the server.** The 10 cap, name tags, colours and the message budget are the room's, unchanged. Presence snapshots are sent at the page's usual state rate. The server holds no game state, so there is nothing new to measure for the tick.
10. **`soloOnly`.** The manifest flag is dropped per game only when that game's slice below passes its test. The page already reads the flag (session 2), and the manifest check already requires a built link that a room can follow to end in `multiplayer` or `presence` scenes.

**Order of work** (each slice its own commit, tested):
1. This note.
2. Server and manifest: game places as presence scenes, `canReach` and `goto` through them, tests. `soloOnly` stays.
3. Right Door, Wrong Exit in a room: peers drawn in its scene; `tools/games_party_test.mjs` has two clients enter the game separately, meet in one place, go on through all seven rooms (each its own place, each inside the server's position limits), and leave without breaking the other's game; a round that ends while one is in the game shows that one the results on the way back. Then drop `soloOnly` on its gate.
4. The Intern: the postMessage bridge and the same test. Then drop its `soloOnly`. **Built.** What the build settled:
   - The Intern lays its building out as each player walks it, so two players' coordinates differ. A spot is therefore sent in the frame of the room it is in, with that room's name (`sub`, e.g. `S3_H`) beside the place (`intern:S3`). The server relays `sub` as a short name and does not read it. A figure is drawn only while a room of that name is live in the viewer's game, so two players of one stage who are in its two different renders (`S3_C` and `S3_H`) do not see each other.
   - The bridge is `games/intern/src/coop.js`: the game posts `intern-state` to the page about 15 times a second, the page posts `intern-peers` into the game. The game is unchanged when it is not embedded.
   - "Go to a friend" starts your game at the friend's stage, in the render whose room they are in (`?start=S3&room=S3_H`). Your own score starts as the game's dev start sets it for that stage, not from stages you played.
   - The job shift from the City (`city.666>intern`) stays solo only.

**Not in this session.** Shared puzzle state, shared endings, voice or text between players in a game, games reached from the Overworld's forest or the city (their links stay planned), and the City's job shifts, which stay solo.

**Questions for the owner** (each has the default above): (a) are other players audible in the Intern, or only visible; (b) does a player inside a game block the round's finish; (c) should a player be able to jump into a friend's *Intern* stage, or only to Right Door, Wrong Exit rooms (the Intern's stages build on each other's state).

## Decisions

Settled:
- Room size is 10.
- Co-op inside the games is optional, and friends can pop in at any time, so a party of 10 can split across levels and games (RND-12, RND-15).
- A death is a down nobody revived. Revives are counted and add to the total score (RND-20, RND-27).
- Backend: PostgreSQL on Railway (Hobby now, Pro when needed). Players start anonymous and can sign in with Discord. The audience is 18 and over. Email sign-in and marketing email come later. See `docs/BACKEND.md`.

- Score (RND-27): the starting formula stays as it is, and a board ranks by score with the faster time breaking a tie. The results screen still lists the order players walked out in. The owner left this to the coordinator (2026-11-24).
- The Going back in loadout locker is called the **Lost and Found**: it is where your gear turns up after a death. The B1 loot lockers keep their name (2026-11-24).

Still open: nothing from this list.
