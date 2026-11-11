// Going back in, slice 2 (solo): the loadout locker and the hunting crossbow. Checks the crossbow's own ammo rule (bolts, a slow reload, a kill), that the ray still only banishes,
// that ammo packs give bolts, the locker panel, and the death rule: gear comes back from the locker for free, ammo does not. The Original has neither.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/gbi2_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const start = REGISTRY.modes.going_back_in.startChamber;
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage(); page.on("pageerror", e => errors.push(e.message));
const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
const st = () => page.evaluate(() => { const g = window.__game; return {owned: g.owned(), rounds: g.LT.rounds, bolts: g.BOW.st.bolts, cool: g.BOW.st.cool, mons: g.monsters.length, kills: g.GB.wave && g.GB.wave.kills, cleared: g.GB.wave && g.GB.wave.cleared, carry: g.GB.load && g.GB.load.carry, stash: g.GB.load && g.GB.load.stash, held: g.HELD.item}; });
// a clear line of 6 m on the floor: stand at one end looking at the other, with monster 0 at the far end
const lineUp = () => page.evaluate(() => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 4000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a), qx = x + fx * 6, qz = z + fz * 6;
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, 6.3) || g.collide({x: qx, y: g.S.floor + 0.02, z: qz}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0;
    const m = g.monsters[0]; m.pos.x = qx; m.pos.z = qz; m.state = "patrol"; return true;
  }
  return false;
});
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no crossbow and no loadout locker", await page.evaluate(() => !window.__game.owned().includes("crossbow") && !window.__game.nearStation() && window.__game.GB.load === null));

  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  let s = await st();
  check("Going back in starts with the ray, the cloak and the crossbow carried, and the crossbow's bolts", ["gun", "cloak", "crossbow"].every(i => s.owned.includes(i)) && s.bolts === 4, JSON.stringify(s));
  check("the crossbow is a fourth thing to hold (key 4)", await page.evaluate(() => { const g = window.__game; g.setHeld("crossbow"); return g.HELD.item === "crossbow"; }));

  // the ray only banishes: the monster is still there after a ray shot
  check("a clear 6 m line was found", await lineUp());
  await page.evaluate(() => { const g = window.__game; g.setHeld("gun"); g.GUN.cool = 0; g.fire(); });
  s = await st(); check("the ray does not kill (the monster count is unchanged)", s.mons === 3 && s.kills === 0, JSON.stringify(s));

  // the crossbow kills, uses a bolt, and reloads slowly
  await lineUp(); await frames(20);                                   // 1 s: past the ray's cooldown
  await lineUp();
  await page.evaluate(() => { const g = window.__game; g.setHeld("crossbow"); g.fireBow(); });
  s = await st();
  check("a bolt kills the monster in line and uses one bolt", s.mons === 2 && s.bolts === 3 && s.kills === 1, JSON.stringify(s));
  const again = await page.evaluate(() => window.__game.fireBow());
  s = await st(); check("it is reloading: a second shot at once does nothing", again === false && s.bolts === 3 && s.cool > 0, JSON.stringify(s));
  await frames(40);                                                    // 2 s
  s = await st(); check("after the reload it is ready again", s.cool === 0);
  await page.evaluate(() => { window.__game.BOW.st.bolts = 0; });
  check("an empty crossbow does not fire", (await page.evaluate(() => window.__game.fireBow())) === false);
  // killing the rest clears the wave
  await page.evaluate(() => { const g = window.__game; g.BOW.st = {bolts: 6, cool: 0}; });
  for (let k = 0; k < 2; k++) { await lineUp(); await page.evaluate(() => { const g = window.__game; g.BOW.st.cool = 0; g.fireBow(); }); }
  s = await st(); check("all three killed: the wave is cleared", s.mons === 0 && s.kills === 3 && s.cleared === true, JSON.stringify(s));

  // ammo packs give bolts to a crossbow carrier
  const b0 = (await st()).bolts;
  const gotPack = await page.evaluate(() => { const g = window.__game, p = g.LT.vis && g.LT.vis.packs[0]; if (!p) return false; g.P.p.set(p.home[0], g.S.floor + 0.02, p.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack gives bolts too (+2, capped at 6)", gotPack && s.bolts === Math.min(6, b0 + 2), JSON.stringify({b0, s}));

  // the locker: a station in the chamber, a panel, take and leave
  const stn = await page.evaluate(() => { const g = window.__game, x = g.STN.spot; if (!x) return null; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); return {near: !!g.nearStation()}; });
  check("the chamber has a loadout locker and you can reach it", !!stn && stn.near, JSON.stringify(stn));
  await page.evaluate(() => window.__game.doAction()); await frames(2);
  const panel = await page.evaluate(() => ({open: window.__game.STN.open, shown: getComputedStyle(document.getElementById("station")).display !== "none", rows: document.querySelectorAll("#station button[data-gear]").length}));
  check("the action button opens the panel, which lists the gear", panel.open && panel.shown && panel.rows === 3, JSON.stringify(panel));
  const m0 = await page.evaluate(() => window.__game.monsters.length);
  await frames(10);
  check("the game is paused while it is open", (await page.evaluate(() => window.__game.monsters.length)) === m0);
  await page.click('#station button[data-gear="crossbow"]');
  s = await st(); check("clicking the crossbow leaves it in the locker (and out of your hands)", !s.owned.includes("crossbow") && s.stash.includes("crossbow") && s.held !== "crossbow", JSON.stringify(s));
  await page.click('#station button[data-gear="crossbow"]');
  s = await st(); check("clicking again takes it back", s.owned.includes("crossbow") && !s.stash.includes("crossbow"), JSON.stringify(s));
  await page.keyboard.press("Escape");
  check("Escape closes the panel", await page.evaluate(() => !window.__game.STN.open));

  // death: gear is in the locker and ammo is gone; the locker gives the gear back for free but not the ammo
  await page.evaluate(() => { const g = window.__game; g.LT.rounds = 5; g.BOW.st.bolts = 4; g.die(); });
  await frames(100);
  s = await st();
  check("after a death you carry no gear, no rays and no bolts", s.owned.length === 0 && s.rounds === 0 && s.bolts === 0 && s.carry.length === 0 && s.stash.length === 3, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); });
  for (const gear of ["gun", "cloak", "crossbow"]) await page.click(`#station button[data-gear="${gear}"]`);
  await page.keyboard.press("Escape");
  s = await st();
  check("the locker returns all the gear for free, and no ammo", ["gun", "cloak", "crossbow"].every(i => s.owned.includes(i)) && s.rounds === 0 && s.bolts === 0, JSON.stringify(s));

  // the Original again: no crossbow, no locker
  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no crossbow, no locker, no wave", await page.evaluate(() => { const g = window.__game; return !g.owned().includes("crossbow") && g.GB.load === null && g.GB.wave === null && !g.STN.spot; }));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
