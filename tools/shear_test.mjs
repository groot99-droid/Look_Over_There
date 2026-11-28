// Going back in: the hydraulic rebar shear and its barricades (docs/ITEMS.md 4.7, solo). Checks that it waits in the locker (the eleventh row, click only), the spool (1 s) and the cut on release
// (a creature 1.5 m ahead dies and the wave counts it; let go early and nothing happens), a cut on air uses a cut, the worn spring (100 to a free monster, a kill on a stunned one, the 3 s reset
// by hand that a short hold does not do), a pack makes it fresh, the loud motor, the slower walk, the supply cage (shut to the action button, a cut opens it, its two packs), the chained door
// (refuses you and a monster, a cut frees it, a pack behind it), and the death rule. The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/shear_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, h = g.SHEAR.st, m = g.monsters[0]; return {owned: g.owned(), held: g.HELD.item, cuts: h.cuts, spares: h.spares, spool: +h.spool.toFixed(2), cool: +h.cool.toFixed(2), needReset: h.needReset, reset: +h.reset.toFixed(2), mons: g.monsters.length, hp: m ? +m.hp.toFixed(1) : null, kills: g.GB.wave && g.GB.wave.kills, shotT: +g.P.shotT.toFixed(2), stash: g.GB.load && g.GB.load.stash}; });
// stand with a clear line ahead; monster 0 is d0 m ahead, standing still; the others far away
const stage = (d0, clear = d0 + 1) => page.evaluate(([d0, clear]) => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 40000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a);
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, clear) || !g.rayClear([x, g.S.floor + 1.0, z], d, clear) || g.collide({x: x + fx * d0, y: g.S.floor + 0.02, z: z + fz * d0}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    if (g.BAR.st && g.BAR.st.cage && Math.hypot(g.BAR.st.cage.x - x, g.BAR.st.cage.z - z) < 4) continue;          // not next to the cage: the cut would bite it
    if (g.BAR.st && g.BAR.st.door && Math.hypot(g.BAR.st.door.cx - x, g.BAR.st.door.cz - z) < 4) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    g.monsters.forEach((m, i) => { m.cfg = {...m.cfg, patrol: 0, alert: 0, chase: 0, sight: 0, hearing: 0}; m.state = "patrol"; m.path = []; m.stunT = 0; m.hp = m.cfg.hp; m.slowT = m.jellyT = m.burnT = 0; if (i === 0) m.pos.set(x + fx * d0, m.fy, z + fz * d0); else m.pos.set(x + 900, m.fy, z + 900); });
    return true;
  }
  return false;
}, [d0, clear]);
// hold a button for n sim frames of 0.05 s in one go, then let go and run one more frame (the release is what cuts)
const holdFor = (which, n) => page.evaluate(([which, n]) => { const g = window.__game; g.HELD[which] = true; for (let i = 0; i < n; i++) g.sim(0.05, i); g.HELD[which] = false; g.sim(0.05, n); }, [which, n]);
const cut = () => holdFor("mouseFire", 22);                     // 1.1 s: spooled
const cooled = () => frames(32);                                // past the 1.5 s cooldown
const setShear = o => page.evaluate(o => { const g = window.__game; g.SHEAR.st = {...g.SHEAR.st, swapT: 0, cool: 0, spool: 0, ready: 0, needReset: false, reset: 0, ...o}; }, o);
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no shear and no barricades", await page.evaluate(() => !window.__game.owned().includes("shear") && window.__game.GB.load === null && window.__game.BAR.st === null));
  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("the shear waits in the locker with one fresh cartridge (four cuts) and no spare", !s.owned.includes("shear") && s.stash.includes("shear") && s.cuts === 4 && s.spares === 0, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  const rows = await page.evaluate(() => [...document.querySelectorAll("#station button[data-gear]")].map(b => b.textContent));
  check("the locker lists eleven pieces of gear; the eleventh (the shear) has no number key", rows.length === 11 && /Hydraulic rebar shear/.test(rows[10]) && !/^\s*1[01]/.test(rows[10]), JSON.stringify(rows.slice(9)));
  await page.click('#station button[data-gear="driver"]'); await page.click('#station button[data-gear="shear"]'); await page.keyboard.press("Escape"); s = await st();
  check("leave the driver, click the shear: it is carried", s.owned.includes("shear") && !s.owned.includes("driver"), JSON.stringify(s));
  await page.keyboard.press("Digit5"); s = await st(); check("key 5 holds it", s.held === "shear", JSON.stringify(s));

  // the cut
  check("a creature 1.5 m ahead", await stage(1.5)); await setShear({cuts: 4});
  await holdFor("mouseFire", 12); s = await st();
  check("let go after 0.6 s: not spooled, nothing happens and nothing is spent", s.mons === 3 && s.hp === 100 && s.cuts === 4 && s.cool === 0, JSON.stringify(s));
  check("the motor is loud while it spools", s.shotT > 0, JSON.stringify(s));
  await cut(); s = await st();
  check("held past 1 s and let go: the creature dies, the wave counts it, a cut is used, it cools", s.mons === 2 && s.kills === 1 && s.cuts === 3 && s.cool > 1, JSON.stringify(s));
  await cooled(); await stage(6, 7); await cut(); s = await st();
  check("a cut on air (nothing within 2 m) still uses a cut", s.cuts === 2 && s.hp === 100, JSON.stringify(s));
  await cooled(); await page.evaluate(() => { const g = window.__game; g.SHEAR.st = {...g.SHEAR.st, ready: 0, spool: 0}; });
  await holdFor("mouseFire", 22 + 62); s = await st();
  check("held ready past 3 s it winds down: the release then cuts nothing", s.cuts === 2 && s.cool === 0, JSON.stringify(s));

  // worn
  await stage(1.5); await setShear({cuts: 0}); await page.evaluate(() => { const m = window.__game.monsters[0]; m.cfg = {...m.cfg}; m.hp = 180; });
  await cut(); s = await st();
  check("worn: a monster moving freely takes 100, not a kill", s.hp === 80 && s.mons >= 1, JSON.stringify(s));
  check("and the jaw now needs a reset", s.needReset === true, JSON.stringify(s));
  await cooled(); await holdFor("mouseFire", 30); s = await st();
  check("it will not spool until it is reset", s.spool === 0 && s.hp === 80, JSON.stringify(s));
  await holdFor("mouseAlt", 40); s = await st();
  check("a 2 s hold of right click is not enough (and letting go starts over)", s.needReset === true && s.reset === 0, JSON.stringify(s));
  await holdFor("mouseAlt", 61); s = await st();
  check("3 s of right click resets the jaw", s.needReset === false, JSON.stringify(s));
  await page.evaluate(() => { const m = window.__game.monsters[0]; m.hp = 180; m.stun(3); });
  await cut(); s = await st();
  check("worn: a stunned monster still dies (helpless)", s.kills >= 2, JSON.stringify(s));

  // fluid
  await setShear({cuts: 0, needReset: true});
  const gotPack = await page.evaluate(() => { const g = window.__game, p = g.LT.vis && g.LT.vis.packs.find((p, i) => g.LT.st[g.S.id] ? g.LT.st[g.S.id].packs[i] === 0 : true); if (!p) return false; g.P.p.set(p.home[0], g.S.floor + 0.02, p.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack gives 2 cuts: the spring is fresh and owes no reset", gotPack && s.cuts === 2 && !s.needReset, JSON.stringify(s));

  // you walk at 0.8 with it in your hands
  await stage(1, 12);
  const walked = item => page.evaluate(item => { const g = window.__game; g.setHeld(item); g.P.v.set(0, 0, 0); const x0 = g.P.p.x, z0 = g.P.p.z; g.keys.KeyW = true; for (let i = 0; i < 20; i++) g.sim(0.05, i); g.keys.KeyW = false; return Math.hypot(g.P.p.x - x0, g.P.p.z - z0); }, item);
  await page.evaluate(() => window.__game.monsters.forEach(m => m.pos.set(m.pos.x + 900, m.fy, m.pos.z + 900)));
  const slow = await walked("shear"); await stage(1, 12); await page.evaluate(() => window.__game.monsters.forEach(m => m.pos.set(m.pos.x + 900, m.fy, m.pos.z + 900))); const quick = await walked("crossbow");
  check("you walk at 0.8 of the pace with it", Math.abs(slow / quick - 0.8) < 0.08, JSON.stringify({slow, quick}));
  await page.evaluate(() => window.__game.setHeld("shear"));

  // the supply cage
  const cage = await page.evaluate(() => { const g = window.__game, c = g.BAR.st && g.BAR.st.cage; return c && {x: c.x, z: c.z, open: c.open, packs: g.BAR.cage.packs.length}; });
  check("the chamber has a shut supply cage with two packs", cage && !cage.open && cage.packs === 2, JSON.stringify(cage));
  const atCage = () => page.evaluate(() => { const g = window.__game, c = g.BAR.st.cage, cells = g.mainRegion().map(g.cellXZ);
    const spot = cells.filter(([x, z]) => { const d = Math.hypot(x - c.x, z - c.z); return d > 1.0 && d < 1.3; })[0]; if (!spot) return false;
    g.P.p.set(spot[0], g.S.floor + 0.02, spot[1]); g.P.v.set(0, 0, 0); g.P.yaw = Math.atan2(-(c.x - spot[0]), -(c.z - spot[1])); g.P.pitch = 0; return true; });
  check("stand at the cage", await atCage());
  const roundsBefore = await page.evaluate(() => window.__game.LT.rounds);
  await page.evaluate(() => window.__game.doAction());
  check("the action button does not open it", await page.evaluate(() => !window.__game.BAR.st.cage.open) && (await page.evaluate(() => window.__game.LT.rounds)) === roundsBefore);
  await setShear({cuts: 0}); await atCage(); await cut(); s = await st();
  check("a worn shear's cut opens it (and owes a reset)", await page.evaluate(() => window.__game.BAR.st.cage.open) && s.needReset, JSON.stringify(s));
  await page.evaluate(() => { window.__game.LT.rounds = 0; }); await page.evaluate(() => window.__game.doAction()); await page.evaluate(() => window.__game.doAction());
  const taken = await page.evaluate(() => ({left: window.__game.BAR.cage.packs.filter(p => p.visible).length, rounds: window.__game.LT.rounds}));
  check("its two packs are taken one at a time", taken.left === 0 && taken.rounds > 0, JSON.stringify(taken));

  // the chained door: since #123 L3's stairwell door is its chamber's way on (never chained), so the first chamber of the run that gets a chained door
  let chained = null;
  for (const id of REGISTRY.chambers) {
    await page.evaluate(id => window.__game.loadScene(id), id); await settled(id); await page.evaluate(() => { window.__game.P.imm = 1e9; });
    chained = await page.evaluate(() => { const g = window.__game, d = g.BAR.st && g.BAR.st.door; if (!d || !g.BAR.behind.length) return null; window.__chainedDoor = d.d.name; return {name: d.d.name, chained: d.chained, box: d.box.chained, target: d.target, behind: g.BAR.behind.length, link: !!d.link}; });
    if (chained) { chained.scene = id; break; }
  }
  const door = chained;
  check("a chamber of the run has a chained door, with a pack behind it, and it is never a way on", door && door.chained && door.box && door.target === 0 && door.behind === 1 && !door.link, JSON.stringify(door));
  const atDoor = () => page.evaluate(() => { const g = window.__game, d = g.BAR.st.door || g.doors.find(x => x.d.name === window.__chainedDoor), nx = d.dir[1], nz = -d.dir[0];
    for (const k of [1.2, -1.2]) { const x = d.cx + nx * k, z = d.cz + nz * k, c = g.nearestWalk(g.S.nav, x, z); if (c >= 0 && g.mainRegion().includes(c)) { g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = Math.atan2(nx * Math.sign(k), nz * Math.sign(k)); g.P.pitch = 0; return true; } }
    return false; });
  check("stand at the door", await atDoor());
  await page.evaluate(() => window.__game.doAction()); await frames(2);
  check("the action button does not open it", await page.evaluate(() => window.__game.doors.find(x => x.d.name === window.__chainedDoor).target === 0));
  await page.evaluate(() => { const g = window.__game, d = g.doors.find(x => x.d.name === window.__chainedDoor); g.openDoor(d); });
  check("a monster cannot open it either", await page.evaluate(() => window.__game.doors.find(x => x.d.name === window.__chainedDoor).target === 0));
  await page.evaluate(() => window.__game.monsters.forEach(m => m.pos.set(m.pos.x + 900, m.fy, m.pos.z + 900)));
  await page.evaluate(() => window.__game.setHeld("shear")); await setShear({cuts: 2}); await atDoor(); await cut(); s = await st();
  const freed = await page.evaluate(() => { const g = window.__game, d = g.doors.find(x => x.d.name === window.__chainedDoor); return {chained: !!d.chained, box: !!d.box.chained, bar: g.BAR.st.door}; });
  check("a fresh cut frees it and uses a cut", !freed.chained && !freed.box && freed.bar === null && s.cuts === 1, JSON.stringify({freed, s}));
  await page.evaluate(() => window.__game.doAction()); await frames(2);
  check("now it opens", await page.evaluate(() => window.__game.doors.find(x => x.d.name === window.__chainedDoor).target === 1));
  const behind = await page.evaluate(() => { const g = window.__game, b = g.BAR.behind[0]; g.P.p.set(b.home[0], g.S.floor + 0.02, b.home[1]); g.P.v.set(0, 0, 0); g.LT.rounds = 0; g.tryBarricade(); return {taken: b.taken, rounds: g.LT.rounds}; });
  check("the pack behind it can be taken", behind.taken && behind.rounds > 0, JSON.stringify(behind));

  // death
  await page.evaluate(() => window.__game.die()); await frames(100);
  s = await st(); check("after a death: no shear, no cuts, no spare (you come back worn)", !s.owned.includes("shear") && s.cuts === 0 && s.spares === 0 && s.stash.includes("shear"), JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no shear and no barricades", await page.evaluate(() => !window.__game.owned().includes("shear") && window.__game.GB.load === null && window.__game.BAR.st === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close();
console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
