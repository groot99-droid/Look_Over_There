// The Overworld and the City in rooms (session 17): presence only. Starts server/server.js on a free port and opens real game pages in one room.
//   slice 1: two players finish a round, both walk out to the parking lot and see each other move there; a third who has not finished the Original cannot enter, and
//            from a Backrooms floor sees nobody in the lot.
// The server is in this process, so the checks wait on the server's own view of a player (what it relays from), never on a fixed delay after a teleport.
// Usage: node tools/world_mp_test.mjs      (needs Playwright + Chromium and internet for three.js from unpkg)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; return !!ok; };

const CODE = "WORLD", srv = await createServer({port: 0, countdownMs: 400});
const room = () => srv.rooms.get(CODE), playerOf = id => room()?.players.get(id);
const xzOf = p => p && p.st ? `server sees ${p.name} in ${p.scene} at (${p.st.x.toFixed(1)}, ${p.st.y.toFixed(1)}, ${p.st.z.toFixed(1)})` : `server has no position (${p ? p.scene : "no player"})`;
const serverUntil = async (name, fn, why = () => "", ms = 60000) => { const end = Date.now() + ms; while (Date.now() < end) { if (fn()) return check(name, true); await sleep(50); } return check(name, false, why()); };
// the server has player `id` in `scene`, within 0.5 m of (x, z) when given
const serverHas = (id, scene, x = null, z = null) => { const p = playerOf(id); return !!p && p.scene === scene && !!p.st && (x === null || Math.hypot(p.st.x - x, p.st.z - z) < 0.5); };
const guard = () => { for (const p of room().players.values()) p.ps.immUntil = 1e15; };                    // the server's immunity: no monster interferes
const parkMonsters = floor => floor.monsters.forEach((m, i) => { m.cfg = {...m.cfg, patrol: 0, alert: 0, chase: 0}; m.pos.set(900 + i * 5, m.fy, 900); m.state = "patrol"; m.path = []; m.wait = 99; });

const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const errors = [];
async function open(name, char, query = "&ready=1") {                  // one window each: a background tab's animation is paused, which would stall that player's game clock
  const page = await (await browser.newContext({viewport: {width: 320, height: 200}})).newPage();
  page.on("pageerror", e => { errors.push(`${name}: ${e.message}`); console.log(`[${name} pageerror]`, e.message); });
  await page.goto(`http://localhost:${srv.port}/?room=${CODE}&name=${name}&char=${char}&auto=1${query}`);
  return page;
}
const inGame = p => p.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
const settled = (page, id) => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
const until = (name, page, fn, arg, why = () => "") => page.waitForFunction(fn, arg, {timeout: 60000, polling: 200}).then(() => check(name, true), async () => check(name, false, await why()));
const press = (page, sel) => page.$eval(sel, el => { if (el.hidden || el.disabled) throw new Error(`${el.id || el.tagName} cannot be pressed`); el.click(); });          // a real click on the element (the test windows are too small for Playwright to aim at it)
const idOf = page => page.evaluate(() => window.__game.net.id);
// what a page knows about one peer
const peerOn = (page, id) => page.evaluate(id => { const g = window.__game, p = g.net.peers.get(id); return p ? {scene: p.scene, visible: p.obj.visible, tx: p.tx, ty: p.ty, tz: p.tz, x: p.x, z: p.z, tag: !!p.tex, name: p.name} : null; }, id);
// puts the page's player at (x, z) on the scene's ground, then waits for the server to have them there
async function stand(page, id, scene, x, z, label) {
  const free = await page.evaluate(([x, z]) => { const g = window.__game, y = g.S.floor + 0.02; if (g.collide({x, y, z})) return false; g.P.p.set(x, y, z); g.P.v.set(0, 0, 0); return true; }, [x, z]);
  if (!free) return check(`${label}: the spot is open ground`, false, `(${x}, ${z}) is inside a collider`);
  return serverUntil(`${label}: the server has them there`, () => serverHas(id, scene, x, z), () => xzOf(playerOf(id)));
}

try {
  const out = REGISTRY.linkFrom("L4", "front_doors");
  check("the manifest: the lot is a presence scene and the walk out is a link a room can follow, still needing original_complete", REGISTRY.presence.parking_lot !== undefined && !!out && !out.soloOnly && (out.requires || []).includes("original_complete"));

  // ---- a round for two, finished: both get the results, and both hold the flag (it was their first finish)
  const a = await open("Ann", 0), b = await open("Bob", 3);
  await Promise.all([inGame(a), inGame(b)]);
  await serverUntil("both are in the room and the round has started", () => room() && room().players.size === 2 && room().phase === "playing"); guard();
  const idA = await idOf(a), idB = await idOf(b);
  for (const pg of [a, b]) { await pg.evaluate(() => window.__game.loadScene("L4")); await settled(pg, "L4"); }
  await serverUntil("the server has both on L4", () => serverHas(idA, "L4") && serverHas(idB, "L4"), () => xzOf(playerOf(idA)) + "; " + xzOf(playerOf(idB))); parkMonsters(room().floors.L4);
  check("before the round is over the walk out is not offered", await a.evaluate(() => document.getElementById("r-walk").hidden));
  await a.evaluate(() => window.__game.net.send({t: "power"}));          // the power itself is tools/mp_test.mjs's business: here the server is simply told, once it has Ann on L4
  await until("the power is on for both", b, () => window.__game.POWER.on);
  for (const pg of [a, b]) await pg.evaluate(() => { const g = window.__game; g.P.imm = 99; g.P.p.set(0, g.S.floor + 0.02, g.EXIT_Z + 0.5); g.step(0.02); });
  await until("both walked out of the store: Ann sees the results", a, () => !!window.__game.FIN.results);
  await until("and Bob", b, () => !!window.__game.FIN.results);
  check("the server knows for itself that both finished the Original", playerOf(idA).flags.has("original_complete") && playerOf(idB).flags.has("original_complete"));
  const offer = pg => pg.evaluate(() => ({shown: !document.getElementById("r-walk").hidden, flag: window.__game.heldFlags().includes("original_complete"), on: window.__game.net.on}));
  const oa = await offer(a), ob = await offer(b);
  check("in a room the results screen offers the walk out to both", oa.shown && ob.shown && oa.flag && ob.flag && oa.on && ob.on, JSON.stringify({oa, ob}));

  // ---- both walk out: each arrives at the table, the server has both in the lot, and each sees the other there
  await press(a, "#r-walk"); await settled(a, "parking_lot");
  await serverUntil("Ann walked out: the server has her in the lot", () => serverHas(idA, "parking_lot", out.to.arrive[0], out.to.arrive[2]), () => xzOf(playerOf(idA)));
  check("Bob, still at the results on L4, does not see Ann in his scene", !(await peerOn(b, idA)).visible);
  await press(b, "#r-walk"); await settled(b, "parking_lot");
  await serverUntil("Bob walked out: the server has him in the lot", () => serverHas(idB, "parking_lot"), () => xzOf(playerOf(idB)));
  check("the results screen is gone and the HUD says who is here", await a.evaluate(() => getComputedStyle(document.getElementById("results")).display === "none" && /Bob/.test(document.getElementById("hud").textContent)));
  check("the server runs no floor for the lot", room().floors.parking_lot === undefined, Object.keys(room().floors).join());
  await stand(a, idA, "parking_lot", -8, 46, "Ann by the table"); await stand(b, idB, "parking_lot", -5, 46, "Bob three metres away");
  await until("Ann sees Bob in the lot, with his avatar and name tag", a, id => { const p = window.__game.net.peers.get(id); return p && p.scene === "parking_lot" && p.obj.visible && Math.hypot(p.tx + 5, p.tz - 46) < 0.5 && Math.abs(p.ty - 9.6) < 0.3 && p.obj.children.some(o => o.isSprite && o.material.map === p.tex); }, idB, async () => JSON.stringify(await peerOn(a, idB)) + "; " + xzOf(playerOf(idB)));
  await until("Bob sees Ann in the lot", b, id => { const p = window.__game.net.peers.get(id); return p && p.scene === "parking_lot" && p.obj.visible && Math.hypot(p.tx + 8, p.tz - 46) < 0.5; }, idA, async () => JSON.stringify(await peerOn(b, idA)) + "; " + xzOf(playerOf(idA)));
  // each sees the other move
  await stand(b, idB, "parking_lot", -12, 50, "Bob walks off");
  await until("Ann sees Bob move, and his avatar follows", a, id => { const p = window.__game.net.peers.get(id); return p && Math.hypot(p.tx + 12, p.tz - 50) < 0.5 && Math.hypot(p.obj.position.x + 12, p.obj.position.z - 50) < 1; }, idB, async () => JSON.stringify(await peerOn(a, idB)));
  await stand(a, idA, "parking_lot", -20, 44, "Ann walks off");
  await until("Bob sees Ann move", b, id => { const p = window.__game.net.peers.get(id); return p && Math.hypot(p.tx + 20, p.tz - 44) < 0.5 && Math.hypot(p.obj.position.x + 20, p.obj.position.z - 44) < 1; }, idA, async () => JSON.stringify(await peerOn(b, idA)));

  // ---- the lot runs no rules: the store-doors screen is each player's own, and Going back in is not offered to a room
  await a.evaluate(() => { const g = window.__game; g.OW.armed = true; g.P.p.set(0, g.S.floor + 0.02, 30); g.P.v.set(0, 0, 0); g.step(0.02); });
  const opt = await a.evaluate(() => ({open: window.__game.OW.open, back: document.getElementById("o-back").disabled}));
  check("at the store doors the options screen opens, with Going back in shut for a room", opt.open && opt.back, JSON.stringify(opt));
  check("Bob's screen did not open", !(await b.evaluate(() => window.__game.OW.open)));
  await a.evaluate(() => window.__game.closeOptions());

  // ---- a third player joins late and has never finished the Original: no way out, and the server refuses a page that goes anyway
  const c = await open("Cy", 2); await inGame(c);
  const idC = await idOf(c); guard();
  check("the newcomer does not hold the flag and is not offered the walk out", await c.evaluate(() => !window.__game.heldFlags().includes("original_complete") && document.getElementById("r-walk").hidden));
  check("the newcomer already knows the other two are in the lot", (await peerOn(c, idA)).scene === "parking_lot" && (await peerOn(c, idB)).scene === "parking_lot", JSON.stringify(await peerOn(c, idA)));
  await c.evaluate(() => { document.getElementById("results").style.display = "none"; return window.__game.loadScene("L4"); }); await settled(c, "L4");
  await serverUntil("the server has the newcomer on L4", () => serverHas(idC, "L4"), () => xzOf(playerOf(idC)));
  await stand(a, idA, "parking_lot", -9, 45, "Ann moves while Cy is on L4");
  await sleep(600);                                                     // nothing should arrive: give it time to (a wait for an absence has nothing to wait on)
  const seen = await peerOn(c, idA);
  check("from a Backrooms floor the lot's players are not drawn and their positions do not arrive", !seen.visible && seen.scene === "parking_lot" && Math.hypot(seen.tx + 9, seen.tz - 45) > 0.5, JSON.stringify(seen));
  check("and the lot does not see the player on L4", !(await peerOn(a, idC)).visible && (await peerOn(a, idC)).scene === "L4");
  await c.evaluate(() => window.__game.loadScene("parking_lot", {pos: [-8, 9.6, 43.6]})); await settled(c, "parking_lot");          // a page that goes anyway (the game never offers it)
  await until("the server refuses, and the page says so", c, () => /will not let you in/.test(document.getElementById("toast").textContent));
  await sleep(600);
  check("the server has the newcomer nowhere, and nobody in the lot sees them", playerOf(idC).scene === null && !(await peerOn(a, idC)).visible && !(await peerOn(b, idC)).visible, xzOf(playerOf(idC)));
  check("the newcomer sees nobody either", !(await peerOn(c, idA)).visible && !(await peerOn(c, idB)).visible, JSON.stringify(await peerOn(c, idA)));

  // ---- leaving the room: the others are told
  await b.close();
  await until("Bob left: Ann no longer has him", a, id => !window.__game.net.peers.has(id), idB);
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e); failed++; }
await browser.close(); await srv.close();
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
