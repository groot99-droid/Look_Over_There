// Ten players in one party, the tenth driving the real lobby in a headless browser: mode buttons, the open-rooms list, the waiting room, then the HUD in the round.
// The other nine are plain WebSocket clients. Run: node tools/lobby10_test.mjs
import {createRequire} from "node:module";
import {WebSocket} from "../server/node_modules/ws/wrapper.mjs";
import {createServer} from "../server/server.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let fails = 0; const check = (name, ok) => { console.log((ok ? "ok   " : "FAIL ") + name); if (!ok) fails++; };
const srv = await createServer({countdownMs: 500}), base = `http://localhost:${srv.port}`;
const bots = [];
for (let i = 0; i < 9; i++) { const ws = new WebSocket(`ws://localhost:${srv.port}/ws`); await new Promise(r => ws.on("open", r)); ws.send(JSON.stringify({t: "join", room: "TEN", name: "Bot" + i, char: i % 5})); bots.push(ws); }
const browser = await chromium.launch(), page = await browser.newPage();
const errors = []; page.on("pageerror", e => errors.push(e.message));
await page.goto(base + "/"); await page.waitForSelector("#l-open button");
check("the open-rooms list shows the party with 9/10", (await page.textContent("#l-open")).includes("TEN · 9/10"));
check("Going back in is shown and cannot be picked", await page.$eval('#l-mode button[data-mode="going_back_in"]', b => b.disabled && /soon/.test(b.textContent)));
await page.click("#l-open button"); await page.fill("#l-name", "Human"); await page.click("#l-join");
await page.waitForSelector("#l-wait", {state: "visible"});
await page.waitForFunction(() => document.querySelectorAll("#l-players > div").length === 10, null, {timeout: 5000}).then(() => check("the waiting room lists all 10", true), () => check("the waiting room lists all 10", false));
const overflow = await page.$eval("#l-wait", el => el.scrollHeight <= innerHeight + 1 || getComputedStyle(el).overflowY !== "visible");
await page.screenshot({path: "/tmp/claude-0/s/lobby10.png"});
check("the waiting room fits the window at 10 players (or scrolls)", overflow);
for (const ws of bots) ws.send(JSON.stringify({t: "ready", ready: true}));
await page.click("#l-ready");
await page.waitForFunction(() => /10 in the building/.test(document.getElementById("hud")?.textContent || ""), null, {timeout: 20000}).then(() => check("in the round the HUD counts 10 in the building", true), () => check("in the round the HUD counts 10 in the building", false));
check("no page errors", errors.length === 0); if (errors.length) console.log(errors);
const late = new WebSocket(`ws://localhost:${srv.port}/ws`); const got = await new Promise(r => { late.on("open", () => late.send(JSON.stringify({t: "join", room: "TEN", name: "L"}))); late.on("message", d => r(JSON.parse(d))); });
check("an eleventh is told the limit", got.t === "full" && got.max === 10);
await browser.close(); bots.forEach(b => b.close()); await srv.close(); process.exit(fails ? 1 : 0);
