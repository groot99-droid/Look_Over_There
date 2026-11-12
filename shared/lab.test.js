import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {LAB, LAB_FRONT, BENCH, shiftEnds, cardOf, newBench, stationNear, useStation, cardText, benchPay, labDoc} from "./lab.js";
import {DOORS, DAY_S, hourAt, secondsAt} from "./city.js";
import {STUB_SHIFTS} from "./pay.js";
import {REGISTRY} from "./registry.js";

test("world/laboratory.json is what shared/lab.js makes, and the links match", () => {
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/laboratory.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(labDoc())));
  const into = REGISTRY.linkFrom("street", "w214"), out = REGISTRY.linkFrom("laboratory", "front_door");
  assert.ok(into && out && into.soloOnly && out.soloOnly);
  assert.deepEqual(into.requires, ["job_lab"]);
  assert.deepEqual(into.to.arrive, LAB.arrive); assert.deepEqual(into.to.face, LAB.face);
  assert.deepEqual(out.to.arrive, LAB_FRONT.arrive); assert.deepEqual(out.to.face, LAB_FRONT.face);
  const door = DOORS.find(d => d.id === "w214");
  assert.ok(Math.hypot(door.x - LAB_FRONT.arrive[0], door.z - LAB_FRONT.arrive[2]) < door.reach);
});
test("the room: five stations inside, each reachable and none in reach of another; you arrive by the door", () => {
  const [hx, hz] = LAB.half;
  assert.equal(LAB.stations.length, 5);
  assert.ok(Math.hypot(LAB.arrive[0] - LAB.door.at[0], LAB.arrive[2] - LAB.door.at[1]) < LAB.door.reach);
  for (const s of LAB.stations) {
    assert.ok(Math.abs(s.x) + s.half < hx && Math.abs(s.z) + s.half < hz, s.id);
    assert.ok(s.half + 0.3 < s.reach);
    for (const o of LAB.stations) if (o !== s) assert.ok(Math.hypot(o.x - s.x, o.z - s.z) > s.reach + o.reach, `${s.id} and ${o.id} apart`);
    assert.ok(Math.hypot(s.x - LAB.door.at[0], s.z - LAB.door.at[1]) > s.reach + LAB.door.reach);
  }
  assert.equal(stationNear(LAB.stations[2].x, LAB.stations[2].z + 1.2), 2); assert.equal(stationNear(0, 0), -1);
});
test("the shift keeps the stub's hours: 4", () => {
  assert.equal(BENCH.hours, STUB_SHIFTS.lab.hours);
  assert.ok(Math.abs(hourAt(shiftEnds(secondsAt(9, 2))) - 13) < 1e-9);
  assert.ok(Math.abs(shiftEnds(0) - 4 / 24 * DAY_S) < 1e-9);
});
test("each card names three different stations, in a fixed order that varies from card to card", () => {
  const ids = new Set(LAB.stations.map(s => s.id));
  for (let n = 0; n < 40; n++) { const c = cardOf(n); assert.equal(c.length, 3); assert.equal(new Set(c).size, 3); assert.ok(c.every(id => ids.has(id))); assert.deepEqual(c, cardOf(n)); }
  assert.ok(new Set(Array.from({length: 20}, (_, n) => cardOf(n).join())).size >= 8, "the cards are not all the same");
});
test("the right station does the step; the third finishes the card; a wrong one spoils it and the next card comes up", () => {
  let b = newBench(); const c = cardOf(0);
  let r = useStation(b, c[0]); assert.equal(r.result, "step"); assert.equal(r.b.step, 1);
  r = useStation(r.b, c[1]); assert.equal(r.result, "step");
  r = useStation(r.b, c[2]); assert.equal(r.result, "done"); assert.deepEqual([r.b.card, r.b.step, r.b.done, r.b.spoiled], [1, 0, 1, 0]);
  const c1 = cardOf(1), wrongId = LAB.stations.map(s => s.id).find(id => id !== c1[0]);
  r = useStation(r.b, wrongId); assert.equal(r.result, "wrong"); assert.equal(r.want, c1[0]); assert.deepEqual([r.b.card, r.b.step, r.b.done, r.b.spoiled], [2, 0, 1, 1]);
  assert.match(cardText({card: 0, step: 1}), /^✓ \w[\w ]*  > /);
});
test("pay: $3 a card done, $1 off a card spoiled, $0 to $20; leaving early pays nothing", () => {
  assert.equal(benchPay({done: 4, spoiled: 2}, "done").pay, 10);
  assert.deepEqual(benchPay({done: 4, spoiled: 2}, "done").lines, ["Cards done: 4", "Cards spoiled: 2", "Paid: $10"]);
  assert.equal(benchPay({done: 9, spoiled: 0}, "done").pay, 20);
  assert.equal(benchPay({done: 0, spoiled: 3}, "done").pay, 0);
  assert.equal(benchPay({done: 4, spoiled: 0}, "left").pay, 0); assert.equal(benchPay({done: 4, spoiled: 0}, "left").note, "Lab: left early");
  assert.equal(benchPay({done: 4, spoiled: 2}, "done").note, "Lab 4 done, 2 spoiled");
});
