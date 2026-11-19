// The dreamcore forest and meadow (docs/WORLD.md, "Dreamcore forest and house"): road, then forest, then a meadow with the shed, then the house. The manifest's
// `dreamcore_forest` area, scenes `forest` and `meadow`. You reach the forest by the road from the parking lot (a signpost by the lot's north-west hedge, F, as the bus is
// taken); the forest's path runs north to a bright gap in the trees, and walking through it takes you into the meadow. In the meadow the shed stands beside the path and the
// house at its end: the house's door is Right Door, Wrong Exit (solo only, as its gate in the Overworld is), the shed is locked until its puzzle and addon exist.
// Both scenes are `presence` scenes: a room's players see each other walk there, and nothing else is shared. Pure here: the layout, the trees, the colliders and the zones;
// the page draws it (index.html, forestProps / meadowProps) and tools/make_street.mjs writes world/forest.json and world/meadow.json from it.

export const FOREST_Y = 0;

// a small seeded random (mulberry32), so every player gets the same trees in the same places
export function seeded(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6D2B79F5) >>> 0; let t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}

// ---- the forest: x in [-40, 40], z in [-100, 12]. You arrive at the road's end in the south, facing north; the path winds north to the gap at z = -94.
export const FOREST = {
  half: [40, 56], cz: -44,                                   // the ground: x in [-40, 40], z in [-100, 12]
  arrive: [0, 0, 6], face: [0, -1],                          // where the road from the lot leaves you
  back: {at: [2.6, 8.4], reach: 2.4},                        // the signpost back to the parking lot, beside the road's end
  gap: {z: -92, halfX: 4},                                   // walk north past z = -92 within 4 m of the path and you come out in the meadow
  fromMeadow: {arrive: [0, 0, -86], face: [0, 1]},           // where you stand when you walk back in from the meadow (south of the gap, facing back down the path)
  trees: 260, seed: 1919, clear: 4.2,                        // how many trees, their seed, and how far from the path's middle they keep
};
// the path's middle line: a slow S through the trees, straight at both ends so the road and the gap line up
export function pathX(z) {
  if (z > -6) return 0;
  if (z < -84) return 0;
  return 7 * Math.sin((z + 6) / 78 * Math.PI * 2) * Math.sin((z + 6) / 78 * Math.PI);
}

// ---- the meadow: x in [-45, 45], z in [-84, 12]. You come in from the forest in the south; the path runs north to the house; the shed stands west of the path.
export const MEADOW = {
  half: [45, 48], cz: -36,                                   // the ground: x in [-45, 45], z in [-84, 12]
  arrive: [0, 0, 6], face: [0, -1],                          // where you come out of the trees
  gap: {z: 9.5, halfX: 4},                                   // walk south past z = 9.5 within 4 m of the path and you are back in the forest
  // the shed (models/world/shed.glb): its front (+Z in the file) turned to face the path (+X); about 6.2 m tall
  shed: {at: [-15, -30], height: 6.2, yaw: Math.PI / 2, half: [3.0, 3.2], door: {at: [-11, -30], reach: 2.4}},
  // the house (models/world/cottage.glb): its front door (+X in the file) turned to face down the path (+Z); about 7.5 m tall
  house: {at: [0, -66], height: 7.5, yaw: -Math.PI / 2, half: [3.0, 3.6], door: {at: [0, -61.4], reach: 2.4}},
  returnHouse: {arrive: [0, 0, -57.5], face: [0, 1]},        // after Right Door, Wrong Exit: back on the path in front of the house, facing away from it
  trees: 120, seed: 2026, clear: 12,                         // a ring of trees round the edge (none within 12 m of the open meadow)
  flowers: 420, flowerSeed: 77,
};

// the forest's trees: [x, z, r] (r = trunk radius), seeded; none near the path, the arrival or the signpost
export function forestTrees() {
  const rnd = seeded(FOREST.seed), out = [], [hx, hz] = FOREST.half, z0 = FOREST.cz - hz, z1 = FOREST.cz + hz;
  let tries = 0;
  while (out.length < FOREST.trees && tries++ < 20000) {
    const x = (rnd() * 2 - 1) * (hx - 1.5), z = z0 + 1.5 + rnd() * (z1 - z0 - 3), r = 0.22 + rnd() * 0.18;
    if (Math.abs(x - pathX(z)) < FOREST.clear + r) continue;
    if (Math.hypot(x - FOREST.back.at[0], z - FOREST.back.at[1]) < 3) continue;
    if (out.some(([ox, oz]) => Math.hypot(ox - x, oz - z) < 2.2)) continue;
    out.push([+x.toFixed(2), +z.toFixed(2), +r.toFixed(2)]);
  }
  return out;
}
// the meadow's ring of trees: only near the edge, away from the open field
export function meadowTrees() {
  const rnd = seeded(MEADOW.seed), out = [], [hx, hz] = MEADOW.half, cz = MEADOW.cz;
  let tries = 0;
  while (out.length < MEADOW.trees && tries++ < 20000) {
    const x = (rnd() * 2 - 1) * (hx - 1.5), z = cz + (rnd() * 2 - 1) * (hz - 1.5), r = 0.22 + rnd() * 0.18;
    const edge = Math.min(hx - Math.abs(x), hz - Math.abs(z - cz));
    if (edge > 9) continue;                                                                 // the field stays open
    if (Math.abs(x) < 6 && z > cz + hz - 12) continue;                                     // the way back to the forest
    if (out.some(([ox, oz]) => Math.hypot(ox - x, oz - z) < 2.4)) continue;
    out.push([+x.toFixed(2), +z.toFixed(2), +r.toFixed(2)]);
  }
  return out;
}
// the meadow's flowers: [x, z, colour index 0..4], seeded, kept off the path and away from the buildings
export function meadowFlowers() {
  const rnd = seeded(MEADOW.flowerSeed), out = [], [hx, hz] = MEADOW.half, cz = MEADOW.cz;
  while (out.length < MEADOW.flowers) {
    const x = (rnd() * 2 - 1) * (hx - 10), z = cz + (rnd() * 2 - 1) * (hz - 10), c = Math.floor(rnd() * 5);
    if (Math.abs(x) < 1.8) continue;
    if (Math.abs(x - MEADOW.shed.at[0]) < 5 && Math.abs(z - MEADOW.shed.at[1]) < 5) continue;
    if (Math.abs(x - MEADOW.house.at[0]) < 6 && Math.abs(z - MEADOW.house.at[1]) < 7) continue;
    out.push([+x.toFixed(2), +z.toFixed(2), c]);
  }
  return out;
}

// is (x, z) in the gap that leads on? (the page checks it every frame)
export const inForestGap = (x, z) => z < FOREST.gap.z && Math.abs(x - pathX(z)) < FOREST.gap.halfX;
export const inMeadowGap = (x, z) => z > MEADOW.gap.z && Math.abs(x) < MEADOW.gap.halfX;

// the collision files: the ground, invisible walls round the edge (open only at the gaps, where the walk takes you on before you reach them), the trunks, and the buildings
function edgeWalls(add, hx, z0, z1, openN, openS) {
  const t = 0.4, h = 6;
  const wallZ = (name, z, open) => {
    if (!open) { add(name, [-hx - t, 0, z - t / 2], [hx + t, h, z + t / 2]); return; }
    add(name + "_w", [-hx - t, 0, z - t / 2], [-open, h, z + t / 2]); add(name + "_e", [open, 0, z - t / 2], [hx + t, h, z + t / 2]);
  };
  wallZ("Edge_N", z0, openN); wallZ("Edge_S", z1, openS);
  add("Edge_W", [-hx - t, 0, z0], [-hx, h, z1]); add("Edge_E", [hx, 0, z0], [hx + t, h, z1]);
}
export function forestColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = FOREST.half, z0 = FOREST.cz - hz, z1 = FOREST.cz + hz;
  add("Ground_Forest", [-hx - 1, -1, z0 - 1], [hx + 1, 0, z1 + 1]);
  edgeWalls(add, hx, z0, z1, 0, 0);                                                          // the gap's walk triggers at z = -92, well before the north edge at z = -100
  for (const [x, z, r] of forestTrees()) add("Trunk", [+(x - r).toFixed(2), 0, +(z - r).toFixed(2)], [+(x + r).toFixed(2), 4, +(z + r).toFixed(2)]);
  const [bx, bz] = FOREST.back.at; add("Signpost_lot", [bx - 0.1, 0, bz - 0.1], [bx + 0.1, 2.2, bz + 0.1]);
  return c;
}
export function meadowColliders() {
  const c = [], add = (s, min, max) => c.push({s, min, max}), [hx, hz] = MEADOW.half, z0 = MEADOW.cz - hz, z1 = MEADOW.cz + hz;
  add("Ground_Meadow", [-hx - 1, -1, z0 - 1], [hx + 1, 0, z1 + 1]);
  edgeWalls(add, hx, z0, z1, 0, 0);                                                          // the walk back triggers at z = 9.5, before the south edge at z = 12
  for (const [x, z, r] of meadowTrees()) add("Trunk", [+(x - r).toFixed(2), 0, +(z - r).toFixed(2)], [+(x + r).toFixed(2), 4, +(z + r).toFixed(2)]);
  for (const [name, b] of [["Shed", MEADOW.shed], ["House", MEADOW.house]]) {
    const [x, z] = b.at, [ax, az] = b.half;
    add(name, [x - ax, 0, z - az], [x + ax, b.height * 0.8, z + az]);
  }
  return c;
}
export const forestDoc = () => ({scene: "forest", colliders: forestColliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_road", kind: "Spawn", level: "forest", position: FOREST.arrive}]});
export const meadowDoc = () => ({scene: "meadow", colliders: meadowColliders(), doors: [], cameras: [],
  markers: [{name: "Spawn_path", kind: "Spawn", level: "meadow", position: MEADOW.arrive}]});

// the signpost in the parking lot (the Overworld's scene `parking_lot`, floor y 9.6), by the north-west hedge: F there walks you down the road to the forest
export const FOREST_ROAD_LOT = {at: [-30, 95.6], reach: 2.6, post: [-30, 96.6]};
