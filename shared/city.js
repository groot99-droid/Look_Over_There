// The City, v0 (session 9): Hallam Row's layout and the game-day clock. Pure data and functions, shared by the page (index.html draws it) and
// tools/make_street.mjs (which writes world/street.json, the collision file, from the same layout) and tested in shared/city.test.js.
// No art exists for the street yet: it is blockout geometry (boxes), and the owner will direct the art.

// ---- the clock. A game day is 15 real minutes. It starts at 08:00 on day 1, runs only while you are in the City (leaving pauses it), and is kept in memory (a reload starts at 08:00).
import {mailLines} from "./application.js";
import {FOODS, pantryLines} from "./needs.js";

export const DAY_S = 900;                       // real seconds per game day
export const START_H = 8;                       // the hour the first day starts at
export const OPEN_H = 8, CLOSE_H = 20;          // stores are open from 08:00 (when the day starts) until 20:00
export const DANGER_H = 0;                      // from midnight (until 06:00) the city turns dangerous (slice 2); 20:00 to midnight is the grace period
export const DAWN_H = 6;
const total = t => START_H + (Math.max(0, t) / DAY_S) * 24;
export const hourAt = t => total(t) % 24;                        // game hour 0..24 after t real seconds in the City
export const dayAt = t => 1 + Math.floor(total(t) / 24);
export const secondsAt = (hour, day = 1) => ((day - 1) * 24 + hour - START_H) / 24 * DAY_S;   // the City time at which it is `hour` on `day`
export function phaseAt(h) { return h >= CLOSE_H ? "evening" : h >= DAWN_H ? "day" : "night"; }   // evening: 20 to 24, stores shut, grace period; night: 0 to 6, danger
export const storesOpen = h => h >= OPEN_H && h < CLOSE_H;
export const dangerous = h => h >= DANGER_H && h < DAWN_H;       // used by slice 2
export function fmtClock(h) { const m = Math.floor(h * 60 + 1e-6) % 1440; return String(Math.floor(m / 60)).padStart(2, "0") + ":" + String(m % 60).padStart(2, "0"); }

// ---- the sky through the day: [hour, background colour, light intensity, light colour]; blended linearly between keys
const SKY = [[0, 0x05060f, 0.14, 0x6a78c0], [5, 0x0a0c1c, 0.2, 0x6a78c0], [6.5, 0xe49a6c, 0.9, 0xffc8a0], [9, 0x9ec8ee, 1.4, 0xfff6e0], [17, 0x9ec8ee, 1.4, 0xfff6e0],
  [19, 0xe8884e, 0.95, 0xffc088], [21, 0x10122a, 0.32, 0x7080c8], [24, 0x05060f, 0.14, 0x6a78c0]];
const mixHex = (a, b, k) => { let o = 0; for (const s of [16, 8, 0]) o |= Math.round(((a >> s) & 255) * (1 - k) + ((b >> s) & 255) * k) << s; return o; };
export function skyAt(h) {
  h = ((h % 24) + 24) % 24;
  let i = 0; while (i < SKY.length - 2 && h >= SKY[i + 1][0]) i++;
  const [h0, c0, l0, k0] = SKY[i], [h1, c1, l1, k1] = SKY[i + 1], k = Math.min(1, Math.max(0, (h - h0) / (h1 - h0)));
  return {bg: mixHex(c0, c1, k), light: l0 + (l1 - l0) * k, lightColor: mixHex(k0, k1, k), night: h >= CLOSE_H + 1 || h < DAWN_H};
}

// ---- Hallam Row. The street runs from the bus stop (z = 12) north to -z, floor at y = 0. The road is x in [-5, 5], the sidewalks 3 m each side, the buildings start at x = +-8.
export const FLOOR_Y = 0;
export const ROAD = {x0: -5, x1: 5, z0: -140, z1: 14}, WALK = 3, FRONT = 8;
// the bus stop on the street: you arrive on the east sidewalk, facing up the street, next to the shelter
export const BUS_STREET = {at: [6.2, 4.0], arrive: [3.6, 0, 4.0], face: [0, -1], radius: 3.4, shelter: [7.0, 5.0]};
// the bus stop in the Overworld's parking lot, beside the lot's own bus stop post (Post_stop2 at x -40, z 41): the shelter is built in index.html
export const BUS_LOT = {at: [-42.4, 44.2], radius: 3.4, shelter: [-43.4, 46.4]};
// kind: tower = the apartment tower (the way in is slice 2), store = closes at night, filler = no door. `n` is the job number where there is one.
export const BUILDINGS = [
  {id: "tower", side: "w", z0: -8, z1: -30, depth: 20, h: 38, color: 0x6c6a72, door: {kind: "tower", label: "APARTMENT TOWER", z: -19}},
  {id: "w41", side: "w", z0: -34, z1: -48, depth: 16, h: 9, color: 0x8a7a6a, door: {kind: "store", label: "41 HALLAM ROW", z: -41, job: "Trash truck worker", quiz: "trash"}},
  {id: "wfill1", side: "w", z0: -52, z1: -82, depth: 14, h: 11, color: 0x6a7480},
  {id: "w214", side: "w", z0: -88, z1: -102, depth: 16, h: 10, color: 0x7a8a86, door: {kind: "store", label: "214 HALLAM ROW", z: -95, job: "Laboratory worker", quiz: "lab"}},
  {id: "wfill2", side: "w", z0: -106, z1: -116, depth: 14, h: 8, color: 0x80726a},
  {id: "w666", side: "w", z0: -120, z1: -134, depth: 18, h: 13, color: 0x5a4a52, door: {kind: "store", label: "666 HALLAM ROW", z: -127, job: "The Intern", quiz: "intern"}},
  {id: "grocery", side: "e", z0: -8, z1: -26, depth: 24, h: 7, color: 0x7a9a78, door: {kind: "store", label: "GROCERY", z: -17}},
  {id: "e108", side: "e", z0: -34, z1: -48, depth: 16, h: 9, color: 0x8a6e7a, door: {kind: "store", label: "108 HALLAM ROW", z: -41, job: "Museum night guard", quiz: "museum"}},
  {id: "mall", side: "e", z0: -52, z1: -82, depth: 30, h: 12, color: 0x6a6a8a, door: {kind: "store", label: "MALL", z: -67}},
  {id: "e330", side: "e", z0: -88, z1: -102, depth: 16, h: 10, color: 0x8a8a6a, door: {kind: "store", label: "330 HALLAM ROW", z: -95, job: "Factory floor worker", quiz: "factory"}},
  {id: "efill", side: "e", z0: -106, z1: -134, depth: 14, h: 9, color: 0x707a70},
];
export const LAMP_ZS = [0, -20, -40, -60, -80, -100, -120];
export const DOOR_W = 1.8, DOOR_H = 2.5, WORLD = {x: 60, z0: -150, z1: 30};

export const sideX = side => side === "w" ? -FRONT : FRONT;
// the window panes on a building's street face (lit at night): floor f from 1, slot k along the front; none on the ground floor beside a door. Slice 21 shares this with the watchers.
export function windowSlots(b) {
  const out = [], fx = sideX(b.side), dir = b.side === "w" ? 1 : -1, zl = Math.min(b.z0, b.z1), zh = Math.max(b.z0, b.z1);
  for (let f = 1; f * 3.6 < b.h - 1; f++) { let k = 0; for (let z = zl + 1.5; z < zh - 1.2; z += 3.4, k++) { if (b.door && f === 1 && Math.abs(z + 0.8 - b.door.z) < 2.4) continue; out.push({f, k, x: fx + dir * 0.02, y: f * 3.6, z: z + 0.8, dir}); } }
  return out;
}
// every door of the street with where it is: the front plane is x = +-8, and you press E within `reach` of its centre
export const DOORS = BUILDINGS.filter(b => b.door).map(b => ({id: b.id, ...b.door, side: b.side, x: sideX(b.side), reach: 2.8}));
export const buildingBox = b => { const x = sideX(b.side), x0 = b.side === "w" ? x - b.depth : x, x1 = b.side === "w" ? x : x + b.depth; return {min: [x0, FLOOR_Y, Math.min(b.z0, b.z1)], max: [x1, FLOOR_Y + b.h, Math.max(b.z0, b.z1)]}; };

// the collision file's colliders: the ground, the buildings, the lamp posts, the shelter bench, and a wall round the edge so nobody walks off the world
export function colliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), r = v => Math.round(v * 1000) / 1000;
  add("Ground_Street", [-WORLD.x, FLOOR_Y - 1, WORLD.z0], [WORLD.x, FLOOR_Y, WORLD.z1]);
  for (const b of BUILDINGS) { const bx = buildingBox(b); add("Building_" + b.id, bx.min, bx.max); }
  for (const z of LAMP_ZS) for (const s of [-1, 1]) add("Lamp_Street", [s * 5.5 - 0.1, FLOOR_Y, z - 0.1], [s * 5.5 + 0.1, FLOOR_Y + 4.2, z + 0.1]);
  add("Bench_BusStop", [BUS_STREET.shelter[0] - 0.7, FLOOR_Y, BUS_STREET.shelter[1] - 0.3], [BUS_STREET.shelter[0] + 0.7, FLOOR_Y + 0.9, BUS_STREET.shelter[1] + 0.3]);
  add("Wall_W", [-WORLD.x - 1, FLOOR_Y, WORLD.z0], [-WORLD.x, FLOOR_Y + 14, WORLD.z1]);
  add("Wall_E", [WORLD.x, FLOOR_Y, WORLD.z0], [WORLD.x + 1, FLOOR_Y + 14, WORLD.z1]);
  add("Wall_N", [-WORLD.x, FLOOR_Y, WORLD.z0 - 1], [WORLD.x, FLOOR_Y + 14, WORLD.z0]);
  add("Wall_S", [-WORLD.x, FLOOR_Y, WORLD.z1], [WORLD.x, FLOOR_Y + 14, WORLD.z1 + 1]);
  return c.map(o => ({s: o.s, min: o.min.map(r), max: o.max.map(r)}));
}
export const streetDoc = () => ({scene: "street", colliders: colliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_bus", kind: "Spawn", level: "street", position: BUS_STREET.arrive}, ...DOORS.map(d => ({name: "Door_" + d.id, kind: "Entrance", level: "street", position: [d.x, FLOOR_Y, d.z], width: DOOR_W}))]});

// ---- the apartment (slice 2): your one room, reached from the apartment tower's door on the street. For v0 the tower door opens straight into it (the tower's lobby, atrium and floors are the
// hotel area, planned); the City's clock keeps running while you are inside. One room, a bed, a desk with the computer, a window onto the street's sky, and a door back out. Blockout, no art.
export const CITY_SCENES = ["street", "apartment", "main_floor", "entrance", "galleries", "factory_floor", "laboratory"];      // slice 13: and the mall; slice 14: the museum; slice 16: the factory; slice 17: the lab            // the scenes where the City's clock (and hunger) runs: the street, your apartment, the grocery
export const APARTMENT = {
  half: [3, 2.5], h: 2.8,                                      // the room is x in [-3, 3], z in [-2.5, 2.5], 2.8 m high
  arrive: [1.5, 0, 1.4], face: [0, -1],                        // you come in through the door on the south wall and face the room
  door: {at: [1.5, 2.1], reach: 1.8},                          // F near here leaves (the door is in the south wall at x = 1.5)
  bed: {min: [-2.9, 0, -2.4], max: [-0.9, 0.6, -0.4]},
  desk: {min: [0.9, 0, -2.4], max: [2.7, 0.78, -1.6]}, computer: {at: [1.8, -1.0], reach: 1.6},    // stand in front of the desk to use it
  fridge: {min: [-2.95, 0, 1.6], max: [-2.25, 1.8, 2.45], at: [-1.75, 2.0], reach: 1.2},       // slice 4: the fridge in the south-west corner, where your groceries go
  window: {x: 2.98, z: [-1.4, 0.6], y: [1.0, 2.2]},            // on the east wall; shows the sky of the hour
};
// the tower's door on the street leads to the apartment, and the apartment's door leads back to the tower's front: both are links in the manifest and these are what they say
export const TOWER_FRONT = {arrive: [-6.2, 0, -19], face: [1, 0]};
export function apartmentColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = APARTMENT.half, h = APARTMENT.h, t = 0.2;
  add("Floor_Apartment", [-hx - t, -1, -hz - t], [hx + t, 0, hz + t]); add("Ceiling_Apartment", [-hx - t, h, -hz - t], [hx + t, h + t, hz + t]);
  add("Wall_N", [-hx - t, 0, -hz - t], [hx + t, h, -hz]); add("Wall_S", [-hx - t, 0, hz], [hx + t, h, hz + t]);
  add("Wall_W", [-hx - t, 0, -hz], [-hx, h, hz]); add("Wall_E", [hx, 0, -hz], [hx + t, h, hz]);
  add("Bed", APARTMENT.bed.min, APARTMENT.bed.max); add("Desk", APARTMENT.desk.min, APARTMENT.desk.max); add("Fridge", APARTMENT.fridge.min, APARTMENT.fridge.max);
  return c;
}
export const apartmentDoc = () => ({scene: "apartment", colliders: apartmentColliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_door", kind: "Spawn", level: "apartment", position: APARTMENT.arrive}, {name: "Computer", kind: "Interact", level: "apartment", position: [APARTMENT.computer.at[0], 0, APARTMENT.computer.at[1]]}]});

// ---- the grocery (slice 4): the manifest's `grocery` area, scene `main_floor`, behind the street's grocery door. Open by day (08:00 to 20:00, like the other stores); at closing you are shown out.
// One hall, x in [-12, 12], z in [-9, 9], 4 m high. The way in is the south wall; a cart corral by the door, four shelf units (one food each) and a checkout counter. Blockout, no art.
export const GROCERY = {
  half: [12, 9], h: 4,
  arrive: [0, 0, 7.4], face: [0, -1],
  door: {at: [0, 8.3], reach: 1.6},
  cart: {at: [-4.5, 7.2], reach: 1.5, min: [-6.2, 0, 7.6], max: [-5.0, 1.0, 8.8]},          // the corral by the door: take a cart from here
  checkout: {at: [6.5, 5.6], reach: 1.7, min: [5.5, 0, 6.4], max: [9.5, 0.95, 7.2]},
  shelves: FOODS.map((f, i) => { const x = -8 + i * 5; return {food: f.id, min: [x - 0.6, 0, -6], max: [x + 0.6, 1.9, 2], at: [x + 1.4, -2], reach: 1.6}; }),   // aisles run north-south; stand on the east side of a unit
};
// slice 19: the security camera, high on the north wall, sweeping to and fro across the store. Its angle follows the City's clock: 0 looks straight down the hall at the door,
// and it swings `sweep` degrees each way over `period` seconds. It sees a point inside its `fov` cone, within `range`. It watches the door about a third of the time.
export const CAMERA = {at: [0, 3.4, -8.7], period: 12, sweep: 40, fov: 40, range: 25};
export const camYaw = t => CAMERA.sweep * Math.sin(2 * Math.PI * t / CAMERA.period);            // degrees; + turns toward +x
export function camSees(t, x, z) {
  const dx = x - CAMERA.at[0], dz = z - CAMERA.at[2]; if (Math.hypot(dx, dz) > CAMERA.range) return false;
  return Math.abs(Math.atan2(dx, dz) * 180 / Math.PI - camYaw(t)) <= CAMERA.fov / 2;
}
// the first City time at or after t when the camera does (or does not) see (x, z): for the tests, and for anyone timing a dash for the door
export function nextCam(t, x, z, want) { for (let k = 0; k <= CAMERA.period * 20; k++) { const u = t + k / 20; if (camSees(u, x, z) === want) return u; } return null; }
export const GROCERY_FRONT = {arrive: [6.2, 0, -17], face: [-1, 0]};            // where you stand on the street when you come out (the grocery door is on the east side at z = -17)
export function groceryColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = GROCERY.half, h = GROCERY.h, t = 0.2;
  add("Floor_Grocery", [-hx - t, -1, -hz - t], [hx + t, 0, hz + t]); add("Ceiling_Grocery", [-hx - t, h, -hz - t], [hx + t, h + t, hz + t]);
  add("Wall_N", [-hx - t, 0, -hz - t], [hx + t, h, -hz]); add("Wall_S", [-hx - t, 0, hz], [hx + t, h, hz + t]);
  add("Wall_W", [-hx - t, 0, -hz], [-hx, h, hz]); add("Wall_E", [hx, 0, -hz], [hx + t, h, hz]);
  for (const sh of GROCERY.shelves) add("Shelf_" + sh.food, sh.min, sh.max);
  add("Checkout", GROCERY.checkout.min, GROCERY.checkout.max); add("Cart_corral", GROCERY.cart.min, GROCERY.cart.max);
  return c;
}
export const groceryDoc = () => ({scene: "main_floor", colliders: groceryColliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_door", kind: "Spawn", level: "main_floor", position: GROCERY.arrive}, {name: "Checkout", kind: "Interact", level: "main_floor", position: [GROCERY.checkout.at[0], 0, GROCERY.checkout.at[1]]}]});

// ---- the mall (slice 13): "The mall can lock you in" (docs/WORLD.md). The manifest's `mall` area, scene `entrance`, behind the street's MALL door. You can go in while the stores
// are open (08:00 to 20:00); unlike the grocery, nobody shows you out: at 20:00 the doors lock with you inside, until dawn (06:00). Hunger and rest go on counting. Two benches
// in the atrium let you sleep through to dawn (they do not save: the bed at home is the only save point). One atrium, x in [-16, 16], z in [-12, 12], 7 m high, a dry fountain
// in the middle and shuttered shopfronts round the walls. Blockout, no art.
export const MALL = {
  half: [16, 12], h: 7,
  arrive: [0, 0, 10.4], face: [0, -1],
  door: {at: [0, 11.3], reach: 1.8},
  fountain: {min: [-2.5, 0, -4.5], max: [2.5, 0.7, 0.5]},
  benches: [-8, 8].map(x => ({min: [x - 1.2, 0, -1.35], max: [x + 1.2, 0.5, -0.65], at: [x, 0.2], reach: 1.6})),          // stand on the south side of a bench
  shops: ["SHOES", "PHONES", "FOOD COURT", "CLOSED FOR RENOVATION", "GIFTS", "PHOTO", "OPTICIAN", "TOYS"],                     // shuttered fronts: four on the north wall, two on each side
};
export const MALL_FRONT = {arrive: [6.2, 0, -67], face: [-1, 0]};               // where you stand on the street when you come out (the MALL door is on the east side at z = -67)
export const mallLocked = h => h >= CLOSE_H || h < DAWN_H;                   // locked from 20:00 to 06:00; you can only go in while the stores are open (storesOpen)
export const mallUnlocks = t => secondsAt(DAWN_H, dayAt(t) + (hourAt(t) >= DAWN_H ? 1 : 0));   // the City time the doors open again: the next 06:00
export function mallColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = MALL.half, h = MALL.h, t = 0.2;
  add("Floor_Mall", [-hx - t, -1, -hz - t], [hx + t, 0, hz + t]); add("Ceiling_Mall", [-hx - t, h, -hz - t], [hx + t, h + t, hz + t]);
  add("Wall_N", [-hx - t, 0, -hz - t], [hx + t, h, -hz]); add("Wall_S", [-hx - t, 0, hz], [hx + t, h, hz + t]);
  add("Wall_W", [-hx - t, 0, -hz], [-hx, h, hz]); add("Wall_E", [hx, 0, -hz], [hx + t, h, hz]);
  add("Fountain", MALL.fountain.min, MALL.fountain.max);
  MALL.benches.forEach((b, i) => add("Bench_" + i, b.min, b.max));
  return c;
}
export const mallDoc = () => ({scene: "entrance", colliders: mallColliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_door", kind: "Spawn", level: "entrance", position: MALL.arrive}]});

// ---- the computer: what its pages say. `st` is {hour, day, clock, open}; `apps` is the applications state of shared/application.js (optional). Pure, so it is tested; the page only draws the strings. Job search lists the five Hallam Row jobs but applications open later (slice 3).
export const JOBS = BUILDINGS.filter(b => b.door && b.door.job).map(b => ({id: b.id, address: b.door.label, job: b.door.job, quiz: b.door.quiz || null}));      // quiz: the key in shared/application.js (only the Intern has one so far)
export const JOB_FRONT = {arrive: [-6.2, 0, -127], face: [1, 0]};            // where you stand when you come back out of your shift at 666 Hallam Row
// the save's time as the computer shows it (slice 9): `t` is the saved City time, or null when nothing is saved
export const savedLine = t => t === null || t === undefined ? "Not saved yet. The bed in your apartment saves." : `Last saved: Day ${dayAt(t)}, ${fmtClock(hourAt(t))}.`;
// savedT (slice 9): the saved City time, null for no save, undefined when the caller does not say (then the bank and system pages leave the line out)
// seen (slice 15): the anomalies spotted and reported (shared/anomalies.js), for the REPORT page; the page draws one button per report
export function computerPages(st, apps = null, needs = null, savedT = undefined, seen = null) {
  const left = st.open ? Math.max(0, CLOSE_H - st.hour) : 0, hh = Math.floor(left), mm = Math.round((left - hh) * 60), mine = apps ? mailLines(apps, st.day) : [];
  const tag = j => !j.quiz ? " (not hiring yet)" : apps && apps.accepted[j.quiz] ? " (ACCEPTED)" : apps && apps.rejectedOn[j.quiz] !== undefined && apps.rejectedOn[j.quiz] >= st.day ? " (rejected: try again tomorrow)" : " (hiring: apply below)";
  return {
    mail: {title: "MAIL", lines: mine.length ? mine : ["No new messages.", "", "(Your inbox is empty. Offers and replies will arrive here once you apply for a job.)"]},
    news: {title: "NEWS", lines: [`Day ${st.day}, ${st.clock}.`, st.open ? `Hallam Row's stores are open for another ${hh} h ${String(mm).padStart(2, "0")} min.` : st.hour >= CLOSE_H || st.hour < DAWN_H ? "The stores on Hallam Row are closed for the night." : "The stores on Hallam Row are not open yet.", "Residents are reminded to be home before midnight."]},
    jobs: {title: "JOB SEARCH", lines: [...JOBS.map(j => `${j.address}: ${j.job}${tag(j)}`), "", "One application at a time."]},
    map: {title: "MAP", lines: ["HALLAM ROW", "West side: apartment tower, 41, 214, 666", "East side: grocery, 108, mall, 330", "The bus stop is at the south end."]},
    bank: {title: "BANK", lines: needs ? ["Balance: $" + needs.money, ...(savedT === undefined ? [] : [savedLine(savedT)]), needs.lastPay !== null && needs.lastPay !== undefined ? "Last shift: +$" + needs.lastPay + (needs.lastNote ? " (" + needs.lastNote + ")" : "") : "No pay yet. A shift at your job pays.", "", "IN YOUR FRIDGE", ...(pantryLines(needs).length ? pantryLines(needs) : ["Nothing."])] : ["Balance unknown."]},
    report: {title: "REPORT", lines: ["Seen something on Hallam Row that should not be there? Report it.", "A true report of something you have seen yourself pays $5. A false report costs $2.", "", seen ? `Reports filed: ${Object.keys(seen.reported).length}.` : ""]},
    system: {title: "SYSTEM", lines: [...(savedT === undefined ? [] : [savedLine(savedT), ""]), "NEW GAME forgets the City: the save, your jobs, your money, the fridge and the clock.", "The Original and the Overworld are kept."]},
  };
}

// ---- the night danger (slice 2b). From midnight to 06:00 (`dangerous`) one stalker walks Hallam Row. It is the City's creature: it never moves while you are looking at it, it creeps toward you when you
// are not, it cannot be killed (it is not one of the floor's monsters, so no gun or beacon touches it), and if it reaches you, you black out and wake in your apartment at 06:00. The apartment is safe.
// It is faster than a walk (4 m/s) and slower than a run (7.5 m/s): you cannot just walk home with your back to it, you have to turn round and look. Pure rules here; index.html draws it and calls them.
export const STALKER = {speed: 5.5, spawnDist: 28, minSpawn: 14, catchDist: 1.5, fovDeg: 38, seeDist: 80, firstWait: 6};   // m/s, metres, degrees, seconds (the wait after midnight or after you step out before it appears)
const clampTo = (v, a, b) => Math.min(b, Math.max(a, v));
// is (sx, sz) inside the cone you are looking along? yaw is the page's: you face (-sin yaw, -cos yaw)
export function inView(px, pz, yaw, sx, sz, fovDeg = STALKER.fovDeg) {
  const dx = sx - px, dz = sz - pz, d = Math.hypot(dx, dz); if (d < 1e-6) return true;
  return (dx * -Math.sin(yaw) + dz * -Math.cos(yaw)) / d >= Math.cos(fovDeg * Math.PI / 180);
}
// where it appears: out of view, on the road, 14 to 28 m along the street from you (behind you first); null if there is no such spot (it tries again next tick)
export function stalkerSpawn(px, pz, yaw) {
  for (const dz of [-Math.cos(yaw) < 0 ? STALKER.spawnDist : -STALKER.spawnDist, -Math.cos(yaw) < 0 ? -STALKER.spawnDist : STALKER.spawnDist]) {
    const z = clampTo(pz + dz, ROAD.z0 + 3, ROAD.z1 - 3), x = clampTo(px, -4, 4);
    if (Math.hypot(x - px, z - pz) >= STALKER.minSpawn && !inView(px, pz, yaw, x, z)) return {x, z};
  }
  return null;
}
// one step: s is {active, x, z, wait}; o is {px, pz, yaw, seen (it is in view with a clear line), danger (dangerous hour and you are on the street)}. Returns the new state and whether it caught you.
export function stalkerStep(s, dt, o) {
  if (!o.danger) return {active: false, x: s.x, z: s.z, wait: STALKER.firstWait, caught: false};          // by day, indoors, or after dawn it is gone, and starts its wait again next time
  if (!s.active) {
    const wait = s.wait - dt; if (wait > 0) return {...s, wait, caught: false};
    const at = stalkerSpawn(o.px, o.pz, o.yaw); return at ? {active: true, x: at.x, z: at.z, wait: 0, caught: false} : {...s, wait: 0, caught: false};
  }
  if (o.seen) return {...s, caught: false};                                                                // seen: it does not move
  const dx = o.px - s.x, dz = o.pz - s.z, d = Math.hypot(dx, dz), k = Math.min(d, STALKER.speed * dt) / (d || 1), x = s.x + dx * k, z = s.z + dz * k;
  return {...s, x, z, caught: Math.hypot(o.px - x, o.pz - z) <= STALKER.catchDist};
}
// the City time (seconds) of the next 06:00 after t: what the bed skips to, and when you wake after a blackout
// ---- the stalker follows you (slice 10): "It is the only monster that follows between areas" (docs/WORLD.md). At night the only places open are the street and your apartment,
// so following means it does not go away when you go in: it waits outside the tower's door, 14 m up or down the street (the side it was on), and is there when you step out.
// The apartment stays safe. It is still gone at dawn, after you sleep and after a blackout, and it does not follow you anywhere but between the street and the apartment.
export const STALKER_WAIT = STALKER.minSpawn;                                              // metres from the tower door's arrival spot
export function stalkerWaitAt(sx, sz, front = TOWER_FRONT.arrive) {
  const side = sz > front[2] ? 1 : -1;                                                     // down the street (toward the bus stop) or up it
  return {x: clampTo(sx, -4, 4), z: clampTo(front[2] + side * STALKER_WAIT, ROAD.z0 + 3, ROAD.z1 - 3)};
}
// what a scene change does to the stalker: s is its state, hour the City's hour, to the scene you are going to
export function carryStalker(s, hour, to) {
  const fresh = {active: false, x: 0, z: 0, wait: STALKER.firstWait};
  if (!s || !s.active || !dangerous(hour)) return fresh;
  if (to === "apartment") return {active: true, ...stalkerWaitAt(s.x, s.z), wait: 0, waited: true};
  if (to === "street") return {active: true, x: s.x, z: s.z, wait: 0, waited: !!s.waited};
  return fresh;
}
export const nextMorning = t => secondsAt(DAWN_H, dayAt(t) + (hourAt(t) >= DAWN_H ? 1 : 0));
export const bedUse = {at: [-1.4, 0.3], reach: 1.5};            // F here sleeps (from 20:00; by day you are not tired)
