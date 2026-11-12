// Stealing and the camera (slice 19): the grocery's camera sweeps to and fro; walking out of the door with unpaid goods while it is turned away keeps them (they go to your
// fridge), while it is on you costs a fine of $5 plus their price, and they go back. Paying first, nothing happens.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/theft_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, GROCERY, camYaw, nextCam, camSees} from "../shared/city.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const page = await browser.newPage({viewport: {width: 900, height: 700}}); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const stand = (x, z, yaw = 0) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const needs = () => page.evaluate(() => JSON.parse(JSON.stringify(window.__game.NEEDS)));
  const shelf = food => GROCERY.shelves.find(s => s.food === food).at;
  const take = async food => { await stand(...shelf(food)); await frames(2); await page.keyboard.press("KeyF"); await frames(1); };
  const intoStore = async () => { await page.evaluate(() => window.__game.loadScene("main_floor", {pos: [0, 0, 7.4], face: [0, -1]})); await settled("main_floor"); await frames(2); };
  const camAt = t => page.evaluate(t => { window.__game.CITY.t = t; }, t);
  const atDoor = async () => { await stand(GROCERY.door.at[0], GROCERY.door.at[1], Math.PI); await frames(1); };
  const doorP = async () => { const p = await page.evaluate(() => window.__game.P.p.toArray()); return [p[0], p[2]]; };

  await intoStore(); await camAt(secondsAt(12, 2)); await page.evaluate(() => { const g = window.__game; g.NEEDS = {...g.NEEDS, money: 20, pantry: {}, cart: [], hasCart: false}; });
  // the camera sweeps
  await frames(1); const y0 = await page.evaluate(() => window.__game.CITY.mats.cam.rotation.y), t0 = await page.evaluate(() => window.__game.CITY.t);
  check("there is a camera, turned to where its sweep says", Math.abs(y0 - camYaw(t0) * Math.PI / 180) < 1e-6, String([y0, t0]));
  await frames(40); const y1 = await page.evaluate(() => window.__game.CITY.mats.cam.rotation.y);
  check("and it moves: two seconds later it points somewhere else", Math.abs(y1 - y0) > 0.05, String([y0, y1]));

  // unseen: you keep it
  await take("apple"); await take("bread"); let n = await needs();
  check("two items in your hands, unpaid", n.cart.length === 2 && n.money === 20, JSON.stringify(n.cart));
  await atDoor();
  check("at the door you are reminded you have not paid", /not paid for 2 items/.test(await prompt()), await prompt());
  { const [x, z] = await doorP(), t = await page.evaluate(() => window.__game.CITY.t), u = nextCam(t, x, z, false); await camAt(u); check("(the camera is turned away)", !camSees(u, x, z)); }
  await page.keyboard.press("KeyF"); await settled("street"); await frames(2); n = await needs();
  check("unseen: out on the street with them, no fine, and they are in your fridge", n.money === 20 && n.pantry.apple === 1 && n.pantry.bread === 1 && n.cart.length === 0 && /Nobody stopped you/.test(await toast()), JSON.stringify(n));

  // seen: fined and they go back
  await intoStore(); await take("meal"); await atDoor();
  { const [x, z] = await doorP(), t = await page.evaluate(() => window.__game.CITY.t), u = nextCam(t, x, z, true); await camAt(u); check("(the camera is on you)", camSees(u, x, z)); }
  await page.keyboard.press("KeyF"); await settled("street"); await frames(2); n = await needs();
  check("seen: fined $5 plus the meal's $6, and it went back", n.money === 9 && !n.pantry.meal && n.pantry.apple === 1 && n.cart.length === 0 && /camera saw you\. You are fined \$11/.test(await toast()), JSON.stringify(n));

  // paying first: nothing to see
  await intoStore(); await take("apple"); await stand(GROCERY.checkout.at[0], GROCERY.checkout.at[1]); await frames(2); await page.keyboard.press("KeyF"); await frames(1);
  await atDoor();
  check("paid: the door just says leave", (await prompt()) === "Press F to leave", await prompt());
  { const [x, z] = await doorP(), t = await page.evaluate(() => window.__game.CITY.t); await camAt(nextCam(t, x, z, true)); }
  await page.keyboard.press("KeyF"); await settled("street"); await frames(2); n = await needs();
  check("and leaving under the camera costs nothing more", n.money === 8 && n.pantry.apple === 2 && !/camera/.test(await toast()), JSON.stringify(n));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
