// The two game gates on L4, in solo play: walk to the gate, go through the passage, enter the game, end it the way it ends normally,
// and check the player is back on L4 at the arrival point in the gate's link (world/L4.json).
//   Right Door, Wrong Exit: the room chain is cancelled (walk.cancel(), what a player quitting does) or finishes ("reached" for every room)
//   The Intern: the game window posts "intern-ending"
// Also: in a room a gate does not open and the toast comes from the manifest's soloOnly flag.
// Usage: node tools/gates_test.mjs     (needs Playwright + Chromium; run from the repo root)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const srv = await createServer({port: 0, countdownMs: 60000});
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const errors = [];
const solo = async () => {
  const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage(); page.on("pageerror", e => errors.push(e.message)); if (process.env.GATES_DEBUG) page.on("console", m => console.log("[console]", m.text().slice(0, 200)));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  return page;
};
const wait = (page, fn, arg, ms = 60000) => page.waitForFunction(fn, arg, {timeout: ms, polling: 100}).then(() => true, () => false);
// L4 -> gate door open -> passage "T" -> its far door open -> the game is running (inGame is not exposed: the game mount is visible)
async function enter(page, door) {
  await page.evaluate(async door => {
    const g = window.__game; if (g.S.id !== "L4") await g.loadScene("L4");
    const dr = g.doors.find(d => d.d.name === door); const [hx, , hz] = [dr.cx, 0, dr.cz];
    g.teleport([hx - dr.dir[1] * 0, g.S.floor, hz + 0.0]);      // on the door line: enough to open it; the passage keeps the way back from where we stood
    g.openDoor(dr, true);
  }, door);
  if (!await wait(page, () => window.__game.S.id === "T" && !window.__game.loading)) return false;
  await page.evaluate(() => { const g = window.__game, dr = g.doors.find(d => d.link && d.link.game); g.openDoor(dr, true); });
  return wait(page, () => document.getElementById("gamemount").style.display === "block");
}
const where = page => page.evaluate(() => { const g = window.__game; return {id: g.S.id, p: g.P.p.toArray().map(v => +v.toFixed(2)), loading: g.loading}; });
const near = (a, b, d = 2.5) => Math.hypot(a[0] - b[0], a[2] - b[2]) < d && Math.abs(a[1] - b[1]) < 1;
async function back(name, page, link) {
  if (process.env.GATES_DEBUG) for (let i = 0; i < 6; i++) { console.log("[state]", JSON.stringify(await page.evaluate(() => ({id: window.__game.S.id, loading: window.__game.loading, mount: document.getElementById("gamemount").style.display, fr: !!document.querySelector("#gamemount iframe"), fade: document.getElementById("gamefade").style.opacity})))); await new Promise(r => setTimeout(r, 5000)); }
  const ok = await wait(page, () => window.__game.S.id !== "T" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000);
  const w = await where(page);
  check(`${name}: back on L4`, ok && w.id === "L4", JSON.stringify(w));
  check(`${name}: at the arrival point in the link`, near(w.p, link.arrive), `${JSON.stringify(w.p)} vs ${JSON.stringify(link.arrive)}`);
}
try {
  const L4 = await (await fetch(`http://localhost:${srv.port}/world/L4.json`)).json();
  const linkOf = name => L4.doors.find(d => d.name === name).link;
  const cases = [
    ["Right Door, Wrong Exit (cancelled)", "DoorLeaf_Gate_RDW", p => p.evaluate(async () => (await import("./games/rdwe/walk.js")).cancel())],
    ["The Intern (intern-ending)", "DoorLeaf_Gate_ITN", p => p.evaluate(() => { const fr = document.querySelector("#gamemount iframe"); fr.contentWindow.eval("parent.postMessage({type: \"intern-ending\"}, \"*\")"); })],   // posted from inside the game window, as the game does
  ];
  const only = process.argv.find(a => a.startsWith("--only="))?.slice(7);        // --only=ITN or --only=RDW
  for (const [name, door, end] of cases) {
    if (only && !door.endsWith(only)) continue;
    const link = linkOf(door), page = await solo();      // a page per game: a game that fails to return leaves its page stuck
    const entered = await enter(page, door);
    check(`${name}: the gate takes us into the game`, entered);
    if (entered) { await new Promise(r => setTimeout(r, 4000)); await end(page); }
    await back(name, page, link);
  }
  // the manifest says both gates are solo only; in a room the door refuses and says so
  check("the manifest marks both gates soloOnly", REGISTRY.links.filter(l => l.connector === "gate" && l.status === "built").every(l => l.soloOnly));
  const room = await (await browser.newContext({viewport: {width: 320, height: 200}})).newPage();
  await room.goto(`http://localhost:${srv.port}/?room=GATES&name=Ann&char=0&auto=1&ready=1`);
  await room.waitForFunction(() => window.__game && !document.getElementById("load") && window.__game.net.phase === "playing", null, {timeout: 240000});
  await room.evaluate(async () => { const g = window.__game; await g.loadScene("L4"); const dr = g.doors.find(d => d.d.name === "DoorLeaf_Gate_RDW"); g.openDoor(dr, true); });
  const toast = await room.evaluate(() => document.getElementById("toast")?.textContent || "");
  const stayed = await room.evaluate(() => window.__game.S.id);
  check("in a room a soloOnly gate does not open and says so", /does not open in a room/.test(toast) && stayed === "L4", `${toast} / ${stayed}`);
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
