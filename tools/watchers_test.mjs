// The watchers (slice 21): at night three of Hallam Row's lit windows have a dark figure inside that turns to follow you; by day they are gone. Seeing one counts as spotting
// an anomaly for the REPORT page. Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/watchers_test.mjs [screenshot dir]
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt} from "../shared/city.js";
import {WATCHERS, watcherAt} from "../shared/anomalies.js";
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
  const setT = h => page.evaluate(t => { window.__game.CITY.t = t; window.__game.CITY.ui = 0; }, secondsAt(h, 2));
  const w = () => page.evaluate(() => { const g = window.__game, a = g.CITY.anom; return {on: a.watchers.visible, n: a.watchers.children.length, figs: a.watchers.children.map(f => [f.position.x, f.position.z, f.rotation.y]), p: g.P.p.toArray(), seen: !!g.CITY.seen.spotted.watchers, toast: document.getElementById("toast").textContent}; });
  const faces = (f, px, pz) => { const fx = -Math.sin(f[2]), fz = -Math.cos(f[2]), dx = px - f[0], dz = pz - f[1], d = Math.hypot(dx, dz); return (fx * dx + fz * dz) / d > 0.999; };
  const face = (fx, fz, tx, tz) => Math.atan2(-(tx - fx), -(tz - fz));

  await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, 0], face: [0, -1]})); await settled("street");
  await setT(12); await stand(0, 0, 0); await frames(3);
  let s = await w();
  check("by day there is nobody in the windows", s.n === WATCHERS.length && !s.on, JSON.stringify(s));
  await setT(22); await frames(3); s = await w();
  check("after dark three figures stand in lit windows", s.on && s.n === 3, JSON.stringify(s));
  // and they can be seen: none is buried in its building (the street's buildings are solid boxes; the figure stands against the outside of the lit pane)
  const clear = await page.evaluate(ws => { const g = window.__game; return ws.map(p => g.segClear(0, g.S.floor + 1.6, p.z + 6, p.x, g.S.floor + p.y - 0.35, p.z, 0.3)); }, WATCHERS.map(watcherAt));
  check("each figure is outside its wall: a clear line reaches it from the street", clear.every(Boolean), JSON.stringify(clear));
  // they turn to follow you as you move
  const t = watcherAt(WATCHERS[1]);                                                    // in a window of 330 Hallam Row, east side
  await stand(-3, t.z + 12, 0); await frames(2); s = await w();
  check("each one faces you", s.figs.every(f => faces(f, s.p[0], s.p[2])), JSON.stringify(s.figs));
  await stand(-3, t.z - 12, Math.PI); await frames(2); const s2 = await w();
  check("walk past and they have turned to keep facing you", s2.figs.every(f => faces(f, s2.p[0], s2.p[2])) && Math.abs(s2.figs[1][2] - s.figs[1][2]) > 0.5, JSON.stringify([s.figs[1], s2.figs[1]]));
  check("you have not spotted one yet: it was never in front of you", !s2.seen);
  // look at one: spotted
  await stand(0, t.z + 8, face(0, t.z + 8, t.x, t.z)); await frames(20); s = await w();
  check("looking at one spots it, and you notice it is watching you", s.seen && /watching you/.test(s.toast), JSON.stringify({seen: s.seen, toast: s.toast}));
  if (SHOTS) await page.screenshot({path: `${SHOTS}/watchers_night.png`});
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
