// Makes the Going back in chamber world files from the floors they reuse (slice 1: art and collision are the Backrooms floors; the chamber rules are in the manifest).
// Usage: node tools/make_chambers.mjs   (rewrites world/gbi_L4_4.json and world/gbi_L3_1.json)
// - gbi_L4_4 is L4 with the store sealed (a solid block across the glass doors, as in the parking lot), the two game gates unlinked (no games from a chamber), and only the
//   stairs-down door linked, to gbi_L3_1.
// - gbi_L3_1 is L3 with no links at all: the way back up is closed behind you, and the way down is not built yet.
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
