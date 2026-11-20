// The propane flamethrower (docs/ITEMS.md 4.3): close area control that holds a doorway against a crowd. No graphics here.
// Hold to burn: a cone CONE_M long and CONE_DEG wide, blocked by walls. Everything in it takes DPS a second and is Burning (BURN_DPS a second and slowed to BURN_SLOW, for BURN_S after the flame
// leaves it; half as long on the wet sinew: `burnTime` in world/monsters.json). A burst is loud (monsters within BURST_NOISE_R go to look) and you count as running while you fire; firing switches your cloak off.
// Ammo: propane. The tank holds 100% and burns FUEL_PER_S of it a second (10 s of flame). A pack gives PACK_FUEL to the tank; what does not fit fills the spare canister (at most 100%).
// Swapping to the spare takes SWAP_S and swaps the two. A death empties the tank and takes the spare. A wall within SELF_M of your face throws the flame back (the page hurts you once a second).
import {rayClear} from "./world.js";
import {inCone} from "./cone.js";
export const CONE_M = 6, CONE_DEG = 40, DPS = 40, BURN_S = 4, BURN_DPS = 10, BURN_SLOW = 0.6;
export const FUEL_PER_S = 0.1, PACK_FUEL = 0.25, SWAP_S = 2.5, BURST_NOISE_R = 15, BURST_GAP_S = 0.5, SELF_M = 1.0;
const cap = v => Math.max(0, Math.min(1, v));
// a state is {fuel (the tank, 0..1), spare (0..1), swapT (s left swapping), idle (s since the flame last burned)}
export const newFlame = () => ({fuel: 1, spare: 0, swapT: 0, idle: 99});
export function tick(f, dt) {
  let {fuel, spare, swapT} = f;
  if (swapT > 0) { swapT = Math.max(0, swapT - dt); if (swapT === 0) { const t = fuel; fuel = spare; spare = t; } }          // the swap lands when the time is up
  return {fuel, spare, swapT, idle: f.idle + dt};
}
// burn for dt: {ok: true, flame, burst} (burst: this is a new burst, not a flame carrying on), or {ok: false, why: "swapping" | "empty"}
export function burn(f, dt) {
  if (f.swapT > 0) return {ok: false, why: "swapping"};
  if (f.fuel <= 0) return {ok: false, why: "empty"};
  return {ok: true, burst: f.idle >= BURST_GAP_S, flame: {...f, fuel: cap(f.fuel - FUEL_PER_S * dt), idle: 0}};
}
// start swapping to the spare canister: {ok: true, flame}, or {ok: false, why: "swapping" | "no spare"}
export function startSwap(f) {
  if (f.swapT > 0) return {ok: false, why: "swapping"};
  if (f.spare <= 0) return {ok: false, why: "no spare"};
  return {ok: true, flame: {...f, swapT: SWAP_S}};
}
export function addFuel(f, n) { const fuel = cap(f.fuel + n), over = f.fuel + n - fuel; return {...f, fuel, spare: cap(f.spare + Math.max(0, over))}; }
export const lost = () => ({fuel: 0, spare: 0, swapT: 0, idle: 99});
// seconds a burn lasts on a monster kind (the sinew is wet: world/monsters.json `burnTime` 0.5)
export const burnSecs = (cfg, secs) => secs * ((cfg && cfg.burnTime) || 1);
// every monster in the flame's cone from eye o facing the unit vector f = [x, z]: on o's floor, within CONE_M and CONE_DEG, with nothing solid between
export const coneTargets = (W, monsters, o, f) => inCone(W, monsters, o, f, CONE_M, CONE_DEG);
// is there a wall right in front of your face (the flame has nowhere to go but back)? o: the eye, d: the unit view direction
export const blockedAtFeet = (W, o, d) => !rayClear(W, o, d, SELF_M);
