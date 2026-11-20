// The almond water aerosol rocket launcher (docs/ITEMS.md 4.5): the big area burst. Very loud, very few shots. No graphics here.
// A rocket flies SPEED m/s for RANGE_M m and bursts on the first monster or wall it meets (or at the end of its range). One that bursts within ARM_M of where it was fired has not armed: it drops, does nothing and is lost.
// The blast hurts everything within BLAST_R: DMG_MAX within FULL_R, falling evenly to DMG_MIN at BLAST_R. Then a mist MIST_R out stays for MIST_S: monsters in it are slowed to MIST_SLOW.
// The burst is heard NOISE_R away. It hurts you too inside BLAST_R (the page: one monster hit). Reload RELOAD_S; you cannot run with it in your hands.
// Ammo: rockets (bought), START_ROCKETS to begin, at most MAX_ROCKETS, never from a pack. Lost on a death.
import {newFlight, stepFlight as flightStep} from "./flight.js";
export const START_ROCKETS = 1, MAX_ROCKETS = 3, RELOAD_S = 3.5, SPEED = 25, RANGE_M = 40, ARM_M = 5;
export const BLAST_R = 5, FULL_R = 2, DMG_MAX = 150, DMG_MIN = 50, MIST_R = 2.5, MIST_S = 6, MIST_SLOW = 0.5, NOISE_R = 40;
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
export const newRocket = (rockets = 0) => ({rockets: clamp(Math.floor(rockets) || 0, 0, MAX_ROCKETS), cool: 0});
export const addRockets = (r, n) => ({...r, rockets: clamp(r.rockets + n, 0, MAX_ROCKETS)});
export const tick = (r, dt) => r.cool > 0 ? {...r, cool: Math.max(0, r.cool - dt)} : r;
// a shot: {ok: true, rocket} (one used, reloading), or {ok: false, why: "reloading" | "empty"}
export function fire(r) {
  if (r.cool > 0) return {ok: false, why: "reloading"};
  if (r.rockets <= 0) return {ok: false, why: "empty"};
  return {ok: true, rocket: {rockets: r.rockets - 1, cool: RELOAD_S}};
}
export const lost = () => newRocket(0);
export {newFlight};
export const stepFlight = (W, monsters, f, dt) => flightStep(W, monsters, f, dt, SPEED, RANGE_M);
export const armed = f => f.flown >= ARM_M;
// the damage at distance d (m) from the burst: 150 within 2 m, then evenly down to 50 at 5 m, and none beyond
export const blastDamage = d => d <= FULL_R ? DMG_MAX : d <= BLAST_R ? DMG_MAX - (DMG_MAX - DMG_MIN) * (d - FULL_R) / (BLAST_R - FULL_R) : 0;
// who a burst at (x, z) on the floor of height y hurts, and by how much: [{m, dmg}] (the blast does not care about walls, like the tripwire's)
export function blastTargets(monsters, x, y, z) {
  const out = []; for (const m of monsters) { if (Math.abs(y - m.fy) >= 1.6) continue; const dmg = blastDamage(Math.hypot(m.pos.x - x, m.pos.z - z)); if (dmg > 0) out.push({m, dmg}); }
  return out;
}
// the monsters standing in the mist at (x, z)
export const inMist = (monsters, x, y, z) => monsters.filter(m => Math.abs(y - m.fy) < 1.6 && Math.hypot(m.pos.x - x, m.pos.z - z) <= MIST_R);
