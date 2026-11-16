import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {newDart, addDarts, tick, shoot, lost, newFlight, stepFlight, spreadTargets, START_DARTS, MAX_DARTS, PACK_DARTS, RELOAD_S, SPEED, RANGE_M, JELLY_S, JELLY_DPS, JELLY_SLOW, SPREAD_R, SPREAD_S} from "./dart.js";
import {indexBoxes} from "./world.js";
import {SHOT_NOISE_S as RAY_NOISE_S} from "./monsters.js";

const monCfg = JSON.parse(readFileSync(new URL("../world/monsters.json", import.meta.url)));
const hpOf = n => monCfg.monsters.find(m => m.name === n).hp;
const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};          // open ground
const mon = (x, z, o = {}) => { const m = {pos: {x, z}, fy: 0, cfg: {height: 2}, hp: 100, jellyT: 0, immuneT: 0, glitchT: 0, ...o}; return m; };

test("a shot uses one dart and starts the reload; nothing fires while reloading or empty", () => {
  let d = newDart(START_DARTS); assert.equal(START_DARTS, 3);
  const r = shoot(d); assert.ok(r.ok); d = r.dart; assert.equal(d.darts, 2); assert.equal(d.cool, RELOAD_S);
  assert.deepEqual(shoot(d), {ok: false, why: "reloading"});
  d = tick(d, RELOAD_S); assert.equal(d.cool, 0); assert.ok(shoot(d).ok);
  assert.deepEqual(shoot(newDart(0)), {ok: false, why: "empty"});
});
test("darts are capped at 5, a pack gives 1, and a death takes them all", () => {
  assert.equal(MAX_DARTS, 5); assert.equal(PACK_DARTS, 1); assert.equal(newDart(99).darts, MAX_DARTS);
  assert.equal(addDarts(newDart(2), PACK_DARTS).darts, 3); assert.equal(addDarts(newDart(MAX_DARTS), 1).darts, MAX_DARTS);
  assert.equal(lost().darts, 0);
});
test("a dart flies at 35 m/s and hits the monster it reaches; a monster that has moved on is missed (it must be led)", () => {
  assert.equal(SPEED, 35);
  const run = target => { let f = newFlight([0, 1.5, 0], [0, 0, -1]), t = 0, hit = null; while (t < 2 && !hit) { const r = stepFlight(W, [target], f, 0.02); f = r.f; hit = r.hit; t += 0.02; if (r.gone) break; target.pos.x += target.vx * 0.02; } return {hit, t}; };
  const still = run({...mon(0, -14), vx: 0}); assert.ok(still.hit, "still, 14 m"); assert.ok(Math.abs(still.t - 14 / 35) < 0.06, "takes about 0.4 s: " + still.t);
  const moving = run({...mon(0, -14), vx: 5}); assert.equal(moving.hit, null, "a monster walking across at 5 m/s is out of the line by the time it arrives");
});
test("a dart stops at a wall and at 30 m, and hits the nearest of two", () => {
  const walled = {...W, boxes: [{n: [-1, 0, -5.6], x: [1, 3, -5.0]}]}; indexBoxes(walled);
  let f = newFlight([0, 1.5, 0], [0, 0, -1]), gone = false; for (let i = 0; i < 100 && !gone; i++) { const r = stepFlight(walled, [mon(0, -9)], f, 0.02); assert.equal(r.hit, null, "never through the wall"); f = r.f; gone = r.gone; } assert.ok(gone, "stopped at the wall");
  f = newFlight([0, 1.5, 0], [0, 0, -1]); let n = 0; for (; n < 400; n++) { const r = stepFlight(W, [], f, 0.02); f = r.f; if (r.gone) break; } assert.ok(Math.abs(n * 0.02 * SPEED - RANGE_M) < 1.5, "flew about 30 m: " + n * 0.02 * SPEED);
  f = newFlight([0, 1.5, 0], [0, 0, -1]); const a = mon(0, -4), b = mon(0, -8); let hit = null; for (let i = 0; i < 50 && !hit; i++) { const r = stepFlight(W, [b, a], f, 0.02); f = r.f; hit = r.hit; } assert.equal(hit, a);
});
test("the numbers: 10 s at 15 a second is 150, slowed to half; the spread is 5 s within 4 m", () => {
  assert.equal(JELLY_S * JELLY_DPS, 150); assert.equal(JELLY_SLOW, 0.5); assert.equal(SPREAD_R, 4); assert.equal(SPREAD_S, 5); assert.equal(RELOAD_S, 2.5);
  for (const k of ["sinew", "pale_traveler", "clawed", "creature"]) assert.ok(JELLY_S * JELLY_DPS >= hpOf(k), k + " dies of one dart if left alone");
  assert.equal(0, 0); assert.ok(RAY_NOISE_S > 0);
});
test("the spread: every other monster within 4 m of the one that died, on its floor", () => {
  const dead = mon(0, 0), near = mon(3.9, 0), edge = mon(0, 4.1), other = {...mon(1, 1), fy: 5};
  assert.deepEqual(spreadTargets([dead, near, edge, other], dead), [near]);
});
