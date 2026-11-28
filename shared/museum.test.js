import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {MUSEUM, MUSEUM_FRONT, MOVE_S, MAX_OFF, FIX_REACH, GUARD, shiftEnds, newExhibits, exhibitAt, stepExhibits, setBack, homeCount, guardPay, museumDoc} from "./museum.js";
import {DOORS, DAY_S, hourAt, secondsAt} from "./city.js";
import {STUB_SHIFTS} from "./pay.js";
import {REGISTRY} from "./registry.js";

test("world/galleries.json is what shared/museum.js makes, and the links match", () => {
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/galleries.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(museumDoc())));
  const into = REGISTRY.linkFrom("street", "e108"), out = REGISTRY.linkFrom("galleries", "front_door");
  assert.ok(into && out && into.soloOnly && out.soloOnly);
  assert.deepEqual(into.requires, ["job_museum"]);
  assert.deepEqual(into.to.arrive, MUSEUM.arrive); assert.deepEqual(into.to.face, MUSEUM.face);
  assert.deepEqual(out.to.arrive, MUSEUM_FRONT.arrive); assert.deepEqual(out.to.face, MUSEUM_FRONT.face);
  const door = DOORS.find(d => d.id === "e108");
  assert.ok(Math.hypot(door.x - MUSEUM_FRONT.arrive[0], door.z - MUSEUM_FRONT.arrive[2]) < door.reach);
});
test("the hall: six plinths, the door by the arrival, every statue's path inside the hall and clear of the plinths", () => {
  const [hx, hz] = MUSEUM.half;
  assert.equal(MUSEUM.homes.length, 6); assert.equal(MUSEUM.names.length, 6);
  assert.ok(Math.hypot(MUSEUM.arrive[0] - MUSEUM.door.at[0], MUSEUM.arrive[2] - MUSEUM.door.at[1]) < MUSEUM.door.reach);
  MUSEUM.homes.forEach((h, i) => {
    for (let off = 1; off <= MAX_OFF; off++) {
      const [x, z] = exhibitAt(i, off);
      assert.ok(Math.abs(x) < hx - 0.5 && Math.abs(z - MUSEUM.cz) < hz - 0.5, `inside: ${i} ${off}`);
      for (const [px, pz] of MUSEUM.homes) assert.ok(Math.max(Math.abs(x - px), Math.abs(z - pz)) > MUSEUM.plinth + 0.2, `statue ${i} at ${off} clear of a plinth`);
    }
    assert.deepEqual(exhibitAt(i, 0), h);
  });
});
test("the shift keeps the stub's hours: 3, from 20:00 or 21:00", () => {
  assert.equal(GUARD.hours, STUB_SHIFTS.museum.hours);
  assert.ok(Math.abs(hourAt(shiftEnds(secondsAt(20.5, 2))) - 23.5) < 1e-9);
  assert.ok(Math.abs(shiftEnds(0) - 3 / 24 * DAY_S) < 1e-9);
});
test("a watched statue never moves; an unwatched one steps off its plinth when its clock runs out, three steps at most", () => {
  let ex = newExhibits();
  assert.ok(ex.every(e => e.off === 0));
  assert.ok(new Set(ex.map(e => e.clock)).size === 6, "staggered");
  const all = Array(6).fill(true), none = Array(6).fill(false);
  for (let k = 0; k < 100; k++) ex = stepExhibits(ex, 1, all);
  assert.ok(ex.every(e => e.off === 0), "watched for 100 s: nothing moved");
  ex = stepExhibits(newExhibits(), MOVE_S / 6 + 0.01, none);
  assert.equal(ex[0].off, 1); assert.ok(ex.slice(1).every(e => e.off === 0), "the first statue moves first");
  for (let k = 0; k < 200; k++) ex = stepExhibits(ex, 0.5, none);
  assert.ok(ex.every(e => e.off === MAX_OFF), "never past three steps");
  const one = Array(6).fill(false); one[2] = true;
  let ex2 = newExhibits(); for (let k = 0; k < 60; k++) ex2 = stepExhibits(ex2, 0.5, one);
  assert.equal(ex2[2].off, 0, "the one you watch stays home"); assert.ok(ex2[0].off > 0);
});
test("F sets back the nearest moved statue within reach, and its clock starts again", () => {
  let ex = newExhibits().map((e, i) => i === 3 ? {off: 2, clock: 1} : e);
  const [x, z] = exhibitAt(3, 2);
  assert.equal(setBack(ex, x + FIX_REACH + 0.1, z).fixed, -1, "out of reach");
  const r = setBack(ex, x + 0.5, z);
  assert.equal(r.fixed, 3); assert.equal(r.ex[3].off, 0); assert.equal(r.ex[3].clock, MOVE_S);
  assert.equal(setBack(r.ex, x, z).fixed, -1, "nothing left to set back");
});
test("pay: $2 a statue home at the end, $1 a statue set back (up to $8); leaving early pays nothing", () => {
  const home = newExhibits(), two = home.map((e, i) => i < 2 ? {off: 1, clock: 1} : e);
  assert.equal(guardPay(home, 0, "done").pay, 12);
  assert.equal(guardPay(home, 5, "done").pay, 17);
  assert.equal(guardPay(home, 30, "done").pay, 20, "the fix pay is capped");
  assert.equal(guardPay(two, 1, "done").pay, 9);
  assert.equal(guardPay(home, 5, "left").pay, 0);
  assert.equal(homeCount(two), 4);
  assert.deepEqual(guardPay(two, 3, "done").lines, ["Statues on their plinths: 4 of 6 ($8)", "Set back during the night: 3 (+$3)", "Paid: $11"]);
  assert.equal(guardPay(two, 3, "done").note, "Museum 4/6");
});
