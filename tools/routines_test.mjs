// Pedestrians with routines (slice 18): by day each pedestrian walks a short beat along its sidewalk while you are not looking, and stands still the moment it is in
// your view. They always face up the street. At night they are gone and nothing moves.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/routines_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt} from "../shared/city.js";
import {PED_ROUTE, pedAt} from "../shared/anomalies.js";
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
  const stand = (x, z, yaw = 0) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const peds = () => page.evaluate(() => { const g = window.__game, a = g.CITY.anom; return {s: g.CITY.peds.map(p => p.s), on: a.peds.visible, mesh: a.peds.children.map(f => [f.position.x, f.position.z, f.rotation.y])}; });
  const moved = (a, b) => a.s.map((s, i) => Math.abs(s - b.s[i]) > 1e-6);

  await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, -138], face: [0, -1]})); await settled("street");
  await page.evaluate(t => { window.__game.CITY.t = t; window.__game.CITY.ui = 0; }, secondsAt(12, 2)); await frames(2);
  // at the north end of the street, facing the end: every pedestrian is behind you
  await stand(0, -138, 0); await frames(2);
  let p0 = await peds(); await frames(60); let p1 = await peds();
  check("with your back to all of them, every pedestrian walks its beat", p1.on && moved(p0, p1).every(Boolean), JSON.stringify({p0: p0.s, p1: p1.s}));
  check("they stay on their beats, 3 m either side of where they stood", p1.s.every(s => Math.abs(s) <= PED_ROUTE + 1e-9), JSON.stringify(p1.s));
  check("the figures are where the routines say", p1.mesh.every(([x, z], i) => { const [ex, ez] = pedAt(i, p1.s[i]); return Math.abs(x - ex) < 1e-6 && Math.abs(z - ez) < 1e-6; }), JSON.stringify(p1.mesh));
  check("even walking, they all face up the street", p1.mesh.every(m => m[2] === 0), JSON.stringify(p1.mesh.map(m => m[2])));
  // turn round: the ones in front of you stop
  await page.evaluate(() => { window.__game.P.yaw = Math.PI; }); await frames(2);
  p0 = await peds(); await frames(80); p1 = await peds();
  const still = moved(p0, p1).map(m => !m);
  check("turn round and look down the street: the nearest ones, in front of you, stand still", still[5] && still[4] && still.filter(Boolean).length >= 3, JSON.stringify({still, s: p1.s}));
  check("and still all face up the street, toward you", p1.mesh.every(m => m[2] === 0));
  // look away again: they go on
  await page.evaluate(() => { window.__game.P.yaw = 0; }); await frames(2);
  p0 = await peds(); await frames(40); p1 = await peds();
  check("look away again and they walk on", moved(p0, p1).every(Boolean), JSON.stringify({p0: p0.s, p1: p1.s}));

  // at night they are gone and nothing moves
  await page.evaluate(t => { window.__game.CITY.t = t; window.__game.CITY.ui = 0; }, secondsAt(21, 2)); await frames(3);
  p0 = await peds(); await frames(60); p1 = await peds();
  check("at night the pedestrians are gone and their routines stop", !p1.on && moved(p0, p1).every(m => !m), JSON.stringify({on: p1.on}));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
