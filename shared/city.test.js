import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {GROCERY, GROCERY_FRONT, groceryDoc} from "./city.js";
import {newNeeds, FOODS} from "./needs.js";
import {DAY_S, START_H, hourAt, dayAt, secondsAt, phaseAt, storesOpen, dangerous, fmtClock, skyAt, DOORS, BUILDINGS, buildingBox, streetDoc, BUS_STREET, APARTMENT, TOWER_FRONT, CITY_SCENES, apartmentDoc, computerPages, JOBS, JOB_FRONT, inView, stalkerSpawn, stalkerStep, STALKER, nextMorning, ROAD} from "./city.js";
import {REGISTRY} from "./registry.js";
import {newApplications, begin, finish} from "./application.js";
import {requirementsMet} from "./manifest.js";

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

test("world/apartment.json is what shared/city.js makes", () => {
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/apartment.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(apartmentDoc())));
});
test("the apartment links match the layout, and the clock runs in both City scenes", () => {
  const into = REGISTRY.linkFrom("street", "tower"), out = REGISTRY.linkFrom("apartment", "front_door");
  assert.ok(into && into.status === "built" && into.soloOnly && out && out.status === "built" && out.soloOnly);
  assert.deepEqual(into.to.arrive, APARTMENT.arrive); assert.deepEqual(into.to.face, APARTMENT.face);
  assert.deepEqual(out.to.arrive, TOWER_FRONT.arrive); assert.deepEqual(out.to.face, TOWER_FRONT.face);
  assert.deepEqual(CITY_SCENES, ["street", "apartment", "main_floor", "entrance", "galleries", "factory_floor", "laboratory"]);
  const [hx, hz] = APARTMENT.half, inside = ([x, z]) => Math.abs(x) < hx && Math.abs(z) < hz, hit = ([x, z], b) => x > b.min[0] && x < b.max[0] && z > b.min[2] && z < b.max[2];
  for (const p of [APARTMENT.arrive.filter((_, i) => i !== 1), APARTMENT.door.at, APARTMENT.computer.at]) { assert.ok(inside(p), "inside the room " + p); assert.ok(!hit(p, APARTMENT.bed) && !hit(p, APARTMENT.desk), "clear of furniture " + p); }
});
test("the computer's pages say the day, the store hours and the five jobs", () => {
  assert.equal(JOBS.length, 5);
  const open = computerPages({hour: 12.5, day: 1, clock: "12:30", open: true}), shut = computerPages({hour: 22, day: 1, clock: "22:00", open: false});
  assert.match(open.news.lines[1], /open for another 7 h 30 min/); assert.match(shut.news.lines[1], /closed for the night/);
  assert.ok(open.jobs.lines.some(l => /666 HALLAM ROW: The Intern/.test(l)) && open.jobs.lines.every(l => !/not hiring yet/.test(l)));
  assert.deepEqual(Object.keys(open), ["mail", "news", "jobs", "map", "bank", "report", "system"]);
});

test("you see what is in front of you: the cone is 38 degrees either side of where you face", () => {
  assert.ok(inView(0, 0, 0, 0, -10), "yaw 0 faces -z"); assert.ok(!inView(0, 0, 0, 0, 10), "behind you"); assert.ok(inView(0, 0, Math.PI, 0, 10), "yaw PI faces +z");
  assert.ok(inView(0, 0, 0, 5, -10) && !inView(0, 0, 0, 10, -5), "inside and outside the cone");
});
test("the stalker appears out of view behind you, on the road, never close", () => {
  const at = stalkerSpawn(0, -60, Math.PI);                       // facing +z: behind is -z
  assert.ok(at && at.z < -60 && Math.abs(at.x) <= 4 && Math.hypot(at.x, at.z + 60) >= STALKER.minSpawn && !inView(0, -60, Math.PI, at.x, at.z));
  const edge = stalkerSpawn(0, ROAD.z0 + 5, 0);                   // at the north end facing north: behind is south, room enough
  assert.ok(edge && edge.z > ROAD.z0 + 5);
  assert.equal(stalkerSpawn(0, 0, 0), null, "at the south end facing north there is no room behind you and ahead is in view: no spawn yet");
  const side = stalkerSpawn(0, 0, Math.PI); assert.ok(side && side.z < 0 && !inView(0, 0, Math.PI, side.x, side.z), "turn round and it can appear up the street, behind your new back");
});
test("it waits, appears, freezes when seen, creeps when not, and catches you", () => {
  const base = {px: 0, pz: -60, yaw: Math.PI, seen: false, danger: true};
  let s = {active: false, x: 0, z: 0, wait: STALKER.firstWait};
  for (let i = 0; i < 100 && !s.active; i++) s = stalkerStep(s, 0.1, base);
  assert.ok(s.active, "it appeared after its wait (about 6 s)");
  const z0 = s.z; let t = stalkerStep(s, 1, {...base, seen: true}); assert.equal(t.z, z0, "seen: it does not move"); assert.equal(t.caught, false);
  t = stalkerStep(s, 1, base); assert.ok(Math.abs(Math.abs(t.z - z0) - STALKER.speed) < 1e-9, "unseen: it moves 5.5 m in a second");
  assert.ok(STALKER.speed > 4.0 && STALKER.speed < 7.5, "faster than a walk, slower than a run");
  let c = {active: true, x: 0, z: -60 - 3, wait: 0}; let caught = false;
  for (let i = 0; i < 20 && !caught; i++) { c = stalkerStep(c, 0.1, base); caught = c.caught; }
  assert.ok(caught, "within 1.5 m it has you");
  const gone = stalkerStep(c, 0.1, {...base, danger: false}); assert.equal(gone.active, false); assert.equal(gone.wait, STALKER.firstWait, "by day or indoors it is gone and its wait starts again");
});
test("sleeping or a blackout lands on 06:00 of the next morning", () => {
  assert.equal(hourAt(nextMorning(secondsAt(22))), 6); assert.equal(dayAt(nextMorning(secondsAt(22))), 2);          // 22:00 day 1 -> 06:00 day 2
  assert.equal(hourAt(nextMorning(secondsAt(2, 2))), 6); assert.equal(dayAt(nextMorning(secondsAt(2, 2))), 2);      // 02:00 day 2 -> 06:00 the same day
  assert.ok(nextMorning(secondsAt(12)) > secondsAt(12));
});

test("every job is hiring (slice 6), the job search says so, and the mail follows your application", () => {
  assert.deepEqual(Object.fromEntries(JOBS.map(j => [j.id, j.quiz])), {w41: "trash", w214: "lab", w666: "intern", e108: "museum", e330: "factory"});
  const st = {hour: 12, day: 1, clock: "12:00", open: true}, none = computerPages(st, newApplications());
  assert.ok(none.jobs.lines.some(l => /666 HALLAM ROW: The Intern \(hiring: apply below\)/.test(l)) && none.jobs.lines.filter(l => /hiring: apply below/.test(l)).length === 5);
  assert.match(none.mail.lines[0], /No new messages/);
  const rej = finish(begin(newApplications(), "intern", 1), "intern", {pass: false}, 1);
  assert.ok(computerPages(st, rej).jobs.lines.some(l => /rejected: try again tomorrow/.test(l))); assert.match(computerPages(st, rej).mail.lines[0], /REJECTED/);
  assert.ok(computerPages({...st, day: 2}, rej).jobs.lines.some(l => /hiring: apply below/.test(l)));
  const acc = finish(begin(newApplications(), "intern", 1), "intern", {pass: true}, 1);
  assert.ok(computerPages(st, acc).jobs.lines.some(l => /\(ACCEPTED\)/.test(l))); assert.match(computerPages(st, acc).mail.lines[0], /ACCEPTED/);
});
test("the shift link needs job_intern, starts at 666 Hallam Row, and returns to its front door", () => {
  const l = REGISTRY.linkFrom("street", "w666"); assert.ok(l && l.status === "built" && l.soloOnly && l.to.area === "intern");
  assert.equal(requirementsMet(l, []).ok, false); assert.equal(requirementsMet(l, ["original_complete"]).ok, false); assert.equal(requirementsMet(l, ["job_intern"]).ok, true);
  const d = DOORS.find(x => x.id === "w666"); assert.deepEqual(l.returnTo.arrive, JOB_FRONT.arrive); assert.deepEqual(l.returnTo.face, JOB_FRONT.face);
  assert.ok(Math.abs(JOB_FRONT.arrive[2] - d.z) < 1e-9 && Math.abs(JOB_FRONT.arrive[0] - d.x) < 2, "just outside the door");
});

test("world/main_floor.json is what shared/city.js makes", () => {
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/main_floor.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(groceryDoc())));
});
test("the grocery: links match the layout, one shelf per food, and every spot you stand on is clear and inside", () => {
  const into = REGISTRY.linkFrom("street", "grocery"), out = REGISTRY.linkFrom("main_floor", "front_door");
  assert.ok(into && into.status === "built" && into.soloOnly && out && out.status === "built" && out.soloOnly);
  assert.deepEqual(into.to.arrive, GROCERY.arrive); assert.deepEqual(into.to.face, GROCERY.face);
  assert.deepEqual(out.to.arrive, GROCERY_FRONT.arrive); assert.deepEqual(out.to.face, GROCERY_FRONT.face);
  assert.deepEqual(GROCERY.shelves.map(x => x.food), FOODS.map(f => f.id));
  const [hx, hz] = GROCERY.half, solid = [...GROCERY.shelves, GROCERY.checkout, GROCERY.cart], hit = ([x, z], b) => x > b.min[0] - 0.3 && x < b.max[0] + 0.3 && z > b.min[2] - 0.3 && z < b.max[2] + 0.3;
  for (const p of [[GROCERY.arrive[0], GROCERY.arrive[2]], GROCERY.door.at, GROCERY.cart.at, GROCERY.checkout.at, ...GROCERY.shelves.map(x => x.at)]) {
    assert.ok(Math.abs(p[0]) < hx - 0.3 && Math.abs(p[1]) < hz - 0.3, "inside " + p);
    assert.ok(!solid.some(b => hit(p, b)), "clear of furniture " + p);
  }
  const fr = APARTMENT.fridge.at, bed = APARTMENT.bed, desk = APARTMENT.desk, f = APARTMENT.fridge, inF = ([x, z], b) => x > b.min[0] && x < b.max[0] && z > b.min[2] && z < b.max[2];
  assert.ok(!inF(fr, bed) && !inF(fr, desk) && !inF(fr, f), "the fridge spot is clear");
});
test("the bank page shows your money, the last pay and the fridge", () => {
  const st = {hour: 12, day: 1, clock: "12:00", open: true};
  assert.match(computerPages(st, null, newNeeds()).bank.lines.join("\n"), /Balance: \$20[\s\S]*No pay yet[\s\S]*Nothing\./);
  assert.match(computerPages(st, null, {...newNeeds(), money: 31, lastPay: 10, lastNote: "PENDING", pantry: {soup: 2}}).bank.lines.join("\n"), /Balance: \$31[\s\S]*\+\$10 \(PENDING\)[\s\S]*Canned soup: 2/);
});

test("the bank and the system page say when the City was last saved (slice 9)", async () => {
  const {computerPages, savedLine, secondsAt} = await import("./city.js");
  const {newNeeds} = await import("./needs.js");
  const st = {hour: 10, clock: "10:00", day: 2, open: true, phase: "day"};
  assert.equal(savedLine(null), "Not saved yet. The bed in your apartment saves.");
  assert.equal(savedLine(secondsAt(14.5, 3)), "Last saved: Day 3, 14:30.");
  const p = computerPages(st, null, newNeeds(), secondsAt(6, 2));
  assert.ok(p.bank.lines.includes("Last saved: Day 2, 06:00."), p.bank.lines.join("|"));
  assert.ok(p.system.lines.includes("Last saved: Day 2, 06:00."));
  assert.match(p.system.lines.join(" "), /NEW GAME/);
  const none = computerPages(st, null, newNeeds(), null);
  assert.ok(none.bank.lines.includes("Not saved yet. The bed in your apartment saves."));
  const old = computerPages(st, null, newNeeds());
  assert.ok(!old.bank.lines.some(l => /saved/i.test(l)), "callers that do not pass a save time get no line");
});

test("the stalker waits outside the tower door, 14 m along the street on the side it was (slice 10)", async () => {
  const {stalkerWaitAt, STALKER_WAIT, TOWER_FRONT, ROAD, BUILDINGS, buildingBox} = await import("./city.js");
  const [ax, , az] = TOWER_FRONT.arrive;
  for (const [sx, sz] of [[0, -40], [3, -100], [-2, 5], [-6, -19.5], [9, -18]]) {
    const w = stalkerWaitAt(sx, sz);
    assert.ok(Math.hypot(w.x - ax, w.z - az) >= STALKER_WAIT - 1e-9, `${sx},${sz} -> ${JSON.stringify(w)}`);
    assert.ok(Math.abs(w.x) <= 4 && w.z >= ROAD.z0 && w.z <= ROAD.z1, "on the road");
    for (const b of BUILDINGS) { const bx = buildingBox(b); assert.ok(!(w.x > bx.min[0] && w.x < bx.max[0] && w.z > bx.min[2] && w.z < bx.max[2]), b.id); }
  }
  assert.ok(stalkerWaitAt(0, -60).z < az && stalkerWaitAt(0, 0).z > az, "it stays on the side of the door it came from");
});
test("only a stalker that is out at night follows, and only between the street and the apartment (slice 10)", async () => {
  const {carryStalker, STALKER} = await import("./city.js");
  const out = {active: true, x: 1, z: -50, wait: 0};
  const inside = carryStalker(out, 1.5, "apartment");
  assert.ok(inside.active && inside.waited && inside.wait === 0);
  const back = carryStalker(inside, 2, "street");
  assert.ok(back.active && back.waited && back.x === inside.x && back.z === inside.z, "it is where it waited");
  for (const [s, h, to] of [[out, 7, "apartment"], [out, 12, "street"], [{...out, active: false, wait: 2}, 1, "apartment"], [out, 1, "parking_lot"], [out, 1, "main_floor"], [null, 1, "street"]]) {
    const r = carryStalker(s, h, to);
    assert.deepEqual(r, {active: false, x: 0, z: 0, wait: STALKER.firstWait}, JSON.stringify([s, h, to]));
  }
});

test("the mall (slice 13): world/entrance.json is what shared/city.js makes, and the links match the layout", async () => {
  const {MALL, MALL_FRONT, mallDoc, DOORS} = await import("./city.js");
  assert.deepEqual(JSON.parse(fs.readFileSync(new URL("../world/entrance.json", import.meta.url), "utf8")), JSON.parse(JSON.stringify(mallDoc())));
  const {REGISTRY} = await import("./registry.js");
  const into = REGISTRY.linkFrom("street", "mall"), out = REGISTRY.linkFrom("entrance", "front_door");
  assert.ok(into && out && into.soloOnly && out.soloOnly);
  assert.deepEqual(into.to.arrive, MALL.arrive); assert.deepEqual(into.to.face, MALL.face);
  assert.deepEqual(out.to.arrive, MALL_FRONT.arrive); assert.deepEqual(out.to.face, MALL_FRONT.face);
  const door = DOORS.find(d => d.id === "mall");
  assert.ok(Math.hypot(door.x - MALL_FRONT.arrive[0], door.z - MALL_FRONT.arrive[2]) < door.reach, "you come out at the MALL door");
  const [hx, hz] = MALL.half, solid = [MALL.fountain, ...MALL.benches], hit = ([x, z], b) => x > b.min[0] - 0.3 && x < b.max[0] + 0.3 && z > b.min[2] - 0.3 && z < b.max[2] + 0.3;
  for (const p of [[MALL.arrive[0], MALL.arrive[2]], MALL.door.at, ...MALL.benches.map(b => b.at)]) {
    assert.ok(Math.abs(p[0]) < hx && Math.abs(p[1]) < hz, `inside: ${p}`);
    for (const b of solid) assert.ok(!hit(p, b), `${p} clear of a solid`);
  }
  assert.ok(Math.hypot(MALL.arrive[0] - MALL.door.at[0], MALL.arrive[2] - MALL.door.at[1]) < MALL.door.reach, "you arrive by the door");
});
test("the mall locks from 20:00 to 06:00, and unlocks at the next 06:00", async () => {
  const {mallLocked, mallUnlocks, storesOpen, secondsAt, hourAt, dayAt} = await import("./city.js");
  for (const h of [20, 21.5, 23.9, 0, 3, 5.9]) assert.ok(mallLocked(h), `locked at ${h}`);
  for (const h of [6, 8, 12, 19.9]) assert.ok(!mallLocked(h), `unlocked at ${h}`);
  assert.ok(!storesOpen(7) && !mallLocked(7), "06:00 to 08:00: you can leave but not go in");
  const u = mallUnlocks(secondsAt(20.5, 2)); assert.equal(dayAt(u), 3); assert.ok(Math.abs(hourAt(u) - 6) < 1e-9);
  const v = mallUnlocks(secondsAt(2, 3)); assert.equal(dayAt(v), 3); assert.ok(Math.abs(hourAt(v) - 6) < 1e-9);
});

test("the grocery's camera (slice 19): it sweeps to and fro, sees the door about a third of the time, and nextCam finds a time it does or does not", async () => {
  const {CAMERA, camYaw, camSees, nextCam, GROCERY} = await import("./city.js");
  const [dx, dz] = GROCERY.door.at;
  assert.equal(camYaw(0), 0); assert.ok(Math.abs(camYaw(CAMERA.period / 4) - CAMERA.sweep) < 1e-9);
  let seen = 0; const N = 1200; for (let k = 0; k < N; k++) if (camSees(k * CAMERA.period / N, dx, dz)) seen++;
  assert.ok(seen / N > 0.25 && seen / N < 0.4, String(seen / N));
  assert.ok(Math.abs(CAMERA.at[2]) < GROCERY.half[1] && CAMERA.at[1] < GROCERY.h, "inside the store, under the ceiling");
  const on = nextCam(100, dx, dz, true), off = nextCam(100, dx, dz, false);
  assert.ok(on >= 100 && camSees(on, dx, dz)); assert.ok(off >= 100 && !camSees(off, dx, dz));
  assert.ok(!camSees(0, dx + 30, dz), "out of range");
});
