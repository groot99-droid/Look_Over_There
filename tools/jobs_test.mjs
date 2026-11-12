// The other four jobs (City slice 6): each has an application on the computer (the shared quiz) and its own flag; accepted, its door on Hallam Row offers a shift in
// its hours (the museum's in the evening); a shift is a screen while the job's game is not built: it takes the job's hours off the clock, drains hunger, and pays.
// Needs Playwright + Chromium and internet for three.js from unpkg. Usage: node tools/jobs_test.mjs
import {createRequire} from "node:module";
import {createServer} from "../server/server.js";
import {secondsAt, APARTMENT, DOORS} from "../shared/city.js";
import {QUIZZES} from "../shared/application.js";
import {STUB_SHIFTS} from "../shared/pay.js";
import {MUSEUM} from "../shared/museum.js";
import {FACTORY} from "../shared/factory.js";
import {HUNGER} from "../shared/needs.js";
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
  const stand = (x, z, yaw = 0) => page.evaluate(([x, z, yaw]) => { const g = window.__game; g.P.p.set(x, 0.02, z); g.P.v.set(0, 0, 0); g.P.yaw = yaw; }, [x, z, yaw]);
  const prompt = () => page.evaluate(() => { const e = document.getElementById("prompt"); return e.style.display === "none" ? "" : e.textContent; });
  const toast = () => page.evaluate(() => document.getElementById("toast").textContent);
  const setT = (h, day = 1) => page.evaluate(([a]) => { window.__game.CITY.t = a; }, [secondsAt(h, day)]);
  const state = () => page.evaluate(() => ({...window.__game.cityState(), needs: JSON.parse(JSON.stringify(window.__game.NEEDS)), flags: window.__game.heldFlags(), sh: window.__game.SH.open}));
  const door = id => DOORS.find(d => d.id === id), front = d => [d.x + (d.side === "w" ? 1.8 : -1.8), d.z];

  // apply on the computer: every round answered right (or one graded item wrong), by clicking an item and then its bin
  async function apply(job, right) {
    await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await settled("apartment");
    await stand(...APARTMENT.computer.at); await frames(3);
    await page.keyboard.press("KeyF"); await page.keyboard.press("Digit3");
    await page.click(`#pc-actions button[data-job="${job}"]`);
    const q = QUIZZES[job];
    for (const r of q.rounds) {
      let first = true;
      for (const it of r.items) {
        let bin = r.graded ? r.answer[it.id] : r.bins[0].id;
        if (!right && r.graded && first) bin = r.bins.find(b => b.id !== bin).id;
        first = false;
        await page.click(`#qz .chip[data-item="${it.id}"]`); await page.click(`#qz .bin[data-bin="${bin}"] b`);
      }
      await page.click("#qz-next");
    }
    const res = await page.evaluate(() => document.getElementById("qz-prompt").textContent);
    await page.click("#qz-next"); await page.keyboard.press("Escape");
    return res;
  }
  async function atDoor(id, h, day = 1) {
    await page.evaluate(([x, z]) => window.__game.loadScene("street", {pos: [x, 0, z], face: [1, 0]}), front(door(id))); await settled("street");
    await setT(h, day); await frames(3);
  }

  // the job search now lists five jobs, all hiring
  await setT(9);
  const btns = await (async () => { await page.evaluate(() => window.__game.loadScene("apartment", {pos: [1.5, 0, 1.4], face: [0, -1]})); await settled("apartment"); await stand(...APARTMENT.computer.at); await frames(3); await page.keyboard.press("KeyF"); await page.keyboard.press("Digit3"); const b = await page.evaluate(() => [...document.querySelectorAll("#pc-actions button")].map(b => ({job: b.dataset.job, off: b.disabled}))); await page.keyboard.press("Escape"); return b; })();
  check("the job search has five Apply buttons, all open", btns.length === 5 && btns.every(b => !b.off) && ["trash", "lab", "intern", "museum", "factory"].every(j => btns.some(b => b.job === j)), JSON.stringify(btns));

  // before applying: the door is by application only
  await atDoor("w41", 10);
  check("41 Hallam Row without the job: by application only", /41 HALLAM ROW: press F/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(2);
  check("F says to apply, and no shift screen opens", /by application only/.test(await toast()) && !(await state()).sh);

  // a wrong answer rejects; the right answers accept and set the job's own flag
  let res = await apply("lab", false);
  check("the lab application with a wrong answer is rejected, and no flag", /REJECTED/.test(res) && !(await state()).flags.includes("job_lab"), res);
  res = await apply("trash", true);
  check("the trash application with right answers is accepted; job_trash is held", /ACCEPTED/.test(res) && (await state()).flags.includes("job_trash"), res);
  res = await apply("museum", true);
  check("a second job can be held too: job_museum", /ACCEPTED/.test(res) && (await state()).flags.includes("job_museum"), res);

  // the trash depot: a day shift
  await atDoor("w41", 10);
  check("41 Hallam Row with the job, at 10:00: your shift is offered", /start your shift \(Trash truck worker\)/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF");
  let s0 = await state();
  const shown = await page.evaluate(() => ({title: document.getElementById("sh-title").textContent, text: document.getElementById("sh-text").textContent}));
  check("F opens the shift screen: the job, the route, the hours and the pay (slice 11: the trash job is a route)", s0.sh && /41 HALLAM ROW · TRASH TRUCK WORKER/.test(shown.title) && /8 bins.*4 hours.*\$2 a bin/.test(shown.text), JSON.stringify(shown));
  const pBefore = await page.evaluate(() => window.__game.P.p.toArray());
  await page.evaluate(() => { window.__game.keys.KeyW = true; }); await frames(30); await page.evaluate(() => { window.__game.keys.KeyW = false; });
  check("while the screen is up you do not walk", (await page.evaluate(() => window.__game.P.p.toArray())).every((v, i) => Math.abs(v - pBefore[i]) < 1e-6));
  await page.keyboard.press("Escape");
  check("Esc closes it and nothing happened", !(await state()).sh && Math.abs((await state()).hour - s0.hour) < 0.05 && (await state()).needs.money === s0.needs.money);
  await page.keyboard.press("KeyF"); await page.click("#sh-work"); await frames(2);
  let s1 = await state();
  check("starting it puts you on the route (the clock does not jump)", !s1.sh && Math.abs(s1.hour - s0.hour) < 0.1 && await page.evaluate(() => window.__game.CITY.tr.active), JSON.stringify([s0.hour, s1.hour]));
  await page.keyboard.press("KeyF"); await frames(2); s1 = await state();
  check("clocking out straight away at the depot pays $0 for 0 bins (the whole route is in trash_test)", !(await page.evaluate(() => window.__game.CITY.tr.active)) && s1.needs.money === s0.needs.money && s1.needs.lastNote === "Trash route 0/8" && /Paid: \$0/.test(await toast()), JSON.stringify(s1.needs));
  await atDoor("w41", 17);
  check("after 16:00 the trash shift says when shifts start", /Shifts start between 08:00 and 16:00/.test(await prompt()), await prompt());
  await page.keyboard.press("KeyF"); await frames(2);
  check("and F does not open the screen", !(await state()).sh);

  // the museum: an evening shift, through the shut door
  await atDoor("e108", 12);
  check("the museum at noon: shifts start between 20:00 and 21:00", /Museum night guard\): Shifts start between 20:00 and 21:00/.test(await prompt()), await prompt());
  await atDoor("e108", 20.5);
  check("at 20:30 (the stores are shut) the museum guard's shift is offered", /start your shift \(Museum night guard\)/.test(await prompt()) && !(await state()).open, await prompt());
  s0 = await state(); await page.keyboard.press("KeyF");
  check("the museum's screen offers the shift (slice 14: it is played in the galleries)", /Watch the 6 statues/.test(await page.evaluate(() => document.getElementById("sh-text").textContent)) && await page.evaluate(() => document.getElementById("sh-work").textContent) === "Start the shift");
  await page.click("#sh-work"); await settled("galleries"); await frames(2);
  check("starting it takes you into the museum, on shift", await page.evaluate(() => window.__game.CITY.mu.active));
  await stand(MUSEUM.door.at[0], MUSEUM.door.at[1] - 0.6, Math.PI); await frames(2); await page.keyboard.press("KeyF"); await settled("street"); await frames(2); s1 = await state();
  check("walking straight out is leaving your post: no pay (the full shift is in museum_test)", s1.needs.money === s0.needs.money && s1.needs.lastNote === "Museum: left early" && !(await page.evaluate(() => window.__game.CITY.mu.active)), JSON.stringify(s1.needs));

  // the factory (slice 16: its shift is played on the factory floor)
  res = await apply("factory", true);
  check("the factory application with right answers is accepted", /ACCEPTED/.test(res) && (await state()).flags.includes("job_factory"), res);
  await atDoor("e330", 10); s0 = await state(); await page.keyboard.press("KeyF");
  check("the factory's screen offers the shift on the belt", /Parts come down the belt/.test(await page.evaluate(() => document.getElementById("sh-text").textContent)) && await page.evaluate(() => document.getElementById("sh-work").textContent) === "Start the shift");
  await page.click("#sh-work"); await settled("factory_floor"); await frames(2);
  check("starting it takes you onto the factory floor, on shift", await page.evaluate(() => window.__game.CITY.fa.active));
  await stand(FACTORY.door.at[0], FACTORY.door.at[1] - 0.6, Math.PI); await frames(2); await page.keyboard.press("KeyF"); await settled("street"); await frames(2); s1 = await state();
  check("walking straight out is leaving your post: no pay (the full shift is in factory_test)", s1.needs.money === s0.needs.money && s1.needs.lastNote === "Factory: left early", JSON.stringify(s1.needs));

  // the lab: rejected today, so still by application only
  await atDoor("w214", 10, 1);
  check("214 Hallam Row (rejected): still by application only", /214 HALLAM ROW: press F/.test(await prompt()), await prompt());

  // the last stub shift: the lab (rejected on day 1, so apply again on day 2)
  await setT(9, 2); res = await apply("lab", true);
  check("on day 2 the lab application with right answers is accepted", /ACCEPTED/.test(res) && (await state()).flags.includes("job_lab"), res);
  await atDoor("w214", 10, 2); s0 = await state(); await page.keyboard.press("KeyF");
  check("the lab's screen says its game is not built yet, 4 hours, $14", /not built yet.*4 hours.*\$14/.test(await page.evaluate(() => document.getElementById("sh-text").textContent)));
  await page.click("#sh-work"); await frames(2); s1 = await state();
  check("working the stub: 4 hours pass and $14 is paid with the job's name", Math.abs(s1.hour - (s0.hour + 4)) < 0.1 && s1.needs.money === s0.needs.money + STUB_SHIFTS.lab.pay && s1.needs.lastNote === "Laboratory worker", JSON.stringify([s0.hour, s1.hour, s1.needs.money]));

  // a reload keeps the jobs
  await page.reload(); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("a reload keeps every job held (trash, museum, factory, lab), and they are accepted on the computer", await page.evaluate(() => { const g = window.__game, f = g.heldFlags(); return ["job_trash", "job_museum", "job_factory", "job_lab"].every(k => f.includes(k)) && g.APP.st.accepted.trash && g.APP.st.accepted.museum && g.APP.st.accepted.factory && g.APP.st.accepted.lab; }));
  check("no page errors", errors.length === 0, errors.join(" | "));
} finally { await browser.close(); await srv.close(); }
process.exit(failed ? 1 : 0);
