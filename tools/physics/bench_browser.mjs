// The same bench in headless Chromium (software GL flags, as the other tools here use; physics itself does not use the GPU).
// node tools/physics/bench_browser.mjs
import {createRequire} from "node:module";
import {readFile} from "node:fs/promises";
import {serve} from "./serve.mjs";
const {chromium} = createRequire(import.meta.url)("playwright");
const srv = await serve(0), nm = new URL("./node_modules/", import.meta.url);
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const page = await browser.newPage();
await page.route("https://unpkg.com/**", async r => r.fulfill({body: await readFile(new URL(r.request().url().includes("cannon-es") ? "cannon-es/dist/cannon-es.js" : "@dimforge/rapier3d-compat/rapier.mjs", nm)), contentType: "text/javascript"}));
await page.goto(`http://localhost:${srv.address().port}/bench.html`);
await page.waitForFunction(() => window.__ready);
const rows = await page.evaluate(() => window.__bench());
console.log(await browser.version(), "(headless, swiftshader flags);", "ms per 1/60 s step, 200 bodies");
for (const r of rows) console.log(r.engine.padEnd(7), "static+" + String(r.staticClutter).padEnd(5), "active mean", r.active.mean, "p95", r.active.p95, "max", r.active.max, "| rest mean", r.rest.mean, "p95", r.rest.p95, "| asleep", r.asleepAfter20s + "/200");
await browser.close(); srv.close();
