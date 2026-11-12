// The City HUD's layout (slice 20): the clock, the needs line, the job line under it and a long toast must not overlap each other or run off the screen, at a desktop width
// and at a phone width, with the longest HUD there is (a lab shift's procedure card). Outside the City the toast is back where the rest of the game puts it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/hud_test.mjs [screenshot dir]
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt} from "../shared/city.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const SHOTS = process.argv[2] || "";
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const LONG = "Wrong station: the card wanted the CENTRIFUGE. That card is spoiled; here is the next one. Shift over (Laboratory worker). Cards done: 12. Cards spoiled: 4. Paid: $20.";
try {
  for (const [w, h, name] of [[900, 700, "desktop"], [390, 844, "phone"]]) {
    const page = await browser.newPage({viewport: {width: w, height: h}}); page.on("pageerror", e => errors.push(e.message));
    await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
    await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
    const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
    const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
    await page.evaluate(() => window.__game.loadScene("laboratory", {pos: [0, 0, 4.4], face: [0, -1]})); await settled("laboratory");
    await page.evaluate(t => { const g = window.__game; g.CITY.t = t; g.CITY.lb = {active: true, b: {card: 3, step: 1, done: 12, spoiled: 4}, end: t + 500}; g.NEEDS = {...g.NEEDS, money: 1234}; g.CITY.ui = 0; }, secondsAt(10, 2));
    await frames(3);
    await page.evaluate(m => { const el = document.getElementById("toast"); el.textContent = m; el.style.transition = "none"; el.style.opacity = 1; }, LONG);
    const r = await page.evaluate(() => {
      const box = id => { const b = document.getElementById(id).getBoundingClientRect(); return {l: b.left, t: b.top, r: b.right, b: b.bottom}; };
      return {clock: box("clock"), needs: box("needs"), toast: box("toast"), job: document.getElementById("needs-j").textContent, line: document.getElementById("needs-n").textContent,
        vw: innerWidth, sw: document.documentElement.scrollWidth, city: document.body.classList.contains("cityhud")};
    });
    const meet = (a, b) => a.l < b.r && b.l < a.r && a.t < b.b && b.t < a.b, inside = a => a.l >= 0 && a.r <= r.vw + 0.5;
    check(`${name}: the job line is on its own line under the needs`, /^HUNGER \d+ · \$1234 · REST \d+$/.test(r.line) && /^CARD: /.test(r.job) && r.city, JSON.stringify({line: r.line, job: r.job}));
    check(`${name}: the clock, the HUD and a long toast do not overlap`, !meet(r.clock, r.needs) && !meet(r.toast, r.needs) && !meet(r.toast, r.clock), JSON.stringify(r));
    check(`${name}: everything is on the screen, and nothing scrolls sideways`, inside(r.clock) && inside(r.needs) && inside(r.toast) && r.sw <= r.vw, JSON.stringify({vw: r.vw, sw: r.sw, needs: r.needs, toast: r.toast}));
    if (SHOTS) await page.screenshot({path: `${SHOTS}/hud_${name}.png`});
    // out of the City: the HUD goes and the toast is back where the rest of the game has it
    await page.evaluate(() => { window.__game.CITY.lb.active = false; return window.__game.loadScene("parking_lot", {pos: [-8, 9.6, 38], face: [0, -1]}); }); await settled("parking_lot"); await frames(2);
    const out = await page.evaluate(() => ({city: document.body.classList.contains("cityhud"), needs: getComputedStyle(document.getElementById("needs")).display, top: getComputedStyle(document.getElementById("toast")).top, h: innerHeight}));
    check(`${name}: outside the City the HUD is gone and the toast is at its usual place`, !out.city && out.needs === "none" && Math.abs(parseFloat(out.top) - out.h * 0.09) < 1, JSON.stringify(out));
    await page.close();
  }
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
