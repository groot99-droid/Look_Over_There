import test from "node:test";
import assert from "node:assert/strict";
import {newDriver, addNails, damage, tick, shoot, nailHit, lost, MAX_NAILS, START_NAILS, PACK_NAILS, GAUGE, COOL_S, REFILL_DELAY_S, REFILL_S, RANGE_M, SHOT_NOISE_S} from "./driver.js";
import {SHOT_NOISE_S as BOW_NOISE_S} from "./crossbow.js";

// fire as fast as the cooldown lets us, `n` times, returning the damage of each shot
function burst(d, n) { const out = []; for (let i = 0; i < n; i++) { d = tick(d, COOL_S); const r = shoot(d); assert.ok(r.ok, "shot " + (i + 1)); out.push(r.dmg); d = r.driver; } return {d, out}; }

test("eight shots from a full gauge do 35, 32.5, 30 ... 17.5, and a ninth still fires at 15", () => {
  const {d, out} = burst(newDriver(START_NAILS), 8);
  assert.deepEqual(out, [35, 32.5, 30, 27.5, 25, 22.5, 20, 17.5]);
  assert.equal(d.air, 0); assert.equal(damage(d), 15);
  assert.equal(burst(d, 1).out[0], 15, "an empty gauge fires at the minimum");
});
test("a shot uses one nail and starts the cooldown; nothing fires while cooling or with no nails", () => {
  let d = newDriver(START_NAILS); const r = shoot(d); assert.ok(r.ok); d = r.driver;
  assert.equal(d.nails, START_NAILS - 1); assert.equal(d.cool, COOL_S);
  assert.deepEqual(shoot(d), {ok: false, why: "cooling"});
  assert.deepEqual(shoot(tick(newDriver(0), 1)), {ok: false, why: "empty"});
});
test("nails are capped, start at 16, and a pack gives 8", () => {
  assert.equal(START_NAILS, 16); assert.equal(newDriver(99).nails, MAX_NAILS);
  assert.equal(addNails(newDriver(START_NAILS), PACK_NAILS).nails, 24);
  assert.equal(addNails(newDriver(MAX_NAILS - 3), PACK_NAILS).nails, MAX_NAILS);
});
test("the gauge waits REFILL_DELAY_S after a shot, then gains an eighth every REFILL_S, and stops full", () => {
  let d = burst(newDriver(START_NAILS), 4).d; assert.equal(d.air, 4);
  d = tick(d, REFILL_DELAY_S - 0.05); assert.equal(d.air, 4, "still waiting");
  d = tick(d, 0.05 + REFILL_S - 0.01); assert.equal(d.air, 4, "not yet an eighth");
  d = tick(d, 0.02); assert.equal(d.air, 5);
  d = tick(d, 100); assert.equal(d.air, GAUGE); assert.equal(d.fill, 0);
  // firing again resets the wait
  let e = burst(newDriver(START_NAILS), 2).d; e = tick(e, REFILL_DELAY_S + REFILL_S * 0.9); const f = shoot(tick(e, 0)); e = f.driver; assert.equal(e.fill, 0); assert.equal(e.idle, 0);
});
test("from empty the air takes REFILL_S x GAUGE of refilling (12 s) after the 1 s wait", () => {
  let d = burst(newDriver(START_NAILS), 8).d; assert.equal(d.air, 0);
  d = tick(d, REFILL_DELAY_S + REFILL_S * GAUGE - 0.01); assert.equal(d.air, GAUGE - 1);
  d = tick(d, 0.02); assert.equal(d.air, GAUGE);
});
test("it is as quiet as the crossbow (a puff), and a death takes the nails but not the air", () => {
  assert.equal(SHOT_NOISE_S, BOW_NOISE_S);
  const d = lost(); assert.equal(d.nails, 0); assert.equal(d.air, GAUGE);
});
test("a nail hits the nearest monster within 18 m, and nothing farther or behind", () => {
  const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};
  const m = (x, z) => ({pos: {x, z}, fy: 0, cfg: {height: 2}, immuneT: 0, glitchT: 0});
  const a = m(0, -5), b = m(0, -10), far = m(0, -22);
  assert.equal(nailHit(W, [b, a], [0, 1.5, 0], [0, 0, -1]).m, a);
  assert.equal(nailHit(W, [far], [0, 1.5, 0], [0, 0, -1]), null, "22 m is past the nail's 18 m (the ray reaches 25)");
  assert.equal(nailHit(W, [m(0, -RANGE_M + 1)], [0, 1.5, 0], [0, 0, -1]).m.pos.z, -RANGE_M + 1);
  assert.equal(nailHit(W, [a], [0, 1.5, 0], [0, 0, 1]), null, "aimed the other way");
});
