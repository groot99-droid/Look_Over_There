// Going back in in a room (session 16): two real pages in one going_back_in room against server/server.js. Slice 1: the lobby's button, both land in the first chamber,
// the server's wave on both pages, presence, the stairs down to the next chamber, and the mode's death rule. Slice 2: the locker's loadout, the crossbow's bolts and kills
// (the server's), the cleared wave, and the locker after a death. Slice 3: the flash-vial, the land mine and the tripwire, counted and decided by the server and seen by both.
// Every wait is on what the page or the server holds (the server runs in this process), never a fixed sleep after a teleport: the server acts on the position it last heard.
// Usage: node tools/gbi_mp_test.mjs      (needs Playwright + Chromium and internet for three.js from unpkg)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import * as PS from "../server/playerstate.js";
import {REGISTRY} from "../shared/registry.js";
import {GUN_ROUNDS} from "../shared/loot.js";
import {START_BOLTS} from "../shared/crossbow.js";
import {GEAR} from "../shared/loadout.js";
import {START as KIT_START} from "../shared/consumables.js";
import {mainRegion, cellXZ, cellOf, segClear, rayClear, rng32} from "../shared/world.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; return !!ok; };
const MODE = "going_back_in", GBI = REGISTRY.modes[MODE], START = GBI.startChamber, first = REGISTRY.chamber(START), NEXT = first.next, next = REGISTRY.chamber(NEXT), CODE = "GBT", KEY = `${MODE}:${CODE}`;

let skew = 0;                                                             // the server's clock is the test's: a down time can be skipped without waiting for it
const srv = await createServer({port: 0, countdownMs: 400, clock: () => Date.now() / 1000 + skew});
const room = () => srv.rooms.get(KEY), floorOf = scene => room()?.floors[scene], playerOf = id => room()?.players.get(id);
const serverUntil = async (name, fn, why = () => "", ms = 30000) => { const end = Date.now() + ms; while (Date.now() < end) { if (fn()) return check(name, true); await sleep(100); } return check(name, false, why()); };
const until = (name, page, fn, arg, why = () => "") => page.waitForFunction(fn, arg, {timeout: 60000, polling: 200}).then(() => check(name, true), async () => check(name, false, await why()));
const view = page => page.evaluate(() => { const g = window.__game; return JSON.stringify({scene: g.S.id, loading: g.loading, dead: g.dead, at: g.P.p.toArray().map(v => +v.toFixed(1)), wave: g.GB.wave, mons: g.monsters.map(m => [m.wid, +m.pos.x.toFixed(1), +m.pos.z.toFixed(1)]), peers: [...g.net.peers.values()].map(p => [p.name, p.scene])}); }).catch(e => `(no page view: ${e.message})`);
const serverView = scene => { const f = floorOf(scene); return f ? `server ${scene}: wave ${JSON.stringify(f.wave)}, monsters ${JSON.stringify(f.monsters.map(m => [m.wid, +m.pos.x.toFixed(1), +m.pos.z.toFixed(1)]))}, players ${f.players().map(p => p.name)}` : `server has no floor ${scene}`; };
const both = async (page, scene) => `${await view(page)}; ${serverView(scene)}`;
// waits until the server has this page's player within 0.5 m of where the page has them, on `scene`
const serverHasMe = async (page, scene, ms = 30000) => { const end = Date.now() + ms; while (Date.now() < end) { const me = await page.evaluate(() => { const g = window.__game; return {id: g.net.id, x: g.P.p.x, z: g.P.p.z}; }), p = playerOf(me.id); if (p && p.scene === scene && p.st && Math.hypot(p.st.x - me.x, p.st.z - me.z) < 0.5) return true; await sleep(50); } return false; };
// monsters ignore the players unless a check lifts this. Kept up on a timer from the lobby on: the round's start gives everyone a new state, and one page can be in the
// chamber (and hunted) long before the other has finished loading.
let guarded = true; const guardT = setInterval(() => { if (guarded && room()) for (const p of room().players.values()) p.ps.immUntil = 1e15; }, 20);
// the server's monsters of a chamber stand still from now on, so a page that follows the server must come to rest on the same spots
const hold = scene => floorOf(scene).monsters.forEach(m => { m.cfg = {...m.cfg, patrol: 0, alert: 0, chase: 0}; m.state = "patrol"; m.path = []; m.target = null; m.last = null; m.wait = 1e9; });
// the page's monsters are the server's: the same ids in the same order, each within 0.5 m of where the server has it (call hold(scene) first: the page eases toward the snapshots)
async function sameMonsters(name, page, scene) {
  const end = Date.now() + 60000; let last = "";
  while (Date.now() < end) {
    const mine = await page.evaluate(() => window.__game.monsters.map(m => [m.wid, m.pos.x, m.pos.z])), theirs = floorOf(scene).monsters.map(m => [m.wid, m.pos.x, m.pos.z]);
    if (mine.length === theirs.length && mine.every((p, i) => p[0] === theirs[i][0] && Math.hypot(p[1] - theirs[i][1], p[2] - theirs[i][2]) < 0.5)) return check(name, true);
    last = JSON.stringify({mine, theirs}); await sleep(150);
  }
  return check(name, false, last);
}

// a spot of the chamber with a clear straight line of d metres to another walkable spot (as server/floors.test.js does)
function clearPair(W, d, seed = 4) {
  const cells = mainRegion(W), r = rng32(seed), inRegion = new Set(cells);
  for (let i = 0; i < 4000; i++) {
    const [x, z] = cellXZ(cells[Math.floor(r() * cells.length)]), a = r() * 6.28, x2 = x + Math.cos(a) * d, z2 = z + Math.sin(a) * d;
    if (!inRegion.has(cellOf(x2, z2))) continue;
    if ([0.25, 0.5, 0.75, 1].every(u => segClear(W, x, W.floor + 1.0, z, x + (x2 - x) * u, W.floor + 1.0, z + (z2 - z) * u, 0)) && segClear(W, x, W.floor + 1.5, z, x2, W.floor + 1.5, z2, 0) && rayClear(W, [x, W.floor + 1.52, z], [(x2 - x) / d, 0, (z2 - z) / d], d)) return [[x, z], [x2, z2]];
  }
  throw new Error("no clear pair");
}
// puts the page's player at (x, z) on the floor and waits until the page has them standing there and the server has heard it
async function stand(page, scene, x, z, label) {
  const free = await page.evaluate(([x, z]) => { const g = window.__game, y = g.S.floor + 0.02; if (g.collide({x, y, z})) return false; g.P.p.set(x, y, z); g.P.v.set(0, 0, 0); return true; }, [x, z]);
  if (!free) return check(`${label}: the spot is open floor`, false, `(${x.toFixed(2)}, ${z.toFixed(2)}) is inside a collider`);
  const onPage = await page.waitForFunction(([x, z]) => { const g = window.__game, p = g.P.p; return !g.loading && g.P.ground && Math.abs(p.y - g.S.floor) < 0.1 && Math.hypot(p.x - x, p.z - z) < 0.05; }, [x, z], {timeout: 60000, polling: 100}).then(() => true, () => false);
  return check(`${label}: the page and the server have the player standing there`, onPage && await serverHasMe(page, scene), `${await view(page)}; ${serverView(scene)}`);
}
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const newPage = async name => { const page = await (await browser.newContext({viewport: {width: 320, height: 200}})).newPage(); page.on("pageerror", e => { console.log(`[${name} pageerror]`, e.message); failed++; }); return page; };          // one window each: a background tab's animation is paused
const inGame = p => p.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
const settled = (p, id) => p.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
// through the stairs-down door as a player goes: stand at it, open it, wait for the leaf, step into the hallway behind it
async function takeStairs(page, doorName) {
  await page.evaluate(n => { const g = window.__game, dr = g.doors.find(d => d.d.name === n); g.P.p.set(dr.cx, g.S.floor + 0.02, dr.cz + 1.2); g.P.v.set(0, 0, 0); g.openDoor(dr, true); }, doorName);
  await page.waitForFunction(n => { const dr = window.__game.doors.find(d => d.d.name === n); return dr && dr.hallN && dr.p >= 0.6; }, doorName, {timeout: 60000, polling: 100});
  await page.evaluate(n => { const g = window.__game, dr = g.doors.find(d => d.d.name === n); g.P.p.set(dr.hallC[0] + dr.hallN[0] * 0.3, g.S.floor + 0.02, dr.hallC[1] + dr.hallN[1] * 0.3); g.P.v.set(0, 0, 0); }, doorName);
}
try {
  // ---- the lobby: Ann picks the mode with the button, Bob comes by a shared link
  const a = await newPage("Ann"), b = await newPage("Bob");
  await a.setViewportSize({width: 900, height: 700});                    // the lobby form needs the room; the game then runs small, like Bob's
  await a.goto(`http://localhost:${srv.port}/?name=Ann&char=0`); await a.waitForSelector("#l-mode button");
  const btn = await a.$eval(`#l-mode button[data-mode="${MODE}"]`, x => ({disabled: x.disabled, text: x.textContent}));
  check("the lobby's Going back in button can be picked", !btn.disabled && !/soon/i.test(btn.text), JSON.stringify(btn));
  await a.click(`#l-mode button[data-mode="${MODE}"]`); await a.fill("#l-room", CODE); await a.click("#l-join");
  await a.waitForFunction(() => getComputedStyle(document.getElementById("l-wait")).display === "flex", null, {timeout: 60000});
  await a.setViewportSize({width: 320, height: 200});
  check("joining makes a room under the party key going_back_in:CODE", !!room() && room().mode === MODE && srv.rooms.size === 1, [...srv.rooms.keys()].join(","));
  await b.goto(`http://localhost:${srv.port}/?room=${CODE}&name=Bob&char=3&mode=${MODE}&auto=1`);
  await b.waitForFunction(() => getComputedStyle(document.getElementById("l-wait")).display === "flex", null, {timeout: 60000});
  await serverUntil("both are in the one room's waiting room", () => room().players.size === 2 && srv.rooms.size === 1, () => [...srv.rooms.keys()].join(","));
  await a.click("#l-ready"); await b.click("#l-ready");
  await Promise.all([inGame(a), inGame(b)]); await Promise.all([settled(a, START), settled(b, START)]);

  // ---- the first chamber: one wave, the server's, on both pages
  await serverUntil("the server runs the first chamber and started its wave once", () => floorOf(START)?.wave && floorOf(START).monsters.length === first.wave.monsters && floorOf(START).wave.no === first.wave.no, () => serverView(START));
  const t0 = floorOf(START).wave.t0, homes = floorOf(START).monsters.map(m => [...m.home]); hold(START);
  for (const [n, p] of [["Ann", a], ["Bob", b]]) {
    await until(`${n} is in the first chamber with the wave the server started`, p, ([no, n]) => { const g = window.__game; return g.GB.mode === "going_back_in" && g.GB.wave && g.GB.wave.no === no && g.monsters.length === n; }, [first.wave.no, first.wave.monsters], () => both(p, START));
    await sameMonsters(`${n} sees the server's monsters`, p, START);
    check(`${n} starts with the ray and the cloak (the server's word)`, await p.evaluate(r => { const g = window.__game; return g.LT.gun && g.LT.rounds === r && g.CL.have; }, GUN_ROUNDS));
  }
  check("the wave was not started a second time by the second player", floorOf(START).wave.t0 === t0 && floorOf(START).monsters.length === first.wave.monsters, serverView(START));
  const spawn = await Promise.all([a, b].map(p => p.evaluate(() => { const g = window.__game; return {at: [g.P.p.x, g.P.p.z], free: !g.collide({x: g.P.p.x, y: g.S.floor + 0.05, z: g.P.p.z})}; })));
  check("the party starts the chamber together, on open floor", Math.hypot(spawn[0].at[0] - spawn[1].at[0], spawn[0].at[1] - spawn[1].at[1]) < 4 && spawn[0].free && spawn[1].free, JSON.stringify(spawn));
  const far = Math.min(...homes.flatMap(h => spawn.map(sp => Math.hypot(h[0] - sp.at[0], h[1] - sp.at[1]))));
  check("the wave started well away from where the party stands", far >= 14, String(far));
  await until("Ann sees Bob in the chamber", a, s => [...window.__game.net.peers.values()].some(p => p.name === "Bob" && p.scene === s && Math.hypot(p.tx - p.x, p.tz - p.z) < 1), START, () => view(a));
  await until("Bob sees Ann in the chamber", b, s => [...window.__game.net.peers.values()].some(p => p.name === "Ann" && p.scene === s), START, () => view(b));

  // ---- the stairs down: Ann goes first, Bob follows
  await takeStairs(a, first.stairsDown); await settled(a, NEXT);
  check("Ann lands in the next chamber, on its floor", await a.evaluate(y => { const g = window.__game; return Math.abs(g.S.floor - y) < 0.01 && Math.abs(g.P.p.y - y) < 0.6; }, next.floorY), await view(a));
  check("the server has Ann in the next chamber", await serverHasMe(a, NEXT), serverView(NEXT));
  await serverUntil("the next chamber's own wave started when she stepped in", () => floorOf(NEXT)?.wave?.no === next.wave.no && floorOf(NEXT).monsters.length === next.wave.monsters, () => serverView(NEXT));
  hold(NEXT);
  await until("Ann has the next chamber's wave", a, ([no, n]) => { const g = window.__game; return g.GB.wave && g.GB.wave.no === no && g.monsters.length === n; }, [next.wave.no, next.wave.monsters], () => both(a, NEXT));
  await sameMonsters("Ann sees the server's monsters downstairs", a, NEXT);
  await until("Bob, still upstairs, learns Ann went down and keeps his own wave", b, ([s, no]) => { const g = window.__game; return [...g.net.peers.values()].some(p => p.name === "Ann" && p.scene === s) && g.GB.wave.no === no; }, [NEXT, first.wave.no], () => view(b));
  check("the chamber upstairs still has its monsters", floorOf(START).monsters.length === first.wave.monsters, serverView(START));
  const t1 = floorOf(NEXT).wave.t0;
  // Bob follows her with the party list (session 17): P shows where Ann is, and Go takes him to her spot
  const annId = await a.evaluate(() => window.__game.net.id), annSpot = await serverHasMe(a, NEXT) && [playerOf(annId).st.x, playerOf(annId).st.z];
  await b.evaluate(() => window.__game.openParty());
  await until("the party list says Ann is in the next chamber's wave and offers Go", b, ([id, no]) => { const r = document.querySelector(`#pt-rows .row[data-id="${id}"]`); return !!r && r.textContent.includes(`wave ${no}`) && !!r.querySelector("[data-go]"); }, [annId, next.wave.no], () => b.evaluate(() => document.getElementById("pt-rows").textContent));
  await b.click(`#pt-rows [data-go="${annId}"]`); await settled(b, NEXT);
  check("Bob arrives where Ann stands", await b.evaluate(([x, z]) => Math.hypot(window.__game.P.p.x - x, window.__game.P.p.z - z) < 1.5, annSpot), await view(b));
  check("the server has Bob in the next chamber", await serverHasMe(b, NEXT), serverView(NEXT));
  await until("Bob has the same wave Ann met, not a new one", b, ([no, n]) => { const g = window.__game; return g.GB.wave && g.GB.wave.no === no && g.monsters.length === n; }, [next.wave.no, next.wave.monsters], () => both(b, NEXT));
  check("the next chamber's wave started once", floorOf(NEXT).wave.t0 === t1 && floorOf(NEXT).monsters.length === next.wave.monsters, serverView(NEXT));
  await sameMonsters("Bob sees the server's monsters downstairs", b, NEXT);
  await until("they see each other downstairs", a, s => [...window.__game.net.peers.values()].some(p => p.name === "Bob" && p.scene === s), NEXT, () => view(a));

  // ---- slice 2: the locker. Both pages put it in the same place; what you carry is the server's, and each player's own
  const bobId = await b.evaluate(() => window.__game.net.id), pa = playerOf(annId), pb = playerOf(bobId);
  const spots = await Promise.all([a, b].map(p => p.evaluate(() => window.__game.STN.spot)));
  check("the chamber's locker stands in the same place on both pages", !!spots[0] && JSON.stringify(spots[0]) === JSON.stringify(spots[1]), JSON.stringify(spots));
  check("both start carrying the ray, the cloak and the crossbow with its bolts (the server's word)", JSON.stringify(pa.ps.gbi.load.carry) === JSON.stringify(GEAR) && await a.evaluate(n => { const g = window.__game; return g.GB.load && g.GB.load.carry.length === 3 && g.BOW.st.bolts === n && g.owned().includes("crossbow"); }, START_BOLTS), await view(a));
  const side = await a.evaluate(() => { const g = window.__game, [sx, sz] = g.STN.spot; for (const [dx, dz] of [[1.2, 0], [-1.2, 0], [0, 1.2], [0, -1.2]]) if (!g.collide({x: sx + dx, y: g.S.floor + 0.02, z: sz + dz})) return [sx + dx, sz + dz]; return null; });
  await stand(a, NEXT, side[0], side[1], "Ann at the locker");
  check("Ann opens the locker with the action button", await a.evaluate(() => { const g = window.__game; return !!g.nearStation() && g.tryStation() && g.STN.open; }));
  await a.click('#st-rows button[data-gear="crossbow"]');
  await serverUntil("leaving the crossbow in the locker is the server's change, and only Ann's", () => !pa.ps.gbi.load.carry.includes("crossbow") && pb.ps.gbi.load.carry.includes("crossbow"), () => JSON.stringify([pa.ps.gbi.load, pb.ps.gbi.load]));
  await until("Ann's page shows it in the locker and no longer offers it to hold", a, () => { const g = window.__game; return !g.GB.load.carry.includes("crossbow") && !g.owned().includes("crossbow") && /IN LOCKER/.test(document.querySelector('#st-rows button[data-gear="crossbow"]').textContent); }, null, () => view(a));
  check("without it in hand a bolt cannot be shot", await a.evaluate(() => window.__game.fireBow() === false));
  await a.click('#st-rows button[data-gear="crossbow"]');
  await until("she takes it back", a, () => window.__game.GB.load.carry.includes("crossbow") && /CARRIED/.test(document.querySelector('#st-rows button[data-gear="crossbow"]').textContent), null, () => view(a));
  await a.evaluate(() => document.getElementById("st-close").click());

  // ---- slice 3: the Q and E consumables. The counts, the stun and the kills are the server's; both pages see the flash and the traps
  const fl = floorOf(NEXT), [pA, pB] = clearPair(fl.W, 6), total = next.wave.monsters;
  const park = () => fl.monsters.forEach((m, i) => m.pos.set(900 + i * 5, m.fy, 900));                   // out of the way; they are standing still (hold)
  const lost = async (label, wid, kills) => { for (const [nm, p] of [["Ann", a], ["Bob", b]]) await until(`${label}: ${nm}'s page lost the same monster and counts ${kills} down`, p, ([wid, k, left]) => { const g = window.__game; return !g.monsters.some(m => m.wid === wid) && g.monsters.length === left && g.GB.wave.kills === k; }, [wid, kills, total - kills], () => both(p, NEXT)); };
  park();
  for (const p of [a, b]) await p.evaluate(() => { const f = window.__game.TRAPS.flashes, push = f.push.bind(f); window.__flashes = 0; f.push = (...x) => { window.__flashes++; return push(...x); }; });          // count the bursts a page draws
  check("both start with the mode's consumables (the server's word)", JSON.stringify(pa.ps.gbi.kit) === JSON.stringify({n: KIT_START, e: "mine"}) && await a.evaluate(k => JSON.stringify(window.__game.GB.kit) === k, JSON.stringify({n: KIT_START, e: "mine"})), await a.evaluate(() => JSON.stringify(window.__game.GB.kit)));
  await stand(a, NEXT, pA[0], pA[1], "Ann at the firing spot");
  await a.evaluate(([pA, pB]) => { const g = window.__game; g.P.yaw = Math.atan2(-(pB[0] - pA[0]), -(pB[1] - pA[1])); g.P.pitch = 0; }, [pA, pB]);
  const m0 = fl.monsters[0]; m0.pos.set(pB[0], m0.fy, pB[1]); m0.stunT = 0;
  check("Q: Ann throws a flash-vial", await a.evaluate(() => window.__game.useConsumable(0) === true), await view(a));
  await serverUntil("the server took one vial and stunned the monster where it landed, and killed nothing", () => pa.ps.gbi.kit.n.flash === KIT_START.flash - 1 && m0.stunT > 0 && fl.monsters.length === total && fl.wave.kills === 0, () => `kit ${JSON.stringify(pa.ps.gbi.kit)}, stun ${m0.stunT}; ${serverView(NEXT)}`);
  await until("Ann's page shows the burst and the server's count", a, n => window.__flashes === 1 && window.__game.GB.kit.n.flash === n, KIT_START.flash - 1, () => view(a));
  await until("Bob's page shows the burst too, and his own vials are untouched", b, n => window.__flashes === 1 && window.__game.GB.kit.n.flash === n, KIT_START.flash, () => view(b));
  park();
  // E, the land mine: Bob sets one, both pages draw it where the server has it, and the server springs it under a monster
  await stand(b, NEXT, pB[0], pB[1], "Bob where the mine goes");
  check("E: Bob sets a land mine", await b.evaluate(() => window.__game.useConsumable(1) === true), await view(b));
  await serverUntil("the server holds the mine where it has Bob, and took one from his kit", () => fl.traps.length === 1 && fl.traps[0].kind === "mine" && Math.hypot(fl.traps[0].x - pB[0], fl.traps[0].z - pB[1]) < 0.5 && pb.ps.gbi.kit.n.mine === KIT_START.mine - 1, () => JSON.stringify(fl.traps));
  const mine = fl.traps[0];
  for (const [nm, p] of [["Ann", a], ["Bob", b]]) await until(`${nm}'s page shows the mine there`, p, ([id, x, z]) => window.__game.TRAPS.list.some(t => t.id === id && t.kind === "mine" && !t.done && t.mesh && Math.hypot(t.x - x, t.z - z) < 0.05), [mine.id, mine.x, mine.z], () => p.evaluate(() => JSON.stringify(window.__game.TRAPS.list.map(t => [t.id, t.kind, t.x, t.z, t.done]))));
  await stand(b, NEXT, pA[0] + 1, pA[1], "Bob steps away from it");
  const w1 = fl.monsters[0].wid; fl.monsters[0].pos.set(mine.x, fl.monsters[0].fy, mine.z);
  await serverUntil("a monster on the armed mine dies: the server's kill, credited to Bob", () => !fl.monsters.some(m => m.wid === w1) && fl.wave.kills === 1 && fl.traps.length === 0, () => `${serverView(NEXT)}; traps ${JSON.stringify(fl.traps)}`);
  await lost("the mine", w1, 1);
  await until("the spent mine is gone from both pages", a, id => window.__game.TRAPS.list.every(t => t.id !== id || t.done), mine.id, () => view(a)); await until("(Bob's too)", b, id => window.__game.TRAPS.list.every(t => t.id !== id || t.done), mine.id, () => view(b));
  // E, the tripwire: chosen at the locker (the server's choice to keep), then set by Ann
  await stand(a, NEXT, side[0], side[1], "Ann back at the locker");
  check("Ann opens the locker again", await a.evaluate(() => { const g = window.__game; return g.tryStation() && g.STN.open; }));
  await a.click('#st-rows button[data-slot="e"]');
  await serverUntil("the E slot now holds the tripwire, by the server", () => pa.ps.gbi.kit.e === "wire" && pb.ps.gbi.kit.e === "mine", () => JSON.stringify([pa.ps.gbi.kit, pb.ps.gbi.kit]));
  await until("the locker panel says so", a, () => window.__game.GB.kit.e === "wire" && /TRIPWIRE/.test(document.querySelector('#st-rows button[data-slot="e"]').textContent), null, () => view(a));
  await a.evaluate(() => document.getElementById("st-close").click());
  await stand(a, NEXT, pB[0], pB[1], "Ann where the tripwire goes");
  check("E: Ann sets the tripwire", await a.evaluate(() => window.__game.useConsumable(1) === true), await view(a));
  await serverUntil("the server holds the tripwire", () => fl.traps.length === 1 && fl.traps[0].kind === "wire" && pa.ps.gbi.kit.n.wire === KIT_START.wire - 1, () => JSON.stringify(fl.traps));
  const wire = fl.traps[0];
  await until("Bob's page shows Ann's tripwire", b, id => window.__game.TRAPS.list.some(t => t.id === id && t.kind === "wire" && !t.done), wire.id, () => view(b));
  await stand(a, NEXT, pA[0], pA[1], "Ann back at the firing spot");
  const w2 = fl.monsters[0].wid; fl.monsters[0].pos.set(wire.x + 1, fl.monsters[0].fy, wire.z);
  await serverUntil("a monster crossing the tripwire dies in the blast", () => !fl.monsters.some(m => m.wid === w2) && fl.wave.kills === 2 && fl.traps.length === 0, () => `${serverView(NEXT)}; traps ${JSON.stringify(fl.traps)}`);
  await lost("the tripwire", w2, 2);
  hold(NEXT); park();                                                                                      // the blast was loud: the one left went to look; stand it still again

  // ---- slice 2: the crossbow. Ann shoots what is left of the wave; the kills are the server's and both pages lose the same monsters
  await a.evaluate(([pA, pB]) => { const g = window.__game; g.P.yaw = Math.atan2(-(pB[0] - pA[0]), -(pB[1] - pA[1])); g.P.pitch = 0; g.setHeld("crossbow"); }, [pA, pB]);
  const before = fl.wave.kills;
  for (let n = 1; before + n <= total; n++) {
    const target = fl.monsters[0], wid = target.wid; target.pos.set(pB[0], target.fy, pB[1]);
    await until(`bolt ${n}: Ann's page has the monster in front of her and the bow is ready`, a, ([wid, x, z]) => { const g = window.__game, m = g.monsters.find(q => q.wid === wid); return m && Math.hypot(m.pos.x - x, m.pos.z - z) < 0.5 && g.BOW.st.cool === 0; }, [wid, pB[0], pB[1]], () => both(a, NEXT));
    await serverUntil(`bolt ${n}: the server's bow is reloaded`, () => pa.ps.gbi.bow.cool === 0, () => JSON.stringify(pa.ps.gbi.bow));
    check(`bolt ${n}: Ann shoots`, await a.evaluate(() => window.__game.fireBow() === true), await view(a));
    await serverUntil(`bolt ${n}: the server killed that monster and took one bolt`, () => !fl.monsters.some(m => m.wid === wid) && fl.wave.kills === before + n && pa.ps.gbi.bow.bolts === START_BOLTS - n, () => `${serverView(NEXT)}; bow ${JSON.stringify(pa.ps.gbi.bow)}`);
    await lost(`bolt ${n}`, wid, before + n);
  }
  check("the server says the wave is cleared", fl.wave.cleared === true && fl.monsters.length === 0, serverView(NEXT));
  await until("both pages know the wave is cleared", a, () => window.__game.GB.wave.cleared === true, null, () => view(a)); await until("(Bob too)", b, () => window.__game.GB.wave.cleared === true, null, () => view(b));
  await until("Ann's bolts on the page are the server's count", a, n => window.__game.BOW.st.bolts === n, START_BOLTS - (total - before), () => view(a));
  check("the chamber upstairs is untouched: its wave is not cleared", floorOf(START).wave.cleared === false && floorOf(START).monsters.length === first.wave.monsters, serverView(START));

  // ---- the mode's death rule in a room: down, nobody lifts you, you get up in the same chamber without your ammunition
  guarded = false; pb.ps.immUntil = 0; PS.hit(pb.ps, 100, Date.now() / 1000 + skew);
  await until("Bob is downed (the server's word), not dead: he can be lifted", b, () => window.__game.dead && /DOWNED/.test(document.getElementById("death").textContent), null, () => view(b));
  check("a down alone costs nothing yet", pb.ps.rounds === GUN_ROUNDS);
  skew += PS.DOWNED_S + 1;
  await until("with nobody lifting him the down time ends and Bob gets up", b, () => !window.__game.dead, null, () => view(b));
  await until("in the same chamber, with his ammunition gone", b, s => { const g = window.__game; return g.S.id === s && !g.loading && g.LT.rounds === 0 && g.HP.h.hp === 100; }, NEXT, () => view(b));
  check("the server counted one death", pb.ps.stats.deaths === 1 && pb.scene === NEXT, JSON.stringify(pb.ps.stats));
  await until("his gear is in the locker: he carries nothing and holds nothing", b, () => { const g = window.__game; return g.GB.load.carry.length === 0 && g.owned().length === 0 && g.HELD.item === null && g.BOW.st.bolts === 0; }, null, () => view(b));
  guarded = true;
  await stand(b, NEXT, side[0], side[1], "Bob at the locker");
  check("Bob opens the locker", await b.evaluate(() => { const g = window.__game; return g.tryStation() && g.STN.open; }));
  for (const g of GEAR) await b.click(`#st-rows button[data-gear="${g}"]`);
  await until("the locker returns the ray, the cloak and the crossbow for free, but no ammunition", b, () => { const g = window.__game; return g.GB.load.carry.length === 3 && g.LT.gun && g.CL.have && g.LT.rounds === 0 && g.BOW.st.bolts === 0 && g.GB.kit.n.flash === 0 && g.GB.kit.n.mine === 0; }, null, () => view(b));
  check("Ann lost nothing by Bob's death", pa.ps.gbi.load.carry.length === 3 && pa.ps.rounds === GUN_ROUNDS, JSON.stringify(pa.ps.gbi));
} catch (e) { console.log("ERROR", e.stack || e.message); failed++; }
finally { clearInterval(guardT); await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "all passed"); process.exit(failed ? 1 : 0);
