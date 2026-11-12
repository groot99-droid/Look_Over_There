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
  assert.equal(REPORTS.length, 7);                                    // slice 21 added the watchers
  assert.deepEqual([...REAL_IDS].sort(), ["peds", "sign", "watchers", "window"]);
  assert.equal(new Set(REPORTS.map(r => r.id)).size, 7);
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

test("routines (slice 18): each pedestrian's whole beat is on its sidewalk, clear of doors, lamp posts, the bus stop and the trash bins", async () => {
  const {PED_ROUTE, pedAt} = await import("./anomalies.js");
  const {BINS} = await import("./trash.js");
  PEDESTRIANS.forEach((_, i) => {
    for (let s = -PED_ROUTE; s <= PED_ROUTE + 1e-9; s += 0.25) {
      const [x, z] = pedAt(i, s);
      assert.ok(Math.abs(x) > ROAD.x1 && Math.abs(x) < ROAD.x1 + WALK && z > ROAD.z0 && z < ROAD.z1, `on the sidewalk: ${i} ${s}`);
      for (const d of DOORS) assert.ok(Math.hypot(d.x - x, d.z - z) > d.reach, `pedestrian ${i} at ${s} clear of ${d.id}'s door`);
      for (const lz of LAMP_ZS) assert.ok(Math.hypot(Math.sign(x) * 5.5 - x, lz - z) > 0.6, `pedestrian ${i} at ${s} clear of the lamp at ${lz}`);
      assert.ok(Math.hypot(BUS_STREET.at[0] - x, BUS_STREET.at[1] - z) > BUS_STREET.radius, "clear of the bus stop");
      for (const [bx, bz] of BINS) assert.ok(Math.hypot(bx - x, bz - z) > 0.8, `pedestrian ${i} at ${s} clear of the bin at ${bz}`);
    }
  });
});
test("routines: unwatched pedestrians walk their beat and turn at its ends; a watched one stops where it is", async () => {
  const {PED_ROUTE, PED_SPEED, newPeds, stepPeds} = await import("./anomalies.js");
  let ps = newPeds(); const none = ps.map(() => false), all = ps.map(() => true);
  assert.ok(ps.every(p => p.s === 0));
  for (let k = 0; k < 50; k++) ps = stepPeds(ps, 0.5, all);
  assert.ok(ps.every(p => p.s === 0), "watched: nobody moved");
  ps = stepPeds(newPeds(), 1, none);
  assert.ok(ps.every(p => Math.abs(Math.abs(p.s) - PED_SPEED) < 1e-9), "one second unwatched: each walked 1.2 m");
  let lo = 0, hi = 0;
  for (let k = 0; k < 400; k++) { ps = stepPeds(ps, 0.1, none); for (const p of ps) { lo = Math.min(lo, p.s); hi = Math.max(hi, p.s); assert.ok(Math.abs(p.s) <= PED_ROUTE + 1e-9); } }
  assert.ok(lo < -PED_ROUTE + 0.2 && hi > PED_ROUTE - 0.2, "they reach both ends of the beat and come back");
  const one = ps.map((_, i) => i === 2), before = ps[2].s; ps = stepPeds(ps, 3, one);
  assert.equal(ps[2].s, before, "the one you watch stays put"); assert.notEqual(ps[0].s, stepPeds(ps, 0, one)[0].s + 1, "others go on");
  const big = stepPeds(newPeds(), 100, none); assert.ok(big.every(p => Math.abs(p.s) <= PED_ROUTE), "even a long step stays on the beat");
});

test("watchers (slice 21): each stands just inside one of the windows the street draws, above the ground floor, on three different buildings", async () => {
  const {WATCHERS, watcherAt} = await import("./anomalies.js");
  const {windowSlots} = await import("./city.js");
  assert.equal(WATCHERS.length, 3); assert.equal(new Set(WATCHERS.map(w => w.building)).size, 3);
  for (const w of WATCHERS) {
    const b = BUILDINGS.find(x => x.id === w.building), s = windowSlots(b).find(x => x.f === w.f && x.k === w.k), p = watcherAt(w);
    assert.ok(s && p, `a drawn window for ${w.building}`); assert.ok(w.f >= 2, "above the ground floor");
    assert.ok(Math.abs(p.z - s.z) < 1e-9 && Math.abs(p.y - s.y) < 1e-9);
    const bx = buildingBox(b); assert.ok(p.x > bx.min[0] && p.x < bx.max[0], "inside the building, behind the glass");
  }
});
test("watchers: out only at night, and they turn to face you", async () => {
  const {watchersOut, watcherYaw} = await import("./anomalies.js");
  assert.ok(watchersOut(22) && watchersOut(2) && !watchersOut(12));
  const yaw = watcherYaw(0, 0, 3, 4), fx = -Math.sin(yaw), fz = -Math.cos(yaw);                      // the page's facing for a yaw is (-sin, -cos)
  assert.ok(Math.abs(fx - 0.6) < 1e-9 && Math.abs(fz - 0.8) < 1e-9, "faces the point");
});
test("the street's windows: windowSlots never puts one beside a ground-floor door", async () => {
  const {windowSlots} = await import("./city.js");
  for (const b of BUILDINGS) for (const s of windowSlots(b)) if (b.door && s.f === 1) assert.ok(Math.abs(s.z - b.door.z) >= 2.4, `${b.id} ${s.z}`);
  assert.ok(windowSlots(BUILDINGS.find(b => b.id === "tower")).length > 20);
});
