// Going back in: the pneumatic bolt driver (docs/ITEMS.md 4.1, solo). Checks its own ammo (nails and the pressure gauge), that a hit hurts a monster (it has health: 100 for a creature)
// and does not kill outright, that the fourth nail does, that packs give nails, the locker row and key 5, and the death rule (nails gone, the gun back for free). The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/driver_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, d = g.DRV.st; return {owned: g.owned(), held: g.HELD.item, nails: d.nails, air: d.air, cool: d.cool, mons: g.monsters.length, hp: g.monsters[0] ? g.monsters[0].hp : null, kills: g.GB.wave && g.GB.wave.kills, shotT: g.P.shotT, carry: g.GB.load && g.GB.load.carry, stash: g.GB.load && g.GB.load.stash}; });
// a clear line of 6 m on the floor: stand at one end looking at the other, with monster 0 at the far end (the same helper as tools/gbi2_test.mjs)
const lineUp = () => page.evaluate(() => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 4000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a), qx = x + fx * 6, qz = z + fz * 6;
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, 6.3) || g.collide({x: qx, y: g.S.floor + 0.02, z: qz}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    const m = g.monsters[0]; if (!m) return true; m.pos.x = qx; m.pos.z = qz; m.state = "patrol"; return true;
  }
  return false;
});
const shoot = async () => { await lineUp(); return page.evaluate(() => { const g = window.__game; g.DRV.st.cool = 0; return g.fireDriver(); }); };
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  await page.keyboard.press("Digit5");
  check("the Original has no bolt driver and key 5 holds nothing", await page.evaluate(() => !window.__game.owned().includes("driver") && window.__game.HELD.item !== "driver" && window.__game.GB.load === null));

  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("Going back in starts with the driver carried and 16 nails", s.owned.includes("driver") && s.nails === 16 && s.air === 8, JSON.stringify(s));
  await page.keyboard.press("Digit5"); s = await st();
  check("key 5 holds it", s.held === "driver", JSON.stringify(s));
  check("the creature has 100 health", s.hp === 100, JSON.stringify(s));

  check("a clear 6 m line was found", await lineUp());
  check("shot 1 fires", await shoot());
  s = await st();
  check("a full-gauge nail does 35: the creature is hurt, not dead; one nail and an eighth of air used", s.hp === 65 && s.mons === 3 && s.nails === 15 && s.air === 7, JSON.stringify(s));
  check("the shot is a puff of noise (0.25 s)", s.shotT > 0 && s.shotT <= 0.25, JSON.stringify(s));
  const again = await page.evaluate(() => window.__game.fireDriver());
  s = await st(); check("it is cooling: a second shot at once does nothing", again === false && s.nails === 15 && s.cool > 0, JSON.stringify(s));
  await shoot(); await shoot(); s = await st();
  check("three nails (35 + 32.5 + 30) leave the creature on 2.5 health", s.hp === 2.5 && s.mons === 3 && s.kills === 0 && s.nails === 13, JSON.stringify(s));
  await shoot(); s = await st();
  check("the fourth kills it and counts toward the wave", s.mons === 2 && s.kills === 1 && s.nails === 12, JSON.stringify(s));

  // air refills when you stop; an empty gauge still fires; no nails, no shot
  await frames(40 + 20 * 6);                                          // 2 s idle + 6 s: one eighth per 1.5 s after the first second
  s = await st(); check("the air refills while you wait (4 eighths gone: 1 s, then 1.5 s each, is 7 s)", s.air === 8, JSON.stringify(s));
  await page.evaluate(() => { window.__game.DRV.st.air = 0; });
  check("an empty gauge still fires", await shoot());
  s = await st(); check("... for 15 damage (the next monster had 100)", s.hp === 85, JSON.stringify(s));
  await page.evaluate(() => { window.__game.DRV.st.nails = 0; });
  check("no nails: it does not fire", (await shoot()) === false);

  // ammo packs give nails to a driver carrier
  const n0 = 3; await page.evaluate(n => { window.__game.DRV.st.nails = n; }, n0);
  const gotPack = await page.evaluate(() => { const g = window.__game, p = g.LT.vis && g.LT.vis.packs[0]; if (!p) return false; g.P.p.set(p.home[0], g.S.floor + 0.02, p.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack gives 8 nails", gotPack && s.nails === n0 + 8, JSON.stringify({gotPack, s}));

  // the locker: a row for it, leave and take
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  check("the locker panel lists six pieces of gear", (await page.evaluate(() => document.querySelectorAll("#station button[data-gear]").length)) === 6);
  await page.click('#station button[data-gear="driver"]'); s = await st();
  check("clicking the driver leaves it in the locker", !s.owned.includes("driver") && s.stash.includes("driver") && s.held !== "driver", JSON.stringify(s));
  await page.click('#station button[data-gear="driver"]'); s = await st();
  check("clicking again takes it back", s.owned.includes("driver"), JSON.stringify(s));
  await page.keyboard.press("Escape");

  // death: the nails are gone, the gun comes back from the locker for free
  await page.evaluate(() => { const g = window.__game; g.DRV.st.nails = 20; g.die(); }); await frames(100);
  s = await st(); check("after a death you carry no driver and no nails", !s.owned.includes("driver") && s.nails === 0 && s.stash.includes("driver"), JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); });
  await page.click('#station button[data-gear="driver"]'); await page.keyboard.press("Escape"); s = await st();
  check("the locker returns the driver for free, and no nails", s.owned.includes("driver") && s.nails === 0, JSON.stringify(s));

  // the Original again: none of it
  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no driver", await page.evaluate(() => !window.__game.owned().includes("driver") && window.__game.GB.load === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
