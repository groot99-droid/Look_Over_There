// The City, v0 (session 9): Hallam Row's layout and the game-day clock. Pure data and functions, shared by the page (index.html draws it) and
// tools/make_street.mjs (which writes world/street.json, the collision file, from the same layout) and tested in shared/city.test.js.
// No art exists for the street yet: it is blockout geometry (boxes), and the owner will direct the art.

// ---- the clock. A game day is 15 real minutes. It starts at 08:00 on day 1, runs only while you are in the City (leaving pauses it), and is kept in memory (a reload starts at 08:00).
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
  {id: "w41", side: "w", z0: -34, z1: -48, depth: 16, h: 9, color: 0x8a7a6a, door: {kind: "store", label: "41 HALLAM ROW", z: -41, job: "Trash truck worker"}},
  {id: "wfill1", side: "w", z0: -52, z1: -82, depth: 14, h: 11, color: 0x6a7480},
  {id: "w214", side: "w", z0: -88, z1: -102, depth: 16, h: 10, color: 0x7a8a86, door: {kind: "store", label: "214 HALLAM ROW", z: -95, job: "Laboratory worker"}},
  {id: "wfill2", side: "w", z0: -106, z1: -116, depth: 14, h: 8, color: 0x80726a},
  {id: "w666", side: "w", z0: -120, z1: -134, depth: 18, h: 13, color: 0x5a4a52, door: {kind: "store", label: "666 HALLAM ROW", z: -127, job: "The Intern"}},
  {id: "grocery", side: "e", z0: -8, z1: -26, depth: 24, h: 7, color: 0x7a9a78, door: {kind: "store", label: "GROCERY", z: -17}},
  {id: "e108", side: "e", z0: -34, z1: -48, depth: 16, h: 9, color: 0x8a6e7a, door: {kind: "store", label: "108 HALLAM ROW", z: -41, job: "Museum night guard"}},
  {id: "mall", side: "e", z0: -52, z1: -82, depth: 30, h: 12, color: 0x6a6a8a, door: {kind: "store", label: "MALL", z: -67}},
  {id: "e330", side: "e", z0: -88, z1: -102, depth: 16, h: 10, color: 0x8a8a6a, door: {kind: "store", label: "330 HALLAM ROW", z: -95, job: "Factory floor worker"}},
  {id: "efill", side: "e", z0: -106, z1: -134, depth: 14, h: 9, color: 0x707a70},
];
export const LAMP_ZS = [0, -20, -40, -60, -80, -100, -120];
export const DOOR_W = 1.8, DOOR_H = 2.5, WORLD = {x: 60, z0: -150, z1: 30};

export const sideX = side => side === "w" ? -FRONT : FRONT;
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
