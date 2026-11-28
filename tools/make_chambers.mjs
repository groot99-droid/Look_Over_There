// Makes the Going back in chamber world files from the floors they reuse (slice 1: art and collision are the Backrooms floors; the chamber rules are in the manifest).
// Usage: node tools/make_chambers.mjs   (rewrites world/gbi_L4_4.json, gbi_L3_1.json, gbi_L2_1.json, gbi_L1_1.json and gbi_B1_1.json)
// - gbi_L4_4 is L4 with the store sealed (a solid block across the glass doors, as in the parking lot), the two game gates unlinked (no games from a chamber), and only the
//   stairs-down door linked, to gbi_L3_1.
// - gbi_L3_1, gbi_L2_1, gbi_L1_1 and gbi_B1_1 are the first chamber of their floor (#123): the stairs from the floor above arrive in the store's real stairwell, the way back up is
//   closed behind you, and the floor's own stairs down are its way on, into chamber 2 (B1 has none: its way on is the F spot the manifest names, gbi.gbi_B1_1.sky_hall_north).
// A link here must match the manifest's built link (tools/manifest.mjs check compares them).
import fs from "node:fs";
import path from "node:path";
import {FARWAY} from "../shared/farway.manifest.js";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const read = f => JSON.parse(fs.readFileSync(path.join(root, `world/${f}.json`), "utf8"));
const write = (id, doc) => { fs.writeFileSync(path.join(root, `world/${id}.json`), JSON.stringify(doc)); console.log(`world/${id}.json: ${doc.colliders.length} colliders, ${doc.doors.filter(d => d.link).length} linked doors`); };
const links = FARWAY.links.filter(l => l.status === "built" && l.connector === "stair_door" && l.from.area === "gbi");
function make(id, srcId, {seal}) {
  const src = read(srcId), mine = links.filter(l => l.from.scene === id);
  const doors = src.doors.map(d => {
    const {link, ...rest} = d, l = mine.find(x => x.from.door === d.name);
    return l ? {...rest, link: {scene: l.to.scene, door: l.to.door, arrive: l.to.arrive, face: l.to.face}} : rest;
  });
  const colliders = seal ? [...src.colliders, {s: "Block_store_doors", min: [-2.7, 9.6, 27.0], max: [2.7, 13.0, 27.5]}] : src.colliders;
  write(id, {...src, scene: id, colliders, doors});
}
make("gbi_L4_4", "L4", {seal: true});
make("gbi_L3_1", "L3", {seal: false});
make("gbi_L2_1", "L2", {seal: false});
make("gbi_L1_1", "L1", {seal: false});
make("gbi_B1_1", "B1", {seal: false});
