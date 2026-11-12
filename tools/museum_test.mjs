// The museum night guard (slice 14): at 108 Hallam Row between 20:00 and 21:00 the shift starts in the galleries. Six statues stand on plinths; the one you look at never moves,
// the others step off their plinths while you are not looking and turn to face you; F sets one back. At the end of 3 hours you are paid for the statues at home and the ones
// you set back. Fainting or passing out mid-shift loses it. Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/museum_test.mjs [screenshot dir]
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, DOORS} from "../shared/city.js";
import {MUSEUM, MUSEUM_FRONT, exhibitAt, GUARD} from "../shared/museum.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const SHOTS = process.argv[2] || "";
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
  const mu = () => page.evaluate(() => { const g = window.__game, m = g.CITY.mu; return {active: m.active, offs: m.ex.map(e => e.off), fixes: m.fixes, end: m.end, id: g.S.id, money: g.NEEDS.money, note: g.NEEDS.lastNote, hud: document.getElementById("needs").textContent, sub: document.getElementById("clock").lastChild.textContent,
    figs: m.figs.map(f => [f.position.x, f.position.y, f.position.z, f.rotation.y]), p: g.P.p.toArray()}; });
  const shot = async name => { if (SHOTS) await page.screenshot({path: `${SHOTS}/museum_${name}.png`}); };
  const door = DOORS.find(d => d.id === "e108");
  const face = (fx, fz, tx, tz) => Math.atan2(-(tx - fx), -(tz - fz));        // the yaw that looks from (fx, fz) at (tx, tz)

  await page.evaluate(() => { localStorage.setItem("job_museum", "1"); return window.__game.loadScene("street", {pos: [0, 0, -41], face: [0, -1]}); }); await settled("street");
  await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(20.5, 2)); await stand(door.x - 1.6, door.z, -Math.PI / 2); await frames(2);
  check("at 108 at 20:30 with the job, the shift is offered", /start your shift \(Museum night guard\)/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); const m0 = (await mu()).money;
  await page.click("#sh-work"); await settled("galleries"); await frames(2);
  let m = await mu();
  check("the shift starts in the galleries: six statues home, until 23:30 on the clock and the HUD", m.active && m.id === "galleries" && m.offs.every(o => o === 0) && /ON SHIFT UNTIL 23:30/.test(m.sub) && /STATUES HOME 6\/6/.test(m.hud), JSON.stringify(m));
  check("on their plinths the statues stand on top of them", m.figs.every(f => Math.abs(f[1] - 0.6) < 1e-6), JSON.stringify(m.figs));

  // watch THE ORATOR (statue 2) for 20 seconds, with your back to BOY AND GOOSE (statue 3)
  const [ox, oz] = MUSEUM.homes[2]; await stand(0, oz, face(0, oz, ox, oz)); await frames(400);
  m = await mu();
  check("the statue you watch never moves", m.offs[2] === 0, JSON.stringify(m.offs));
  check("the one behind you has stepped off its plinth (up to three steps), and the HUD says so", m.offs[3] >= 1 && m.offs[3] <= 3 && /STATUES HOME [0-5]\/6/.test(m.hud), JSON.stringify(m));
  const [sx, , sz, sry] = m.figs[3], want = Math.atan2(m.p[0] - sx, m.p[2] - sz) + Math.PI;
  check("a moved statue is off its plinth, on the floor, turned to face you", Math.abs(m.figs[3][1]) < 1e-6 && Math.abs(Math.sin(sry - want)) < 1e-3 && Math.cos(sry - want) > 0, JSON.stringify(m.figs[3]));
  await page.evaluate(() => { window.__game.P.yaw += Math.PI; }); await frames(1); await shot("turned");

  // set it back
  const [bx, bz] = exhibitAt(3, m.offs[3]); await stand(bx - 0.9, bz, face(bx - 0.9, bz, bx, bz)); await frames(1);
  check("next to it you are offered to set it back", /set BOY AND GOOSE back on its plinth/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(1); m = await mu();
  check("F sets it back: home again, one fix", m.offs[3] === 0 && m.fixes === 1 && /back on its plinth/.test(await toast()), JSON.stringify(m));

  // the end of the shift
  const homeNow = m.offs.filter(o => !o).length;
  await page.evaluate(() => { const g = window.__game; g.CITY.t = g.CITY.mu.end - 0.01; }); await stand(0, 0, face(0, 0, MUSEUM.homes[0][0], MUSEUM.homes[0][1])); await frames(3);
  await settled("street"); await frames(2); m = await mu();
  const expect = Math.min(homeNow * GUARD.perHome + 1, 99);
  check("at 23:30 the shift ends: back on the street at 108, paid for the statues home and the one set back", !m.active && m.id === "street" && Math.abs(m.p[0] - MUSEUM_FRONT.arrive[0]) < 0.05 && Math.abs(m.p[2] - MUSEUM_FRONT.arrive[2]) < 0.05 && m.money - m0 >= expect - GUARD.perHome && m.money - m0 <= expect && /^Museum \d\/6$/.test(m.note) && /Set back during the night: 1/.test(await toast()), JSON.stringify({m, m0, homeNow}));

  // passing out mid-shift loses it
  await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(20.2, 3)); await stand(door.x - 1.6, door.z, -Math.PI / 2); await frames(2);
  await page.keyboard.press("KeyF"); await page.click("#sh-work"); await settled("galleries"); await frames(2);
  const m1 = (await mu()).money;
  await page.evaluate(() => { const g = window.__game; g.NEEDS = {...g.NEEDS, rest: 0.05}; }); await frames(20); await settled("apartment"); await frames(3);
  m = await mu();
  check("passing out mid-shift takes you home and the shift is lost: no pay", !m.active && m.id === "apartment" && m.money === m1 && m.note === "Museum: left early", JSON.stringify(m));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
