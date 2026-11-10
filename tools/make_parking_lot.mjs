// Makes world/parking_lot.json, the collision file for the Overworld's parking lot, from world/L4.json (the lot and the city set pieces are already in it).
// The lot is the same ground as L4's, so it keeps every collider; what changes is that the store cannot be entered (a solid block across the glass doors), there are
// no doors, cameras or stairs, and the spawn is the table. Usage: node tools/make_parking_lot.mjs   (rewrites world/parking_lot.json)
import fs from "node:fs";
import path from "node:path";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const l4 = JSON.parse(fs.readFileSync(path.join(root, "world/L4.json"), "utf8"));
const SPAWN = [-8.0, 9.6, 43.6];                                             // where you arrive: 2.6 m from the table at (-8, 41) (index.html OW_TABLE), facing the store. The same point as the manifest link's `arrive`.
const doc = {
  scene: "parking_lot",
  // the store is solid here: the glass doors are blocked by an invisible box (L4 does this in code until the power is on), and the stair door leaf is dropped with the doors
  colliders: [...l4.colliders, {s: "Block_store_doors", min: [-2.7, 9.6, 27.0], max: [2.7, 13.0, 27.5]}],
  doors: [], cameras: [],
  markers: [{name: "Spawn_table", kind: "Spawn", level: "parking_lot", position: SPAWN}, {name: "Store_doors", kind: "Entrance", level: "parking_lot", position: [0.0, 9.6, 28.5], width: 5.4}],
};
fs.writeFileSync(path.join(root, "world/parking_lot.json"), JSON.stringify(doc));
console.log(`world/parking_lot.json: ${doc.colliders.length} colliders`);
