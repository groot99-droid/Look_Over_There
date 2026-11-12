// Rest, the second need (slice 12): it drains while you are awake in the City, warns at 30 and 10, and at 0 you pass out and wake at home at dawn. The bed refills it: a
// night's sleep fills it, and by day, when you are tired, the bed lets you nap for 3 hours. Rest is on the HUD and in the save.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/rest_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, bedUse} from "../shared/city.js";
import {REST} from "../shared/needs.js";
import {SAVE_KEY} from "../shared/save.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const page = await browser.newPage({viewport: {width: 900, height: 700}}); page.on("pageerror", e => errors.push(e.message));
  const boot = async () => { await page.click("#l-solo"); await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000}); };
  await page.goto(`http://localhost:${srv.port}/`); await boot();
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const st = () => page.evaluate(() => { const g = window.__game, s = g.cityState(); return {id: g.S.id, hour: s.hour, day: s.day, rest: g.NEEDS.rest, hud: document.getElementById("needs").textContent, low: document.getElementById("needs").classList.contains("low")}; });
  const setRest = r => page.evaluate(r => { const g = window.__game; g.NEEDS = {...g.NEEDS, rest: r, hunger: 90}; }, r);
  const setT = (h, d = 2) => page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(h, d));
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  const atBed = async () => { await page.evaluate(([x, z]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); }, bedUse.at); await frames(3); };

  await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, -40], face: [0, -1]})); await settled("street");
  await setT(10); await frames(3);
  let s = await st();
  check("rest is on the HUD after the money, starting near 90", /HUNGER \d+ · \$20 · REST (89|90)\b/.test(s.hud) && s.rest > 89 && s.rest <= 90, JSON.stringify(s));
  const r0 = s.rest; await frames(100); s = await st();
  const want = 5 * 100 * 0.05 * 24 / 900;                                             // the page's own frame loop also runs between steps, so allow 10%
  check("awake in the City it drains: 5 an hour of City time", Math.abs((r0 - s.rest) - want) < want * 0.1, JSON.stringify([r0, s.rest, want]));
  await setRest(30.1); await frames(40); s = await st();
  check("crossing 30: you are told you are tired, and the HUD turns red", /You are tired/.test(await toast()) && s.low && s.rest < 30, JSON.stringify(s));
  await setRest(10.1); await frames(40);
  check("crossing 10: you are told you are exhausted", /exhausted/.test(await toast()), await toast());
  await setRest(0.1); await frames(40); await settled("apartment"); await frames(2); s = await st();
  check("at 0 you pass out and wake in your apartment at 06:00 the next day, partly rested", s.id === "apartment" && Math.abs(s.hour - 6) < 0.05 && s.day === 3 && s.rest >= REST.wakeAt - 0.5 && /pass out/.test(await toast()), JSON.stringify(s));

  // the bed by day
  await setT(12, 3); await setRest(80); await atBed();
  check("rested, by day, the bed offers only to save", /Press F to save \(you can sleep from 20:00\)/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(2); s = await st();
  check("and F saves without passing time", /not tired/.test(await toast()) && Math.abs(s.hour - 12) < 0.05, JSON.stringify(s));
  await setRest(25); await frames(2);
  check("tired, by day, the bed offers a 3-hour nap", /Press F to nap \(3 hours\) and save/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(2); s = await st();
  check("the nap: 3 hours pass, rest goes up by 36, and it saves", Math.abs(s.hour - 15) < 0.05 && Math.abs(s.rest - 61) < 0.2 && /nap for 3 hours\. Saved/.test(await toast()) && await page.evaluate(k => JSON.parse(localStorage.getItem(k)).needs.rest > 60, SAVE_KEY), JSON.stringify(s));

  // the bed at night fills it
  await setT(22, 3); await setRest(20); await frames(2); await page.keyboard.press("KeyF"); await frames(2); s = await st();
  check("a night's sleep from 22:00 fills rest to 100 by 06:00", Math.abs(s.hour - 6) < 0.05 && s.day === 4 && s.rest > 99.9, JSON.stringify(s));

  // rest is in the save
  await setRest(42); await page.evaluate(() => window.__game.saveCity());
  await page.reload(); await boot(); s = await st();
  check("a reload resumes with the saved rest", Math.abs(s.rest - 42) < 0.01, JSON.stringify(s));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
