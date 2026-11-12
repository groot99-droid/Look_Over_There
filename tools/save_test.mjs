// Saving the City (slice 7): the bed saves (by day it only saves; from 20:00 it also skips the night), and a reload resumes the City from the last save: the clock and day,
// hunger, money, the fridge, the last pay and the applications. What happened after the save is lost. A corrupt save is ignored; blocked storage changes nothing.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/save_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, bedUse} from "../shared/city.js";
import {SAVE_KEY} from "../shared/save.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const ctx = await browser.newContext({viewport: {width: 900, height: 700}});             // one context: localStorage survives a reload, as for a player
  async function solo(c = ctx) {
    const page = await c.newPage(); page.on("pageerror", e => errors.push(e.message));
    await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
    await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
    return page;
  }
  const tools = page => ({
    settled: id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000}),
    frames: n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n),
    st: () => page.evaluate(() => ({...window.__game.cityState(), needs: JSON.parse(JSON.stringify(window.__game.NEEDS)), apps: JSON.parse(JSON.stringify(window.__game.APP.st))})),
    toast: () => page.evaluate(() => document.getElementById("toast").textContent),
    prompt: () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; }),
    atBed: async () => { await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await page.waitForFunction(() => window.__game.S.id === "apartment" && !window.__game.loading, null, {timeout: 180000}); await page.evaluate(([x, z]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); }, bedUse.at); await page.evaluate(() => { for (let i = 0; i < 3; i++) window.__game.sim(0.05, i); }); },
  });

  // a fresh browser: no save, the City starts at 08:00 with $20
  let p = await solo(), T = tools(p);
  let s = await T.st();
  check("a fresh browser has no save and starts the City at 08:00, day 1, with $20", s.t === 0 && s.needs.money === 20 && await p.evaluate(k => localStorage.getItem(k) === null, SAVE_KEY), JSON.stringify(s));

  // by day the bed only saves
  await T.atBed();
  await p.evaluate(([a]) => { const g = window.__game; g.CITY.t = a; g.NEEDS = {...g.NEEDS, hunger: 41, money: 33, pantry: {soup: 2}, lastPay: 24, lastNote: "ASSIMILATION"}; g.APP.st = {...g.APP.st, rejectedOn: {lab: 3}}; }, [secondsAt(14, 3)]);
  await T.frames(3);
  check("by day the bed offers a save", /Press F to save/.test(await T.prompt()), await T.prompt());
  await p.keyboard.press("KeyF"); await T.frames(2);
  s = await T.st();
  check("F saves without skipping time", /Saved/.test(await T.toast()) && Math.abs(s.hour - 14) < 0.1 && s.day === 3 && await p.evaluate(k => !!localStorage.getItem(k), SAVE_KEY), await T.toast());
  const saved = s;                                                                     // read two frames after the save, so hunger may be a hair lower than what was stored
  await p.evaluate(() => { const g = window.__game; g.NEEDS = {...g.NEEDS, money: 99}; g.CITY.t += 3000; });       // after the save: lost on a reload

  // a reload resumes from the save
  await p.close(); p = await solo(); T = tools(p);
  s = await T.st();
  check("a reload resumes the clock and day from the save", Math.abs(s.t - saved.t) < 0.5 && s.day === 3 && Math.abs(s.hour - saved.hour) < 0.05, `${saved.t} -> ${s.t}`);
  check("hunger, money, the fridge and the last pay are as saved; what came after is lost", Math.abs(s.needs.hunger - saved.needs.hunger) < 0.1 && s.needs.money === 33 && s.needs.pantry.soup === 2 && s.needs.lastPay === 24 && s.needs.lastNote === "ASSIMILATION", JSON.stringify(s.needs));
  check("the rejection is still recorded for day 3", s.apps.rejectedOn.lab === 3 && s.apps.active === null, JSON.stringify(s.apps));
  await p.evaluate(() => window.__game.loadScene("street", {pos: [3.6, 0, 4], face: [0, -1]})); await T.settled("street"); await T.frames(5);
  const hud = await p.evaluate(() => ({clock: document.getElementById("clock").firstChild.textContent, sub: document.getElementById("clock").lastChild.textContent, needs: document.getElementById("needs").textContent}));
  check("on the street the clock says day 3 at about 14:00, and the money and hunger are the saved ones", /^14:0/.test(hud.clock) && /DAY 3/.test(hud.sub) && /HUNGER 41 · \$33/.test(hud.needs), JSON.stringify(hud));

  // from 20:00 the bed sleeps until morning and saves
  await T.atBed(); await p.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(22, 3)]); await T.frames(2);
  check("in the evening the bed offers sleep and a save", /sleep until morning and save/.test(await T.prompt()), await T.prompt());
  await p.keyboard.press("KeyF"); await T.frames(2);
  check("sleeping saves at dawn", /Dawn\. Saved/.test(await T.toast()));
  await p.close(); p = await solo(); T = tools(p);
  s = await T.st();
  check("a reload after sleeping resumes at 06:00 on day 4", Math.abs(s.hour - 6) < 0.05 && s.day === 4, JSON.stringify([s.hour, s.day]));

  // a corrupt save is ignored: a fresh City, no error
  await p.evaluate(k => localStorage.setItem(k, "{not json"), SAVE_KEY);
  await p.close(); p = await solo(); T = tools(p);
  s = await T.st();
  check("a corrupt save is ignored: the City starts fresh", s.t === 0 && s.needs.money === 20 && s.day === 1, JSON.stringify(s));
  await p.close();

  // blocked storage: nothing saves, nothing breaks
  const ctx2 = await browser.newContext({viewport: {width: 900, height: 700}});
  await ctx2.addInitScript(() => { Object.defineProperty(window, "localStorage", {get() { throw new Error("blocked"); }}); });
  p = await solo(ctx2); T = tools(p);
  await T.atBed(); await p.keyboard.press("KeyF"); await T.frames(2);
  check("with storage blocked the bed does not claim to save", /not tired/.test(await T.toast()) && !/Saved/.test(await T.toast()), await T.toast());
  await p.close(); await ctx2.close();
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
