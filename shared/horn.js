// The sound-amplified frequency horn (docs/ITEMS.md 4.8): the loud lure and the shove. It hurts nothing. No graphics here.
// Blast: a cone BLAST_RANGE_M long and BLAST_ARC_DEG wide; every monster in it is knocked KNOCK_M straight away from you (the clawed half as far: `knockback` in world/monsters.json), stopping before a wall,
// and stunned STUN_S. It is as loud as it gets: every monster within BLAST_NOISE_R comes to look. Call: one low tone, free: every monster within CALL_R comes to look at where you stood.
// Each has its own COOL_S cooldown. Ammo: a car battery of BLASTS blasts; a locker recharges it for free; one spare battery may be carried (the Market sells it) and swaps in by itself in SWAP_S when the battery is flat.
// A death flattens the battery and takes the spare.
import {inCone} from "./cone.js";
import {cellOf, rayClear} from "./world.js";
export const BLASTS = 6, BLAST_RANGE_M = 10, BLAST_ARC_DEG = 60, KNOCK_M = 6, STUN_S = 2, COOL_S = 4, CALL_R = 25, BLAST_NOISE_R = 40, SWAP_S = 3, SPARE_MAX = 1;
// a state is {charge (blasts left), spare (batteries carried), swapT (s left swapping), coolB, coolC (s until the next blast / call)}
export const newHorn = () => ({charge: BLASTS, spare: 0, swapT: 0, coolB: 0, coolC: 0});
export function tick(h, dt) {
  let {charge, spare, swapT, coolB, coolC} = h; coolB = Math.max(0, coolB - dt); coolC = Math.max(0, coolC - dt);
  if (swapT > 0) { swapT = Math.max(0, swapT - dt); if (swapT === 0) { charge = BLASTS; spare = Math.max(0, spare - 1); } }
  else if (charge <= 0 && spare > 0) swapT = SWAP_S;                          // a flat battery with a spare: it swaps by itself
  return {charge, spare, swapT, coolB, coolC};
}
// a blast: {ok: true, horn}, or {ok: false, why: "swapping" | "cooling" | "empty"}
export function blast(h) {
  if (h.swapT > 0) return {ok: false, why: "swapping"};
  if (h.coolB > 0) return {ok: false, why: "cooling"};
  if (h.charge <= 0) return {ok: false, why: "empty"};
  return {ok: true, horn: {...h, charge: h.charge - 1, coolB: COOL_S}};
}
// the call uses no charge: {ok: true, horn}, or {ok: false, why: "cooling"}
export function call(h) { return h.coolC > 0 ? {ok: false, why: "cooling"} : {ok: true, horn: {...h, coolC: COOL_S}}; }
export const recharge = h => ({...h, charge: BLASTS, swapT: 0});                // at a locker: free
export const addSpare = h => ({...h, spare: Math.min(SPARE_MAX, h.spare + 1)});
export const lost = () => ({charge: 0, spare: 0, swapT: 0, coolB: 0, coolC: 0});
export const blastTargets = (W, monsters, o, f) => inCone(W, monsters, o, f, BLAST_RANGE_M, BLAST_ARC_DEG);
// how far a monster of this kind is thrown (the clawed grip the floor: world/monsters.json `knockback` 0.5)
export const knockDist = cfg => KNOCK_M * ((cfg && cfg.knockback) ?? 1);
// where a monster ends up when thrown dist metres straight away from the horn at (from[0], from[1]): quarter-metre steps, stopping 0.5 m before anything solid and at the edge of the walkable floor
export function knockEnd(W, m, from, dist) {
  let x = m.pos.x, z = m.pos.z; const dx = x - from[0], dz = z - from[1], d = Math.hypot(dx, dz) || 1, ux = dx / d, uz = dz / d, y = m.fy + 1.0;
  for (let t = 0; t + 1e-9 < dist; t += 0.25) {
    const step = Math.min(0.25, dist - t), nx = x + ux * step, nz = z + uz * step;
    if (W.nav) { const c = cellOf(nx, nz); if (c < 0 || !W.nav[c]) break; }
    if (!rayClear(W, [x - ux * 0.3, y, z - uz * 0.3], [ux, 0, uz], 0.3 + step + 0.5 + 0.01)) break;
    x = nx; z = nz;
  }
  return [x, z];
}
// the monsters within r of (x, z) on the player's floor: who hears a call or a blast
export const within = (monsters, x, y, z, r) => monsters.filter(m => Math.abs(y - m.fy) < 1.6 && Math.hypot(m.pos.x - x, m.pos.z - z) <= r);
