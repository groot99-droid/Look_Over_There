import test from "node:test";
import assert from "node:assert/strict";
import {BINS, BIN_REACH, TRASH, routeEnds, nearBin, trashPay} from "./trash.js";
import {DOORS, LAMP_ZS, BUS_STREET, ROAD, DAY_S, secondsAt, hourAt} from "./city.js";
import {PEDESTRIANS} from "./anomalies.js";

test("eight bins at the kerb on both sides, clear of doors, lamp posts, the bus stop and the pedestrians", () => {
  assert.equal(BINS.length, 8);
  assert.equal(new Set(BINS.map(([x]) => Math.sign(x))).size, 2);
  for (const [x, z] of BINS) {
    assert.ok(Math.abs(x) > ROAD.x1 && Math.abs(x) < ROAD.x1 + 1, `at the kerb: ${x}`);
    for (const d of DOORS) assert.ok(Math.hypot(d.x - x, d.z - z) > d.reach + BIN_REACH, `clear of ${d.id}'s door at ${z}`);
    for (const lz of LAMP_ZS) assert.ok(Math.hypot(Math.sign(x) * 5.5 - x, lz - z) > 1.5, `clear of the lamp at ${lz}`);
    assert.ok(Math.hypot(BUS_STREET.at[0] - x, BUS_STREET.at[1] - z) > BUS_STREET.radius + BIN_REACH, "clear of the bus stop");
    for (const [px, pz] of PEDESTRIANS) assert.ok(Math.hypot(px - x, pz - z) > 2, `clear of the pedestrian at ${pz}`);
  }
  for (let i = 0; i < BINS.length; i++) for (let j = i + 1; j < BINS.length; j++) assert.ok(Math.hypot(BINS[i][0] - BINS[j][0], BINS[i][1] - BINS[j][1]) > 2 * BIN_REACH, `${i} and ${j} apart`);
});
test("the shift lasts the stub's 4 hours", () => {
  assert.equal(TRASH.hours, 4);
  const t0 = secondsAt(10, 2);
  assert.ok(Math.abs(hourAt(routeEnds(t0)) - 14) < 1e-9);
  assert.ok(Math.abs(routeEnds(0) - 4 / 24 * DAY_S) < 1e-9);
});
test("F empties the nearest bin you have not emptied yet, within reach", () => {
  const [x, z] = BINS[3];
  assert.equal(nearBin(x + 0.5, z, []), 3);
  assert.equal(nearBin(x, z + BIN_REACH + 0.1, []), -1, "out of reach");
  assert.equal(nearBin(x, z, [3]), -1, "already emptied");
  assert.equal(nearBin(0, -200, []), -1);
});
test("pay: $2 a bin, $4 more for the whole route clocked out on time", () => {
  assert.equal(trashPay(0, "done").pay, 0);
  assert.equal(trashPay(5, "done").pay, 10);
  assert.equal(trashPay(8, "done").pay, 20);
  assert.equal(trashPay(8, "time").pay, 16, "no bonus when time runs out");
  assert.equal(trashPay(8, "left").pay, 16, "no bonus when you leave the route");
  assert.equal(trashPay(99, "done").pay, 20, "never more than the route");
  assert.equal(trashPay(-2, "done").pay, 0);
  assert.deepEqual(trashPay(8, "done").lines, ["Bins emptied: 8 of 8", "$2 a bin: $16", "Whole route, clocked out on time: +$4", "Paid: $20"]);
  assert.equal(trashPay(3, "time").note, "Trash route 3/8");
  assert.ok(trashPay(3, "time").lines.includes("Time ran out before you clocked out."));
});
