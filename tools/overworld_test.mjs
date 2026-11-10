// The Overworld, v0: after the Original (solo) the results screen offers a walk out to the parking lot; you arrive at the table facing the store, the table and the store
// doors are solid, walking up to the doors opens the options screen, and a clear sky is lit only there. Needs Playwright + Chromium and internet for three.js from unpkg.
// Usage: node tools/overworld_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
import {requirementsMet} from "../shared/manifest.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const link = REGISTRY.linkFrom("L4", "front_doors");
check("the manifest has the built link, shut until original_complete is held", !!link && link.status === "built" && !requirementsMet(link, []).ok && requirementsMet(link, ["original_complete"]).ok);
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const ctx = await browser.newContext({viewport: {width: 900, height: 700}});          // one context: localStorage survives a reload, as for a player
async function solo(init) {
  const page = await ctx.newPage(); page.on("pageerror", e => errors.push(e.message));
  if (init) await page.addInitScript(init);
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  return page;
}
const settled = (page, id) => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
const frames = (page, n) => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
try {
  // storage blocked: we cannot know the flag, so no welcome and no way on (a link that requires the flag stays shut)
  const b = await solo(() => { Object.defineProperty(window, "localStorage", {get() { throw new Error("blocked"); }}); });
  await b.evaluate(() => { const g = window.__game; g.FIN.t0 = performance.now() - 300000; g.goOut(); });
  check("without a readable flag the walk out is not offered", await b.evaluate(() => document.getElementById("r-walk").hidden));
  await b.close();

  const p = await solo();
  await p.evaluate(() => window.__game.loadScene("L4")); await settled(p, "L4");                  // a solo round starts on B1; finish from the store, as a player does
  await p.evaluate(() => { const g = window.__game; g.FIN.t0 = performance.now() - 600000; g.goOut(); });
  check("after the Original the results screen offers the walk out", await p.evaluate(() => !document.getElementById("r-walk").hidden));
  const skyL4 = await p.evaluate(() => { let v = null; window.__game.S.root.traverse(o => { if (o.name === "Sky_LOT_Exterior") v = o.material.emissiveIntensity; }); return v; });
  await p.click("#r-walk"); await settled(p, "parking_lot");
  const at = await p.evaluate(() => { const g = window.__game; return {p: g.P.p.toArray(), yaw: g.P.yaw, ground: g.P.ground, results: getComputedStyle(document.getElementById("results")).display, fin: !!g.FIN.results, monsters: g.monsters.length}; });
  await frames(p, 10);
  const land = await p.evaluate(() => { const g = window.__game; return {y: g.P.p.y, ground: g.P.ground}; });
  check("you arrive at the table, facing the store, standing on the ground", Math.abs(at.p[0] - link.to.arrive[0]) < 0.01 && Math.abs(at.p[2] - link.to.arrive[2]) < 0.01 && Math.abs(at.yaw) < 0.01 && land.ground && Math.abs(land.y - 9.6) < 0.05, JSON.stringify({at, land}));
  check("the results screen is gone, the HUD is back, and there are no monsters", at.results === "none" && !at.fin && at.monsters === 0);
  const solid = await p.evaluate(() => { const g = window.__game, c = (x, z) => !!g.collide({x, y: 9.62, z}); return {table: c(-8, 41), chair: c(-6.65, 41), doors: c(0, 27.2), open: c(-8, 43.6)}; });
  check("the table, a chair and the store doors are solid; your spawn is clear", solid.table && solid.chair && solid.doors && !solid.open, JSON.stringify(solid));
  const sky = await p.evaluate(() => { let v = null; window.__game.S.root.traverse(o => { if (o.name === "Sky_LOT_Exterior") v = o.material.emissiveIntensity; }); return v; });
  check("the Overworld has its clear sky, brighter than the store's", sky > skyL4, `${skyL4} -> ${sky}`);

  // walk to the doors: the options screen opens; Going back in is shown and can be chosen (session 8; tools/gbi_test.mjs drives it)
  await p.evaluate(() => { const g = window.__game; g.P.p.set(0, 9.62, 33); g.P.v.set(0, 0, 0); g.P.yaw = 0; g.P.pitch = 0; g.keys.KeyW = true; });
  for (let i = 0; i < 80 && !(await p.evaluate(() => window.__game.OW.open)); i++) await frames(p, 5);
  await p.evaluate(() => { window.__game.keys.KeyW = false; });
  const o = await p.evaluate(() => ({open: window.__game.OW.open, shown: getComputedStyle(document.getElementById("options")).display !== "none", orig: !document.getElementById("o-original").disabled, back: document.getElementById("o-back").disabled, text: document.getElementById("o-back").textContent}));
  check("walking up to the store doors opens the options screen", o.open && o.shown);
  check("Original and Going back in can both be chosen", o.orig && !o.back && /Going back in/.test(o.text), JSON.stringify(o));
  await p.click("#o-close");
  await frames(p, 20);
  check("Not yet closes it, and it does not reopen while you stand there", await p.evaluate(() => !window.__game.OW.open && getComputedStyle(document.getElementById("options")).display === "none"));
  await p.evaluate(() => { const g = window.__game; g.P.p.set(-8, 9.62, 44); g.P.v.set(0, 0, 0); });
  await frames(p, 10);
  await p.evaluate(() => { const g = window.__game; g.P.p.set(0, 9.62, 33); g.P.v.set(0, 0, 0); g.P.yaw = 0; g.keys.KeyW = true; });
  for (let i = 0; i < 80 && !(await p.evaluate(() => window.__game.OW.open)); i++) await frames(p, 5);
  await p.evaluate(() => { window.__game.keys.KeyW = false; });
  check("after walking away and back it opens again", await p.evaluate(() => window.__game.OW.open));
  await p.evaluate(() => window.__game.closeOptions());

  // the sky is the Overworld's only: back in the store it is as it was
  await p.evaluate(() => window.__game.loadScene("L4")); await settled(p, "L4");
  const skyBack = await p.evaluate(() => { let v = null; window.__game.S.root.traverse(o => { if (o.name === "Sky_LOT_Exterior") v = o.material.emissiveIntensity; }); return v; });
  check("the store's sky is unchanged after a visit", skyL4 !== null && skyBack === skyL4, `${skyL4} vs ${skyBack}`);

  // a reload keeps the flag, so the way on is still open
  await p.close();
  const q = await solo();
  check("a reload keeps original_complete", await q.evaluate(() => window.__game.heldFlags().includes("original_complete")));
  await q.close();
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
