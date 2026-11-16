// Going back in: the propane flamethrower (docs/ITEMS.md 4.3, solo). Checks that it waits in the locker (two weapons at most), that holding the trigger burns a 6 m cone (40 damage a second and a burn: 10 a second, slowed to 0.6,
// for 4 s after the flame leaves), that a burst is a bang monsters within 15 m come to, that firing puts the cloak out and counts as running, fuel (10% a second, packs, the spare canister and its 2.5 s swap), a kill counting toward the
// wave, and the death rule (propane gone, the weapon back from the locker). The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/flame_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, f = g.FLAME.st, m = g.monsters[0], m1 = g.monsters[1]; return {owned: g.owned(), held: g.HELD.item, fuel: +f.fuel.toFixed(3), spare: +f.spare.toFixed(3), swapT: f.swapT, mons: g.monsters.length, hp: m ? +m.hp.toFixed(2) : null, hp1: m1 ? +m1.hp.toFixed(2) : null, burnT: m ? +m.burnT.toFixed(2) : null, mul: m ? m.slowMul() : null, state: m ? m.state : null, kills: g.GB.wave && g.GB.wave.kills, shotT: g.P.shotT, stash: g.GB.load && g.GB.load.stash}; });
// stand somewhere open facing a clear line; monster 0 is `dist` m ahead (frozen: stunned for ever), the others at the metres in `others` ahead, or parked far away
const stage = (dist, others = []) => page.evaluate(([dist, others]) => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 8000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a), far = Math.max(dist, ...others, 2) + 0.5;
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, far) || g.rayClear(o, d, 0.9) === false || g.collide({x: x + fx * dist, y: g.S.floor + 0.02, z: z + fz * dist}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    g.monsters.forEach((m, i) => { const k = i === 0 ? dist : others[i - 1]; m.state = "patrol"; m.stunT = 1e9; m.jellyT = 0; m.burnT = 0; m.slowT = 0; m.hp = m.cfg.hp; if (k === undefined) m.pos.set(x + 900, m.fy, z + 900); else m.pos.set(x + fx * k, m.fy, z + fz * k); });
    return true;
  }
  return false;
}, [dist, others]);
// hold the trigger for n sim frames of 0.05 s in one go (the page's own frame loop would otherwise burn in the gaps between calls)
const burnFor = n => page.evaluate(n => { const g = window.__game; g.HELD.mouseFire = true; for (let i = 0; i < n; i++) g.sim(0.05, i); g.HELD.mouseFire = false; }, n);
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no flamethrower", await page.evaluate(() => !window.__game.owned().includes("flame") && window.__game.GB.load === null));
  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("the flamethrower waits in the locker with a full tank", !s.owned.includes("flame") && s.stash.includes("flame") && s.fuel === 1 && s.spare === 0, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  await page.click('#station button[data-gear="driver"]'); await page.click('#station button[data-gear="flame"]'); await page.keyboard.press("Escape"); s = await st();
  check("leave the driver and the flamethrower can be taken", s.owned.includes("flame") && !s.owned.includes("driver"), JSON.stringify(s));
  await page.keyboard.press("Digit5"); s = await st(); check("key 5 holds it", s.held === "flame", JSON.stringify(s));

  // hold the trigger: two monsters in the cone (4 m and 5 m), the third far away
  check("two monsters 4 m and 5 m ahead, the third far away", await stage(4, [5]));
  await page.evaluate(() => { const g = window.__game; g.CL.have = true; g.CL.st = {...g.CL.st, on: true, b: 1}; });
  await burnFor(10); s = await st();        // 0.5 s of flame
  check("every monster in the cone takes 40 a second, and the burn ticks too: about 25 in half a second (20 and 5)", Math.abs(s.hp - 75) < 1.5 && Math.abs(s.hp1 - 75) < 1.5, JSON.stringify(s));
  check("and is burning: slowed to 0.6, about 4 s of it", s.burnT > 3.4 && s.burnT <= 4 && s.mul === 0.6, JSON.stringify(s));
  check("fuel burns at 10% a second", Math.abs(s.fuel - 0.95) < 0.011, JSON.stringify(s));
  check("the burst called the monster to look, and you count as running", s.state === "search" && s.shotT > 0, JSON.stringify(s));
  check("firing put the cloak out", await page.evaluate(() => !window.__game.CL.st.on));
  // the burn goes on after the flame leaves, for 4 s, 10 a second
  const hpA = (await st()).hp; await frames(100); s = await st();   // 5 s
  check("the burn keeps hurting for about 4 s after the flame stops (10 a second), then wears off", Math.abs((hpA - s.hp) - 40) < 6 && s.burnT === 0 && s.mul === 1, JSON.stringify({hpA, s}));
  // a kill
  await stage(3); await page.evaluate(() => { window.__game.FLAME.st = {...window.__game.FLAME.st, fuel: 1}; });
  await burnFor(50); s = await st();
  check("a creature in the flame for 2.5 s is dead, and the wave counts it", s.mons === 2 && s.kills === 1, JSON.stringify(s));
  check("that took about a quarter of a tank", s.fuel < 0.8 && s.fuel > 0.6, JSON.stringify(s));

  // empty, pack, spare, swap
  await page.evaluate(() => { const g = window.__game; g.FLAME.st = {...g.FLAME.st, fuel: 0, spare: 0}; });
  await stage(3); await burnFor(10); s = await st();
  check("an empty tank does not burn", s.hp === 100 && s.fuel === 0, JSON.stringify(s));
  check("with no spare there is nothing to swap to", (await page.evaluate(() => window.__game.swapCanister())) === false);
  const gotPack = await page.evaluate(() => { const g = window.__game, p = g.LT.vis && g.LT.vis.packs[0]; if (!p) return false; g.P.p.set(p.home[0], g.S.floor + 0.02, p.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack gives 25% to the tank", gotPack && s.fuel === 0.25, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game; g.FLAME.st = {...g.FLAME.st, fuel: 0.2, spare: 1}; });
  check("swap to the spare", await page.evaluate(() => window.__game.swapCanister()));
  await stage(3); await burnFor(10); s = await st();
  check("it cannot burn while swapping", s.hp === 100 && s.swapT > 0, JSON.stringify(s));
  await frames(50); s = await st();
  check("after 2.5 s the canisters have swapped", s.swapT === 0 && s.fuel === 1 && s.spare === 0.2, JSON.stringify(s));

  // death: the propane is gone, the weapon comes back from the locker
  await page.evaluate(() => window.__game.die()); await frames(100);
  s = await st(); check("after a death: no flamethrower, no propane", !s.owned.includes("flame") && s.fuel === 0 && s.spare === 0 && s.stash.includes("flame"), JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); });
  await page.click('#station button[data-gear="flame"]'); await page.keyboard.press("Escape"); s = await st();
  check("the locker returns it for free, and no propane", s.owned.includes("flame") && s.fuel === 0, JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no flamethrower", await page.evaluate(() => !window.__game.owned().includes("flame") && window.__game.GB.load === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
