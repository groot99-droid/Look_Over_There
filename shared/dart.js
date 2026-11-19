// The moth jelly dart (docs/ITEMS.md 4.9): silent damage over time. Fire and leave. No graphics here.
// A dart is a slow projectile (SPEED m/s, RANGE_M m), not a hitscan: a moving monster has to be led. The monster it hits is Jellied for JELLY_S seconds: it takes JELLY_DPS a second
// (150 in all, enough for any of the four kinds) and is slowed to JELLY_SLOW. A second dart on the same monster only restarts the time; it does not stack. When a jellied monster dies,
// every monster within SPREAD_R of it is jellied for SPREAD_S (the status lives on the monster: MonsterSim.jelly / statusTick in shared/monsters.js). Reload RELOAD_S. Silent.
// Ammo: darts (bought), START_DARTS to begin, at most MAX_DARTS, PACK_DARTS from each ammo pack you pick up while you carry it. Lost on a death.
import {newFlight, stepFlight as flightStep} from "./flight.js";
export const START_DARTS = 3, MAX_DARTS = 5, PACK_DARTS = 1, RELOAD_S = 2.5, SPEED = 35, RANGE_M = 30;
export const JELLY_S = 10, JELLY_DPS = 15, JELLY_SLOW = 0.5, SPREAD_R = 4, SPREAD_S = 5;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const newDart = (darts = 0) => ({darts: clamp(Math.floor(darts) || 0, 0, MAX_DARTS), cool: 0});
export const addDarts = (d, n) => ({...d, darts: clamp(d.darts + n, 0, MAX_DARTS)});
export const tick = (d, dt) => d.cool > 0 ? {...d, cool: Math.max(0, d.cool - dt)} : d;
// a shot: {ok: true, dart} (one dart used, reloading), or {ok: false, why: "reloading" | "empty"}
export function shoot(d) {
  if (d.cool > 0) return {ok: false, why: "reloading"};
  if (d.darts <= 0) return {ok: false, why: "empty"};
  return {ok: true, dart: {darts: d.darts - 1, cool: RELOAD_S}};
}
export const lost = () => newDart(0);
// a dart in the air (shared/flight.js): SPEED m/s for RANGE_M m
export {newFlight};
export const stepFlight = (W, monsters, f, dt) => flightStep(W, monsters, f, dt, SPEED, RANGE_M);
// the monsters a dying jellied one infects: the others within SPREAD_R of it on its floor
export const spreadTargets = (monsters, dead) => monsters.filter(m => m !== dead && Math.abs(m.fy - dead.fy) < 1.6 && Math.hypot(m.pos.x - dead.pos.x, m.pos.z - dead.pos.z) <= SPREAD_R);
