// The factory floor worker's shift (session 9, slice 16): behind 330 Hallam Row, the manifest's `factory` area, scene `factory_floor`. A blockout hall with one conveyor belt.
// Parts come down the belt from the west end, one every SPAWN_S seconds, in a fixed order of three kinds. F next to the belt picks up the nearest part (one at a time);
// F at a bin drops what you hold into it. A part in its own bin is sorted right, in another bin it is sorted wrong, and a part that reaches the east end falls into the
// reject chute (missed). The shift keeps the stub's hours (4 game hours, 150 real seconds, starting between 08:00 and 16:00). Pay: $1 a part sorted right, $1 off for each
// sorted wrong, between $0 and $20 (the stub paid $12). Leaving early, fainting or passing out loses the shift. Pure here; the page draws it. Blockout, no art.
import {DAY_S} from "./city.js";
import {STUB_SHIFTS} from "./pay.js";

export const FACTORY = {
  half: [10, 7], h: 6,                                   // the hall: x in [-10, 10], z in [-7, 7]
  arrive: [0, 0, 5.4], face: [0, -1],
  door: {at: [0, 6.3], reach: 1.8},
  belt: {x0: -8, x1: 8, z: -3, w: 1.2, top: 0.9},        // the belt runs west to east along z = -3
  bins: [{kind: "gears", x: -5}, {kind: "bolts", x: 0}, {kind: "springs", x: 5}].map(b => ({...b, z: 2.5, half: 0.6, reach: 1.6})),
};
export const KINDS = {gears: {label: "GEARS", color: 0xc8a040}, bolts: {label: "BOLTS", color: 0x7a8aa0}, springs: {label: "SPRINGS", color: 0x50a060}};
export const FACTORY_FRONT = {arrive: [6.2, 0, -95], face: [-1, 0]};      // where you stand on the street when you come out (330's door is on the east side at z = -95)
export const LINE = {spawnS: 4, speed: 0.8, reach: 1.6, maxPay: 20, hours: STUB_SHIFTS.factory.hours};
export const shiftEnds = t0 => t0 + LINE.hours / 24 * DAY_S;
const ORDER = ["gears", "bolts", "springs"];
// the kind of the n-th part: a fixed, mixed-up order (the same every shift)
export const kindOf = n => ORDER[(Math.imul(n + 7, 2654435761) >>> 0) % 3];

export const newLine = () => ({t: 0, made: 0, parts: [], held: null, right: 0, wrong: 0, missed: 0});
// one step of the belt: new parts appear at the west end on time; every part moves east; a part past the east end is missed
export function stepLine(st, dt) {
  const t = st.t + Math.max(0, dt), parts = [];
  let made = st.made, missed = st.missed;
  for (const p of st.parts) { const x = p.x + LINE.speed * dt; if (x > FACTORY.belt.x1) missed++; else parts.push({...p, x}); }
  while (made * LINE.spawnS <= t) { const age = t - made * LINE.spawnS, x = FACTORY.belt.x0 + LINE.speed * age; if (x > FACTORY.belt.x1) missed++; else parts.push({id: made, kind: kindOf(made), x}); made++; }
  return {...st, t, made, parts, missed};
}
// F by the belt: pick up the nearest part within reach (nothing if your hands are full)
export function pickUp(st, px, pz) {
  if (st.held) return {st, got: null};
  let best = null, bd = LINE.reach;
  for (const p of st.parts) { const d = Math.hypot(p.x - px, FACTORY.belt.z - pz); if (d < bd) { bd = d; best = p; } }
  if (!best) return {st, got: null};
  return {st: {...st, held: {id: best.id, kind: best.kind}, parts: st.parts.filter(p => p !== best)}, got: best.kind};
}
export const binNear = (px, pz) => FACTORY.bins.findIndex(b => Math.hypot(b.x - px, b.z - pz) < b.reach);
// F at bin i: drop what you hold into it
export function drop(st, i) {
  const b = FACTORY.bins[i]; if (!st.held || !b) return {st, ok: null};
  const ok = st.held.kind === b.kind;
  return {st: {...st, held: null, right: st.right + (ok ? 1 : 0), wrong: st.wrong + (ok ? 0 : 1)}, ok};
}
export function linePay(st, how) {
  if (how === "left") return {pay: 0, lines: ["You left your post before the end of the shift.", "Paid: $0"], note: "Factory: left early"};
  const pay = Math.max(0, Math.min(LINE.maxPay, st.right - st.wrong));
  return {pay, lines: [`Sorted right: ${st.right}`, `In the wrong bin: ${st.wrong}`, `Missed: ${st.missed}`, `Paid: $${pay}`], note: `Factory ${st.right} right, ${st.wrong} wrong`};
}

// the collision file: floor, ceiling, walls, the belt and the three bins
export function factoryColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = FACTORY.half, h = FACTORY.h, t = 0.2, B = FACTORY.belt;
  add("Floor_Factory", [-hx - t, -1, -hz - t], [hx + t, 0, hz + t]); add("Ceiling_Factory", [-hx - t, h, -hz - t], [hx + t, h + t, hz + t]);
  add("Wall_N", [-hx - t, 0, -hz - t], [hx + t, h, -hz]); add("Wall_S", [-hx - t, 0, hz], [hx + t, h, hz + t]);
  add("Wall_W", [-hx - t, 0, -hz], [-hx, h, hz]); add("Wall_E", [hx, 0, -hz], [hx + t, h, hz]);
  add("Belt", [B.x0 - 0.5, 0, B.z - B.w / 2], [B.x1 + 0.5, B.top, B.z + B.w / 2]);
  FACTORY.bins.forEach(b => add("Bin_" + b.kind, [b.x - b.half, 0, b.z - b.half], [b.x + b.half, 1.0, b.z + b.half]));
  return c;
}
export const factoryDoc = () => ({scene: "factory_floor", colliders: factoryColliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_door", kind: "Spawn", level: "factory_floor", position: FACTORY.arrive}]});
