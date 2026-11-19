import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {FOREST, MEADOW, FOREST_ROAD_LOT, pathX, forestTrees, meadowTrees, meadowFlowers, inForestGap, inMeadowGap, forestDoc, meadowDoc, seeded} from "./forest.js";
import {REGISTRY} from "./registry.js";

test("world/forest.json and world/meadow.json are what shared/forest.js makes (run node tools/make_street.mjs)", () => {
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/forest.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(forestDoc())));
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/meadow.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(meadowDoc())));
});

test("the trees are the same for everyone, and none stands on the path, the arrival or the signpost", () => {
  assert.deepEqual(forestTrees(), forestTrees(), "seeded");
  assert.equal(forestTrees().length, FOREST.trees);
  for (const [x, z, r] of forestTrees()) {
    assert.ok(Math.abs(x - pathX(z)) >= FOREST.clear + r, `a tree on the path at ${x}, ${z}`);
    assert.ok(Math.hypot(x - FOREST.arrive[0], z - FOREST.arrive[2]) > 2, "a tree on the arrival");
  }
  const a = seeded(5), b = seeded(5); assert.equal(a(), b());
});

test("the path runs straight at both ends, so the road and the gap line up", () => {
  assert.equal(pathX(6), 0); assert.equal(pathX(-90), 0);
  for (let z = 6; z > -92; z -= 1) assert.ok(Math.abs(pathX(z)) <= 7.01, `the path wanders too far at ${z}`);
});

test("the gaps: you walk on only past the line and near the path, and you arrive outside the other side's gap", () => {
  assert.equal(inForestGap(0, -93), true); assert.equal(inForestGap(0, -80), false); assert.equal(inForestGap(10, -93), false);
  assert.equal(inMeadowGap(0, 10), true); assert.equal(inMeadowGap(0, 5), false); assert.equal(inMeadowGap(20, 10), false);
  assert.equal(inForestGap(FOREST.arrive[0], FOREST.arrive[2]), false); assert.equal(inForestGap(...[FOREST.fromMeadow.arrive[0], FOREST.fromMeadow.arrive[2]]), false);
  assert.equal(inMeadowGap(MEADOW.arrive[0], MEADOW.arrive[2]), false); assert.equal(inMeadowGap(MEADOW.returnHouse.arrive[0], MEADOW.returnHouse.arrive[2]), false);
});

test("the meadow keeps its field open: trees only at the edge, flowers off the path and away from the buildings", () => {
  const [hx, hz] = MEADOW.half;
  for (const [x, z] of meadowTrees()) assert.ok(Math.min(hx - Math.abs(x), hz - Math.abs(z - MEADOW.cz)) <= 9, `a tree in the field at ${x}, ${z}`);
  assert.equal(meadowFlowers().length, MEADOW.flowers);
  for (const [x] of meadowFlowers()) assert.ok(Math.abs(x) >= 1.8);
});

test("nothing solid stands where you arrive, at the doors' fronts or on the way back from the house", () => {
  const solid = (doc, x, z) => doc.colliders.some(c => c.max[1] > 0.2 && x > c.min[0] - 0.3 && x < c.max[0] + 0.3 && z > c.min[2] - 0.3 && z < c.max[2] + 0.3);
  const f = forestDoc(), m = meadowDoc();
  assert.equal(solid(f, FOREST.arrive[0], FOREST.arrive[2]), false); assert.equal(solid(f, FOREST.fromMeadow.arrive[0], FOREST.fromMeadow.arrive[2]), false);
  assert.equal(solid(m, MEADOW.arrive[0], MEADOW.arrive[2]), false); assert.equal(solid(m, MEADOW.returnHouse.arrive[0], MEADOW.returnHouse.arrive[2]), false);
  assert.equal(solid(m, ...MEADOW.house.door.at), false, "the house door's spot is reachable"); assert.equal(solid(m, ...MEADOW.shed.door.at), false, "the shed door's spot is reachable");
});

test("the manifest's links match the layout: the road both ways, the gaps both ways, and the house's door (solo only)", () => {
  const into = REGISTRY.linkFrom("parking_lot", "forest_road"), back = REGISTRY.linkFrom("forest", "road_back");
  assert.deepEqual(into.to.arrive, FOREST.arrive); assert.deepEqual(into.to.face, FOREST.face);
  assert.equal(back.to.scene, "parking_lot"); assert.ok(Math.hypot(back.to.arrive[0] - FOREST_ROAD_LOT.at[0], back.to.arrive[2] - FOREST_ROAD_LOT.at[1]) < FOREST_ROAD_LOT.reach + 1);
  const on = REGISTRY.linkFrom("forest", "gap"), off = REGISTRY.linkFrom("meadow", "gap");
  assert.deepEqual(on.to.arrive, MEADOW.arrive); assert.deepEqual(off.to.arrive, FOREST.fromMeadow.arrive); assert.deepEqual(off.to.face, FOREST.fromMeadow.face);
  const house = REGISTRY.linkFrom("meadow", "house_door");
  assert.equal(house.soloOnly, true); assert.equal(house.to.area, "rdwe");
  assert.deepEqual(house.returnTo.arrive, MEADOW.returnHouse.arrive); assert.deepEqual(house.returnTo.face, MEADOW.returnHouse.face);
  assert.equal(REGISTRY.linkFrom("meadow", "shed"), undefined, "the shed is still a planned link");
});

test("a room may walk the forest and the meadow once it may be in the lot, and not without the flag", () => {
  for (const s of ["forest", "meadow"]) {
    assert.equal(REGISTRY.canReach(s, ["original_complete"]).ok, true, s);
    assert.equal(REGISTRY.canReach(s, []).ok, false, `${s} without the flag`);
  }
});
