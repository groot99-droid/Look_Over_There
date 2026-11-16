// Presence in page scenes (session 17): a room's players can be together in a scene the manifest marks `presence` (the parking lot, then the street). The server only
// relays who is in which scene and where; it runs no rules there. The Original's floors are unchanged (server.test.js).
import test from "node:test";
import assert from "node:assert/strict";
import {WebSocket} from "ws";
import {createServer} from "./server.js";
import {REGISTRY} from "../shared/registry.js";

function client(port) {
  const ws = new WebSocket(`ws://localhost:${port}/ws`), inbox = [], waiters = [];
  ws.on("message", d => { const m = JSON.parse(d); inbox.push(m); waiters.splice(0).forEach(w => w()); });
  return {ws, inbox, send: m => ws.send(JSON.stringify(m)), open: new Promise(r => ws.on("open", r)),
    async next(pred, ms = 2000) {
      const end = Date.now() + ms;
      for (;;) {
        const i = inbox.findIndex(pred); if (i >= 0) return inbox.splice(i, 1)[0];
        if (Date.now() > end) throw new Error("timed out waiting for a message");
        await new Promise(r => { waiters.push(r); setTimeout(r, 50); });
      }
    },
    quiet: async ms => { await new Promise(r => setTimeout(r, ms)); return inbox.splice(0); }};
}
const kind = t => m => m.t === t;
async function join(srv, room, name, extra = {}) { const c = client(srv.port); await c.open; c.send({t: "join", room, name, ...extra}); const w = await c.next(kind("welcome")); return Object.assign(c, {id: w.id, welcome: w}); }
const DONE = ["original_complete"];
const playerOf = (srv, room, c) => srv.rooms.get(room).players.get(c.id);
// waits for the server's own view of a player (what it relays from), not for a delay
const serverSees = async (srv, room, c, scene) => { const end = Date.now() + 2000; while (Date.now() < end) { if (playerOf(srv, room, c).scene === scene) return true; await new Promise(r => setTimeout(r, 10)); } return false; };

test("the manifest's presence scenes are the ones the server accepts", () => {
  assert.ok(Object.hasOwn(REGISTRY.presence, "parking_lot"));
});

test("two players of a room in the parking lot get each other's positions; a player on a floor does not, and the lot does not get the floor's", async () => {
  const srv = await createServer();
  const a = await join(srv, "P1", "Ann", {flags: DONE}), b = await join(srv, "P1", "Bob", {flags: DONE}), c = await join(srv, "P1", "Cy");
  c.send({t: "s", scene: "L4", x: 1, y: 9.6, z: 2, yaw: 0});
  a.send({t: "s", scene: "parking_lot", x: -8, y: 9.6, z: 43.6, yaw: 0});
  b.send({t: "s", scene: "parking_lot", x: -6, y: 9.6, z: 42, yaw: 1});
  assert.ok(await serverSees(srv, "P1", a, "parking_lot") && await serverSees(srv, "P1", b, "parking_lot") && await serverSees(srv, "P1", c, "L4"));
  assert.deepEqual((await c.next(m => m.t === "p" && m.id === a.id)).scene, "parking_lot", "the rest of the room learns which scene you are in");
  await Promise.all([a, b, c].map(x => x.quiet(50)));
  a.send({t: "s", scene: "parking_lot", x: -7, y: 9.6, z: 40, yaw: 0.5, moving: 1, run: 1, crouch: 0, junk: "x", dead: 1});
  const got = await b.next(m => m.t === "s" && m.id === a.id);
  assert.deepEqual([got.scene, got.x, got.y, got.z, got.yaw, got.moving, got.run], ["parking_lot", -7, 9.6, 40, 0.5, 1, 1]);
  assert.equal(got.junk, undefined, "a presence snapshot carries only what presence needs");
  assert.ok(!got.dead && !got.gun && !got.cloak, "nobody is down, armed or cloaked in a presence scene: the server runs no rules there");
  c.send({t: "s", scene: "L4", x: 3, y: 9.6, z: 4, yaw: 0});
  b.send({t: "s", scene: "parking_lot", x: -6, y: 9.6, z: 41, yaw: 1});
  await a.next(m => m.t === "s" && m.id === b.id);
  const [toA, , toC] = await Promise.all([a, b, c].map(x => x.quiet(150)));
  assert.ok(!toC.some(m => m.t === "s"), "the player on L4 gets no positions from the lot");
  assert.ok(!toA.some(m => m.t === "s" && m.id === c.id), "and the lot gets none from L4");
  assert.deepEqual(Object.keys(srv.rooms.get("P1").floors), ["L4"], "the server runs L4 and nothing for the lot");
  await srv.close();
});

test("without original_complete a player cannot be in the lot: nothing is relayed, and they are told what is missing", async () => {
  const srv = await createServer();
  const a = await join(srv, "P2", "Ann", {flags: DONE}), b = await join(srv, "P2", "Bob");
  a.send({t: "s", scene: "parking_lot", x: -8, y: 9.6, z: 43.6, yaw: 0});
  assert.ok(await serverSees(srv, "P2", a, "parking_lot"));
  await Promise.all([a, b].map(x => x.quiet(50)));
  b.send({t: "s", scene: "parking_lot", x: -6, y: 9.6, z: 42, yaw: 0});
  assert.deepEqual(await b.next(kind("noentry")), {t: "noentry", scene: "parking_lot", missing: ["original_complete"]});
  b.send({t: "s", scene: "parking_lot", x: -6, y: 9.6, z: 41, yaw: 0});
  a.send({t: "s", scene: "parking_lot", x: -8, y: 9.6, z: 43, yaw: 0});
  const [toA, toB] = await Promise.all([a, b].map(x => x.quiet(150)));
  assert.equal(playerOf(srv, "P2", b).scene, null, "the server has them nowhere");
  assert.ok(!toA.some(m => m.t === "s" || (m.t === "p" && m.scene === "parking_lot")), "Ann never sees Bob in the lot");
  assert.ok(!toB.some(m => m.t === "s"), "and Bob gets no positions from it");
  assert.ok(!toB.some(m => m.t === "noentry"), "told once, not fifteen times a second");
  // the flag can arrive later (the browser holds it): then the way is open. Unknown flags are dropped.
  b.send({t: "flags", flags: ["original_complete", "made_up", 7]});
  b.send({t: "s", scene: "parking_lot", x: -6, y: 9.6, z: 41, yaw: 0});
  assert.ok(await serverSees(srv, "P2", b, "parking_lot"));
  assert.deepEqual([...playerOf(srv, "P2", b).flags], ["original_complete"]);
  await srv.close();
});

test("finishing the round in a room is the server's own proof of original_complete", async () => {
  const srv = await createServer({countdownMs: 20});
  const a = await join(srv, "P3", "Ann");
  a.send({t: "ready", ready: true}); await a.next(kind("start"));
  a.send({t: "s", scene: "L4", x: 0, y: 9.6, z: 20, yaw: 0}); a.send({t: "power"}); await a.next(kind("power"));
  assert.equal(playerOf(srv, "P3", a).flags.has("original_complete"), false);
  a.send({t: "exit"}); await a.next(kind("results"));
  assert.equal(playerOf(srv, "P3", a).flags.has("original_complete"), true);
  a.send({t: "s", scene: "parking_lot", x: -8, y: 9.6, z: 43.6, yaw: 0});
  assert.ok(await serverSees(srv, "P3", a, "parking_lot"));
  await srv.close();
});

test("a presence scene is not a floor: no floor time, no exit, no shots or loot from it, and a newcomer learns who is where", async () => {
  const logs = [], srv = await createServer({countdownMs: 20, log: l => logs.push(JSON.parse(l))});
  const a = await join(srv, "P4", "Ann", {flags: DONE}), b = await join(srv, "P4", "Bob");
  a.send({t: "ready", ready: true}); b.send({t: "ready", ready: true}); await a.next(kind("start"));
  a.send({t: "s", scene: "parking_lot", x: 0, y: 9.6, z: 30, yaw: 0});          // a client that claims the flag stands in the lot while the round runs
  b.send({t: "s", scene: "L4", x: 0, y: 9.6, z: 20, yaw: 0});
  assert.ok(await serverSees(srv, "P4", a, "parking_lot") && await serverSees(srv, "P4", b, "L4"));
  b.send({t: "power"}); await b.next(kind("power"));
  a.send({t: "exit"}); a.send({t: "shot", o: [0, 11, 30], d: [0, 0, -1]}); a.send({t: "loot", k: "pack", i: 0}); a.send({t: "door", name: "DoorLeaf_Stair_L3_L4_down", open: 1});
  await new Promise(r => setTimeout(r, 250));
  assert.deepEqual(srv.rooms.get("P4").run.exits, [], "the lot is not the store: you cannot finish the round from it");
  const late = await join(srv, "P4", "Cy");
  assert.deepEqual(late.welcome.players.map(p => [p.name, p.scene]).sort(), [["Ann", "parking_lot"], ["Bob", "L4"], ["Cy", null]]);
  a.send({t: "s", scene: "L4", x: 0, y: 9.6, z: 20, yaw: 0}); assert.ok(await serverSees(srv, "P4", a, "L4"));
  for (const c of [a, b, late]) { c.send({t: "s", scene: "L4", x: 0, y: 9.6, z: 20, yaw: 0}); c.send({t: "exit"}); }
  await a.next(kind("results"));
  assert.deepEqual(logs.find(l => l.event === "run").floors.map(f => f.scene), ["L4"], "time is counted on floors only");
  await srv.close();
});

test("a position far off a presence scene is ignored, and leaving the room tells the lot", async () => {
  const srv = await createServer();
  const a = await join(srv, "P5", "Ann", {flags: DONE}), b = await join(srv, "P5", "Bob", {flags: DONE});
  for (const c of [a, b]) c.send({t: "s", scene: "parking_lot", x: -8, y: 9.6, z: 43.6, yaw: 0});
  assert.ok(await serverSees(srv, "P5", a, "parking_lot") && await serverSees(srv, "P5", b, "parking_lot"));
  await b.quiet(50);
  a.send({t: "s", scene: "parking_lot", x: 1e6, y: 9.6, z: "nope", yaw: 0});
  const got = await b.next(m => m.t === "s" && m.id === a.id);
  assert.deepEqual([got.x, got.z], [-8, 43.6], "the player stays where they were");
  a.ws.close();
  assert.equal((await b.next(kind("leave"))).id, a.id);
  await srv.close();
});

test("go to a friend in a page scene: their scene and spot if you may enter it, a refusal naming the flag if not; floors as before", async () => {
  const srv = await createServer();
  const a = await join(srv, "P6", "Ann", {flags: DONE}), b = await join(srv, "P6", "Bob", {flags: DONE}), c = await join(srv, "P6", "Cy");
  a.send({t: "s", scene: "parking_lot", x: -8, y: 9.6, z: 43.6, yaw: 0}); c.send({t: "s", scene: "L2", x: 5, y: 3.2, z: 6, yaw: 0});
  assert.ok(await serverSees(srv, "P6", a, "parking_lot") && await serverSees(srv, "P6", c, "L2"));
  b.send({t: "goto", to: a.id});
  assert.deepEqual(await b.next(kind("goto")), {t: "goto", id: a.id, scene: "parking_lot", x: -8, y: 9.6, z: 43.6});
  c.send({t: "goto", to: a.id});
  assert.deepEqual(await c.next(kind("goto")), {t: "goto", id: a.id, scene: "parking_lot", refused: "requires", missing: ["original_complete"]}, "no spot is given away with a refusal");
  a.send({t: "goto", to: c.id});
  assert.deepEqual(await a.next(kind("goto")), {t: "goto", id: c.id, scene: "L2", x: 5, y: 3.2, z: 6}, "from the lot back to a friend on a floor");
  await srv.close();
});
