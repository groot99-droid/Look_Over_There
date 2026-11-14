// Going back in in a room (session 16): the server runs the chambers as floors, starts each chamber's wave once (when the first player steps in), and everyone on the floor
// sees the same monsters. Real sockets against a real server, like floors.test.js; the clock is the test's.
import test from "node:test";
import assert from "node:assert/strict";
import {WebSocket} from "ws";
import {createServer} from "./server.js";
import {REGISTRY} from "../shared/registry.js";
import {FLOORS, mainRegion, cellXZ} from "../shared/world.js";
import {GUN_ROUNDS} from "../shared/loot.js";
import * as PS from "./playerstate.js";

function client(port) {
  const ws = new WebSocket(`ws://localhost:${port}/ws`), inbox = [], waiters = [];
  ws.on("message", d => { const m = JSON.parse(d); inbox.push(m); waiters.splice(0).forEach(w => w()); });
  return {ws, inbox, send: m => ws.send(JSON.stringify(m)), open: new Promise(r => ws.on("open", r)),
    async next(pred, ms = 3000) { const end = Date.now() + ms; for (;;) { const i = inbox.findIndex(pred); if (i >= 0) return inbox.splice(i, 1)[0]; if (Date.now() > end) throw new Error("timed out"); await new Promise(r => { waiters.push(r); setTimeout(r, 50); }); } },
    quiet: async ms => { await new Promise(r => setTimeout(r, ms)); return inbox.splice(0); }};
}
const kind = t => m => m.t === t, sleep = ms => new Promise(r => setTimeout(r, ms));
const MODE = "going_back_in", GBI = REGISTRY.modes[MODE], START = GBI.startChamber, NEXT = REGISTRY.chamber(START).next;
async function join(srv, room, name, mode = MODE) { const c = client(srv.port); await c.open; c.send({t: "join", room, name, mode}); const w = await c.next(kind("welcome")); return Object.assign(c, {id: w.id, welcome: w}); }
const at = (c, scene, x, z, extra = {}) => c.send({t: "s", scene, x, y: FLOORS[scene] + 0.02, z, yaw: 0, crouch: 0, moving: 0, run: 0, carry: 0, dead: 0, imm: 0, ...extra});
const clockOf = () => { let t = 1000; return {now: () => t, adv: s => { t += s; }}; };
// a room of `names`, everyone ready and the round started; nobody is on a floor yet
async function party(srv, code, names) {
  const ps = []; for (const n of names) ps.push(await join(srv, code, n));
  for (const p of ps) p.send({t: "ready", ready: true});
  for (const p of ps) await p.next(kind("start"));
  return {ps, room: srv.rooms.get(`${MODE}:${code}`)};
}
// a walkable spot of a chamber far from the wave's start spots is not needed: the wave is placed away from whoever steps in first
const spotOf = (srv, room, scene, k = 0) => { const f = room.floors[scene]; const cells = mainRegion(f.W); return cellXZ(cells[(k * 977) % cells.length]); };

test("a room can be made and joined with the mode: its key is going_back_in:CODE, it starts in the first chamber, and /rooms lists it", async () => {
  const srv = await createServer({countdownMs: 60});
  const a = await join(srv, "gb1", "Ann"), b = await join(srv, "GB1", "Bob");
  assert.deepEqual([...srv.rooms.keys()], [`${MODE}:GB1`]);
  assert.equal(a.welcome.mode, MODE); assert.equal(a.welcome.start, START); assert.equal(a.welcome.max, GBI.players.max);
  assert.deepEqual(a.welcome.floors, REGISTRY.chambers, "the room's scenes are the chambers");
  assert.equal(a.welcome.finish, null, "the mode has no finish scene yet");
  assert.equal(b.welcome.players.length, 2);
  const o = await join(srv, "GB1", "Olga", "original");
  assert.equal(srv.rooms.size, 2, "the same code in the Original is another party"); assert.equal(o.welcome.start, "B1");
  const r = await (await fetch(`http://localhost:${srv.port}/rooms?mode=${MODE}`)).json();
  assert.deepEqual(r.rooms, [{mode: MODE, code: "GB1", players: 2, max: GBI.players.max, state: "lobby"}]);
  await srv.close();
});

test("ten players in one room: the wave starts once, when the first of them steps in, and all ten are told the same monsters", async () => {
  const srv = await createServer({countdownMs: 60}), ch = REGISTRY.chamber(START);
  const {ps, room} = await party(srv, "TEN", Array.from({length: 10}, (_, i) => "P" + i));
  assert.equal(room.players.size, 10); assert.equal(Object.keys(room.floors).length, 0, "no chamber runs before anyone is in it");
  const eleventh = client(srv.port); await eleventh.open; eleventh.send({t: "join", room: "TEN", name: "Late", mode: MODE}); assert.equal((await eleventh.next(kind("full"))).max, 10);
  at(ps[0], START, 0, 0);
  const w0 = await ps[0].next(kind("wave"));
  assert.equal(w0.scene, START); assert.equal(w0.no, ch.wave.no); assert.equal(w0.of, GBI.waves); assert.equal(w0.fresh, 1);
  assert.equal(w0.l.length, ch.wave.monsters); assert.equal(w0.monsters, ch.wave.monsters); assert.equal(w0.kills, 0); assert.equal(w0.cleared, false);
  for (const [, x, z] of w0.l) assert.ok(Math.hypot(x, z) >= 16, "the wave starts away from whoever stepped in");
  const floor = room.floors[START], t0 = floor.wave.t0;
  assert.equal(floor.monsters.length, ch.wave.monsters);
  for (let i = 1; i < 10; i++) { const [x, z] = spotOf(srv, room, START, i); at(ps[i], START, x, z); }
  for (let i = 1; i < 10; i++) { const w = await ps[i].next(kind("wave")); assert.deepEqual(w.l.map(e => e[0]), w0.l.map(e => e[0]), "the same monsters, by id"); assert.equal(w.no, w0.no); assert.ok(!w.fresh, "not news for the ones who came after"); }
  assert.equal(floor.wave.t0, t0, "started once"); assert.equal(floor.monsters.length, ch.wave.monsters, "nine more arrivals add no monsters");
  assert.ok(!(await ps[0].quiet(200)).some(m => m.t === "wave"), "the first player is not told of a second wave");
  for (const p of ps) { const m = await p.next(m2 => m2.t === "m" && m2.scene === START); assert.equal(m.l.length, ch.wave.monsters, "everyone follows the same snapshot"); }
  await srv.close();
});

test("players in a chamber see each other, and the stairs lead to the next chamber with its own wave; the one left behind keeps its monsters", async () => {
  const srv = await createServer({countdownMs: 60}), {ps: [a, b], room} = await party(srv, "ST1", ["Ann", "Bob"]);
  at(a, START, 0, 0); await a.next(kind("wave")); at(b, START, 1, 0); await b.next(kind("wave"));
  at(a, START, 0.5, 0); const s = await b.next(m => m.t === "s" && m.id === a.id); assert.equal(s.scene, START); assert.equal(s.x, 0.5);
  const arrive = REGISTRY.linkFrom(START, REGISTRY.chamber(START).stairsDown).to.arrive;
  at(a, NEXT, arrive[0], arrive[2]);
  const w = await a.next(kind("wave")); assert.equal(w.scene, NEXT); assert.equal(w.no, REGISTRY.chamber(NEXT).wave.no); assert.equal(w.l.length, REGISTRY.chamber(NEXT).wave.monsters);
  for (const [, x, z] of w.l) assert.ok(Math.hypot(x - arrive[0], z - arrive[2]) >= 16);
  assert.equal((await b.next(m => m.t === "p" && m.id === a.id && m.scene !== START)).scene, NEXT, "Bob learns Ann went down");
  assert.ok(!(await b.quiet(150)).some(m => m.t === "wave"), "Bob, still upstairs, is told of no new wave");
  at(b, NEXT, arrive[0] + 1, arrive[2]); const wb = await b.next(kind("wave")); assert.deepEqual(wb.l.map(e => e[0]), w.l.map(e => e[0]));
  const up = room.floors[START].monsters.map(m => [m.wid, m.pos.x, m.pos.z]);          // both are downstairs now
  await sleep(150);
  assert.ok(room.floors[START], "the chamber they left is kept for the life of the room");
  assert.deepEqual(room.floors[START].monsters.map(m => [m.wid, m.pos.x, m.pos.z]), up, "and nothing moves in it while it is empty");
  at(b, START, 0, 0); const back = await b.next(kind("wave")); assert.equal(back.scene, START); assert.ok(!back.fresh); assert.equal(room.floors[START].wave.t0 <= room.floors[START].t, true);
  await srv.close();
});

test("a room only takes its own mode's scenes: no Original floor in Going back in, no chamber in the Original", async () => {
  const srv = await createServer({countdownMs: 60}), {ps: [a], room} = await party(srv, "SC1", ["Ann"]);
  at(a, "B1", 0, 0); await sleep(80); assert.equal(room.players.get(a.id).scene, null); assert.equal(Object.keys(room.floors).length, 0);
  const o = await join(srv, "SC1", "Olga", "original"); o.send({t: "ready", ready: true}); await o.next(kind("start"));
  at(o, START, 0, 0); await sleep(80);
  const oroom = srv.rooms.get("SC1"); assert.equal(oroom.players.get(o.id).scene, null); assert.equal(Object.keys(oroom.floors).length, 0);
  assert.ok(!(await o.quiet(50)).some(m => m.t === "wave"));
  await srv.close();
});

test("you start with the ray and the cloak; a down nobody lifts is a death: you get up in the same chamber without your ammunition. A lift costs nothing", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room} = await party(srv, "DT1", ["Ann", "Bob"]);
  const me = await a.next(m => m.t === "me" && m.gun === true); assert.equal(me.rounds, GUN_ROUNDS); assert.ok(me.cloak, "the mode starts you with the ray and the cloak");
  at(a, START, 0, 0); await a.next(kind("wave")); at(b, START, 1, 0); await b.next(kind("wave"));
  const pa = room.players.get(a.id), pb = room.players.get(b.id);
  PS.hit(pa.ps, 100, clk.now()); assert.ok(PS.isDown(pa.ps));
  b.send({t: "revive", to: a.id}); await a.next(kind("revived"));
  assert.equal(pa.ps.rounds, GUN_ROUNDS, "lifted by a teammate: nothing is lost");
  clk.adv(PS.IMMUNE_S + 1); PS.hit(pb.ps, 100, clk.now()); clk.adv(PS.DOWNED_S + 1);
  const up = await b.next(m => m.t === "me" && m.respawn === 1);
  assert.equal(up.hp, 100); assert.equal(up.rounds, 0, "the ammunition is gone"); assert.equal(up.beacons, 0);
  assert.equal(pb.scene, START, "still in the same chamber"); assert.equal(pb.ps.stats.deaths, 1);
  await srv.close();
});

test("the Original's death rule is unchanged: getting up after the down time keeps your rounds", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now});
  const o = await join(srv, "DT2", "Olga", "original"); o.send({t: "ready", ready: true}); await o.next(kind("start"));
  at(o, "B1", 0, 0); await sleep(60);
  const p = srv.rooms.get("DT2").players.get(o.id); PS.gotLocker(p.ps); PS.hit(p.ps, 100, clk.now()); clk.adv(PS.DOWNED_S + 1);
  const up = await o.next(m => m.t === "me" && m.respawn === 1); assert.equal(up.rounds, GUN_ROUNDS);
  await srv.close();
});
