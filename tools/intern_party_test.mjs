// The Intern in a party room (session 11, slice 4): two players of one room enter the game separately, are in one place on the server, see each other in the same
// room of the building, and leave without ending the other's game; a friend can be joined at a later stage. Uses the real server and two headless pages.
// The game runs in an iframe of the page; the test reads it through the iframe's own window (window.__NINETY_NINE__).
// Usage: node tools/intern_party_test.mjs     (needs Playwright + Chromium; run from the repo root)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
const {chromium} = createRequire(import.meta.url)("playwright");
const sleep = ms => new Promise(r => setTimeout(r, ms));
let failed = 0; const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const srv = await createServer({port: 0, countdownMs: 500});
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const errors = [];
const open = async (name, char) => {
  const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage(); page.on("pageerror", e => errors.push(`${name}: ${e.message}`));
  await page.goto(`http://localhost:${srv.port}/?room=INTERN&name=${name}&char=${char}&auto=1&ready=1`);
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000}); return page;
};
const until = (page, fn, arg, ms = 90000) => page.waitForFunction(fn, arg, {timeout: ms, polling: 100}).then(() => true, () => false);
const room = () => srv.rooms.get("INTERN");
const placeOf = id => room().players.get(id)?.scene;
const serverPlace = async (id, want, ms = 30000) => { const t0 = Date.now(); while (Date.now() - t0 < ms) { if (placeOf(id) === want) return true; await sleep(100); } return false; };
const GATE = "DoorLeaf_Gate_ITN", ARRIVE = [116.4, 75.0];
// the game's own window, inside the page: null until the game has booted and the player walks
const game = `(() => { const f = document.querySelector("#gamemount iframe"), n = f && f.contentWindow && f.contentWindow.__NINETY_NINE__; return n && n.coop ? n : null; })()`;
const running = (page, ms = 240000) => until(page, `(() => { const n = ${game}; return !!n && n.stage.isPlayerActive(); })()`, null, ms);
// L4 -> the gate door -> the passage "T" -> its far door -> the game's frame is on the page
async function enter(page, door) {
  await page.evaluate(async door => {
    const g = window.__game; if (g.S.id !== "L4") await g.loadScene("L4");
    const dr = g.doors.find(d => d.d.name === door); g.teleport([dr.cx, g.S.floor, dr.cz]); g.openDoor(dr, true);
  }, door);
  if (!await until(page, () => window.__game.S.id === "T" && !window.__game.loading)) return false;
  await page.evaluate(() => { const g = window.__game, dr = g.doors.find(d => d.link && d.link.game); g.openDoor(dr, true); });
  return await until(page, () => !!document.querySelector("#gamemount iframe")) && running(page);
}
const coop = page => page.evaluate(`(() => { const n = ${game}; return n ? {peers: n.coop.count(), at: n.coop.self(), figures: n.coop.positions()} : null; })()`);
const sees = (page, n, ms = 30000) => until(page, `(() => { const g = ${game}; return !!g && g.coop.count() === ${n}; })()`, null, ms);
const endGame = page => page.evaluate(() => document.querySelector("#gamemount iframe").contentWindow.eval("parent.postMessage({type: \"intern-ending\"}, \"*\")"));          // posted from inside the game's frame, as the game does at its ending
const backOnL4 = page => until(page, () => window.__game.S.id === "L4" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000);
try {
  const a = await open("Ann", 0), b = await open("Bob", 3);
  await Promise.all([a, b].map(p => p.waitForFunction(() => window.__game.net.phase === "playing" && !window.__game.loading, null, {timeout: 120000})));
  const aid = await a.evaluate(() => window.__game.net.id), bid = await b.evaluate(() => window.__game.net.id);
  check("Ann goes through the Intern's gate in a room and the game runs", await enter(a, GATE));
  check("the server has Ann in the game's first stage", await serverPlace(aid, "intern:S0"), String(placeOf(aid)));
  check("Bob goes through the same gate and the game runs for him", await enter(b, GATE));
  check("the server has Bob in the same stage: one place, two players", await serverPlace(bid, "intern:S0"), String(placeOf(bid)));
  check("each sees the other in the game", await sees(a, 1) && await sees(b, 1), JSON.stringify({a: await coop(a), b: await coop(b)}));
  const sa = await coop(a);
  check("a player's spot is given in the room's own frame, with the room's name", !!sa && sa.at && sa.at.room === "S0_X" && [sa.at.x, sa.at.y, sa.at.z].every(Number.isFinite) && Math.abs(sa.at.x) < 3 && Math.abs(sa.at.z) < 3, JSON.stringify(sa && sa.at));
  // Ann steps somewhere else in the room: Bob's figure of her follows, and the server holds the spot she sent (it was inside its limits)
  const to = await a.evaluate(`(() => { const n = ${game}, p = n.stage.player, f = p.feet(); p.teleport(f[0] + 0.6, f[1], f[2] + 0.5, p.yawDeg()); return null; })()`).then(() => sleep(600)).then(() => coop(a)).then(s => s.at);
  const followed = await until(b, `(() => { const g = ${game}, f = g && g.coop.positions()[0]; return !!f && f.room === ${JSON.stringify(to.room)} && Math.hypot(f.x - ${to.x}, f.z - ${to.z}) < 0.3; })()`, null, 30000);
  check("Bob's figure of Ann follows her", followed, JSON.stringify({to, b: await coop(b)}));
  const st = room().players.get(aid).st;
  check("the server holds the spot Ann sent", !!st && Math.hypot(st.x - to.x, st.z - to.z) < 0.3 && st.sub === to.room, JSON.stringify(st));
  // Ann's game ends: she is back on L4 at the gate's arrival point, Bob's game goes on
  await endGame(a);
  check("Ann is back on L4 at the arrival point", await backOnL4(a) && await a.evaluate(([x, z]) => { const p = window.__game.P.p; return Math.hypot(p.x - x, p.z - z) < 2.5; }, ARRIVE));
  check("the server has Ann on L4 and Bob still in the game", await serverPlace(aid, "L4") && placeOf(bid) === "intern:S0", `${placeOf(aid)} / ${placeOf(bid)}`);
  check("Bob's game is still running, alone now", await sees(b, 0) && await b.evaluate(`(() => { const n = ${game}; return !!n && n.stage.isPlayerActive(); })()`));
  await endGame(b);
  check("Bob comes back to L4 too", await backOnL4(b));
  // a later stage, in the building's other render: Bob starts at the fourth stage in the room S3_H (through the page's own entry, as a jump to a friend there does),
  // and Ann goes to him with "go to a friend": the server tells her page his stage and room, and her game starts in that room, not the default one
  await b.evaluate(() => { const g = window.__game; g.enterGame({game: "intern", room: "S3", sub: "S3_H", scene: "L4", arrive: [116.4, 9.6, 75.0], face: [1.0, 0.0]}); });
  check("Bob's game runs at a later stage", await until(b, () => !!document.querySelector("#gamemount iframe")) && await running(b));
  check("the server has Bob in that stage", await serverPlace(bid, "intern:S3"), String(placeOf(bid)));
  const sb = await coop(b);
  check("Bob is in the room he asked for", !!sb && !!sb.at && sb.at.room === "S3_H", JSON.stringify(sb && sb.at));
  await a.evaluate(id => window.__game.goToFriend(id), bid);
  check("Ann goes to her friend and her game runs", await until(a, () => !!document.querySelector("#gamemount iframe"), null, 60000) && await running(a));
  check("the server has Ann in Bob's stage", await serverPlace(aid, "intern:S3"), String(placeOf(aid)));
  const sa3 = await coop(a);
  check("Ann is in the same room of the building as Bob", !!sa3 && !!sb && sa3.at.room === sb.at.room, JSON.stringify({ann: sa3 && sa3.at, bob: sb && sb.at}));
  check("they see each other there", await sees(a, 1) && await sees(b, 1), JSON.stringify({a: await coop(a), b: await coop(b)}));
  await endGame(a); await endGame(b);
  check("both come back to L4", await backOnL4(a) && await backOnL4(b));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
