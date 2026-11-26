// Going back in: the moth jelly dart (docs/ITEMS.md 4.9, solo). Checks the weapon slot swap (the dart waits in the locker), its own ammo (3 darts, a reload, packs), that a dart is a slow projectile that jellies what it hits
// (15 damage a second, slowed to half, 10 s), that a second dart restarts the time and does not add to the damage, that a jellied monster shows on the map, that a kill counts toward the wave, that a dying jellied monster
// infects the ones within 4 m, and the death rule (darts gone, the weapon back from the locker). The Original has none of it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/dart_test.mjs
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
const st = () => page.evaluate(() => { const g = window.__game, m = g.monsters[0]; return {owned: g.owned(), held: g.HELD.item, darts: g.DART.st.darts, cool: g.DART.st.cool, flights: g.DART.flights.length, mons: g.monsters.length, hp: m ? m.hp : null, jellyT: m ? m.jellyT : null, dps: m ? m.jellyDps : null, mul: m ? m.slowMul() : null, kills: g.GB.wave && g.GB.wave.kills, stash: g.GB.load && g.GB.load.stash}; });
// stand somewhere open facing a clear line; monster 0 is `dist` m ahead (frozen: stunned for ever), the others at the metres in `others` ahead, or parked far away
const stage = (dist, others = []) => page.evaluate(([dist, others]) => {
  const g = window.__game, cells = g.mainRegion().map(g.cellXZ);
  for (let t = 0; t < 8000; t++) {
    const [x, z] = cells[Math.floor(Math.random() * cells.length)], a = Math.random() * 6.28, fx = -Math.sin(a), fz = -Math.cos(a), far = Math.max(dist, ...others, 2) + 0.5;
    const o = [x, g.S.floor + g.P.eye, z], d = [fx, 0, fz];
    if (!g.rayClear(o, d, far) || g.collide({x: x + fx * dist, y: g.S.floor + 0.02, z: z + fz * dist}) || g.collide({x, y: g.S.floor + 0.02, z})) continue;
    g.P.p.set(x, g.S.floor + 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = a; g.P.pitch = 0; g.P.imm = 1e9;
    g.monsters.forEach((m, i) => { const k = i === 0 ? dist : others[i - 1]; m.state = "patrol"; m.stunT = 1e9; m.jellyT = 0; m.slowT = 0; m.hp = m.cfg.hp; if (k === undefined) m.pos.set(x + 900, m.fy, z + 900); else m.pos.set(x + fx * k, m.fy, z + fz * k); });
    return true;
  }
  return false;
}, [dist, others]);
const fire = () => page.evaluate(() => { const g = window.__game; g.DART.st.cool = 0; return g.fireDart(); });
try {
  await page.addInitScript(() => { try { localStorage.setItem("original_complete", "1"); } catch (e) {} });
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the Original has no moth jelly dart", await page.evaluate(() => !window.__game.owned().includes("dart") && window.__game.GB.load === null));
  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);
  await page.evaluate(() => { window.__game.P.imm = 1e9; });
  let s = await st();
  check("the dart starts in the locker with the baton (two weapons at most are carried)", !s.owned.includes("dart") && s.stash.includes("dart") && s.darts === 3, JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); }); await frames(2);
  await page.click('#station button[data-gear="driver"]'); await page.click('#station button[data-gear="dart"]'); await page.keyboard.press("Escape"); s = await st();
  check("leave the driver and the dart can be taken", s.owned.includes("dart") && !s.owned.includes("driver"), JSON.stringify(s));
  await page.keyboard.press("Digit5"); s = await st(); check("key 5 holds it (the second weapon you carry)", s.held === "dart", JSON.stringify(s));

  // a dart is a slow projectile: it is in the air, then it hits
  check("a monster 10 m ahead", await stage(10)); s = await st(); const hp0 = s.hp;
  check("the dart fires", await fire()); s = await st();
  check("it is in the air at first, and a dart is used", s.flights === 1 && s.darts === 2 && s.hp === hp0 && s.jellyT === 0, JSON.stringify(s));
  const again = await page.evaluate(() => window.__game.fireDart()); s = await st();
  check("it is reloading: a second shot at once does nothing", again === false && s.darts === 2 && s.cool > 0, JSON.stringify(s));
  await frames(8); s = await st();
  check("it reaches the monster: jellied for 10 s, slowed to half, the dart gone", s.flights === 0 && s.jellyT > 8.5 && s.jellyT <= 10 && s.mul === 0.5 && s.dps === 15, JSON.stringify(s));
  const onMap = await page.evaluate(() => { const g = window.__game; g.MAPSEEN.clear(); g.updateSeen(0); return g.MAPSEEN.has(g.monsters[0]); });
  check("a jellied monster is on the map while it lasts", onMap);
  await frames(40); s = await st();   // 2 s more
  check("it burns 15 a second", Math.abs(s.hp - (hp0 - 15 * (10 - s.jellyT))) < 1.1 && s.hp < hp0 - 20, JSON.stringify({s, hp0}));
  // a second dart restarts the time and does not add damage
  await frames(30); const jt = (await st()).jellyT;
  check("a second dart on it", await fire()); await frames(10); s = await st();
  check("restarts the 10 s and does not add to the damage", s.jellyT > jt && s.jellyT > 8.5 && s.dps === 15, JSON.stringify({s, jt}));
  await frames(160);                                      // run it out: the creature (100) dies after about 6.7 s of jelly
  s = await st(); check("the jelly kills it and the wave counts the kill", s.mons === 2 && s.kills === 1, JSON.stringify(s));

  // an empty weapon, a pack
  await page.evaluate(() => { window.__game.DART.st.darts = 0; });
  check("no darts: it does not fire", (await fire()) === false);
  const gotPack = await page.evaluate(() => { const g = window.__game, p = g.LT.vis && g.LT.vis.packs[0]; if (!p) return false; g.P.p.set(p.home[0], g.S.floor + 0.02, p.home[1]); g.P.v.set(0, 0, 0); return g.tryLoot(); });
  s = await st(); check("an ammo pack gives 1 dart", gotPack && s.darts === 1, JSON.stringify(s));

  // the spread: a jellied monster that dies infects the ones within 4 m
  await page.evaluate(() => window.__game.startGoingBackIn()); await settled(start);            // a fresh chamber: three monsters again
  await page.evaluate(() => { const g = window.__game; g.P.imm = 1e9; g.setHeld(g.owned().includes("dart") ? "dart" : null); });
  check("two monsters 6 m and 7.5 m ahead, the third far away", await stage(6, [7.5]));
  await page.evaluate(() => { const g = window.__game; g.GB.load = {carry: ["gun", "cloak", "crossbow", "dart"], stash: ["driver", "baton", "flame", "horn", "rocket", "laser"]}; g.DART.st.darts = 3; g.monsters[0].hp = 6; });
  await fire(); await frames(14);   // arrives, 6 health: dead in under half a second of jelly
  await frames(12);
  const sp = await page.evaluate(() => { const g = window.__game; return {mons: g.monsters.length, first: g.monsters[0] && g.monsters[0].jellyT, far: g.monsters[1] && g.monsters[1].jellyT}; });
  check("it died, and the one 1.5 m from it is jellied for about 5 s (the far one is not)", sp.mons === 2 && sp.first > 3.5 && sp.first <= 5 && sp.far === 0, JSON.stringify(sp));

  // death: the darts are gone, the weapon comes back from the locker
  await page.evaluate(() => { const g = window.__game; g.DART.st.darts = 4; g.die(); }); await frames(100);
  s = await st(); check("after a death you carry no dart and no darts", !s.owned.includes("dart") && s.darts === 0 && s.stash.includes("dart"), JSON.stringify(s));
  await page.evaluate(() => { const g = window.__game, x = g.STN.spot; g.P.p.set(x[0], g.S.floor + 0.02, x[1] + 1.0); g.P.v.set(0, 0, 0); g.doAction(); });
  await page.click('#station button[data-gear="dart"]'); await page.keyboard.press("Escape"); s = await st();
  check("the locker returns the weapon for free, and no darts", s.owned.includes("dart") && s.darts === 0, JSON.stringify(s));

  await page.evaluate(() => window.__game.loadScene("B1")); await settled("B1");
  check("back in the Original: no dart", await page.evaluate(() => !window.__game.owned().includes("dart") && window.__game.GB.load === null));
  check("no page errors", errors.length === 0, errors.slice(0, 2).join(" | "));
} catch (e) { console.log("FAIL test crashed: " + e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
