// Every monster inside a cone: shared by the flamethrower (docs/ITEMS.md 4.3) and the frequency horn (4.8). No graphics here.
// From eye o = [x, y, z] facing the unit vector f = [x, z]: on o's floor, within reachM and arcDeg (the whole width), with nothing solid between, nearest first is not promised.
import {rayClear} from "./world.js";
export function inCone(W, monsters, o, f, reachM, arcDeg) {
  const out = [];
  for (const m of monsters) {
    if (Math.abs(o[1] - 1.6 - m.fy) > 1.6) continue;
    const dx = m.pos.x - o[0], dz = m.pos.z - o[2], d = Math.hypot(dx, dz);
    if (d > reachM) continue;
    if (d > 0.5) { const ang = Math.acos(Math.max(-1, Math.min(1, (f[0] * dx + f[1] * dz) / d))) * 180 / Math.PI; if (ang > arcDeg / 2) continue; }
    const my = m.fy + 0.5 * ((m.cfg && m.cfg.height) || 2.2), dy = my - o[1], L = Math.hypot(d, dy) || 1;
    if (!rayClear(W, o, [dx / L, dy / L, dz / L], Math.max(0, L - 0.3))) continue;
    out.push(m);
  }
  return out;
}
