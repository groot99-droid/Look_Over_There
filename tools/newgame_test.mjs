// New Game and the save line (slice 9): the bank says when the City was last saved; the computer's SYSTEM page has New Game, which asks twice and then forgets the City
// (the save, every job flag, money, the fridge, the clock) but keeps the Original's flag. A reload after it starts fresh.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/newgame_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, APARTMENT} from "../shared/city.js";
import {SAVE_KEY} from "../shared/save.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const ctx = await browser.newContext({viewport: {width: 900, height: 700}});             // one context: localStorage survives a reload
  async function solo() {
    const page = await ctx.newPage(); page.on("pageerror", e => errors.push(e.message));
    await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
    await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
    return page;
  }
  let page = await solo();
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const pc = () => page.evaluate(() => ({open: window.__game.PC.open, title: document.getElementById("pc-title").textContent, body: document.getElementById("pc-body").textContent,
    tabs: document.querySelectorAll("#pc-tabs button").length, acts: [...document.querySelectorAll("#pc-actions button")].map(b => b.dataset.act || b.dataset.job)}));
  const atDesk = async () => {
    await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]}));
    await page.waitForFunction(() => window.__game.S.id === "apartment" && !window.__game.loading, null, {timeout: 180000});
    await page.evaluate(([x, z]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); }, APARTMENT.computer.at); await frames(3);
  };
  const store = () => page.evaluate(k => ({save: localStorage.getItem(k), lab: localStorage.getItem("job_lab"), intern: localStorage.getItem("job_intern"), orig: localStorage.getItem("original_complete")}), SAVE_KEY);
  const city = () => page.evaluate(() => { const g = window.__game; return {t: g.CITY.t, money: g.NEEDS.money, pantry: g.NEEDS.pantry, accepted: g.APP.st.accepted, passes: g.CITY.signPasses}; });

  // a fresh browser: the bank says nothing is saved
  await atDesk(); await page.keyboard.press("KeyF"); await page.keyboard.press("Digit5");
  let p = await pc();
  check("the computer has seven pages, and with no save the bank says so", p.tabs === 7 && p.title === "BANK" && /Not saved yet/.test(p.body), JSON.stringify(p));
  await page.keyboard.press("Escape");

  // a City worth forgetting: day 3, $77, food, two jobs, a sign passed; saved; and the Original finished
  await page.evaluate(([t]) => {
    const g = window.__game; g.CITY.t = t; g.NEEDS = {...g.NEEDS, money: 77, pantry: {soup: 2}}; g.APP.st = {...g.APP.st, accepted: {lab: true, intern: true}}; g.CITY.signPasses = 4;
    localStorage.setItem("job_lab", "1"); localStorage.setItem("job_intern", "1"); localStorage.setItem("original_complete", "1"); g.saveCity();
  }, [secondsAt(14, 3)]);
  await frames(2); await page.keyboard.press("KeyF"); await page.keyboard.press("Digit5");
  p = await pc();
  check("after a save the bank says when", /Last saved: Day 3, 14:00\./.test(p.body), p.body);
  await page.keyboard.press("Digit7"); p = await pc();
  check("key 7 (slice 15: after REPORT) is the system page, with the save time and one New Game button", p.title === "SYSTEM" && /Last saved: Day 3, 14:00\./.test(p.body) && /NEW GAME/.test(p.body) && p.acts.join() === "newgame", JSON.stringify(p));

  // New Game asks first; Cancel changes nothing
  await page.click('#pc-actions button[data-act="newgame"]'); p = await pc();
  check("New Game asks before it forgets anything", p.acts.join() === "newgame-yes,newgame-no" && (await store()).save !== null, JSON.stringify(p));
  await page.click('#pc-actions button[data-act="newgame-no"]'); p = await pc();
  let c = await city(), s = await store();
  check("Cancel puts the button back and keeps everything", p.acts.join() === "newgame" && c.money === 77 && c.accepted.lab && s.save !== null && s.lab !== null, JSON.stringify({p, c, s}));
  // leaving the page forgets the half-pressed button
  await page.click('#pc-actions button[data-act="newgame"]'); await page.keyboard.press("Digit5"); await page.keyboard.press("Digit7"); p = await pc();
  check("switching page and back shows the single button again", p.acts.join() === "newgame", JSON.stringify(p));

  // yes: the City is forgotten
  await page.click('#pc-actions button[data-act="newgame"]'); await page.click('#pc-actions button[data-act="newgame-yes"]'); await frames(2);
  c = await city(); s = await store(); p = await pc();
  check("yes closes the computer and starts the City again at 08:00 on day 1 with $20, an empty fridge, no jobs and a fresh sign",
    !p.open && c.t < 1 && c.money === 20 && Object.keys(c.pantry).length === 0 && Object.keys(c.accepted).length === 0 && c.passes === 0, JSON.stringify(c));
  check("the save and the job flags are gone; the Original's flag is kept", s.save === null && s.lab === null && s.intern === null && s.orig === "1", JSON.stringify(s));
  check("a toast says so", await page.evaluate(() => /A new start: day 1, 08:00/.test(document.getElementById("toast").textContent)));
  await page.keyboard.press("KeyF"); await page.keyboard.press("Digit5"); p = await pc();
  check("the bank says nothing is saved again", /Not saved yet/.test(p.body) && /Balance: \$20/.test(p.body), p.body);
  await page.keyboard.press("Digit3"); p = await pc();
  check("the job search shows every job hiring again", !/ACCEPTED/.test(p.body) && (p.body.match(/hiring: apply below/g) || []).length === 5, p.body);
  await page.keyboard.press("Escape");

  // a reload after New Game starts fresh, not from the old save
  await page.close(); page = await solo();
  c = await city();
  check("a reload after New Game starts the City fresh", c.t === 0 && c.money === 20 && Object.keys(c.accepted).length === 0, JSON.stringify(c));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
