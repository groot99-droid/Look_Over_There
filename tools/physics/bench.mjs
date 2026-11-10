// Step-cost benchmark: node tools/physics/bench.mjs [--json]
// 200 dynamic bodies dropped into a pit; 0 or 1000 extra static boxes. Phase "active" = the first 300 steps (falling and piling up),
// phase "rest" = steps 900..1200 (bodies mostly asleep). A throwaway world of the same scene is stepped first so the JIT is warm.
import {load} from "./engines/index.mjs";
import {stressScene, DT} from "./scenes.mjs";
const pct = (t, p) => t[Math.min(t.length - 1, Math.floor(t.length * p))];
const stat = t => { const s = [...t].sort((a, b) => a - b); return {mean: +(t.reduce((a, b) => a + b, 0) / t.length).toFixed(3), p95: +pct(s, 0.95).toFixed(3), max: +s[s.length - 1].toFixed(3)}; };
export async function run(now = () => performance.now(), engines = ["cannon", "rapier"], clutters = [0, 1000]) {
  const rows = [];
  for (const name of engines) for (const clutter of clutters) {
    const w = await load(name); stressScene(w, {clutter}); for (let i = 0; i < 120; i++) w.step(DT); w.free();
    const e = await load(name); const bodies = stressScene(e, {clutter});
    const active = [], rest = [];
    for (let i = 0; i < 1200; i++) { const a = now(); e.step(DT); const d = now() - a; if (i < 300) active.push(d); else if (i >= 900) rest.push(d); }
    const asleep = bodies.filter(b => e.asleep(b)).length;
    rows.push({engine: name, staticClutter: clutter, active: stat(active), rest: stat(rest), asleepAfter20s: asleep});
    e.free();
  }
  return rows;
}
if (typeof process !== "undefined" && import.meta.url === `file://${process.argv[1]}`) {
  const rows = await run();
  if (process.argv.includes("--json")) console.log(JSON.stringify(rows));
  else { console.log(`node ${process.version}, ${process.platform}/${process.arch}; ms per 1/60 s step, 200 bodies`); for (const r of rows) console.log(r.engine.padEnd(7), "static+" + String(r.staticClutter).padEnd(5), "active mean", r.active.mean, "p95", r.active.p95, "max", r.active.max, "| rest mean", r.rest.mean, "p95", r.rest.p95, "| asleep", r.asleepAfter20s + "/200"); }
}
