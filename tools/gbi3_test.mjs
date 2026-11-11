// Going back in, slice 3 (solo): the Q and E consumable slots. Q is the flash-vial (stuns, kills nothing); E is the land mine or the nail-bomb tripwire (chosen at the locker; both kill).
// Checks each item's own rule, ammo packs refilling them, the locker's E choice, and that a death takes them and the Original has none.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/gbi3_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game; return {n: g.GB.kit && {...g.GB.kit.n}, e: g.GB.kit && g.GB.kit.e, mons: g.monsters.length, kills: g.GB.wave && g.GB.wave.kills, cleared: g.GB.wave && g.GB.wave.cleared, traps: g.TRAPS.list.filter(t => !t.done).length, stun: g.monsters.map(m => m.stunT > 0), bolts: g.BOW.st.bolts, rounds: g.LT.rounds}; });
// stand somewhere open on a floor with a clear 6 m line ahead; returns the spot and the point 6 m ahead. All monsters are parked far away (the test moves them where it wants them).
const stand = () => page.evaluate(() => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 4000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a), qx = x + fx * 6, qz = z + fz * 6;
    if (!g.rayClear([x, g.S.floor + g.P.eye, z], [fx, 0, fz], 6.3) || g.collide({x: qx, y: g.S.floor + 0.02, z: qz}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;          // the wave is live: it must not catch the test player (a death is tested on purpose below)
    g.monsters.forEach((m, i) => { m.pos.x = x - fx * (30 + i * 2); m.pos.z = z - fz * (30 + i * 2); m.stunT = 99; });          // parked, and held still
    return {x, z, qx, qz, fx, fz};
  }
  return null;
});
// hold: keep it still (a long stun) so a live monster cannot walk off before the trap arms; the flash test needs it free, to measure the stun itself
const put = (i, x, z, hold = true) => page.evaluate(([i, x, z, hold]) => { const m = window.__game.monsters[i]; m.pos.x = x; m.pos.z = z; m.stunT = hold ? 99 : 0; }, [i, x, z, hold]);
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original: Q and E are empty and place nothing", await page.evaluate(() => { const g = window.__game; return g.GB.kit === null && g.useConsumable(0) === false && g.useConsumable(1) === false && g.TRAPS.list.length === 0; }));

  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  let s = await st();
  check("Going back in starts with 2 flash-vials, 2 mines and 1 tripwire, E holding the mine", s.n && s.n.flash === 2 && s.n.mine === 2 && s.n.wire === 1 && s.e === "mine", JSON.stringify(s));
  check("the ammo line shows the Q and E slots", await page.evaluate(() => { const t = document.getElementById("ammo").textContent; return /Q/.test(t) && /E/.test(t); }));

  // Q: the flash-vial stuns the monsters near where it lands, kills nothing, and costs one
  let p = await stand(); await put(0, p.qx + 1, p.qz, false); await put(1, p.qx - 30 * p.fx, p.qz - 30 * p.fz, false);
  check("Q throws a flash-vial", await page.evaluate(() => window.__game.useConsumable(0)));
  s = await st();
  check("it stunned the monster near the landing point, not the far one, and killed nothing", s.stun[0] === true && s.stun[1] === false /* 30 m away: out of the 6 m radius */ && s.mons === 3 && s.kills === 0 && s.n.flash === 1, JSON.stringify(s));
  const stun0 = await page.evaluate(() => window.__game.monsters[0].stunT);
  check("the stun lasts about 6 s", stun0 > 5 && stun0 <= 6.01, String(stun0));

  // E, a mine: armed after a delay, then it kills the monster that steps on it (and only that one)
  p = await stand(); await put(0, p.x + 0.5, p.z); await put(1, p.x + 0.9, p.z + 0.2);
  check("E sets down a land mine", await page.evaluate(() => window.__game.useConsumable(1)));
  await frames(5); s = await st();
  check("it is not armed yet: nothing dies in the first 0.25 s", s.mons === 3 && s.traps === 1 && s.n.mine === 1, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game; g.monsters[1].pos.x += 30; });                         // only monster 0 stays on it
  await frames(40); s = await st();
  check("then it kills the monster on it, is spent, and counts as a kill", s.mons === 2 && s.kills === 1 && s.traps === 0, JSON.stringify(s));

  // E at the locker: switch to the tripwire; it kills everything in its blast and is loud
  const spot = await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); return !!x; });
  await page.keyboard.press("4"); await page.keyboard.press("Escape");
  s = await st(); check("the locker's key 4 changes the E slot to the tripwire", spot && s.e === "wire", JSON.stringify(s));
  p = await stand(); await put(0, p.x + 1.5, p.z); await put(1, p.x, p.z + 2.8);
  const far = await page.evaluate(() => { const g = window.__game; return {x: g.P.p.x, z: g.P.p.z}; });
  check("E sets down a tripwire", await page.evaluate(() => window.__game.useConsumable(1)));
  await frames(2); s = await st(); check("it arms in under a second", s.traps === 1 && s.mons === 2, JSON.stringify(s));
  await frames(20); s = await st();
  check("the blast kills both monsters near it, and the wave is cleared", s.mons === 0 && s.kills === 3 && s.cleared === true && s.traps === 0, JSON.stringify(s));
  check("an empty E slot does nothing and places nothing", await page.evaluate(() => { const g = window.__game; g.GB.kit.n.wire = 0; return g.useConsumable(1) === false && g.TRAPS.list.filter(t => !t.done).length === 0; }));

  // an ammo pack refills the flash-vial and the E item
  const b = await st();
  const pk = await page.evaluate(() => { const g = window.__game, q = g.LT.vis && g.LT.vis.packs[0]; if (!q) return false; g.P.p.set(q.home[0], g.S.floor + 0.02, q.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack gives one flash-vial and one of the E item", pk && s.n.flash === b.n.flash + 1 && s.n.wire === b.n.wire + 1, JSON.stringify({b: b.n, s: s.n}));

  // death takes them; the locker gives the gear back but not these
  await page.evaluate(() => window.__game.die()); await frames(100);
  s = await st(); check("after a death every consumable is gone", s.n.flash === 0 && s.n.mine === 0 && s.n.wire === 0, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); });
  for (const gear of ["gun", "cloak", "crossbow"]) await page.click(`#station button[data-gear="${gear}"]`);
  await page.keyboard.press("Escape"); s = await st();
  check("the locker returns the gear, not the consumables", s.n.flash === 0 && s.n.mine === 0 && s.n.wire === 0 && s.bolts === 0 && s.rounds === 0, JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no kit, no traps", await page.evaluate(() => { const g = window.__game; return g.GB.kit === null && g.TRAPS.list.length === 0 && g.useConsumable(0) === false; }));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
