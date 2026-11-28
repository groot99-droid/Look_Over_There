// Going back in in a room (session 16): the server runs the chambers as floors, starts each chamber's wave once (when the first player steps in), and everyone on the floor
// sees the same monsters. Real sockets against a real server, like floors.test.js; the clock is the test's.
import test from "node:test";
import assert from "node:assert/strict";
import {WebSocket} from "ws";
import {createServer} from "./server.js";
import {REGISTRY} from "../shared/registry.js";
import {FLOORS, mainRegion, cellXZ, cellOf, segClear, rayClear, rng32} from "../shared/world.js";
import {START_BOLTS, RELOAD_S, PACK_BOLTS} from "../shared/crossbow.js";
import {GEAR} from "../shared/loadout.js";
import {START as KIT_START, FLASH_STUN_S, MINE_ARM_S, WIRE_ARM_S, WIRE_BLAST_R, WIRE_NOISE_R} from "../shared/consumables.js";
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
  assert.equal(up.hp, 100); assert.equal(up.rounds, 0, "the ammunition is gone"); assert.equal(up.beacons, 0); assert.equal(up.bolts, 0);
  assert.deepEqual(up.carry, [], "the gear is in the locker (slice 2)"); assert.equal(up.gun, false); assert.equal(up.cloak, null);
  b.send({t: "gear", a: "take", g: "gun"}); const back = await b.next(m => m.t === "me" && m.gun === true && m.carry.length === 1); assert.deepEqual(back.carry, ["gun"]); assert.equal(back.rounds, 0, "the locker returns the ray, not its rounds");
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

// ---- slice 2: the server owns the crossbow (bolts, kills), the cleared wave, and each player's loadout
// a spot with a clear straight line of d metres to another walkable spot (as in floors.test.js)
function clearPair(W, d, seed = 4) {
  const cells = mainRegion(W), r = rng32(seed), inRegion = new Set(cells);
  for (let i = 0; i < 4000; i++) {
    const [x, z] = cellXZ(cells[Math.floor(r() * cells.length)]), a = r() * 6.28, x2 = x + Math.cos(a) * d, z2 = z + Math.sin(a) * d;
    if (!inRegion.has(cellOf(x2, z2))) continue;
    if ([0.25, 0.5, 0.75, 1].every(u => segClear(W, x, W.floor + 1.0, z, x + (x2 - x) * u, W.floor + 1.0, z + (z2 - z) * u, 0)) && segClear(W, x, W.floor + 1.5, z, x2, W.floor + 1.5, z2, 0) && rayClear(W, [x, W.floor + 1.52, z], [(x2 - x) / d, 0, (z2 - z) / d], d)) return [[x, z], [x2, z2]];
  }
  throw new Error("no clear pair");
}
const still = m => { m.cfg = {...m.cfg, patrol: 0, alert: 0, chase: 0}; m.state = "patrol"; m.path = []; m.wait = 1e9; };
// two players in the first chamber, its wave started, the monsters parked far away and standing still; Ann stands at `a` with a clear line to `b`
async function chamberWith(srv, code, clk) {
  const {ps, room} = await party(srv, code, ["Ann", "Bob"]);
  at(ps[0], START, 0, 0); await ps[0].next(kind("wave")); at(ps[1], START, 1, 0); await ps[1].next(kind("wave"));
  const floor = room.floors[START], [a, b] = clearPair(floor.W, 6);
  floor.monsters.forEach((m, i) => { still(m); m.pos.set(900 + i * 5, m.fy, 900); });
  for (const p of room.players.values()) p.ps.immUntil = 1e15;
  at(ps[0], START, a[0], a[1]); at(ps[1], START, a[0] + 1, a[1]); await sleep(120);
  const dx = b[0] - a[0], dz = b[1] - a[1], L = Math.hypot(dx, dz);
  return {ps, room, floor, a, b, o: [a[0], floor.W.floor + 1.52, a[1]], d: [dx / L, 0, dz / L], put: m => m.pos.set(b[0], m.fy, b[1])};
}

test("the crossbow is the server's: a bolt costs one, a hit kills the monster for everyone, and the reload is enforced", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room, floor, o, d, put} = await chamberWith(srv, "BW1", clk);
  const me = await a.next(m => m.t === "me" && m.bolts !== undefined); assert.equal(me.bolts, START_BOLTS, "the crossbow starts in your hands"); assert.deepEqual(me.carry, GEAR);
  const pa = room.players.get(a.id), target = floor.monsters[1], wid = target.wid; put(target); a.inbox.length = 0; b.inbox.length = 0;
  a.send({t: "bolt", o: [o[0] + 40, o[1], o[2]], d}); await sleep(100); assert.equal(pa.ps.gbi.bow.bolts, START_BOLTS, "a bolt from 40 m away from the shooter is refused and costs nothing");
  a.send({t: "bolt", o, d});
  const k = await b.next(kind("kill")); assert.equal(k.scene, START); assert.equal(k.id, wid); assert.equal(k.by, a.id); assert.equal(k.kills, 1); assert.equal(k.cleared, false);
  await a.next(kind("kill")); assert.ok((await b.next(kind("beam"))).o, "the other player sees the bolt fly");
  assert.equal((await a.next(m => m.t === "me" && m.bolts === START_BOLTS - 1)).bolts, START_BOLTS - 1);
  assert.deepEqual(floor.monsters.map(m => m.wid), [0, 1, 2].filter(i => i !== wid), "the monster is gone from the floor");
  a.inbox.length = 0; assert.equal((await a.next(m => m.t === "m" && m.scene === START)).l.length, 2, "and from the snapshots");
  put(floor.monsters[0]); clk.adv(RELOAD_S * 0.5); a.send({t: "bolt", o, d}); await sleep(100);
  assert.equal(floor.monsters.length, 2, "still reloading: no shot"); assert.equal(pa.ps.gbi.bow.bolts, START_BOLTS - 1);
  assert.equal(pa.ps.stats.shots, 1); assert.equal(pa.ps.stats.hits, 1);
  await srv.close();
});

test("the wave is cleared when all its monsters are dead; the kills last for the life of the room, for those who come later too", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room, floor, o, d, put} = await chamberWith(srv, "BW2", clk);
  const pa = room.players.get(a.id); let last;
  for (let n = 1; n <= 3; n++) { put(floor.monsters[0]); pa.ps.gbi.bow = {...pa.ps.gbi.bow, cool: 0}; a.send({t: "bolt", o, d}); last = await b.next(m => m.t === "kill" && m.kills === n); }
  assert.equal(last.cleared, true); assert.equal(floor.wave.cleared, true); assert.equal(floor.monsters.length, 0);
  at(b, NEXT, 16, 8); await b.next(m => m.t === "wave" && m.scene === NEXT); at(a, NEXT, 17, 8); await a.next(m => m.t === "wave" && m.scene === NEXT);
  at(b, START, 0, 0); const w = await b.next(m => m.t === "wave" && m.scene === START);
  assert.deepEqual(w.l, [], "nothing came back"); assert.equal(w.kills, 3); assert.equal(w.cleared, true); assert.ok(!w.fresh);
  const late = await join(srv, "BW2", "Cy"); at(late, START, 0, 0); const wl = await late.next(kind("wave")); assert.equal(wl.cleared, true); assert.equal(wl.l.length, 0);
  await srv.close();
});

test("the locker's loadout is each player's own, kept by the server: leaving the ray there means no shot, and an ammo pack adds bolts for a carried crossbow", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room, floor, o, d, put} = await chamberWith(srv, "LD1", clk);
  const pa = room.players.get(a.id), pb = room.players.get(b.id);
  a.send({t: "gear", a: "leave", g: "crossbow"}); const m1 = await a.next(m => m.t === "me" && m.carry && !m.carry.includes("crossbow"));
  assert.deepEqual(m1.carry, ["gun", "cloak"]); assert.deepEqual(pb.ps.gbi.load.carry, GEAR, "Bob's loadout is his own");
  put(floor.monsters[0]); a.send({t: "bolt", o, d}); await sleep(100); assert.equal(floor.monsters.length, 3, "no crossbow in hand: no bolt");
  a.send({t: "gear", a: "leave", g: "gun"}); await a.next(m => m.t === "me" && m.gun === false);
  a.send({t: "shot", o, d}); await sleep(100); assert.equal(pa.ps.rounds, GUN_ROUNDS, "the ray is in the locker: no shot, no round spent");
  a.send({t: "gear", a: "leave", g: "cloak"}); assert.equal((await a.next(m => m.t === "me" && m.carry.length === 0)).cloak, null);
  a.send({t: "gear", a: "take", g: "nonsense"}); a.send({t: "gear", a: "steal", g: "gun"}); await sleep(80); assert.deepEqual(pa.ps.gbi.load.carry, []);
  for (const g of GEAR) a.send({t: "gear", a: "take", g});
  const m2 = await a.next(m => m.t === "me" && m.carry.length === 3); assert.equal(m2.gun, true); assert.ok(m2.cloak); assert.equal(m2.rounds, GUN_ROUNDS, "the rounds stayed on you");
  pa.ps.rounds = 1; pa.ps.gbi.bow = {bolts: 1, cool: 0}; a.send({t: "loot", k: "pack", i: 0});
  const m3 = await a.next(m => m.t === "me" && m.rounds === 4); assert.equal(m3.bolts, 1 + PACK_BOLTS, "a pack adds bolts too");
  assert.ok((await b.next(m => m.t === "loot" && m.by === a.id)).st.packs[0] === a.id, "the pack is gone for everyone in the chamber");
  pb.ps.immUntil = 0; PS.hit(pb.ps, 100, clk.now()); b.send({t: "gear", a: "leave", g: "gun"}); await sleep(80); assert.deepEqual(pb.ps.gbi.load.carry, GEAR, "not while you are down");
  await srv.close();
});

test("the Original has no crossbow and no loadout: its players are not told of either, and a bolt or a gear message does nothing", async () => {
  const srv = await createServer({countdownMs: 60});
  const o = await join(srv, "OR1", "Olga", "original"); o.send({t: "ready", ready: true}); await o.next(kind("start"));
  const me = await o.next(kind("me")); assert.equal(me.bolts, undefined); assert.equal(me.carry, undefined);
  at(o, "B1", 0, 0); await sleep(80); const floor = srv.rooms.get("OR1").floors.B1, n = floor.monsters.length;
  o.send({t: "bolt", o: [0, FLOORS.B1 + 1.52, 0], d: [1, 0, 0]}); o.send({t: "gear", a: "take", g: "crossbow"}); await sleep(100);
  assert.equal(floor.monsters.length, n); assert.equal(srv.rooms.get("OR1").players.get(o.id).ps.gbi, undefined);
  await srv.close();
});

// ---- slice 3: the Q and E consumables in a room. The server counts them, stuns and kills, and everyone in the chamber sees the traps
const stepN = (floor, secs) => { for (let t = 0; t < secs; t += 0.05) floor.step(0.05); };

test("Q, the flash-vial: the server takes one and stuns the monsters where it lands; everyone sees the flash; it kills nothing", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room, floor, a: spot, b: land, put} = await chamberWith(srv, "CQ1", clk);
  const me = await a.next(m => m.t === "me" && m.kit); assert.deepEqual(me.kit, {n: KIT_START, e: "mine"}, "the mode's starting consumables");
  const pa = room.players.get(a.id), m0 = floor.monsters[0]; put(m0); a.inbox.length = 0; b.inbox.length = 0;
  a.send({t: "use", slot: 0, x: spot[0] + 40, z: spot[1]}); await sleep(80); assert.equal(pa.ps.gbi.kit.n.flash, KIT_START.flash, "a landing far past the throw is refused and costs nothing");
  a.send({t: "use", slot: 0, x: land[0], z: land[1]});
  const f = await b.next(kind("flash")); assert.equal(f.scene, START); assert.equal(f.from, a.id); assert.deepEqual([f.x, f.z], [+land[0].toFixed(2), +land[1].toFixed(2)]); assert.equal(f.n, 1); assert.equal(f.secs, FLASH_STUN_S);
  await a.next(kind("flash"));
  assert.ok(m0.stunT > 0, "the monster at the landing is stunned"); assert.ok(!(floor.monsters[1].stunT > 0), "one far away is not");
  assert.equal((await a.next(m => m.t === "me" && m.kit && m.kit.n.flash === KIT_START.flash - 1)).kit.n.flash, KIT_START.flash - 1);
  assert.equal(floor.monsters.length, 3, "a flash kills nothing"); assert.equal(floor.wave.kills, 0);
  for (let i = 0; i < KIT_START.flash + 2; i++) a.send({t: "use", slot: 0, x: land[0], z: land[1]});
  await sleep(100); assert.equal(pa.ps.gbi.kit.n.flash, 0, "never below none");
  await srv.close();
});

test("E, the land mine: set where the server has you, seen by everyone, armed after a moment; the first monster to step on it dies, and only that one", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room, floor, a: spot} = await chamberWith(srv, "CE1", clk);
  const pa = room.players.get(a.id); a.inbox.length = 0; b.inbox.length = 0;
  a.send({t: "use", slot: 1});
  const t = await b.next(kind("trap")); assert.equal(t.kind, "mine"); assert.equal(t.by, a.id); assert.ok(Math.hypot(t.x - spot[0], t.z - spot[1]) < 0.01, "where Ann stands"); assert.equal(t.arm, MINE_ARM_S);
  assert.equal((await a.next(kind("trap"))).id, t.id); assert.equal(pa.ps.gbi.kit.n.mine, KIT_START.mine - 1);
  const [m0, m1] = floor.monsters, wid = m0.wid; m0.pos.set(spot[0], m0.fy, spot[1]); m1.pos.set(spot[0] + 0.3, m1.fy, spot[1]);
  stepN(floor, MINE_ARM_S * 0.5); assert.equal(floor.monsters.length, 3, "not armed yet");
  stepN(floor, MINE_ARM_S);
  const sp = await b.next(kind("sprung")); assert.equal(sp.id, t.id); const k = await b.next(kind("kill")); assert.equal(k.id, wid); assert.equal(k.by, a.id); assert.equal(k.kills, 1);
  assert.equal(floor.monsters.length, 2, "one mine, one monster"); assert.equal(floor.traps.length, 0, "the mine is spent");
  stepN(floor, 1); assert.equal(floor.monsters.length, 2);
  await srv.close();
});

test("E, the tripwire (chosen at the locker): everything in the blast dies, the noise brings the others, and someone who arrives later is shown a trap still set", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room, floor, a: spot} = await chamberWith(srv, "CE2", clk);
  const pa = room.players.get(a.id);
  a.send({t: "gear", a: "e", g: "wire"}); assert.equal((await a.next(m => m.t === "me" && m.kit && m.kit.e === "wire")).kit.n.wire, KIT_START.wire);
  a.send({t: "gear", a: "e", g: "flash"}); await sleep(60); assert.equal(pa.ps.gbi.kit.e, "wire", "only a land mine or a tripwire goes in E");
  a.send({t: "use", slot: 1}); const t = await b.next(kind("trap")); assert.equal(t.kind, "wire");
  const late = await join(srv, "CE2", "Cy"); at(late, START, 0, 0);
  const w = await late.next(kind("wave")); assert.deepEqual(w.traps.map(x => [x.id, x.kind]), [[t.id, "wire"]], "a late arrival sees the tripwire");
  const [m0, m1, m2] = floor.monsters; m0.pos.set(spot[0] + 1, m0.fy, spot[1]); m1.pos.set(spot[0] - (WIRE_BLAST_R - 0.3), m1.fy, spot[1]); m2.pos.set(spot[0] + WIRE_NOISE_R - 5, m2.fy, spot[1]);
  m2.cfg = {...m2.cfg, sight: 0};          // the far one only hears it: 20 m off it could also see a player, depending on where it faces, and chase instead of looking (the flake on #133 and #134)
  stepN(floor, WIRE_ARM_S + 0.2);
  await b.next(kind("sprung")); const k2 = await b.next(m => m.t === "kill" && m.kills === 2);
  assert.equal(k2.cleared, false); assert.deepEqual(floor.monsters, [m2], "the two in the blast are dead, the far one is not");
  assert.equal(m2.state, "search", "the blast is loud: the one in earshot goes to look"); assert.deepEqual(m2.last, [t.x, t.z]);
  await srv.close();
});

test("consumables are not returned after a death; an ammo pack adds one flash-vial and one of what E holds; the Original has none", async () => {
  const clk = clockOf(), srv = await createServer({countdownMs: 60, clock: clk.now}), {ps: [a, b], room, floor} = await chamberWith(srv, "CK1", clk);
  const pa = room.players.get(a.id); pa.ps.immUntil = 0; PS.hit(pa.ps, 100, clk.now());
  a.send({t: "use", slot: 1}); await sleep(60); assert.equal(floor.traps.length, 0, "nothing can be set while you are down");
  clk.adv(PS.DOWNED_S + 1);
  const up = await a.next(m => m.t === "me" && m.respawn === 1); assert.deepEqual(up.kit.n, {flash: 0, mine: 0, wire: 0});
  a.send({t: "use", slot: 0, x: pa.st.x, z: pa.st.z}); await sleep(60); assert.ok(!(await b.quiet(40)).some(m => m.t === "flash"), "none left: no flash");
  a.send({t: "loot", k: "pack", i: 1}); assert.deepEqual((await a.next(m => m.t === "me" && m.kit.n.flash === 1)).kit.n, {flash: 1, mine: 1, wire: 0});
  const o = await join(srv, "CK1", "Olga", "original"); o.send({t: "ready", ready: true}); await o.next(kind("start"));
  assert.equal((await o.next(kind("me"))).kit, undefined); at(o, "B1", 0, 0); await sleep(60); o.send({t: "use", slot: 1}); o.send({t: "use", slot: 0, x: 0, z: 0});
  assert.ok(!(await o.quiet(100)).some(m => m.t === "trap" || m.t === "flash"));
  await srv.close();
});

// ---- with presence scenes (session 17): a Going back in room still takes only its own scenes
test("a Going back in room does not let anyone into the parking lot, flags or not; go to a friend works between its chambers", async () => {
  const srv = await createServer({countdownMs: 60}), a = client(srv.port), b = client(srv.port); await a.open; await b.open;
  for (const [c, n] of [[a, "Ann"], [b, "Bob"]]) { c.send({t: "join", room: "PR1", name: n, mode: MODE, flags: ["original_complete"]}); c.id = (await c.next(kind("welcome"))).id; }
  const room = srv.rooms.get(`${MODE}:PR1`); a.send({t: "ready", ready: true}); b.send({t: "ready", ready: true}); await a.next(kind("start")); await b.next(kind("start"));
  at(a, "parking_lot", -8, 41); assert.equal((await a.next(kind("noentry"))).scene, "parking_lot"); assert.equal(room.players.get(a.id).scene, null, "nowhere: not in the lot");
  at(a, START, 0, 0); await a.next(kind("wave")); at(b, NEXT, 16, 8); await b.next(kind("wave"));
  a.send({t: "goto", to: b.id}); const g = await a.next(kind("goto")); assert.equal(g.scene, NEXT); assert.equal(g.refused, undefined, "a friend in the next chamber is reachable"); assert.equal(g.x, 16);
  await srv.close();
});
