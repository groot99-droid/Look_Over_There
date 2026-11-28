// The street's extra layout for its Blender build (tools/blender/build_street.py): what the page draws on Hallam Row besides the collision file, so the build
// leaves those spots clear and puts the window panes exactly where the page's watchers look out (docs/BLENDER.md, "7. street"). dump_layout.mjs writes the
// colliders, buildings, doors and lamps; this adds the window slots of every building (shared/city.js windowSlots), the door's size, the PHARMACY sign, the
// ghost window, the watchers' windows and the pedestrians (shared/anomalies.js). Everything is in GAME coordinates (metres, y up).
// Usage: node tools/blender/street_extras.mjs     -> blender/layout/street_extra.json (git ignores that folder)
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {BUILDINGS, windowSlots, DOOR_W, DOOR_H, WALK, FRONT} from "../../shared/city.js";
import {SIGN, GHOST_WINDOW, WATCHERS, watcherAt, PEDESTRIANS} from "../../shared/anomalies.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const out = {
  scene: "street",
  note: "window slots: f = floor from 1, k = slot along the front, (x, y, z) the pane's centre (the page draws a 1.6 x 1.3 m pane there), dir = +1 when the face looks +x",
  door: {w: DOOR_W, h: DOOR_H}, walk: WALK, front: FRONT,
  windows: Object.fromEntries(BUILDINGS.map(b => [b.id, windowSlots(b)])),
  sign: SIGN, ghost_window: GHOST_WINDOW,
  watchers: WATCHERS.map(w => ({...w, at: watcherAt(w)})),
  pedestrians: PEDESTRIANS,
};
fs.mkdirSync(path.join(root, "blender/layout"), {recursive: true});
fs.writeFileSync(path.join(root, "blender/layout/street_extra.json"), JSON.stringify(out, null, 1));
console.log(`blender/layout/street_extra.json  ${Object.values(out.windows).reduce((n, w) => n + w.length, 0)} window slots, ${out.watchers.length} watchers`);
