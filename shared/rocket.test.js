import test from "node:test";
import assert from "node:assert/strict";
import {newRocket, addRockets, tick, fire, lost, newFlight, stepFlight, armed, blastDamage, blastTargets, inMist, START_ROCKETS, MAX_ROCKETS, RELOAD_S, SPEED, RANGE_M, ARM_M, BLAST_R, FULL_R, DMG_MAX, DMG_MIN, MIST_R, MIST_S, MIST_SLOW, NOISE_R} from "./rocket.js";
import {indexBoxes} from "./world.js";

const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};
const mon = (x, z, o = {}) => ({pos: {x, z}, fy: 0, cfg: {height: 2}, ...o});

test("one rocket to start, three at most, none from a pack; a shot uses one and reloads for 3.5 s; a death takes them all", () => {
  assert.equal(START_ROCKETS, 1); assert.equal(MAX_ROCKETS, 3); assert.equal(newRocket(99).rockets, MAX_ROCKETS);
  assert.equal(addRockets(newRocket(1), 1).rockets, 2); assert.equal(addRockets(newRocket(MAX_ROCKETS), 1).rockets, MAX_ROCKETS);
  let r = newRocket(2); const s = fire(r); assert.ok(s.ok); r = s.rocket; assert.equal(r.rockets, 1); assert.equal(r.cool, RELOAD_S); assert.equal(RELOAD_S, 3.5);
  assert.deepEqual(fire(r), {ok: false, why: "reloading"}); r = tick(r, RELOAD_S); assert.ok(fire(r).ok);
  assert.deepEqual(fire(newRocket(0)), {ok: false, why: "empty"}); assert.equal(lost().rockets, 0);
});
test("a rocket flies at 25 m/s for 40 m and bursts on the first monster or wall it meets; one that meets something within 5 m of where it left has not armed", () => {
  assert.equal(SPEED, 25); assert.equal(RANGE_M, 40); assert.equal(ARM_M, 5);
  const run = (monsters, w = W) => { let f = newFlight([0, 1.5, 0], [0, 0, -1]), t = 0, hit = null; while (t < 3) { const r = stepFlight(w, monsters, f, 0.02); f = r.f; hit = r.hit; t += 0.02; if (r.gone) return {f, hit, t}; } return {f, hit, t}; };
  const a = run([mon(0, -12)]); assert.ok(a.hit); assert.ok(Math.abs(a.t - 12 / SPEED) < 0.06, "12 m takes about 0.48 s: " + a.t); assert.ok(armed(a.f));
  const near = run([mon(0, -3)]); assert.ok(near.hit); assert.equal(armed(near.f), false, "3 m is a dud");
  const walled = {...W, boxes: [{n: [-3, 0, -9.6], x: [3, 3, -9.0]}]}; indexBoxes(walled); const w = run([], walled); assert.equal(w.hit, null); assert.ok(w.f.flown > 8 && w.f.flown < 9.4 && armed(w.f), "bursts at the wall: " + w.f.flown);
  const open = run([]); assert.ok(Math.abs(open.f.flown - RANGE_M) < 0.8 && open.t > 1.5, "at 40 m it ends: " + open.f.flown);
});
test("the blast does 150 within 2 m, falling evenly to 50 at 5 m, and nothing beyond", () => {
  assert.equal(DMG_MAX, 150); assert.equal(DMG_MIN, 50); assert.equal(FULL_R, 2); assert.equal(BLAST_R, 5);
  assert.equal(blastDamage(0), 150); assert.equal(blastDamage(2), 150); assert.equal(blastDamage(3.5), 100); assert.equal(blastDamage(5), 50); assert.equal(blastDamage(5.01), 0);
  assert.ok(blastDamage(2.5) > blastDamage(3) && blastDamage(3) > blastDamage(4), "falls with distance");
  const a = mon(1, 0), b = mon(4.5, 0), far = mon(5.5, 0), up = {...mon(1, 1), fy: 5};
  assert.deepEqual(blastTargets([a, b, far, up], 0, 0, 0).map(t => [t.m, Math.round(t.dmg)]), [[a, 150], [b, 67]]);
});
test("the mist is 5 m wide (2.5 m out) and lasts 6 s, slowing what is in it to half; the burst is heard 40 m away", () => {
  assert.equal(MIST_R, 2.5); assert.equal(MIST_S, 6); assert.equal(MIST_SLOW, 0.5); assert.equal(NOISE_R, 40);
  const a = mon(2.4, 0), b = mon(2.6, 0), up = {...mon(0, 1), fy: 5};
  assert.deepEqual(inMist([a, b, up], 0, 0, 0), [a]);
});
