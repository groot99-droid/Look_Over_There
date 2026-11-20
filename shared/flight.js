// A projectile in the air (the moth jelly dart, the rocket): no graphics here. From eye o along the unit vector d, at `speed` m/s for `range` m.
// It hits the first monster its path reaches (the ray's 0.6 m hit radius), is stopped by a wall or a shut door, and ends at the end of its range.
import {rayMonster} from "./monsters.js";
import {rayClear} from "./world.js";
export const newFlight = (o, d) => ({x: o[0], y: o[1], z: o[2], dx: d[0], dy: d[1], dz: d[2], flown: 0});
// advance a flight by dt: {f, hit, gone}. `f.flown` is how far it has gone (a rocket arms by distance).
export function stepFlight(W, monsters, f, dt, speed, range) {
  const L = Math.min(speed * dt, range - f.flown), o = [f.x, f.y, f.z], d = [f.dx, f.dy, f.dz];
  // rayMonster ignores anything closer than 0.3 m along the ray, so look from 0.3 m behind the projectile: a monster right at its nose still counts
  const hit = rayMonster(W, monsters, [o[0] - d[0] * 0.3, o[1] - d[1] * 0.3, o[2] - d[2] * 0.3], d), t = hit ? hit.t - 0.3 : 0;
  if (hit && t <= L) return {f: {...f, x: o[0] + d[0] * t, y: o[1] + d[1] * t, z: o[2] + d[2] * t, flown: f.flown + t}, hit: hit.m, gone: true};
  if (!rayClear(W, o, d, L)) return {f, hit: null, gone: true};
  const g = {...f, x: o[0] + d[0] * L, y: o[1] + d[1] * L, z: o[2] + d[2] * L, flown: f.flown + L};
  return {f: g, hit: null, gone: g.flown >= range - 1e-6};
}
