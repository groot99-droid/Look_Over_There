// The Blender areas are walkable (shared/farway.scenes.js, made by tools/blender/wire_scenes.py): every scene they add loads on the page with its model and its
// colliders and no page error, and every built link between them is followed. For each link: stand at its F spot (the scene file's `at`, or the link's own `from.at`),
// press F (or, for a `walk` link, step onto it), and arrive in the scene it names, where it says, facing the way it says. A planned link says it is shut.
// Also the joins onto the older scenes: the apartment tower's door into the hotel's lobby, your apartment as room 301 on floor 3, the mall's wings off its entrance,
// the grocery's aisles off its main floor, the lab's B2 door into Secret Operations, the museum's side wing, and the lot's walks to the Overworld's scenes.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/walkable_test.mjs [area ...]   (no area: all of them)
import {createRequire} from "node:module";
import fs from "node:fs";
import {createServer} from "../server/server.js";
import {BLENDER_SCENES, BLENDER_LINKS} from "../shared/farway.scenes.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const only = process.argv.slice(2);
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const wait = (page, fn, arg, ms = 60000) => page.waitForFunction(fn, arg, {timeout: ms, polling: 100}).then(() => true, () => false);
const settled = (page, id) => wait(page, i => window.__game.S.id === i && !window.__game.loading, id, 180000);
const where = page => page.evaluate(() => { const g = window.__game; return {id: g.S.id, p: g.P.p.toArray().map(v => +v.toFixed(2)), yaw: +g.P.yaw.toFixed(3)}; });
const at = (page, p) => page.evaluate(p => { const g = window.__game; g.teleport(p); g.P.v.set(0, 0, 0); }, p);
const doc = id => JSON.parse(fs.readFileSync(new URL(`../world/${id}.json`, import.meta.url), "utf8"));
const atOf = l => l.from.at || (doc(l.from.scene).links || []).find(k => k.door === l.from.door)?.at;
// a scene whose way in is drawn by the page's own code, not a scene file (the street, the apartment, the forest): loaded straight, its links checked by the manifest test
const CODE = ["street", "apartment", "forest", "meadow"];
try {
  const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage(); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  // the City's clock at noon, so the stores and the mall are open and nothing locks you in
  await page.evaluate(() => { const g = window.__game; if (g.CITY) g.CITY.t = 12 / 24 * (g.CITY.day || 1200); });

  const areas = Object.entries(BLENDER_SCENES).filter(([a]) => !only.length || only.includes(a));
  for (const [area, scenes] of areas) {
    for (const s of scenes) {
      const e0 = errors.length;
      await page.evaluate(s => window.__game.loadScene(s.id, null), s);
      const ok = await settled(page, s.id);
      const info = ok ? await page.evaluate(() => { const g = window.__game; let meshes = 0; g.S.root.traverse(o => { if (o.isMesh) meshes++; }); return {meshes, boxes: g.boxes.length, floor: g.S.floor, links: (g.S.sceneLinks || []).length}; }) : null;
      check(`${area}/${s.id}: loads with its model and colliders, no page error`, ok && info.meshes > 0 && info.boxes > 0 && Math.abs(info.floor - s.floorY) < 1e-6 && errors.length === e0,
        JSON.stringify(info) + (errors.length > e0 ? " " + errors.slice(e0).join(" | ") : ""));
    }
    const mine = new Set(scenes.map(s => s.id));
    for (const l of BLENDER_LINKS.filter(l => mine.has(l.from.scene) || mine.has(l.to.scene))) {
      if (CODE.includes(l.from.scene)) continue;
      const spot = atOf(l);
      if (!spot) { check(`${l.id}: has an F spot`, false); continue; }
      await page.evaluate(id => window.__game.loadScene(id, null), l.from.scene); await settled(page, l.from.scene);
      await at(page, [spot[0], spot[1], spot[2]]);
      if (l.status !== "built") {
        const p = await page.evaluate(() => window.__game.sceneLinkPrompt());
        check(`${l.id}: planned, so it says it is shut`, /shut/.test(p), p); continue;
      }
      if (l.connector !== "walk") {
        const p = await page.evaluate(() => window.__game.sceneLinkPrompt() || window.__game.cityPrompt());
        check(`${l.id}: at its F spot you are offered the way`, /Press F/.test(p), p);
        await page.evaluate(() => window.__game.doAction());
      } else {
        await at(page, [spot[0] + 3, spot[1], spot[2]]); await page.waitForTimeout(150); await at(page, [spot[0], spot[1], spot[2]]);          // arrive away from it, then step onto it
      }
      const ok = await settled(page, l.to.scene), w = await where(page);
      const face = l.to.face ? Math.abs(((w.yaw - Math.atan2(-l.to.face[0], -l.to.face[1])) + 3 * Math.PI) % (2 * Math.PI) - Math.PI) < 0.05 : true;
      check(`${l.id}: leads to ${l.to.scene}, at its arrival, facing its way`, ok && Math.hypot(w.p[0] - l.to.arrive[0], w.p[2] - l.to.arrive[2]) < 0.6 && face, JSON.stringify(w));
    }
  }
  check("no page errors", errors.length === 0, errors.slice(0, 5).join(" | "));
} catch (e) { check("the run finished", false, e.stack); } finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASS");
process.exit(failed ? 1 : 0);
