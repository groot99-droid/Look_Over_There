// What the server knows about each player that a client must not decide for itself: health, ammunition, cloak battery, beacons, and the down/respawn timers.
// Pure functions over a state object and a clock (seconds); the rules themselves are in shared/health.js, cloak.js, loot.js and monsters.js.
import {newHealth, hurt, regen, revived, downed} from "../shared/health.js";
import {newCloak, toggle as cloakToggle, tick as cloakTick, shortCircuit as cloakShort, broken as cloakBroken} from "../shared/cloak.js";
import {GUN_ROUNDS, MAX_ROUNDS, MAX_BEACONS, roundsAfterPack} from "../shared/loot.js";
import {SHOT_COOL} from "../shared/monsters.js";
import {newBow, addBolts, tick as bowTick, shoot as bowShoot, START_BOLTS, PACK_BOLTS, RELOAD_S} from "../shared/crossbow.js";
import {newKit, setE, slotKind, useSlot, addPack as kitPack, lost as kitLost} from "../shared/consumables.js";
import {newLoadout, carries, take as gearTake, leave as gearLeave, died as gearDied, GEAR} from "../shared/loadout.js";

export const DOWNED_S = 20, IMMUNE_S = 4, REVIVE_R = 2.5, THROW_GAP_S = 1;
// what a round is scored on, counted here because only the server can be trusted with it (RND-20). `floorMs` is time spent on each scene.
export const newStats = () => ({downs: 0, deaths: 0, revives: 0, shots: 0, hits: 0, beacons: 0, floorMs: {}});
export const newPS = () => ({stats: newStats(), hp: newHealth(), gun: false, rounds: 0, beacons: 0, cloak: null, downAt: 0, immUntil: 0, shotAt: -99, throwAt: -99, sent: ""});
// ---- Going back in (session 16). `ps.gbi` exists only in a room of that mode: {load: the loadout (shared/loadout.js), bow: the crossbow (shared/crossbow.js),
// kit: the Q and E consumables (shared/consumables.js)}.
// You start carrying all your gear, with the ray's rounds and the crossbow's bolts, as the solo mode does (there is no Market yet).
export const newGbiPS = () => { const ps = newPS(); gotLocker(ps); ps.gbi = {load: newLoadout(), bow: newBow(START_BOLTS), kit: newKit()}; return ps; };
// what you hold follows the loadout: the ray and the cloak are the same flags the Original uses (ammunition is not part of it; a cloak taken back is a fresh one, as alone)
function syncGear(ps) {
  ps.gun = carries(ps.gbi.load, "gun");
  if (!carries(ps.gbi.load, "cloak")) ps.cloak = null; else if (!ps.cloak) ps.cloak = newCloak();
}
// at the locker: take a piece of gear ("take") or leave it there ("leave"). False when nothing changed (down, not in the mode, not a piece of gear, already so).
export function gbiGear(ps, a, g) {
  if (!ps.gbi || isDown(ps) || !GEAR.includes(g) || (a !== "take" && a !== "leave")) return false;
  const next = a === "take" ? gearTake(ps.gbi.load, g) : gearLeave(ps.gbi.load, g); if (next === ps.gbi.load) return false;
  ps.gbi.load = next; syncGear(ps); return true;
}
// at the locker: what the E slot holds, a land mine or a tripwire (the counts stay). False when nothing changed.
export function gbiSetE(ps, kind) {
  if (!ps.gbi || isDown(ps)) return false;
  const next = setE(ps.gbi.kit, kind); if (next === ps.gbi.kit || next.e === ps.gbi.kit.e) return false;
  ps.gbi.kit = next; return true;
}
// what pressing Q (slot 0) or E (slot 1) would use: "flash" | "mine" | "wire", or null (not in the mode, down, no such slot, none left)
export const gbiSlot = (ps, slot) => { if (!ps.gbi || isDown(ps)) return null; const k = slotKind(ps.gbi.kit, slot); return k && ps.gbi.kit.n[k] > 0 ? k : null; };
// one of it is used: the kind, or null
export function gbiUse(ps, slot) {
  if (!gbiSlot(ps, slot)) return null;
  const r = useSlot(ps.gbi.kit, slot); if (!r.ok) return null;
  ps.gbi.kit = r.kit; return r.kind;
}
// a bolt: one from the bow, only with the crossbow in hand and reloaded (a little slack for the network, as the ray has)
export function shootBow(ps) {
  if (!ps.gbi || isDown(ps) || !carries(ps.gbi.load, "crossbow") || ps.gbi.bow.cool > RELOAD_S * 0.15) return false;
  const r = bowShoot({...ps.gbi.bow, cool: 0}); if (!r.ok) return false;
  ps.gbi.bow = r.bow; ps.stats.shots++; return true;
}
// a death in Going back in (docs/WORLD.md): the gear is in the locker, free to take back; the ammunition (rounds, bolts, beacons) and the consumables are not returned.
// Called when the down time ran out with nobody lifting them.
export function gbiDied(ps) {
  ps.rounds = 0; ps.beacons = 0; if (!ps.gbi) return;
  ps.gbi.load = gearDied(ps.gbi.load); ps.gbi.bow = newBow(0); ps.gbi.kit = kitLost(ps.gbi.kit); syncGear(ps);
}
export const isDown = ps => downed(ps.hp);
export const isImmune = (ps, now) => now < ps.immUntil;
export const cloakOn = ps => !!(ps.cloak && ps.cloak.on);

// a monster touched them: false when they are down, immune, or still in the grace second after another hit; true when it landed (and they may now be down)
export function hit(ps, dmg, now) {
  if (isDown(ps) || isImmune(ps, now)) return false;
  const n = hurt(ps.hp, dmg, now); if (!n) return false;
  ps.hp = n; if (downed(n)) { ps.stats.downs++; ps.downAt = now; ps.cloak = ps.cloak ? {...ps.cloak, on: false} : null; }
  return true;
}
// time passing: regeneration, the cloak's battery, and the end of the down timer (a fresh start with a few seconds of safety; a down nobody lifted in time counts as a death). Returns "respawn" when they get up on their own.
export function tick(ps, dt, now) {
  if (isDown(ps)) { if (now - ps.downAt >= DOWNED_S) { ps.stats.deaths++; ps.hp = newHealth(); ps.immUntil = now + IMMUNE_S; return "respawn"; } return null; }
  ps.hp = regen(ps.hp, now, dt);
  if (ps.cloak) ps.cloak = cloakTick(ps.cloak, dt);
  if (ps.gbi) ps.gbi.bow = bowTick(ps.gbi.bow, dt);
  return null;
}
// a teammate lifts them (the caller has checked who and where): 50 HP, safe for a moment
export function lift(ps, now) { if (!isDown(ps)) return false; ps.hp = revived(now); ps.immUntil = now + IMMUNE_S; return true; }
// a locker opened: the gun with its rounds, and a cloak
export function gotLocker(ps) { ps.gun = true; ps.rounds = GUN_ROUNDS; ps.cloak = newCloak(); }
// the one who lifted a teammate is credited with a revive (the caller has just seen lift() succeed)
export const gaveRevive = ps => { ps.stats.revives++; };
// a shot that banished a monster
export const shotHit = ps => { ps.stats.hits++; };
// time on a floor, in ms; the caller says which scene the player is on (null: none)
export function onFloor(ps, scene, dt) { if (scene) ps.stats.floorMs[scene] = (ps.stats.floorMs[scene] || 0) + dt * 1000; }
// a copy that will not change when the player does (taken as they leave the store)
export const statsOf = ps => ({...ps.stats, floorMs: {...ps.stats.floorMs}});
export const canTakePack = ps => ps.rounds < MAX_ROUNDS;
export function gotPack(ps) { ps.rounds = roundsAfterPack(ps.rounds); if (!ps.gbi) return; ps.gbi.kit = kitPack(ps.gbi.kit); if (carries(ps.gbi.load, "crossbow")) ps.gbi.bow = addBolts(ps.gbi.bow, PACK_BOLTS); }          // Going back in: a pack also holds one flash-vial, one of what E holds, and bolts for a crossbow you carry
export const canTakeBeacon = ps => ps.beacons < MAX_BEACONS;
export function gotBeacon(ps) { ps.beacons = Math.min(MAX_BEACONS, ps.beacons + 1); }
// a shot costs a round and may not come faster than the gun allows (a little slack for the network)
export function shoot(ps, now) {
  if (isDown(ps) || !ps.gun || ps.rounds <= 0 || now - ps.shotAt < SHOT_COOL * 0.85) return false;
  ps.rounds--; ps.shotAt = now; ps.stats.shots++; return true;
}
export function throwBeacon(ps, now) {
  if (isDown(ps) || ps.beacons <= 0 || now - ps.throwAt < THROW_GAP_S) return false;
  ps.beacons--; ps.throwAt = now; ps.stats.beacons++; return true;
}
export function toggleCloak(ps) {
  if (isDown(ps) || !ps.cloak) return false;
  const n = cloakToggle(ps.cloak); if (n === ps.cloak) return false; ps.cloak = n; return true;
}
// what the player is told about themselves
// the cloak's secondary ability: short-circuit it (the caller stuns the monsters round the player). False if they cannot (down, no cloak, already broken).
export function shortCircuit(ps) {
  if (isDown(ps) || !ps.cloak || cloakBroken(ps.cloak)) return false;
  ps.cloak = cloakShort(ps.cloak); return true;
}
export const view = ps => ({hp: Math.round(ps.hp.hp), gun: ps.gun, rounds: ps.rounds, beacons: ps.beacons, cloak: ps.cloak ? {on: ps.cloak.on, b: +ps.cloak.b.toFixed(1), x: Math.ceil(ps.cloak.broken || 0)} : null,
  ...(ps.gbi ? {carry: ps.gbi.load.carry, bolts: ps.gbi.bow.bolts, kit: ps.gbi.kit} : {})});          // Going back in only: what you carry, the crossbow's bolts, and the Q and E consumables
// true when what the player is told has changed since the last time (and remembers it)
export function changed(ps) { const s = JSON.stringify(view(ps)); if (s === ps.sent) return false; ps.sent = s; return true; }
