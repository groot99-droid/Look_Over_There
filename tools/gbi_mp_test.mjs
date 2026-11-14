// Going back in in a room (session 16): two real pages in one going_back_in room against server/server.js. Slice 1: the lobby's button, both land in the first chamber,
// the server's wave on both pages, presence, the stairs down to the next chamber, and the mode's death rule. Later slices add to the end of this file.
// Every wait is on what the page or the server holds (the server runs in this process), never a fixed sleep after a teleport: the server acts on the position it last heard.
// Usage: node tools/gbi_mp_test.mjs      (needs Playwright + Chromium and internet for three.js from unpkg)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import * as PS from "../server/playerstate.js";
import {REGISTRY} from "../shared/registry.js";
import {GUN_ROUNDS} from "../shared/loot.js";
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
  await takeStairs(b, first.stairsDown); await settled(b, NEXT);
  check("the server has Bob in the next chamber", await serverHasMe(b, NEXT), serverView(NEXT));
  await until("Bob has the same wave Ann met, not a new one", b, ([no, n]) => { const g = window.__game; return g.GB.wave && g.GB.wave.no === no && g.monsters.length === n; }, [next.wave.no, next.wave.monsters], () => both(b, NEXT));
  check("the next chamber's wave started once", floorOf(NEXT).wave.t0 === t1 && floorOf(NEXT).monsters.length === next.wave.monsters, serverView(NEXT));
  await sameMonsters("Bob sees the server's monsters downstairs", b, NEXT);
  await until("they see each other downstairs", a, s => [...window.__game.net.peers.values()].some(p => p.name === "Bob" && p.scene === s), NEXT, () => view(a));

  // ---- the mode's death rule in a room: down, nobody lifts you, you get up in the same chamber without your ammunition
  const bobId = await b.evaluate(() => window.__game.net.id), pb = playerOf(bobId);
  guarded = false; pb.ps.immUntil = 0; PS.hit(pb.ps, 100, Date.now() / 1000 + skew);
  await until("Bob is downed (the server's word), not dead: he can be lifted", b, () => window.__game.dead && /DOWNED/.test(document.getElementById("death").textContent), null, () => view(b));
  check("a down alone costs nothing yet", pb.ps.rounds === GUN_ROUNDS);
  skew += PS.DOWNED_S + 1;
  await until("with nobody lifting him the down time ends and Bob gets up", b, () => !window.__game.dead, null, () => view(b));
  await until("in the same chamber, with his ammunition gone", b, s => { const g = window.__game; return g.S.id === s && !g.loading && g.LT.rounds === 0 && g.HP.h.hp === 100; }, NEXT, () => view(b));
  check("the server counted one death", pb.ps.stats.deaths === 1 && pb.scene === NEXT, JSON.stringify(pb.ps.stats));
} catch (e) { console.log("ERROR", e.stack || e.message); failed++; }
finally { clearInterval(guardT); await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "all passed"); process.exit(failed ? 1 : 0);
