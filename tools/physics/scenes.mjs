// Scenes shared by the bench, the test and the page. Pure functions of an engine adapter.
// The floor is a thick box in the game's {n, x} form, so the same code path as the game's `boxes` is used.
export const FLOOR = {n: [-60, -1, -60], x: [60, 0, 60]};
export const DT = 1 / 60;

export function ballScene(e, {drop = 5, r = 0.11} = {}) {
  e.addStaticBox(FLOOR);
  return {ball: e.addBall([0, drop, 0], r), r};
}

// 200 dynamic bodies (half balls, half crates) dropped into a pit walled by `walls` static boxes, plus `clutter` far-away static boxes
// (the game's scenes have thousands of colliders; a physics world would only be given those near the toys, but the worst case is measured too).
export function stressScene(e, {bodies = 200, clutter = 0} = {}) {
  e.addStaticBox(FLOOR);
  for (const [n, x] of [[[-4, 0, -4.5], [4, 3, -4]], [[-4, 0, 4], [4, 3, 4.5]], [[-4.5, 0, -4], [-4, 3, 4]], [[4, 0, -4], [4.5, 3, 4]]]) e.addStaticBox({n, x});
  for (let i = 0; i < clutter; i++) { const gx = (i % 40) * 3 - 59, gz = Math.floor(i / 40) * 3 - 59; e.addStaticBox({n: [gx, 0, gz + 20], x: [gx + 1, 1.5, gz + 21]}); }
  const out = []; let s = 12345; const rnd = () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;     // fixed seed: same scene in both engines
  for (let i = 0; i < bodies; i++) {
    const p = [(rnd() - 0.5) * 6, 0.5 + (i % 20) * 0.5 + rnd() * 0.2, (rnd() - 0.5) * 6];
    out.push(i % 2 ? e.addBall(p, 0.15 + rnd() * 0.1) : e.addBox(p, [0.2, 0.2, 0.2]));
  }
  return out;
}

export function swingScene(e, {length = 2, angle = 0.5, pivot = [0, 4, 0]} = {}) {
  e.addStaticBox(FLOOR);
  const seat = e.addSwing({pivot, length, angle});
  return {seat, pivot, length};
}

// angle of the seat from straight down, in the x-y plane
export const swingAngle = (e, sw) => { const p = e.pos(sw.seat); return Math.atan2(p[0] - sw.pivot[0], sw.pivot[1] - p[1]); };

// median step time and p95 in ms over `steps` fixed steps, after `warm` unrecorded steps (JIT). `now` is performance.now.
export function timeSteps(e, now, {steps = 600, warm = 60} = {}) {
  for (let i = 0; i < warm; i++) e.step(DT);
  const t = [];
  for (let i = 0; i < steps; i++) { const a = now(); e.step(DT); t.push(now() - a); }
  t.sort((a, b) => a - b);
  const mean = t.reduce((a, b) => a + b, 0) / t.length;
  return {mean, median: t[t.length >> 1], p95: t[Math.floor(t.length * 0.95)], max: t[t.length - 1]};
}
