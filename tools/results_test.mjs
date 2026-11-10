// The results screen in a solo round: time, deaths, revives, score, your best time, and the one-time welcome to Farway (flag `original_complete`).
// Usage: node tools/results_test.mjs      (needs Playwright + Chromium and internet for three.js from unpkg)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
// one context for the whole test so localStorage survives a reload, as it does for a player
const ctx = await browser.newContext({viewport: {width: 900, height: 700}});
async function solo() {
  const page = await ctx.newPage(); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  return page;
}
const screen = page => page.evaluate(() => ({shown: getComputedStyle(document.getElementById("results")).display !== "none",
  cells: [...document.querySelectorAll("#r-rows tr.me td")].map(td => td.textContent), best: document.getElementById("r-best").textContent,
  welcome: document.getElementById("r-welcome").hidden ? "" : document.getElementById("r-welcome").textContent,
  flag: (() => { try { return localStorage.getItem("original_complete"); } catch (e) { return "blocked"; } })()}));
try {
  const p = await solo();
  check("before the first finish there is no flag", (await screen(p)).flag === null);
  // fall once (alone, that is a death), get up, then walk out 10 minutes in
  await p.evaluate(() => { const g = window.__game; g.die(); g.respawn(); g.FIN.t0 = performance.now() - 600000; g.goOut(); });
  let s = await screen(p);
  check("the results screen shows", s.shown);
  check("it lists time, deaths, revives and score for you", s.cells.join("|") === "1|You|10:00|1|0|" + (1000 - 100 - 120), s.cells.join("|"));
  check("it shows your best time on this browser", /NEW RECORD 10:00/.test(s.best), s.best);
  check("the first finish welcomes you to Farway and sets original_complete", /Welcome to Farway/.test(s.welcome) && s.flag === "1", JSON.stringify([s.welcome, s.flag]));
  // a reload: the flag stays, there is no second welcome, and a slower run is not a new record
  await p.close(); const q = await solo();
  check("the flag survives a reload", (await screen(q)).flag === "1");
  await q.evaluate(() => { const g = window.__game; g.FIN.t0 = performance.now() - 900000; g.goOut(); });
  s = await screen(q);
  check("a second finish has no welcome", s.welcome === "", s.welcome);
  check("a slower run shows the old best", /^BEST 10:00/.test(s.best), s.best);
  check("no deaths this time, a lower score for the longer round", s.cells.slice(3).join("|") === "0|0|" + (1000 - 180), s.cells.join("|"));
  // storage that throws must not break the screen
  const r = await ctx.newPage(); r.on("pageerror", e => errors.push(e.message));
  await r.addInitScript(() => { Object.defineProperty(window, "localStorage", {get() { throw new Error("blocked"); }}); });
  await r.goto(`http://localhost:${srv.port}/`); await r.click("#l-solo");
  await r.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  await r.evaluate(() => { const g = window.__game; g.FIN.t0 = performance.now() - 60000; g.goOut(); });
  s = await r.evaluate(() => ({shown: getComputedStyle(document.getElementById("results")).display !== "none", welcome: document.getElementById("r-welcome").hidden}));
  check("with storage blocked the results still show, with no welcome", s.shown && s.welcome);
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
