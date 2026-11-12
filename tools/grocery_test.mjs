// The City's needs and the grocery (slice 4): hunger drains with the City's clock and waits outside it, warns, and makes you faint at 0; the grocery is open by day behind the
// street's door; you take a cart, put food in it, pay at the checkout, and eat it from the fridge at home; leaving without paying puts it back; at 20:00 you are shown out;
// sleep drains hunger at half rate; a shift at the Intern pays; the computer's bank page shows it. Needs Playwright + Chromium and internet for three.js from unpkg.
// Usage: node tools/grocery_test.mjs   (SHOTS=dir saves screenshots)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
import {secondsAt, APARTMENT, GROCERY, GROCERY_FRONT, bedUse} from "../shared/city.js";
import {HUNGER, MONEY} from "../shared/needs.js";
import {shiftPay} from "../shared/pay.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const into = REGISTRY.linkFrom("street", "grocery"), out = REGISTRY.linkFrom("main_floor", "front_door");
check("the manifest has the grocery door there and back, solo only", !!into && !!out && into.soloOnly && out.soloOnly && into.to.scene === "main_floor" && out.to.scene === "street");
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const ctx = await browser.newContext({viewport: {width: 900, height: 700}});
const shots = process.env.SHOTS;
try {
  const page = await ctx.newPage(); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const stand = (x, z, yaw = 0) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const needs = () => page.evaluate(() => JSON.parse(JSON.stringify(window.__game.NEEDS)));
  const setNeeds = v => page.evaluate(v => { window.__game.NEEDS = {...window.__game.NEEDS, ...v}; }, v);
  const setT = (h, day = 1) => page.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(h, day)]);
  const press = async () => { await page.keyboard.press("KeyF"); await frames(2); };
  const hud = () => page.evaluate(() => ({shown: getComputedStyle(document.getElementById("needs")).display, text: document.getElementById("needs").textContent}));

  // hunger: it starts at 80 with $20, is on screen in the City, drains with the clock, and waits outside it
  await page.evaluate(() => window.__game.loadScene("street", {pos: [6.2, 0, -17], face: [-1, 0]})); await settled("street"); await setT(10); await frames(5);
  let n = await needs(), h = await hud();
  check("in the City: hunger 80 and $20 are on screen", n.hunger <= 80 && n.hunger > 79.5 && n.money === MONEY.start && h.shown === "block" && /HUNGER 80 · \$20/.test(h.text), JSON.stringify({n, h}));
  const h0 = n.hunger; await frames(400);                                   // 20 s of play = 0.533 game hours
  n = await needs();
  check("20 s in the City drains hunger by about 1.5 (36 game hours from full to empty)", Math.abs((h0 - n.hunger) - 20 * 24 / 900 * HUNGER.perHour) < 0.2, `${h0} -> ${n.hunger}`);
  await page.evaluate(() => window.__game.loadScene("parking_lot")); await settled("parking_lot"); await page.evaluate(() => window.__game.closeOptions());
  const hOut = (await needs()).hunger; await frames(200);
  check("outside the City hunger waits, and it is not on screen", (await needs()).hunger === hOut && (await hud()).shown === "none");

  // the grocery: by day the door takes you in
  await page.evaluate(() => window.__game.loadScene("street", {pos: [6.2, 0, -17], face: [-1, 0]})); await settled("street"); await setT(10); await frames(5);
  check("at the grocery door by day you are offered the way in", /go into the grocery/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await settled("main_floor"); await frames(10);
  const inside = await page.evaluate(() => { const g = window.__game; return {p: g.P.p.toArray(), ground: g.P.ground, monsters: g.monsters.length, clock: getComputedStyle(document.getElementById("clock")).display}; });
  check("you arrive inside the grocery, on the floor, and the City's clock still shows", Math.abs(inside.p[0] - GROCERY.arrive[0]) < 0.01 && Math.abs(inside.p[2] - GROCERY.arrive[2]) < 0.01 && inside.ground && inside.monsters === 0 && inside.clock === "block", JSON.stringify(inside));
  const solid = await page.evaluate(([sh, co]) => { const g = window.__game, c = (x, z) => !!g.collide({x, y: 0.02, z}); return {shelf: c(sh[0], sh[1]), checkout: c(co[0], co[1]), aisle: c(-5.5, -2), wall: c(12.1, 0)}; }, [[GROCERY.shelves[0].min[0] + 0.6, -2], [7.5, 6.8]]);
  check("the shelves, the checkout and the walls are solid; the aisles are clear", solid.shelf && solid.checkout && solid.wall && !solid.aisle, JSON.stringify(solid));
  if (shots) { await new Promise(r => setTimeout(r, 400)); await page.screenshot({path: `${shots}/grocery.png`}); }

  // two items in your hands; a third needs a cart
  const shelf = id => GROCERY.shelves.find(s => s.food === id).at;
  await stand(...shelf("bread")); await frames(3);
  check("by a shelf you are offered its food and its price", /take Bread \(\$2\)/.test(await prompt()), await prompt());
  await press(); await press(); await press();
  n = await needs();
  check("without a cart you carry 2; the third asks you to take a cart", n.cart.length === 2 && /Take a cart/.test(await toast()), JSON.stringify(n.cart) + " " + await toast());
  await stand(...GROCERY.cart.at); await frames(3);
  check("by the corral you are offered a cart", /take a cart/.test(await prompt()));
  await press();
  await stand(...shelf("meal")); await frames(3); await press(); await press();
  await stand(...shelf("soup")); await frames(3); await press();
  n = await needs(); h = await hud();
  check("with a cart you carry more; the screen shows the cart and its total", n.hasCart && n.cart.length === 5 && /CART 5\/8 \$19/.test(h.text), JSON.stringify(n) + " " + h.text);

  // too little money: nothing changes. Enough: it is paid and goes home.
  await stand(...GROCERY.checkout.at); await frames(3);
  check("at the checkout you are told the total", /pay: \$19 for 5 items/.test(await prompt()), await prompt());
  await setNeeds({money: 10}); await press();
  n = await needs();
  check("$19 with $10: refused, nothing paid, the cart is still full", /\$19.*\$10/.test(await toast()) && n.money === 10 && n.cart.length === 5, await toast());
  await setNeeds({money: 20}); await press();
  n = await needs();
  check("with $20: you pay $19, the cart is empty and the food is in your pantry", n.money === 1 && n.cart.length === 0 && !n.hasCart && n.pantry.bread === 2 && n.pantry.meal === 2 && n.pantry.soup === 1 && /pay \$19/.test(await toast()), JSON.stringify(n));

  // leaving with unpaid items puts them back
  await stand(...shelf("apple")); await frames(3); await press();
  check("one more item in your hands", (await needs()).cart.length === 1);
  await stand(...GROCERY.door.at); await frames(3);
  check("by the door you are offered the way out", /leave/.test(await prompt()));
  await page.keyboard.press("KeyF"); await settled("street"); await frames(5);
  const outP = await page.evaluate(() => window.__game.P.p.toArray());
  n = await needs();
  check("you come out at the grocery door; what you did not pay for went back", Math.abs(outP[0] - GROCERY_FRONT.arrive[0]) < 0.01 && Math.abs(outP[2] - GROCERY_FRONT.arrive[2]) < 0.01 && n.cart.length === 0 && n.money === 1 && /put back/.test(await toast()), JSON.stringify({outP, n}));

  // closing time: shown out at 20:00, and the door is shut
  await page.keyboard.press("KeyF"); await settled("main_floor"); await setT(19.98); await frames(3);
  await stand(...shelf("apple")); await frames(2); await press();
  await frames(40);                                                        // 2 s: past 20:00
  await settled("street"); await frames(3);
  n = await needs();
  check("at 20:00 you are shown out, and the unpaid apple goes back", (await page.evaluate(() => window.__game.S.id)) === "street" && n.cart.length === 0 && /closing/.test(await toast()), await toast());
  await stand(6.2, -17, -Math.PI / 2); await frames(3);
  check("after 20:00 the grocery door is closed", /GROCERY: closed/.test(await prompt()), await prompt());
  await press();
  check("and F does not take you in", (await page.evaluate(() => window.__game.S.id)) === "street");

  // home: eat from the fridge
  await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await settled("apartment"); await setT(12, 2); await frames(5);
  await setNeeds({hunger: 20}); await stand(...APARTMENT.fridge.at); await frames(3);
  check("by the fridge you are offered something to eat", /eat from the fridge/.test(await prompt()), await prompt());
  await press();
  n = await needs();
  check("you eat the most filling thing you have: a ready meal (+60)", Math.abs(n.hunger - 80) < 0.5 && n.pantry.meal === 1 && /Ready meal/.test(await toast()), JSON.stringify(n));
  await setNeeds({hunger: 97}); await press();
  check("full: not hungry, nothing eaten", /not hungry/.test(await toast()) && (await needs()).pantry.meal === 1);
  await setNeeds({hunger: 50, pantry: {}}); await press();
  check("an empty fridge says so", /fridge is empty/.test(await toast()));

  // warnings and fainting
  await setNeeds({hunger: HUNGER.warn + 0.005}); await frames(4);
  check("crossing 30: you are told you are hungry, and the number turns red", /You are hungry/.test(await toast()) && await page.evaluate(() => document.getElementById("needs").classList.contains("low")));
  await setNeeds({hunger: HUNGER.starve + 0.005}); await frames(4);
  check("crossing 10: starving", /starving/.test(await toast()));
  await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, -60], face: [0, -1]})); await settled("street"); await setT(14, 2); await frames(3);
  await setNeeds({hunger: 0.02}); await frames(4); await settled("apartment"); await frames(2);
  const woke = await page.evaluate(() => { const g = window.__game, s = g.cityState(); return {id: g.S.id, hour: s.hour, day: s.day, hunger: g.NEEDS.hunger}; });
  check("at 0 you faint and wake in your apartment at 06:00 the next day with hunger 25", woke.id === "apartment" && Math.abs(woke.hour - 6) < 0.05 && woke.day === 3 && Math.abs(woke.hunger - HUNGER.wakeAt) < 0.1 && /faint from hunger/.test(await toast()), JSON.stringify(woke));

  // sleep: half the drain, never below 5
  await setT(22, 3); await setNeeds({hunger: 50}); await stand(...bedUse.at); await frames(2); await press();
  n = await needs();
  check("a night's sleep (22:00 to 06:00, 8 game hours) costs about 11 hunger, half the waking rate", Math.abs((50 - n.hunger) - 8 * HUNGER.perHour * 0.5) < 0.3, `50 -> ${n.hunger}`);
  await setT(22, 4); await setNeeds({hunger: 7}); await press();
  check("you never sleep below 5 (the frames after the press drain a little)", Math.abs((await needs()).hunger - 5) < 0.05, String((await needs()).hunger));

  // the bank page
  await setNeeds({money: 1, lastPay: null, pantry: {bread: 2, soup: 1}}); await stand(...APARTMENT.computer.at); await frames(3); await press(); await page.keyboard.press("Digit5");
  let bank = await page.evaluate(() => ({title: document.getElementById("pc-title").textContent, body: document.getElementById("pc-body").textContent, tabs: document.querySelectorAll("#pc-tabs button").length}));
  check("key 5 is the bank: balance, no pay yet, and what is in the fridge", bank.title === "BANK" && bank.tabs === 6 && /Balance: \$1\n/.test(bank.body) && /No pay yet/.test(bank.body) && /Bread: 2/.test(bank.body) && /Canned soup: 1/.test(bank.body), bank.body);
  await page.keyboard.press("Escape");

  // a shift pays $10
  await page.evaluate(() => { localStorage.setItem("job_intern", "1"); window.__game.APP.st.accepted.intern = true; });
  await page.evaluate(() => window.__game.loadScene("street", {pos: [-6.2, 0, -127], face: [1, 0]})); await settled("street"); await setT(12, 5); await frames(3);
  await press(); await page.waitForSelector("#gamemount iframe", {timeout: 60000});
  await new Promise(r => setTimeout(r, 4000));                             // a shift lasts: end it after the game has loaded and taken focus, as a player would
  await page.evaluate(() => { const fr = document.querySelector("#gamemount iframe"); fr.contentWindow.eval("parent.postMessage({type: \"intern-ending\"}, \"*\")"); });
  await page.waitForFunction(() => !document.querySelector("#gamemount iframe") && !window.__game.loading && window.__game.S.id === "street", null, {timeout: 120000});
  await page.waitForFunction(() => window.__game.NEEDS.lastPay !== null, null, {timeout: 10000});
  n = await needs();
  const want = shiftPay(undefined).pay;                                    // this message carries no result (posted by hand, as an older game would): a PENDING shift
  check(`after a shift with no result you are paid the PENDING base ($${want})`, n.money === 1 + want && n.lastPay === want && n.lastNote === "PENDING" && new RegExp(`paid \\$${want}`).test(await toast()), JSON.stringify(n) + " " + await toast());
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
