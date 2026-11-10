// Automated check, two layers: node --test tools/physics/physics.test.mjs
//  1. both engines in Node: the ball falls, bounces and comes to rest; the swing swings with the pendulum period.
//  2. the prototype page in headless Chromium (software GL not involved: the page is 2D canvas), stepping the page's own world through window.__physics.
// Chromium is skipped (and says so) when playwright is not installed. Libraries are served from node_modules through route interception, so it needs no network.
import test from "node:test";
import assert from "node:assert/strict";
import {createRequire} from "node:module";
import {readFile} from "node:fs/promises";
import {load} from "./engines/index.mjs";
import {DT, ballScene, swingScene, swingAngle} from "./scenes.mjs";
import {serve} from "./serve.mjs";

const G = 9.81;
// the ball: dropped from 5 m (centre), radius 0.11. Returns what a watcher would see.
function dropTrace(e, seconds = 20) {
  const {ball, r} = ballScene(e, {drop: 5});
  const tr = []; for (let i = 0; i < seconds / DT; i++) { e.step(DT); const p = e.pos(ball); tr.push({t: (i + 1) * DT, y: p[1], v: Math.hypot(...e.vel(ball)), s: e.asleep(ball)}); }
  return {tr, r};
}
function analyse(tr, r) {
  const hit = tr.findIndex((s, i) => i && s.y <= r + 0.02);                 // first contact with the floor
  let apex1 = 0, k = hit + 3; while (k < tr.length && tr[k].y >= tr[k - 1].y - 1e-9 || k < hit + 10) { apex1 = Math.max(apex1, tr[k].y); k++; }
  const monotonic = tr.slice(0, hit).every((s, i, a) => !i || s.y < a[i - 1].y);
  const calm = tr.findIndex(s => s.v < 0.05 && Math.abs(s.y - r) < 0.03);
  return {hit, tHit: tr[hit].t, apex1, monotonic, calm, tCalm: calm < 0 ? null : tr[calm].t, final: tr.at(-1)};
}
function swingPeriod(e, seconds = 20) {
  const sw = swingScene(e, {length: 2, angle: 0.5}); const a = [];
  for (let i = 0; i < seconds / DT; i++) { e.step(DT); a.push(swingAngle(e, sw)); }
  const up = []; for (let i = 1; i < a.length; i++) if (a[i - 1] < 0 && a[i] >= 0) up.push(i * DT);       // upward zero crossings: one per period
  return {a, period: up.length > 2 ? (up[2] - up[0]) / 2 : NaN, min: Math.min(...a), max: Math.max(...a)};
}
// a rigid pendulum of length 2 released at 0.5 rad: T = 2*pi*sqrt(L/g) with the large-angle (+1.6%) and seat-inertia (+0.4%) corrections
const T = 2 * Math.PI * Math.sqrt(2 / G) * 1.016 * 1.004;

for (const name of ["cannon", "rapier"]) {
  test(`${name}: ball falls, bounces, comes to rest`, async () => {
    const e = await load(name); const {tr, r} = dropTrace(e); const a = analyse(tr, r);
    console.log(name, "ball: first contact", a.tHit.toFixed(2), "s, first rebound apex", a.apex1.toFixed(2), "m, calm at", a.tCalm?.toFixed(2), "s, final y", a.final.y.toFixed(3), "asleep", a.final.s);
    assert.ok(a.monotonic, "falls without stopping");
    assert.ok(Math.abs(a.tHit - Math.sqrt(2 * (5 - r) / G)) < 0.06, "free fall time matches sqrt(2h/g)");
    assert.ok(a.apex1 > 0.4 && a.apex1 < 4.5, "bounces, but not as high as it fell (apex " + a.apex1 + ")");
    assert.ok(a.calm > 0 && a.tCalm < 15, "comes to rest within 15 s");
    assert.ok(Math.abs(a.final.y - r) < 0.03 && a.final.v < 0.05, "rests on the floor, not sinking or floating");
    e.free();
  });
  test(`${name}: swing swings with the pendulum period`, async () => {
    const e = await load(name); const s = swingPeriod(e);
    console.log(name, "swing: period", s.period.toFixed(3), "s (theory", T.toFixed(3) + "), range", s.min.toFixed(2), "to", s.max.toFixed(2), "rad");
    assert.ok(s.min < -0.4 && s.max > 0.4, "swings through the bottom to the other side");
    assert.ok(Math.abs(s.period - T) < 0.1, "period within 0.1 s of the pendulum formula");
    assert.ok(s.max < 0.55, "does not gain energy");
    e.free();
  });
}

let chromium; try { chromium = createRequire(import.meta.url)("playwright").chromium; } catch { /* skipped below */ }
for (const name of ["cannon", "rapier"]) {
  test(`${name}: prototype page in headless Chromium`, {skip: !chromium && "playwright not installed"}, async () => {
    const srv = await serve(0), port = srv.address().port;
    const browser = await chromium.launch(); const page = await browser.newPage(); const errs = [];
    try {
    page.on("pageerror", x => errs.push(String(x))); page.on("console", m => m.type() === "error" && errs.push(m.text()));
    const nm = new URL("./node_modules/", import.meta.url);
    await page.route("https://unpkg.com/**", async route => {
      const u = route.request().url();
      const f = u.includes("cannon-es") ? "cannon-es/dist/cannon-es.js" : "@dimforge/rapier3d-compat/rapier.mjs";
      await route.fulfill({body: await readFile(new URL(f, nm)), contentType: "text/javascript"});
    });
    await page.goto(`http://localhost:${port}/?engine=${name}`);
    await page.waitForFunction(() => window.__physics && window.__physics.ready, null, {timeout: 20000});
    const y0 = await page.evaluate(() => window.__physics.ballPos()[1]);
    await page.waitForTimeout(500);                                    // real frames: the page's own loop must advance the world
    const y1 = await page.evaluate(() => window.__physics.ballPos()[1]);
    assert.ok(y1 < y0 - 0.5, `the page's loop drops the ball (${y0} -> ${y1})`);
    const r = await page.evaluate(() => { const p = window.__physics; let minY = 9, bounced = false, prev = p.ballPos()[1], up = 0, swMin = 0, swMax = 0;
      for (let i = 0; i < 1200; i++) { p.step(1); const y = p.ballPos()[1]; if (y > prev + 1e-4 && y < 6) up++; prev = y; const a = p.angle(); swMin = Math.min(swMin, a); swMax = Math.max(swMax, a); }
      p.step(600); return {y: p.ballPos()[1], v: Math.hypot(...p.ballVel()), up, swMin, swMax}; });
    assert.deepEqual(errs, [], "no page errors");
    assert.ok(r.up > 5, "the ball went up again after hitting the floor");
    assert.ok(Math.abs(r.y - 0.11) < 0.03 && r.v < 0.05, `at rest on the floor (y=${r.y}, v=${r.v})`);
    assert.ok(r.swMin < -0.3 && r.swMax > 0.3, `swing crossed the bottom (${r.swMin}..${r.swMax})`);
    } finally { await browser.close(); srv.close(); }      // never leave the browser or server running when an assertion fails
  });
}
