// The City, v0: from the Overworld's parking lot you take the bus to Hallam Row, the 15-minute game day starts at 08:00 and advances only while you are in the City, and the
// stores close at 20:00. Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/city_test.mjs   (SHOTS=dir saves screenshots)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
import {secondsAt, DAY_S} from "../shared/city.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const there = REGISTRY.linkFrom("parking_lot", "bus_stop"), back = REGISTRY.linkFrom("street", "bus_stop");
check("the manifest has the bus there and back, solo only", !!there && !!back && there.soloOnly && back.soloOnly && there.to.scene === "street" && back.to.scene === "parking_lot");
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage(); page.on("pageerror", e => errors.push(e.message));
await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
const st = () => page.evaluate(() => { const g = window.__game, s = g.cityState(); return {...s, clockText: document.getElementById("clock").firstChild.textContent, sub: document.getElementById("clock").lastChild.textContent, shown: getComputedStyle(document.getElementById("clock")).display}; });
const shots = process.env.SHOTS, shot = n => shots && page.screenshot({path: `${shots}/${n}.png`});
const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
const stand = (x, y, z, yaw = 0) => page.evaluate(([x, y, z, yaw]) => { const g = window.__game; g.P.p.set(x, y, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, y, z, yaw]);
const closedDoors = () => page.evaluate(() => window.__game.CITY.doors.filter(c => c.shutter.visible).map(c => c.d.id));
try {
  // the clock is not running outside the City
  await page.evaluate(() => window.__game.loadScene("parking_lot")); await settled("parking_lot");
  await frames(40);
  await page.evaluate(() => window.__game.closeOptions());                 // the first spawn can be at the store doors, which opens the Original/Going back in screen
  check("before the bus the City's clock has not started and is not on screen", await page.evaluate(() => window.__game.CITY.t === 0 && getComputedStyle(document.getElementById("clock")).display === "none"));

  // the bus stop in the lot: stand by the shelter, the prompt shows, F rides
  await stand(-41, 9.62, 43, 0); await frames(10);
  check("by the shelter in the lot you are offered the bus", /bus to Hallam Row/.test(await prompt()), await prompt());
  await stand(0, 9.62, 33, 0); await frames(5);
  check("away from the shelter you are not", !/bus/.test(await prompt()));
  await stand(-41, 9.62, 43, 0); await frames(5);
  await page.evaluate(() => window.__game.openOptions());                  // the store-doors screen is up as you ride: it must not follow you
  await page.keyboard.press("KeyF"); await settled("street");
  const at = await page.evaluate(() => { const g = window.__game; return {p: g.P.p.toArray(), yaw: g.P.yaw}; });
  await frames(10);
  const land = await page.evaluate(() => { const g = window.__game; return {y: g.P.p.y, ground: g.P.ground, monsters: g.monsters.length}; });
  check("the bus brings you to Hallam Row at the bus stop, facing up the street, on the ground", Math.abs(at.p[0] - there.to.arrive[0]) < 0.01 && Math.abs(at.p[2] - there.to.arrive[2]) < 0.01 && Math.abs(at.yaw) < 0.01 && land.ground && Math.abs(land.y) < 0.05 && land.monsters === 0, JSON.stringify({at, land}));

  // the clock: starts at 08:00 on day 1 and advances; a game day is 15 real minutes
  let s = await st();
  check("the store-doors screen does not follow you onto the street", await page.evaluate(() => !window.__game.OW.open && getComputedStyle(document.getElementById("options")).display === "none"));
  check("the clock starts at 08:00 on day 1, with stores open", s.clockText === "08:00" && s.day === 1 && s.open && s.shown === "block" && /STORES OPEN/.test(s.sub), JSON.stringify(s));
  const t0 = s.t; await frames(400);            // 20 s of play
  s = await st();
  check("20 s later it is about 08:32 (24 hours pass in 15 minutes)", Math.abs((s.t - t0) - 20) < 1 && Math.abs(s.hour - (8 + s.t / 900 * 24)) < 1e-9 && s.hour > 8.5 && s.hour < 8.56 && /^08:3[23]$/.test(s.clockText), JSON.stringify(s));
  check("by day the sky is bright and no shutter is down", (await closedDoors()).length === 0);
  await page.evaluate(() => { window.__game.CITY.t = 4 * 37.5 + 1; }); await frames(6);                  // 12:00
  const noon = await page.evaluate(() => ({light: window.__game.HEMI.intensity, bg: window.__game.S && window.__game.HEMI.color.getHex()}));
  await shot("street_noon");

  // leaving pauses it
  await stand(3.6, 0.02, 4.0, 0); await frames(5);
  check("by the bus stop on the street you are offered the ride back", /bus back/.test(await prompt()), await prompt());
  const tAway = (await st()).t;
  await page.keyboard.press("KeyF"); await settled("parking_lot");
  const tIn = await page.evaluate(() => window.__game.CITY.t); await frames(200);
  check("the clock is paused while you are away (10 s of play, no time passes), and the lot has its own light back", await page.evaluate(t => window.__game.CITY.t === t && getComputedStyle(document.getElementById("clock")).display === "none" && window.__game.HEMI.intensity === 1.25, tIn) && Math.abs(tIn - tAway) < 1);
  const lotP = await page.evaluate(() => { const g = window.__game; return {p: g.P.p.toArray(), ground: g.P.ground}; });
  check("the ride back leaves you at the lot's bus stop", Math.abs(lotP.p[0] - back.to.arrive[0]) < 0.01 && Math.abs(lotP.p[2] - back.to.arrive[2]) < 0.01, JSON.stringify(lotP));
  await frames(5); await page.keyboard.press("KeyF"); await settled("street");
  check("riding again resumes the clock where it stopped", Math.abs((await st()).t - tIn) < 1);

  // the street is solid and has doors
  const solid = await page.evaluate(() => { const g = window.__game, c = (x, z) => !!g.collide({x, y: 0.02, z}); return {tower: c(-15, -19), grocery: c(15, -17), road: c(0, -30), sidewalk: c(6.5, -30), edge: c(61, -20)}; });
  check("buildings and the edge of the world are solid; road and sidewalk are clear", solid.tower && solid.grocery && solid.edge && !solid.road && !solid.sidewalk, JSON.stringify(solid));

  // the night rule, first half: at 20:00 the stores close
  await stand(6.4, 0.02, -41, -Math.PI / 2);
  await page.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(19.97)]); await frames(10);
  s = await st();
  check("at 19:58 the stores are open and a door tells you what is behind it", s.open && /^19:5/.test(s.clockText) && (await closedDoors()).length === 0 && /108 HALLAM ROW: press F/.test(await prompt()), JSON.stringify(s) + await prompt());
  await frames(40);                              // 2 s: past 20:00
  s = await st();
  const shut = await closedDoors();
  check("at 20:00 the stores close: shutters down, clock says so, doors refuse", !s.open && s.phase === "evening" && /STORES CLOSED/.test(s.sub) && shut.length === 7 && !shut.includes("tower"), JSON.stringify({s, shut}));
  check("the closed door says closed, and F gives the reason", /closed/.test(await prompt()) && (await (async () => { await page.keyboard.press("KeyF"); return page.evaluate(() => document.getElementById("toast").textContent); })()).includes("closed"));
  const dusk = await page.evaluate(() => window.__game.HEMI.intensity);
  await page.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(23)]); await frames(10); await shot("street_night");
  const late = await page.evaluate(() => ({light: window.__game.HEMI.intensity, sub: document.getElementById("clock").lastChild.textContent}));
  check("by night the sky is dark, the apartment tower stays open and the stores stay shut", noon.light > late.light * 4 && dusk < noon.light && /STORES CLOSED/.test(late.sub), JSON.stringify({noon, dusk, late}));
  await page.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(9.02, 2)]); await frames(10);
  check("the next morning at 09:00 they open again, on day 2", (await closedDoors()).length === 0 && (await st()).day === 2, JSON.stringify(await st()));
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
