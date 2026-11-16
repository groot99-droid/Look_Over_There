// The stun-baton capacitor (docs/ITEMS.md 4.4): melee crowd control with free ammo, the weapon that still works after you have lost everything. No graphics here.
// Three capacitors. A swing that HITS uses one, hurts the nearest monster in reach (SWING_DMG) and stuns it (SWING_STUN_S); a swing that misses costs nothing but the cooldown.
// A spent capacitor recharges in RECHARGE_S, one at a time. The discharge (all three) hurts and stuns every monster within BURST_R and leaves the baton dead for DEAD_S (it does not charge while dead).
// No ammo to buy and nothing is lost on a death. It does nothing to a player.
import {rayClear} from "./world.js";
export const CAPS = 3, RECHARGE_S = 8, COOL_S = 0.6, REACH_M = 1.8, ARC_DEG = 60, SWING_DMG = 25, SWING_STUN_S = 4;
export const BURST_R = 4, BURST_DMG = 15, BURST_STUN_S = 3, DEAD_S = 20;
export const HIT_NOISE_S = 0.25, BURST_NOISE_R = 15;                         // a hit counts as a puff (the crossbow's); the discharge sends monsters within BURST_NOISE_R to look
// a state is {caps (0..CAPS), charge (s towards the next capacitor), cool (s until the next swing), dead (s the baton stays dead)}
export const newBaton = () => ({caps: CAPS, charge: 0, cool: 0, dead: 0});
export function tick(b, dt) {
  let {caps, charge, cool, dead} = b; cool = Math.max(0, cool - dt);
  if (dead > 0) dead = Math.max(0, dead - dt);                               // dead: no charging until it wakes
  else if (caps < CAPS) { charge += dt; while (charge >= RECHARGE_S && caps < CAPS) { charge -= RECHARGE_S; caps++; } }
  if (caps >= CAPS) charge = 0;
  return {caps, charge, cool, dead};
}
// a swing: {ok: true, baton} (the cooldown starts; a capacitor is spent only if it `landed`), or {ok: false, why: "dead" | "cooling" | "empty"}
export function swing(b, landed) {
  if (b.dead > 0) return {ok: false, why: "dead"};
  if (b.cool > 0) return {ok: false, why: "cooling"};
  if (b.caps <= 0) return {ok: false, why: "empty"};
  return {ok: true, baton: {...b, caps: b.caps - (landed ? 1 : 0), cool: COOL_S}};
}
// the discharge: needs every capacitor. {ok: true, baton} (empty and dead for DEAD_S), or {ok: false, why: "dead" | "cooling" | "charging"}
export function discharge(b) {
  if (b.dead > 0) return {ok: false, why: "dead"};
  if (b.cool > 0) return {ok: false, why: "cooling"};
  if (b.caps < CAPS) return {ok: false, why: "charging"};
  return {ok: true, baton: {caps: 0, charge: 0, cool: COOL_S, dead: DEAD_S}};
}
// seconds a monster is stunned: electricity lasts longer on a wet one (world/monsters.json `batonStun`: the sinew 1.5, the others 1)
export const stunFor = (cfg, secs) => secs * ((cfg && cfg.batonStun) || 1);
// the monster a swing from eye o facing the unit vector f = [x, z] hits: the nearest on o's floor within REACH_M and ARC_DEG, with nothing solid between, or null
export function swingTarget(W, monsters, o, f) {
  let best = null, bd = 1e9;
  for (const m of monsters) {
    if (Math.abs(o[1] - 1.6 - m.fy) > 1.6) continue;
    const dx = m.pos.x - o[0], dz = m.pos.z - o[2], d = Math.hypot(dx, dz);
    if (d > REACH_M || d >= bd) continue;
    if (d > 0.5) { const ang = Math.acos(Math.max(-1, Math.min(1, (f[0] * dx + f[1] * dz) / d))) * 180 / Math.PI; if (ang > ARC_DEG / 2) continue; }
    const my = m.fy + 0.5 * ((m.cfg && m.cfg.height) || 2.2), dy = my - o[1], L = Math.hypot(d, dy) || 1;
    if (!rayClear(W, o, [dx / L, dy / L, dz / L], Math.max(0, L - 0.3))) continue;
    best = m; bd = d;
  }
  return best;
}
// every monster of the player's floor within BURST_R of (x, z) (y is the player's feet)
export const dischargeTargets = (monsters, x, y, z) => monsters.filter(m => Math.abs(y - m.fy) < 1.6 && Math.hypot(m.pos.x - x, m.pos.z - z) <= BURST_R);
