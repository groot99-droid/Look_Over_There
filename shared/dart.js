// The moth jelly dart (docs/ITEMS.md 4.9): silent damage over time. Fire and leave. No graphics here.
// A dart is a slow projectile (SPEED m/s, RANGE_M m), not a hitscan: a moving monster has to be led. The monster it hits is Jellied for JELLY_S seconds: it takes JELLY_DPS a second
// (150 in all, enough for any of the four kinds) and is slowed to JELLY_SLOW. A second dart on the same monster only restarts the time; it does not stack. When a jellied monster dies,
// every monster within SPREAD_R of it is jellied for SPREAD_S (the status lives on the monster: MonsterSim.jelly / statusTick in shared/monsters.js). Reload RELOAD_S. Silent.
// Ammo: darts (bought), START_DARTS to begin, at most MAX_DARTS, PACK_DARTS from each ammo pack you pick up while you carry it. Lost on a death.
import {rayMonster} from "./monsters.js";
import {rayClear} from "./world.js";
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
// a dart in the air: from eye o along the unit vector d
export const newFlight = (o, d) => ({x: o[0], y: o[1], z: o[2], dx: d[0], dy: d[1], dz: d[2], flown: 0});
// advance a flight by dt: {f, hit, gone}. It hits the first monster its path reaches (the ray's 0.6 m hit radius), is stopped by a wall or a shut door, and ends at RANGE_M.
export function stepFlight(W, monsters, f, dt) {
  const L = Math.min(SPEED * dt, RANGE_M - f.flown), o = [f.x, f.y, f.z], d = [f.dx, f.dy, f.dz];
  // rayMonster ignores anything closer than 0.3 m along the ray, so look from 0.3 m behind the dart: a monster right at the dart's nose still counts
  const hit = rayMonster(W, monsters, [o[0] - d[0] * 0.3, o[1] - d[1] * 0.3, o[2] - d[2] * 0.3], d), t = hit ? hit.t - 0.3 : 0;
  if (hit && t <= L) return {f: {...f, x: o[0] + d[0] * t, y: o[1] + d[1] * t, z: o[2] + d[2] * t, flown: f.flown + t}, hit: hit.m, gone: true};
  if (!rayClear(W, o, d, L)) return {f, hit: null, gone: true};
  const g = {...f, x: o[0] + d[0] * L, y: o[1] + d[1] * L, z: o[2] + d[2] * L, flown: f.flown + L};
  return {f: g, hit: null, gone: g.flown >= RANGE_M - 1e-6};
}
// the monsters a dying jellied one infects: the others within SPREAD_R of it on its floor
export const spreadTargets = (monsters, dead) => monsters.filter(m => m !== dead && Math.abs(m.fy - dead.fy) < 1.6 && Math.hypot(m.pos.x - dead.pos.x, m.pos.z - dead.pos.z) <= SPREAD_R);
