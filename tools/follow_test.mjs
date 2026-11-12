// The stalker follows you (slice 10): if it is out when you go into your apartment at night, it waits outside the tower's door and is there when you step out.
// The apartment stays safe. It is gone at dawn and after you sleep, and nothing follows if it was not out.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/follow_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, APARTMENT, TOWER_FRONT, STALKER_WAIT, bedUse} from "../shared/city.js";
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
  const stand = (x, z, yaw) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const setT = (h, day = 2) => page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(h, day));
  const stk = () => page.evaluate(() => { const g = window.__game, s = g.CITY.st; return {active: s.active, waited: !!s.waited, x: s.x, z: s.z, wait: s.wait, id: g.S.id, hour: g.cityState().hour, mesh: !!(g.CITY.mesh && g.CITY.mesh.visible)}; });
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const goIn = async () => { await stand(-6.4, -19, Math.PI / 2); await frames(2); await page.keyboard.press("KeyF"); await settled("apartment"); };
  const goOut = async () => { await stand(APARTMENT.door.at[0], APARTMENT.door.at[1] - 0.4, Math.PI); await frames(2); await page.keyboard.press("KeyF"); await settled("street"); };
  const fromDoor = s => Math.hypot(s.x - TOWER_FRONT.arrive[0], s.z - TOWER_FRONT.arrive[2]);

  await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, -19], face: [0, -1]})); await settled("street");
  // 01:00 on day 2, the stalker is out up the street
  await setT(1); await stand(-6.4, -19, Math.PI / 2); await page.evaluate(() => { window.__game.CITY.st = {active: true, x: 1, z: -60, wait: 0}; }); await frames(2);
  check("at 01:00 the stalker is out on the street", (await stk()).active);
  await goIn();
  let s = await stk();
  check("you go in; it does not go away: it waits outside the door, 14 m up the street (along it, on the road)", s.id === "apartment" && s.active && s.waited && Math.abs((TOWER_FRONT.arrive[2] - s.z) - STALKER_WAIT) < 0.01 && fromDoor(s) >= STALKER_WAIT, JSON.stringify(s));
  const waitSpot = {x: s.x, z: s.z};
  await frames(200);
  s = await stk();
  check("inside, you are safe and it stays where it waits", s.id === "apartment" && s.active && s.x === waitSpot.x && s.z === waitSpot.z, JSON.stringify(s));
  await goOut(); await frames(2);
  s = await stk();
  check("you step out and it is there, by your door", s.id === "street" && s.active && s.mesh && Math.abs(s.x - waitSpot.x) < 0.5 && Math.abs(s.z - waitSpot.z) < 0.5 + 5.5 * 0.1, JSON.stringify(s));
  check("a toast warns you that it waited", /It waited for you/.test(await toast()), await toast());
  // looking at it still holds it
  await page.evaluate(() => { const g = window.__game; g.P.yaw = Math.atan2(-(g.CITY.st.x - g.P.p.x), -(g.CITY.st.z - g.P.p.z)); }); await frames(1);
  const held = await stk(); await frames(40); s = await stk();
  check("it still never moves while you look at it", s.active && Math.abs(s.x - held.x) < 1e-6 && Math.abs(s.z - held.z) < 1e-6, JSON.stringify({held, s}));
  await page.evaluate(() => { window.__game.P.yaw += Math.PI; }); await frames(6); const crept = await stk();
  check("and creeps when you turn away", Math.hypot(crept.x - s.x, crept.z - s.z) > 1, JSON.stringify(crept));

  // straight back in: it follows to the door again, then dawn comes while you are inside and it is gone
  await page.evaluate(() => { const g = window.__game; g.P.yaw = Math.atan2(-(g.CITY.st.x - g.P.p.x), -(g.CITY.st.z - g.P.p.z)); }); await frames(1);
  await goIn(); s = await stk();
  check("going back in, it waits outside again", s.active && s.waited, JSON.stringify(s));
  await setT(5.99); await frames(20);
  s = await stk();
  check("at dawn, while you are inside, it is gone", !s.active && s.hour >= 6, JSON.stringify(s));
  await goOut(); await frames(10);
  s = await stk();
  check("stepping out after dawn there is nothing waiting", !s.active && !s.mesh, JSON.stringify(s));

  // asleep: the bed skips the night and it does not wait for morning
  await setT(2, 3); await stand(-6.4, -19, Math.PI / 2); await page.evaluate(() => { window.__game.CITY.st = {active: true, x: 0, z: -5, wait: 0}; }); await frames(1);
  await goIn(); check("it waited again on night 3", (await stk()).waited);
  await stand(bedUse.at[0], bedUse.at[1], 0); await frames(2); await page.keyboard.press("KeyF"); await frames(5);
  s = await stk();
  check("you sleep until 06:00, and it is gone", !s.active && Math.abs(s.hour - 6) < 0.1, JSON.stringify(s));

  // nothing out, nothing follows: going in and out at night gives the usual wait before it first appears
  await setT(1, 4); await page.evaluate(() => { window.__game.CITY.st = {active: false, x: 0, z: 0, wait: 6}; }); await frames(1);
  await goOut(); s = await stk();
  check("if it was not out when you went in, nothing is waiting when you step out", !s.active && s.wait > 5, JSON.stringify(s));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
