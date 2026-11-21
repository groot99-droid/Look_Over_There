// Writes the layout a Blender build of a scene must match, so a build script never copies numbers by hand (docs/BLENDER.md).
// One JSON per scene: the collision file (world/<id>.json: colliders, doors, markers), the scene's constants from its shared module, and the seeded
// placements the page draws (the forest's and meadow's trees, the meadow's flowers, the forest's path, the street's buildings and lamps).
// Everything is in GAME coordinates (metres, y up). In Blender (z up) a game point (x, y, z) is (x, -z, y): the glTF exporter turns it back.
// Usage: node tools/blender/dump_layout.mjs [scene ...]      (no scene: every code-built scene)  -> blender/layout/<scene>.json
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import * as city from "../../shared/city.js";
import * as forest from "../../shared/forest.js";
import {MUSEUM} from "../../shared/museum.js";
import {FACTORY} from "../../shared/factory.js";
import {LAB} from "../../shared/lab.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const doc = id => JSON.parse(fs.readFileSync(path.join(root, `world/${id}.json`), "utf8"));
const pathSamples = () => { const out = []; for (let z = 12; z >= -100; z -= 1) out.push([+forest.pathX(z).toFixed(3), z]); return out; };

const SCENES = {
  apartment: () => ({constants: city.APARTMENT}),
  main_floor: () => ({constants: city.GROCERY, camera: city.CAMERA}),
  entrance: () => ({constants: city.MALL}),
  galleries: () => ({constants: MUSEUM}),
  factory_floor: () => ({constants: FACTORY}),
  laboratory: () => ({constants: LAB}),
  street: () => ({constants: {ROAD: city.ROAD, WORLD: city.WORLD, LAMP_ZS: city.LAMP_ZS, BUS_STREET: city.BUS_STREET}, buildings: city.BUILDINGS, doors: city.DOORS}),
  forest: () => ({constants: forest.FOREST, trees: forest.forestTrees(), path: pathSamples(), note: "trees are [x, z, trunk radius]; path is [x, z], the path's middle line"}),
  meadow: () => ({constants: forest.MEADOW, trees: forest.meadowTrees(), flowers: forest.meadowFlowers(), note: "trees are [x, z, trunk radius]; flowers are [x, z, colour index 0..4]; the shed and the house are the owner's models (models/world/), drawn by the page"}),
};

const want = process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SCENES);
fs.mkdirSync(path.join(root, "blender/layout"), {recursive: true});
for (const id of want) {
  if (!SCENES[id]) { console.error(`no layout for "${id}" (known: ${Object.keys(SCENES).join(", ")})`); process.exitCode = 1; continue; }
  const out = {scene: id, axes: "game: metres, y up. Blender: (x, -z, y)", ...SCENES[id](), world: doc(id)};
  fs.writeFileSync(path.join(root, `blender/layout/${id}.json`), JSON.stringify(out, null, 1));
  console.log(`blender/layout/${id}.json  ${out.world.colliders.length} colliders`);
}
