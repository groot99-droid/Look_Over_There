// The Intern's job (City slice 3): apply on the apartment computer through the application quiz; a wrong answer is a rejection that waits until tomorrow; right answers are an acceptance
// that sets job_intern; with it, the door of 666 Hallam Row starts a shift (the Intern game) and you come back out to the street. Needs Playwright + Chromium and internet for three.js from unpkg.
// Usage: node tools/intern_job_test.mjs   (SHOTS=dir saves screenshots)
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {REGISTRY} from "../shared/registry.js";
import {requirementsMet} from "../shared/manifest.js";
import {secondsAt, APARTMENT, JOB_FRONT} from "../shared/city.js";
import {QUIZZES} from "../shared/application.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };
const link = REGISTRY.linkFrom("street", "w666");
check("the manifest has the shift link, shut until job_intern is held", !!link && link.status === "built" && !requirementsMet(link, []).ok && requirementsMet(link, ["job_intern"]).ok);
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const srv = await createServer({countdownMs: 60000}), errors = [];
const ctx = await browser.newContext({viewport: {width: 900, height: 700}});                  // one context: localStorage survives a reload, as for a player
async function solo() {
  const page = await ctx.newPage(); page.on("pageerror", e => errors.push(e.message));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  return page;
}
const shots = process.env.SHOTS;
try {
  const page = await solo();
  const settled = id => page.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  const frames = n => page.evaluate(n => { for (let i = 0; i < n; i++) window.__game.sim(0.05, i); }, n);
  const stand = (x, y, z, yaw = 0) => page.evaluate(([x, y, z, yaw]) => { const g = window.__game; g.P.p.set(x, y, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; g.P.pitch = 0; }, [x, y, z, yaw]);
  const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const setT = (h, day = 1) => page.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(h, day)]);
  const flag = () => page.evaluate(() => window.__game.heldFlags().includes("job_intern"));
  const qz = () => page.evaluate(() => ({open: window.__game.QZ.open, shown: getComputedStyle(document.getElementById("qz")).display, title: document.getElementById("qz-title").textContent, next: document.getElementById("qz-next").textContent, nextOff: document.getElementById("qz-next").disabled, tray: document.querySelectorAll("#qz-tray .chip").length, bins: document.querySelectorAll("#qz .bin").length, prompt: document.getElementById("qz-prompt").textContent}));
  const toBin = (item, bin) => page.dragAndDrop(`#qz .chip[data-item="${item}"]`, `#qz .bin[data-bin="${bin}"]`);          // a real drag and drop
  const clickBin = async (item, bin) => { await page.click(`#qz .chip[data-item="${item}"]`); await page.click(`#qz .bin[data-bin="${bin}"] b`); };      // or click an item, then a bin
  const answer = async (right, firstDrag = true) => {                                            // fill all three rounds; right=false puts the 'doors' task in the wrong bin
    const R = QUIZZES.intern.rounds;
    for (let i = 0; i < R.length; i++) {
      let n = 0;
      for (const it of R[i].items) {
        let bin = R[i].graded ? R[i].answer[it.id] : (n % 2 ? "no" : "yes"); if (!right && R[i].id === "tasks" && it.id === "doors") bin = "mine";
        if (firstDrag && n === 0) await toBin(it.id, bin); else await clickBin(it.id, bin); n++;
      }
      await page.click("#qz-next");
    }
  };

  // before applying: the door of 666 is by application only
  await page.evaluate(() => window.__game.loadScene("street", {pos: [-6.2, 0, -127], face: [1, 0]})); await settled("street"); await frames(10);
  await setT(12); await frames(5);
  check("at 666 Hallam Row, open, with no job: it is by application only", /666 HALLAM ROW: press F/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(2);
  check("F says to apply on your computer, and nothing starts", /by application only/.test(await toast()) && !(await page.$("#gamemount iframe")));

  // the computer: job search offers one application, for the Intern
  await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await settled("apartment"); await frames(10);
  await stand(APARTMENT.computer.at[0], 0.02, APARTMENT.computer.at[1], 0); await frames(5);
  await page.keyboard.press("KeyF"); await page.keyboard.press("Digit3");
  let jobs = await page.evaluate(() => ({body: document.getElementById("pc-body").textContent, btns: [...document.querySelectorAll("#pc-actions button")].map(b => ({t: b.textContent, off: b.disabled, job: b.dataset.job}))}));
  const ib = jobs.btns.find(b => b.job === "intern");
  check("the job search has an Apply button for The Intern (one of five since slice 6), and every job is hiring", jobs.btns.length === 5 && !!ib && !ib.off && /Apply: The Intern \(666 HALLAM ROW\)/.test(ib.t) && (jobs.body.match(/hiring: apply below/g) || []).length === 5, JSON.stringify(jobs));

  // closing the quiz half way counts as nothing
  await page.click('#pc-actions button[data-job="intern"]');
  let q = await qz();
  check("Apply opens the quiz on round 1: five tasks, two bins, Next shut until all are placed", q.open && q.shown === "flex" && /1 of 3/.test(q.title) && q.tray === 5 && q.bins === 2 && q.nextOff && q.next === "Next", JSON.stringify(q));
  if (shots) await page.screenshot({path: `${shots}/quiz.png`});
  await toBin("coffee", "mine");
  q = await qz(); check("a real drag and drop puts the item in its bin", q.tray === 4 && await page.evaluate(() => !!document.querySelector('#qz .bin[data-bin="mine"] .chip[data-item="coffee"]')));
  await page.click('#qz .bin[data-bin="mine"] .chip[data-item="coffee"]');
  q = await qz(); check("clicking an item in a bin takes it back to the tray", q.tray === 5);
  await page.keyboard.press("Escape");
  check("Esc closes the quiz and leaves the computer open; the application counts for nothing", await page.evaluate(() => !window.__game.QZ.open && window.__game.PC.open && window.__game.APP.st.active === null && Object.keys(window.__game.APP.st.rejectedOn).length === 0));

  // a wrong answer is a rejection
  await page.click('#pc-actions button[data-job="intern"]');
  await answer(false);
  q = await qz();
  check("a wrong answer in a graded round: REJECTED", /REJECTED/.test(q.prompt) && q.next === "Close", q.prompt);
  check("no flag, and the application is recorded for day 1", !(await flag()) && await page.evaluate(() => window.__game.APP.st.rejectedOn.intern === 1 && window.__game.APP.st.active === null));
  await page.click("#qz-next");
  jobs = await page.evaluate(() => ({body: document.getElementById("pc-body").textContent, btn: document.querySelector('#pc-actions button[data-job="intern"]').textContent, off: document.querySelector('#pc-actions button[data-job="intern"]').disabled}));
  check("the job search now says rejected and the button is shut with its reason", jobs.off && /tomorrow/.test(jobs.btn) && /rejected: try again tomorrow/.test(jobs.body), JSON.stringify(jobs));
  await page.keyboard.press("Digit1");
  check("the mail has the rejection", await page.evaluate(() => /REJECTED: The Intern, 666 HALLAM ROW/.test(document.getElementById("pc-body").textContent)));

  // the next day: apply again, all right
  await setT(9, 2); await page.keyboard.press("Digit3");
  check("the next game day the button is open again", await page.evaluate(() => !document.querySelector('#pc-actions button[data-job="intern"]').disabled), await page.evaluate(() => document.querySelector('#pc-actions button[data-job="intern"]').textContent));
  await page.click('#pc-actions button[data-job="intern"]');
  await answer(true);
  q = await qz();
  check("all graded rounds right (the intrusive round has no wrong answer): ACCEPTED", /ACCEPTED/.test(q.prompt) && /noted your answers/.test(q.prompt), q.prompt);
  if (shots) await page.screenshot({path: `${shots}/quiz_accepted.png`});
  check("the flag job_intern is held", await flag());
  await page.click("#qz-next");
  jobs = await page.evaluate(() => ({body: document.getElementById("pc-body").textContent, btn: document.querySelector('#pc-actions button[data-job="intern"]').textContent, off: document.querySelector('#pc-actions button[data-job="intern"]').disabled}));
  check("the job search says ACCEPTED and cannot be applied for again", jobs.off && /already accepted/.test(jobs.btn) && /\(ACCEPTED\)/.test(jobs.body), JSON.stringify(jobs));
  await page.keyboard.press("Digit1");
  check("the mail has the offer", await page.evaluate(() => /ACCEPTED: The Intern/.test(document.getElementById("pc-body").textContent)));
  await page.keyboard.press("Escape");

  // a reload keeps the job
  await page.close();
  const p2 = await solo();
  check("a reload keeps job_intern and the accepted application", await p2.evaluate(() => window.__game.heldFlags().includes("job_intern") && window.__game.APP.st.accepted.intern === true));
  await p2.close();

  // the shift: the door of 666 starts the Intern game; the game's ending brings you back to the street door
  const p3 = await solo();
  const settled3 = id => p3.waitForFunction(i => window.__game.S.id === i && !window.__game.loading, id, {timeout: 180000});
  await p3.evaluate(() => window.__game.loadScene("street", {pos: [-6.2, 0, -127], face: [1, 0]})); await settled3("street");
  await p3.evaluate(([a]) => { window.__game.CITY.t = a; window.__game.keys = window.__game.keys; }, [secondsAt(21, 2)]); await p3.evaluate(() => { for (let i = 0; i < 6; i++) window.__game.sim(0.05, i); });
  const pr = () => p3.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  check("after 20:00 the door is closed even with the job", /closed/.test(await pr()), await pr());
  await p3.keyboard.press("KeyF"); await p3.evaluate(() => { for (let i = 0; i < 3; i++) window.__game.sim(0.05, i); });
  check("and F does not start a shift", !(await p3.$("#gamemount iframe")));
  await p3.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(12, 2)]); await p3.evaluate(() => { for (let i = 0; i < 6; i++) window.__game.sim(0.05, i); });
  check("by day, with the job, the door offers your shift", /start your shift \(The Intern\)/.test(await pr()), await pr());
  await p3.keyboard.press("KeyF");
  await p3.waitForSelector("#gamemount iframe", {timeout: 60000});
  const inGame = await p3.evaluate(() => ({mount: getComputedStyle(document.getElementById("gamemount")).display, loading: window.__game.loading, src: document.querySelector("#gamemount iframe").src}));
  check("F starts the Intern game in its own window", inGame.mount === "block" && inGame.loading && /games\/intern\/index\.html/.test(inGame.src), JSON.stringify(inGame));
  const t0 = await p3.evaluate(() => window.__game.cityState().t); await new Promise(r => setTimeout(r, 1500));
  check("the City's clock waits during your shift", Math.abs((await p3.evaluate(() => window.__game.cityState().t)) - t0) < 0.01);
  await p3.evaluate(() => { const fr = document.querySelector("#gamemount iframe"); fr.contentWindow.eval("parent.postMessage({type: \"intern-ending\"}, \"*\")"); });      // posted from inside the game window, as the game does
  await p3.waitForFunction(() => !document.querySelector("#gamemount iframe") && !window.__game.loading && window.__game.S.id === "street", null, {timeout: 120000});
  await p3.evaluate(() => { for (let i = 0; i < 10; i++) window.__game.sim(0.05, i); });
  const back = await p3.evaluate(() => { const g = window.__game; return {p: g.P.p.toArray(), yaw: g.P.yaw, mount: getComputedStyle(document.getElementById("gamemount")).display, canvas: g.S.id}; });
  check("the game's ending brings you back out to the street door of 666, and the page is the City's again", Math.abs(back.p[0] - JOB_FRONT.arrive[0]) < 0.01 && Math.abs(back.p[2] - JOB_FRONT.arrive[2]) < 0.01 && back.mount === "none" && back.canvas === "street", JSON.stringify(back));
  await p3.close();
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
