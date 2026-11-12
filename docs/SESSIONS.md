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
| 8 | Going back in prototype | Then | 3 and 4 | **slice 1 in draft PR** (solo: the options screen to a chamber, a wave on entry, stairs down to the next chamber); slice 2 (the locker and the hunting crossbow) and slice 3 (the Q/E consumables) on the same branch |
| 9 | City v0 on Hallam Row | Then | 6 | **slices 1 and 2 merged** (PR #11): bus, Hallam Row blockout, day clock, stores close. Slice 2 done on the same branch: the apartment and its computer, the night danger (a stalker from midnight to 06:00) and a bed that skips the night. Slice 3 (the Intern's job) not started |
| 13 | Make `tools/solo_test.mjs` deterministic | Now | | **done**, merged (PR #12): the flaky checks needed room around a random respawn spot; the test now stages a spot that has it. No game change |
| 14 | Make `tools/mp_test.mjs` deterministic | Now | | **done**, in draft PR: the recurring failures were the test racing the server (the server acts on its own, trailing, record of where a player is) and an L1 monster parked where it had no path to the noise. The test now waits for the server's view; 7 of 7 runs passed. Going back in's per-frame work in rooms was not measurable. No game change |
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
```

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
