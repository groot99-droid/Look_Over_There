// Going back in: the pure rules for a chamber's wave, with no graphics. The page (index.html) places the monsters this plan names; a room's server will use the same plan later.
// A chamber's wave starts when the player enters it; the rest of the time is quiet (nothing here ticks a clock).
import {pickSpots, rng32} from "./world.js";

// Where a chamber's wave starts: `chamber.wave.monsters` spots on the walkable grid, at least 16 m from every player (pickSpots keeps that distance from `avoid`) and off the stair doors.
// Seeded from the chamber id, so the same chamber gives the same wave everywhere. monCfg: world/monsters.json. Returns [{cfg, x, z}]; fewer than asked if the floor has no room.
export function wavePlan(W, monCfg, chamber, avoid = []) {
  const cfg = monCfg.monsters.find(m => m.name === chamber.wave.kind);
  if (!cfg) throw new Error(`chamber ${chamber.id}: no monster kind ${chamber.wave.kind}`);
  const seed = [...chamber.id].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
  return pickSpots(W, chamber.wave.monsters, rng32(seed), avoid).map(([x, z]) => ({cfg, x, z}));
}
// The state of a chamber's wave: null before you enter. `no` is the wave's number in the run (1 to 20).
export const startWave = (chamber, now) => ({chamber: chamber.id, no: chamber.wave.no, monsters: chamber.wave.monsters, t0: now, kills: 0, cleared: false});
// a monster of the wave was killed (a lethal weapon; the ray only banishes): the wave is cleared when all of them are. Only the kill count is a clear rule so far.
export const killed = w => { const kills = w.kills + 1; return {...w, kills, cleared: kills >= w.monsters}; };
