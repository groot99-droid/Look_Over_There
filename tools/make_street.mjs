// Makes world/street.json, the collision file for the City's Hallam Row, from shared/city.js (the same layout the page draws).
// Usage: node tools/make_street.mjs   (rewrites world/street.json); shared/city.test.js fails if the file is out of date.
import fs from "node:fs";
import path from "node:path";
import {streetDoc} from "../shared/city.js";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
const doc = streetDoc();
fs.writeFileSync(path.join(root, "world/street.json"), JSON.stringify(doc));
console.log(`world/street.json: ${doc.colliders.length} colliders`);
