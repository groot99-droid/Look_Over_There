// The optical laser pointer dissector (docs/ITEMS.md 4.6): silent and long range, and the game's title as a mechanic: look over there. No graphics here.
// Beam (hold): a hitscan RANGE_M long. Damage climbs the longer it stays on one target: DPS_MIN a second at first, evenly up to DPS_MAX after RAMP_S. Leaving the target for more than LOSE_S (or meeting
// another monster) starts the climb again. The pale traveler takes 1.25 times (`laser` in world/monsters.json). After HEAT_S of beam it overheats and locks for LOCK_S (rest cools it at the rate it heated).
// Dot (hold): a dot where you point. A monster that is patrolling or searching, within DOT_R of the dot and with a clear line to it, goes to look. It does nothing to a chaser.
// Ammo: a battery pack is 100%. The beam uses DRAIN_PER_S a second, the dot DOT_DRAIN_PER_S. One pack loaded and one spare to start, MAX_SPARES at most; a flat pack swaps to a spare by itself in SWAP_S.
// An ammo pack pickup adds PACK_CHARGE to the loaded pack. A death takes the charge and the spares.
import {segClear} from "./world.js";
export const RANGE_M = 30, DPS_MIN = 15, DPS_MAX = 60, RAMP_S = 2, LOSE_S = 0.3, HEAT_S = 5, LOCK_S = 3;
export const DRAIN_PER_S = 0.08, DOT_DRAIN_PER_S = 0.005, SWAP_S = 2, MAX_SPARES = 2, PACK_CHARGE = 0.25, DOT_R = 12;
const cap = v => Math.max(0, Math.min(1, v));
// a state is {charge 0..1, spares, swapT, heat (s of beam not yet cooled), lock (s left overheated), target (the monster the climb is on), onT (s of climb), offT (s since the beam left it)}
export const newLaser = () => ({charge: 1, spares: 1, swapT: 0, heat: 0, lock: 0, target: null, onT: 0, offT: 0});
export const dps = onT => DPS_MIN + (DPS_MAX - DPS_MIN) * Math.min(1, Math.max(0, onT) / RAMP_S);
export const dmgMul = cfg => (cfg && cfg.laser) || 1;
const flat = l => l.charge <= 0 && l.spares > 0 && l.swapT <= 0 ? {...l, swapT: SWAP_S} : l;          // a flat pack with a spare: the swap starts by itself
const blocked = l => l.swapT > 0 ? "swapping" : l.lock > 0 ? "overheated" : l.charge <= 0 ? "empty" : null;
function lose(l, dt) { const offT = l.offT + dt; return offT > LOSE_S ? {...l, target: null, onT: 0, offT} : {...l, offT}; }
// time passing without the beam: the swap and the lock run down, the heat cools, the climb is lost after LOSE_S
export function idle(l, dt) {
  let {swapT, charge, spares, lock, heat} = l;
  if (swapT > 0) { swapT = Math.max(0, swapT - dt); if (swapT === 0) { charge = 1; spares = Math.max(0, spares - 1); } }
  return lose({...l, swapT, charge, spares, lock: Math.max(0, lock - dt), heat: Math.max(0, heat - dt)}, dt);
}
// the beam held for dt on `target` (the monster it reaches, or null): {ok: true, laser, dmg} (dmg before the monster's own multiplier), or {ok: false, why: "swapping" | "overheated" | "empty"}
export function beam(l, dt, target) {
  const why = blocked(l); if (why) return {ok: false, why};
  let n = {...l, charge: cap(l.charge - DRAIN_PER_S * dt), heat: l.heat + dt}, dmg = 0;
  if (!target) n = lose(n, dt);
  else { const onT = target === l.target ? l.onT : 0; dmg = (dps(onT) + dps(onT + dt)) / 2 * dt; n = {...n, target, onT: onT + dt, offT: 0}; }
  if (n.heat >= HEAT_S) n = {...n, heat: 0, lock: LOCK_S};
  return {ok: true, dmg, laser: flat(n)};
}
// the dot held for dt: {ok: true, laser}, or {ok: false, why}. It makes no heat.
export function dot(l, dt) { const why = blocked(l); return why ? {ok: false, why} : {ok: true, laser: flat(lose({...l, charge: cap(l.charge - DOT_DRAIN_PER_S * dt)}, dt))}; }
export const addCharge = (l, n) => ({...l, charge: cap(l.charge + n)});
export const addSpare = l => ({...l, spares: Math.min(MAX_SPARES, l.spares + 1)});
export const lost = () => ({...newLaser(), charge: 0, spares: 0});
// the monsters the dot at p = [x, y, z] draws: patrolling or searching, on its floor, within DOT_R, with a clear line from their eyes to it
export const dotHears = (W, monsters, p) => monsters.filter(m => (m.state === "patrol" || m.state === "search") && Math.abs(p[1] - m.fy) < 3 && Math.hypot(m.pos.x - p[0], m.pos.z - p[2]) <= DOT_R &&
  segClear(W, m.pos.x, m.fy + 1.6, m.pos.z, p[0], Math.max(p[1], m.fy + 0.3), p[2], 0.3));
