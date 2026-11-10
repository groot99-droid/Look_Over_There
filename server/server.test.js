import test from "node:test";
import assert from "node:assert/strict";
import {WebSocket} from "ws";
import {createServer} from "./server.js";
import {REGISTRY} from "../shared/registry.js";
import * as PS from "./playerstate.js";

// a tiny client: queues what it receives so a test can wait for a message of a given kind
function client(port) {
  const ws = new WebSocket(`ws://localhost:${port}/ws`), inbox = [], waiters = [];
  ws.on("message", d => { const m = JSON.parse(d); inbox.push(m); waiters.splice(0).forEach(w => w()); });
  const c = {ws, inbox, send: m => ws.send(JSON.stringify(m)),
    open: new Promise(r => ws.on("open", r)),
    async next(pred, ms = 2000) {
      const end = Date.now() + ms;
      for (;;) {
        const i = inbox.findIndex(pred); if (i >= 0) return inbox.splice(i, 1)[0];
        if (Date.now() > end) throw new Error("timed out waiting for a message");
        await new Promise(r => { waiters.push(r); setTimeout(r, 50); });
      }
    },
    quiet: async ms => { await new Promise(r => setTimeout(r, ms)); return inbox.splice(0); }};
  return c;
}
const kind = t => m => m.t === t;
async function join(srv, room, name) { const c = client(srv.port); await c.open; c.send({t: "join", room, name}); const w = await c.next(kind("welcome")); return Object.assign(c, {id: w.id, welcome: w}); }

test("round starts only when everyone is ready, after the countdown", async () => {
  const srv = await createServer({countdownMs: 150});
  const a = await join(srv, "R1", "Ann"), b = await join(srv, "R1", "Bob");
  assert.equal(a.welcome.phase, "lobby");
  a.send({t: "ready", ready: true});
  assert.equal((await a.next(m => m.t === "lobby" && m.players.every(p => p.id !== a.id || p.ready))).countdownMs, null, "no countdown while Bob is not ready");
  b.send({t: "ready", ready: true});
  const l = await a.next(m => m.t === "lobby" && m.countdownMs);
  assert.equal(l.players.length, 2);
  await a.next(kind("start")); await b.next(kind("start"));
  const late = await join(srv, "R1", "Cy");
  assert.equal(late.welcome.phase, "playing", "someone joining mid-round skips the lobby");
  await srv.close();
});

test("un-readying or a newcomer cancels the countdown", async () => {
  const srv = await createServer({countdownMs: 300});
  const a = await join(srv, "R2", "Ann");
  a.send({t: "ready", ready: true}); await a.next(m => m.t === "lobby" && m.countdownMs);
  const b = await join(srv, "R2", "Bob");
  const got = await a.quiet(500);
  assert.ok(!got.some(m => m.t === "start"), "no start after a newcomer joined");
  assert.ok(got.some(m => m.t === "lobby" && m.countdownMs === null));
  await srv.close();
});

test("positions go only to players on the same floor", async () => {
  const srv = await createServer();
  const a = await join(srv, "R3", "Ann"), b = await join(srv, "R3", "Bob"), c = await join(srv, "R3", "Cy");
  const at = {a: {t: "s", scene: "B1", x: 1, y: 0, z: 2, yaw: 0}};
  a.send(at.a); b.send({t: "s", scene: "B1", x: 3, y: 0, z: 4, yaw: 0}); c.send({t: "s", scene: "L1", x: 9, y: 9, z: 9, yaw: 0});
  await new Promise(r => setTimeout(r, 200));                                   // everyone's floor is known now
  const drained = await Promise.all([a, b, c].map(x => x.quiet(100)));
  a.send(at.a);
  await b.next(m => m.t === "s" && m.id === a.id);
  const cGot = [...drained[2], ...await c.quiet(300)];
  assert.ok(!cGot.some(m => m.t === "s"), "Cy on L1 got no positions from B1");
  assert.ok(cGot.some(m => m.t === "p" && m.id === a.id && m.scene === "B1"), "but learned Ann is on B1");
  assert.ok(!JSON.stringify(cGot).includes('"x":1'), "no coordinates leaked");
  await srv.close();
});

test("clients cannot send monsters, hits or zaps; revive needs the same floor, a downed target and a reach", async () => {
  const srv = await createServer();
  const a = await join(srv, "R4", "Ann"), b = await join(srv, "R4", "Bob"), c = await join(srv, "R4", "Cy");
  a.send({t: "s", scene: "B1", x: 0, y: -3, z: 0}); b.send({t: "s", scene: "B1", x: 1, y: -3, z: 0}); c.send({t: "s", scene: "L1", x: 0, y: 0, z: 0});
  await Promise.all([a, b, c].map(x => x.quiet(150)));
  b.send({t: "m", scene: "B1", l: [[1, 1, 0, 0, 0]]}); b.send({t: "hit", to: a.id, dmg: 35}); b.send({t: "zap", scene: "B1", i: 0, from: [1, 2], to: [30, 40]});
  const got = await a.quiet(200);
  assert.ok(!got.some(m => m.t === "hit" || m.t === "zap" || (m.t === "m" && m.l.length === 1)), "the server runs the monsters: nothing a client sends counts");
  b.send({t: "revive", to: a.id}); assert.ok(!(await a.quiet(150)).some(m => m.t === "revived"), "Ann is not down");
  c.send({t: "revive", to: a.id}); assert.ok(!(await a.quiet(150)).some(m => m.t === "revived"), "Cy is on another floor");
  await srv.close();
});

test("characters: a choice is kept (duplicates allowed), no choice gets one nobody has", async () => {
  const srv = await createServer();
  const a = client(srv.port); await a.open; a.send({t: "join", room: "R5", name: "Ann", char: 3}); const wa = await a.next(kind("welcome"));
  assert.equal(wa.players.find(p => p.id === wa.id).char, 3);
  const b = client(srv.port); await b.open; b.send({t: "join", room: "R5", name: "Bob", char: 3}); const wb = await b.next(kind("welcome"));
  assert.equal(wb.players.find(p => p.id === wb.id).char, 3, "two players may be the same character");
  const c = client(srv.port); await c.open; c.send({t: "join", room: "R5", name: "Cy"}); const wc = await c.next(kind("welcome"));
  assert.equal(wc.players.find(p => p.id === wc.id).char, 0, "the first character nobody has");
  const d = client(srv.port); await d.open; d.send({t: "join", room: "R5", name: "Di", char: 99}); const wd = await d.next(kind("welcome"));
  assert.equal(wd.players.find(p => p.id === wd.id).char, 1, "an invalid choice is treated as none");
  const joined = await a.next(m => m.t === "join" && m.name === "Cy"); assert.equal(joined.char, 0);
  await srv.close();
});

test("a door shut is relayed as shut, not open, only for a real door near the player; a stair door is never theirs", async () => {
  const srv = await createServer();
  const a = await join(srv, "R6", "Ann"), b = await join(srv, "R6", "Bob");
  a.send({t: "s", scene: "L1", x: 0, y: 0, z: 0}); b.send({t: "s", scene: "L1", x: 1, y: 0, z: 0}); await Promise.all([a, b].map(x => x.quiet(200)));
  const floor = srv.rooms.get("R6").floors.L1, dr = floor.W.doors.find(d => !d.link), link = floor.W.doors.find(d => d.link);
  a.send({t: "door", scene: "L1", name: "D1", open: 1}); assert.ok(!(await b.quiet(150)).some(m => m.t === "door"), "no such door");
  a.send({t: "s", scene: "L1", x: dr.cx + 2, y: 0, z: dr.cz}); await b.quiet(100);          // near, but not standing in the doorway
  a.send({t: "door", scene: "L1", name: dr.d.name, open: 1}); assert.equal((await b.next(kind("door"))).open, 1);
  a.send({t: "door", scene: "L1", name: dr.d.name, open: 0}); assert.equal((await b.next(kind("door"))).open, 0);
  a.send({t: "s", scene: "L1", x: link.cx + 1, y: 0, z: link.cz}); await b.quiet(100);
  a.send({t: "door", scene: "L1", name: link.d.name, open: 1}); assert.ok(!(await b.quiet(150)).some(m => m.t === "door"), "stair doors are not a player's to open");
  await srv.close();
});

test("fuses: take and slot are relayed to the floor, a floor change or leaving puts a carried fuse back", async () => {
  const srv = await createServer();
  const a = await join(srv, "R7", "Ann"), b = await join(srv, "R7", "Bob");
  a.send({t: "s", scene: "B1"}); b.send({t: "s", scene: "B1"});
  const first = await a.next(kind("fuses"));                             // entering a gated floor sends its state
  assert.equal(first.scene, "B1"); assert.ok(first.st.every(f => f.s === 0));
  await b.next(kind("fuses"));
  a.send({t: "fuse", a: "take", i: 1});
  const took = await b.next(m => m.t === "fuses" && m.st[1].s === 1);
  assert.equal(took.st[1].by, a.id, "Bob sees Ann carrying fuse 1");
  b.send({t: "fuse", a: "take", i: 1});                                  // already taken
  b.send({t: "fuse", a: "take", i: 0}); const bobs = await a.next(m => m.t === "fuses" && m.st[0].s === 1);
  assert.equal(bobs.st[1].by, a.id, "Ann's fuse is still hers");
  b.send({t: "fuse", a: "drop", x: 3.5, z: -1});
  assert.deepEqual((await a.next(m => m.t === "fuses" && m.st[0].s === 3)).st[0], {s: 3, x: 3.5, z: -1});
  a.send({t: "s", scene: "L3"});                                         // Ann walks off the floor carrying fuse 1
  assert.equal((await b.next(m => m.t === "fuses" && m.st[1].s === 0)).st[1].s, 0, "the fuse went back");
  a.send({t: "fuse", a: "take", i: 2});                                  // L3 is not gated
  assert.ok(!(await b.quiet(150)).some(m => m.t === "fuses" && m.st[2].s === 1));
  await srv.close();
});

test("fuses: state is kept for the room; leaving releases; junk is ignored", async () => {
  const srv = await createServer();
  const a = await join(srv, "R8", "Ann"); a.send({t: "s", scene: "B1"}); await a.next(kind("fuses"));
  a.send({t: "fuse", a: "take", i: 0}); await a.next(m => m.t === "fuses" && m.st[0].s === 1);
  a.send({t: "fuse", a: "slot"}); await a.next(m => m.t === "fuses" && m.st[0].s === 2);
  a.send({t: "fuse", a: "take", i: "x"}); a.send({t: "fuse", a: "evil", i: 1}); a.send({t: "fuse", a: "drop", x: NaN, z: 0});
  assert.ok(!(await a.quiet(150)).some(m => m.t === "fuses"), "junk changed nothing");
  const b = await join(srv, "R8", "Bob"); b.send({t: "s", scene: "B1"});
  assert.equal((await b.next(kind("fuses"))).st[0].s, 2, "a later joiner sees the slotted fuse");
  b.send({t: "fuse", a: "take", i: 1}); await a.next(m => m.t === "fuses" && m.st[1].s === 1);
  b.ws.close(); const back = await a.next(m => m.t === "fuses" && m.st[1].s === 0);
  assert.equal(back.st[1].s, 0, "Bob left holding a fuse, it went back");
  await srv.close();
});

test("switches: flipped one at a time on L1, kept for the room, refused elsewhere", async () => {
  const srv = await createServer();
  const a = await join(srv, "R9", "Ann"), b = await join(srv, "R9", "Bob");
  a.send({t: "s", scene: "L1"}); b.send({t: "s", scene: "B1"});
  const first = await a.next(kind("switches")); assert.deepEqual(first.st, [{on: false}, {on: false}]);
  a.send({t: "switch", i: 1}); const one = await a.next(m => m.t === "switches" && m.st[1].on);
  assert.equal(one.st[0].on, false, "only the one flipped is on");
  a.send({t: "switch", i: 1}); a.send({t: "switch", i: 7}); a.send({t: "switch", i: "x"});
  assert.ok(!(await a.quiet(150)).some(m => m.t === "switches"), "flipping it again, or a switch that does not exist, changes nothing");
  b.send({t: "switch", i: 0});                                           // Bob is on B1, which has no switches
  assert.ok(!(await a.quiet(150)).some(m => m.t === "switches"));
  b.send({t: "s", scene: "L1"}); assert.equal((await b.next(kind("switches"))).st[1].on, true, "Bob arrives and sees Ann's flip");
  b.send({t: "switch", i: 0}); const done = await a.next(m => m.t === "switches" && m.st[0].on);
  assert.ok(done.st.every(s => s.on), "both on: done");
  await srv.close();
});

// a rng that makes the code 1 2 3 4
const code1234 = (() => { let k = 0; return () => ((k++ % 4) + 1 + 0.5) / 10; })();
test("keypad: digits are shown to the team as they are found, and the code never leaves the server", async () => {
  const srv = await createServer({rng: code1234});
  const a = await join(srv, "R10", "Ann"), b = await join(srv, "R10", "Bob");
  a.send({t: "s", scene: "L2"}); b.send({t: "s", scene: "L2"});
  const first = await a.next(kind("keypad")); assert.deepEqual(first.found, [null, null, null, null]); assert.equal(first.solved, false);
  await b.next(kind("keypad"));                                                       // Bob's own arrival state
  a.send({t: "keypad", a: "find", i: 2});
  const seen = await b.next(m => m.t === "keypad" && m.found[2] !== null);
  assert.deepEqual(seen.found, [null, null, 3, null], "Bob sees the digit Ann read");
  a.send({t: "keypad", a: "find", i: 2}); a.send({t: "keypad", a: "find", i: 9});
  assert.ok(!(await b.quiet(150)).some(m => m.t === "keypad"), "reading it again, or a note that does not exist, changes nothing");
  const everything = JSON.stringify([...a.inbox, ...b.inbox, seen, first]);
  assert.ok(!everything.includes('"code"'), "no message carries the code");
  const late = await join(srv, "R10", "Cy"); late.send({t: "s", scene: "L2"});
  assert.deepEqual((await late.next(kind("keypad"))).found, [null, null, 3, null], "a late joiner sees what was found");
  await srv.close();
});
test("keypad: a wrong code locks it for everyone; the right one opens the door", async () => {
  const srv = await createServer({rng: code1234});
  const a = await join(srv, "R11", "Ann"), b = await join(srv, "R11", "Bob");
  a.send({t: "s", scene: "L2"}); b.send({t: "s", scene: "L2"}); await a.next(kind("keypad")); await b.next(kind("keypad"));
  a.send({t: "keypad", a: "try", code: "9999"});
  const bad = await b.next(m => m.t === "keypad" && m.fails === 1);
  assert.ok(bad.lockMs > 7000 && bad.lockMs <= 8000, "the lock runs for about 8 s");
  b.send({t: "keypad", a: "try", code: "1234"});                                  // right code, but it is locked
  const told = await b.next(kind("keypad")); assert.equal(told.solved, false); assert.ok(told.lockMs > 0, "Bob is told how long it has left");
  assert.ok(!(await a.quiet(150)).some(m => m.t === "keypad" && m.solved), "and it did not open for anyone");
  b.send({t: "keypad", a: "try", code: "12"}); b.send({t: "keypad", a: "try", code: "abcd"});
  assert.ok(!(await a.quiet(150)).some(m => m.t === "keypad" && m.fails > 1), "malformed input is not a fail");
  await srv.close();
});
test("keypad: only on a keypad floor, and the right code solves it", async () => {
  const srv = await createServer({rng: code1234});
  const a = await join(srv, "R12", "Ann"); a.send({t: "s", scene: "B1"}); await a.next(kind("fuses"));
  a.send({t: "keypad", a: "find", i: 0}); a.send({t: "keypad", a: "try", code: "1234"});
  assert.ok(!(await a.quiet(150)).some(m => m.t === "keypad"), "B1 has no keypad");
  a.send({t: "s", scene: "L2"}); await a.next(kind("keypad"));
  a.send({t: "keypad", a: "try", code: "1234"});
  const done = await a.next(m => m.t === "keypad" && m.solved); assert.equal(done.fails, 0);
  a.send({t: "keypad", a: "find", i: 1});
  assert.ok(!(await a.quiet(150)).some(m => m.t === "keypad"), "an open door takes no more notes");
  await srv.close();
});

test("power: thrown once from L3 or L4 and told to the whole room, including late joiners", async () => {
  const srv = await createServer();
  const a = await join(srv, "R13", "Ann"), b = await join(srv, "R13", "Bob");
  assert.equal(a.welcome.power, false);
  a.send({t: "s", scene: "L2"}); b.send({t: "s", scene: "B1"});
  a.send({t: "power"}); b.send({t: "power"});                                      // neither is on a power floor
  assert.ok(!(await a.quiet(150)).some(m => m.t === "power"), "L2 and B1 have no power switch");
  a.send({t: "s", scene: "L3"}); await a.quiet(60);
  a.send({t: "power"});
  const heard = await b.next(kind("power"));                                       // Bob is on B1 and still hears of it
  assert.deepEqual([heard.on, heard.by], [true, "L3"]);
  await a.next(kind("power"));
  a.send({t: "s", scene: "L4"}); a.send({t: "power"});
  assert.ok(!(await b.quiet(150)).some(m => m.t === "power"), "thrown once: a second throw is not announced");
  const late = await join(srv, "R13", "Cy"); assert.equal(late.welcome.power, true, "a late joiner is told it is on");
  await srv.close();
});
test("power: a room that nobody powers stays off, and rooms are separate", async () => {
  const srv = await createServer();
  const a = await join(srv, "R14", "Ann"), b = await join(srv, "R15", "Bob");
  a.send({t: "s", scene: "L4"}); a.send({t: "power"}); await a.next(kind("power"));
  assert.equal((await join(srv, "R15", "Di")).welcome.power, false, "R15 is still off");
  assert.ok(!(await b.quiet(150)).some(m => m.t === "power"));
  await srv.close();
});

// a started round with these players in it
async function round(srv, room, names) {
  const cs = []; for (const n of names) cs.push(await join(srv, room, n));
  for (const c of cs) c.send({t: "ready", ready: true});
  for (const c of cs) await c.next(kind("start"));
  return cs;
}
test("finale: the alarm goes off once, when the doors are open and someone is in the store", async () => {
  const srv = await createServer({countdownMs: 100});
  const [a, b] = await round(srv, "R16", ["Ann", "Bob"]);
  a.send({t: "s", scene: "L3"}); b.send({t: "s", scene: "L2"});
  a.send({t: "power"}); await b.next(kind("power"));
  assert.ok(!(await b.quiet(150)).some(m => m.t === "alarm"), "power on but nobody on L4 yet: quiet");
  a.send({t: "s", scene: "L4"});
  const al = await b.next(kind("alarm")); assert.equal(al.ms, 60000);
  b.send({t: "s", scene: "L4"});
  assert.ok(!(await a.quiet(150)).filter(m => m.t === "alarm").slice(1).length, "once only");
  const late = await join(srv, "R16", "Cy"); assert.ok(late.welcome.alarmMs > 0 && late.welcome.alarmMs <= 60000);
  await srv.close();
});
test("finale: exits only from L4 with the power on; places in order; results when the last one is out", async () => {
  const srv = await createServer({countdownMs: 100});
  const [a, b] = await round(srv, "R17", ["Ann", "Bob"]);
  a.send({t: "s", scene: "L4"}); b.send({t: "s", scene: "L4"});
  a.send({t: "exit"});                                                             // the doors are shut: nobody is out
  assert.ok(!(await b.quiet(150)).some(m => m.t === "exited"));
  a.send({t: "power"}); await b.next(kind("power"));
  b.send({t: "s", scene: "L3"}); b.send({t: "exit"});                              // wrong floor
  assert.ok(!(await a.quiet(150)).some(m => m.t === "exited"));
  b.send({t: "s", scene: "L4"}); await a.quiet(60);
  a.send({t: "exit"}); const e1 = await b.next(kind("exited")); assert.deepEqual([e1.id, e1.place, e1.name], [a.id, 1, "Ann"]);
  a.send({t: "exit"}); assert.ok(!(await b.quiet(120)).some(m => m.t === "exited"), "leaving twice changes nothing");
  assert.ok(!(await a.quiet(10)).some(m => m.t === "results"), "Bob is still inside");
  b.send({t: "exit"});
  const r = await a.next(kind("results")); assert.deepEqual(r.rows.map(x => [x.place, x.name]), [[1, "Ann"], [2, "Bob"]]);
  await b.next(kind("results"));
  const late = await join(srv, "R17", "Cy"); assert.equal(late.welcome.results.length, 2, "a late joiner sees the finished round");
  await srv.close();
});
test("finale: someone who leaves the room does not hold the round up", async () => {
  const srv = await createServer({countdownMs: 100});
  const [a, b] = await round(srv, "R18", ["Ann", "Bob"]);
  a.send({t: "s", scene: "L4"}); b.send({t: "s", scene: "L4"}); a.send({t: "power"}); await a.next(kind("power"));
  a.send({t: "exit"}); await a.next(kind("exited"));
  b.ws.close();
  const r = await a.next(kind("results")); assert.deepEqual(r.rows.map(x => x.name), ["Ann"]);
  await srv.close();
});

test("loot: the floor's state arrives with you; a pack is taken once and told to the floor only", async () => {
  const srv = await createServer();
  const a = await join(srv, "R20", "Ann"), b = await join(srv, "R20", "Bob"), c = await join(srv, "R20", "Cy");
  a.send({t: "s", scene: "L2"}); b.send({t: "s", scene: "L2"}); c.send({t: "s", scene: "L1"});
  const first = await a.next(kind("loot")); assert.equal(first.scene, "L2"); assert.deepEqual(first.st, {lockers: [], packs: [0, 0, 0], beacons: [0, 0]});
  a.send({t: "loot", k: "pack", i: 1, rounds: 3});
  const got = await b.next(m => m.t === "loot" && m.by === a.id); assert.deepEqual([got.st.packs[1], got.by, got.k], [a.id, a.id, "pack"]);
  b.send({t: "loot", k: "pack", i: 1, rounds: 0});
  assert.ok(!(await a.quiet(200)).some(m => m.t === "loot" && m.by === b.id), "a pack that is gone cannot be taken again");
  assert.ok(!(await c.quiet(10)).some(m => m.t === "loot" && m.st.packs && m.st.packs[1] !== 0 && m.scene === "L2"), "Cy is on another floor");
  const late = await join(srv, "R20", "Di"); late.send({t: "s", scene: "L2"});
  assert.equal((await late.next(kind("loot"))).st.packs[1], a.id, "a late joiner sees what is taken");
  await srv.close();
});
test("loot: the server counts the rounds: a pack is refused when the player is full (whatever they claim), and nothing happens off the loot floors", async () => {
  const srv = await createServer();
  const a = await join(srv, "R21", "Ann"); a.send({t: "s", scene: "B1"}); await a.next(kind("loot"));
  a.send({t: "loot", k: "locker", i: 0}); await a.next(m => m.t === "me" && m.rounds === 3);
  a.send({t: "loot", k: "pack", i: 0, rounds: 0}); await a.next(m => m.t === "me" && m.rounds === 6);
  a.send({t: "loot", k: "pack", i: 1, rounds: 0}); await a.next(m => m.t === "me" && m.rounds === 9);
  await a.quiet(100); a.send({t: "loot", k: "pack", i: 2, rounds: 0}); a.send({t: "loot", k: "weird", i: 0}); a.send({t: "loot", k: "pack", i: 99, rounds: 0});
  assert.ok(!(await a.quiet(200)).some(m => m.t === "loot" || m.t === "me" && m.rounds !== 9), "full (the claim of 0 rounds is ignored), bad kind and bad index all do nothing");
  a.send({t: "s", scene: null}); a.send({t: "loot", k: "pack", i: 2, rounds: 0});
  assert.ok(!(await a.quiet(150)).some(m => m.t === "loot"), "not on a floor");
  await srv.close();
});

test("loot: one gun each from the B1 lockers, and leaving puts the locker back", async () => {
  const srv = await createServer();
  const a = await join(srv, "R22", "Ann"), b = await join(srv, "R22", "Bob");
  a.send({t: "s", scene: "B1"}); b.send({t: "s", scene: "B1"}); await a.next(kind("loot")); await b.next(kind("loot"));
  a.send({t: "loot", k: "locker", i: 0}); const l1 = await b.next(kind("loot")); assert.deepEqual([l1.st.lockers[0], l1.k], [a.id, "locker"]);
  a.send({t: "loot", k: "locker", i: 1}); assert.ok(!(await b.quiet(200)).some(m => m.t === "loot"), "Ann already has a gun");
  b.send({t: "loot", k: "locker", i: 0}); assert.ok(!(await a.quiet(200)).some(m => m.t === "loot" && m.by === b.id), "that locker is open already");
  b.send({t: "loot", k: "locker", i: 5}); assert.equal((await a.next(kind("loot"))).st.lockers[5], b.id);
  a.ws.close();                                                                      // Ann leaves with her gun: her locker is usable again
  const back = await b.next(m => m.t === "loot" && m.st.lockers[0] === 0); assert.equal(back.scene, "B1");
  assert.equal(back.st.lockers[5], b.id, "Bob keeps his");
  const c = await join(srv, "R22", "Cy"); c.send({t: "s", scene: "B1"}); await c.next(kind("loot"));
  c.send({t: "loot", k: "locker", i: 0}); assert.ok(await b.next(m => m.t === "loot" && m.st.lockers[0] === c.id), "a newcomer can use it");
  await srv.close();
});

test("ray gun: a shot needs the gun and a round, everyone else on the floor sees the beam, other floors and the shooter do not", async () => {
  const srv = await createServer({countdownMs: 100});
  const [a, b, c] = await round(srv, "R23", ["Ann", "Bob", "Cy"]);
  a.send({t: "s", scene: "B1", x: 1, y: -3, z: 2}); b.send({t: "s", scene: "B1", x: 2, y: -3, z: 2}); c.send({t: "s", scene: "L1", x: 1, y: 0, z: 2}); await a.quiet(150);
  const o = [1, -1.5, 2], d = [0, 0, -1];
  a.send({t: "shot", o, d, e: [1, -1.5, -20]}); assert.ok(!(await b.quiet(200)).some(m => m.t === "beam"), "no gun, no shot");
  a.send({t: "loot", k: "locker", i: 0}); await a.next(m => m.t === "me" && m.gun); await b.quiet(50);
  a.send({t: "shot", o, d, e: [1, -1.5, -20]});
  const beam = await b.next(kind("beam")); assert.deepEqual(beam.e, [1, -1.5, -20]);
  assert.equal((await a.next(m => m.t === "me" && m.rounds === 2)).rounds, 2, "the server counted the round");
  assert.ok(!(await a.quiet(150)).some(m => m.t === "beam"), "the shooter is told nothing back"); assert.ok(!(await c.quiet(10)).some(m => m.t === "beam"), "Cy is on another floor");
  a.send({t: "shot", o: [1, 2], d}); a.send({t: "shot", o: ["x", 0, 0], d}); a.send({t: "shot", o}); assert.ok(!(await b.quiet(150)).some(m => m.t === "beam"), "bad aims are dropped");
  await srv.close();
});

test("a thrown beacon needs one carried; the others on the floor learn where it lies; junk and other floors get nothing; beacons are taken once, two at most", async () => {
  const srv = await createServer();
  const a = await join(srv, "RB", "Ann"), b = await join(srv, "RB", "Bob"), c = await join(srv, "RB", "Cy");
  a.send({t: "s", scene: "L1", x: 0, y: 0, z: 0}); b.send({t: "s", scene: "L1", x: 1, y: 0, z: 0}); c.send({t: "s", scene: "L2", x: 0, y: 3.2, z: 0});
  await Promise.all([a, b, c].map(x => x.quiet(200)));
  a.send({t: "beacon", x: 3, z: 4}); assert.ok(!(await b.quiet(150)).some(m => m.t === "beacon"), "none carried");
  a.send({t: "loot", k: "beacon", i: 0}); assert.equal((await a.next(m => m.t === "me" && m.beacons === 1)).beacons, 1);
  a.send({t: "beacon", x: "x", z: 1}); a.send({t: "beacon", x: 1e9, z: 1}); assert.ok(!(await b.quiet(150)).some(m => m.t === "beacon"), "junk");
  a.send({t: "beacon", x: 3, z: 4});
  const got = await b.next(kind("beacon")); assert.deepEqual([got.x, got.z, got.from], [3, 4, a.id]);
  assert.ok(!(await c.quiet(100)).some(m => m.t === "beacon"), "another floor");
  b.send({t: "loot", k: "beacon", i: 0}); assert.ok(!(await b.quiet(150)).some(m => m.t === "loot" && m.by === b.id), "already taken");
  b.send({t: "loot", k: "beacon", i: 1}); b.send({t: "loot", k: "beacon", i: 1});
  await b.next(m => m.t === "me" && m.beacons === 1); await srv.close();
});

test("a flood of messages is dropped and the flooder disconnected, while others are served; a position off the map is ignored", async () => {
  const srv = await createServer();
  const a = await join(srv, "RF", "Ann"), b = await join(srv, "RF", "Bob");
  a.send({t: "s", scene: "B1", x: 1, y: -3, z: 2, yaw: 0}); b.send({t: "s", scene: "B1", x: 3, y: -3, z: 4, yaw: 0}); await a.quiet(150);
  b.send({t: "s", scene: "B1", x: 1e9, y: -3, z: 4, yaw: 0}); await a.quiet(120);
  assert.deepEqual([...srv.rooms.get("RF").players.values()].map(p => p.st && [p.st.x, p.st.z]).filter(Boolean)[1], [3, 4], "an impossible position was ignored");
  for (let i = 0; i < 3000; i++) a.send({t: "junk", n: i});
  await new Promise(r => setTimeout(r, 400));
  b.send({t: "s", scene: "B1", x: 5, y: -3, z: 6, yaw: 0}); const got = await a.next(m => m.t === "s" && m.x === 5, 2000).catch(() => null);
  assert.ok(got === null || got, "the server is still up"); assert.equal(a.ws.readyState === 3 || a.ws.readyState === 2 || a.ws.readyState === 1, true);
  await new Promise(r => setTimeout(r, 300)); assert.ok(a.ws.readyState >= 2, "the flooder was disconnected");
  await srv.close();
});

test("a room holds the manifest's maximum number of players, each with a different colour, and refuses one more", async () => {
  const max = REGISTRY.maxPlayers("original"), srv = await createServer(), cs = [];
  for (let i = 0; i < max; i++) cs.push(await join(srv, "FULL", "P" + i));
  const lobby = await cs[0].next(m => m.t === "lobby" && m.players.length === max);
  assert.equal(new Set(lobby.players.map(p => p.color)).size, max, "every player has their own colour");
  const extra = client(srv.port); await extra.open; extra.send({t: "join", room: "FULL", name: "Late"});
  await extra.next(kind("full"));
  assert.ok(!(await extra.quiet(100)).some(m => m.t === "welcome"), "the one over the limit is never welcomed");
  await srv.close();
});

test("stats: downs, deaths, revives, shots, hits, beacons and floor time reach the results and one log line without names", async () => {
  let t = 1000; const lines = [], srv = await createServer({countdownMs: 100, clock: () => t, log: l => lines.push(l)});
  const [a, b] = await round(srv, "R30", ["Ann", "Bob"]), room = srv.rooms.get("R30"), A = room.players.get(a.id).ps, B = room.players.get(b.id).ps;
  for (const c of [a, b]) c.send({t: "s", scene: "L4", x: 0, y: 0, z: 0});
  a.send({t: "power"}); await a.next(kind("power")); await a.quiet(300);
  // Ann is downed and Bob lifts her: a down and a revive given, no death
  PS.hit(A, 50, t); t += 2; PS.hit(A, 50, t); assert.ok(PS.isDown(A));
  b.send({t: "revive", to: a.id}); await a.next(kind("revived"));
  // Ann is downed again and nobody comes: the 45 s run out, which is a death
  t += 10; PS.hit(A, 50, t); t += 2; PS.hit(A, 50, t); t += PS.DOWNED_S + 1; await a.next(kind("me"), 2000); await a.quiet(300);
  // Bob shoots twice (one hits) and throws a beacon
  PS.gotLocker(B); PS.gotBeacon(B); room.floors.L4.shot = (p, o, d, spend) => spend() ? {r: p.id === b.id && B.stats.shots === 2 ? {i: 0} : null} : null;
  b.send({t: "shot", o: [0, 1.5, 0], d: [0, 0, -1]}); await b.quiet(100); t += 2; b.send({t: "shot", o: [0, 1.5, 0], d: [0, 0, -1]}); await b.quiet(100); t += 2;
  b.send({t: "beacon", x: 3, z: 3}); await b.quiet(150);
  assert.deepEqual([A.stats.downs, A.stats.deaths, A.stats.revives], [2, 1, 0]);
  assert.deepEqual([B.stats.revives, B.stats.shots, B.stats.hits, B.stats.beacons], [1, 2, 1, 1]);
  assert.ok(B.stats.floorMs.L4 > 100, "floor time is counted");
  assert.equal(lines.length, 0, "nothing logged before the round ends");
  a.send({t: "exit"}); await a.next(kind("exited")); b.send({t: "exit"});
  const r = await a.next(kind("results")), ann = r.rows.find(x => x.id === a.id), bob = r.rows.find(x => x.id === b.id);
  assert.equal(ann.name, "Ann", "the old fields stay");
  assert.deepEqual([ann.downs, ann.deaths, ann.revives], [2, 1, 0]); assert.deepEqual([bob.revives, bob.shots, bob.hits, bob.beacons], [1, 2, 1, 1]);
  assert.equal(bob.score, 1000 + 150 - Math.floor(bob.ms / 5000)); assert.equal(r.mode, "original"); assert.ok(r.floors.some(f => f.scene === "L4" && f.ms > 100));
  assert.equal(lines.length, 1, "one line per finished round");
  const rec = JSON.parse(lines[0]); assert.equal(rec.event, "run"); assert.equal(rec.roomCode, "R30"); assert.equal(rec.mode, "original");
  assert.ok(rec.endedAt >= rec.startedAt && rec.floors.some(f => f.scene === "L4"));
  assert.deepEqual(rec.players.map(p => p.place), [1, 2]); assert.deepEqual(rec.players.map(p => [p.downs, p.deaths, p.revives, p.shots]), [[2, 1, 0, 0], [0, 0, 1, 2]]);
  assert.ok(!/Ann|Bob/.test(lines[0]), "no names in the log");
  await b.next(kind("results")); await srv.close();
});
test("stats: a player who walks out and then disconnects still counts", async () => {
  const lines = [], srv = await createServer({countdownMs: 100, log: l => lines.push(l)});
  const [a, b] = await round(srv, "R31", ["Ann", "Bob"]), room = srv.rooms.get("R31");
  for (const c of [a, b]) c.send({t: "s", scene: "L4", x: 0, y: 0, z: 0});
  a.send({t: "power"}); await a.next(kind("power"));
  PS.gotBeacon(room.players.get(a.id).ps); a.send({t: "beacon", x: 2, z: 2}); await a.quiet(150);
  a.send({t: "exit"}); await b.next(kind("exited")); a.ws.close(); await b.quiet(100);
  b.send({t: "exit"}); const r = await b.next(kind("results"));
  assert.equal(r.rows.find(x => x.name === "Ann").beacons, 1, "Ann's numbers were taken when she walked out"); assert.equal(lines.length, 1);
  await srv.close();
});

// ---- session 4: modes and parties
const joinRaw = async (srv, msg) => { const c = client(srv.port); await c.open; c.send({t: "join", ...msg}); return c; };
const getJson = async (srv, p) => { const r = await fetch(`http://localhost:${srv.port}${p}`); return {status: r.status, body: await r.json()}; };

test("a join with no mode is the original; the room takes its floors, size and finish from the manifest", async () => {
  const srv = await createServer(), a = await join(srv, "MD1", "Ann"), w = a.welcome;
  assert.equal(w.mode, "original");
  assert.deepEqual(w.floors, REGISTRY.modes.original.floors);
  assert.equal(w.max, REGISTRY.maxPlayers("original"));
  assert.equal(w.finish, REGISTRY.modes.original.finish.scene);
  const b = await joinRaw(srv, {room: "MD2", name: "Bob", mode: "original"}); assert.equal((await b.next(kind("welcome"))).mode, "original");
  await srv.close();
});

test("a mode that is planned is refused with 'soon', an unknown one with 'unknown_mode', and neither crashes or opens a room", async () => {
  const srv = await createServer();
  const g = await joinRaw(srv, {room: "MD3", name: "Gus", mode: "going_back_in"});
  const r1 = await g.next(kind("refused")); assert.equal(r1.reason, "soon"); assert.equal(r1.mode, "going_back_in");
  const x = await joinRaw(srv, {room: "MD3", name: "Xi", mode: "nope"});
  assert.equal((await x.next(kind("refused"))).reason, "unknown_mode");
  const j = await joinRaw(srv, {room: "MD3", name: "Jo", mode: {}}); assert.equal((await j.next(kind("refused"))).reason, "unknown_mode");
  assert.equal(srv.rooms.size, 0);
  assert.ok(!(await g.quiet(50)).some(m => m.t === "welcome"));
  const ok = await join(srv, "MD3", "Ok"); assert.ok(ok.id, "the server still serves joins");
  await srv.close();
});

test("a party is one room per mode and code, whatever the letter case (guard; it also passes on main)", async () => {
  const srv = await createServer(), a = await join(srv, "KEY1", "Ann"), b = await join(srv, "key1", "Bob");
  assert.equal(srv.rooms.size, 1, "the same mode and code, in any case, is one room");
  assert.equal(b.welcome.players.length, 2);
  await srv.close();
});

test("GET /rooms?mode= lists open rooms with mode, code, players, max and state, and no names", async () => {
  const srv = await createServer({countdownMs: 60}), max = REGISTRY.maxPlayers("original");
  const a = await join(srv, "OPEN1", "Secretname"), b = await join(srv, "OPEN1", "Other");
  const full = []; for (let i = 0; i < max; i++) full.push(await join(srv, "FULLR", "F" + i));
  const c = await join(srv, "PLAY1", "Pat"); c.send({t: "ready", ready: true}); await c.next(kind("start"));
  const r = await getJson(srv, "/rooms?mode=original");
  assert.equal(r.status, 200);
  const by = Object.fromEntries(r.body.rooms.map(x => [x.code, x]));
  assert.deepEqual(by.OPEN1, {mode: "original", code: "OPEN1", players: 2, max, state: "lobby"});
  assert.equal(by.PLAY1.state, "playing");
  assert.ok(!by.FULLR, "a full room is not open");
  assert.ok(!JSON.stringify(r.body).match(/Secretname|Other|Pat/), "no player names");
  assert.equal((await getJson(srv, "/rooms?mode=going_back_in")).body.rooms.length, 0);
  assert.equal((await getJson(srv, "/rooms?mode=nope")).status, 400);
  assert.equal((await getJson(srv, "/rooms")).body.rooms.length, 2, "no mode: all modes");
  await srv.close();
});

test("ten players: ten colours in the lobby, all ten see each other on a floor, an eleventh is refused with the limit", async () => {
  const srv = await createServer({countdownMs: 60}), cs = [];
  for (let i = 0; i < 10; i++) cs.push(await join(srv, "TEN", "P" + i));
  const lobby = await cs[0].next(m => m.t === "lobby" && m.players.length === 10);
  assert.equal(new Set(lobby.players.map(p => p.color)).size, 10);
  for (const c of cs) c.send({t: "ready", ready: true});
  for (const c of cs) await c.next(kind("start"));
  cs.forEach((c, i) => c.send({t: "s", scene: "B1", x: i, y: -3, z: 0, yaw: 0}));
  await new Promise(r => setTimeout(r, 150));                           // everyone is on B1 now: a state from one reaches the other nine
  cs.forEach((c, i) => c.send({t: "s", scene: "B1", x: i, y: -3, z: 1, yaw: 0}));
  for (const c of cs) for (const o of cs) if (o !== c) await c.next(m => m.t === "s" && m.id === o.id && m.z === 1);
  const late = await joinRaw(srv, {room: "TEN", name: "Late"});
  const f = await late.next(kind("full")); assert.equal(f.max, 10);
  await srv.close();
});

test("go to a friend: the server tells you their floor and spot; refused for yourself, a stranger, or someone not on a floor", async () => {
  const srv = await createServer(), a = await join(srv, "GO", "Ann"), b = await join(srv, "GO", "Bob"), other = await join(srv, "GO2", "Zed");
  a.send({t: "goto", to: b.id}); await a.quiet(60);
  b.send({t: "s", scene: "L2", x: 5, y: 3.2, z: 6, yaw: 0}); await a.next(m => m.t === "p" && m.id === b.id);
  a.send({t: "goto", to: b.id});
  const g = await a.next(kind("goto")); assert.deepEqual([g.id, g.scene, g.x, g.y, g.z], [b.id, "L2", 5, 3.2, 6]);
  a.send({t: "goto", to: a.id}); a.send({t: "goto", to: other.id}); a.send({t: "goto", to: "x"});
  assert.ok(!(await a.quiet(100)).some(m => m.t === "goto"));
  await srv.close();
});
