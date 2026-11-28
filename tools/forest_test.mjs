// The dreamcore forest and meadow (shared/forest.js), solo, plus one room check. From the parking lot's signpost (F) down the road into the forest; the path's gap into the
// meadow; the shed and the house drawn with the owner's models (models/world/); the house's door into Right Door, Wrong Exit and back out in front of it; the shed locked;
// back through the gap and up the road to the lot. In a room the house does not open and says so. Needs Playwright + Chromium and internet for three.js from unpkg.
// Usage: node tools/forest_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {FOREST, MEADOW, FOREST_ROAD_LOT} from "../shared/forest.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const wait = (page, fn, arg, ms = 60000) => page.waitForFunction(fn, arg, {timeout: ms, polling: 100}).then(() => true, () => false);
const settled = (page, id) => wait(page, i => window.__game.S.id === i && !window.__game.loading, id, 180000);
const where = page => page.evaluate(() => { const g = window.__game; return {id: g.S.id, p: g.P.p.toArray().map(v => +v.toFixed(2)), yaw: +g.P.yaw.toFixed(2)}; });
const near = (p, a, d = 1.2) => Math.hypot(p[0] - a[0], p[2] - a[2]) < d;
// press F where you stand (the same action the key runs)
const pressF = page => page.evaluate(() => window.__game.doAction());
const at = (page, x, y, z) => page.evaluate(([x, y, z]) => { const g = window.__game; g.teleport([x, y, z]); g.P.v.set(0, 0, 0); }, [x, y, z]);
const prompt = page => page.evaluate(() => window.__game.cityPrompt());
try {
  const page = await (await browser.newContext({viewport: {width: 640, height: 400}})).newPage(); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});

  // the parking lot: the signpost by the north-west hedge
  await page.evaluate(() => window.__game.loadScene("parking_lot", {pos: [-8, 9.6, 43.6]})); await settled(page, "parking_lot");
  check("away from the signpost the lot offers no road", !/forest/.test(await prompt(page)));
  await at(page, FOREST_ROAD_LOT.at[0], 9.6, FOREST_ROAD_LOT.at[1]);
  check("at the signpost: F walks down the road", /walk down the road/.test(await prompt(page)), await prompt(page));
  // since #115 the signpost leads onto the Overworld's road; its far end walks into the forest
  await pressF(page); check("the signpost leads onto the road", await settled(page, "road"));
  const roadEnd = (await page.evaluate(() => fetch("world/road.json").then(r => r.json()))).links.find(l => l.door === "forest");
  await at(page, roadEnd.at[0], 0, roadEnd.at[2] + 4); await page.waitForTimeout(200); await at(page, roadEnd.at[0], 0, roadEnd.at[2]);
  check("the road's far end leads into the forest", await settled(page, "forest"));
  let w = await where(page);
  check("you arrive at the road's end, facing up the path", near(w.p, FOREST.arrive) && Math.abs(w.yaw) < 0.05, JSON.stringify(w));
  check("the forest has its trees and the pastel haze", await page.evaluate(() => { const g = window.__game; let n = 0; g.S.root.traverse(o => { if (o.isInstancedMesh) n += o.count; }); return n > 400 && g.FST.hazy(); }));

  // up the path to the gap: walking through it takes you into the meadow
  await at(page, 0, 0, -80); await page.waitForTimeout(400);
  check("short of the gap you stay in the forest", (await where(page)).id === "forest");
  await at(page, 0, 0, FOREST.gap.z - 1);
  check("walking through the gap takes you into the meadow", await settled(page, "meadow"));
  w = await where(page); check("you come out of the trees on the meadow's path", near(w.p, MEADOW.arrive), JSON.stringify(w));
  check("the shed and the house are the owner's models", await wait(page, () => !!window.__game.FST.shed && !!window.__game.FST.house, null, 30000));
  const heights = await page.evaluate(() => { const f = window.__game.FST; return {shed: +f.heightOf(f.shed).toFixed(2), house: +f.heightOf(f.house).toFixed(2)}; });
  check("they stand at their sizes (shed about 6.2 m, house about 7.5 m)", Math.abs(heights.shed - MEADOW.shed.height) < 0.2 && Math.abs(heights.house - MEADOW.house.height) < 0.2, JSON.stringify(heights));

  // the shed is locked
  await at(page, ...[MEADOW.shed.door.at[0], 0, MEADOW.shed.door.at[1]]);
  check("the shed says it is locked", /shed is locked/.test(await prompt(page)), await prompt(page));
  await pressF(page); check("and F there takes you nowhere", (await where(page)).id === "meadow");

  // the house's door: Right Door, Wrong Exit, then back out in front of the house
  await at(page, MEADOW.house.door.at[0], 0, MEADOW.house.door.at[1]);
  check("at the house: F opens the door", /open the door/.test(await prompt(page)), await prompt(page));
  await pressF(page);
  check("the door takes you into Right Door, Wrong Exit", await wait(page, () => document.getElementById("gamemount").style.display === "block"));
  await new Promise(r => setTimeout(r, 4000)); await page.evaluate(async () => (await import("./games/rdwe/walk.js")).cancel());
  check("and you come back to the meadow", await wait(page, () => window.__game.S.id === "meadow" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000));
  w = await where(page); check("in front of the house, facing away from it", near(w.p, MEADOW.returnHouse.arrive) && Math.abs(Math.abs(w.yaw) - Math.PI) < 0.05, JSON.stringify(w));

  // back south through the meadow's gap into the forest, and down the road to the lot
  await at(page, 0, 0, MEADOW.gap.z + 1);
  check("walking back south takes you into the forest", await settled(page, "forest"));
  w = await where(page); check("at the path's north end, facing back down it", near(w.p, FOREST.fromMeadow.arrive) && Math.abs(Math.abs(w.yaw) - Math.PI) < 0.05, JSON.stringify(w));
  await at(page, FOREST.back.at[0], 0, FOREST.back.at[1]);
  check("the signpost at the road's end walks you back", /back down the road/.test(await prompt(page)), await prompt(page));
  await pressF(page); check("onto the road, at its forest end", await settled(page, "road"));
  w = await where(page); check("where the road meets the forest", near(w.p, roadEnd.arrive), JSON.stringify(w));
  const roadHome = (await page.evaluate(() => fetch("world/road.json").then(r => r.json()))).links.find(l => l.door === "lot");
  await at(page, roadHome.at[0], 0, roadHome.at[2] - 4); await page.waitForTimeout(200); await at(page, roadHome.at[0], 0, roadHome.at[2]);
  check("the road's lot end walks you to the parking lot", await settled(page, "parking_lot"));
  w = await where(page); check("beside the signpost you left by", near(w.p, [FOREST_ROAD_LOT.at[0], 0, FOREST_ROAD_LOT.at[1]], FOREST_ROAD_LOT.reach + 1), JSON.stringify(w));
  check("the lot has its own sky again (no forest haze)", await page.evaluate(() => !window.__game.FST.hazy()));

  // in a room the house does not open, and says so
  const room = await (await browser.newContext({viewport: {width: 320, height: 200}})).newPage(); room.on("pageerror", e => errors.push("[room] " + e.message));
  await room.goto(`http://localhost:${srv.port}/?room=FOREST&name=Ann&char=0&auto=1&ready=1`);
  await room.waitForFunction(() => window.__game && !document.getElementById("load") && window.__game.net.phase === "playing", null, {timeout: 240000});
  await room.evaluate(() => window.__game.loadScene("meadow", {pos: [0, 0, 6]})); await settled(room, "meadow");
  await room.evaluate(([x, z]) => { window.__game.teleport([x, 0, z]); }, MEADOW.house.door.at);
  // since #133 a room can follow the house's door into Right Door, Wrong Exit (the owner, 2026-11-27: the meadow house is the co-op way in)
  check("in a room the house's door opens too", /Press F to open the door/.test(await prompt(room)), await prompt(room));
  await pressF(room);
  check("and F there takes you into the game", await room.waitForFunction(() => document.getElementById("gamemount").style.display === "block", null, {timeout: 90000}).then(() => true, () => false));
  check("no page errors", errors.length === 0, errors.slice(0, 3).join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
