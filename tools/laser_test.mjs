// Going back in: the laser pointer dissector (docs/ITEMS.md 4.6, solo). Checks that it waits in the locker (two weapons at most), the beam (held: silent, reaches a monster 28 m away, its damage climbs on one target so a creature dies
// in about 2.4 s, a hurt monster comes for you, the battery drains 8% a second, it overheats after 5 s, you move at a crouch's pace), the dot (held: a patrolling monster near it goes to look, a chasing one does not, almost no battery),
// an ammo pack's 25%, the swap to the spare, the locker's E key for the E slot, and the death rule. The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/laser_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, l = g.LASER.st, m = g.monsters[0]; return {owned: g.owned(), held: g.HELD.item, charge: +l.charge.toFixed(3), spares: l.spares, swapT: l.swapT, lock: +l.lock.toFixed(2), heat: +l.heat.toFixed(2), mons: g.monsters.length, hp: m ? +m.hp.toFixed(1) : null, state: m ? m.state : null, kills: g.GB.wave && g.GB.wave.kills, shotT: g.P.shotT, stash: g.GB.load && g.GB.load.stash, e: g.GB.kit.e}; });
// stand somewhere with a clear line of `clear` m at eye and body height; monster 0 is d0 m ahead, standing still (speeds zero); the others far away.
// `walk`: the body itself (not only a ray) fits every 0.2 m for that far ahead, for a check that walks: a ray passes a shelf corner the body catches on
const stage = (d0, clear = d0 + 1, walk = 0) => page.evaluate(([d0, clear, walk]) => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 40000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a);
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, clear) || !g.rayClear([x, g.S.floor + 1.0, z], d, clear) || g.collide({x: x + fx * d0, y: g.S.floor + 0.02, z: z + fz * d0}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    let lane = true; for (let w = 0.2; w <= walk && lane; w += 0.2) lane = !g.collide({x: x + fx * w, y: g.S.floor + 0.02, z: z + fz * w}); if (!lane) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    g.monsters.forEach((m, i) => { m.cfg = {...m.cfg, patrol: 0, alert: 0, chase: 0, sight: 0}; m.state = "patrol"; m.path = []; m.stunT = 0; m.hp = m.cfg.hp; if (i === 0) m.pos.set(x + fx * d0, m.fy, z + fz * d0); else m.pos.set(x + 900, m.fy, z + 900); });
    return true;
  }
  return false;
}, [d0, clear, walk]);
// hold a button for n sim frames of 0.05 s in one go (the page's own frame loop would otherwise run in the gaps)
const holdFor = (which, n) => page.evaluate(([which, n]) => { const g = window.__game; g.HELD[which] = true; for (let i = 0; i < n; i++) g.sim(0.05, i); g.HELD[which] = false; }, [which, n]);
const fresh = () => page.evaluate(() => { const g = window.__game; g.LASER.st = {charge: 1, spares: 1, swapT: 0, heat: 0, lock: 0, target: null, onT: 0, offT: 0}; });
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no laser", await page.evaluate(() => !window.__game.owned().includes("laser") && window.__game.GB.load === null));
  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("the laser waits in the locker with a full pack and one spare", !s.owned.includes("laser") && s.stash.includes("laser") && s.charge === 1 && s.spares === 1, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  check("the locker lists eleven pieces of gear", (await page.evaluate(() => document.querySelectorAll("#station button[data-gear]").length)) === 11);
  await page.keyboard.press("e"); s = await st(); check("the locker's E key swaps the E slot (it stays open)", s.e === "wire" && await page.evaluate(() => window.__game.STN.open), JSON.stringify(s));
  await page.keyboard.press("e");
  await page.click('#station button[data-gear="driver"]'); await page.keyboard.press("0"); await page.keyboard.press("Escape"); s = await st();
  check("leave the driver, and key 0 (the tenth row) takes the laser", s.owned.includes("laser") && !s.owned.includes("driver"), JSON.stringify(s));
  await page.keyboard.press("Digit5"); s = await st(); check("key 5 holds it", s.held === "laser", JSON.stringify(s));

  // the beam at a creature 8 m away
  check("a creature 8 m ahead", await stage(8)); await fresh();
  await holdFor("mouseFire", 20); s = await st();      // 1 s
  check("one second of beam does about 26 (15 a second climbing), and the monster is not dead", Math.abs(100 - s.hp - 26.25) < 2 && s.mons === 3, JSON.stringify(s));
  check("it is silent, it drains 8% a second, and the monster comes for you", s.shotT === 0 && Math.abs(s.charge - 0.92) < 0.006 && s.state === "chase", JSON.stringify(s));
  await holdFor("mouseFire", 20); s = await st();      // 2 s in all
  check("two seconds in all is about 75: still alive", s.mons === 3 && Math.abs(100 - s.hp - 75) < 3, JSON.stringify(s));
  await holdFor("mouseFire", 12); s = await st();
  check("it dies at about 2.4 s, and the wave counts it", s.mons === 2 && s.kills === 1, JSON.stringify(s));

  // letting go for half a second starts the climb again
  await stage(8); await fresh(); await holdFor("mouseFire", 30); await frames(10); const hpA = (await st()).hp; await holdFor("mouseFire", 20); s = await st();
  check("after half a second off the trigger the climb starts again (about 26 in the next second, not 60)", Math.abs(hpA - s.hp - 26.25) < 2.5, JSON.stringify({hpA, s}));

  // range: a monster 28 m away is reached (the ray gun stops at 25)
  const far = await stage(28, 29);
  if (far) { await fresh(); await holdFor("mouseFire", 10); s = await st(); check("the beam reaches a monster 28 m away", s.hp < 100, JSON.stringify(s)); }
  else console.log("SKIP no clear 29 m line in this chamber (the 30 m range is a unit test)");

  // overheat
  await stage(8); await fresh(); await page.evaluate(() => { window.__game.monsters[0].hp = 1e6; });
  await holdFor("mouseFire", 104); s = await st();
  check("after 5 s of beam it overheats and locks", s.lock > 2 && s.lock <= 3, JSON.stringify(s));
  const hpLock = await page.evaluate(() => window.__game.monsters[0].hp); await holdFor("mouseFire", 10);
  check("an overheated laser does no damage", (await page.evaluate(() => window.__game.monsters[0].hp)) === hpLock);

  // you move at a crouch's pace while the beam is on
  await stage(8, 14, 6); await fresh();
  const walked = on => page.evaluate(on => { const g = window.__game; g.P.v.set(0, 0, 0); const x0 = g.P.p.x, z0 = g.P.p.z; g.keys.KeyW = true; g.HELD.mouseFire = on; for (let i = 0; i < 20; i++) g.sim(0.05, i); g.keys.KeyW = false; g.HELD.mouseFire = false; return Math.hypot(g.P.p.x - x0, g.P.p.z - z0); }, on);
  const slow = await walked(true); await stage(8, 14, 6); await page.evaluate(() => window.__game.setHeld("laser")); const quick = await walked(false);
  check("with the beam on you cover about 2.2 m in a second, against about 4 m without", slow > 1.6 && slow < 2.6 && quick > 3.2, JSON.stringify({slow, quick}));

  // the dot: a patrolling monster 5 m to the side of where you point goes to look; a chasing one does not
  await stage(8, 12); await fresh();
  await page.evaluate(() => { const g = window.__game, m = g.monsters[0], fx = -Math.sin(g.P.yaw), fz = -Math.cos(g.P.yaw); g.P.pitch = -0.2; m.pos.set(g.P.p.x + fx * 6 + fz * 3, m.fy, g.P.p.z + fz * 6 - fx * 3); m.state = "patrol"; });
  await holdFor("mouseAlt", 12); s = await st(); const dot = await page.evaluate(() => { const g = window.__game, m = g.monsters[0]; return {last: m.last, dotAt: g.LASER.dotAt, d: Math.hypot(m.pos.x - g.LASER.dotAt[0], m.pos.z - g.LASER.dotAt[2])}; });
  check("the dot sends a patrolling monster near it to look at it", s.state === "search" && dot.d < 12 && Math.abs(dot.last[0] - dot.dotAt[0]) < 0.01 && Math.abs(dot.last[1] - dot.dotAt[2]) < 0.01, JSON.stringify({s, dot}));
  check("the dot costs almost nothing (0.5% a second) and does no damage", s.charge > 0.995 && s.hp === 100, JSON.stringify(s));
  await page.evaluate(() => { const m = window.__game.monsters[0]; m.state = "chase"; m.last = [1, 1]; }); await holdFor("mouseAlt", 12);
  check("a chasing monster ignores the dot", await page.evaluate(() => { const m = window.__game.monsters[0]; return m.state === "chase" || (m.last[0] === 1 && m.last[1] === 1); }));

  // battery: a pack, the swap, flat
  await page.evaluate(() => { const g = window.__game; g.LASER.st = {...g.LASER.st, charge: 0.5, lock: 0, heat: 0}; });
  const gotPack = await page.evaluate(() => { const g = window.__game, p = g.LT.vis && g.LT.vis.packs[0]; if (!p) return false; g.P.p.set(p.home[0], g.S.floor + 0.02, p.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack adds 25% to the battery", gotPack && s.charge === 0.75, JSON.stringify(s));
  await stage(8); await page.evaluate(() => { const g = window.__game; g.LASER.st = {...g.LASER.st, charge: 0.02, spares: 1, lock: 0, heat: 0}; });
  await holdFor("mouseFire", 10); s = await st(); check("a flat pack starts swapping to the spare by itself", s.charge === 0 && s.swapT > 0, JSON.stringify(s));
  await frames(45); s = await st(); check("2 s later the spare is in: full, and none left", s.charge === 1 && s.spares === 0 && s.swapT === 0, JSON.stringify(s));

  // death
  await page.evaluate(() => window.__game.die()); await frames(100);
  s = await st(); check("after a death: no laser, a flat battery and no spare", !s.owned.includes("laser") && s.charge === 0 && s.spares === 0 && s.stash.includes("laser"), JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  await page.click('#station button[data-gear="laser"]'); await page.keyboard.press("Escape"); s = await st();
  check("the locker returns it for free, with no charge", s.owned.includes("laser") && s.charge === 0, JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no laser", await page.evaluate(() => !window.__game.owned().includes("laser") && window.__game.GB.load === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
