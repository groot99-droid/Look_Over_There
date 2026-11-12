import test from "node:test";
import assert from "node:assert/strict";
import {SIGN, signText, passedSign, PEDESTRIANS, PED_FACE, pedsOut, GHOST_WINDOW, ghostLit} from "./anomalies.js";
import {BUILDINGS, DOORS, LAMP_ZS, BUS_STREET, ROAD, WALK, buildingBox, FRONT} from "./city.js";

test("the sign reads PHARMACY until you pass it", () => {
  assert.equal(signText(0), "PHARMACY");
  assert.equal(signText(-3), "PHARMACY");
});
test("each pass changes exactly one letter, always to another capital letter", () => {
  let prev = signText(0);
  for (let i = 1; i <= 300; i++) {
    const s = signText(i);
    assert.equal(s.length, SIGN.text.length);
    assert.match(s, /^[A-Z]+$/);
    let diff = 0; for (let k = 0; k < s.length; k++) if (s[k] !== prev[k]) diff++;
    assert.equal(diff, 1, `pass ${i}: ${prev} -> ${s}`);
    prev = s;
  }
});
test("the same number of passes always gives the same text", () => {
  for (const n of [1, 2, 7, 40]) assert.equal(signText(n), signText(n));
  assert.notEqual(signText(1), signText(2));
});
test("passing the sign means crossing its line on the street, either way", () => {
  assert.ok(passedSign(SIGN.z + 0.1, SIGN.z - 0.1, 0));
  assert.ok(passedSign(SIGN.z - 0.1, SIGN.z + 0.1, -6));
  assert.ok(!passedSign(SIGN.z + 1, SIGN.z + 0.2, 0), "not yet at it");
  assert.ok(!passedSign(SIGN.z + 0.5, SIGN.z, 0), "touching the line is not passing it");
  assert.ok(!passedSign(SIGN.z + 0.1, SIGN.z - 0.1, FRONT + 1), "off the street");
});
test("the sign hangs on a building with no door", () => {
  const b = BUILDINGS.find(b => b.side === SIGN.side && Math.min(b.z0, b.z1) < SIGN.z && Math.max(b.z0, b.z1) > SIGN.z);
  assert.ok(b, "a building behind the sign"); assert.ok(!b.door, b.id);
  assert.ok(SIGN.y < b.h);
});
test("the pedestrians stand on the sidewalks, clear of doors, lamp posts and the bus stop, and all face up the street", () => {
  for (const [x, z] of PEDESTRIANS) {
    assert.ok(Math.abs(x) > ROAD.x1 && Math.abs(x) < ROAD.x1 + WALK, `on a sidewalk: ${x}`);
    for (const d of DOORS) assert.ok(Math.hypot(d.x - x, d.z - z) > d.reach + 0.5, `clear of ${d.id}`);
    for (const lz of LAMP_ZS) assert.ok(Math.hypot(Math.sign(x) * 5.5 - x, lz - z) > 0.8, `clear of the lamp at ${lz}`);
    assert.ok(Math.hypot(BUS_STREET.at[0] - x, BUS_STREET.at[1] - z) > BUS_STREET.radius + 1, "clear of the bus stop");
  }
  assert.deepEqual(PED_FACE, [0, -1]);
  assert.ok(new Set(PEDESTRIANS.map(([x]) => Math.sign(x))).size === 2, "on both sides of the street");
});
test("the pedestrians are out while the stores are open, and gone at night", () => {
  assert.ok(pedsOut(8) && pedsOut(12) && pedsOut(19.9));
  assert.ok(!pedsOut(7.9) && !pedsOut(20) && !pedsOut(23) && !pedsOut(2));
});
test("the window is lit only at night, and there is no building where it hangs", () => {
  assert.ok(ghostLit(22) && ghostLit(0) && ghostLit(5));
  assert.ok(!ghostLit(8) && !ghostLit(13) && !ghostLit(19));
  const [x, y, z] = GHOST_WINDOW.at;
  for (const b of BUILDINGS) { const bx = buildingBox(b); assert.ok(!(x >= bx.min[0] - 2 && x <= bx.max[0] + 2 && z >= bx.min[2] - 2 && z <= bx.max[2] + 2), `not on ${b.id}`); }
  assert.ok(y > 6, "high up");
});

test("reports (slice 15): six on the list, three real (the slice 8 anomalies) and three not", async () => {
  const {REPORTS, REAL_IDS} = await import("./anomalies.js");
  assert.equal(REPORTS.length, 6);
  assert.deepEqual([...REAL_IDS].sort(), ["peds", "sign", "window"]);
  assert.equal(new Set(REPORTS.map(r => r.id)).size, 6);
});
test("spotting: only the real anomalies, and only once", async () => {
  const {newSightings, spot} = await import("./anomalies.js");
  let s = spot(newSightings(), "sign"); assert.deepEqual(s.spotted, {sign: true});
  assert.equal(spot(s, "sign"), s, "spotting it again changes nothing");
  assert.deepEqual(spot(s, "lamp").spotted, {sign: true}, "there is nothing to spot for an unreal one");
});
test("a true report of a spotted anomaly pays $5 once; anything else is false and costs $2, never below $0", async () => {
  const {newSightings, spot, fileReport, REPORT} = await import("./anomalies.js");
  const s = spot(newSightings(), "window");
  let r = fileReport(s, "window", 10);
  assert.ok(r.ok); assert.equal(r.delta, REPORT.reward); assert.deepEqual(r.s.reported, {window: true});
  const again = fileReport(r.s, "window", 10); assert.ok(!again.ok); assert.equal(again.delta, 0, "no second reward, no cost");
  r = fileReport(s, "door", 10); assert.ok(!r.ok); assert.equal(r.delta, -REPORT.falseCost); assert.match(r.msg, /nothing like that/); assert.deepEqual(r.s.reported, {}, "a false report is not filed");
  r = fileReport(s, "sign", 10); assert.ok(!r.ok); assert.equal(r.delta, -2); assert.match(r.msg, /not seen that yourself/);
  assert.equal(fileReport(s, "bus", 1).delta, -1); assert.equal(fileReport(s, "bus", 0).delta, 0);
  assert.ok(!fileReport(s, "ufo", 10).ok);
});
