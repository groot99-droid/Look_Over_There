import test from "node:test";
import assert from "node:assert/strict";
import {newBow, addBolts, tick, shoot, killShot, MAX_BOLTS, START_BOLTS, PACK_BOLTS, RELOAD_S} from "./crossbow.js";
import {SHOT_NOISE_S as RAY_NOISE_S} from "./monsters.js";
import {SHOT_NOISE_S} from "./crossbow.js";

test("a shot uses one bolt and starts the reload; nothing fires while reloading or empty", () => {
  let b = newBow(START_BOLTS);
  const r = shoot(b); assert.ok(r.ok); b = r.bow;
  assert.equal(b.bolts, START_BOLTS - 1); assert.equal(b.cool, RELOAD_S);
  assert.deepEqual(shoot(b), {ok: false, why: "reloading"});
  b = tick(b, RELOAD_S); assert.equal(b.cool, 0); assert.ok(shoot(b).ok);
  assert.deepEqual(shoot(newBow(0)), {ok: false, why: "empty"});
});
test("bolts are capped, and a pack gives PACK_BOLTS", () => {
  assert.equal(newBow(99).bolts, MAX_BOLTS);
  assert.equal(addBolts(newBow(1), PACK_BOLTS).bolts, 1 + PACK_BOLTS);
  assert.equal(addBolts(newBow(MAX_BOLTS - 1), PACK_BOLTS).bolts, MAX_BOLTS);
});
test("the crossbow is quieter than the ray and reloads slower than the ray cools", () => { assert.ok(SHOT_NOISE_S < RAY_NOISE_S); assert.ok(RELOAD_S > 0.6); });
test("a bolt kills the nearest monster on the ray, and none when a wall is between", () => {
  // a world with open ground: no boxes, so every ray is clear
  const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};
  const m = (x, z) => ({pos: {x, z}, fy: 0, cfg: {height: 2}, immuneT: 0, glitchT: 0});
  const a = m(0, -5), b = m(0, -10);
  assert.equal(killShot(W, [b, a], [0, 1.5, 0], [0, 0, -1]), a);
  assert.equal(killShot(W, [a], [0, 1.5, 0], [0, 0, 1]), null, "aimed the other way");
});
