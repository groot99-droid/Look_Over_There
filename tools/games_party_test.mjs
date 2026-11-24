// Right Door, Wrong Exit in a party room (session 11, slice 3): two players of one room enter the game separately, meet in one place, see each other, and leave
// without breaking the other's game. Uses the real server and two headless pages. The Intern is still solo only and must still refuse in a room.
// Usage: node tools/games_party_test.mjs     (needs Playwright + Chromium; run from the repo root)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
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
const GATE = "DoorLeaf_Gate_RDW";
// L4 -> the gate door -> the passage "T" -> its far door -> the game runs (the game mount is shown)
async function enter(page, door) {
  await page.evaluate(async door => {
    const g = window.__game; if (g.S.id !== "L4") await g.loadScene("L4");
    const dr = g.doors.find(d => d.d.name === door); g.teleport([dr.cx, g.S.floor, dr.cz]); g.openDoor(dr, true);
  }, door);
  if (!await until(page, () => window.__game.S.id === "T" && !window.__game.loading)) return false;
  await page.evaluate(() => { const g = window.__game, dr = g.doors.find(d => d.link && d.link.game); g.openDoor(dr, true); });
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
  // Ann quits the game: she is back on L4 at the gate's arrival point, Bob's game goes on
  await a.evaluate(async () => (await import("./games/rdwe/walk.js")).cancel());
  check("Ann is back on L4 at the arrival point", await until(a, () => window.__game.S.id === "L4" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000)
    && await a.evaluate(() => { const p = window.__game.P.p; return Math.hypot(p.x + 121.2, p.z - 63.6) < 2.5; }));
  check("the server has Ann on L4 and Bob still in the game", await serverPlace(aid, "L4") && placeOf(bid) === "rdwe:dining", `${placeOf(aid)} / ${placeOf(bid)}`);
  const sb2 = await gameState(b);
  check("Bob's game is still running, alone now", !!sb2 && sb2.peers === 0, JSON.stringify(sb2));
  await b.evaluate(async () => (await import("./games/rdwe/walk.js")).cancel());
  check("Bob comes back to L4 too", await until(b, () => window.__game.S.id === "L4" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000));
  // the Intern is still solo only
  await a.evaluate(() => { const g = window.__game, dr = g.doors.find(d => d.d.name === "DoorLeaf_Gate_ITN"); g.teleport([dr.cx, g.S.floor, dr.cz]); g.openDoor(dr, true); });
  const toast = await a.evaluate(() => document.getElementById("toast")?.textContent || "");
  check("the Intern's gate still does not open in a room", /does not open in a room/.test(toast) && await a.evaluate(() => window.__game.S.id) === "L4", toast);
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
