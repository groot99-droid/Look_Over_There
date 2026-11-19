// The hydraulic rebar shear (docs/ITEMS.md 4.7): the melee finisher, and the tool that opens what is chained shut. No graphics here.
// Hold to spool the motor (SPOOL_S); once spooled it stays ready for READY_S; letting go cuts the nearest thing in reach (REACH_M, ARC_DEG). COOL_S before it can spool again.
// A fresh spring has CUTS cuts and each kills anything (DMG). After the last one the spring is WORN until fluid is refilled: a worn cut kills only a monster that is helpless (stunned, slowed or held),
// a free one takes DMG_WORN, and after every worn cut the jaw must be reset by hand (hold the other button RESET_S; letting go starts over) before it can spool again.
// A cut on empty air still uses a fresh cut. A cut opens a barricade (a chained cage or door), fresh or worn. You walk at WALK_K with it in your hands; the motor is loud.
// Fluid: a cartridge is CUTS cuts. One loaded to start, MAX_SPARES spare at most; a flat cartridge swaps to a spare by itself in SWAP_S; an ammo pack gives PACK_CUTS. A death takes it all.
import {inCone} from "./cone.js";
export const CUTS = 4, DMG = 200, DMG_WORN = 100, SPOOL_S = 1.0, READY_S = 3.0, COOL_S = 1.5, RESET_S = 3.0, REACH_M = 2.0, ARC_DEG = 30, BARRICADE_ARC_DEG = 70;
export const MAX_SPARES = 2, SWAP_S = 2, PACK_CUTS = 2, WALK_K = 0.8, NOISE_S = 0.5;
// a state is {cuts (fresh cuts left), spares, swapT, spool (s), ready (s held ready), cool (s), needReset, reset (s of the reset done)}
export const newShear = () => ({cuts: CUTS, spares: 0, swapT: 0, spool: 0, ready: 0, cool: 0, needReset: false, reset: 0});
export const worn = s => s.cuts <= 0;
export const spooled = s => s.spool >= SPOOL_S;
export const blocked = s => s.swapT > 0 ? "swapping" : s.cool > 0 ? "cooling" : s.needReset ? "reset" : null;
// time passing: the cooldown and the swap run down (a finished swap is a fresh spring)
export function tick(s, dt) {
  let {cool, swapT, cuts, spares, needReset, reset} = s; cool = Math.max(0, cool - dt);
  if (swapT > 0) { swapT = Math.max(0, swapT - dt); if (swapT === 0) { cuts = CUTS; spares = Math.max(0, spares - 1); needReset = false; reset = 0; } }
  return {...s, cool, swapT, cuts, spares, needReset, reset};
}
// the trigger held for dt: the motor spools, then holds ready; held past READY_S it winds down and has to spool again. Blocked (cooling, swapping, needs a reset): nothing moves.
export function hold(s, dt) {
  if (blocked(s)) return {...s, spool: 0, ready: 0};
  if (s.spool < SPOOL_S) return {...s, spool: Math.min(SPOOL_S, s.spool + dt), ready: 0};
  const ready = s.ready + dt; return ready > READY_S ? {...s, spool: 0, ready: 0} : {...s, ready};
}
// the trigger let go. target: {kind: "monster", helpless} | {kind: "barricade"} | null.
// Returns {ok: false, why: "early", shear} (not spooled: nothing spent), or {ok: true, shear, dmg (to a monster), opened (a barricade), wornCut}
export function release(s, target) {
  const rest = {...s, spool: 0, ready: 0};
  if (!spooled(s) || blocked(s)) return {ok: false, why: "early", shear: rest};
  const w = worn(s), isMon = !!target && target.kind === "monster", dmg = isMon ? (w ? (target.helpless ? DMG : DMG_WORN) : DMG) : 0;
  let n = {...rest, cool: COOL_S};
  if (w) n = {...n, needReset: true, reset: 0};
  else { n = {...n, cuts: s.cuts - 1}; if (n.cuts <= 0 && n.spares > 0) n = {...n, swapT: SWAP_S}; }          // the last fresh cut: a spare cartridge goes in by itself
  return {ok: true, shear: n, dmg, opened: !!target && target.kind === "barricade", wornCut: w};
}
// the reset button held (or not) for dt: only a jaw that needs it. RESET_S of holding clears it; letting go starts over.
export function resetHold(s, dt, held) {
  if (!s.needReset) return s.reset ? {...s, reset: 0} : s;
  if (!held) return s.reset ? {...s, reset: 0} : s;
  const reset = s.reset + dt; return reset >= RESET_S ? {...s, needReset: false, reset: 0} : {...s, reset};
}
// fluid from an ammo pack: fresh cuts again (and a fresh spring needs no reset)
export const addCuts = (s, n) => { const cuts = Math.min(CUTS, s.cuts + n); return {...s, cuts, ...(cuts > 0 ? {needReset: false, reset: 0, swapT: 0} : {})}; };
export const addSpare = s => ({...s, spares: Math.min(MAX_SPARES, s.spares + 1)});
export const lost = () => ({...newShear(), cuts: 0});
// a monster a worn shear can still kill: stunned, slowed (jelly, fire, the mist) or held (the gauntlet)
export const helpless = m => (m.stunT || 0) > 0 || (typeof m.slowMul === "function" && m.slowMul() < 1) || !!m.held;
// what a cut from eye o facing the unit vector f = [x, z] bites: the nearest of the monsters in reach and arc and the shut barricades [{id, x, z, y, open}] in reach (they are big: a wider arc).
// Returns {kind: "monster", m, helpless} | {kind: "barricade", b} | null
export function cutTarget(W, monsters, barricades, o, f) {
  let best = null, bd = 1e9;
  for (const m of inCone(W, monsters, o, f, REACH_M, ARC_DEG)) { const d = Math.hypot(m.pos.x - o[0], m.pos.z - o[2]); if (d < bd) { bd = d; best = {kind: "monster", m, helpless: helpless(m)}; } }
  for (const b of barricades) {
    if (b.open || Math.abs(o[1] - 1.6 - (b.y ?? o[1] - 1.6)) > 1.6) continue;
    const dx = b.x - o[0], dz = b.z - o[2], d = Math.hypot(dx, dz); if (d > REACH_M || d >= bd) continue;
    if (d > 0.5 && Math.acos(Math.max(-1, Math.min(1, (f[0] * dx + f[1] * dz) / d))) * 180 / Math.PI > BARRICADE_ARC_DEG / 2) continue;
    bd = d; best = {kind: "barricade", b};
  }
  return best;
}
