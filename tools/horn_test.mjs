// Going back in: the sound-amplified frequency horn (docs/ITEMS.md 4.8, solo). Checks that it waits in the locker (two weapons at most), the blast (a 10 m cone: every monster in it is thrown 6 m straight back and stunned 2 s, nothing
// is hurt, the clawed go half as far, the whole floor within 40 m comes to look), the call (free, 25 m, its own cooldown), the battery (6 blasts, a free recharge at the locker, flat means no blast but the call still works),
// and the death rule (battery flat, the weapon back from the locker, and the next locker fills it). The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/horn_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, h = g.HORN.st; return {owned: g.owned(), held: g.HELD.item, charge: h.charge, coolB: +h.coolB.toFixed(2), coolC: +h.coolC.toFixed(2), swapT: h.swapT, stash: g.GB.load && g.GB.load.stash}; });
// the monsters' positions as distances ahead of the player along his facing, their stun, their health and state
const ahead = () => page.evaluate(() => { const g = window.__game, fx = -Math.sin(g.P.yaw), fz = -Math.cos(g.P.yaw); return g.monsters.map(m => ({d: +((m.pos.x - g.P.p.x) * fx + (m.pos.z - g.P.p.z) * fz).toFixed(2), side: +((m.pos.x - g.P.p.x) * fz - (m.pos.z - g.P.p.z) * fx).toFixed(2), stun: +m.stunT.toFixed(2), hp: m.hp, cap: m.cfg.hp, state: m.state})); });
// stand somewhere open facing a clear line `clear` m long; monster 0 is `dist` m ahead, monster 1 `d1` m ahead; the third is put `back` m behind you (or far away). Their speeds are zero so they stay where they are put.
const stage = ({dist, d1, back = 900, clear = 12}) => page.evaluate(({dist, d1, back, clear}) => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 12000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a);
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, clear + 0.5) || !g.rayClear([x, g.S.floor + 1.0, z], d, clear + 0.5) || g.collide({x: x + fx * dist, y: g.S.floor + 0.02, z: z + fz * dist}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    g.monsters.forEach((m, i) => { m.cfg = {...m.cfg, patrol: 0, alert: 0, chase: 0}; m.state = "patrol"; m.stunT = 0; m.hp = m.cfg.hp; const k = i === 0 ? dist : i === 1 ? d1 : null; if (k !== undefined && k !== null) m.pos.set(x + fx * k, m.fy, z + fz * k); else if (back < 800) m.pos.set(x - fx * back, m.fy, z - fz * back); else m.pos.set(x + 900, m.fy, z + 900); });
    return true;
  }
  return false;
}, {dist, d1, back, clear});
const fresh = () => page.evaluate(() => { const h = window.__game.HORN.st; window.__game.HORN.st = {...h, coolB: 0, coolC: 0}; });
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no horn", await page.evaluate(() => !window.__game.owned().includes("horn") && window.__game.GB.load === null));
  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("the horn waits in the locker with a full battery", !s.owned.includes("horn") && s.stash.includes("horn") && s.charge === 6, JSON.stringify(s));
  await page.evaluate(() => { window.__game.HORN.st = {...window.__game.HORN.st, charge: 2}; });
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  s = await st(); check("opening the locker recharges the battery for free", s.charge === 6, JSON.stringify(s));
  await page.click('#station button[data-gear="driver"]'); await page.click('#station button[data-gear="horn"]'); await page.keyboard.press("Escape"); s = await st();
  check("leave the driver and the horn can be taken", s.owned.includes("horn") && !s.owned.includes("driver"), JSON.stringify(s));
  await page.keyboard.press("Digit5"); s = await st(); check("key 5 holds it", s.held === "horn", JSON.stringify(s));

  // the blast: monsters 4 m and 7 m ahead (both in the cone), a third 30 m behind, the cone clear for 12 m
  check("monsters 4 m and 7 m ahead and one 30 m behind", await stage({dist: 4, d1: 7, back: 30}));
  let before = await ahead();
  check("the blast fires", await page.evaluate(() => window.__game.blowHorn()));
  let after = await ahead(); s = await st();
  check("each monster in the cone is thrown 6 m straight back (4 to 10 m, 7 to 13 m) and is no more than a hair off the line", Math.abs(after[0].d - 10) < 0.4 && Math.abs(after[1].d - 13) < 0.4 && Math.abs(after[0].side) < 0.3 && Math.abs(after[1].side) < 0.3, JSON.stringify({before, after}));
  check("and stunned for 2 s, and not hurt", after[0].stun > 1.5 && after[0].stun <= 2 && after[1].stun > 1.5 && after[0].hp === after[0].cap && after[1].hp === after[1].cap, JSON.stringify(after));
  check("it used a charge and the 4 s cooldown started", s.charge === 5 && s.coolB > 3.5 && s.coolB <= 4, JSON.stringify(s));
  check("the one 30 m behind heard it (within 40 m) and goes to look", after[2].state === "search" && after[2].stun === 0, JSON.stringify(after));
  check("a second blast at once does nothing", (await page.evaluate(() => window.__game.blowHorn())) === false && (await st()).charge === 5);

  // the clawed grip the floor: half as far
  await stage({dist: 4, d1: 7}); await fresh();
  await page.evaluate(() => { const m = window.__game.monsters[0]; m.cfg = {...m.cfg, knockback: 0.5}; });
  await page.evaluate(() => window.__game.blowHorn()); after = await ahead();
  check("a monster with knockback 0.5 (the clawed) goes 3 m, not 6", Math.abs(after[0].d - 7) < 0.4 && Math.abs(after[1].d - 13) < 0.4, JSON.stringify(after));

  // out of the cone: a monster beside you is not thrown (but still hears it)
  await stage({dist: 4, d1: 7}); await fresh();
  await page.evaluate(() => { const g = window.__game, m = g.monsters[1], fx = -Math.sin(g.P.yaw), fz = -Math.cos(g.P.yaw); m.pos.set(g.P.p.x + fz * 5, m.fy, g.P.p.z - fx * 5); });
  const side0 = await ahead(); await page.evaluate(() => window.__game.blowHorn()); after = await ahead();
  check("a monster 5 m to your side is outside the 60 degree cone: not thrown, not stunned, but it heard", after[1].d === side0[1].d && after[1].side === side0[1].side && after[1].stun === 0 && after[1].state === "search", JSON.stringify({side0, after}));

  // the call: free, 25 m, its own cooldown
  await stage({dist: 4, d1: 7, back: 20}); await fresh();
  await page.evaluate(() => { const g = window.__game, m = g.monsters[1], fx = -Math.sin(g.P.yaw), fz = -Math.cos(g.P.yaw); m.pos.set(g.P.p.x - fx * 30, m.fy, g.P.p.z - fz * 30); });
  const c0 = (await st()).charge; check("the call", await page.evaluate(() => window.__game.callHorn()));
  after = await ahead(); s = await st();
  check("it costs no charge; a monster 20 m away comes to look, one 30 m away does not, and none is stunned or moved", s.charge === c0 && after[2].state === "search" && after[1].state === "patrol" && after[0].stun === 0 && after[0].d === 4, JSON.stringify({s, after}));
  check("the call has its own 4 s cooldown, and a second call at once does nothing", s.coolC > 3.5 && (await page.evaluate(() => window.__game.callHorn())) === false);
  await fresh(); await page.evaluate(() => { window.__game.HORN.st = {...window.__game.HORN.st, coolB: 0}; });
  check("a call does not stop a blast", await page.evaluate(() => window.__game.blowHorn()));

  // a flat battery: no blast, the call still works
  await page.evaluate(() => { window.__game.HORN.st = {...window.__game.HORN.st, charge: 0, coolB: 0, coolC: 0}; });
  check("a flat battery does not blast", (await page.evaluate(() => window.__game.blowHorn())) === false);
  check("but the call still works", await page.evaluate(() => window.__game.callHorn()));
  await frames(100); check("and a flat battery stays flat with no spare (nothing recharges it but a locker)", (await st()).charge === 0);

  // death: the battery is flat, the weapon comes back, and the next locker fills it
  await page.evaluate(() => window.__game.die()); await frames(100);
  s = await st(); check("after a death: no horn and a flat battery", !s.owned.includes("horn") && s.charge === 0 && s.stash.includes("horn"), JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  await page.click('#station button[data-gear="horn"]'); await page.keyboard.press("Escape"); s = await st();
  check("the locker returns it for free and fills the battery", s.owned.includes("horn") && s.charge === 6, JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no horn", await page.evaluate(() => !window.__game.owned().includes("horn") && window.__game.GB.load === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
