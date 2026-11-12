// The trash truck worker's route (slice 11): start the shift at 41 Hallam Row, empty the eight bins at the kerb with F, clock out at the depot. $2 a bin, $4 more
// for the whole route on time. Running out of time or leaving the street ends the shift and pays the bins only.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/trash_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, DOORS, BUS_STREET} from "../shared/city.js";
import {BINS, routeEnds} from "../shared/trash.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const page = await browser.newPage({viewport: {width: 900, height: 700}}); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const stand = (x, z, yaw = 0) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const tr = () => page.evaluate(() => { const g = window.__game, t = g.CITY.tr; return {active: t.active, got: [...t.got], end: t.end, shown: t.group ? t.group.children.map(c => c.visible) : null, money: g.NEEDS.money, note: g.NEEDS.lastNote, id: g.S.id, hud: document.getElementById("needs").textContent, sh: g.SH.open}; });
  const depot = DOORS.find(d => d.id === "w41");
  const atDepot = async () => { await stand(depot.x + 1.6, depot.z, Math.PI / 2); await frames(2); };
  const start = async h => {
    await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(h, 2)); await atDepot();
    await page.keyboard.press("KeyF"); await page.click("#sh-work"); await frames(2);
  };
  const empty = async i => { await stand(BINS[i][0] + (BINS[i][0] < 0 ? 0.8 : -0.8), BINS[i][1]); await frames(2); await page.keyboard.press("KeyF"); await frames(1); };

  await page.evaluate(() => { localStorage.setItem("job_trash", "1"); return window.__game.loadScene("street", {pos: [0, 0, -40], face: [0, -1]}); }); await settled("street");
  await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(10, 2)); await atDepot();
  check("at 41 with the job at 10:00 your shift is offered", /start your shift \(Trash truck worker\)/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF");
  const shown = await page.evaluate(() => ({text: document.getElementById("sh-text").textContent, btn: document.getElementById("sh-work").textContent}));
  check("the briefing names the route, the hours and the pay, and offers to start it", /8 bins.*4 hours.*\$2 a bin, \$4 more/.test(shown.text) && shown.btn === "Start the route", JSON.stringify(shown));
  const m0 = (await tr()).money, t0 = await page.evaluate(() => window.__game.CITY.t);
  await page.click("#sh-work"); await frames(2);
  let r = await tr();
  check("starting: the route is on, eight bins at the kerb, the clock did not jump, the HUD shows it", r.active && !r.sh && r.shown.length === 8 && r.shown.every(Boolean) && /ROUTE 0\/8 UNTIL 14:00/.test(r.hud) && Math.abs(r.end - routeEnds(t0)) < 0.5, JSON.stringify(r));
  check("the depot door now offers to clock out", /clock out \(0\/8 bins\)/.test(await prompt()), await prompt());

  // walk up to the first bin
  await stand(BINS[0][0], BINS[0][1] + 4, 0); await frames(2);
  check("away from a bin there is nothing to empty", !/empty the bin/.test(await prompt()), await prompt());
  await page.evaluate(() => { window.__game.keys.KeyW = true; }); await frames(14); await page.evaluate(() => { window.__game.keys.KeyW = false; }); await frames(2);
  check("walking up to a bin you are offered to empty it", /empty the bin \(1\/8\)/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(1);
  r = await tr();
  check("F empties it: one bin, gone from the kerb, and it is not offered again", r.got.length === 1 && r.shown[0] === false && !/empty the bin/.test(await prompt()) && /Bin emptied \(1\/8\)/.test(await toast()), JSON.stringify(r));
  for (let i = 1; i < BINS.length; i++) await empty(i);
  r = await tr();
  check("all eight emptied; the toast says to clock out", r.got.length === 8 && r.shown.every(v => !v) && /whole route/.test(await toast()), JSON.stringify(r));
  check("the clock ran while you worked, short of the end of the shift", await page.evaluate(([a, b]) => window.__game.CITY.t > a && window.__game.CITY.t < b, [t0, r.end]));
  await atDepot(); await page.keyboard.press("KeyF"); await frames(1);
  r = await tr();
  check("clocking out with the whole route on time pays $20 ($16 + $4)", !r.active && r.money === m0 + 20 && r.note === "Trash route 8/8" && /\+\$4/.test(await toast()) && /Paid: \$20/.test(await toast()), JSON.stringify(r));
  check("the bins are gone from the street and the HUD", await page.evaluate(() => !window.__game.CITY.tr.group) && !/ROUTE/.test(r.hud), r.hud);

  // time runs out: the bins only
  let m = r.money; await start(12); await empty(0); await empty(1); await empty(2);
  await page.evaluate(() => { const g = window.__game; g.CITY.t = g.CITY.tr.end + 1; }); await frames(2);
  r = await tr();
  check("when time runs out the shift ends and pays the bins only: 3 bins, $6", !r.active && r.money === m + 6 && r.note === "Trash route 3/8" && /Time ran out/.test(await toast()), JSON.stringify(r));

  // leaving the street ends it too
  m = r.money; await start(13); await empty(4); await empty(5);
  await stand(BUS_STREET.arrive[0], BUS_STREET.arrive[2], 0); await frames(2);
  check("on the route the bus stop warns that it ends your shift", /ends your shift/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await settled("parking_lot"); await frames(2);
  r = await tr();
  check("taking the bus ends the shift and pays the bins: 2 bins, $4", !r.active && r.money === m + 4 && r.note === "Trash route 2/8" && /left the route/.test(await toast()), JSON.stringify(r));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
