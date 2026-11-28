// Going back in, slice 1 (solo): from the Overworld's store-doors options screen, pick Going back in, land in a chamber that the manifest defines, see the wave start on
// entry, and take the stairs down to the next chamber. Also checks that the Original is unchanged (no wave, "Original" still starts a round).
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/gbi_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const mode = REGISTRY.modes.going_back_in, startId = mode.startChamber, first = REGISTRY.chamber(startId), nextId = first && first.next, next = nextId && REGISTRY.chamber(nextId);
check("the manifest names a built first chamber and the chamber after its stairs down", !!first && !!next && !!REGISTRY.pageScenes[startId] && !!REGISTRY.pageScenes[nextId], JSON.stringify({startId, nextId}));
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const ctx = await browser.newContext({viewport: {width: 900, height: 700}});
const page = await ctx.newPage(); page.on("pageerror", e => errors.push(e.message));
const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no wave", await page.evaluate(() => window.__game.GB.wave === null));
  await page.evaluate(() => window.__game.loadScene("parking_lot")); await settled("parking_lot");
  await page.evaluate(() => { const g = window.__game; g.P.p.set(0, 9.62, 33); g.P.v.set(0, 0, 0); g.P.yaw = 0; g.P.pitch = 0; g.keys.KeyW = true; });
  for (let i = 0; i < 80 && !(await page.evaluate(() => window.__game.OW.open)); i++) await frames(5);
  await page.evaluate(() => { window.__game.keys.KeyW = false; });
  const o = await page.evaluate(() => ({open: window.__game.OW.open, back: document.getElementById("o-back").disabled, text: document.getElementById("o-back").textContent}));
  check("the options screen opens and Going back in can be chosen", o.open && !o.back, JSON.stringify(o));

  await page.click("#o-back"); await settled(startId);
  const e1 = await page.evaluate(() => { const g = window.__game; return {opts: getComputedStyle(document.getElementById("options")).display, wave: g.GB.wave && {...g.GB.wave}, mons: g.monsters.length, mode: g.GB.mode, hp: g.P.p.toArray(), floor: g.S.floor, dist: Math.min(...g.monsters.map(m => Math.hypot(m.pos.x - g.P.p.x, m.pos.z - g.P.p.z)))}; });
  check("you land in the first chamber and the options screen closes", e1.opts === "none" && e1.mode === "going_back_in");
  check("the wave started on entry: the wave number, and as many monsters as the manifest says", !!e1.wave && e1.wave.no === first.wave.no && e1.mons === first.wave.monsters, JSON.stringify(e1.wave));
  check("the monsters start well away from you", e1.dist >= 16, String(e1.dist));
  const stand = await page.evaluate(() => { const g = window.__game; g.sim(0.05, 0); return !g.collide({x: g.P.p.x, y: g.P.p.y + 0.02, z: g.P.p.z}); });
  check("you are not standing inside a wall", stand);

  // the way on, as a player takes it: a Blender chamber's link (F at its spot, #123) or a store floor's stairs-down door, opened and stepped through
  const wayOn = async (fromId, toId) => {
    const ch = REGISTRY.chamber(fromId), n = ch.stairsDown;
    const kind = await page.evaluate(([n, to]) => { const g = window.__game, dr = g.doors.find(d => d.d.name === n && d.link), x = (g.S.sceneLinks || []).find(l => l.door === n);
      return dr ? (dr.link.scene === to ? "door" : "door to " + dr.link.scene) : x && x.link && x.link.to.scene === to ? "link" : "none"; }, [n, toId]);
    check(`${fromId}: its way on (${n}) leads to ${toId}`, kind === "door" || kind === "link", kind);
    if (kind === "link") {
      await page.evaluate(n => { const g = window.__game, x = g.S.sceneLinks.find(l => l.door === n); g.teleport(x.at); g.P.v.set(0, 0, 0); g.doAction(); }, n);
    } else if (kind === "door") {
      await page.evaluate(n => { const g = window.__game, dr = g.doors.find(d => d.d.name === n); g.P.p.set(dr.cx, g.S.floor + 0.02, dr.cz + 1.2); g.P.v.set(0, 0, 0); g.openDoor(dr, true); }, n);          // the portal (its hallway) is built when the door opens
      check(`${fromId}: the door opens and the hallway behind it is built`, await page.evaluate(n => !!window.__game.doors.find(d => d.d.name === n).hallN, n));
      for (let i = 0; i < 30 && !(await page.evaluate(n => window.__game.doors.find(d => d.d.name === n).p >= 0.6, n)); i++) await frames(5);
      await page.evaluate(n => { const g = window.__game, dr = g.doors.find(d => d.d.name === n); g.P.p.set(dr.hallC[0] + dr.hallN[0] * 0.3, g.S.floor + 0.02, dr.hallC[1] + dr.hallN[1] * 0.3); }, n);
      await frames(2);
    }
    await settled(toId);
    const e2 = await page.evaluate(() => { const g = window.__game; return {wave: g.GB.wave && {...g.GB.wave}, mons: g.monsters.length, floor: g.S.floor, y: g.P.p.y}; }), to = REGISTRY.chamber(toId);
    check(`${fromId} to ${toId}: you land in the next chamber, on its floor`, Math.abs(e2.floor - to.floorY) < 0.01 && Math.abs(e2.y - to.floorY) < 0.5, JSON.stringify(e2));
    check(`${toId} starts its own wave`, !!e2.wave && e2.wave.no === to.wave.no && e2.mons === to.wave.monsters, JSON.stringify(e2));
  };
  await wayOn(startId, nextId);
  // and the store's own stairs: from L4's chamber (gbi_L4_4) down to L3's first
  await page.evaluate(() => window.__game.loadScene("gbi_L4_4")); await settled("gbi_L4_4");
  await wayOn("gbi_L4_4", "gbi_L3_1");
  await page.evaluate(id => window.__game.loadScene(id), nextId); await settled(nextId);

  // a random-spot respawn after a death stays in the chamber (death is real here: the doc's rule; the locker comes with slice 2)
  await page.evaluate(() => { window.__game.die(); });
  await frames(100);                                                                                   // 5 s of game time: past the 3 s wait
  check("after a death you are back in the same chamber", await page.evaluate(n => window.__game.S.id === n && !window.__game.dead, nextId));

  // the Original is unchanged: a normal floor has no wave
  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("the Original's floors have no wave", await page.evaluate(() => window.__game.GB.wave === null));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
