// The museum night guard's shift (session 9, slice 14): "A small museum where everything comes alive at night" (docs/WORLD.md). The manifest's `museum` area, scene `galleries`,
// behind 108 Hallam Row's door; you go in when your shift starts (20:00 to 21:00) and it lasts 3 game hours (112.5 real seconds). Six statues stand on plinths down the hall.
// The rule is the stalker's: a statue never moves while you are looking at it. Out of your sight its clock runs, and every MOVE_S seconds unwatched it takes one step off its
// plinth toward the middle of the hall, turned to face you (three steps at most). F next to a moved statue sets it back. When the shift ends you are paid for the statues
// that are home and for each one you set back; leaving your post early pays nothing. Pure here; the page draws the hall and calls these. Blockout, no art.
import {DAY_S} from "./city.js";

export const MUSEUM = {
  half: [6, 13], h: 5, cz: -7,                          // the hall: x in [-6, 6], z in [-20, 6]
  arrive: [0, 0, 4.4], face: [0, -1],
  door: {at: [0, 5.3], reach: 1.8},
  plinth: 0.45,                                         // half-width of a plinth (0.9 m square, 0.6 m high)
  homes: [[-4.4, -1], [4.4, -1], [-4.4, -7], [4.4, -7], [-4.4, -13], [4.4, -13]],
  wing: {z: -10, w: 1.8, top: {w: 2.6, e: 2.1}},       // the doorways to galleries_wing: Doric (west, leaves 2.6 m) and arched (east, leaves 2.1 m)
  // the six statues are warriors (the owner, 2026-11-26: "Those warriors and the T. rex should be in the main museum hall instead of those faceless people"), in homes order
  names: ["THE PHARAOH", "THE VIKING", "THE TERRACOTTA WARRIOR", "THE KNIGHT", "THE SAMURAI", "THE ROMAN"],
  // their models (models/characters/, PR #78) and the scale each is drawn at so it stands 1.75 m tall, as in the bake's shadows (docs/renders/galleries/README.md)
  models: [["warrior_egyptian_pharaoh", 4.105], ["warrior_viking_raider", 3.952], ["warrior_qin_terracotta", 3.858], ["warrior_medieval_knight", 3.440], ["warrior_japanese_samurai", 3.545], ["warrior_roman_legionary", 3.483]],
  // the fixed exhibits built into world/galleries.glb (build_galleries.py): solid, never moving; each a pedestal and the figure's box above it
  exhibits: [
    {s: "Exhibit_Mongol", min: [2.316, 0.6, 4.557], max: [3.184, 2.35, 5.243]},
    {s: "Exhibit_Mongol_Plinth", min: [2.3, 0, 4.45], max: [3.2, 0.6, 5.35]},
    {s: "Exhibit_Redcoat", min: [-3.044, 0.6, 4.685], max: [-2.456, 2.35, 5.115]},
    {s: "Exhibit_Redcoat_Plinth", min: [-3.2, 0, 4.45], max: [-2.3, 0.6, 5.35]},
    {s: "TRex_Platform", min: [-3.7, 0, -19.6], max: [3.7, 0.3, -15.6]},
    {s: "TRex_Skeleton", min: [-3.367, 0.3, -18.363], max: [3.188, 2.319, -16.81]},
  ],
};
export const MUSEUM_FRONT = {arrive: [6.2, 0, -41], face: [-1, 0]};      // where you stand on the street when you come out (108's door is on the east side at z = -41)
export const MOVE_S = 9, STEP_M = 1.0, MAX_OFF = 3, FIX_REACH = 1.6;
export const GUARD = {perHome: 2, perFix: 1, maxFixPay: 8, hours: 3};    // $12 for all six home, up to $8 for setting them back: $20 at best (the stub paid $16)
export const shiftEnds = t0 => t0 + GUARD.hours / 24 * DAY_S;

// the statues at the start of a shift: all home, their clocks staggered so they do not all move at once
export const newExhibits = () => MUSEUM.homes.map((h, i) => ({off: 0, clock: MOVE_S * (i + 1) / MUSEUM.homes.length}));
// where statue i stands: `off` steps from its plinth toward the middle of the hall
export function exhibitAt(i, off) { const [x, z] = MUSEUM.homes[i]; return [x - Math.sign(x) * (MUSEUM.plinth + 0.5) * Math.min(1, off) - Math.sign(x) * STEP_M * Math.max(0, off - 1), z]; }
// one step: `seen[i]` is whether statue i is in your view with a clear line. A watched statue's clock does not run; an unwatched one moves a step when its clock runs out.
export function stepExhibits(ex, dt, seen) {
  return ex.map((e, i) => {
    if (seen[i] || e.off >= MAX_OFF) return e;
    const clock = e.clock - dt; if (clock > 0) return {...e, clock};
    return {off: e.off + 1, clock: clock + MOVE_S};
  });
}
// F: the nearest moved statue within reach of (px, pz) goes back on its plinth; returns {ex, fixed: index or -1}
export function setBack(ex, px, pz) {
  let best = -1, bd = FIX_REACH;
  ex.forEach((e, i) => { if (!e.off) return; const [x, z] = exhibitAt(i, e.off), d = Math.hypot(x - px, z - pz); if (d < bd) { bd = d; best = i; } });
  if (best < 0) return {ex, fixed: -1};
  return {ex: ex.map((e, i) => i === best ? {off: 0, clock: MOVE_S} : e), fixed: best};
}
export const homeCount = ex => ex.filter(e => !e.off).length;
// how it ends: "done" = the shift ran its hours; "left" = you walked out early (no pay)
export function guardPay(ex, fixes, how) {
  const home = homeCount(ex), n = ex.length;
  if (how === "left") return {pay: 0, home, lines: ["You left your post before the end of the shift.", "Paid: $0"], note: "Museum: left early"};
  const fixPay = Math.min(GUARD.maxFixPay, Math.max(0, fixes) * GUARD.perFix), pay = home * GUARD.perHome + fixPay;
  return {pay, home, lines: [`Statues on their plinths: ${home} of ${n} ($${home * GUARD.perHome})`, `Set back during the night: ${fixes} (+$${fixPay})`, `Paid: $${pay}`], note: `Museum ${home}/${n}`};
}

// the collision file: floor, ceiling, walls and the six plinths (the statues are drawn, not solid)
export function museumColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = MUSEUM.half, cz = MUSEUM.cz, h = MUSEUM.h, t = 0.2, p = MUSEUM.plinth;
  add("Floor_Museum", [-hx - t, -1, cz - hz - t], [hx + t, 0, cz + hz + t]); add("Ceiling_Museum", [-hx - t, h, cz - hz - t], [hx + t, h + t, cz + hz + t]);
  add("Wall_N", [-hx - t, 0, cz - hz - t], [hx + t, h, cz - hz]); add("Wall_S", [-hx - t, 0, cz + hz], [hx + t, h, cz + hz + t]);
  // the wing's two doorways (scene galleries_wing): 1.8 m wide at z = -10, each long wall split into the piece south of it, the piece north (_N) and the head (_Head)
  const side = (s, x0, x1, top) => { const [z0, z1] = [MUSEUM.wing.z - MUSEUM.wing.w / 2, MUSEUM.wing.z + MUSEUM.wing.w / 2];
    add(s, [x0, 0, z1], [x1, h, cz + hz]); add(s + "_N", [x0, 0, cz - hz], [x1, h, z0]); add(s + "_Head", [x0, top, z0], [x1, h, z1]); };
  side("Wall_W", -hx - t, -hx, MUSEUM.wing.top.w); side("Wall_E", hx, hx + t, MUSEUM.wing.top.e);
  MUSEUM.homes.forEach(([x, z], i) => add("Plinth_" + i, [x - p, 0, z - p], [x + p, 0.6, z + p]));
  MUSEUM.exhibits.forEach(e => add(e.s, e.min, e.max));
  return c;
}
// the wing doorways' four closed leaves (build_galleries.py writes the same): hinge at each jamb, 0.896 m wide, swinging into the hall
const leaf = (name, x, z, height, yaw, swing) => ({name, level: "galleries", hinge: [x, 0, z], width: 0.896, height, closed_yaw_deg: yaw, swing_deg: swing, state: "closed"});
export const museumDoors = () => { const {z, w, top} = MUSEUM.wing, [z0, z1] = [z - w / 2, z + w / 2], hx = MUSEUM.half[0];
  return [leaf("DoorLeaf_wing_e_A", hx, z0, top.e, -90, -95), leaf("DoorLeaf_wing_e_B", hx, z1, top.e, 90, 95),
          leaf("DoorLeaf_wing_w_A", -hx, z0, top.w, -90, 95), leaf("DoorLeaf_wing_w_B", -hx, z1, top.w, 90, -95)]; };
export const museumDoc = () => ({scene: "galleries", colliders: museumColliders(), doors: museumDoors(), cameras: [],
  markers: [{name: "Spawn_door", kind: "Spawn", level: "galleries", position: MUSEUM.arrive}]});
