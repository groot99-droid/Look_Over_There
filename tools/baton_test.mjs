// Going back in: the stun baton (docs/ITEMS.md 4.4, solo). Checks the two-weapon cap and the weapon slots (keys 4 and 5), the swing (25 damage and a 4 s stun on what it hits, one capacitor, a cooldown),
// that a whiff is free, that empty capacitors recharge one at a time, the discharge (all three: 15 damage and a 3 s stun within 4 m, a bang monsters within 15 m come to, then dead for 20 s),
// a kill counting toward the wave, and that a death loses nothing. The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/baton_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, b = g.BAT.st, m = g.monsters[0]; return {owned: g.owned(), held: g.HELD.item, caps: b.caps, cool: b.cool, dead: b.dead, mons: g.monsters.length, hp: m ? m.hp : null, stun: m ? m.stunT : null, kills: g.GB.wave && g.GB.wave.kills, shotT: g.P.shotT, carry: g.GB.load && g.GB.load.carry, stash: g.GB.load && g.GB.load.stash}; });
// stand somewhere open facing a clear line and put monster 0 `dist` m ahead of you; the other monsters are parked far away unless `others` says where (metres ahead)
const stage = (dist, others = []) => page.evaluate(([dist, others]) => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 6000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a), far = Math.max(dist, ...others, 2) + 0.5;
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, far) || g.collide({x: x + fx * dist, y: g.S.floor + 0.02, z: z + fz * dist}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    g.monsters.forEach((m, i) => { const k = i === 0 ? dist : others[i - 1]; m.state = "patrol"; m.stunT = 0; if (k === undefined) m.pos.set(x + 900, m.fy, z + 900); else m.pos.set(x + fx * k, m.fy, z + fz * k); });
    return true;
  }
  return false;
}, [dist, others]);
const swing = () => page.evaluate(() => { const g = window.__game; g.BAT.st.cool = 0; return g.swingBaton(); });
const press = k => page.keyboard.press(k);
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no stun baton", await page.evaluate(() => !window.__game.owned().includes("baton") && window.__game.GB.load === null));

  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("you start with two arsenal weapons (crossbow, driver) and the baton waits in the locker", s.owned.includes("crossbow") && s.owned.includes("driver") && !s.owned.includes("baton") && s.stash.includes("baton"), JSON.stringify(s));
  await press("Digit4"); s = await st(); check("key 4 holds the first weapon you carry (the crossbow)", s.held === "crossbow", JSON.stringify(s));
  await press("Digit5"); s = await st(); check("key 5 holds the second (the bolt driver)", s.held === "driver", JSON.stringify(s));

  // the locker: a third arsenal weapon is refused until you leave one
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  check("the locker lists nine pieces of gear", (await page.evaluate(() => document.querySelectorAll("#station button[data-gear]").length)) === 9);
  await page.click('#station button[data-gear="baton"]'); s = await st();
  check("taking the baton as a third weapon is refused", !s.owned.includes("baton") && s.stash.includes("baton"), JSON.stringify(s));
  await page.click('#station button[data-gear="crossbow"]'); await page.click('#station button[data-gear="baton"]'); s = await st();
  check("leave the crossbow and the baton can be taken", s.owned.includes("baton") && !s.owned.includes("crossbow"), JSON.stringify(s));
  await press("Escape");
  await press("Digit4"); s = await st(); check("the weapon slots follow the order you took them: key 4 is now the driver", s.held === "driver", JSON.stringify(s));
  await press("Digit5"); s = await st(); check("and key 5 is the baton", s.held === "baton", JSON.stringify(s));

  // the swing
  check("a monster 1.5 m ahead", await stage(1.5)); s = await st(); const hp0 = s.hp;
  check("swing 1 lands", await swing());
  s = await st();
  check("it hurts (25) and stuns (4 s) what it hits, and uses a capacitor", s.hp === hp0 - 25 && s.stun > 3.5 && s.stun <= 4 && s.caps === 2 && s.mons === 3, JSON.stringify(s));
  check("a hit is a puff of noise", s.shotT > 0 && s.shotT <= 0.25, JSON.stringify(s));
  check("it is cooling: a second swing at once does nothing", (await page.evaluate(() => window.__game.swingBaton())) === false);
  await swing(); await swing(); s = await st();
  check("three hits (75 of the creature's 100) use all three capacitors", s.hp === hp0 - 75 && s.caps === 0 && s.kills === 0, JSON.stringify(s));
  check("no capacitors: it cannot swing", (await swing()) === false);
  await frames(8 * 20 + 2);                                            // 8 s (frames are 0.05 s) and a little over
  s = await st(); check("a capacitor recharges after 8 s", s.caps === 1, JSON.stringify(s));
  check("a whiff (nothing in reach) is free", await stage(5) && (await swing()) && (await st()).caps === 1);
  await stage(1.5); await page.evaluate(() => { window.__game.monsters[0].hp = 20; });
  check("a swing that finishes a monster kills it, and the wave counts it", (await swing()) && (await st()).kills === 1 && (await st()).mons === 2);

  // the discharge
  await page.evaluate(() => { window.__game.BAT.st = {caps: 2, charge: 0, cool: 0, dead: 0}; });
  check("the discharge needs all three capacitors", (await page.evaluate(() => window.__game.dischargeBaton())) === false);
  await page.evaluate(() => { window.__game.BAT.st = {caps: 3, charge: 0, cool: 0, dead: 0}; });
  check("a monster 3 m away, another 12 m away, none close behind", await stage(3, [12]));
  const before = await page.evaluate(() => window.__game.monsters.map(m => m.hp));
  check("the discharge fires", await page.evaluate(() => window.__game.dischargeBaton()));
  const after = await page.evaluate(() => window.__game.monsters.map(m => ({hp: m.hp, stun: m.stunT, state: m.state})));
  check("it hurts (15) and stuns (3 s) the monster within 4 m, not the one 12 m away", after[0].hp === before[0] - 15 && after[0].stun > 2.5 && after[1].hp === before[1] && after[1].stun === 0, JSON.stringify({before, after}));
  check("the bang sends the one 12 m away to look (it is within 15 m)", after[1].state === "search", JSON.stringify(after));
  s = await st(); check("the baton is empty and dead for 20 s", s.caps === 0 && s.dead > 19 && s.dead <= 20, JSON.stringify(s));
  check("a dead baton does not swing", (await swing()) === false);
  await frames(20 * 20); s = await st(); check("after 20 s it wakes, still empty", s.dead === 0 && s.caps === 0, JSON.stringify(s));
  await frames(8 * 20 + 2); s = await st(); check("and charges again, one capacitor per 8 s", s.caps === 1, JSON.stringify(s));

  // death loses nothing: the baton is in the locker and comes back free
  await page.evaluate(() => { window.__game.BAT.st = {caps: 2, charge: 0, cool: 0, dead: 0}; window.__game.die(); }); await frames(100);
  s = await st(); check("after a death the baton is in the locker and its charge is as it was", !s.owned.includes("baton") && s.stash.includes("baton") && s.caps === 2, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); });
  await page.click('#station button[data-gear="baton"]'); await page.click('#station button[data-gear="driver"]'); await page.click('#station button[data-gear="crossbow"]'); await press("Escape"); s = await st();
  check("the locker gives the baton back free, and refuses the third weapon again", s.owned.includes("baton") && s.owned.includes("driver") && !s.owned.includes("crossbow"), JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no baton", await page.evaluate(() => !window.__game.owned().includes("baton") && window.__game.GB.load === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
