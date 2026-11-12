// Reporting the anomalies (slice 15): you spot an anomaly by seeing it yourself on the street; the computer's REPORT page lists six reports, three real and three not.
// A true report of something you have spotted pays $5 once; anything else is a false report and costs $2. What you have spotted and reported is saved; New Game clears it.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/report_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, APARTMENT, sideX} from "../shared/city.js";
import {SIGN, GHOST_WINDOW, REPORTS} from "../shared/anomalies.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
try {
  const page = await browser.newPage({viewport: {width: 900, height: 700}}); page.on("pageerror", e => errors.push(e.message));
  const boot = async () => { await page.click("#l-solo"); await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000}); };
  await page.goto(`http://localhost:${srv.port}/`); await boot();
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const stand = (x, z, yaw = 0) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, z, yaw]);
  const face = (fx, fz, tx, tz) => Math.atan2(-(tx - fx), -(tz - fz));
  const setT = (h, d = 2) => page.evaluate(t => { window.__game.CITY.t = t; }, secondsAt(h, d));
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const seen = () => page.evaluate(() => JSON.parse(JSON.stringify(window.__game.CITY.seen)));
  const money = () => page.evaluate(() => window.__game.NEEDS.money);
  const street = async () => { await page.evaluate(() => window.__game.loadScene("street", {pos: [0, 0, 5], face: [0, -1]})); await settled("street"); };
  const reportPage = async () => {
    await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await settled("apartment");
    await page.evaluate(([x, z]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); }, APARTMENT.computer.at); await frames(3);
    await page.keyboard.press("KeyF"); await page.keyboard.press("Digit6");
    return page.evaluate(() => ({title: document.getElementById("pc-title").textContent, body: document.getElementById("pc-body").textContent, tabs: document.querySelectorAll("#pc-tabs button").length,
      btns: [...document.querySelectorAll("#pc-actions button")].map(b => ({id: b.dataset.report, off: b.disabled, text: b.textContent}))}));
  };
  const body = () => page.evaluate(() => document.getElementById("pc-body").textContent);
  const file = async id => { await page.click(`#pc-actions button[data-report="${id}"]`); return body(); };

  await page.evaluate(() => { const g = window.__game; g.NEEDS = {...g.NEEDS, money: 20}; });
  let r = await reportPage();
  check("key 6 is the REPORT page: seven tabs, six reports, none filed", r.title === "REPORT" && r.tabs === 7 && r.btns.length === REPORTS.length && r.btns.every(b => !b.off) && /\$5/.test(r.body) && /Reports filed: 0/.test(r.body), JSON.stringify(r));
  let b = await file("sign");
  check("reporting a real anomaly you have not seen yourself costs $2", /not seen that yourself/.test(b) && await money() === 18, b);
  b = await file("lamp");
  check("reporting something that is not real costs $2", /nothing like that/.test(b) && await money() === 16, b);
  await page.keyboard.press("Escape");

  // spot the pedestrians: by day, from the bus stop, looking up the street
  await street(); await setT(12); await stand(0, 5, 0); await frames(20);
  check("by day, two pedestrians in view facing the same way: spotted, and you notice it", (await seen()).spotted.peds && /all facing the same way/.test(await toast()), JSON.stringify(await seen()));
  // the sign: not before it has changed; after you pass it and look at it, yes
  const sx = sideX(SIGN.side);
  await stand(0, SIGN.z + 8, face(0, SIGN.z + 8, sx, SIGN.z)); await frames(20);
  check("looking at the sign before it has changed is not spotting it", !(await seen()).spotted.sign);
  await stand(-3, SIGN.z + 2, 0); await frames(2); await stand(-3, SIGN.z - 2, 0); await frames(2);
  await stand(0, SIGN.z - 8, face(0, SIGN.z - 8, sx, SIGN.z)); await frames(20);
  check("after it changed as you passed, looking at it spots it", (await seen()).spotted.sign && /sign just change/.test(await toast()), JSON.stringify(await seen()));
  // the window: only at night
  const [wx, , wz] = GHOST_WINDOW.at; await stand(0, -100, face(0, -100, wx, wz)); await frames(20);
  check("by day there is no window to spot", !(await seen()).spotted.window);
  await setT(22); await page.evaluate(() => { window.__game.CITY.ui = 0; }); await frames(20);
  check("at 22:00 looking at it spots it", (await seen()).spotted.window && /no building/.test(await toast()), JSON.stringify(await seen()));

  // report them
  r = await reportPage();
  b = await file("peds");
  check("a true report of a spotted anomaly pays $5", /Report filed/.test(b) && await money() === 21, b);
  r = await page.evaluate(() => [...document.querySelectorAll("#pc-actions button")].map(b => ({id: b.dataset.report, off: b.disabled, text: b.textContent})));
  check("its button now says Reported and is shut", r.find(x => x.id === "peds").off && /^Reported:/.test(r.find(x => x.id === "peds").text) && /Reports filed: 1/.test(await body()), JSON.stringify(r));
  b = await file("bus");
  check("a false report still costs $2 after a true one", /nothing like that/.test(b) && await money() === 19, b);
  b = await file("window");
  check("the window: filed, $5", /Report filed/.test(b) && await money() === 24 && /Reports filed: 2/.test(await body()), b);
  await page.keyboard.press("Escape");

  // saved and read back
  await page.evaluate(() => window.__game.saveCity());
  await page.reload(); await boot();
  const s2 = await seen();
  check("a reload keeps what you spotted and reported", s2.spotted.peds && s2.spotted.sign && s2.spotted.window && s2.reported.peds && s2.reported.window && !s2.reported.sign, JSON.stringify(s2));
  r = await reportPage();
  check("and the REPORT page still shows them filed", r.btns.filter(x => x.off).map(x => x.id).sort().join() === "peds,window" && /Reports filed: 2/.test(r.body), JSON.stringify(r.btns));
  b = await file("sign");
  check("the sign, spotted before the reload, can still be reported for $5", /Report filed/.test(b), b);

  // New Game forgets it
  await page.keyboard.press("Digit7"); await page.click('#pc-actions button[data-act="newgame"]'); await page.click('#pc-actions button[data-act="newgame-yes"]'); await frames(2);
  const s3 = await seen();
  check("New Game forgets what you spotted and reported", Object.keys(s3.spotted).length === 0 && Object.keys(s3.reported).length === 0, JSON.stringify(s3));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("FAIL crashed: " + (e && e.stack || e)); failed++; }
finally { await browser.close(); await srv.close(); }
console.log(failed ? `${failed} FAILED` : "ALL PASSED");
process.exit(failed ? 1 : 0);
