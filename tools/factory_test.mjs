// The factory floor (slice 16): at 330 Hallam Row between 08:00 and 16:00 the shift starts on the factory floor. Parts come down the belt; F by the belt picks one up, F at a
// bin drops it in; parts that reach the end of the belt are lost. After 4 hours you are paid $1 for each part sorted right, $1 off for each in the wrong bin.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/factory_test.mjs [screenshot dir]
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, DOORS} from "../shared/city.js";
import {FACTORY, FACTORY_FRONT, KINDS} from "../shared/factory.js";
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
  const fa = () => page.evaluate(() => { const g = window.__game, f = g.CITY.fa; return {active: f.active, st: f.st && JSON.parse(JSON.stringify(f.st)), end: f.end, id: g.S.id, money: g.NEEDS.money, note: g.NEEDS.lastNote, hud: document.getElementById("needs").textContent, sub: document.getElementById("clock").lastChild.textContent, p: g.P.p.toArray(), meshes: f.parts ? f.parts.children.length : 0}; });
  const shot = async name => { if (SHOTS) await page.screenshot({path: `${SHOTS}/factory_${name}.png`}); };
  const door = DOORS.find(d => d.id === "e330"), B = FACTORY.belt;
  const binOf = kind => FACTORY.bins.find(b => b.kind === kind);
  // pick up the part furthest along the belt, standing beside it on the near side
  const pickFirst = async () => { const s = (await fa()).st, p = s.parts.reduce((a, b) => b.x > a.x ? b : a); await stand(p.x, B.z + 1.1, 0); await frames(1); const pr = await prompt(); await page.keyboard.press("KeyF"); await frames(1); return {kind: p.kind, pr}; };
  const dropIn = async kind => { const b = binOf(kind); await stand(b.x, b.z + 1.0, 0); await frames(1); const pr = await prompt(); await page.keyboard.press("KeyF"); await frames(1); return pr; };

  await page.evaluate(() => { localStorage.setItem("job_factory", "1"); return window.__game.loadScene("street", {pos: [0, 0, -95], face: [0, -1]}); }); await settled("street");
  await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(10, 2)); await stand(door.x - 1.6, door.z, -Math.PI / 2); await frames(2);
  check("at 330 at 10:00 with the job, the shift is offered", /start your shift \(Factory floor worker\)/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); const m0 = (await fa()).money;
  await page.click("#sh-work"); await settled("factory_floor"); await frames(2);
  let f = await fa();
  check("the shift starts on the factory floor, until 14:00, the HUD counting", f.active && f.id === "factory_floor" && /ON SHIFT UNTIL 14:00/.test(f.sub) && /SORTED 0 · WRONG 0/.test(f.hud), JSON.stringify(f));
  await frames(100); f = await fa();
  check("parts come down the belt from the west end and move east", f.st.parts.length >= 2 && f.st.parts.every(p => p.x > B.x0 - 1e-6 && p.x <= B.x1) && f.meshes === f.st.parts.length, JSON.stringify(f.st));
  await shot("belt");

  // right bin
  let r = await pickFirst(); f = await fa();
  check("beside the belt you are offered the part; F picks it up and it leaves the belt", new RegExp(`pick up the ${KINDS[r.kind].label}`).test(r.pr) && f.st.held && f.st.held.kind === r.kind && new RegExp(`HOLDING ${KINDS[r.kind].label}`).test(f.hud), JSON.stringify({r, held: f.st.held}));
  const other = f.st.parts[0]; await stand(other.x, B.z + 1.1, 0); await frames(1);
  check("with your hands full the belt offers nothing", !/pick up/.test(await prompt()), await prompt());
  let pr = await dropIn(r.kind); f = await fa();
  check("at its own bin you are offered to put it in; F sorts it right", new RegExp(`put the ${KINDS[r.kind].label} in the ${KINDS[r.kind].label} bin`).test(pr) && f.st.right === 1 && !f.st.held && /Right/.test(await toast()), JSON.stringify({pr, st: f.st}));
  // another right one
  await frames(60); r = await pickFirst(); await dropIn(r.kind); f = await fa();
  check("a second part sorted right", f.st.right === 2, JSON.stringify(f.st));
  // a wrong one
  await frames(60); r = await pickFirst(); const wrongKind = Object.keys(KINDS).find(k => k !== r.kind); await dropIn(wrongKind); f = await fa();
  check("a part in another bin is sorted wrong", f.st.wrong === 1 && /Wrong bin/.test(await toast()) && /SORTED 2 · WRONG 1/.test(f.hud), JSON.stringify(f.st));
  // leave the belt alone: parts fall off the end
  await frames(500); f = await fa();
  check("parts nobody picks up fall off the east end and are counted as missed", f.st.missed >= 2 && f.st.parts.every(p => p.x <= B.x1), JSON.stringify(f.st));

  // the end of the shift
  await page.evaluate(() => { const g = window.__game; g.CITY.t = g.CITY.fa.end - 0.01; }); await frames(3); await settled("street"); await frames(2); f = await fa();
  check("at 14:00 the shift ends: back by 330, paid $1 (2 right, 1 wrong)", !f.active && f.id === "street" && Math.abs(f.p[0] - FACTORY_FRONT.arrive[0]) < 0.05 && Math.abs(f.p[2] - FACTORY_FRONT.arrive[2]) < 0.05 && f.money === m0 + 1 && f.note === "Factory 2 right, 1 wrong" && /Paid: \$1/.test(await toast()), JSON.stringify(f));

  // passing out mid-shift loses it
  await page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(11, 3)); await stand(door.x - 1.6, door.z, -Math.PI / 2); await frames(2);
  await page.keyboard.press("KeyF"); await page.click("#sh-work"); await settled("factory_floor"); await frames(2);
  const m1 = (await fa()).money;
  await page.evaluate(() => { const g = window.__game; g.NEEDS = {...g.NEEDS, rest: 0.05}; }); await frames(20); await settled("apartment"); await frames(3);
  f = await fa();
  check("passing out mid-shift takes you home and the shift is lost: no pay", !f.active && f.id === "apartment" && f.money === m1 && f.note === "Factory: left early", JSON.stringify(f));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
