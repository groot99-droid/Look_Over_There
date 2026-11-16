// The pneumatic bolt driver (docs/ITEMS.md, 4.1): the cheap workhorse of Going back in. No graphics here. Its own ammo rule, two things:
//   nails: bought, one per shot, START_NAILS to begin, at most MAX_NAILS, PACK_NAILS from each ammo pack you pick up while you carry it. Lost on a death.
//   air: free. The gauge holds GAUGE eighths; a shot uses one and does less damage the lower the gauge is (35 at full, down to 15 at empty).
//        After REFILL_DELAY_S without firing it refills one eighth every REFILL_S (REFILL_S x GAUGE = 12 s from empty, plus the 1 s wait).
// A hit hurts a monster (it has health in this mode: world/monsters.json `hp`, MonsterSim.hurt); it does not kill outright like a crossbow bolt. It does nothing to a player.
import {rayMonster} from "./monsters.js";
export const MAX_NAILS = 32, START_NAILS = 16, PACK_NAILS = 8;
export const GAUGE = 8, DMG_MAX = 35, DMG_MIN = 15, RANGE_M = 18, COOL_S = 0.35, REFILL_DELAY_S = 1.0, REFILL_S = 1.5, SHOT_NOISE_S = 0.25;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
// a state is {nails, air (eighths, 0..GAUGE), cool (s until the next shot), idle (s since the last shot), fill (s towards the next eighth)}
export const newDriver = (nails = 0) => ({nails: clamp(Math.floor(nails) || 0, 0, MAX_NAILS), air: GAUGE, cool: 0, idle: REFILL_DELAY_S, fill: 0});
export const addNails = (d, n) => ({...d, nails: clamp(d.nails + n, 0, MAX_NAILS)});
// damage of the next shot: 15 + 20 x (air / 8), so a full gauge is 35 and each eighth spent is 2.5 less (the eighth is spent after the damage is read)
export const damage = d => DMG_MIN + (DMG_MAX - DMG_MIN) * (d.air / GAUGE);
export function tick(d, dt) {
  let {cool, idle, fill, air} = d; cool = Math.max(0, cool - dt); idle += dt;
  if (idle >= REFILL_DELAY_S && air < GAUGE) { fill += Math.min(dt, idle - REFILL_DELAY_S);      // only the time past the wait counts
    while (fill >= REFILL_S && air < GAUGE) { fill -= REFILL_S; air++; } }
  if (air >= GAUGE) fill = 0;
  return {...d, cool, idle, fill, air};
}
// a shot: {ok: true, driver, dmg} (one nail and an eighth of air used), or {ok: false, why: "cooling" | "empty"}. With the gauge empty it still fires, at DMG_MIN.
export function shoot(d) {
  if (d.cool > 0) return {ok: false, why: "cooling"};
  if (d.nails <= 0) return {ok: false, why: "empty"};
  return {ok: true, dmg: damage(d), driver: {nails: d.nails - 1, air: Math.max(0, d.air - 1), cool: COOL_S, idle: 0, fill: 0}};
}
// the monster a nail from o along d (unit) hits: the nearest on o's floor within RANGE_M that the ray reaches (a wall or a shut door stops it), as {m, t}, or null
export function nailHit(W, monsters, o, d) { const hit = rayMonster(W, monsters, o, d); return hit && hit.t <= RANGE_M ? hit : null; }
// after a death: the nails are gone, the air is full again (the locker gives the gun back, docs/WORLD.md "Death in Going back in")
export const lost = () => newDriver(0);
