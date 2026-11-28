// Right Door, Wrong Exit in a party room (session 11, slice 3): two players of one room enter the game separately, meet in one place, see each other, go on through
// the rooms (each its own place), and leave without breaking the other's game; a round that ends meanwhile gives the one in the game the results on the way back. Uses the real server and two headless pages. The Intern has its own: tools/intern_party_test.mjs.
// Usage: node tools/games_party_test.mjs     (needs Playwright + Chromium; run from the repo root)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {MEADOW} from "../shared/forest.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failed = 0; const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const srv = await createServer({port: 0, countdownMs: 500});
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const errors = [];
const open = async (name, char) => {
  const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage(); page.on("pageerror", e => errors.push(`${name}: ${e.message}`));
  await page.goto(`http://localhost:${srv.port}/?room=GAMES&name=${name}&char=${char}&auto=1&ready=1`);
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000}); return page;
};
const wait = (fn, arg, ms = 90000) => Promise.resolve(fn).then(f => f(arg, ms));
const until = (page, fn, arg, ms = 90000) => page.waitForFunction(fn, arg, {timeout: ms, polling: 100}).then(() => true, () => false);
const room = () => srv.rooms.get("GAMES");
const placeOf = id => room().players.get(id)?.scene;
const serverPlace = async (id, want, ms = 20000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (placeOf(id) === want) return true; await sleep(100); } return false; };
// since #133 the way in is the meadow house's door (the balloon house and its gate on L4's lot are gone), and a room can follow it (the owner, 2026-11-27).
// The meadow is past the parking lot, so the room's server lets you be there only with the Original's flag: the page holds it, and tells the server.
const GATE = "meadow house";
async function enter(page) {
  await page.evaluate(async door => {
    const g = window.__game;
    try { localStorage.setItem("original_complete", "1"); } catch (e) {}
    g.net.send({t: "flags", flags: ["original_complete"]});
    if (g.S.id !== "meadow") await g.loadScene("meadow", {pos: [door.at[0], 0, door.at[1] + 0.5], face: [0, -1]});
    g.teleport([door.at[0], 0, door.at[1]]); g.doAction();
  }, MEADOW.house.door);
  return until(page, () => document.getElementById("gamemount").style.display === "block");
}
const gameState = page => page.evaluate(async () => { const c = (await import("./games/rdwe/walk.js")).debug.current; return c ? {peers: c.peerCount(), at: c.controls.position().toArray()} : null; });
try {
  const a = await open("Ann", 0), b = await open("Bob", 3);
  await Promise.all([a, b].map(p => p.waitForFunction(() => window.__game.net.phase === "playing" && !window.__game.loading, null, {timeout: 120000})));
  const aid = await a.evaluate(() => window.__game.net.id), bid = await b.evaluate(() => window.__game.net.id);
  check("Ann goes through the gate in a room and the game runs", await enter(a, GATE));
  check("the server has Ann in the game's first room", await serverPlace(aid, "rdwe:dining"), String(placeOf(aid)));
  check("Bob goes through the same gate and the game runs for him", await enter(b, GATE));
  check("the server has Bob in the same room: one place, two players", await serverPlace(bid, "rdwe:dining"), String(placeOf(bid)));
  await until(a, async () => (await import("./games/rdwe/walk.js")).debug.current?.peerCount() === 1, null, 20000);
  const sa = await gameState(a), sb = await gameState(b);
  check("each sees the other in the game", sa && sb && sa.peers === 1 && sb.peers === 1, JSON.stringify({sa, sb}));
  // Ann walks somewhere else in the room: Bob's figure of her follows
  await a.evaluate(async () => { const c = (await import("./games/rdwe/walk.js")).debug.current, p = c.controls.position(); window.__annTo = [p.x + 1.5, p.y, p.z + 1.5]; c.controls.setPosition(...window.__annTo); });
  const to = await a.evaluate(() => window.__annTo);
  const followed = await until(b, async to => { const f = (await import("./games/rdwe/walk.js")).debug.current.peerPositions()[0]; return !!f && Math.hypot(f[0] - to[0], f[2] - to[2]) < 0.5; }, to, 20000);
  check("Bob's figure of Ann follows her", followed);
  // Ann finishes the first room: she is in the next one, a different place, and Bob (still in the first) no longer sees her
  const ROOMS = ["dining", "hallway", "teal", "teal2", "flooded", "trampoline", "grocery"], REACH = 2000, Y_MIN = -20, Y_MAX = 30;          // the server's limits on a relayed position (server/server.js)
  const finishRoom = page => page.evaluate(async () => (await import("./games/rdwe/walk.js")).debug.current.finish("reached"));
  const inRoom = (page, id) => until(page, async id => { const c = (await import("./games/rdwe/walk.js")).debug.current; return !!c && c.built.meta.id === id; }, id, 150000);
  // what a room's walker can send: the walkable extent, the eye height at the start, and (for the endless room) where the wrap puts a walker who went past it
  const extent = page => page.evaluate(async () => {
    const c = (await import("./games/rdwe/walk.js")).debug.current, b = {...c.built.bounds}, eye = c.camera.position.y;
    if (c.built.wrap) {          // the edge is the last position, going out in half-metre steps, that the wrap leaves alone (a wrap the probe caused is undone by one the other way)
      const p = c.controls.position(), [x0, y0, z0] = [p.x, p.y, p.z];
      const edge = dir => { let z = z0; for (let i = 0; i < 4000; i++) { c.controls.setPosition(x0, y0, z + dir * 0.5); if (c.built.wrap(c.controls.position())) { c.built.wrap({z: -dir * 1e9}); break; } z += dir * 0.5; } c.controls.setPosition(x0, y0, z0); return z; };
      b.minZ = Math.max(b.minZ, edge(-1)); b.maxZ = Math.min(b.maxZ, edge(1));
    }
    return {b, eye};
  });
  const fits = e => !!e && [e.b.minX, e.b.maxX, e.b.minZ, e.b.maxZ].every(v => Number.isFinite(v) && Math.abs(v) <= REACH) && e.eye > Y_MIN && e.eye < Y_MAX;
  const ext = {dining: await extent(a)};
  await finishRoom(a);
  check("Ann finishes the first room and the second one runs", await inRoom(a, "hallway"));
  check("the server has Ann in the second room and Bob in the first", await serverPlace(aid, "rdwe:hallway") && placeOf(bid) === "rdwe:dining", `${placeOf(aid)} / ${placeOf(bid)}`);
  check("two rooms of one game are two places: neither sees the other", await until(b, async () => (await import("./games/rdwe/walk.js")).debug.current?.peerCount() === 0, null, 20000) && (await gameState(a))?.peers === 0);
  await finishRoom(b);
  check("Bob finishes the first room too and the second one runs for him", await inRoom(b, "hallway"));
  check("the server has both in the second room", await serverPlace(bid, "rdwe:hallway") && placeOf(aid) === "rdwe:hallway", `${placeOf(aid)} / ${placeOf(bid)}`);
  check("they see each other again in the second room", await until(a, async () => (await import("./games/rdwe/walk.js")).debug.current?.peerCount() === 1, null, 20000) && await until(b, async () => (await import("./games/rdwe/walk.js")).debug.current?.peerCount() === 1, null, 20000));
  // Ann walks the rest of the chain alone: every room is a place the server accepts, and every room's walkable extent is inside what the server relays
  ext.hallway = await extent(a);
  for (const id of ROOMS.slice(2)) {
    await finishRoom(a);
    const ran = await inRoom(a, id);
    check(`Ann reaches the room "${id}" and the server has her there`, ran && await serverPlace(aid, `rdwe:${id}`), String(placeOf(aid)));
    if (ran) ext[id] = await extent(a);
  }
  for (const id of ROOMS) check(`positions in the room "${id}" are inside the server's limits`, fits(ext[id]), JSON.stringify(ext[id]));
  // the Blender rooms off the story are places too: Ann goes through the grocery's stockroom door into the vending room (games/rdwe/blender_rooms.js), and back
  const jump = (page, room, via) => page.evaluate(async ([room, via]) => (await import("./games/rdwe/walk.js")).debug.current.jump(room, via), [room, via]);
  await jump(a, "vending_room", "machine");
  check("Ann reaches a room off the story (the vending room) and the server has her there", await inRoom(a, "vending_room") && await serverPlace(aid, "rdwe:vending_room"), String(placeOf(aid)));
  check(`positions in the vending room are inside the server's limits`, fits(await extent(a)));
  await jump(a, "grocery", "stockroom");
  check("and back into the grocery", await inRoom(a, "grocery") && await serverPlace(aid, "rdwe:grocery"), String(placeOf(aid)));
  check("Bob is still in the second room, alone", placeOf(bid) === "rdwe:hallway" && (await gameState(b))?.peers === 0, String(placeOf(bid)));
  // Ann finishes the last room: she is back in the meadow in front of the house (its link's returnTo), Bob's game goes on
  await finishRoom(a);
  check("Ann is back in the meadow, in front of the house", await until(a, () => window.__game.S.id === "meadow" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000)
    && await a.evaluate(([x, z]) => { const p = window.__game.P.p; return Math.hypot(p.x - x, p.z - z) < 2.5; }, [MEADOW.returnHouse.arrive[0], MEADOW.returnHouse.arrive[2]]));
  check("the server has Ann in the meadow and Bob still in the game", await serverPlace(aid, "meadow") && placeOf(bid) === "rdwe:hallway", `${placeOf(aid)} / ${placeOf(bid)}`);
  const sb2 = await gameState(b);
  check("Bob's game is still running", !!sb2 && sb2.peers === 0, JSON.stringify(sb2));
  await a.evaluate(() => window.__game.loadScene("L4")); await until(a, () => window.__game.S.id === "L4" && !window.__game.loading);          // back up to the store for the finish (the Intern in a room has its own test: tools/intern_party_test.mjs)
  // Ann finishes the Original while Bob is in the game: the round ends without him, and he gets the results when he comes back (docs/ROUND.md section D)
  for (const p of room().players.values()) p.ps.immUntil = 1e15;          // the server's immunity: this part is about the results, not the monsters
  await a.evaluate(() => { const g = window.__game, sp = g.S.pw.spot; g.P.imm = 99; g.P.p.set(sp[0] + 1.2, g.S.floor + 0.02, sp[1]); g.P.v.set(0, 0, 0); });
  await a.keyboard.press("KeyX");
  check("the L4 switch sets off the alarm", await until(a, () => window.__game.POWER.on && window.__game.FIN.alarmUntil > 0, null, 60000));
  await a.evaluate(() => { const g = window.__game; g.P.imm = 99; g.P.p.set(0, g.S.floor + 0.02, g.EXIT_Z + 0.5); g.step(0.02); });
  check("Ann walks out and gets the results: the round does not wait for the player in the game", await until(a, () => !!window.__game.FIN.results, null, 60000));
  const rows = room().final || [];
  check("the results rank Ann alone", rows.length === 1 && rows[0].id === aid, JSON.stringify(rows.map(r => r.name)));
  check("Bob, in the game, holds the results and is not shown them", await until(b, () => !!window.__game.net.heldResults, null, 20000) && await b.evaluate(() => !window.__game.FIN.results && getComputedStyle(document.getElementById("results")).display === "none" && document.getElementById("gamemount").style.display === "block"));
  check("and his game is still running", !!(await gameState(b)));
  await b.evaluate(async () => (await import("./games/rdwe/walk.js")).cancel());
  check("Bob comes back out of the house, to the meadow", await until(b, () => window.__game.S.id === "meadow" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000));
  check("and is shown the results then", await until(b, () => !!window.__game.FIN.results && !window.__game.net.heldResults && getComputedStyle(document.getElementById("results")).display === "flex", null, 20000)
    && await b.evaluate(() => [...document.querySelectorAll("#r-rows tr")].filter(r => r.querySelector("td")).length === 1));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
