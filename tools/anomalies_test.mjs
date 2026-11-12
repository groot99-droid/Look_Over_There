// City anomalies (slice 8): the sign that changes one letter each time you walk past it, the pedestrians who all face up the street by day, and the lit window at night
// with no building round it. Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/anomalies_test.mjs [screenshot dir]
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, BUS_STREET} from "../shared/city.js";
import {SIGN, PEDESTRIANS, GHOST_WINDOW} from "../shared/anomalies.js";
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
  const stand = (x, z, yaw) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const walk = async n => { await page.evaluate(() => { window.__game.keys.KeyW = true; }); await frames(n); await page.evaluate(() => { window.__game.keys.KeyW = false; }); await frames(2); };
  const at = h => page.evaluate(t => { window.__game.CITY.t = t; window.__game.CITY.ui = 0; }, secondsAt(h)).then(() => frames(3));
  const anom = () => page.evaluate(() => { const g = window.__game, a = g.CITY.anom; return a && {passes: g.CITY.signPasses, map: a.sign.material.map.uuid, peds: a.peds.children.length, pedsOn: a.peds.visible, yaws: a.peds.children.map(f => f.rotation.y),
    ghostOn: a.ghost.visible, glow: a.ghost.material.emissiveIntensity, z: g.P.p.z}; });
  const shot = async name => { if (SHOTS) await page.screenshot({path: `${SHOTS}/anomalies_${name}.png`}); };

  await page.evaluate(([p, f]) => window.__game.loadScene("street", {pos: p, face: f}), [BUS_STREET.arrive, BUS_STREET.face]); await settled("street");
  await at(12);
  let a = await anom();
  check("on Hallam Row the sign is up and has not been passed yet", !!a && a.passes === 0, JSON.stringify(a));

  // walk up the street past the sign
  await stand(-3, SIGN.z + 4, 0); await frames(2);
  const map0 = (await anom()).map;
  await walk(40);
  a = await anom();
  check("walking up the street past the sign counts one pass and redraws it", a.passes === 1 && a.map !== map0 && a.z < SIGN.z, JSON.stringify(a));
  // and back down past it
  const map1 = a.map;
  await page.evaluate(() => { window.__game.P.yaw = Math.PI; }); await walk(40);
  a = await anom();
  check("walking back down past it counts a second pass", a.passes === 2 && a.map !== map1 && a.z > SIGN.z, JSON.stringify(a));
  // standing near the sign without crossing its line changes nothing
  await stand(-3, SIGN.z + 1.5, 0); await frames(4); await stand(-3, SIGN.z + 0.4, 0); await frames(4); await stand(-3, SIGN.z + 2, 0); await frames(4);
  check("going up to the sign and turning back is not a pass", (await anom()).passes === 2);

  // by day: the pedestrians are out, all facing the same way; no window
  await stand(3.6, -20, 0); await at(12);
  a = await anom();
  check("at noon all the pedestrians are on the sidewalks", a.pedsOn && a.peds === PEDESTRIANS.length, JSON.stringify(a));
  check("and every one of them faces the same way (up the street)", a.yaws.every(y => y === a.yaws[0]) && a.yaws[0] === 0, JSON.stringify(a.yaws));
  check("by day there is no window over the empty lot", !a.ghostOn, JSON.stringify(a));
  await shot("noon");

  // the pedestrians are gone at closing; the window lights after dark
  await at(20.5);
  a = await anom();
  check("when the stores close the pedestrians are gone", !a.pedsOn, JSON.stringify(a));
  await at(22);
  a = await anom();
  check("after dark a window is lit where there is no building", a.ghostOn && a.glow > 0.5 && !a.pedsOn, JSON.stringify(a));
  const ray = await page.evaluate(([x, y, z]) => window.__game.segClear(0, 1.6, -100, x, y, z, 0.05), GHOST_WINDOW.at);
  check("nothing solid stands between the street and the window", ray === true, String(ray));
  await stand(0, -100, Math.atan2(-(GHOST_WINDOW.at[0] - 0), -(GHOST_WINDOW.at[2] + 100))); await frames(3); await shot("night");

  // leave and come back: the sign keeps its passes, and coming back is not a pass (the bus stop is past the sign from where you left, so a stale position would count one)
  const before = (await anom()).passes;
  await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await settled("apartment"); await frames(3);
  await page.evaluate(([p, f]) => window.__game.loadScene("street", {pos: p, face: f}), [BUS_STREET.arrive, BUS_STREET.face]); await settled("street"); await frames(5);
  a = await anom();
  check("back on the street the sign keeps its passes, and arriving is not a pass", a.passes === before && before >= 2, JSON.stringify({before, ...a}));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
