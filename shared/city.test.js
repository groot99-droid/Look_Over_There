import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {DAY_S, START_H, hourAt, dayAt, secondsAt, phaseAt, storesOpen, dangerous, fmtClock, skyAt, DOORS, BUILDINGS, buildingBox, streetDoc, BUS_STREET} from "./city.js";

test("a game day is 15 real minutes and starts at 08:00", () => {
  assert.equal(DAY_S, 900); assert.equal(hourAt(0), START_H); assert.equal(fmtClock(hourAt(0)), "08:00");
  assert.equal(hourAt(DAY_S / 2), 20); assert.equal(hourAt(DAY_S), 8); assert.equal(dayAt(0), 1); assert.equal(dayAt(599), 1); assert.equal(dayAt(600), 2);   // the calendar day turns at midnight, 10 minutes in
  assert.ok(Math.abs(secondsAt(20) - 450) < 1e-9);
});
test("stores open at 08:00, close at 20:00; 20:00 to midnight is the grace period, then danger until 06:00", () => {
  assert.equal(storesOpen(7.99), false); assert.equal(storesOpen(8), true); assert.equal(storesOpen(19.99), true); assert.equal(storesOpen(20), false); assert.equal(storesOpen(2), false);
  assert.equal(phaseAt(12), "day"); assert.equal(phaseAt(22), "evening"); assert.equal(phaseAt(3), "night");
  assert.equal(dangerous(22), false); assert.equal(dangerous(0), true); assert.equal(dangerous(5.9), true); assert.equal(dangerous(6), false);
});
test("the sky is dark at night and bright at noon", () => {
  assert.ok(skyAt(12).light > skyAt(2).light * 5); assert.equal(skyAt(2).night, true); assert.equal(skyAt(12).night, false);
  assert.ok(skyAt(24).bg === skyAt(0).bg, "the day wraps cleanly");
});
test("every shop door has a sidewalk to stand on and no building overlaps another", () => {
  assert.ok(DOORS.length >= 8);
  for (const s of ["w", "e"]) { const bs = BUILDINGS.filter(b => b.side === s).map(buildingBox).sort((a, b) => a.min[2] - b.min[2]); for (let i = 1; i < bs.length; i++) assert.ok(bs[i].min[2] >= bs[i - 1].max[2], "overlap on side " + s); }
  assert.ok(BUILDINGS.find(b => b.id === "w666").door.label === "666 HALLAM ROW");
  assert.ok(BUS_STREET.arrive[0] > -5 && BUS_STREET.arrive[0] < 8);
});
test("world/street.json is what shared/city.js makes (run node tools/make_street.mjs)", () => {
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/street.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(streetDoc())));
});
