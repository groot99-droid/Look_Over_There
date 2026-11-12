// City anomalies (session 9, slice 8): three small wrong things on Hallam Row, from the world bible's proposals (docs/WORLD.md, section 9). Pure and tested; the page draws them.
//  1. A shop sign that changes one letter each time you walk past it.
//  2. Pedestrians who all face the same way: up the street, toward 666 Hallam Row. They stand on the sidewalks by day and are gone when the stores close.
//  3. A lit window, at night, in a building that is not there.
// Blockout only. None of them collides with anything (they are drawn, not in world/street.json), and none of them is saved: a reload puts the sign back.
import {storesOpen, skyAt, FRONT} from "./city.js";

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

// 3. the window: past the end of the east side (the last building there, efill, ends at z -134), high over the grass (above the roofline, so it shows from most of the street), facing back down the street. Lit only at night.
export const GHOST_WINDOW = {at: [12, 14, -142], w: 1.6, h: 1.3};
export const ghostLit = hour => skyAt(hour).night;
