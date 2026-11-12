// The mall locks you in (slice 13): the street's MALL door opens by day into the atrium; at 20:00 the doors lock with you inside until 06:00; the benches let you sleep
// through to dawn (no save). The clock, hunger and rest run inside. At night the street door is shut.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/mall_test.mjs [screenshot dir]
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, DOORS, MALL, MALL_FRONT} from "../shared/city.js";
import {REGISTRY} from "../shared/registry.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const SHOTS = process.argv[2] || "";
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const into = REGISTRY.linkFrom("street", "mall"), out = REGISTRY.linkFrom("entrance", "front_door");
  check("the manifest has the mall door both ways, built and solo only", into && out && into.status === "built" && out.status === "built" && into.soloOnly && out.soloOnly);
  const page = await browser.newPage({viewport: {width: 900, height: 700}}); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const stand = (x, z, yaw = 0) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const setT = (h, d = 2) => page.evaluate(t => { window.__game.CITY.t = t; window.__game.CITY.ui = 0; }, secondsAt(h, d));
  const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const st = () => page.evaluate(() => { const g = window.__game, s = g.cityState(); return {id: g.S.id, t: g.CITY.t, hour: s.hour, day: s.day, p: g.P.p.toArray(), sub: document.getElementById("clock").lastChild.textContent, clock: getComputedStyle(document.getElementById("clock")).display, light: g.HEMI ? g.HEMI.intensity : null, rest: g.NEEDS.rest, hunger: g.NEEDS.hunger}; });
  const shot = async name => { if (SHOTS) await page.screenshot({path: `${SHOTS}/mall_${name}.png`}); };
  const door = DOORS.find(d => d.id === "mall");
  const atStreetDoor = async () => { await stand(door.x - 1.6, door.z, -Math.PI / 2); await frames(2); };

  await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, -60], face: [0, -1]})); await settled("street");
  // at night the street door is shut
  await setT(22); await atStreetDoor();
  check("at 22:00 the MALL door on the street is closed", /MALL: closed/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(2);
  check("and F does not open it", (await st()).id === "street" && /closed/.test(await toast()), await toast());
  // by day: in
  await setT(12); await atStreetDoor();
  check("at noon the MALL door offers the mall", /Press F to go into the mall/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await settled("entrance"); await frames(2);
  let s = await st();
  check("inside: the atrium, by the doors, the clock on screen", s.id === "entrance" && Math.abs(s.p[0] - MALL.arrive[0]) < 0.05 && Math.abs(s.p[2] - MALL.arrive[2]) < 0.05 && s.clock === "block" && /STORES OPEN/.test(s.sub), JSON.stringify(s));
  const t0 = s.t; await frames(40); s = await st();
  check("the City's clock runs in the mall", s.t > t0 + 1.5, JSON.stringify([t0, s.t]));
  const solid = await page.evaluate(([f, b]) => { const g = window.__game; return {fountain: !!g.collide({x: (f.min[0] + f.max[0]) / 2, y: 0.02, z: (f.min[2] + f.max[2]) / 2}), bench: !!g.collide({x: (b.min[0] + b.max[0]) / 2, y: 0.02, z: (b.min[2] + b.max[2]) / 2}), floor: !!g.collide({x: 0, y: 0.02, z: 6})}; }, [MALL.fountain, MALL.benches[0]]);
  check("the fountain and benches are solid, the floor is clear", solid.fountain && solid.bench && !solid.floor, JSON.stringify(solid));
  await shot("day");
  await stand(MALL.benches[0].at[0], MALL.benches[0].at[1]); await frames(2);
  check("by day a bench offers nothing", (await prompt()) === "", await prompt());
  await stand(MALL.door.at[0], MALL.door.at[1] - 0.6, Math.PI); await frames(2);
  check("by day the doors offer the way out", /Press F to leave/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await settled("street"); s = await st();
  check("out: back on the street at the MALL door", Math.abs(s.p[0] - MALL_FRONT.arrive[0]) < 0.05 && Math.abs(s.p[2] - MALL_FRONT.arrive[2]) < 0.05, JSON.stringify(s.p));

  // stay too late: locked in
  await setT(19.9); await atStreetDoor(); await page.keyboard.press("KeyF"); await settled("entrance"); await frames(2);
  const dayLight = (await st()).light;
  await setT(19.99); await frames(30); s = await st();
  check("at 20:00 the doors lock with you inside, and you are told", s.hour >= 20 && /locked in until 06:00/.test(await toast()) && /LOCKED IN UNTIL 06:00/.test(s.sub), JSON.stringify(s));
  check("the lights go down to the emergency lights", s.light < dayLight * 0.5, JSON.stringify([dayLight, s.light]));
  await stand(MALL.door.at[0], MALL.door.at[1] - 0.6, Math.PI); await frames(2);
  check("the doors say they are locked until 06:00", /locked until 06:00/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(2);
  check("and F does not let you out", (await st()).id === "entrance" && /open at 06:00/.test(await toast()), await toast());
  await setT(0.5, 3); await frames(30); s = await st();
  check("past midnight you are still in, and nothing comes in after you", s.id === "entrance" && !(await page.evaluate(() => window.__game.CITY.st.active)) && /nothing comes in here/.test(await toast()), JSON.stringify(s));
  await shot("night");
  // a bench: sleep through to dawn
  await page.evaluate(() => { const g = window.__game; g.NEEDS = {...g.NEEDS, rest: 20, hunger: 80}; });
  await stand(MALL.benches[1].at[0], MALL.benches[1].at[1]); await frames(2);
  check("at night a bench offers sleep until 06:00", /sleep on the bench until 06:00/.test(await prompt()), await prompt());
  const saveBefore = await page.evaluate(() => localStorage.getItem("city_save"));
  await page.keyboard.press("KeyF"); await frames(2); s = await st();
  check("you sleep until 06:00: rest refills, hunger drains a little, and nothing is saved", Math.abs(s.hour - 6) < 0.05 && s.day === 3 && s.rest > 80 && s.hunger < 80 && s.hunger > 60 && /sleep on a bench/.test(await toast()) && await page.evaluate(b => localStorage.getItem("city_save") === b, saveBefore), JSON.stringify(s));
  await stand(MALL.door.at[0], MALL.door.at[1] - 0.6, Math.PI); await frames(2);
  check("at 06:00 the doors let you out", /Press F to leave/.test(await prompt()) && !/LOCKED/.test((await st()).sub), await prompt());
  await page.keyboard.press("KeyF"); await settled("street"); await frames(5);
  check("out onto the street at dawn, with nothing waiting", (await st()).id === "street" && !(await page.evaluate(() => window.__game.CITY.st.active)));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
