// Barricades for the rebar shear (docs/ITEMS.md 4.7), solo Going back in only. No graphics here.
// Each chamber has a chained supply cage (two ammo packs inside; the second becomes a med kit when that exists) and may have one chained door.
// Only a shear cut opens either; then it stays open for that visit (a chamber is fresh again each time you enter, like the traps).
// A chained door is a wall to everyone: the nav treats it as one (shared/world.js buildNav reads box.chained), so no monster paths through it, and nobody can open it.
// Which door: one that leaves every spot that matters (the start, the locker, the loot, the stairs, the spawns) reachable with it shut. A chamber where no door is safe has none.
// The chambers have no doors between two parts of the open floor, only side doors into dead-end stairwells, so the chained door shuts a side room; BEHIND_PACKS ammo packs wait inside (behindSpot) so a cut is worth spending.
import {NW, NH, buildNav, nearestWalk, mainRegion, cellXZ} from "./world.js";
export const CAGE_PACKS = 2, BEHIND_PACKS = 1;
// flood-fill a walk grid from cell c0: the set of cells reached (8-way, no corner cutting, as A* walks)
export function reach(walk, c0) {
  const seen = new Uint8Array(NW * NH); if (c0 < 0 || !walk[c0]) return seen;
  const stack = [c0]; seen[c0] = 1;
  while (stack.length) {
    const c = stack.pop(), ci = c % NW, cj = (c / NW) | 0;
    for (let dj = -1; dj <= 1; dj++) for (let di = -1; di <= 1; di++) {
      if (!di && !dj) continue;
      const i = ci + di, j = cj + dj; if (i < 0 || j < 0 || i >= NW || j >= NH) continue;
      const n = j * NW + i; if (seen[n] || !walk[n]) continue;
      if (di && dj && (!walk[cj * NW + i] || !walk[j * NW + ci])) continue;
      seen[n] = 1; stack.push(n);
    }
  }
  return seen;
}
// chain or unchain a door: the box becomes a wall to the nav (and the door is marked so nobody opens it). The caller rebuilds W.nav (relink).
export function setChained(W, dr, on) { dr.chained = !!on; dr.box.chained = !!on; }
export const relink = W => { W.nav = buildNav(W, W.floor); return W.nav; };
// is it safe to chain door dr: with it shut and chained, every spot [x, z] in `spots` can still be reached from spots[0]?
export function safeToChain(W, dr, spots) {
  if (dr.link || Math.abs(dr.cy - W.floor) > 0.6 || !spots.length) return false;
  const was = [dr.chained, dr.box.chained, dr.box.off]; dr.box.off = false; setChained(W, dr, true);
  const walk = buildNav(W, W.floor);
  dr.chained = was[0]; dr.box.chained = was[1]; dr.box.off = was[2];
  const start = nearestWalk(walk, spots[0][0], spots[0][1]); if (start < 0) return false;
  const seen = reach(walk, start);
  if (!spots.every(([x, z]) => { const c = nearestWalk(walk, x, z); return c >= 0 && seen[c]; })) return false;
  const a = nearestWalk(W.nav, ...side(dr, 1)), b = nearestWalk(W.nav, ...side(dr, -1));
  if (a < 0 || b < 0) return false;                                  // not a doorway on this floor's walkable ground (a gate off the map)
  if (seen[a] && seen[b]) return true;                               // a shortcut: both sides still joined the long way round
  return !!behindSpot(W, dr, seen);                                  // a side room: nothing that matters is in it
}
// the two sides of a door, 0.8 m out along its normal
const side = (dr, k) => [dr.cx + k * dr.dir[1] * 0.8, dr.cz - k * dr.dir[0] * 0.8];
// a doorway joins the region `seen` (reached from the start) on one side and floor that is not on the other: the walkable spot 1.5 m into the far side, or null
export function behindSpot(W, dr, seen = null) {
  if (!seen) { const reg = mainRegion(W); seen = new Uint8Array(NW * NH); for (const c of reg) seen[c] = 1; }
  for (const k of [1, -1]) {
    const near = nearestWalk(W.nav, ...side(dr, k)), far = nearestWalk(W.nav, ...side(dr, -k));
    if (near < 0 || far < 0 || !seen[near] || seen[far]) continue;
    const c = nearestWalk(W.nav, dr.cx - k * dr.dir[1] * 1.5, dr.cz + k * dr.dir[0] * 1.5);
    return c >= 0 && !seen[c] ? cellXZ(c) : cellXZ(far);
  }
  return null;
}
// pick the chained door: candidates in random order (rnd), the first that is safe. Returns the door or null.
export function pickChainedDoor(W, spots, rnd) {
  const cand = W.doors.filter(dr => !dr.link && Math.abs(dr.cy - W.floor) < 0.6);
  for (let i = cand.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [cand[i], cand[j]] = [cand[j], cand[i]]; }
  return cand.find(dr => safeToChain(W, dr, spots)) || null;
}
// the chamber's barricade state: {cage: {x, z, open, packs}, door: the chained door or null}
export const newBarricades = (cageAt, door) => ({cage: cageAt ? {id: "cage", x: cageAt[0], z: cageAt[1], open: false, packs: CAGE_PACKS} : null, door: door || null});
// a cut on barricade id ("cage" or "door"): opens it for good. Returns the new state; the caller unchains and relinks for a door.
export function cutOpen(st, id) {
  if (id === "cage" && st.cage && !st.cage.open) return {...st, cage: {...st.cage, open: true}};
  if (id === "door" && st.door) return {...st, door: null};
  return st;
}
// the shut ones as the shear sees them: [{id, x, z, y, open}] (the door's spot is its middle)
export function shutList(st, floor) {
  const out = [];
  if (st.cage && !st.cage.open) out.push({id: "cage", x: st.cage.x, z: st.cage.z, y: floor, open: false});
  if (st.door) out.push({id: "door", x: st.door.cx, z: st.door.cz, y: floor, open: false});
  return out;
}
