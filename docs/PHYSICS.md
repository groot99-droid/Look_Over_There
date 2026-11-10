# Physics: the decision

Status: **accepted by the owner: cannon-es.** The first draft of this document recommended Rapier; the owner chose cannon-es instead, and this section is rewritten to match. The Rapier numbers stay below as the comparison. Nothing here touches `index.html`, the server or the manifest, and no game code uses either engine yet. The prototype is in `tools/physics/` and does not import the game.

## Decision

**Use cannon-es, pinned to `cannon-es@0.20.0` (MIT), for gravity and physics objects everywhere in Farway.** It is 36 KB gzip minified (75 KB unminified, as served from unpkg), loads in about 35 ms in Node, and has no WASM to compile. The prototype's default engine is already cannon-es.

What choosing it costs, from the measurements below, and the rules that keep the cost small:
- **Step cost grows with the world, so keep the world small.** 200 bodies cost about 2.4 to 3 ms per step while moving and 1.7 to 1.9 ms at rest (cannon-es slept 119 of 200). That is acceptable for a room, but a share of a 16.7 ms frame that matters on a phone, which I could not measure. Budget about 50 bodies per scene as a working limit until a phone has been tried; measured in Node with 50 bodies and 40 nearby static boxes (3 runs): 0.4 to 0.5 ms per step while moving, about 0.14 ms at rest, worst step 1.3 to 2.6 ms.
- **Never hand a scene's whole `boxes` array to the world.** With 1000 extra static boxes the step went to about 8 ms (worst step 52 ms in Node, 22 ms in Chromium), against 0.5 ms for Rapier. Feed only the boxes within a few metres of a physics object, using the existing `near()` grid. Scenes here have 48 to 591 colliders, so the full array is in the bad zone.
- **Sleeping must be on** (the adapter sets it) and bodies that leave the playable area should be removed.
- **The swing is 1.7% long** against the pendulum formula (2.942 s against 2.894 s); Rapier was within 0.1%. Fine for a toy; tune the constraint if a mini-game needs timing.
- **No continuous collision detection.** Fast kicked balls can pass through thin walls (0.2 m here). Cap the kick speed and use thicker invisible colliders around physics areas. Not tested.
- **cannon-es is unmaintained** (last release 0.20.0, August 2022). Both engines sit behind the same small adapter in `tools/physics/engines/`, so Rapier remains a drop-in if this ever bites. If a phone test shows cannon-es too slow, that is the trigger to revisit; Rapier 0.19.3 (834 KB gzip) is the measured alternative. Rapier 0.21.0 is not recommended (1.65 MB gzip, and bodies slept far less in the same bench).

## What was measured, and where

All numbers: 200 dynamic bodies (100 balls, 100 crates, fixed seed, same scene in both engines) dropped into a walled pit, stepped at a fixed 1/60 s. "Active" is the first 300 steps (falling, piling up); "rest" is steps 900 to 1200 (15 to 20 s in). A throwaway world is stepped first so the JIT is warm. "+1000" adds 1000 far-away static boxes. The machine is a 4-core Xeon at 2.1 GHz in a cloud container (a cloud sandbox: other load on the host is unknown). Node v22.23.4. Chromium 153 headless with `--use-gl=swiftshader` (software GL). **Physics does not use the GPU, so software GL does not change these numbers; it is the flag set the other tools in this repo use, and I say so rather than imply a GPU test.** Chromium rounds `performance.now()` to 0.1 ms, so its small values are coarse.

Step cost, ms per step (mean, p95), 3 runs in Node and 2 in Chromium agreed within about 15%; the table shows one typical run each:

| | Node active | Node rest | Chromium active | Chromium rest | asleep at 20 s |
|---|---|---|---|---|---|
| cannon-es 0.20.0 | 2.7 / 4.3 | 1.9 / 2.3 | 2.4 / 3.4 | 1.7 / 2.0 | 119 of 200 |
| cannon-es, +1000 static | 8.9 / 12.0 | 8.2 / 9.5 | 7.9 / 9.8 | 7.7 / 10.6 | 101 of 200 |
| Rapier 0.19.3 | 0.48 / 0.69 | 0.05 / 0.09 | 0.46 / 0.6 | 0.04 / 0.1 | 196 of 200 |
| Rapier 0.19.3, +1000 static | 0.57 / 0.80 | 0.10 / 0.14 | 0.51 / 0.7 | 0.09 / 0.2 | 194 of 200 |
| Rapier 0.21.0 (for comparison) | 0.85 / 1.1 | 0.65 / 0.8 | 0.88 / 1.2 | 0.63 / 1.0 | 83 of 200 |

Worst single step: cannon-es +1000 had a 52 ms spike in Node (22 ms in Chromium); Rapier 0.19.3 never passed 3.5 ms. A 16.7 ms frame is the budget the rendering shares.

Download size, real bytes (`gzip -9`; the server's own compression may differ, and I did not test brotli):

| | raw | gzip |
|---|---|---|
| cannon-es 0.20.0 `dist/cannon-es.js` (not minified) | 346,256 | 74,520 |
| cannon-es, minified with esbuild | 124,991 | 36,008 |
| Rapier 0.19.3 `rapier.mjs` (the .wasm inlined as base64) | 2,238,719 | 834,345 |
| Rapier 0.19.3 the `.wasm` alone | 1,569,588 | 583,479 |
| Rapier 0.21.0 `dist/rapier.mjs` | 4,340,292 | 1,652,936 |
| Rapier 0.14.0 `rapier.es.js` (my first pin, measured and dropped) | 2,059,628 | 765,513 |

For scale: `three@0.160.0` (what the game loads from unpkg) is 256 KB gzip, and `world/` is 30 MB. The `-compat` build is the one that works with an import map and no bundler; the plain `@dimforge/rapier3d` package keeps the WASM as a separate file (584 KB gzip in 0.19.3) but needs a bundler or a manual `fetch`. Switching to it later would save about 250 KB and is not measured as a load.

Start-up: in Node, importing and creating a Rapier world took about 90 ms (0.21.0 init alone: 67 ms), cannon-es about 35 ms. Browser load time over a real network is not measured.

## Fit with the box colliders

Read from `index.html`: the world is `boxes`, a flat array of `{n: [x,y,z], x: [x,y,z]}` (min and max, axis-aligned), filled from each scene's `colliders` (`world/*.json`: B1 591 boxes, L1 490, L2 560, L3 48, L4 234) plus doors and the shutter, which carry an `off` flag. `collide(p)` asks `near()` (a grid over the boxes) which ones overlap the player's box (R 0.28, H 1.7). The player is a kinematic AABB with its own `move()`; it is not a rigid body.

- **Both engines take these boxes as they are.** `addStaticBox({n, x})` converts min/max to centre and half extents and is one line in each adapter. The test scene's floor is built that way.
- **Keep the player out of the physics world.** The game's walking is tuned (step height, run and crouch numbers); a rigid-body player would change all of it. Treat the player as a moving box that pushes bodies: when `overlap` says the player box touches a physics body, apply an impulse along the movement. Not prototyped.
- **Do not hand the whole scene to the engine.** Feed only the boxes within a few metres of a physics object (`near()` already gives them), and add or remove them as objects move between cells. The +1000 rows show why this matters for cannon-es; Rapier tolerates it.
- **Doors and the shutter** (`off` true or false) must add or remove their static box in the physics world when the flag flips. Not prototyped.
- **Fast kicked balls can tunnel through thin boxes** (walls here are about 0.2 m thick). Rapier has continuous collision detection per body; cannon-es has none. Not tested in either.

## Visual only in rooms: what it costs

The default is that each client simulates its own physics objects and the server does not. What that means:

- **Two players will see the ball in different places.** Each client has its own ball, kicked only by the local player's movement (the server never learns of it). If you and a friend stand at the same swing, you do not see them push it. Starting positions agree (same scene); after any kick they do not, and nothing pulls them back together.
- **Nothing can depend on it.** No score, money, puzzle, loot pickup, door or monster behaviour may read a physics object's position, because the server and the other clients would not agree.
- **Cheap and safe.** No network traffic, no server step cost, no cheating surface.

**It stops being acceptable when any of these is true:** an object pays money or counts for a result (the playground mini-games in `docs/WORLD.md` do, so the first one that pays needs this solved); two players need to see or hit the same object (a party passing a ball is the obvious case; I expect players to notice this first, in the playground); a physics object can block a path or hold a switch. Then pick one:

1. **Owner simulates.** The player who last touched the object runs it and sends position and velocity at about 10 Hz through the server; the others interpolate. Cheap on the server, good enough for toys, trivially cheated, so not for anything that pays.
2. **Server simulates.** The server steps the world for the objects that matter. Both engines run in Node (the tests do it), and the measured step cost for 200 bodies is 0.5 to 3 ms, small beside the existing floor simulation. This is the only choice that is safe for rewards. It needs a snapshot message for the objects and client-side interpolation.

I did not build either; this is the cost estimate.

## The prototype

- `tools/physics/index.html`: side view of a 3D simulation, a kickable ball (click near it) and a swing (Push button). `node tools/physics/serve.mjs` then open `http://localhost:8123/` (`?engine=rapier` for Rapier; the default is cannon-es). Libraries load from pinned unpkg URLs in an import map.
- `engines/cannon.mjs` and `engines/rapier.mjs`: the adapter. `scenes.mjs`: the ball, swing and 200-body scenes. `bench.mjs` (Node), `bench_browser.mjs` (Chromium), `physics.test.mjs` (the check).
- **The check** (`node --test tools/physics/physics.test.mjs`, after `npm ci` in `tools/physics`) runs both engines and asserts: the ball falls with the free-fall time sqrt(2h/g) within 0.06 s, bounces (rises again, below drop height), and comes to rest on the floor (speed under 0.05, within 3 cm of resting height) within 15 s; the swing crosses the bottom, reaches the other side, does not gain energy, and has the pendulum period within 0.1 s. It then loads the page in headless Chromium, checks that the page's own animation loop drops the ball, steps the page's world, and asserts the same bounce, rest and swing there, with no page errors. Chromium is skipped with a message if Playwright is not installed.
- Ball: first contact at 1.00 s; first rebound apex 1.99 m (cannon-es) and 1.86 m (Rapier); at rest after 4.8 s and 3.9 s. Swing at 0.5 rad, length 2 m: period 2.942 s (cannon-es) and 2.892 s (Rapier) against 2.894 s from the pendulum formula with the large-angle and seat-inertia corrections.
- Checked that it can fail: with gravity changed from 9.81 to 3 in both adapters, all 6 tests failed; with 9.81 restored, all 6 pass. (This also caught a bug in the test itself: a failed assertion left the browser open and the run hung, now fixed with try/finally.)

## Licences

Nothing is vendored: no library file is committed. `tools/physics/package.json` pins the two packages exactly and `package-lock.json` is committed. cannon-es is MIT; `@dimforge/rapier3d-compat` is Apache-2.0 (its package carries the licence; if a Rapier file is ever copied into the repo, include that LICENSE). The page loads them from unpkg at the pinned versions.

## What I could not measure

- Any phone or tablet. They are likely several times slower than this Xeon; the 200-body numbers for cannon-es would then be a real share of a frame. This is the biggest open question and it favours Rapier.
- A real GPU, real rendering cost alongside physics, and the game's frame time with physics in it. Nothing was added to the game.
- Firefox and Safari, and the browser's real download and WASM compile time over a network (Chromium got the files from a local route, not from unpkg).
- Memory use, and garbage-collection pauses (the 52 ms cannon-es spike may be start-up, not steady state; I did not separate them).
- Player-pushes-ball, doors toggling, fast balls through thin walls, and a ball rolling between cells of the `near()` grid.
- Cross-machine determinism (whether two clients given the same kicks agree). Rapier publishes a deterministic build (`@dimforge/rapier3d-deterministic-compat`) that I did not try; for visual-only objects it does not matter, for owner-simulates it could.
- Why Rapier 0.21.0 sleeps less and is twice the size; I used 0.19.3 and left it at that.
- Rapier at 1000 or more bodies; only 200 was asked for.
- That cannon-es is unmaintained: its last release is 0.20.0 (Aug 2022). I take that as a risk, not a measurement.

## Open items

1. Visual only until a physics object pays or is shared; then the server simulates it. Still the default; the owner has not commented on it.
2. Try the prototype on a real phone and record the 200-body and 50-body step times; that decides whether the body budget above is right.
