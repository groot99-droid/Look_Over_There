// The laboratory worker's shift (session 9, slice 17): behind 214 Hallam Row, "the nearest job to Secret Operations" (docs/WORLD.md). The manifest's `lab` area, scene
// `laboratory`: a blockout room with five stations round the walls and a sealed door marked B2 on the north wall (nothing behind it yet). Each procedure card names three
// stations in order; F at the right station does the next step, and after the third the card is done and the next card comes up. F at any other station is a mistake: that
// card is spoiled and a new one comes up. The shift keeps the stub's hours (4 game hours, starting between 08:00 and 16:00). Pay: $3 a card done, $1 off a card spoiled,
// from $0 to $20 (the stub paid $14). Leaving early, fainting or passing out loses the shift. Pure here; the page draws it. Blockout, no art.
import {DAY_S} from "./city.js";
import {STUB_SHIFTS} from "./pay.js";

export const LAB = {
  half: [9, 6], h: 4,                                   // the room: x in [-9, 9], z in [-6, 6]
  arrive: [0, 0, 4.4], face: [0, -1],
  door: {at: [0, 5.3], reach: 1.8},
  b2: {x: 0, z: -6},                                    // the sealed door on the north wall
  stations: [
    {id: "sink", label: "SINK", x: -7.6, z: -3},
    {id: "scale", label: "SCALE", x: -7.6, z: 2},
    {id: "centrifuge", label: "CENTRIFUGE", x: -4, z: -4.6},
    {id: "freezer", label: "FREEZER", x: 4, z: -4.6},
    {id: "log", label: "LOG BOOK", x: 7.6, z: 0},
  ].map(s => ({...s, half: 0.6, reach: 1.7})),
};
export const LAB_FRONT = {arrive: [-6.2, 0, -95], face: [1, 0]};          // where you stand on the street when you come out (214's door is on the west side at z = -95)
export const BENCH = {steps: 3, perCard: 3, perSpoil: 1, maxPay: 20, hours: STUB_SHIFTS.lab.hours};
export const shiftEnds = t0 => t0 + BENCH.hours / 24 * DAY_S;
const IDS = LAB.stations.map(s => s.id);
// the n-th card: three different stations, in a fixed mixed order (the same every shift)
export function cardOf(n) {
  const left = [...IDS], out = [];
  for (let k = 0; k < BENCH.steps; k++) { const h = Math.imul(n * 7 + k + 3, 2654435761) >>> 0; out.push(left.splice(h % left.length, 1)[0]); }
  return out;
}
export const newBench = () => ({card: 0, step: 0, done: 0, spoiled: 0});
export const stationNear = (px, pz) => LAB.stations.findIndex(s => Math.hypot(s.x - px, s.z - pz) < s.reach);
// F at station `id`: "step" (the right station, more to do), "done" (the card's last step), or "wrong" (the card is spoiled; the next one comes up)
export function useStation(b, id) {
  const want = cardOf(b.card)[b.step];
  if (id !== want) return {b: {...b, card: b.card + 1, step: 0, spoiled: b.spoiled + 1}, result: "wrong", want};
  if (b.step + 1 >= BENCH.steps) return {b: {...b, card: b.card + 1, step: 0, done: b.done + 1}, result: "done", want};
  return {b: {...b, step: b.step + 1}, result: "step", want};
}
export const labelOf = id => LAB.stations.find(s => s.id === id).label;
export const cardText = b => cardOf(b.card).map((id, i) => (i < b.step ? "✓ " : i === b.step ? "> " : "") + labelOf(id)).join("  ");
export function benchPay(b, how) {
  if (how === "left") return {pay: 0, lines: ["You left your post before the end of the shift.", "Paid: $0"], note: "Lab: left early"};
  const pay = Math.max(0, Math.min(BENCH.maxPay, b.done * BENCH.perCard - b.spoiled * BENCH.perSpoil));
  return {pay, lines: [`Cards done: ${b.done}`, `Cards spoiled: ${b.spoiled}`, `Paid: $${pay}`], note: `Lab ${b.done} done, ${b.spoiled} spoiled`};
}

// the collision file: floor, ceiling, walls and the five stations (benches, sink, scale, centrifuge, freezer, log desk)
export function labColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = LAB.half, h = LAB.h, t = 0.2;
  add("Floor_Lab", [-hx - t, -1, -hz - t], [hx + t, 0, hz + t]); add("Ceiling_Lab", [-hx - t, h, -hz - t], [hx + t, h + t, hz + t]);
  add("Wall_N", [-hx - t, 0, -hz - t], [hx + t, h, -hz]); add("Wall_S", [-hx - t, 0, hz], [hx + t, h, hz + t]);
  add("Wall_W", [-hx - t, 0, -hz], [-hx, h, hz]); add("Wall_E", [hx, 0, -hz], [hx + t, h, hz]);
  for (const s of LAB.stations) add("Station_" + s.id, [s.x - s.half, 0, s.z - s.half], [s.x + s.half, s.id === "freezer" ? 1.9 : 0.95, s.z + s.half]);
  return c;
}
export const labDoc = () => ({scene: "laboratory", colliders: labColliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_door", kind: "Spawn", level: "laboratory", position: LAB.arrive}]});
