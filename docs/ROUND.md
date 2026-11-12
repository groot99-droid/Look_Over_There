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
| RND-12 | A party is a room (the same mode and the same code). Where you are is separate from who you party with: ten players can split across floors, chambers and games in any number of groups, and each player can join or leave a place at any time. A player can jump to a friend. | PART BUILT: the party key is mode plus code, and `{t:"goto",to:id}` returns a friend's floor and spot (server only; the page does not use it yet). Chambers and games do not exist yet. | Ten clients in one party stand in three different places, and a late joiner goes to a friend's place. |
| RND-13 | The server can list open rooms for a mode: code, mode, players, phase, floor furthest along. | BUILT | `GET /rooms?mode=original` returns only open, non-full rooms. |
| RND-14 | Until RND-15 lands the two game gates are solo only. A manifest link marks this with `soloOnly`, and the page reads the flag instead of hard-coding it. | CHANGE | A test asserts the toast comes from the manifest flag. |
| RND-15 | Co-op inside a game (Right Door, Wrong Exit, the Intern) is optional, never required. A player may enter a game alone or with friends, and friends can pop in at any time. Each game runs one instance per party, and the players inside it see each other. A game's gate stops being solo only once the game supports this. | NEW | Two clients enter Right Door, Wrong Exit separately and meet in one instance. |

### Results, deaths and ranking

| ID | Requirement | Status | How we know |
|---|---|---|---|
| RND-20 | The server counts per player: downs, **deaths** (a down nobody revived: the 45 s ran out, or any down in solo play), **revives given**, shots, shots that hit, beacons thrown, cloak seconds, time on each floor. Today it keeps none of these. | BUILT, except cloak seconds (not counted yet) | `server/playerstate.test.js` covers each counter. |
| RND-21 | At the end the server builds one **run record**: `{roomCode, mode, startedAt, endedAt, floors: [{scene, ms}], players: [{name, char, place, ms, downs, deaths, revives, shots, score}]}`. Only the server writes it. For now it goes to the server log as one JSON line without names; a database comes with session 5. | BUILT (the record has no names; solo play has no server, so it is not logged) | A test plays a fake round and checks the record. |
| RND-22 | The results screen shows place, time, deaths, revives and score, your best time on this browser, and a welcome to Farway the first time you finish the Original. | BUILT (shows place, time, deaths, revives, score, best; the browser check is `tools/results_test.mjs`, solo only) | A browser test finishes a solo round and reads the screen. |
| RND-23 | Finishing the Original for the first time sets the flag `original_complete`. It is stored on this device first and moves to the account when accounts exist. | BUILT (stored on this browser only) | The flag survives a reload. |
| RND-24 | After the results the player can walk out to the Overworld. The link `lot.L4.front_doors>overworld` requires `original_complete`. | BUILT, solo only (a room cannot enter the Overworld yet; the walk out is offered on the results screen once the flag is held; `tools/overworld_test.mjs`) | `tools/manifest.mjs links` shows it open once the flag is held. |
| RND-25 | Ranking is online and counts runs from the whole game. Boards are kept apart by mode and by group size: solo, 2 to 4, 5 to 10. Whether a board ranks by time or by score is open. | NEW | `docs/BACKEND.md`; Decision 1 (time or score) |
| RND-26 | A run time is accepted only from a run record the server made. A client cannot send a time. | NEW | A test posts a made-up time and it is refused. |
| RND-27 | Revives count toward a player's total score and deaths count against it. Starting formula, to tune: 1000, plus 150 per revive, minus 100 per death, minus 1 per 5 s of round time, never below 0. | BUILT (placeholder numbers in `SCORE`, `shared/finish.js`; not confirmed by the owner) | A test scores a made-up run. |

### Safety and load

| ID | Requirement | Status | How we know |
|---|---|---|---|
| RND-30 | A finish is accepted only from L4 with the power on. | BUILT | `server/server.test.js` |
| RND-31 | The server rejects puzzle claims that the floor's state does not allow (a fuse you are not near, a wrong code, a switch already on). | BUILT | `shared/*.test.js` |
| RND-32 | The server tick averages under 5 ms with a full room. It measured 0.31 ms with 8 bots. Measure again at 10. | BUILT at 8, CHANGE at 10 | `node tools/bots.mjs 8` prints the tick time. |
| RND-33 | Each socket has a message budget (a burst of 240, 90 a second, a kick past 600). | BUILT | `server/server.test.js` |

## C. Going back in (planned)

A 20-wave run: 5 floors, 4 chambers each, top down: L4, L3, L2, L1, B1. A chamber is as big as an original floor.

| ID | Requirement | Status | How we know |
|---|---|---|---|
| GBI-1 | The mode `going_back_in` lists its floors top down, `chambersPerFloor: 4` and `waves: 20`. Version 1 has 4 chambers per floor, so no randomness yet. The existing floor is one of the four. | PART BUILT: the mode has these and a `startChamber`; 2 of the 20 chambers exist | Manifest check, `shared/manifest.test.js`. |
| GBI-2 | A chamber is a scene of the manifest. The 4th chamber on each floor has the stairs down. Chambers join with a mix of vent crawls, elevators, stairs, doors and painted-sky halls. | PART BUILT: two chambers, joined by stairs (solo only). The walk to the bottom floor is not built. | `tools/gbi_test.mjs` walks from the Overworld through the stairs. |
| GBI-3 | The wave starts when the players enter the chamber. The rest is quiet time: objects to find, puzzles, loot, defences to build. A chamber is cleared when its objectives are done. | PART BUILT: the wave starts on entry (solo). Quiet-time objectives and "cleared" are not built. | `shared/gbi.test.js`, `tools/gbi_test.mjs` |
| GBI-4 | Unkillable threats are environmental (crushing walls, lava floor, high tides, toxic gas, chainsaw blades). Special entities come later. | NEW | One hazard per chamber type. |
| GBI-5 | Doors can be closed, trapped or barricaded, and nothing else. Players can crawl into vents. Monsters never use vents. | NEW | |
| GBI-6 | A safe house on every floor holds a shop, a stash, a save, crafting and a respawn point. | NEW | |
| GBI-7 | A locker (one per safe house and one per chamber) shows your loadout and lets you change it. After you die it returns your weapons and gear for free. It does not return ammo, consumables or perks. Those are bought back at the Market or a safe house. The existing one-time loot locker on B1 needs a different name. | PART BUILT: one per chamber, solo; no safe house, no Market | `tools/gbi2_test.mjs` dies and checks what the locker returns |
| GBI-8 | Lethal weapons come from the arsenal (ten weapons, three consumables). Each needs its own ammo rule. The ray, the cloak and the beacon stay non-lethal. Q and E (LB and RB) are consumable slots. | PART BUILT: the hunting crossbow, and the Q/E slots with the three consumables. Seven weapons are not built. | `shared/crossbow.test.js`, `shared/consumables.test.js`, `tools/gbi2_test.mjs`, `tools/gbi3_test.mjs` |
| GBI-9 | Money comes from clearing chambers and from kills and revives. Level comes from achievements. Money and items are shared with the rest of the game. Progress is its own save. | NEW | |
| GBI-10 | Per-run score goes to an online leaderboard, with personal and overall bests. | NEW | `docs/BACKEND.md` |
| GBI-11 | The 20 waves stay 20 when floors are added, by sampling. | NEW | |

### Session 8 plan: Going back in, in slices (solo only)

| Slice | GBI items | Status |
|---|---|---|
| 1 | GBI-1 (the mode names its first chamber), GBI-2 (two chambers as manifest scenes, stairs down between them), GBI-3 (the wave starts on entry) | BUILT, solo only: `tools/gbi_test.mjs`, `shared/gbi.test.js` |
| 2 | GBI-7 (the loadout locker), GBI-8 for one weapon: the hunting crossbow with its own ammo rule | BUILT, solo only: `shared/crossbow.test.js`, `shared/loadout.test.js`, `tools/gbi2_test.mjs`. The Q/E consumable slots are NOT built (they still say empty) |
| 3 | GBI-8's consumable slots: Q and E, with the flash-vial, the land mine and the tripwire | BUILT, solo only: `shared/consumables.test.js`, `tools/gbi3_test.mjs` |
| left | GBI-8's other nine weapons, GBI-4 hazards, GBI-5 doors and vents, GBI-6 safe house, GBI-9 to GBI-11, and rooms running the mode (the server still answers `{t:"refused",reason:"soon"}`) | NEW |

What slice 1 does: from the Overworld's store-doors options screen, "Going back in" loads `gbi_L4_4` (the 4th chamber of L4, which is the L4 model with the store sealed) as wave 4 of 20, and the wave (3 monsters, 16 m or more from you) starts as you land. Its stairs-down door leads to `gbi_L3_1` (the L3 model; wave 5, its own 3 monsters). That chamber's way down and the 14 other chambers are not built. The chamber's wave number is its floor's place in the mode times four plus its index. The stairs are open from the start: there are no clear rules yet (objects, puzzles, kill count, timer), so "cleared" is not checked. Death is the solo rule (respawn at a random spot in the same chamber).

What a room needs to run the mode (not done): the server's `FLOORS` and floor sims must take the chamber scenes (`multiplayer: true` plus a `floorY`), a wave must be started by the server when the first player enters a chamber, the mode's `status` must go to `built`, and the lobby's disabled "GOING BACK IN" button must be enabled.

**Slice 2 rules (defaults the owner may change).**
- *Crossbow:* its own ammo, bolts, not rounds. One per shot, at most 6 carried, 4 at the start (the Market does not exist, so the crossbow starts in your hands), +2 from each ammo pack you pick up while you carry it, 1.8 s reload between shots. A bolt that hits kills the monster for good (the ray still only banishes). A shot makes half the ray's noise. Key 4 holds it.
- *Locker:* one per chamber, placed like a pack, opened with the action button (X / E). A panel lists the ray, the cloak and the crossbow: carry one or leave it in the locker (keys 1 to 3, a click, or D-pad and A). The game pauses while it is open.
- *Death:* all your gear goes to the locker, and ray rounds, bolts and beacons are gone. Walk to a locker and take the gear back for free; the ammo does not come back. A beacon is counted as charges, so it is lost like ammo (the doc lists it as gear; say if you want the device kept).
- *Kills:* a kill is counted, and killing every monster of the wave clears it (toast). That is the only clear rule so far.
- *Name:* the panel and the code call it "the locker" and "the loadout locker". The open question (Decision 2) stands.

**Slice 3 rules (defaults the owner may change).** The doc names the three consumables but not which slot holds what, nor their numbers.
- *Q (support): the phosphor-core flash-vial.* Thrown up to 6 m ahead (it stops at a wall); every monster within 6 m of where it lands is stunned for 6 s. It kills nothing. Max 3, start 2.
- *E (combat / objective): the almond water land mine or the nail-bomb tripwire, chosen at the locker (key 4, or the E row with D-pad and A).* The mine is set down where you stand, arms after 1.5 s, and kills the one monster that comes within 1.2 m. Max 3, start 2. The tripwire arms after 0.5 s; a monster within 2 m sets it off and every monster within 3 m dies; the blast is loud, so monsters within 25 m go and look. Max 2, start 1. Both count as kills toward the wave. A trap is yours to walk into too: nothing here hurts the player (monsters are the only target in v1).
- *Refills:* each ammo pack adds one flash-vial and one of the E item, up to the cap. The Market does not exist yet, so there is no other source.
- *Death:* all consumables are gone and the locker does not return them (docs/WORLD.md). Traps already set stay until a monster springs them, and are cleared when you change chamber.
- *Controls:* Q and RB-side E are as `docs/GAMEPLAY.md` says (LB / Q support, RB / E combat). `tools/controls_test.mjs` still passes. In the Original the slots stay empty.

## Decisions

Settled:
- Room size is 10.
- Co-op inside the games is optional, and friends can pop in at any time, so a party of 10 can split across levels and games (RND-12, RND-15).
- A death is a down nobody revived. Revives are counted and add to the total score (RND-20, RND-27).
- Backend: PostgreSQL on Railway (Hobby now, Pro when needed). Players start anonymous and can sign in with Discord. The audience is 18 and over. Email sign-in and marketing email come later. See `docs/BACKEND.md`.

Still open:
1. **Score formula and what ranks the board.** The RND-27 formula is a placeholder. A board can rank by time, by score, or have one of each.
2. **Name for the Going back in locker**, since the existing locker is a one-time pickup.
