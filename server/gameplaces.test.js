// Co-op inside the games (session 11, slice 2): a game room is a place like the parking lot. The server relays positions between the players of a room whose place is
// the same (`rdwe:teal`) and runs no rules there. The shipped manifest keeps both games solo only, so the co-op tests build a registry with it switched on.
import test from "node:test";
import assert from "node:assert/strict";
import {WebSocket} from "ws";
import {createServer} from "./server.js";
import {FARWAY} from "../shared/farway.manifest.js";
import {buildRegistry} from "../shared/manifest.js";

const coopDoc = structuredClone(FARWAY);
for (const a of coopDoc.areas) if (a.id === "rdwe" || a.id === "intern") a.coop = true;
for (const l of coopDoc.links) if (l.connector === "gate" && l.status === "built") delete l.soloOnly;
const COOP = buildRegistry(coopDoc);

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
// since #133 the way into Right Door, Wrong Exit is the meadow house, past the lot: the Original's flag opens it (the browser holds it, see presence.test.js)
async function join(srv, room, name) { const c = client(srv.port); await c.open; c.send({t: "join", room, name, flags: ["original_complete"]}); const w = await c.next(kind("welcome")); return Object.assign(c, {id: w.id, welcome: w}); }
const sees = async (srv, room, c, scene) => { const end = Date.now() + 2000; while (Date.now() < end) { if (srv.rooms.get(room).players.get(c.id).scene === scene) return true; await new Promise(r => setTimeout(r, 10)); } return false; };

test("shipped: a place in either game is accepted, a stage the Intern does not have is refused", async () => {
  const srv = await createServer(), a = await join(srv, "G0", "Ann");
  a.send({t: "s", scene: "intern:S9", x: 1, y: 0, z: 2, yaw: 0});
  await new Promise(r => setTimeout(r, 150));
  assert.equal(srv.rooms.get("G0").players.get(a.id).scene, null);
  a.send({t: "s", scene: "intern:S3", x: 1, y: 0, z: 2, yaw: 0});
  assert.ok(await sees(srv, "G0", a, "intern:S3"));
  a.send({t: "s", scene: "rdwe:teal", x: 1, y: 0, z: 2, yaw: 0});
  assert.ok(await sees(srv, "G0", a, "rdwe:teal"));
  await srv.close();
});

test("two players in the same game room get each other's positions; a third elsewhere in the game, and one on a floor, do not", async () => {
  const srv = await createServer({registry: COOP});
  const a = await join(srv, "G1", "Ann"), b = await join(srv, "G1", "Bob"), c = await join(srv, "G1", "Cy"), d = await join(srv, "G1", "Di");
  d.send({t: "s", scene: "L4", x: 0, y: 9.6, z: 20, yaw: 0});
  a.send({t: "s", scene: "rdwe:teal", x: 3, y: 0, z: -4, yaw: 0});
  b.send({t: "s", scene: "rdwe:teal", x: 5, y: 0, z: -2, yaw: 1});
  c.send({t: "s", scene: "rdwe:hallway", x: 1, y: 0, z: 1, yaw: 0});
  for (const [x, s] of [[a, "rdwe:teal"], [b, "rdwe:teal"], [c, "rdwe:hallway"], [d, "L4"]]) assert.ok(await sees(srv, "G1", x, s), `${x.id} is in ${s}`);
  assert.equal((await d.next(m => m.t === "p" && m.id === a.id)).scene, "rdwe:teal", "the rest of the room learns which place you are in");
  await Promise.all([a, b, c, d].map(x => x.quiet(50)));
  a.send({t: "s", scene: "rdwe:teal", x: 3.5, y: 0, z: -4.5, yaw: 0.5, moving: 1, crouch: 1, junk: "x", dead: 1, gun: 1});
  const got = await b.next(m => m.t === "s" && m.id === a.id);
  assert.deepEqual([got.scene, got.x, got.y, got.z, got.yaw, got.moving, got.crouch], ["rdwe:teal", 3.5, 0, -4.5, 0.5, 1, 1]);
  assert.ok(!got.dead && !got.gun && got.junk === undefined, "presence only: the server runs no rules inside a game");
  const others = await Promise.all([c, d].map(x => x.quiet(150)));
  assert.ok(others.every(box => !box.some(m => m.t === "s" && m.id === a.id)), "only the same place gets the snapshot");
  await srv.close();
});

test("a friend can jump to a player inside a game; leaving the game tells the others and does not touch theirs", async () => {
  const srv = await createServer({registry: COOP});
  const a = await join(srv, "G2", "Ann"), b = await join(srv, "G2", "Bob");
  a.send({t: "s", scene: "intern:S3", x: 2, y: 0, z: 7, yaw: 0}); assert.ok(await sees(srv, "G2", a, "intern:S3"));
  b.send({t: "goto", to: a.id});
  const g = await b.next(kind("goto"));
  assert.deepEqual([g.scene, g.x, g.y, g.z, g.refused], ["intern:S3", 2, 0, 7, undefined]);
  b.send({t: "s", scene: "intern:S3", x: 2, y: 0, z: 6, yaw: 0}); assert.ok(await sees(srv, "G2", b, "intern:S3"));
  await Promise.all([a, b].map(x => x.quiet(50)));
  a.send({t: "s", scene: "L4", x: 116.4, y: 9.6, z: 75, yaw: 0}); assert.ok(await sees(srv, "G2", a, "L4"));
  assert.equal((await b.next(m => m.t === "p" && m.id === a.id)).scene, "L4", "Bob sees Ann leave the game");
  assert.equal(srv.rooms.get("G2").players.get(b.id).scene, "intern:S3", "Bob is still in it");
  b.send({t: "s", scene: "intern:S4", x: 0, y: 0, z: 0, yaw: 0}); assert.ok(await sees(srv, "G2", b, "intern:S4"), "and can move on to another stage");
  b.send({t: "s", scene: "rdwe:nowhere", x: 0, y: 0, z: 0, yaw: 0});
  await new Promise(r => setTimeout(r, 150));
  assert.equal(srv.rooms.get("G2").players.get(b.id).scene, null, "a place the game does not have is refused");
  await srv.close();
});

test("a player inside a game does not hold the Original's finish: the others finish, and the one inside is not ranked", async () => {
  const srv = await createServer({registry: COOP, countdownMs: 20});
  const a = await join(srv, "G3", "Ann"), b = await join(srv, "G3", "Bob");
  a.send({t: "ready", ready: true}); b.send({t: "ready", ready: true}); await a.next(kind("start"));
  a.send({t: "s", scene: "L4", x: 0, y: 9.6, z: 20, yaw: 0});
  b.send({t: "s", scene: "rdwe:dining", x: 0, y: 0, z: 0, yaw: 0});
  assert.ok(await sees(srv, "G3", a, "L4") && await sees(srv, "G3", b, "rdwe:dining"));
  a.send({t: "power"}); await a.next(kind("power"));
  a.send({t: "exit"});
  const res = await a.next(kind("results"));
  assert.deepEqual(res.rows.map(r => r.id), [a.id], "Ann is ranked, Bob is still inside the game");
  await srv.close();
});

test("the room of a stage (sub) is relayed with a spot in a game, comes with a jump to a friend, and a bad one is dropped", async () => {
  const srv = await createServer();
  const a = await join(srv, "G5", "Ann"), b = await join(srv, "G5", "Bob");
  b.send({t: "s", scene: "intern:S3", x: 0, y: 0, z: 0, yaw: 0}); assert.ok(await sees(srv, "G5", b, "intern:S3"));
  a.send({t: "s", scene: "intern:S3", x: 1, y: 0, z: 2, yaw: 0.5, sub: "S3_H"});
  const s = await b.next(m => m.t === "s" && m.id === a.id);
  assert.deepEqual([s.scene, s.x, s.z, s.sub], ["intern:S3", 1, 2, "S3_H"]);
  b.send({t: "goto", to: a.id});
  assert.equal((await b.next(kind("goto"))).sub, "S3_H", "the friend's room comes with their place");
  for (const bad of ["<script>", "x".repeat(25), 7, ""]) {
    a.send({t: "s", scene: "intern:S3", x: 3, y: 0, z: 4, yaw: 0, sub: bad});
    const t = await b.next(m => m.t === "s" && m.id === a.id && m.x === 3);
    assert.equal(t.sub, undefined, `sub ${JSON.stringify(bad)} is not relayed`);
  }
  a.send({t: "s", scene: "L4", x: 1, y: 9.6, z: 2, yaw: 0, sub: "S3_H"});
  assert.ok(await sees(srv, "G5", a, "L4"));
  assert.equal(srv.rooms.get("G5").players.get(a.id).st.sub, undefined, "a floor has no sub");
  await srv.close();
});
