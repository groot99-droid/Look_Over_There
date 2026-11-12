// City anomalies (session 9, slice 8): three small wrong things on Hallam Row, from the world bible's proposals (docs/WORLD.md, section 9). Pure and tested; the page draws them.
//  1. A shop sign that changes one letter each time you walk past it.
//  2. Pedestrians who all face the same way: up the street, toward 666 Hallam Row. They stand on the sidewalks by day and are gone when the stores close.
//  3. A lit window, at night, in a building that is not there.
// Blockout only. None of them collides with anything (they are drawn, not in world/street.json), and none of them is saved: a reload puts the sign back.
import {storesOpen, skyAt, FRONT, BUILDINGS, windowSlots} from "./city.js";

// 1. the sign: on the filler building on the west side (wfill1, z -52 to -82), which has no door. Passing = crossing the line z = SIGN.z while on the street.
export const SIGN = {text: "PHARMACY", side: "w", z: -67, y: 4.2};
const ALPHA = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
const mix = i => { let h = Math.imul(i ^ 0x9e3779b9, 0x85ebca6b); h ^= h >>> 13; h = Math.imul(h, 0xc2b2ae35); h ^= h >>> 16; return h >>> 0; };
// the sign's text after `passes` passes: each pass changes exactly one letter of the text before it (always to a different letter). The same count always gives the same text.
export function signText(passes, base = SIGN.text) {
  const a = base.split(""), n = Math.max(0, Math.floor(passes) || 0);
  for (let i = 1; i <= n; i++) {
    const h = mix(i), pos = h % a.length;
    let c = ALPHA[(h >>> 8) % 26];
    if (c === a[pos]) c = ALPHA[(ALPHA.indexOf(c) + 1) % 26];
    a[pos] = c;
  }
  return a.join("");
}
// did a step from z0 to z1 (at x) walk past the sign? Only on the street between the building fronts, and only a real crossing (touching the line and turning back does not count).
export const passedSign = (z0, z1, x) => Math.abs(x) < FRONT && (z0 - SIGN.z) * (z1 - SIGN.z) < 0;

// 2. the pedestrians: [x, z] on the sidewalks (x +-6.6), clear of the doors, the lamp posts and the bus stop. All face -z: up the street, toward 666.
export const PEDESTRIANS = [[-6.6, -12], [6.6, -30], [-6.6, -55], [6.6, -78], [6.6, -104], [-6.6, -112]];
export const PED_FACE = [0, -1];
export const pedsOut = hour => storesOpen(hour);
// slice 18, "people with routines" (docs/WORLD.md): while nobody looks at them, each pedestrian walks a beat up and down its sidewalk, PED_ROUTE metres either side
// of where it stands, at PED_SPEED. The moment one is in your view it stops where it is. They always face up the street, even mid-step: you never see one turn.
export const PED_ROUTE = 3, PED_SPEED = 1.2;
export const newPeds = () => PEDESTRIANS.map((p, i) => ({s: 0, dir: i % 2 ? 1 : -1}));
export const pedAt = (i, s) => [PEDESTRIANS[i][0], PEDESTRIANS[i][1] + s];
export function stepPeds(ps, dt, seen) {
  return ps.map((p, i) => {
    if (seen[i]) return p;
    let s = p.s + p.dir * PED_SPEED * dt, dir = p.dir;
    if (s > PED_ROUTE) { s = 2 * PED_ROUTE - s; dir = -1; } else if (s < -PED_ROUTE) { s = -2 * PED_ROUTE - s; dir = 1; }
    return {s: Math.max(-PED_ROUTE, Math.min(PED_ROUTE, s)), dir};
  });
}

// 3. the window: past the end of the east side (the last building there, efill, ends at z -134), high over the grass (above the roofline, so it shows from most of the street), facing back down the street. Lit only at night.
export const GHOST_WINDOW = {at: [12, 14, -142], w: 1.6, h: 1.3};
export const ghostLit = hour => skyAt(hour).night;

// 4. the watchers (slice 21): "The lit windows are a mix of decoration, NPC apartments, apartments you can visit and things watching you" (docs/WORLD.md). At night three of the
// street's lit windows have a dark figure standing just inside the glass, which turns to follow you. Each is one of the windows the street draws (windowSlots).
export const WATCHERS = [{building: "wfill1", f: 2, k: 1}, {building: "e330", f: 2, k: 2}, {building: "tower", f: 5, k: 2}];
export function watcherAt(w) { const b = BUILDINGS.find(x => x.id === w.building), s = windowSlots(b).find(x => x.f === w.f && x.k === w.k); return s && {x: s.x - s.dir * 0.25, y: s.y, z: s.z, dir: s.dir}; }
export const watchersOut = hour => skyAt(hour).night;
// the yaw (the page's: 0 looks down -z) that turns a figure at (wx, wz) to face (px, pz)
export const watcherYaw = (wx, wz, px, pz) => Math.atan2(px - wx, pz - wz) + Math.PI;

// ---- reporting them (slice 15): "Anomalies are both spot-and-report and avoid" (docs/WORLD.md). You spot an anomaly by seeing it for yourself (`SPOT`: the sign once it has
// changed, two or more of the pedestrians at once, the window at night, each in view with a clear line). The computer's REPORT page lists six things people report on Hallam Row:
// three are real, three are not. A true report of something you have spotted pays $5, once each. A report of something that is not real, or of a real thing you have not seen
// yourself, is a false report and costs $2 (never below $0). What you have spotted and reported is saved.
export const SPOT = {signDist: 25, pedDist: 40, pedCount: 2, windowDist: 95, watcherDist: 30};
export const REPORT = {reward: 5, falseCost: 2};
export const REPORTS = [
  {id: "sign", label: "A shop sign that changes its letters", real: true},
  {id: "lamp", label: "A streetlight that follows people home", real: false},
  {id: "peds", label: "People who all stand facing the same way", real: true},
  {id: "door", label: "A door that was not there yesterday", real: false},
  {id: "window", label: "A lit window where there is no building", real: true},
  {id: "bus", label: "A bus driver with no face", real: false},
  {id: "watchers", label: "Someone in a lit window who turns to watch you", real: true},          // slice 21
];
export const REAL_IDS = REPORTS.filter(r => r.real).map(r => r.id);
export const newSightings = () => ({spotted: {}, reported: {}});
export const spot = (s, id) => !REAL_IDS.includes(id) || s.spotted[id] ? s : {...s, spotted: {...s.spotted, [id]: true}};
// file a report: returns the new sightings, the change in money, and what the page says
export function fileReport(s, id, money) {
  const r = REPORTS.find(x => x.id === id);
  if (!r) return {s, delta: 0, ok: false, msg: "There is no such report."};
  if (s.reported[id]) return {s, delta: 0, ok: false, msg: "You have already reported that."};
  if (r.real && s.spotted[id]) return {s: {...s, reported: {...s.reported, [id]: true}}, delta: REPORT.reward, ok: true, msg: `Report filed: "${r.label}". Thank you. $${REPORT.reward} has been paid to your account.`};
  const cost = Math.min(REPORT.falseCost, Math.max(0, money));
  return {s, delta: cost ? -cost : 0, ok: false, msg: r.real ? `You have not seen that yourself. An unconfirmed report counts as false: $${cost} is taken from your account.` : `There is nothing like that on Hallam Row. A false report costs $${cost}.`};
}
