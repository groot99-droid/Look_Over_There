# Sessions: how the work is split

The Farway plan is too big for one session. This file splits it into sessions that can run side by side, says which must come first, and gives each a brief that stands on its own, since a new session starts from its prompt and a fresh checkout.

Read first: `docs/WORLD.md` (what Farway is), `docs/ROUND.md` (what a round must do), `docs/MANIFEST.md` (the world manifest), `docs/GAMEPLAY.md` (what is built).

## Status

| # | Session | When | Needs | Status |
|---|---|---|---|---|
| 1 | Manifest core and loader | done | | **done**, merged (PR #3) |
| 2 | Gate return fix, links read from the manifest | Now | 1 | **done**, merged (PR #5) |
| 3 | Results v2, local: deaths, revives, score, a round log line | Now | 1 | **done**, merged (PR #4) |
| 12 | Tune the Original, starting with B1 | Now | 1 (better with 3) | **bot pass done and merged** (PR #6): down time 20 s, 6 packs on B1; needs the owner's playtests |
| 6 | Overworld v0 | Next | 1 and 3, after 2 | **done**, merged (PR #9); solo only, rooms cannot enter it yet |
| 7 | Physics: decision and a playground prototype | Next | | **done**, merged (PR #8); `docs/PHYSICS.md` accepted by the owner with cannon-es, visual only in rooms |
| 4 | Modes and parties | Next | 1 | **done**, merged (PR #7); server and lobby, "go to a friend" is server-side only |
| 8 | Going back in prototype | Then | 3 and 4 | **slices 1 to 3 merged** (PR #10, solo only): the options screen to a chamber, a wave on entry, stairs down (2 of 20 chambers); the loadout locker and the hunting crossbow; the Q/E consumables. Rooms still refuse the mode ("soon"). Next step: session 16 |
| 9 | City v0 on Hallam Row | Then | 6 | **slices 1 to 21 merged** (PRs #11, #14, #15, #19 to #21, #24 to #27, #29 to #31, #33 to #39; solo only): bus, street, day clock and night rules, apartment and computer, stalker and bed, the five jobs (Intern quiz, trash route, museum, factory, lab) and pay, hunger, rest, grocery and theft with its camera, saving and New Game, the mall, the anomalies and reporting them, pedestrians with routines, the HUD layout, the watchers. Not played by a person yet |
| 13 | Make `tools/solo_test.mjs` deterministic | Now | | **done**, merged (PR #12): the flaky checks needed room around a random respawn spot; the test now stages a spot that has it. No game change |
| 14 | Make `tools/mp_test.mjs` deterministic | Now | | **done**, merged (PR #17): the recurring failures were the test racing the server (the server acts on its own, trailing, record of where a player is) and an L1 monster parked where it had no path to the noise. The test now waits for the server's view; 7 of 7 runs passed. Going back in's per-frame work in rooms was not measurable. No game change |
| 15 | `mp_test`: the L4 finale switch race | Round 4 | 14 | **done**, merged (PR #43): not a teleport race (the server takes the power by floor, not position). The failure was not reproduced on its own in 12 finale runs; forcing Xia down at the press gives the same failed checks and the same crash, and she stood unguarded on B1 while the second page loaded. The test now guards each player once the round has them and checks the server's and the page's view at the press; missing results fail a check instead of throwing. A second, older flake (a 60 s wait for two pages to arrive on L4) got the finale's 170 s. 6 of 6 runs passed (114 checks). No game change |
| 16 | Going back in in rooms | Round 4 | 4 and 8; waits for the owner's playtest and decisions | **slices 1 to 3 merged** (PR #42): a room of up to 10 plays the two chambers; the server starts each wave once and owns the bolts, kills, loadout and consumables (`docs/ROUND.md`, "Session 16"). Open for the owner: the locker's name, the crossbow at the start, wave size for a party, a finish and score for the mode. Not played by a person yet |
| 17 | Overworld and City in rooms, and "go to a friend" in the page | Round 4 | 4, 6 and 9; waits for the owner's playtest | **slices 1 to 3 merged** (PR #41), presence only: a room walks out to the parking lot, rides the bus to Hallam Row and uses the apartment, and sees each other there (the manifest's `presence` scenes; the server relays positions and runs no rules); P lists the party with where each player is and a Go button. Every other interior, both games and Going back in stay solo only. Not played by a person; seven questions for the owner are in the PR |
| 18 | Item rules: one document for every item | Round 4 | | **written, merged** (PR #44): `docs/ITEMS.md` proposes rules, prices and tuning tables for all 24 modelled items plus the ray, cloak and beacon. A design document only: no game code, models or manifest changed. Waits for the owner's critique before any of it is built |
| 19 | Build the pneumatic bolt driver (the first arsenal weapon after the crossbow) | Round 4 | 18 | **built, merged** (PR #46): `shared/driver.js`, monster health (`hp`, `MonsterSim.hurt`), key 5 and a locker row, solo only. Rooms (session 16) and the Market are not touched |
| 20 | Build the stun baton, the two-weapon carry cap and the weapon slots | Round 4 | 19 | **built, merged** (PR #47): `shared/baton.js`, `ARSENAL`/`canTake` in `shared/loadout.js`, solo only. Rooms and the Market are not touched |
| 21 | Build the moth jelly dart and the Slowed and Jellied statuses | Round 4 | 20 | **built, merged** (PR #48): `shared/dart.js`, `MonsterSim.slow`/`jelly`/`statusTick`, solo only. Rooms and the Market are not touched |
| 22 | Build the propane flamethrower and the Burning status | Round 4 | 21 | **built, merged** (PR #49): `shared/flame.js`, `MonsterSim.burn`, solo only. Rooms and the Market are not touched |
| 23 | Build the frequency horn | Round 4 | 22 | **built**, draft PR on `claude/frequency-horn`: `shared/horn.js`, `shared/cone.js`, `MonsterSim.shove`, solo only. Rooms and the Market are not touched |
| 24 | Build the rocket launcher | Round 4 | 23 | **built**, draft PR on `claude/rocket-launcher`, stacked on session 23's `claude/frequency-horn`: `shared/rocket.js`, `shared/flight.js`, solo only. Rooms and the Market are not touched |
| 5 | Backend: Postgres, anonymous accounts, Discord sign-in, leaderboard | Later | 3 | decided, plan in `docs/BACKEND.md`; not started |
| 10 | Editor for scenes and links | Later | 1 | not started |
| 11 | Games inside parties (co-op in Right Door, Wrong Exit and the Intern) | Later | 4 | not started |

Update this table in the last commit of each session.

## Order

```
Now:    2    3    12          touch different files, so they can run side by side
Next:   6 (after 2 and 3)    7    4
Then:   8 (needs 3 and 4)    9 (needs 6)
Later:  5 (needs 3)    10    11 (needs 4)
Round 4: 15 to 22, all merged by 2026-11-16 (PRs #41 to #49)
```

Also merged outside the sessions on 2026-11-16: the 24 item models (PR #45), the fuse model (PR #50), the land mine and tripwire models (PR #51), and a lobby fix (PR #52). Status as of 2026-11-19.

- **Round 4 starts with a playtest by the owner.** Nothing from sessions 6, 8, 9 or 12 has been played by a person yet. Sessions 16 and 17 were planned to wait for that; both were merged on 2026-11-16 without it, so the owner's playtest and open decisions (the score formula, the name of the Going back in locker, "different truths per area", whether the crossbow starts in your hands) still apply to what is now on `main`.

- **The game does not need the backend to be built.** Session 5 waits until there are players who want saved progress or a ranking across players, or until the server log is not enough data. Until then the Original-complete flag lives in the browser and the best time is per browser.
- **Session 12 matters most for whether the game is fun.** The Original is untuned (see its brief), and a bigger world does not help if the opening floor is too punishing.
- Sessions in the same row can run side by side. A session in a later row starts when what it needs has merged.

## Rules for every session

1. Start from `main` after the manifest PR is merged. Work on a branch named `claude/<short-name>`, one branch and one draft PR per session.
2. Before pushing, run all three:
   - `node --test shared/*.test.js`
   - `cd server && npm ci && npm test`
   - `node tools/manifest.mjs check`
3. A change to what the game does needs a test that fails first and passes after. Say in the PR what you ran and what you did not run. Do not say a browser flow works unless you drove it.
4. Stay inside your files (table below). If you must touch another session's region, keep it to a few lines and say so in the PR.
5. Follow the existing style: short comments that say why. No key or secret in any file, and tests use fake values.
6. When you need a decision from the owner, write the question and the default you will use, and carry on with the default.

### Who touches `index.html`

`index.html` is one large file, so parallel sessions conflict there. Keep to these regions:

| Region | Session |
|---|---|
| gates, `goLink`, `enterGame`, the "That door does not open in a room" toast | 2 |
| the finale and `#results` (markup, styles and code) | 3 |
| the lobby overlay and the join code | 4 |
| `loadScene`, scene types, the options screen at the store doors | 6 |
| held items, consumable slots, the chamber loader | 8 |
| the player's walk, run and crouch numbers (`WALK_SPEED`, `RUN_SPEED`, `RUN_S`, `RECOVER_S`) | 12 |

Merge order when several are open: 2, then 3, then 6.

---

## Briefs

Every prompt below starts with this line:
> You are working in `groot99-droid/Look_Over_There`. Read `docs/WORLD.md`, `docs/ROUND.md`, `docs/MANIFEST.md` and `docs/SESSIONS.md` first, branch from `main`, and follow the rules in `docs/SESSIONS.md`.

### Session 2: gate return fix, links read from the manifest
- **Goal.** Reproduce the suspected bug first. After Right Door, Wrong Exit ends, the page may call `loadScene(l.scene || S.id)` with `S.id` equal to the passage scene `T`, which has no entry in `SCENES`. Prove it in a headless browser, then fix it using `returnTo` from the manifest. Read the "solo only" toast from the manifest's `soloOnly` flag.
- **Touches.** `index.html` (gates region), a new `tools/gates_test.mjs`.
- **Done when.** The new test fails on `main` for the Right Door, Wrong Exit gate and passes after the fix. Both gates return to L4 at the arrival point in their link. The Intern's gate still works.
- **Prompt.** Reproduce the gate return bug in `tools/gates_test.mjs` (Playwright, same style as `tools/stairs_test.mjs`): walk to each gate in solo play, enter the game, end it, and assert the player is back on L4. For Right Door, Wrong Exit, end it by calling the walk module's finish. For the Intern, post the `intern-ending` message. Show the test failing, then fix `enterGame` using `REGISTRY` and the link's `returnTo`. Make the room toast read `soloOnly`.

### Session 3: results v2, local
- **Goal.** RND-20 to RND-23 in `docs/ROUND.md`, with no database and no accounts.
- **Touches.** `server/playerstate.js`, `server/server.js` (stat hooks, the run record), `shared/finish.js`, the `#results` region of `index.html`.
- **Does not touch.** Accounts, storing run records, ranking. Those are session 5, later.
- **Done when.** The server counts downs, deaths, revives given, shots, shots that hit, beacons thrown and time per floor, and each counter has a test. At the end it builds the run record from RND-21 and writes it to the server log as one JSON line, without player names. The results screen shows time, deaths, revives, score and the best time on this browser. The first Original finish shows a welcome to Farway and sets `original_complete` in `localStorage`.
- **Decided.** A death is a down nobody revived (the 45 s ran out, or any down in solo play). Revives given are counted and add to the score. Use the RND-27 formula, which is a placeholder.
- **Prompt.** Add per-player counters to the server's player state, with tests. Build the run record in `shared/finish.js` as a pure function with tests, and log it as one JSON line per finished round with no names. Extend the `results` message and the results screen. Store `original_complete` in `localStorage` under one key, wrapped in try and catch.

### Session 4: modes and parties
- **Goal.** RND-10 to RND-14, and the first half of RND-12: a party is a room, each player's place is separate from the party, any player can join or leave a floor at any time, and "go to a friend" jumps to their floor.
- **Touches.** The join and lobby code in `server/server.js` and the lobby overlay in `index.html`; `shared/registry.js` lookups for modes.
- **Done when.** A client joins with a `mode`. The room takes its floors, size and finish from the manifest. A party key groups people by mode and code. `GET /rooms?mode=` lists open rooms. The server refuses to start if the manifest's room size exceeds the player colours.
- **Decided.** Room size is 10 (done in the manifest PR). Make sure the lobby, name tags and spawns handle 10.

### Session 5: backend (Postgres, anonymous accounts, Discord sign-in, leaderboard)
- **When.** Later. The game does not need it to be built. Start it when players want saved progress or a ranking, or when the server log is not enough data.
- **Decided.** `docs/BACKEND.md` is the plan: Postgres as its own Railway service, anonymous accounts first, Discord sign-in, server-only writes, 18+ audience. Email and marketing come later.
- **Goal.** The five build steps in `docs/BACKEND.md`: the store interface with an in-memory and a Postgres implementation, anonymous sessions, Discord sign-in, run records and the leaderboard, and the privacy routes.
- **Touches.** New files under `server/store/` and `server/auth/`, a few lines in `server/server.js` (the join and the end of a round), new migration files. Nothing in `index.html` except a sign-in button and the leaderboard screen, kept to a small new region.
- **Needs.** Session 3 merged for steps 4 and 5. Steps 1 to 3 can start earlier.
- **The owner must first** create the Discord application, add the Railway Postgres service and set the variables listed in `docs/BACKEND.md`. Never put a secret in a file, a test or a chat.
- **Done when.** The existing server tests pass unchanged against the in-memory store, a reload keeps `original_complete`, Discord sign-in works against a fake Discord in tests, and a time sent by a client is refused.
- **Prompt.** Follow `docs/BACKEND.md` step by step. Start with the store interface and migrations, with every existing test passing on the in-memory store. Use a fake Discord server in tests. Say in the PR what ran against a real database and what did not.

### Session 6: Overworld v0
- **Goal.** The smallest Overworld. Promote `overworld` to built in the manifest with a `parking_lot` scene made from `world/Exterior.glb`, the table and chairs as the spawn, the Look Over There store doors, and one sky mode. Walking out of L4 after the Original continues into it. The store doors show an options screen: Original, or Going back in (disabled, "soon"). The link `lot.L4.front_doors>overworld` requires `original_complete`.
- **Touches.** The `loadScene` and scene-type region of `index.html`, new files under `world/`, the manifest.
- **Does not touch.** The city, the bus, the forest, physics.
- **Done when.** A solo round ends in the Overworld, a reload keeps the flag, and `node tools/manifest.mjs check` passes with the Overworld built.
- **Needs.** Sessions 1 and 3, and after session 2.

### Session 7: physics decision and playground prototype
- **Goal.** Choose how objects get gravity and physics everywhere. Compare a WASM engine (Rapier) with a small JS one (cannon-es) on download size, step cost with 200 bodies, and fit with the existing box colliders. Write `docs/PHYSICS.md`. Build an isolated prototype (a kickable ball, a swing) under `tools/physics/`.
- **Does not touch.** `index.html`. Nothing merges into the game until the owner accepts the document.
- **Decision to carry on with a default.** Physics objects are visual only in rooms (each client simulates them, the server does not).

### Session 8: Going back in prototype
- **Goal.** GBI-1 to GBI-8 for one floor. A chamber scene loaded through the manifest, the wave starting on entry, a stairs-down chamber, a loadout locker, consumable slots on Q and E, and one lethal weapon with its own ammo rule (the hunting crossbow).
- **Needs.** Sessions 3 and 4. Split it further before starting if it grows.

### Session 9: city v0 on Hallam Row
- **Goal.** A street scene reached by the bus, the apartment with its computer, a 15-minute game day, the night rule (stores close, then danger), and the Intern's job at 666 Hallam Row through the shared application quiz.
- **Needs.** Session 6.

### Session 10: editor for scenes and links
- **Goal.** A local page for placing doors, spawn points and links and writing them to the manifest and the scene files. Decide first whether the manifest becomes JSON with a thin JS wrapper (so a tool can write it safely); `node tools/manifest.mjs export` already produces the JSON.
- **Needs.** Session 1.

### Session 11: games inside parties
- **Goal.** RND-15. Co-op inside Right Door, Wrong Exit and the Intern is optional: a player can enter a game alone or with friends, and friends can pop in at any time. A party of 10 can split across levels and games.
- **Needs.** Session 4 (a party is a room, and a player's place is separate from the party).
- **Start with a design note** in `docs/ROUND.md` before code: one instance per party and game, which players are in it, and what is shared. Default for version 1: players in the same instance see each other walk (presence and positions only), and each player's puzzles stay their own. Shared puzzle state comes later.
- **Done when.** Two clients enter Right Door, Wrong Exit separately, meet in one instance, and leave without breaking the other's game. The gate's `soloOnly` flag is dropped for that game in the manifest. Then the same for the Intern.

### Session 12: tune the Original, starting with B1
- **Why.** The Original is untuned. `docs/GAMEPLAY.md` plans about 20 minutes, with B1 taking about 4. The owner's solo round took 36 minutes, with about 23 downs on B1, and no bot team ever solved B1's fuse puzzle. Expanding the world does not help if the opening floor is too punishing.
- **Goal.** A team of 3 or 4 can finish B1 in about 4 minutes without being downed over and over. Then the same for L1 and L2.
- **Starting numbers.** These are defaults for the owner to confirm: B1 cleared in about 4 minutes, and fewer than 5 downs per player on B1.
- **Levers to try, one at a time,** from the notes in `docs/GAMEPLAY.md`:
  - a shorter down time (45 s now; try 20 s first);
  - more ammo on B1 (more packs, or more rounds per pack);
  - spawns nearer the fuses, or fuses nearer the spawn. The group spawns far east and the fuses are in the west, about 80 m of path through one corridor where nearly every death happened;
  - fewer monsters on B1 (4 now), or a way round that corridor;
  - whether the cloak is worth its cost. The owner rarely used it.
- **Method.** Change one lever, then take 3 playtests with real players, noting time per floor, downs, and what they say about it. The bots can run each change, but they are too cautious (see the bot note in `docs/GAMEPLAY.md`), so make them take more risks before trusting them. Use session 3's round log line once it exists, or time rounds by hand.
- **Touches.** The numbers in `shared/health.js`, `shared/spawn.js`, `shared/loot.js` (the loot counts are in the manifest), `shared/fuses.js`, `shared/monsters.js`, `world/monsters.json`, and the player constants in `index.html`. No new features.
- **Done when.** The targets above are met in 3 playtests with 3 or 4 players, and the PR shows the numbers before and after for each lever.
- **Decision to carry on with a default.** The targets above. The owner may change them.
- **Prompt.** Reproduce the problem first: run `node tools/bots.mjs` on B1 and record time to the first fuse and downs per player. Then change the levers one at a time, in the order above, and record the same numbers after each. Keep every change in the numbers, never in new rules. Ask the owner for playtests and write down what they report.

### Session 15: `mp_test`: the L4 finale switch race
- **Goal.** `tools/mp_test.mjs` still fails now and then in the finale room: "the L4 switch sets off the alarm for both players" fails, and every finale check after it fails with it. The test teleports Xia to the L4 power switch and presses X at once, the same teleport-then-act race session 14 fixed at the L1 switch, the L2 keypad and doors and the L4 far switch, but this one was not covered.
- **Touches.** `tools/mp_test.mjs` only. A game or server change only if you find a real bug, as its own commit with a test that fails first.
- **Done when.** The finale switch waits on the server's view of the player (the same `serverSees`/`atServer` approach the test already uses) before the press. Failure output prints what the page and the server each see. `mp_test` passes at least 6 runs in a row, one at a time, and the PR lists every run. No assertion weakened, no timeout widened, no blind sleep.

### Session 16: Going back in in rooms
- **Goal.** Let a party play Going back in together. The server runs chambers as floors (`floorY`, monsters, waves), starts the wave when the first player steps in, and owns bolts, kills and the loadout. The mode's `status` becomes built and the lobby's disabled button is enabled. Session 8 wrote down what is needed in `docs/ROUND.md`.
- **Touches.** `server/server.js` and the floor sim, the manifest (`going_back_in` and the `gbi` area), the lobby region and the chamber region of `index.html`, server and browser tests.
- **Waits for.** The owner's playtest of the solo mode and the open decisions (the locker's name, the crossbow at the start).
- **Done when.** Two clients in one room play a chamber and take the stairs to the next one, and a server test with 10 clients passes.

### Session 17: Overworld and City in rooms, and "go to a friend"
- **Goal.** A party can walk out of the Original into the parking lot together and ride the bus to Hallam Row, seeing each other (presence and positions only, as session 11's default). Each player's City clock, needs and jobs stay their own in version 1. The page gets the "go to a friend" button that session 4 left server-side.
- **Touches.** `server/server.js` (page scenes a room can hold with presence only), the scene region of `index.html`, the lobby region for the friend list, tests.
- **Waits for.** The owner's playtest of the solo City.
- **Done when.** Two clients in one room meet in the parking lot and on the street and see each other move, and "go to a friend" moves one to the other's scene in a browser test.
