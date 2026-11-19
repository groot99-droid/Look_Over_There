// Going back in: the almond water rocket launcher (docs/ITEMS.md 4.5, solo). Checks that it waits in the locker (two weapons at most) with one rocket, that a rocket is a slow projectile that bursts on the first monster it meets
// (150 within 2 m, falling to 50 at 5 m, a kill counting toward the wave), leaves a 6 s mist that slows what stands in it, is heard 40 m away, is a dud inside 5 m of flight, hurts you inside 5 m of the burst, reloads for 3.5 s,
// gets no rockets from an ammo pack, stops you running while you hold it, and the death rule. The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/rocket_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, r = g.ROCKET.st, m = g.monsters; return {owned: g.owned(), held: g.HELD.item, rockets: r.rockets, cool: +r.cool.toFixed(2), flights: g.ROCKET.flights.length, mists: g.ROCKET.mists.length, mons: m.length, kills: g.GB.wave && g.GB.wave.kills, stash: g.GB.load && g.GB.load.stash, hp: g.HP.h.hp}; });
// stand somewhere open facing a clear line of `clear` m (at eye and at body height); monster 0 is d0 m ahead, monster 1 d1 m ahead, monster 2 `back` m behind you; their speeds are zero
const stage = ({d0, d1, back = 900, clear = 16}) => page.evaluate(({d0, d1, back, clear}) => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 20000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a);
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, clear + 0.5) || !g.rayClear([x, g.S.floor + 1.0, z], d, clear + 0.5) || g.collide({x: x + fx * d0, y: g.S.floor + 0.02, z: z + fz * d0}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    g.monsters.forEach((m, i) => { m.cfg = {...m.cfg, patrol: 0, alert: 0, chase: 0}; m.state = "patrol"; m.stunT = 0; m.slowT = 0; m.hp = m.cfg.hp; const k = i === 0 ? d0 : i === 1 ? d1 : null; if (k !== null && k !== undefined) m.pos.set(x + fx * k, m.fy, z + fz * k); else if (back < 800) m.pos.set(x - fx * back, m.fy, z - fz * back); else m.pos.set(x + 900, m.fy, z + 900); });
    return true;
  }
  return false;
}, {d0, d1, back, clear});
const fire = () => page.evaluate(() => { const g = window.__game; g.ROCKET.st.cool = 0; return g.fireRocket(); });
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no rocket launcher", await page.evaluate(() => !window.__game.owned().includes("rocket") && window.__game.GB.load === null));
  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("the launcher waits in the locker with one rocket", !s.owned.includes("rocket") && s.stash.includes("rocket") && s.rockets === 1, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  check("the locker lists nine pieces of gear", (await page.evaluate(() => document.querySelectorAll("#station button[data-gear]").length)) === 9);
  await page.click('#station button[data-gear="driver"]'); await page.click('#station button[data-gear="rocket"]'); await page.keyboard.press("Escape"); s = await st();
  check("leave the driver and the launcher can be taken", s.owned.includes("rocket") && !s.owned.includes("driver"), JSON.stringify(s));
  await page.keyboard.press("Digit5"); s = await st(); check("key 5 holds it", s.held === "rocket", JSON.stringify(s));
  // too heavy to run with
  const run = item => page.evaluate(item => { const g = window.__game; g.setHeld(item); g.keys.KeyW = true; g.keys.KeyR = true; g.sim(0.05, 0); g.sim(0.05, 0); const r = g.P.running; g.keys.KeyW = false; g.keys.KeyR = false; return r; }, item);
  check("you can run with the ray gun but not with the launcher in your hands", (await run("gun")) === true && (await run("rocket")) === false);

  // a rocket at a monster 12 m ahead; a second 2.3 m beyond it (inside the mist, just outside the full blast); a third 25 m behind
  check("monsters 12 m and 14.3 m ahead, one 25 m behind", await stage({d0: 12, d1: 14.3, back: 25}));
  await page.evaluate(() => { const g = window.__game; g.setHeld("rocket"); g.monsters[1].hp = 400; });
  check("the rocket fires", await fire()); s = await st();
  check("it is in the air at first, the rocket is used and the reload starts", s.flights === 1 && s.rockets === 0 && s.cool > 3 && s.mons === 3, JSON.stringify(s));
  check("a second shot does nothing (reloading, and no rockets)", (await page.evaluate(() => window.__game.fireRocket())) === false);
  await frames(16); s = await st();                                                            // 0.8 s: 12 m at 25 m/s takes about 0.5 s (the speed itself is a unit test: the page's own frames also tick in the gaps)
  check("it burst on the first monster: dead, and the wave counts it", s.flights === 0 && s.mons === 2 && s.kills === 1, JSON.stringify(s));
  const after = await page.evaluate(() => { const g = window.__game, m = g.monsters; return {hp1: m[0].hp, mul1: m[0].slowMul(), state1: m[0].state, state2: m[1].state}; });
  check("the one 2.3 m from the burst took about 140 (150 falling to 50 over 2 to 5 m) and is slowed to half by the mist", after.hp1 > 400 - 150 && after.hp1 < 400 - 130 && after.mul1 === 0.5, JSON.stringify(after));
  check("the bang called the one 25 m behind (37 m from the burst, inside 40 m)", after.state2 === "search" && after.state1 === "search", JSON.stringify(after));
  s = await st(); check("there is a mist", s.mists === 1, JSON.stringify(s));
  await frames(130); s = await st(); const gone = await page.evaluate(() => ({mul: window.__game.monsters[0].slowMul(), mists: window.__game.ROCKET.mists.length}));
  check("after 6 s the mist is gone and the monster is quick again", gone.mists === 0 && gone.mul === 1, JSON.stringify(gone));

  // a dud inside 5 m
  await page.evaluate(() => { window.__game.ROCKET.st = {rockets: 2, cool: 0}; });
  check("a monster 3 m ahead", await stage({d0: 3, d1: 14.3}));
  const hpBefore = await page.evaluate(() => window.__game.monsters[0].hp);
  await fire(); await frames(6); s = await st(); const dud = await page.evaluate(() => ({hp: window.__game.monsters[0].hp}));
  check("a rocket that meets something 3 m away has not armed: it drops, no burst, no mist, no damage", s.flights === 0 && s.mists === 0 && dud.hp === hpBefore && s.mons === 2 && s.rockets === 1, JSON.stringify({s, dud, hpBefore}));

  // the blast hurts you too: fire at 12 m, then step up beside the target before it lands
  check("a monster 12 m ahead again", await stage({d0: 12, d1: 14.3}));
  await page.evaluate(() => { const g = window.__game; g.ROCKET.st = {rockets: 1, cool: 0}; g.P.imm = 0; g.fireRocket(); const fx = -Math.sin(g.P.yaw), fz = -Math.cos(g.P.yaw); g.P.p.set(g.P.p.x + fx * 9, g.P.p.y, g.P.p.z + fz * 9); });
  const hp0 = (await st()).hp; await frames(14); s = await st();
  check("standing 3 m from the burst costs you a hit (35)", hp0 - s.hp >= 34 && hp0 - s.hp <= 36, JSON.stringify({hp0, now: s.hp}));
  await page.evaluate(() => { window.__game.P.imm = 1e9; });

  // no rockets from a pack; the cap
  await page.evaluate(() => { window.__game.ROCKET.st = {rockets: 1, cool: 0}; });
  const gotPack = await page.evaluate(() => { const g = window.__game, p = g.LT.vis && g.LT.vis.packs[0]; if (!p) return false; g.P.p.set(p.home[0], g.S.floor + 0.02, p.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack gives no rockets", gotPack && s.rockets === 1, JSON.stringify({gotPack, s}));

  // death: the rockets are gone, the launcher comes back
  await page.evaluate(() => { window.__game.ROCKET.st = {rockets: 3, cool: 0}; window.__game.die(); }); await frames(100);
  s = await st(); check("after a death: no launcher and no rockets", !s.owned.includes("rocket") && s.rockets === 0 && s.stash.includes("rocket"), JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  await page.click('#station button[data-gear="rocket"]'); await page.keyboard.press("Escape"); s = await st();
  check("the locker returns the launcher for free, and no rockets", s.owned.includes("rocket") && s.rockets === 0, JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no launcher", await page.evaluate(() => !window.__game.owned().includes("rocket") && window.__game.GB.load === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
