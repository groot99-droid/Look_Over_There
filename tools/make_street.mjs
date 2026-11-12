// Makes world/street.json and world/apartment.json, the collision files for the City's Hallam Row and your apartment, from shared/city.js (the same layout the page draws).
// Usage: node tools/make_street.mjs   (rewrites both); shared/city.test.js fails if the file is out of date.
import fs from "node:fs";
import path from "node:path";
import {streetDoc, apartmentDoc, groceryDoc, mallDoc} from "../shared/city.js";
import {museumDoc} from "../shared/museum.js";
import {factoryDoc} from "../shared/factory.js";
const root = path.resolve(path.dirname(new URL(import.meta.url).pathname), "..");
for (const [name, doc] of [["street", streetDoc()], ["apartment", apartmentDoc()], ["main_floor", groceryDoc()], ["entrance", mallDoc()], ["galleries", museumDoc()], ["factory_floor", factoryDoc()]]) {
  fs.writeFileSync(path.join(root, `world/${name}.json`), JSON.stringify(doc));
  console.log(`world/${name}.json: ${doc.colliders.length} colliders`);
}
