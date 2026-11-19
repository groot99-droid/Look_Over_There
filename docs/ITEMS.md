# Items: the rules for every item

Session 18. One document a build session can implement from. It covers the 24 items the owner has made models for, plus the three that already exist (the ray, the cloak, the AFK Beacon), so this is the whole item list.

Every line is one of two kinds.

- **[BUILT]** it is in the code today. The file is named and the numbers are copied from it.
- **[PROPOSAL]** a call made in this session. Nothing here is confirmed: the owner can change any of it. Section 12 lists the calls that matter most, each with the default chosen.

Nothing in this session changed game code, models or the manifest.

**Credit.** "Almond water" and the moths behind "moth jelly" (deathmoths) are ideas from Backrooms community lore (the Backrooms wikis), believed to be licensed CC BY-SA. Only the names are used here. Every rule and every line of text in this file is original, and nothing was copied. If text is ever lifted from those wikis, attribute it and keep the licence.

## Contents

1. Rules every item shares
2. The price ladder
3. The three items that already exist
4. Weapons: the master arsenal (10)
5. Consumables (3)
6. Med kit and Spicy Brew (new)
7. Dealer items (5)
8. Food (4)
9. The ten weapons compared, and which to build first
10. Tuning tables
11. What a build session needs
12. Open questions for the owner

---

## 1. Rules every item shares

### 1.1 What is built today (the facts the proposals stand on)

| Fact | Number | File |
|---|---|---|
| Player health | 100 HP, 35 per monster hit, 1 s of grace after any hit, regeneration 1 HP a second starting 10 s after the last hit, a lifted player starts at 50 | `shared/health.js` |
| Down and revive in a room | down for 20 s, a teammate lifts you in 4 s within 2.5 m | `server/playerstate.js` (`DOWNED_S`, `REVIVE_R`), `index.html` (`REVIVE_S`). `docs/WORLD.md` still says 45 s; the code says 20. |
| Player speeds | walk 4.0, run 7.5, crouch 2.2 m/s; a run lasts 4 s and recovers in 6 s | `index.html` (`WALK_SPEED`, `RUN_SPEED`, `CROUCH_SPEED`, `RUN_S`, `RECOVER_S`) |
| Monster kinds | sinew (B1), pale_traveler (L1), clawed (L2), creature (L4, and both built Going back in chambers). All see 16 m in a 110 degree cone and hear 9 m. Chase speeds 5.5, 5.4, 5.7, 5.4 m/s | `world/monsters.json`, `shared/farway.manifest.js` |
| A monster hits you | when it is within 1.0 m with a clear line, at most every 1.2 s per monster | `shared/monsters.js` (`TOUCH_M`), `shared/health.js` (`HIT_GAP`) |
| Monsters have no health | a crossbow bolt, a mine or a tripwire removes a monster outright; the ray moves it | `shared/crossbow.js`, `shared/consumables.js`, `shared/monsters.js` |
| Hearing | running is heard at the full 9 m, walking at half, crouching not at all; a wall halves it. A monster that hears goes to look at its searching pace; only seeing you starts a chase | `shared/monsters.js` (`NOISE_WALK`, `NOISE_WALL`) |
| A shot's noise | the shooter counts as running for 0.5 s (ray) or 0.25 s (crossbow), even when crouched | `shared/monsters.js` (`SHOT_NOISE_S`), `shared/crossbow.js` (`SHOT_NOISE_S`) |
| A loud event | every monster within a radius goes to look unless it is already chasing: 25 m for the tripwire, 40 m for the L1 switches | `shared/consumables.js` (`WIRE_NOISE_R`), `server/floorsim.js` (`ALERT_R`) |
| Keys | 1 ray, 2 cloak, 3 beacon, 4 crossbow. Y rotates (tap) or opens a wheel (hold). Left click or RT uses what you hold. Right click or LT aims the ray, or is the secondary of the cloak and beacon. Q and E (LB and RB) are the consumable slots. F or X is the action button | `index.html` (the `keydown` handler), `tools/controls_test.mjs` |
| Death in Going back in | all gear goes to the locker and comes back free; ray rounds, bolts, beacons and consumables are gone | `shared/loadout.js`, `shared/consumables.js` (`lost`), `index.html` |
| Money | you start the City with $20 | `shared/needs.js` (`MONEY.start`) |
| Pay | Intern $0 to $30 a shift; trash route up to $20; museum up to $20; factory $0 to $20; lab $0 to $20; a true anomaly report $5 once each, a false one costs $2 | `shared/pay.js`, `shared/trash.js`, `shared/museum.js`, `shared/factory.js`, `shared/lab.js`, `shared/anomalies.js` |

### 1.2 Where items exist [PROPOSAL]

| Place | What works there |
|---|---|
| **The Original** | Only the ray, the cloak and the AFK Beacon, as today. No arsenal weapon, no consumable, no med kit, no dealer item. The Q and E slots stay empty. The owner decided the Original is non-lethal; this proposal also keeps it free of everything bought, so a first-time player and a returning one play the same round. |
| **Going back in** | Everything except food. |
| **Secret Operations** | Everything except food. Weapons and gear carry over (`docs/WORLD.md`). |
| **City, hotel, mall, grocery** | Food, dealer items, Spicy Brew. Weapons cannot be taken out there: the bus does not carry them (they wait in your locker). The med kit can be bought and carried but nothing in the City takes HP today. |
| **Overworld** | The Market sells; nothing is used. |

### 1.3 Slots and controls [PROPOSAL]

Nothing that is bound today moves. `tools/controls_test.mjs` must still pass unchanged.

- **Keys 1, 2, 3:** ray, cloak, beacon, as today.
- **Key 4:** arsenal weapon A. [BUILT in solo, session 20: it is the first arsenal weapon you carry, in the order you took them; the crossbow when you start.]
- **Key 5:** arsenal weapon B [BUILT in solo: the second one you carry].
- **You carry at most two arsenal weapons.** The rest wait in the locker. The locker panel gets one row per owned weapon, and choosing a third asks which to leave [BUILT in solo: the locker refuses it with a toast until you leave one; the E slot's key in the panel is then the last row's number, 6].
- **Y:** tap still rotates through what you carry, hold still opens the wheel. The wheel grows from 4 entries to at most 6 (hands, ray, cloak, beacon, A, B). On a controller this is the only way to choose a weapon, as it is today.
- **Left click / RT:** the primary use. Weapons that say "hold" fire for as long as it is held.
- **Right click / LT:** aim (a zoom and a slower look, the ray's rule) for the bolt driver, crossbow, rocket launcher and jelly dart. The other six weapons have a secondary there, written in each entry.
- **Q / LB (support slot) and E / RB (combat slot):** a tap uses the selected item, as today. New: **holding** Q or E for 350 ms (the same time Y uses) opens a small ring of what that slot carries; the right stick, the arrows or the mouse wheel choose, and letting go selects without using. With one kind in a slot the hold does nothing.
  - **Support ring (Q):** flash-vial, med kit, Spicy Brew and the five dealer items.
  - **Combat ring (E):** land mine and tripwire. Today you choose one of the two at the locker; with the ring you carry both and choose in the field. The locker row can stay as a second way to choose.
- **Food** uses no slot. It is eaten at the fridge, as built.
- No new key except 5. No reload key: every reload in this document is automatic.

### 1.4 Monster health [PROPOSAL]

Ten weapons cannot differ if every hit is a kill, so monsters get health in Going back in and Secret Operations. In the Original monsters stay unkillable.

| Kind | Health | Trait (small, so the four kinds differ) |
|---|---|---|
| pale_traveler | 80 | Light hurts it: flash-vial stuns last 1.5 times as long, and the laser does 1.25 times its damage. |
| creature | 100 | The baseline. No trait. |
| clawed | 100 | It grips the floor: every knockback moves it half as far. |
| sinew | 140 | It is wet: burning lasts half as long on it, and electric stuns (the stun baton) last 1.5 times as long. |

- The crossbow bolt, the mine and the tripwire do 150 or more, so what is built today still kills in one, unchanged.
- The ray still does no damage. It banishes.
- **Not killable:** the stalker (the City), the environmental threats of Going back in, and anything later marked as a special entity. On these, damage does nothing, a stun lasts 1 s at most, and a knockback moves them half as far. The Registrar is a boss fight with its own targets (cameras, breakers, server racks) and is not designed here.
- **Agents** (Secret Operations) are killable (`docs/WORLD.md`). Until they are designed, treat one as 60 health with no trait.

**Statuses.** One list, so weapons share code.

| Status | What it does | Exists today? |
|---|---|---|
| Stunned | It neither moves nor hits for the time given. | Yes: `MonsterSim.stun` (the cloak's short circuit, the flash-vial) |
| Banished | Moved 15 m or more from every player and out of sight, waits 4 s, immune to banishing for 8 s. | Yes: `MonsterSim.banish` |
| Lured / alerted | Goes to a point and looks. | Yes: `MonsterSim.alert`, the beacon |
| Slowed | Every speed is multiplied by the factor given. The strongest slow wins; they do not stack. | No |
| Burning | 10 damage a second and slowed to 0.6, for 4 s after the last flame touched it. | No |
| Jellied | 15 damage a second and slowed to 0.5, for 10 s. | No |
| Knocked back | Pushed in a straight line, stopping at the first wall. | No |
| Passive | It does not chase or hit one named player (Green Leaf). | No |

### 1.5 Noise classes [PROPOSAL, built where marked]

Every item names one class. The two mechanisms behind them already exist.

| Class | Meaning | Example |
|---|---|---|
| N0 silent | Nothing hears it. | the land mine [BUILT] |
| N1 puff | You count as running for 0.25 s: heard within 9 m, half through a wall. | the crossbow [BUILT] |
| N2 shot | You count as running for 0.5 s. | the ray [BUILT] |
| N3 bang | Every monster within 15 m goes to look. | new |
| N4 blast | Every monster within 25 m goes to look. | the tripwire [BUILT] |
| N5 alarm | Every monster within 40 m goes to look. | the L1 switches [BUILT] |

For scale: running is N2 for as long as you run, walking is half of that, crouching is silent.

### 1.6 Ammo, packs and death [PROPOSAL, built where marked]

- **Each weapon has its own ammo.** Nothing shares rounds with the ray.
- **An ammo pack** today gives the ray 3 rounds, the crossbow 2 bolts if you carry it, one flash-vial and one of your E item [BUILT: `shared/loot.js`, `shared/crossbow.js`, `shared/consumables.js`]. Proposal: a pack also gives each of the (at most two) arsenal weapons you carry its "pack" amount from the table in section 10. Rockets, med kits and dealer items never come from a pack.
- **On death the locker returns** the ray, the cloak, every arsenal weapon and every weapon upgrade, free [BUILT for the ray, cloak and crossbow: `shared/loadout.js`].
- **On death you lose** every count of bought ammo, every consumable, every beacon and every dealer item you carried [BUILT for rounds, bolts, beacons and the three consumables]. Any dealer effect running on you ends, crash included.
- **Three weapons refill themselves** (the stun baton, the gauntlet and the bolt driver's air) and one refills free at any locker (the horn). After a death they are the weapons that still work with no money. They are the weakest killers, on purpose.
- **Traps you have set** stay until sprung and are cleared when you change chamber [BUILT].

### 1.7 Who can be hurt [PROPOSAL]

- A weapon aimed at a player does nothing. There is no friendly fire from bolts, nails, darts, beams, cuts or punches.
- **Two things hurt everyone in their area, the owner included:** the rocket's blast and the flamethrower's cone. Each is treated as one monster hit (35 HP, with the built 1 s of grace), so a team cannot be wiped by one mistake.
- The three built consumables hurt no player, as today [BUILT: `docs/ROUND.md`, slice 3].
- Dealer effects are personal. Other players see a small icon by your name tag and nothing else.

### 1.8 In a room: the pattern for every item [PROPOSAL]

The server already owns each player's HP, rounds, beacons and cloak, and resolves a `shot` on its own monsters (`server/playerstate.js`, `server/floorsim.js`). Every item follows the same pattern, and each entry below only adds what is special.

- The client sends an intent (for example `{t:"fire", w:"driver", o, d}`, `{t:"use", slot:"q", kind:"medkit"}`, `{t:"buy", id, n}`).
- The server owns: what you own and carry, every ammo count, every cooldown and reload clock, monster health and statuses, the hit, the kill, the money. It checks the shot starts near the shooter, as it does for the ray.
- The server tells the floor what happened (a beam, a blast, a status) so every client can draw it. Clients draw; they decide nothing.
- Dealer effects: the server owns the timers and applies what changes the rules (speed limits, noise, damage taken, who a monster ignores). The filters and the wobble are drawn by the client.

---

## 2. The price ladder [PROPOSAL]

One currency, dollars, everywhere. The anchor is built: **one good shift pays about $20** and a game day (15 real minutes) has room for one or two shifts, while eating costs about $6 a day (hunger drains 100 in 36 game hours, and a $6 ready meal gives 60: `shared/needs.js`).

| Tier | Price | What is in it | In shifts |
|---|---|---|---|
| Food | $1 to $6 | the four groceries [BUILT] | minutes |
| Ammo | $1 to $5 a refill; a rocket $8 | nails, bolts, ray rounds, propane, batteries, fluid, darts | a refill is a quarter of a shift or less |
| Consumables | $5 to $12 | flash-vial $5, land mine $6, AFK Beacon $6, tripwire $10, med kit $12 | about half a shift each |
| Dealer items | $5 to $15 | Old Brew $5, Spicy Brew $7, Munchy Mushies $8, Green Leaf $10, Trippy Paper $12, Sugar Rush $15 | half a shift to most of one |
| Weapons | $25 to $180, bought once and kept for good | see below | 1 to 9 shifts |
| Weapon upgrade | $100 | the gauntlet's violet lenses | 5 shifts |
| Perks | $80 to $150 | not designed in this document | 4 to 8 shifts |
| Keycards | tier 1 $300, tier 2 $750 | `keycard_tier_1`, `keycard_tier_2` in the manifest's flags | 15 and 38 shifts |

**Weapons.**

| Weapon | Price |
|---|---|
| Pneumatic bolt driver | $25 |
| Hunting crossbow | $40 (free in your hands until the Market exists, as built) |
| Stun-baton capacitor | $45 |
| Spring gauntlet (unlit) | $50 |
| Sound-amplified frequency horn | $55 |
| Moth jelly dart | $60 |
| Hydraulic rebar shear | $70 |
| Propane flamethrower | $90 |
| Optical laser pointer dissector | $110 |
| Almond water aerosol rocket launcher | $180 |

**Ammo.**

| Ammo | Price | For |
|---|---|---|
| Ray rounds | $2 for 3 | the ray |
| Bolts | $1 each | crossbow |
| Nails | $1 for 8 | bolt driver |
| Propane canister | $4 | flamethrower (a full tank) |
| Battery pack | $5 | laser dissector (a full charge) |
| Hydraulic fluid | $3 | rebar shear (4 cuts) |
| Car battery | $4 | horn (6 blasts; a recharge at a locker is free) |
| Jelly dart | $3 each | moth jelly dart |
| Rocket | $8 each | rocket launcher |
| (none) | free | stun baton, gauntlet |

**Money earned in Going back in** (the bible says chamber clears, kills and revives pay; no number exists): $1 a kill, $2 a revive, $5 a chamber cleared, $10 more for a floor's fourth chamber. A full 20-chamber run with waves of 3 pays about $210, which is roughly what its ammo and one buy-back cost.

**Where things are sold.** The Market (Overworld) sells everything in the weapon, ammo, consumable, perk and keycard tiers. A safe house shop (Going back in) sells ammo, consumables and med kits only, at the same prices. The dealers sell only dealer items. The grocery sells only food. Nothing is sold in the Original.

**A buy-back, as a check.** After a death with the starting kit of today (3 rounds, 4 bolts, 2 flash-vials, 2 mines): $2 + $4 + $10 + $12 = $28, a shift and a half.

---

## 3. The three items that already exist

These are not changed by this document. Their numbers are from the code.

### Error Deletion Ray [BUILT: `shared/monsters.js`, `shared/loot.js`]

- **What it is.** A taped-up ray gun with an "ERR" display. It does not kill. It no-clips a monster to somewhere else, which is the same act the world does to people.
- **Where you get it.** A B1 locker in the Original (8 lockers, one ray and one cloak each, taken once). In Going back in you start with it. Price: none; rounds $2 for 3 [PROPOSAL].
- **Slot and controls.** Key 1. Left click / RT fires. Right click / LT aims.
- **What it does.** A hitscan ray 25 m long, blocked by walls and shut doors, hitting within 0.6 m of a monster's body. One shot every 0.6 s. The monster flickers for 0.5 s, then stands at a spot at least 15 m from every player, out of everyone's sight and 35 m away by path where the floor allows. It waits 4 s and patrols again. It cannot be banished again for 8 s, so a second shot in that time is wasted. The same for every monster kind. It does nothing to a player.
- **Noise.** N2.
- **Ammo.** Rounds: 3 with the gun, 3 in a pack, 9 at most. Lost on death in Going back in.
- **Downside.** It solves one chase, not a floor: the monster comes back, and it may land near your objective.
- **Where it works.** Everywhere monsters are, the Original included.
- **In a room.** The server takes the round, checks the shot and resolves it on its own monsters [BUILT].
- **What I would change.** Nothing now. Once monsters have health, a banished monster keeps the health it had.

**Admin's red version, "ATL X"** [PROPOSAL; only the name, the colour and "deletes instead of no-clipping" are in `docs/WORLD.md`, and nothing is in the code but the `admin_access` flag]. Held only by a player with `admin_access` (after The Registrar). The same gun, red. A hit removes the monster for good and counts as a kill; there is no flicker wait and no immunity. Rounds are not counted. On a player in a room it does nothing unless the room's host has switched "admin rules" on; then the player is sent to the Overworld's table and chairs, with nothing shown. It is not sold and cannot be put in the locker of a player without the flag.

### Cloak [BUILT: `shared/cloak.js`]

- **What it is.** A battery-powered sheet that makes monsters lose sight of you.
- **Where you get it.** The same B1 locker; you start with it in Going back in. Not sold.
- **Slot and controls.** Key 2. Left click / RT switches it on and off. Right click / LT is the short circuit.
- **What it does.** On: monsters cannot see you beyond 1.5 m. They still hear you. The battery lasts 15 s, recharges in 45 s after 2 s off, and will not switch on below 10%. Short circuit: every monster within 8 m is stunned for 5 s and the cloak is dead for 5 minutes.
- **Noise.** N0. **Ammo.** None: the battery. **Downside.** It does nothing about sound, and the short circuit costs you the cloak for 5 minutes.
- **In a room.** The server owns the battery and the stun [BUILT].
- **What I would change.** Nothing. Proposal for the arsenal: firing the flamethrower switches the cloak off.

### AFK Beacon [BUILT: `shared/beacon.js`, `shared/loot.js`]

- **What it is.** A can that broadcasts "a disconnected player with 1 HP". Monsters cannot resist it.
- **Where you get it.** Two lie on every floor of the Original, taken once. You start Going back in with none. Proposal: $6 at the Market and the safe house shop.
- **Slot and controls.** Key 3. Left click / RT rolls it. Right click / LT reverses the nearest running one.
- **What it does.** Rolls up to 12 m, stopping at a wall. For 25 s every monster within 30 m goes to a ring 1.5 to 3 m round it and idles, ignoring players unless one comes within 4 m of that monster. Reverse (once per beacon): they run from it for 12 s, then group round it for at least 10 s more.
- **Noise.** N0. **Ammo.** It is its own ammo: carry 2 at most. Lost on death in Going back in (counted as charges). **Downside.** It only moves the problem, and walking within 4 m of a lured monster wakes it.
- **In a room.** The server counts beacons and runs the lure [BUILT].

---

## 4. Weapons: the master arsenal

All ten: bought at the Market, kept for good, returned free by the locker, used in Going back in and Secret Operations only. Each entry says only what is special; sections 1.6 to 1.8 give the shared rules. Kill counts per monster kind are in the table in section 9.

### 4.1 Pneumatic bolt driver [BUILT, solo Going back in] (model: `Rustborn_Raycaster`)

**Built (session 19):** `shared/driver.js` and `shared/driver.test.js` (the rules), `MonsterSim.hurt` and `hp` in `world/monsters.json` (`shared/monsters.test.js`), the page (`index.html`: key 5, the locker row, the HUD line `NAILS n/32 AIR ▮▮▮…`, packs, death) and `tools/driver_test.mjs`. Everything below is as built except what this note lists.
- *Not built yet:* the Market (like the crossbow, it starts in your hands, with 16 nails, until the Market exists); the right-click / LT aim; the monster traits of 1.4 (only the health is built, and since the baton the sinew's longer stun); the model (a box placeholder is drawn in code; `models/items/pneumatic_bolt_driver.glb` is not loaded); rooms: session 16's server runs three pieces of gear (`GEAR` in `shared/loadout.js`), so the driver is `SOLO_GEAR` only, absent from a room's loadout and locker rows, until the server owns its nails, gauge and hits.
- *Clarified while building:* the air refills one eighth every 1.5 s starting 1 s after your last shot, so from empty it is full again 13 s after the last shot (12 s of refilling). The weapon's damage is read before the eighth is spent, so shots from a full gauge do 35, 32.5, 30, 27.5 ...
- *Built:* a creature (100) falls to 4 nails, as the table in section 9 says.

- **What it is.** A rusted nail gun with a pressure gauge and a coiled air hose. The first thing you can afford: it works, as long as you let it breathe.
- **Role.** The cheap workhorse: single target, a short burst, mid range.
- **Where and price.** Market, $25.
- **Slot and controls.** Arsenal slot (key 4 or 5). Left click / RT fires one nail a press. Right click / LT aims.
- **What it does.** A hitscan nail, 18 m, the ray's 0.6 m hit radius. One shot every 0.35 s. Damage follows the gauge: 35 at full pressure down to 15 at empty. Each shot takes an eighth of the gauge, so eight shots from full do 35, 32.5, 30, 27.5, 25, 22.5, 20 and 17.5. After 1 s without firing the gauge refills an eighth every 1.5 s (12 s from empty). With the gauge empty it still fires at 15.
- **Noise.** N1 a shot.
- **Ammo.** Two things. Nails are bought: start 16, cap 32, a pack gives 8, $1 for 8. Air is free: the gauge above. On death the nails are lost and the gauge is full.
- **Downside.** The third and fourth shots are weak, so it kills one monster and then needs 12 s. Two monsters at once are too many.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server owns the nail count and the gauge, so a client cannot fire a full-pressure shot twice.

### 4.2 Hunting crossbow [BUILT: `shared/crossbow.js`, `shared/crossbow.test.js`, `index.html`] (model: `Rustbound_Recurve`)

- **What it is.** A crossbow with a taped stock and a scope. Slow, quiet and final.
- **Role.** The quiet single kill.
- **Where and price.** Today it starts in your hands in Going back in, because the Market does not exist. Proposal: $40 at the Market once there is one.
- **Slot and controls.** Key 4. Left click / RT shoots. There is no aim today; proposal: right click / LT aims, since the model has a scope.
- **What it does, as built.** The ray's hitscan (25 m, 0.6 m radius, blocked by walls). A bolt that hits a monster kills it for good, whatever its state, banished or glitching included. 1.8 s reload between shots. A kill counts toward the wave, and killing the whole wave clears it. It does nothing to a player.
- **Noise, as built.** N1: half the ray's.
- **Ammo, as built.** Bolts: 4 at the start, 6 at most, +2 from each ammo pack picked up while you carry it. Lost on death.
- **Downside.** One shot every 1.8 s and six bolts. A miss costs a sixth of everything you have.
- **In a room.** Session 16 is giving the server the bolts, the reload clock and the kill.
- **What I would change.**
  1. Give the bolt a damage number, 150, so it still kills all four kinds in one hit under the health rule and a later tougher thing can survive one.
  2. A bolt that kills can be picked up again where the monster fell (walk over it). A miss is gone. This rewards aim and keeps the cap of 6 meaningful.
  3. Sell bolts at $1 each, and the crossbow at $40, when the Market exists. Until then keep the free start.
  4. Add the aim on right click / LT.

### 4.3 Propane flamethrower [BUILT, solo Going back in] (model: `Rustborn_Flamethrower`)

**Built (session 22):** `shared/flame.js` and `shared/flame.test.js` (the fuel, the swap, the cone, the wall at your feet), the Burning status on `MonsterSim` (`burn`, and `statusTick` now adds every running status together; `shared/monsters.test.js`), `burnTime` on the sinew in `world/monsters.json`, the page (`index.html`: hold to burn on left click or RT, the swap on right click or LT, orange puffs along the view, a red-orange glow on a burning monster, the HUD line `FUEL 90%  SPARE 100%`, packs, death), `tools/flame_test.mjs`. Everything below is as built except what this note lists.
- *Readings I made where the text was open:* the burn damage (10 a second) runs the whole time a monster is burning, including while you still hold the flame on it, so inside the flame it is 50 a second and a creature falls in 2 s (20% of a tank), not the 2.5 s the table in section 9 gives; a pack's 25% goes to the tank and what does not fit fills the spare canister (so a spare comes from packs until the Market sells canisters); swapping exchanges the two canisters (a half-empty one becomes the spare); a burst is "new" after 0.5 s without flame; a wall within 1 m of your face costs you one hit of 35, repeated each time the hit's one second of grace ends while you keep burning it; you count as running (noise) for as long as you fire and the cloak goes off.
- *Not built:* the Market (it starts in the locker, with a full tank and no spare); the toxic gas chamber's ignition (no gas exists yet); the model (a placeholder is drawn in code); rooms (solo only, `SOLO_GEAR`); the other players' hit from the flame (solo has none).

- **What it is.** A blue propane tank strapped to a rifle frame. It lights the corridor up, and everything in the corridor knows.
- **Role.** Close area control: it holds a doorway against a crowd.
- **Where and price.** Market, $90.
- **Slot and controls.** Arsenal slot. Hold left click / RT to burn. Right click / LT swaps in the spare canister (2.5 s).
- **What it does.** A cone 6 m long and 40 degrees wide, blocked by walls. Everything in it takes 40 damage a second and is Burning (10 a second and slowed to 0.6, for 4 s after the flame leaves it). A burning monster chases at about 3.3 m/s, slower than your 4 m/s walk, so you can back away while you burn it. On the sinew burning lasts 2 s. A player in the cone, you included if you fire into a wall at your feet, takes one hit of 35.
- **Noise.** N3 when a burst starts, and you count as running for as long as you fire. Firing switches your cloak off.
- **Ammo.** Propane: the tank holds 100% and burns 10% a second (10 s of flame). Start with a full tank; carry one spare canister at most; a pack gives 25%; a canister is $4. Lost on death: the tank is empty and the spare is gone.
- **Downside.** Six metres is close, it calls the floor to you, and ten seconds go quickly. It cannot be used cloaked.
- **Where it works.** Going back in, Secret Operations. Proposal for a toxic gas chamber: lighting it there sets the gas off, one hit of 35 to everyone in the gas.
- **In a room.** The server owns the fuel and the burning status, and decides who is in the cone each tick.

### 4.4 Stun-baton capacitor [BUILT, solo Going back in] (model: `Rustbound_Contraption`)

**Built (session 20):** `shared/baton.js` and `shared/baton.test.js` (the rules), `batonStun` on the sinew in `world/monsters.json`, the page (`index.html`: the swing, the discharge, a placeholder mesh drawn in code, the HUD line `BATON ● ● ○`), `tools/baton_test.mjs`. It also builds the two-weapon carry cap and the weapon slots of 1.3, because a third arsenal weapon is what makes them bind (`ARSENAL`, `MAX_ARSENAL`, `canTake` in `shared/loadout.js`). Everything below is as built except what this note lists.
- *Readings I made where the text was open:* a swing that misses costs nothing but the cooldown (only a hit uses a capacitor); the baton does not charge while it is dead (so the first capacitor is back 20 + 8 s after a discharge); a death changes nothing about its charge ("nothing is lost"); the 60 degree arc is measured on the floor plane from where you face, with a clear line to the monster's middle.
- *Not built:* the Market (it starts in the locker because you carry two arsenal weapons at most, so you leave the crossbow or the driver to take it); the model (a placeholder is drawn in code); rooms (solo only, `SOLO_GEAR`); the other monster traits of 1.4 (only the sinew's longer stun).

- **What it is.** A long baton with a bank of capacitors and bare wires. It does not finish anything. It makes something stop.
- **Role.** Melee crowd control with free ammo: the weapon that still works after you have lost everything.
- **Where and price.** Market, $45.
- **Slot and controls.** Arsenal slot. Left click / RT swings. Right click / LT discharges everything.
- **What it does.** A swing reaches 1.8 m in a 60 degree arc and hits the nearest monster in it: 25 damage and Stunned for 4 s (6 s on the sinew). One swing every 0.6 s. Each hit uses one of three capacitors. Discharge (needs all three): every monster within 4 m takes 15 and is stunned for 3 s, and the baton is dead for 20 s.
- **Noise.** N1 a hit; N3 for the discharge.
- **Ammo.** No ammo to buy. Three capacitors; an empty one recharges in 8 s, one at a time. Nothing is lost on death.
- **Downside.** You have to be within 1.8 m of something that hits at 1.0 m. Four hits to kill needs more than the three capacitors, so it cannot kill quickly alone.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server owns the capacitors and the stun.

### 4.5 Almond water aerosol rocket launcher [PROPOSAL] (model: `Scrapyard_Blaster`)

- **What it is.** A shoulder tube with aerosol cans strapped on. One loud answer to a room that has gone wrong.
- **Role.** The big area burst. Very loud, very few shots.
- **Where and price.** Market, $180. A rocket is $8.
- **Slot and controls.** Arsenal slot. Left click / RT fires. Right click / LT aims.
- **What it does.** A rocket flies at 25 m/s for up to 40 m and bursts on the first thing it meets. Monsters within 2 m take 150; from 2 m out to 5 m the damage falls evenly to 50. It then leaves a mist 5 m wide for 6 s: monsters in it are slowed to 0.5. A rocket that hits within 5 m of you has not armed: it drops, does nothing and is lost. Players within 5 m of a burst take one hit of 35. Reload 3.5 s. You cannot run while it is in your hands.
- **Noise.** N5 at the burst: every monster within 40 m comes to look at where it landed.
- **Ammo.** Rockets: start with 1 when you buy it, cap 3, never in a pack, $8 each. Lost on death.
- **Downside.** Three shots at $8, it empties the floor onto the spot you fired at, it hurts you inside 5 m, and you walk.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server flies the rocket and owns the burst, the mist and who was in it.

### 4.6 Optical laser pointer dissector [PROPOSAL] (model: `Scraplight_Blaster`)

- **What it is.** A lens assembly on a drum, fed by battery packs. At low power it is a red dot on the far wall, and things go and look at it. At full power it takes things apart quietly.
- **Role.** Silent, long range, and the game's title as a mechanic: look over there.
- **Where and price.** Market, $110.
- **Slot and controls.** Arsenal slot. Hold left click / RT for the beam. Hold right click / LT for the pointer dot.
- **What it does.**
  - **Beam.** Hitscan, 30 m. Damage climbs the longer it stays on one target: 15 a second at first, rising evenly to 60 a second after 2 s. Leaving the target for more than 0.3 s starts the climb again. 1.25 times the damage on the pale_traveler. You move at crouch speed (2.2 m/s) while it is on. After 5 s of beam it overheats and locks for 3 s. A monster hit while patrolling or searching turns and chases you.
  - **Dot.** A dot where you point, up to 30 m. A monster that is patrolling or searching, within 12 m of the dot and with a clear line to it, walks to the dot and looks, for as long as you hold it there and 6 s after (the built search time). It does nothing to a monster that is chasing.
- **Noise.** N0 for both.
- **Ammo.** Battery: 100% a pack. The beam uses 8% a second (12.5 s), the dot 0.5% a second. Start with one pack loaded and one spare; carry two spares at most; a pack pickup gives 25%; a battery pack is $5. A swap is automatic and takes 2 s. Lost on death: the charge is zero and the spares are gone.
- **Downside.** It kills one thing at a time, slowly, while you stand nearly still, and the thing knows where you are from the first second. It is poor against two.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server owns the charge, the heat, the damage climb per target, and the dot's lure.

### 4.7 Hydraulic rebar shear [PROPOSAL] (model: `Rustborn_Rebar_Cannon`)

- **What it is.** A heavy jaw on a hydraulic cylinder with a motor. Built to cut steel bar. It does not care what is in the jaw.
- **Role.** The melee finisher, and the tool that opens what is shut.
- **Where and price.** Market, $70.
- **Slot and controls.** Arsenal slot. Hold left click / RT to spool the motor (1.0 s), let go to cut. Right click / LT does nothing.
- **What it does.** Once spooled you can hold it ready for up to 3 s. Letting go cuts the nearest thing in a 2.0 m reach and a 30 degree arc: 200 damage to one monster, which kills any of the four kinds. 1.5 s before you can spool again. The same cut opens one barricade, chain, padlock or vent grille (Going back in's doors can be barricaded: `docs/WORLD.md`), and in Secret Operations cuts a camera's cable or a breaker's feed without setting it off. You walk at 0.8 of your speed while it is in your hands.
- **Noise.** N2 while the motor spools and for the cut.
- **Ammo.** Hydraulic fluid: a cartridge is 4 cuts. Start with one loaded; carry two spare; a pack gives 2 cuts; a cartridge is $3. A cut on empty air still uses one. Lost on death.
- **Downside.** A chasing monster crosses the gap between your 2.0 m and its 1.0 m in under a fifth of a second. Alone it is a timing gamble; it wants a stunned, slowed or lured target, so it pairs with the flash-vial, the baton, the jelly dart and the beacon.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server owns the spool clock, the fluid, the kill and which barricade or cable was cut.

### 4.8 Sound-amplified frequency horn [BUILT, solo Going back in] (model: `Junkyard_Sonic_Blaster`)

**Built (session 23):** `shared/horn.js` and `shared/horn.test.js` (the battery, the two cooldowns, the cone, the knockback), `shared/cone.js` (the cone test, now shared with the flamethrower), `MonsterSim.shove` and `knockback` on the clawed in `world/monsters.json`, the page (`index.html`: the blast on left click or RT, the call on right click or LT, rings along the cone, the HUD line `HORN ▮▮▮▮▮▯ 5/6`, a free recharge each time you open the locker, death), `tools/horn_test.mjs`. Everything below is as built except what this note lists.
- *Readings I made where the text was open:* the blast and the call have separate cooldowns (a blast does not stop a call and the other way round); a knocked-back monster is moved at once, in quarter-metre steps straight away from you, and stops 0.5 m before anything solid or at the edge of the walkable floor; opening the locker recharges the battery whether the horn is in your hands or in the locker, so taking it out always gives a full one; a monster already chasing is not drawn by the call or the blast (the alert never takes a chaser off its chase), but is still thrown and stunned by a blast; the blast's noise and the call's reach are measured from where you stand, on your floor.
- *Not built:* the spare battery has a rule (`addSpare`, the automatic 3 s swap, both tested) but no source until the Market sells it ($4); the Market; the model (a placeholder is drawn in code; `models/items/frequency_horn.glb` is not loaded); rooms (solo only, `SOLO_GEAR`); the unkillable monsters' halved knockback (no such monster is in the mode yet).

- **What it is.** A dented megaphone horn wired to a car battery box. It hurts nothing. It moves everything, and then everything comes.
- **Role.** The loud lure and the shove. No damage at all.
- **Where and price.** Market, $55.
- **Slot and controls.** Arsenal slot. Left click / RT is the blast. Right click / LT is the call.
- **What it does.**
  - **Blast.** A cone 10 m long and 60 degrees wide. Every monster in it is knocked back 6 m (3 m for the clawed), stopping at a wall, and Stunned for 2 s. No damage. 4 s between blasts.
  - **Call.** One low tone. Every monster within 25 m comes to look at where you stood. It uses no charge. 4 s between calls.
- **Noise.** N5 for the blast, N4 for the call. That is the point of it.
- **Ammo.** A car battery: 6 blasts. Recharging at any locker or safe house is free. One spare battery may be carried ($4), swapped automatically in 3 s. On death the charge is zero and the spare is gone; the next locker fills it again.
- **Downside.** It kills nothing and tells the whole floor where you are. Used without a plan it is the worst item in the game.
- **With a plan.** Call a wave onto a tripwire or into a rocket. Blast a chaser back down the corridor it came from and shut the door.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server owns the charge, the knockback and the alert.

### 4.9 Moth jelly dart [BUILT, solo Going back in] (model: `Moth_Jelly_Blaster`)

**Built (session 21):** `shared/dart.js` and `shared/dart.test.js` (the ammo, the projectile and the spread), the statuses on `MonsterSim` in `shared/monsters.js` (`slow`, `slowMul`, `jelly`, `statusTick`; `shared/monsters.test.js`), the page (`index.html`: the dart in the air, an amber glow on a jellied monster, the map mark, the HUD line `DARTS n/5`, packs, death), `tools/dart_test.mjs`. It is the first thing to use the Slowed status of 1.4, so the flamethrower and the rocket's mist can reuse it. Everything below is as built except what this note lists.
- *Readings I made where the text was open:* the strongest slow wins and replaces a weaker one (a weaker one does not resume when the stronger ends); a dart restarts the 10 s and never adds to the damage (the dps stays 15); the spread is itself a jelly of 5 s, so a monster already jellied for longer keeps its longer time, and a monster the spread kills infects its neighbours in turn; any death of a jellied monster spreads (a baton or a bolt too); the dart flies straight (no drop); a dart in the air is lost when you change chamber.
- *Not built:* the Market; the right-click / LT aim; the model (a placeholder is drawn in code); rooms (solo only, `SOLO_GEAR`); the "team map" is the handheld map today and shows a jellied monster at its real position, refreshed every 0.2 s, while the jelly lasts.

- **What it is.** An air rifle with a syringe of amber jelly. You fire once and walk away. The moths do the rest.
- **Role.** Silent damage over time. Fire and leave.
- **Where and price.** Market, $60. A dart is $3.
- **Slot and controls.** Arsenal slot. Left click / RT fires. Right click / LT aims.
- **What it does.** A dart flies at 35 m/s for up to 30 m, so a moving target needs a lead. The monster it hits is Jellied for 10 s: 15 damage a second (150 in all, enough for any of the four kinds) and slowed to 0.5, which is slower than your walk. A second dart on the same monster only restarts the 10 s. A jellied monster shows on the team map while it lasts. When a jellied monster dies, every monster within 4 m of it is jellied for 5 s (75 damage). Reload 2.5 s.
- **Noise.** N0.
- **Ammo.** Darts: start 3, cap 5, a pack gives 1, $3 each. Lost on death.
- **Downside.** Nothing happens for several seconds: the monster keeps coming, at half speed, and still hits if it reaches you. A kill takes 5 to 10 s. A missed dart is $3 gone.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server flies the dart and owns the status, the spread on death and the kill (credited to whoever fired).

### 4.10 Spring-loaded gravity gauntlet [PROPOSAL] (model: `Violet_Arc_Gauntlet`)

- **What it is.** A forearm gauntlet of springs with violet lenses. A wound spring, let go at the right moment, moves a monster. Or you.
- **Role.** Movement, and the shove.
- **The plain, unlit version.** It is the same item, in two states. You buy it unlit, as the **Spring gauntlet** ($50): the punch only. Fitting the **violet lenses** ($100, at the Market, kept for good and returned by the locker like the weapon) makes it the **Gravity gauntlet** and adds the leap. The lit model's lenses also show the charge: three bright, dim when empty. One item, one slot, one upgrade.
- **Slot and controls.** Arsenal slot. Left click / RT punches. Right click / LT leaps (lenses only).
- **What it does.**
  - **Punch** (1 charge). Reaches 2.0 m. 30 damage, a knockback of 5 m (8 m with the lenses; half for the clawed) and Stunned for 1 s. A monster knocked into a wall takes 30 more. 0.8 s between punches.
  - **Leap** (2 charges, lenses only). Throws you up to 9 m the way you look and up to 3 m high. No fall damage from it. It crosses what the floor cannot: lava, tide, the chainsaw blades' lane. You cannot leap while carrying an objective object.
- **Noise.** N1 a punch. N2 where you land.
- **Ammo.** No ammo to buy. Three spring charges; one rewinds every 5 s on its own. Nothing is lost on death.
- **Downside.** It kills slowly (30 a punch) at arm's length, the leap can put you somewhere worse, and a leap leaves one charge for whatever is waiting there.
- **Where it works.** Going back in, Secret Operations.
- **In a room.** The server owns the charges and the knockback, and checks a leap's landing spot is one the floor allows (within 9 m, not through a wall), as it checks a shot's start.

---

## 5. Consumables

Single use, on Q and E, in Going back in and Secret Operations. The three below are built for solo Going back in (`shared/consumables.js`, `shared/consumables.test.js`, `index.html`, `tools/gbi3_test.mjs`).

### 5.1 Phosphor-core incendiary flash-vial [BUILT] (model: `Rustbound_Ember_Lantern`)

- **What it is.** A glass vial with a phosphor core in a wire cage. It goes off like a camera flash the size of a room.
- **Where and price.** You start Going back in with 2. Proposal: $5 at the Market and the safe house shop.
- **Slot and controls.** Q / LB, the support slot.
- **What it does, as built.** Thrown 6 m ahead, stopping at a wall. Every monster within 6 m of where it lands is stunned for 6 s. It kills nothing and does nothing to a player. Proposal with the health rule: 9 s on the pale_traveler.
- **Noise.** None in the code.
- **Ammo, as built.** Start 2, cap 3, +1 from each ammo pack. Lost on death.
- **Downside.** Six seconds, and then everything is exactly where it was.
- **In a room.** The server owns the count, the landing spot and the stun.
- **What I would change.**
  1. It is named "incendiary" and burns nothing. Keep it harmless (Q is the support slot) and let the name be the brand on the vial. The alternative, a short Burning status, is in the open questions.
  2. In a room, a teammate within 6 m who is looking at it gets a white screen for 1.5 s. No stun, no damage. It makes the throw a call you shout first.
  3. Give it noise class N1.

### 5.2 Almond water land mine [BUILT] (model: `Scrapyard_Contraption`)

- **What it is.** A pressure plate on a can of something that should have been a drink. It makes one quiet correction.
- **Where and price.** You start with 2. Proposal: $6.
- **Slot and controls.** E / RB, the combat slot. Today the locker chooses between this and the tripwire.
- **What it does, as built.** Set down where you stand. Armed after 1.5 s. The first monster within 1.2 m sets it off and dies: one monster, the nearest. It is not loud. It counts as a kill toward the wave. It does nothing to a player.
- **Noise, as built.** N0.
- **Ammo, as built.** Start 2, cap 3, +1 from a pack when it is your E item. Lost on death. A set mine stays until sprung and is cleared when you change chamber.
- **Downside.** One monster, and only if it walks over that exact square metre.
- **In a room.** The server owns the trap list and springs it on its own monsters.
- **What I would change.**
  1. With the health rule it does 200 to the one monster.
  2. An unsprung mine can be picked up again with the action button, so leaving a chamber does not waste one.
  3. Carry both traps and choose with a held E (section 1.3).

### 5.3 Compressed-air nail-bomb tripwire [BUILT] (model: `Rustfang_Apparatus`)

- **What it is.** An air cylinder packed with nails, on a wire across a doorway. The loud correction.
- **Where and price.** You start with 1. Proposal: $10.
- **Slot and controls.** E / RB.
- **What it does, as built.** Armed after 0.5 s. A monster within 2 m sets it off and every monster within 3 m dies. The blast is loud: monsters within 25 m go and look. Each death counts toward the wave. It does nothing to a player.
- **Noise, as built.** N4.
- **Ammo, as built.** Start 1, cap 2, +1 from a pack when it is your E item. Lost on death.
- **Downside.** It can kill a whole wave or one straggler, and either way it brings the rest.
- **In a room.** As the mine.
- **What I would change.**
  1. With the health rule it does 200 to everything within 3 m.
  2. Keep it harmless to players for now; whether the blast should cost a careless player one hit is in the open questions.
  3. It should be set on a doorway or corridor (snapped to the nearest one within 2 m) so the model reads as a wire. Where there is none it sits on the floor as today.

---

## 6. Med kit and Spicy Brew (new)

### 6.1 Med kit [PROPOSAL] (model: `Apocalypse_Med_Kit`)

- **What it is.** A battered red first-aid tin. Somebody packed it carefully, a long time ago, for somebody else.
- **Where and price.** $12 at the Market and the safe house shop. Found: one at a seeded spot in the first chamber of each Going back in floor (5 in a run), taken once, like a pack. Never in an ammo pack.
- **Slot and controls.** Q / LB, in the support ring. Hold Q for 2.5 s to use it; letting go early cancels and keeps the kit. You move at crouch speed and cannot use what you hold while you do it.
- **What it does.**
  - **On yourself:** +60 HP at once, and regeneration starts straight away instead of after the built 10 s wait. Refused at 95 HP or more ("You do not need it").
  - **On a downed teammate, in a room:** hold the action button beside them as usual. With a med kit carried, the lift takes 1.5 s instead of the built 4 s and they stand up at 100 HP instead of 50. It uses the kit.
  - It does nothing to monsters and cannot be used on a standing teammate.
- **Noise.** N0.
- **Ammo.** Carry 2 at most. Start with none. Lost on death, like every consumable.
- **Downside.** Two and a half seconds of standing nearly still, at $12, taking the slot press a flash-vial could have had. Regeneration is free if you can hide for 10 s; the kit is for when you cannot.
- **Where it works.** Going back in and Secret Operations. Not the Original (section 1.2): its regeneration, downs and lifts already do this job, and the round stays the same for everyone. It can be carried in the City but nothing there takes HP today.
- **In a room.** The server owns the count, the 2.5 s clock (it must see the hold start and end), the HP and the faster lift.

### 6.2 Spicy Brew (model: `Spicy_Brew_Bottle`)

**The rule is the owner's, relayed to this session by the owner's coordinating session after the first draft** (marked **[OWNER, relayed]**; this session could not confirm it with the owner directly). The numbers are proposals.

- **What it is.** "XXX Spicy Brew", a chilli on the label. It does to your legs what Old Brew does to your balance, and it burns through you while it does it.
- **The rule [OWNER, relayed].** It has Old Brew's alcohol effects: the funny walk and run, the wobble that grows with each drink, and aim you cannot hold steady. But it makes you faster, and instead of making you pass out it makes you hungrier. Each drink speeds you up and drains hunger, stacking. Too much of it and you die of hunger quickly. There is no blackout from Spicy Brew.
- **How it differs from Old Brew.** Old Brew: 5% less damage taken a bottle, blackout at 5. Spicy Brew: faster a bottle, no damage reduction, no blackout, and it eats your hunger.
- **Where and price [PROPOSAL].** $7, from the same dealer who sells Old Brew, and at the Market.
- **Slot and controls [PROPOSAL].** Q / LB, in the support ring. A tap drinks it (1 s).
- **The numbers [PROPOSAL].**
  - A drink lasts 90 s, the same as an Old Brew drink.
  - **Wobble.** Each running drink adds the same sway and aim drift as an Old Brew drink (0.25 m and 1 degree), and the two brews add together for wobble. The aim zoom does not hold steady.
  - **Speed.** Each running drink adds 8% to every speed of yours, up to 5 drinks (+40%: walk 5.6, run 10.5 m/s). A sixth adds no speed. A run still lasts 4 s. With a trip running the two multiply, and the total is capped at 1.6 times normal.
  - **Hunger.** Each running drink drains 8 hunger a real minute on top of the normal drain, so one drink costs 12 hunger over its 90 s. **Too much is four:** with four or more running at once every drink drains double, 16 a minute each. Four drinks together are 64 a minute, so the City's starting 80 is gone in 75 s.
  - **No blackout.** Spicy Brew drinks do not count toward Old Brew's five. Only Old Brew drinks do.
- **Hunger where hunger exists (the City).** It uses the built hunger in `shared/needs.js` as it is: the same 0 to 100 bar, the same warnings at 30 and 10, and at 0 the built rule, you faint and wake at home with 25. The City has no death today, so "die of hunger" is that faint there. The extra drain runs on real time, so it keeps draining while the City's clock is paused. Green Leaf's doubling applies to the normal drain only.
- **Hunger where there is none yet (Going back in, Secret Operations).** Your one hunger bar travels with you. Nothing drains it there today except Spicy Brew, and the HUD shows the bar while a drink is running. At 0 you die, by that mode's death rule (gear to the locker, ammo and consumables lost), and you come back with hunger at 25. What you spent stays spent: you arrive back in the City as hungry as you left the run. A player who has never been to the City starts at the built 80.
- **Getting hunger back.** Only food at the fridge, and Munchy Mushies (+10). So in a run every bottle is paid for with hunger you cannot refill there.
- **What it does to monsters and players.** Nothing directly. At +40% your walk (5.6) matches a monster's chase (5.4 to 5.7), which no other item gives you for this long.
- **Ammo.** Carry 5 at most. Lost on death in Going back in.
- **Downside.** The hunger, the wobble, and no way to stop a drink once it is down. Three is strong. Four is a countdown.
- **Where it works.** Everywhere except the Original (section 1.2).
- **In a room.** The server owns the drink timers, the speed limit it allows you, and the hunger, so a client cannot drink without paying.

---

## 7. Dealer items

Sold by the shady dealers in the hotel lobby. The effect, downside and duration of the five are the owner's (`docs/WORLD.md`, section 5, "use those") and are kept as written; they are marked **[OWNER]** below. Everything else is a proposal.

**Rules for all five** [PROPOSAL].

- **On-screen names.** The names on the models: Green Leaf, Trippy Paper, Munchy Mushies, Sugar Rush, Old Brew. The bible's words (green plant, paper tab, mushrooms, white powder, alcohol) are never shown.
- **Where you get them.** The lobby's dealers. The lobby is not built, so until it is, one dealer stands by the dry fountain in the mall (built: `world/entrance.json`) while the stores are open. Each dealer has 2 of each trip and 6 of each brew a game day.
- **Slot and controls.** Q / LB, in the support ring (the bible puts them on Q and E). A tap uses one; it takes 1 s.
- **Carry.** 2 of each trip, 5 of each brew (five Old Brews must be reachable, since the fifth is the owner's blackout).
- **One trip at a time.** Green Leaf, Trippy Paper, Munchy Mushies and Sugar Rush are trips. Taking one while another runs ends the first; if the first has a crash, the crash starts at once and runs under the new trip. Old Brew and Spicy Brew are drinks and stack on top of a trip.
- **Where they work.** Everywhere except the Original (section 1.2). In the City and hotel there is no HP and no weapon, so only the speed, hunger, noise and stalker parts apply.
- **Death.** Carried items are lost on death in Going back in. A running effect ends when you die.
- **Monsters and players.** They change you, not the monsters; each entry says where that is not true. In a room other players see an icon by your name and nothing else.
- **In a room.** The server owns every timer and the rule changes (speed limit, noise, damage taken, who ignores you). The client draws the filter.
- **Tone.** Fictional names, nothing shown being taken, no real-world instructions: a bottle or a packet in the hand and a change in the screen.

### 7.1 Green Leaf (model: `Green_Leaf_Pack`), $10

- **What it is.** A small green packet. Everything gets slow and soft, and for a while nothing in here minds you.
- **Effect [OWNER].** Slower, hungrier, all enemies become passive, a 64-bit waving filter. **Downside [OWNER]:** the slowness and the hunger. **Duration [OWNER]:** 5 minutes.
- **The numbers [PROPOSAL].** Every speed of yours is 0.75 of normal (walk 3.0, run 5.6 m/s). Hunger drains twice as fast. Monsters are Passive toward you: they do not chase or hit you, and walk their patrols as if you were not there.
- **What ends the calm.** Damage a monster and it, and every monster within 16 m of it, is hostile to you again for the rest of the trip.
- **Each kind.** All four monster kinds and the stalker go passive. Agents, The Registrar and the environmental threats do not: a camera still sees you and a crushing wall still crushes.
- **In a room.** Passive is toward you only. A monster that ignores you still chases your teammates, and a wave still has to be killed to be cleared.
- **Why it is not strictly best.** You cannot clear a wave with it, you are slow enough that the moment it ends is dangerous, and it is useless against the things that are not monsters.

### 7.2 Trippy Paper (model: `Psychedelic_Sticker_Pack`), $12

- **What it is.** A sheet of bright stickers. The world speeds up and comes loose, and then it sends the bill.
- **Effect [OWNER].** Fast, mushroom effects, plus the wave filter. **Downside [OWNER]:** a longer, harsher crash. **Duration [OWNER]:** 5 minutes, then a 2 minute crash.
- **The numbers [PROPOSAL].** For 5 minutes every speed of yours is 1.25 of normal (walk 5.0, run 9.4 m/s; a run still lasts 4 s). "Mushroom effects" means both halves of Munchy Mushies: you get its outlines (7.3), and you get its off-target throws and jumps.
- **The crash, 2 minutes.** Speed 0.7 of normal, no running at all, and your walking is heard as running.
- **Monsters and players.** Nothing directly. At 9.4 m/s you outrun every monster kind (5.4 to 5.7) by more than the built run does.
- **Why it is not strictly best.** Five good minutes buy two helpless ones, and you cannot choose when they start.

### 7.3 Munchy Mushies (model: `Munchy_Mushies`), $8

- **What it is.** A paper bag of small mushrooms. The world goes wavy and a bit kinder, and tells you things it normally keeps to itself.
- **Effect [OWNER].** A wavy, weirder world, in a good way. **Downside [OWNER]:** unreliable depth: jumps and throws land off target. **Duration [OWNER]:** 3 minutes.
- **The "good way" [PROPOSAL].** Monsters within 12 m show as a soft coloured outline through walls. Loot (packs, beacons, med kits, the locker) glows from 20 m. In the City, anything that is an anomaly shimmers. They are food too: +10 hunger when eaten.
- **The downside, in numbers [PROPOSAL].** Anything you throw, roll or launch (flash-vial, beacon, dart, rocket) leaves up to 15 degrees off your aim and lands up to 20% short or long. A gauntlet leap lands up to 2 m off. Hitscan weapons are not affected.
- **Monsters and players.** Nothing directly.
- **Why it is not strictly best.** The best scouting in the game, and the worst time to throw anything.

### 7.4 Sugar Rush (model: `Sugar_Rush_Ice_Pack`), $15

- **What it is.** A frosted packet of something white and sweet. One minute of being the fastest thing in the building.
- **Effect [OWNER].** Faster and stronger. **Downside [OWNER]:** a crash afterwards: slower, weaker, louder, as long as the boost. **Duration [OWNER]:** a 60 s boost, then a 60 s crash.
- **The boost [PROPOSAL].** Speed 1.3 of normal (walk 5.2, run 9.75 m/s) and the run does not drain. Stronger: melee weapons (baton, shear, gauntlet) do 1.5 times their damage, carrying an objective object does not make you easier to find, and you lift a downed teammate in 2 s instead of 4.
- **The crash [PROPOSAL].** Speed 0.75 of normal. Melee does half damage. Louder: your walking is heard as running and your crouching as walking.
- **Monsters and players.** Nothing directly.
- **Why it is not strictly best.** It is the dearest, the shortest, and the crash is exactly as long as the fun.

### 7.5 Old Brew (model: `Old_Brew_Bottle`), $5

- **What it is.** A brown bottle with a faded label. Each one makes the hits matter a little less and the floor a little less level.
- **Effect [OWNER].** A funny walk and run, wobble that grows with each drink, 5% less damage per bottle. **Downside [OWNER]:** a blackout at 5 drinks for 15 s, and it is impossible to aim stably. **Duration [OWNER]:** per drink.
- **The numbers [PROPOSAL].** A drink lasts 90 s. Each drink running on you means you take 5% less damage from a hit: 35 becomes 33.25, 31.5, 29.75 and 28 with one to four drinks. Each also adds a sway to your walk (your path drifts up to 0.25 m a drink to either side) and 1 degree of drift to your aim; the aim zoom on right click / LT does not hold steady at all.
- **The fifth.** Five Old Brew drinks running at once (Spicy Brew drinks do not count): the screen goes black for 15 s. You can still move and you can still be hit. Then every drink is cleared.
- **Reading the owner's line.** "5% less damage per bottle" is read as damage you take. If it meant damage you deal, say so (open question 9).
- **Monsters and players.** Nothing directly.
- **Why it is not strictly best.** A fifth of the damage off at four bottles, for $20 and an aim you cannot trust; one more and you are blind for 15 s.

---

## 8. Food

Built: `shared/needs.js`, `shared/needs.test.js`, `tools/grocery_test.mjs`, `tools/theft_test.mjs`.

| # | Model | Name in the code today | Price | Hunger | $ per 10 hunger |
|---|---|---|---|---|---|
| 19 | `Industrial_Apple_Slices` | Apples | $1 | +12 | 0.83 |
| 20 | `Industrial_Bread` | Bread | $2 | +25 | 0.80 |
| 21 | `Industrial_Soup_Can` | Canned soup | $3 | +35 | 0.86 |
| 22 | `Industrial_Ready_Meal` | Ready meal | $6 | +60 | 1.00 |

**The rules, as built.**

- **What it is.** Food with one brand on every packet, because there is only one brand.
- **Where you get it.** The grocery on Hallam Row, open 08:00 to 20:00. Take a cart at the entrance (8 items; 2 in your hands without one), pay at the checkout, and what you paid for goes to the fridge in your apartment.
- **Slot and controls.** No slot. The action button at a shelf, the checkout and the fridge.
- **What it does.** The fridge feeds you one item a press, the most filling one you have, and refuses at 95 hunger or more. Hunger runs 0 to 100, starts at 80, drains 100 in 36 game hours (half as fast asleep, never below 5 from sleep), warns at 30 and 10, and at 0 you faint and wake at home with 25.
- **Theft.** Walking out of the door with what you have not paid for: if the grocery's camera is turned away you keep it; if it is on you, you are fined $5 plus what it would have cost, never more than you have, and it goes back on the shelves. The camera sweeps 40 degrees each way every 12 s.
- **Ammo, death, monsters, players.** None of these apply. Food is not lost on a Going back in death because it is never carried there.
- **Downside.** Money and a walk to the shop before 20:00.
- **Where it works.** The City only.
- **In a room.** Each player's needs stay their own in version 1 (session 17's default), so the server would only need to own money, the cart and the pantry when the City gets shared saves.

**The on-screen names** [PROPOSAL]. Change them to match the labels on the models. A world with one brand called "Industrial" is exactly the liminal tone the bible asks for, and the player will see the label on the shelf anyway.

| id (unchanged) | Shelf, cart and receipt | Fridge line (short) |
|---|---|---|
| `apple` | Industrial Fruit Apple Slices | Apple slices |
| `bread` | Industrial Bread | Bread |
| `soup` | Industrial Soup | Soup |
| `meal` | Industrial Meal: Ready to Eat Meal | Ready meal |

Prices and hunger values do not change. The ids do not change, so saves keep working.

**What I would change otherwise.** Nothing in the numbers. One later idea, not for now: when Going back in gets its hunger pressure (`docs/WORLD.md`, "soft pressure"), let one food item be carried in the support ring as a packed lunch.

---

## 9. The ten weapons compared

| # | Weapon | Role | Range | Hits | Damage | Noise | Ammo | Price | Its risk |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Bolt driver | Cheap single-target burst | 18 m | one | 35 falling to 15 a nail | N1 | nails (bought) + air (free) | $25 | weak after three shots |
| 2 | Crossbow [BUILT] | Quiet one-shot kill | 25 m | one | kills | N1 | 6 bolts | $40 | 1.8 s a shot, six shots |
| 3 | Flamethrower | Close area control | 6 m cone | all in cone | 40 a second + burning | N3, and as running | propane, 10 s | $90 | close, loud, no cloak |
| 4 | Stun baton | Melee stun, free ammo | 1.8 m | one (4 m burst) | 25 + 4 s stun | N1 | 3 capacitors, self-charging | $45 | arm's length, cannot kill fast |
| 5 | Rocket launcher | Big area burst | 40 m, 5 m blast | all in blast | 150 falling to 50 | N5 | 3 rockets at $8 | $180 | calls the floor, hurts you, walk only |
| 6 | Laser dissector | Silent long range; the distraction dot | 30 m | one | 15 rising to 60 a second | N0 | battery, 12.5 s | $110 | stand still, one target, overheats |
| 7 | Rebar shear | Melee finisher; opens barricades | 2.0 m | one | 200 | N2 | fluid, 4 cuts | $70 | 1 s spool, timing |
| 8 | Frequency horn | Loud lure and shove | 10 m cone | all in cone | 0 | N5 / N4 | 6 blasts, free recharge at a locker | $55 | kills nothing, calls everything |
| 9 | Moth jelly dart | Silent damage over time | 30 m | one, spreads on death | 150 over 10 s | N0 | 5 darts at $3 | $60 | slow to kill, slow dart |
| 10 | Gravity gauntlet | Movement and shove | 2.0 m; 9 m leap | one | 30 (+30 into a wall) | N1 / N2 | 3 springs, self-winding | $50 + $100 | arm's length, weak damage |

**What it takes to kill each kind** (from full, no misses; the ray never kills).

| Weapon | pale_traveler (80) | creature (100) | clawed (100) | sinew (140) |
|---|---|---|---|---|
| Bolt driver | 3 nails | 4 nails | 4 nails | 5 nails |
| Crossbow | 1 bolt | 1 bolt | 1 bolt | 1 bolt |
| Flamethrower | 2.0 s (20% fuel) | 2.5 s (25%) | 2.5 s (25%) | 3.5 s (35%) |
| Stun baton | 4 hits | 4 hits | 4 hits | 6 hits |
| Rocket (within 2 m) | 1 | 1 | 1 | 1 |
| Laser | 1.8 s | 2.4 s | 2.4 s | 3.1 s |
| Rebar shear | 1 cut | 1 cut | 1 cut | 1 cut |
| Horn | never | never | never | never |
| Jelly dart | 1 dart, 5.3 s | 1 dart, 6.7 s | 1 dart, 6.7 s | 1 dart, 9.3 s |
| Gauntlet (open floor / into walls) | 3 / 2 punches | 4 / 2 | 4 / 2 | 5 / 3 |

**No weapon is strictly best.** The two that kill anything in one (crossbow, shear) are the slowest to use. The two that hit a crowd (flamethrower, rocket) are the loudest. The two that are silent (laser, jelly dart) take seconds to kill. The three with free ammo (baton, gauntlet, horn) barely kill at all. The cheapest (bolt driver) is good at exactly one monster.

**Pairs that are meant to work.** Horn call, then tripwire or rocket. Flash-vial or baton, then shear. Jelly dart, then walk away. Laser dot to turn a patrol, then crossbow from behind. Gauntlet leap to get out of what any of the loud ones brought.

### Which to build first

The crossbow exists. Next, in this order:

1. **Pneumatic bolt driver.** It is the ray's hitscan with a damage number, so it is the smallest step that forces the one big change everything else needs: monster health (section 1.4). It is also the $25 weapon, the first thing a player can buy, so the Market has a reason to exist.
2. **Stun-baton capacitor.** The stun already exists (`MonsterSim.stun`). It adds melee reach and self-charging ammo, and it gives a player who has just died and has no money something that works.
3. **Sound-amplified frequency horn.** The alert already exists (`MonsterSim.alert`, used by the tripwire). It adds knockback, the only new piece, and it makes the two built traps worth planning around. It shows the game's own idea best: you win by deciding where they look.
4. **Moth jelly dart.** It brings the status system (Slowed, damage over time) that the flamethrower and the rocket's mist then reuse, and it is the first projectile that is not hitscan, which the rocket reuses.

After those four the rest are mostly reuse: the flamethrower is a cone (horn) with a status (dart); the rocket is a projectile (dart) with a blast (tripwire); the laser is a held hitscan (driver) with a lure (horn); the shear is a melee hit (baton) with a door action; the gauntlet is a knockback (horn) plus the leap, which touches the player's movement and should go last.

The med kit is small and independent and can go in beside any of them.

---

## 10. Tuning tables

Every proposed number in one place. Built numbers are repeated with their file so the table is complete; change those in the code, not here.

### 10.1 Monsters [PROPOSAL]

| Kind | Health | Flash stun | Laser | Knockback | Burning | Baton stun |
|---|---|---|---|---|---|---|
| pale_traveler | 80 | x1.5 | x1.25 | x1 | x1 | x1 |
| creature | 100 | x1 | x1 | x1 | x1 | x1 |
| clawed | 100 | x1 | x1 | x0.5 | x1 | x1 |
| sinew | 140 | x1 | x1 | x1 | x0.5 time | x1.5 time |
| agent (placeholder) | 60 | x1 | x1 | x1 | x1 | x1 |

Statuses: Burning 10 a second, slow 0.6, 4 s. Jellied 15 a second, slow 0.5, 10 s (5 s when spread). Rocket mist slow 0.5, 6 s. Unkillable things: stun 1 s at most, knockback x0.5.

### 10.2 Weapons [PROPOSAL except the crossbow]

| Weapon | Range | Damage | Rate | Ammo: start / cap / pack / price | Other numbers |
|---|---|---|---|---|---|
| Bolt driver | 18 m | 15 + 20 x gauge | 0.35 s | nails 16 / 32 / +8 / $1 for 8 | gauge: 1/8 a shot, refills 1/8 per 1.5 s after 1 s idle |
| Crossbow [BUILT `shared/crossbow.js`] | 25 m | kills (proposed 150) | 1.8 s | bolts 4 / 6 / +2 / proposed $1 | noise 0.25 s |
| Flamethrower | 6 m, 40 degrees | 40 a second | held | propane 100% / tank + 1 spare / +25% / $4 | 10% a second; swap 2.5 s; self hit 35 |
| Stun baton | 1.8 m, 60 degrees | 25, stun 4 s | 0.6 s | capacitors 3 / 3 / none / free | recharge 8 s each; discharge 4 m, 15, stun 3 s, dead 20 s |
| Rocket launcher | 40 m at 25 m/s | 150 within 2 m to 50 at 5 m | 3.5 s | rockets 1 / 3 / none / $8 | arms at 5 m; self hit 35 within 5 m; mist 6 s; no running |
| Laser dissector | 30 m | 15 to 60 a second over 2 s | held | battery 100% + 1 spare / 2 spares / +25% / $5 | 8% a second; overheat after 5 s for 3 s; dot 0.5% a second, lures within 12 m; move at 2.2 m/s |
| Rebar shear | 2.0 m, 30 degrees | 200 | 1.0 s spool + 1.5 s | cuts 4 / 4 + 2 cartridges / +2 / $3 | hold ready 3 s; walk x0.8 |
| Frequency horn | 10 m, 60 degrees | 0 | 4 s | blasts 6 / 6 + 1 spare / none / $4, free at a locker | knockback 6 m, stun 2 s; call 25 m |
| Moth jelly dart | 30 m at 35 m/s | 15 a second for 10 s | 2.5 s | darts 3 / 5 / +1 / $3 | spreads within 4 m on death for 5 s |
| Gauntlet | 2.0 m | 30, +30 into a wall | 0.8 s | springs 3 / 3 / none / free | rewind 5 s each; knockback 5 m (8 m lit); stun 1 s; leap 9 m, 3 m high, 2 springs |

### 10.3 The existing three [BUILT]

| Item | Numbers | File |
|---|---|---|
| Ray | range 25 m, 0.6 s a shot, hit radius 0.6 m, noise 0.5 s, banish 15 m from players and 35 m by path, wait 4 s, immune 8 s, flicker 0.5 s; rounds 3 / 9 / +3 | `shared/monsters.js`, `shared/loot.js` |
| Cloak | 15 s on, 45 s recharge after 2 s, 10% to switch on, seen within 1.5 m; short circuit 8 m, 5 s stun, dead 300 s | `shared/cloak.js` |
| Beacon | roll 12 m, lure 30 m for 25 s, safe distance 4 m, ring 1.5 to 3 m; reverse 12 s then group 10 s; 2 a floor, carry 2 | `shared/beacon.js`, `shared/loot.js` |

Proposed prices: ray rounds $2 for 3, a beacon $6. ATL X: a hit removes the monster, no round count.

### 10.4 Consumables, med kit, Spicy Brew

| Item | Built numbers (`shared/consumables.js`) | Proposed |
|---|---|---|
| Flash-vial | throw 6 m, radius 6 m, stun 6 s; start 2, cap 3, +1 a pack | $5; noise N1; x1.5 on pale_traveler; teammates' screens white 1.5 s |
| Land mine | arm 1.5 s, trigger 1.2 m, kills 1; start 2, cap 3, +1 a pack | $6; 200 damage; can be picked up again |
| Tripwire | arm 0.5 s, trigger 2 m, kills within 3 m, heard 25 m; start 1, cap 2, +1 a pack | $10; 200 damage; snaps to a doorway within 2 m |
| Med kit | none | $12; use 2.5 s; +60 HP; refused at 95; cap 2; lift 1.5 s to 100 HP; 1 found per floor |
| Spicy Brew | none | $7; 90 s a drink; Old Brew's wobble; +8% speed a drink up to 5 (total speed cap x1.6); 8 hunger a real minute a drink, 16 with four or more running; no blackout; at 0 hunger the City's faint, or a death in Going back in (back at 25); cap 5 |

### 10.5 Dealer items

| Item | Price | Owner's duration | Proposed numbers |
|---|---|---|---|
| Green Leaf | $10 | 5 min | speed x0.75; hunger x2; passive breaks within 16 m of a monster you hurt |
| Trippy Paper | $12 | 5 min + 2 min crash | speed x1.25; Mushies' outlines and scatter; crash: speed x0.7, no run, walking heard as running |
| Munchy Mushies | $8 | 3 min | outlines 12 m, loot glow 20 m, +10 hunger; scatter 15 degrees and 20%, leap 2 m |
| Sugar Rush | $15 | 60 s + 60 s crash | speed x1.3, run does not drain, melee x1.5, lift 2 s; crash: speed x0.75, melee x0.5, noise one step louder |
| Old Brew | $5 | per drink | 90 s a drink; 5% less damage taken each; 0.25 m sway and 1 degree drift each; blackout at 5 for 15 s |

All: 1 s to use; one trip at a time. Carry 2 of each trip and 5 of each brew; a dealer stocks 2 of each trip and 6 of each brew a game day.

### 10.6 Food [BUILT `shared/needs.js`]

| id | Price | Hunger |
|---|---|---|
| apple | $1 | 12 |
| bread | $2 | 25 |
| soup | $3 | 35 |
| meal | $6 | 60 |

Start money $20. Cart 8, hands 2. Theft fine $5 plus the cart's price, capped at what you have.

### 10.7 Economy [PROPOSAL]

Going back in pays $1 a kill, $2 a revive, $5 a chamber, $10 more for a floor's last chamber. Carry limit: two arsenal weapons. Keycards $300 and $750. Perks $80 to $150.

---

## 11. What a build session needs

Rules for all of it: the pure rules go in `shared/` with a unit test that fails first; the page only draws and reads input; the three checks in `docs/SESSIONS.md` run before every push; `tools/controls_test.mjs` must pass unchanged, because nothing bound today moves. The held items and consumable slots are session 8's region of `index.html`; the server side is session 16's.

### 11.1 Groundwork (once, before the first new weapon)

| Piece | Files | Tests |
|---|---|---|
| Monster health and statuses | `shared/monsters.js` (`hp` on `MonsterSim`, `hurt`, `slow`, `burn`, `knock`; speeds read the slow), `world/monsters.json` (health and traits per kind), `shared/gbi.js` (`killed` when health reaches 0) | `shared/monsters.test.js`: a hit takes health, 0 is a kill, the Original's sims have no health and cannot die, a slow multiplies each speed, a knockback stops at a wall, the clawed moves half as far |
| The arsenal list and two-weapon carry | `shared/loadout.js` (`GEAR` grows; owned against carried; a cap of two arsenal weapons), new `shared/arsenal.js` (one table: id, name, ammo rule, pack amount) | `shared/loadout.test.js`: a third weapon is refused, death returns all of them; a test that every id in the arsenal table has a model name and a price |
| Prices and buying | new `shared/market.js` (the ladder of section 2 as data; `buy(state, id, n)`), `shared/needs.js` (money is already here) | `shared/market.test.js`: cannot buy without money, caps hold, a weapon is bought once |
| Keys and rings | `index.html` (key 5; held Q and E rings; the wheel up to 6) | `tools/controls_test.mjs` unchanged, plus a new `tools/arsenal_test.mjs`: key 5 holds weapon B, a tap on Q still throws a flash-vial, a hold opens the ring |
| Packs feed the arsenal | `index.html` (the pack pickup), `shared/arsenal.js` | a unit test of "what a pack gives a loadout" |
| The server | `server/playerstate.js` (owned weapons, ammo counts, cooldowns), `server/floorsim.js` (health, statuses, hits), `server/server.js` (the `fire`, `use` and `buy` intents) | `server/playerstate.test.js`, `server/floors.test.js`: a client cannot fire with no ammo, during a cooldown, or from far from where it stands |
| Models | `models/<id>.glb` for each, prepared as `docs/MODELS.md` says (1024 px WebP, Draco, under about 1 MB), `models/README.md`; the page must work without them, as it does for the fuse | none; the manifest check if a model is listed there |

### 11.2 Per item

| Item | Files that change | Tests it needs |
|---|---|---|
| Bolt driver | new `shared/driver.js`; `index.html` (held item, HUD gauge) | `shared/driver.test.js`: damage by gauge, the eight-shot sequence, the refill after 1 s idle, nails cap and pack; browser: four nails kill a creature |
| Crossbow (changes) | `shared/crossbow.js` (damage 150, a recoverable bolt), `index.html` (aim, the dropped bolt) | extend `shared/crossbow.test.js`; `tools/gbi2_test.mjs` still passes |
| Flamethrower | new `shared/flame.js`; `shared/monsters.js` (Burning); `shared/cloak.js` caller (firing switches it off) | cone membership, fuel drain, burning lasts 2 s on the sinew, a player in the cone takes one hit |
| Stun baton | new `shared/baton.js` | capacitors recharge one at a time, a hit needs one, the discharge needs three and locks for 20 s, the sinew is stunned 6 s |
| Rocket launcher | new `shared/rocket.js` (flight, arming distance, blast falloff, mist) | a dud inside 5 m, 150 at 2 m and 50 at 5 m, the shooter is hit inside 5 m, the alert reaches 40 m |
| Laser dissector | new `shared/laser.js` | the damage climb and its reset after 0.3 s, overheat at 5 s, battery drain, the dot lures a patrolling monster and not a chasing one |
| Rebar shear | new `shared/shear.js`; the chamber's barricades (GBI-5, not built) | spool then cut, the 3 s hold, a cut on air costs fluid, a barricade opens |
| Frequency horn | new `shared/horn.js`; `shared/monsters.js` (knockback) | cone membership, 6 m and 3 m knockbacks, the wall stop, the free recharge at a locker, the call's 25 m |
| Moth jelly dart | new `shared/dart.js`; `shared/monsters.js` (Jellied) | 150 over 10 s, a second dart restarts and does not stack, the spread on death, the kill is credited to the shooter |
| Gauntlet | new `shared/gauntlet.js`; the player's movement in `index.html` (session 12's region: say so in the PR) | charges rewind, the leap needs the lenses and two charges, the wall bonus, the landing spot is checked |
| Flash-vial, mine, tripwire (changes) | `shared/consumables.js` (damage numbers, pick a mine up, carry both traps), `index.html` | extend `shared/consumables.test.js`; `tools/gbi3_test.mjs` still passes |
| Med kit | `shared/consumables.js` (a fourth kind on the Q slot), `shared/health.js` (`heal`, a lift at full health), `server/playerstate.js` (the faster lift), `shared/loot.js` and the manifest (one found per floor) | heal by 60 and never above 100, refused at 95, cancelled if let go early, the lift takes 1.5 s and gives 100 HP and uses the kit |
| Spicy Brew, the five dealer items | new `shared/effects.js` (one state: the trip, the crash, the drinks, with timers and the multipliers the rest of the game reads), `shared/monsters.js` (Passive toward one player; noise one step louder), `shared/needs.js` (hunger x2; Spicy Brew's extra drain on real time, and the bar used outside the City), `index.html` (filters, wobble, the dealer in the mall), `shared/save.js` (carried items and running timers) | `shared/effects.test.js`: each duration and crash, one trip at a time, the fifth Old Brew blacks out and clears, Spicy Brew adds speed and hunger drain a drink and never blacks out, four at once double the drain, hunger 0 faints in the City and kills in a chamber, passive breaks on damage; a browser test buys one from the dealer and sees the speed change |
| Food names | `shared/needs.js` (`label` and a new short label), the tests that read the old names (`shared/needs.test.js` checks "Apples: 1"), `tools/grocery_test.mjs` | the fridge line and the receipt show the new names; prices and hunger values are unchanged |
| ATL X | `shared/monsters.js` (a deleting shot), `index.html` (the red gun), the `admin_access` flag | a deleting shot removes the monster and needs the flag |
| Docs | `docs/ROUND.md` (GBI-8 and its slice table), `docs/GAMEPLAY.md` (controls), `docs/WORLD.md` (section 10, item 6, is answered by this file) | the doc-against-code tests in `shared/*.test.js` |

---

## 12. Open questions for the owner

Each has the default this document uses. Change any of them and the entries above change with it.

1. **Do monsters get health in Going back in?** Default: yes (80, 100, 100, 140), with the crossbow and the traps still killing in one. Without it the ten weapons cannot differ.
2. **How many arsenal weapons can you carry?** Default: two (keys 4 and 5), the rest in the locker.
3. **Is the Original closed to everything bought?** Default: yes, only the ray, cloak and beacon, although the bible says dealer effects are "everywhere". The reason is Green Leaf: five minutes of passive monsters would end a floor's danger. Say if dealer items should work there too, or all of them except Green Leaf.
4. **Does the med kit belong in the Original?** Default: no. It would be the easiest help for B1, which the owner found hardest, so this is worth a second look after the playtest.
5. **The unlit gauntlet.** Default: the same item unpowered, sold at $50, with the violet lenses as a $100 upgrade that adds the leap.
6. **Who do explosions and fire hurt?** Default: the rocket's blast and the flamethrower's cone cost any player in them one hit of 35, the owner included. Everything else, the built traps included, hurts no player.
7. **Should the flash-vial burn, since it is called incendiary?** Default: no, it only stuns, as built.
8. **Should the tripwire's blast hurt a player standing in it?** Default: no, as built.
9. **Old Brew's "5% less damage per bottle".** Default: damage you take.
10. **Trippy Paper's "mushroom effects".** Default: both the good half (outlines) and the bad half (scatter) of Munchy Mushies.
11. **Green Leaf and the stalker.** Default: the stalker goes passive too; agents, the boss and the environment do not.
12. **Spicy Brew's numbers.** The rule is the owner's as relayed (Old Brew's wobble, faster, hungrier, no blackout, too much starves you). Defaults for the numbers: +8% speed and 8 hunger a minute a drink, four at once is "too much" and doubles the drain, and at 0 hunger you faint in the City (the built rule) and die in Going back in. Say if starving in the City should be a real death too.
13. **Where dealers stand before the hotel lobby exists.** Default: one dealer by the mall's fountain during opening hours.
14. **Can weapons leave Going back in and Secret Operations?** Default: no, they stay in the locker; the City has only the stalker, which nothing kills.
15. **The crossbow at the start** (already open in `docs/SESSIONS.md`). Default: it stays free in your hands until the Market exists, then costs $40.
16. **Food names.** Default: the shelf and receipt use the models' full "Industrial" names; the fridge uses short ones.
17. **Money from Going back in.** Default: $1 a kill, $2 a revive, $5 a chamber, $10 more for a floor. This is about $210 a full run, ten shifts' worth, so say if a run should pay less than a job.
18. **ATL X on players.** Default: nothing, unless the room's host switches admin rules on; then it sends the player to the Overworld.
19. **The name of the Going back in locker** (already open). This document says "the locker" throughout.
