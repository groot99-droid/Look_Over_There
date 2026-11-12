// The laboratory (slice 17): at 214 Hallam Row between 08:00 and 16:00 the shift starts in the lab. Each procedure card names three stations in order; F at each in turn
// does the card, F at a wrong station spoils it. After 4 hours: $3 a card done, $1 off a card spoiled. The B2 door is sealed.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/lab_test.mjs [screenshot dir]
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, DOORS} from "../shared/city.js";
import {LAB, LAB_FRONT, cardOf, labelOf} from "../shared/lab.js";
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
  const lb = () => page.evaluate(() => { const g = window.__game, l = g.CITY.lb; return {active: l.active, b: l.b && {...l.b}, end: l.end, id: g.S.id, money: g.NEEDS.money, note: g.NEEDS.lastNote, hud: document.getElementById("needs").textContent, sub: document.getElementById("clock").lastChild.textContent, p: g.P.p.toArray()}; });
  const shot = async name => { if (SHOTS) await page.screenshot({path: `${SHOTS}/lab_${name}.png`}); };
  const door = DOORS.find(d => d.id === "w214");
  // stand in front of a station, between it and the middle of the room, and press F
  const use = async id => { const s = LAB.stations.find(x => x.id === id), k = 1.1 / Math.hypot(s.x, s.z); await stand(s.x - s.x * k, s.z - s.z * k, Math.atan2(s.x, s.z)); await frames(1); const pr = await prompt(); await page.keyboard.press("KeyF"); await frames(1); return pr; };

  await page.evaluate(() => { localStorage.setItem("job_lab", "1"); return window.__game.loadScene("street", {pos: [0, 0, -95], face: [0, -1]}); }); await settled("street");
  await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(9, 2)); await stand(door.x + 1.6, door.z, Math.PI / 2); await frames(2);
  check("at 214 at 09:00 with the job, the shift is offered", /start your shift \(Laboratory worker\)/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); const m0 = (await lb()).money;
  await page.click("#sh-work"); await settled("laboratory"); await frames(2);
  let l = await lb(); const c0 = cardOf(0);
  check("the shift starts in the lab, until 13:00, with the first card on the HUD", l.active && l.id === "laboratory" && /ON SHIFT UNTIL 13:00/.test(l.sub) && l.hud.includes("CARD: > " + labelOf(c0[0])) && /DONE 0 · SPOILED 0/.test(l.hud), JSON.stringify(l));
  await shot("start");

  // the first card, step by step
  let pr = await use(c0[0]); l = await lb();
  check("at the card's first station you are offered it, and F does the step", new RegExp(`use the ${labelOf(c0[0])}`).test(pr) && l.b.step === 1 && l.hud.includes("✓ " + labelOf(c0[0])), JSON.stringify({pr, b: l.b}));
  await use(c0[1]); await use(c0[2]); l = await lb();
  check("the third station finishes the card; the next card comes up", l.b.done === 1 && l.b.card === 1 && l.b.step === 0 && /Card done/.test(await toast()) && l.hud.includes("CARD: > " + labelOf(cardOf(1)[0])), JSON.stringify(l));
  // a wrong station spoils the card
  const c1 = cardOf(1), wrong = LAB.stations.map(s => s.id).find(id => id !== c1[0]);
  await use(wrong); l = await lb();
  check("a wrong station spoils the card, says which one it wanted, and the next card comes up", l.b.spoiled === 1 && l.b.card === 2 && new RegExp(`wanted the ${labelOf(c1[0])}`).test(await toast()), JSON.stringify(l.b));
  // the sealed door
  await stand(LAB.b2.x, LAB.b2.z + 0.8, 0); await frames(1);
  check("the B2 door is sealed", /B2 · AUTHORISED STAFF ONLY\. The door is sealed\./.test(await prompt()), await prompt());
  await shot("b2");

  // the end of the shift
  await page.evaluate(() => { const g = window.__game; g.CITY.t = g.CITY.lb.end - 0.01; }); await stand(0, 0, 0); await frames(3); await settled("street"); await frames(2); l = await lb();
  check("at 13:00 the shift ends: back by 214, paid $2 (1 card done, 1 spoiled)", !l.active && l.id === "street" && Math.abs(l.p[0] - LAB_FRONT.arrive[0]) < 0.05 && Math.abs(l.p[2] - LAB_FRONT.arrive[2]) < 0.05 && l.money === m0 + 2 && l.note === "Lab 1 done, 1 spoiled" && /Paid: \$2/.test(await toast()), JSON.stringify(l));

  // passing out mid-shift loses it
  await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(10, 3)); await stand(door.x + 1.6, door.z, Math.PI / 2); await frames(2);
  await page.keyboard.press("KeyF"); await page.click("#sh-work"); await settled("laboratory"); await frames(2);
  const m1 = (await lb()).money;
  await page.evaluate(() => { const g = window.__game; g.NEEDS = {...g.NEEDS, rest: 0.05}; }); await frames(20); await settled("apartment"); await frames(3);
  l = await lb();
  check("passing out mid-shift takes you home and the shift is lost: no pay", !l.active && l.id === "apartment" && l.money === m1 && l.note === "Lab: left early", JSON.stringify(l));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
