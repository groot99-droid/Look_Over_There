import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {REGISTRY} from "./registry.js";
import {worldFromDoc, pickSpots, rng32, nearestWalk, newWorld, indexBoxes, cellOf} from "./world.js";
import {reach, setChained, relink, safeToChain, pickChainedDoor, behindSpot, newBarricades, cutOpen, shutList, CAGE_PACKS, BEHIND_PACKS} from "./barricade.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const worldOf = id => { const ch = REGISTRY.chamber(id); return worldFromDoc(JSON.parse(fs.readFileSync(path.join(ROOT, `world/${id}.json`), "utf8")), id, {floor: ch.floorY, art: ch.floor}); };
const spotsOf = W => pickSpots(W, 10, rng32(7), [], 5);
const L3_DOOR = "DoorLeaf_Stair_L2_L3_down";

test("a chained door is a wall to the nav until it is cut; an unchained door is not", () => {
  const W = newWorld("x", 0); W.boxes.push({n: [-5, -1, -5], x: [5, 0, 5]});
  const box = {n: [-0.5, 0, -0.07], x: [0.5, 2.1, 0.07], door: true, off: false, link: false}, dr = {box, cx: 0, cz: 0, cy: 0, dir: [1, 0], link: null};
  W.boxes.push(box); W.doors.push(dr); indexBoxes(W); relink(W);
  const c = cellOf(0.25, 0.25); assert.equal(W.nav[c], 1, "a shut door is passable to the nav: monsters open doors");
  setChained(W, dr, true); relink(W); assert.equal(W.nav[c], 0, "chained: a wall");
  setChained(W, dr, false); relink(W); assert.equal(W.nav[c], 1, "cut: a door again");
});
test("the third floor chamber's stairwell door opens on a side room; chaining it shuts nothing that matters", () => {
  const W = worldOf("gbi_L3_1"), dr = W.doors.find(d => d.d.name === L3_DOOR), spot = behindSpot(W, dr);
  assert.ok(spot, "there is floor behind it for a pack"); assert.ok(Math.hypot(spot[0] - dr.cx, spot[1] - dr.cz) < 2.5, "just inside the door");
  const seen = reach(W.nav, nearestWalk(W.nav, ...spotsOf(W)[0])); assert.ok(!seen[nearestWalk(W.nav, ...spot)], "not on the open floor");
});
test("on every chamber, the picked door leaves every spot reachable; never a stair link, a door on another floor or a gate off the map", () => {
  let picked = 0;
  for (const id of REGISTRY.chambers) for (let seed = 1; seed <= 3; seed++) {
    const W = worldOf(id), spots = spotsOf(W), dr = pickChainedDoor(W, spots, rng32(seed));
    if (!dr) continue;
    picked++;
    assert.ok(!dr.link && Math.abs(dr.cy - W.floor) < 0.6, id + " " + dr.d.name);
    setChained(W, dr, true); relink(W);
    const seen = reach(W.nav, nearestWalk(W.nav, ...spots[0]));
    for (const s of spots) assert.ok(seen[nearestWalk(W.nav, ...s)], id + " seed " + seed + ": a spot behind the chain");
  }
  assert.ok(picked > 0, "some chamber has a door that is safe to chain");
  // since #123 the third floor's stairwell door is chamber 1's way on (into chamber 2), so it is a link and never chained
  const l31 = pickChainedDoor(worldOf("gbi_L3_1"), spotsOf(worldOf("gbi_L3_1")), rng32(1)); assert.ok(!l31 || l31.d.name !== L3_DOOR);
  assert.equal(pickChainedDoor(worldOf("gbi_L4_4"), spotsOf(worldOf("gbi_L4_4")), rng32(1)), null, "the fourth floor chamber has no door that is safe: its stair door is the way on, its gates are off the map");
});
test("a door with a spot that matters behind it is never safe", () => {
  const pick = c => { const W = worldOf(c), dr = pickChainedDoor(W, spotsOf(W), rng32(1)); return dr && behindSpot(W, dr) ? {W, dr} : null; };          // a chamber with a safe door that has floor behind it
  const id = REGISTRY.chambers.find(c => pick(c)), {W, dr} = pick(id), spots = spotsOf(W);
  assert.equal(safeToChain(W, dr, spots), true, id);
  assert.equal(safeToChain(W, dr, [...spots, behindSpot(W, dr)]), false, "the locker or the loot is in the side room");
  assert.equal(safeToChain(W, {...dr, link: {to: "L2"}}, spots), false, "a stair door");
});
test("the cage: two packs, shut until a cut; a cut opens the cage or the door for good; the shut ones are what the shear can bite", () => {
  assert.equal(CAGE_PACKS, 2); assert.equal(BEHIND_PACKS, 1);
  const dr = {cx: 3, cz: 4};
  let st = newBarricades([1, 2], dr); assert.deepEqual(st.cage, {id: "cage", x: 1, z: 2, open: false, packs: 2});
  assert.deepEqual(shutList(st, 6.4).map(b => b.id), ["cage", "door"]);
  st = cutOpen(st, "cage"); assert.equal(st.cage.open, true); assert.deepEqual(shutList(st, 6.4).map(b => b.id), ["door"]);
  st = cutOpen(st, "door"); assert.equal(st.door, null); assert.deepEqual(shutList(st, 6.4), []);
  assert.equal(cutOpen(st, "cage"), st, "cutting what is open changes nothing");
  assert.equal(newBarricades(null, null).cage, null);
});
