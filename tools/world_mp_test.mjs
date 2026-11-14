// The Overworld and the City in rooms (session 17): presence only. Starts server/server.js on a free port and opens real game pages in one room.
//   slice 1: two players finish a round, both walk out to the parking lot and see each other move there; a third who has not finished the Original cannot enter, and
//            from a Backrooms floor sees nobody in the lot.
//   slice 2: both ride the bus to Hallam Row and see each other on the street; each has their own clock, and a name tag carries that player's time; the tower door
//            opens for a room (the apartment), every other door of the street says it is a solo place.
//   slice 3: the party list (P) says where each player is; Go takes you to a friend on the street or on a floor; a player without the flag is not offered the City
//            and is refused by the server if their page asks anyway; at night (your own clock) there is no way out of the City by a friend either.
// The server is in this process, so the checks wait on the server's own view of a player (what it relays from), never on a fixed delay after a teleport.
// Usage: node tools/world_mp_test.mjs      (needs Playwright + Chromium and internet for three.js from unpkg)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
import {DOORS, BUS_LOT, BUS_STREET, APARTMENT, secondsAt} from "../shared/city.js";
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

  // ---- slice 2: the bus to Hallam Row, in a room. Presence only: every City rule stays each player's own.
  const bus = REGISTRY.linkFrom("parking_lot", "bus_stop"), busBack = REGISTRY.linkFrom("street", "bus_stop"), streetLinks = REGISTRY.linksFrom("street").filter(l => l.status === "built");
  check("the manifest: the street and the apartment are presence scenes; the bus and the tower door are for rooms too, every other street door is solo only",
    REGISTRY.presence.street === 0 && REGISTRY.presence.apartment === 0 && !bus.soloOnly && !busBack.soloOnly && streetLinks.every(l => !!l.soloOnly === !["bus_stop", "tower"].includes(l.from.door)), streetLinks.filter(l => !l.soloOnly).map(l => l.id).join());
  const toastOf = pg => pg.evaluate(() => document.getElementById("toast").textContent), promptOf = pg => pg.evaluate(() => window.__game.cityPrompt());
  await stand(a, idA, "parking_lot", BUS_LOT.at[0], BUS_LOT.at[1], "Ann at the lot's bus stop");
  check("the bus stop offers the ride to a player in a room", /take the bus to Hallam Row/.test(await promptOf(a)), await promptOf(a));
  await a.evaluate(() => { window.__game.tryCity(); }); await settled(a, "street");
  await serverUntil("Ann rode the bus: the server has her on the street", () => serverHas(idA, "street", bus.to.arrive[0], bus.to.arrive[2]), () => xzOf(playerOf(idA)));
  const hudOf = pg => pg.evaluate(() => document.getElementById("hud").textContent);
  check("in the City the HUD says, for as long as you are there, that only presence is shared", /you only see each other; clocks, money and jobs are your own/.test(await hudOf(a)) && !/your own/.test(await hudOf(b)), `${await hudOf(a)} | ${await hudOf(b)}`);
  await until("Bob, still in the lot, sees that Ann went to the street and no longer draws her", b, id => { const p = window.__game.net.peers.get(id); return p && p.scene === "street" && !p.obj.visible; }, idA);
  await stand(b, idB, "parking_lot", BUS_LOT.at[0], BUS_LOT.at[1], "Bob at the lot's bus stop");
  await b.evaluate(() => { window.__game.tryCity(); }); await settled(b, "street");
  await serverUntil("Bob rode the bus too", () => serverHas(idB, "street"), () => xzOf(playerOf(idB)));
  check("the server runs nothing for the street", Object.keys(room().floors).every(f => REGISTRY.floors[f] !== undefined), Object.keys(room().floors).join());
  await stand(a, idA, "street", 3.6, 1, "Ann on the sidewalk"); await stand(b, idB, "street", 3.6, -2, "Bob beside her");
  await until("Ann sees Bob on the street", a, id => { const p = window.__game.net.peers.get(id); return p && p.scene === "street" && p.obj.visible && Math.hypot(p.tx - 3.6, p.tz + 2) < 0.5; }, idB, async () => JSON.stringify(await peerOn(a, idB)));
  await until("Bob sees Ann on the street", b, id => { const p = window.__game.net.peers.get(id); return p && p.scene === "street" && p.obj.visible && Math.hypot(p.tx - 3.6, p.tz - 1) < 0.5; }, idA, async () => JSON.stringify(await peerOn(b, idA)));
  // each player's clock is their own: Ann's is set to 22:00, Bob's is still in his first morning. Each sees the other's time on the other's name tag.
  await a.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(22));
  const clocks = async () => JSON.stringify({ann: await a.evaluate(id => ({mine: window.__game.cityState().clock, bobTag: window.__game.net.peers.get(id).tod}), idB), bob: await b.evaluate(id => ({mine: window.__game.cityState().clock, annTag: window.__game.net.peers.get(id).tod}), idA)});
  await until("Bob's page has Ann's time for her name tag (late evening) while his own clock says day", b, id => { const g = window.__game, p = g.net.peers.get(id), h = g.cityState().hour; return p && p.tod != null && (p.tod >= 21.9 || p.tod < 3) && h >= 8 && h < 20; }, idA, clocks);
  await until("and Ann's page has Bob's time for his (day) while hers says night", a, id => { const g = window.__game, p = g.net.peers.get(id), h = g.cityState().hour; return p && p.tod != null && p.tod >= 8 && p.tod < 20 && (h >= 21.9 || h < 3); }, idB, clocks);
  await a.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(10));          // back to day, so the night's own rules (the stalker, no bus) stay out of the rest of this test
  // the doors: the grocery is a solo place, the tower (home) opens
  const groc = DOORS.find(d => d.id === "grocery"), tower = DOORS.find(d => d.kind === "tower"), inFront = d => [d.x + (d.side === "w" ? 1.2 : -1.2), d.z];
  await stand(b, idB, "street", ...inFront(groc), "Bob at the grocery door");
  await b.evaluate(() => { window.__game.tryCity(); });
  check("the grocery door says it is a solo place, and Bob stays on the street", /solo place/.test(await toastOf(b)) && /solo place/.test(await promptOf(b)) && await b.evaluate(() => window.__game.S.id === "street" && !window.__game.loading), `${await toastOf(b)} / ${await promptOf(b)}`);
  await stand(b, idB, "street", ...inFront(tower), "Bob at the tower door");
  await b.evaluate(() => { window.__game.tryCity(); }); await settled(b, "apartment");
  await serverUntil("the tower door opens for a room: the server has Bob in the apartment", () => serverHas(idB, "apartment"), () => xzOf(playerOf(idB)));
  await until("Ann, on the street, no longer draws Bob", a, id => { const p = window.__game.net.peers.get(id); return p && p.scene === "apartment" && !p.obj.visible; }, idB);
  await stand(b, idB, "apartment", APARTMENT.door.at[0], APARTMENT.door.at[1] , "Bob at his front door");
  await b.evaluate(() => { window.__game.tryCity(); }); await settled(b, "street");
  await serverUntil("and back out to the street", () => serverHas(idB, "street"), () => xzOf(playerOf(idB)));

  // ---- slice 3: the party list and "go to a friend"
  await c.evaluate(() => window.__game.loadScene("L4")); await settled(c, "L4");
  await serverUntil("Cy is back on L4", () => serverHas(idC, "L4"), () => xzOf(playerOf(idC))); guard(); parkMonsters(room().floors.L4);
  await stand(a, idA, "street", BUS_STREET.at[0] - 1.5, BUS_STREET.at[1], "Ann at the street's bus stop");
  await a.evaluate(() => { window.__game.tryCity(); }); await settled(a, "parking_lot");
  await serverUntil("Ann rode back to the lot", () => serverHas(idA, "parking_lot", busBack.to.arrive[0], busBack.to.arrive[2]), () => xzOf(playerOf(idA)));
  check("back in the lot the City's line is gone from the HUD", !/your own/.test(await hudOf(a)), await hudOf(a));
  await a.keyboard.press("KeyP");
  const rowsOf = pg => pg.evaluate(() => ({shown: getComputedStyle(document.getElementById("party")).display === "flex", rows: [...document.querySelectorAll("#pt-rows .row")].map(r => ({text: r.textContent, go: !!r.querySelector("button")}))}));
  const la = await rowsOf(a);
  check("P opens the party list: where you are, where Bob is (Hallam Row) and where Cy is (floor L4), each with Go", la.shown && /You.*the parking lot/.test(la.rows[0].text) && la.rows.some(r => /Bob.*Hallam Row/.test(r.text) && r.go) && la.rows.some(r => /Cy.*floor L4/.test(r.text) && r.go), JSON.stringify(la));
  await c.evaluate(() => window.__game.openParty());
  const lc = await rowsOf(c);
  check("Cy, who has not finished the Original, sees where the others are but is not offered the City or the lot", lc.shown && lc.rows.some(r => /Ann.*the parking lot.*finish the Original first/.test(r.text) && !r.go) && lc.rows.some(r => /Bob.*Hallam Row.*finish the Original first/.test(r.text) && !r.go), JSON.stringify(lc));
  await c.evaluate(() => window.__game.closeParty());
  await c.evaluate(id => window.__game.net.send({t: "goto", to: id}), idB);          // a page that asks anyway
  await until("the server refuses Cy, and the page says why", c, () => /cannot go to Bob yet: finish the Original first/.test(document.getElementById("toast").textContent));
  check("Cy is still on L4", await c.evaluate(() => window.__game.S.id === "L4") && playerOf(idC).scene === "L4");
  const bobAt = {...playerOf(idB).st};
  await press(a, `#pt-rows [data-go="${idB}"]`); await settled(a, "street");
  await serverUntil("Go takes Ann to Bob: the server has her at his spot on the street", () => serverHas(idA, "street", bobAt.x, bobAt.z), () => xzOf(playerOf(idA)) + "; " + xzOf(playerOf(idB)));
  check("the list closed and the page says where she is", await a.evaluate(() => !window.__game.PT.open && getComputedStyle(document.getElementById("party")).display === "none" && /You are with Bob: Hallam Row/.test(document.getElementById("toast").textContent)), await toastOf(a));
  await until("Bob sees Ann arrive beside him", b, ([id, x, z]) => { const p = window.__game.net.peers.get(id); return p && p.scene === "street" && p.obj.visible && Math.hypot(p.tx - x, p.tz - z) < 0.6; }, [idA, bobAt.x, bobAt.z], async () => JSON.stringify(await peerOn(b, idA)));
  // at night, by your own clock, there is no way out of the City: the bus does not run, and a friend is no way round it
  const night = await a.evaluate(([id, t, day]) => { const g = window.__game, was = g.CITY.t; g.CITY.t = t; const r = g.gotoState(g.net.peers.get(id)); g.CITY.t = day; return r; }, [idC, secondsAt(25), secondsAt(10)]);
  check("at 01:00 on Ann's clock she cannot go to a friend outside the City", night.ok === false && /night/.test(night.why), JSON.stringify(night));
  const cyAt = {...playerOf(idC).st};
  await a.evaluate(id => { window.__game.openParty(); window.__game.goToFriend(id); }, idC); await settled(a, "L4");
  await serverUntil("by day Go takes Ann from the street to Cy on L4", () => serverHas(idA, "L4", cyAt.x, cyAt.z), () => xzOf(playerOf(idA)) + "; " + xzOf(playerOf(idC)));
  await until("Cy sees Ann beside him on L4", c, id => { const p = window.__game.net.peers.get(id); return p && p.scene === "L4" && p.obj.visible; }, idA);

  // ---- leaving the room: the others are told
  await b.close();
  await until("Bob left: Ann no longer has him", a, id => !window.__game.net.peers.has(id), idB);
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e); failed++; }
await browser.close(); await srv.close();
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
