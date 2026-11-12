import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {FACTORY, FACTORY_FRONT, KINDS, LINE, shiftEnds, kindOf, newLine, stepLine, pickUp, binNear, drop, linePay, factoryDoc} from "./factory.js";
import {DOORS, DAY_S, hourAt, secondsAt} from "./city.js";
import {STUB_SHIFTS} from "./pay.js";
import {REGISTRY} from "./registry.js";

test("world/factory_floor.json is what shared/factory.js makes, and the links match", () => {
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/factory_floor.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(factoryDoc())));
  const into = REGISTRY.linkFrom("street", "e330"), out = REGISTRY.linkFrom("factory_floor", "front_door");
  assert.ok(into && out && into.soloOnly && out.soloOnly);
  assert.deepEqual(into.requires, ["job_factory"]);
  assert.deepEqual(into.to.arrive, FACTORY.arrive); assert.deepEqual(into.to.face, FACTORY.face);
  assert.deepEqual(out.to.arrive, FACTORY_FRONT.arrive); assert.deepEqual(out.to.face, FACTORY_FRONT.face);
  const door = DOORS.find(d => d.id === "e330");
  assert.ok(Math.hypot(door.x - FACTORY_FRONT.arrive[0], door.z - FACTORY_FRONT.arrive[2]) < door.reach);
});
test("the hall: you arrive by the door; the belt and bins are inside and you can reach them from the floor", () => {
  const [hx, hz] = FACTORY.half, B = FACTORY.belt;
  assert.ok(Math.hypot(FACTORY.arrive[0] - FACTORY.door.at[0], FACTORY.arrive[2] - FACTORY.door.at[1]) < FACTORY.door.reach);
  assert.ok(B.x0 > -hx && B.x1 < hx && Math.abs(B.z) < hz);
  assert.ok(B.w / 2 + 0.3 < LINE.reach, "a part on the belt is in reach from beside it");
  for (const b of FACTORY.bins) { assert.ok(Math.abs(b.x) < hx && Math.abs(b.z) < hz); assert.ok(b.half + 0.3 < b.reach); assert.ok(KINDS[b.kind]); }
  assert.equal(new Set(FACTORY.bins.map(b => b.kind)).size, 3);
});
test("the shift keeps the stub's hours: 4", () => {
  assert.equal(LINE.hours, STUB_SHIFTS.factory.hours);
  assert.ok(Math.abs(hourAt(shiftEnds(secondsAt(10, 2))) - 14) < 1e-9);
  assert.ok(Math.abs(shiftEnds(0) - 4 / 24 * DAY_S) < 1e-9);
});
test("parts come in a fixed mixed order of the three kinds", () => {
  const seq = Array.from({length: 30}, (_, n) => kindOf(n));
  for (const k of Object.keys(KINDS)) assert.ok(seq.filter(x => x === k).length >= 5, k);
  assert.deepEqual(seq, Array.from({length: 30}, (_, n) => kindOf(n)));
});
test("the belt: a part every 4 s at the west end, moving east at 0.8 m/s, missed when it passes the east end", () => {
  let st = stepLine(newLine(), 0);
  assert.equal(st.parts.length, 1); assert.equal(st.parts[0].x, FACTORY.belt.x0);
  st = stepLine(st, 4); assert.equal(st.parts.length, 2); assert.ok(Math.abs(st.parts[0].x - (FACTORY.belt.x0 + 3.2)) < 1e-9);
  const travel = (FACTORY.belt.x1 - FACTORY.belt.x0) / LINE.speed;            // 20 s
  for (let k = 0; k < 100; k++) st = stepLine(st, 0.25);                        // 29 s in all
  assert.equal(st.made, Math.floor(29 / 4) + 1);
  assert.equal(st.missed + st.parts.length, st.made);
  assert.ok(st.missed >= 2 && st.parts.every(p => p.x <= FACTORY.belt.x1));
  assert.ok(travel === 20);
  const big = stepLine(newLine(), 60); assert.equal(big.made + 0, 16); assert.equal(big.missed + big.parts.length, 16, "one big step loses nothing");
});
test("F picks up the nearest part within reach, one at a time; F at a bin sorts it right or wrong", () => {
  let st = stepLine(newLine(), 0); st = stepLine(st, 10);
  const p = st.parts[0];
  assert.equal(pickUp(st, p.x, FACTORY.belt.z + 5).got, null, "out of reach");
  let r = pickUp(st, p.x, FACTORY.belt.z + 1);
  assert.equal(r.got, p.kind); assert.equal(r.st.parts.length, st.parts.length - 1); assert.deepEqual(r.st.held, {id: p.id, kind: p.kind});
  assert.equal(pickUp(r.st, r.st.parts[0].x, FACTORY.belt.z + 1).got, null, "hands full");
  const right = FACTORY.bins.findIndex(b => b.kind === p.kind), wrong = (right + 1) % 3;
  assert.equal(binNear(FACTORY.bins[right].x, FACTORY.bins[right].z + 1), right); assert.equal(binNear(0, -6), -1);
  const a = drop(r.st, right); assert.equal(a.ok, true); assert.equal(a.st.right, 1); assert.equal(a.st.held, null);
  const b = drop(r.st, wrong); assert.equal(b.ok, false); assert.equal(b.st.wrong, 1);
  assert.equal(drop(a.st, right).ok, null, "nothing to drop");
});
test("pay: $1 a part sorted right, $1 off for each wrong, $0 to $20; leaving early pays nothing", () => {
  const st = {...newLine(), right: 9, wrong: 2, missed: 4};
  assert.equal(linePay(st, "done").pay, 7);
  assert.deepEqual(linePay(st, "done").lines, ["Sorted right: 9", "In the wrong bin: 2", "Missed: 4", "Paid: $7"]);
  assert.equal(linePay({...st, right: 40, wrong: 0}, "done").pay, 20);
  assert.equal(linePay({...st, right: 1, wrong: 5}, "done").pay, 0);
  assert.equal(linePay(st, "left").pay, 0); assert.equal(linePay(st, "left").note, "Factory: left early");
  assert.equal(linePay(st, "done").note, "Factory 9 right, 2 wrong");
});
