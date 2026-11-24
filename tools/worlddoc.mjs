// Checks a scene's layout file (world/<scene>.json) before it reaches the game: its shape, that every link, spot and spawn is somewhere a walker can stand, and its doors against
// the world manifest's links. Written for the files a Blender build exports (docs/BLENDER_AREAS.md); the rules are in shared/worlddoc.js.
// Usage: node tools/worlddoc.mjs check <file ...>     exit code 1 if any file has an error
//        node tools/worlddoc.mjs links <file>         the manifest stanzas the file's links call for, to paste into shared/farway.manifest.js and fill in
import fs from "node:fs";
import {checkWorldDoc, linkStanzas} from "../shared/worlddoc.js";
import {FARWAY} from "../shared/farway.manifest.js";

const [cmd, ...files] = process.argv.slice(2);
const read = f => JSON.parse(fs.readFileSync(f, "utf8"));
const areaOf = id => { for (const a of FARWAY.areas) for (const s of a.scenes || []) if (s.id === id) return a.id; return "AREA"; };
if (cmd === "check" && files.length) {
  let bad = 0;
  for (const f of files) {
    let doc; try { doc = read(f); } catch (e) { console.log(`FAILED ${f}: ${e.message}`); bad++; continue; }
    const {errors, warnings} = checkWorldDoc(doc, {manifest: FARWAY});
    for (const w of warnings) console.log(`  warning: ${w}`);
    for (const e of errors) console.log(`  ERROR: ${e}`);
    const n = k => (doc[k] || []).length;
    console.log(`${errors.length ? "FAILED" : "OK"} ${f}: ${n("colliders")} colliders, ${n("doors")} doors, ${n("markers")} markers, ${n("links")} links, ${n("zones")} zones, ${n("spots")} spots, ${errors.length} errors, ${warnings.length} warnings`);
    if (errors.length) bad++;
  }
  process.exit(bad ? 1 : 0);
} else if (cmd === "links" && files.length === 1) {
  const doc = read(files[0]); console.log(linkStanzas(doc, areaOf(doc.scene)) || "the file has no links");
} else { console.log("usage: node tools/worlddoc.mjs check <file ...> | links <file>"); process.exit(2); }
