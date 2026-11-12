// Pay by performance (City slice 5): a shift at the Intern pays by how it went. This drives the real game: inside its window it sets the game's own state and ends the
// shift through the game's director (jumpToEnding, bail), so the "intern-ending" message and its result come from games/intern/src/main.js, not from the test.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/pay_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, APARTMENT} from "../shared/city.js";
import {shiftPay} from "../shared/pay.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage(); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const needs = () => page.evaluate(() => JSON.parse(JSON.stringify(window.__game.NEEDS)));
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  await page.evaluate(() => { localStorage.setItem("job_intern", "1"); window.__game.APP.st.accepted.intern = true; });

  // one shift: in through 666's door, set the game's state inside its window, end it with the game's own director, and wait to be back on the street
  async function shift(setup) {
    await page.evaluate(() => window.__game.loadScene("street", {pos: [-6.2, 0, -127], face: [1, 0]})); await settled("street");
    await page.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(12, 1)]); await frames(3);
    const before = await needs();
    await page.keyboard.press("KeyF");
    await page.waitForSelector("#gamemount iframe", {timeout: 60000});
    await page.waitForFunction(() => { const fr = document.querySelector("#gamemount iframe"); return fr && fr.contentWindow && fr.contentWindow.__NINETY_NINE__; }, null, {timeout: 120000});
    await new Promise(r => setTimeout(r, 2500));                                 // the game has loaded and taken focus, as in a real shift
    await page.evaluate(setup => { const fr = document.querySelector("#gamemount iframe"); fr.contentWindow.eval(setup); }, setup);
    await page.waitForFunction(() => !document.querySelector("#gamemount iframe") && !window.__game.loading && window.__game.S.id === "street", null, {timeout: 120000});   // the game waits 14 s on its ending card
    await page.waitForFunction(m => window.__game.NEEDS.money !== m || window.__game.NEEDS.lastPay !== null, before.money, {timeout: 10000});
    return {before, after: await needs(), toast: await toast()};
  }

  // a good shift: assimilation, conformance 6, friction 1.6 -> $20 + $6 - $2
  let r = await shift("const N = window.__NINETY_NINE__; N.state.conformance = 6; N.state.dissonance = 1; N.state.friction = 1.6; N.director.jumpToEnding('ASSIMILATION');");
  let want = shiftPay({ending: "ASSIMILATION", conformance: 6, friction: 1.6}).pay;
  check(`an assimilated shift with conformance 6 and friction 1.6 pays $${want}`, want === 24 && r.after.money === r.before.money + want && r.after.lastPay === want && r.after.lastNote === "ASSIMILATION" && /ASSIMILATION.*paid \$24/.test(r.toast), JSON.stringify({r}));

  // expelled with friction: $4 base, nothing for negative conformance, -$3 friction
  r = await shift("const N = window.__NINETY_NINE__; N.state.conformance = -6; N.state.friction = 3.2; N.director.jumpToEnding('EXPULSION');");
  want = shiftPay({ending: "EXPULSION", conformance: -6, friction: 3.2}).pay;
  check(`an expelled shift with friction 3.2 pays $${want}`, want === 1 && r.after.money === r.before.money + want && r.after.lastNote === "EXPULSION", JSON.stringify({r}));

  // quitting: the game's own bail (EARLY_EXIT) pays nothing
  r = await shift("const N = window.__NINETY_NINE__; N.state.conformance = 4; N.director.bail();");
  check("quitting a shift with the game's bail pays $0, and still counts as a shift", r.after.money === r.before.money && r.after.lastPay === 0 && r.after.lastNote === "PENDING" && /paid \$0/.test(r.toast), JSON.stringify({r}));

  // the bank page shows the last shift and its ending
  await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await settled("apartment");
  await page.evaluate(([x, z]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); }, APARTMENT.computer.at); await frames(3);
  await page.keyboard.press("KeyF"); await page.keyboard.press("Digit5");
  const bank = await page.evaluate(() => document.getElementById("pc-body").textContent);
  check("the bank page shows the balance and the last shift: +$0 (PENDING)", /Balance: \$45\n/.test(bank) && /Last shift: \+\$0 \(PENDING\)/.test(bank), bank);
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
