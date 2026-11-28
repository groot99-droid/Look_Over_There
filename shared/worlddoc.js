// The check for a scene's layout file (world/<scene>.json), written for the files a Blender build exports (docs/BLENDER_AREAS.md, tools/blender/export_scene.py) and true of the
// ones the repo already has. Pure: no file access, no page. tools/worlddoc.mjs runs it; shared/worlddoc.test.js holds every existing world file to it.
// A layout file has `scene`, `colliders`, `doors`, `cameras` and `markers` (what the page reads), and a Blender-first one may add `links`, `zones` and `spots` (what the coordinator
// wires into the manifest and the page). All positions are game coordinates: metres, y up.
//   colliders [{s, min: [x, y, z], max: [x, y, z]}]            axis-aligned boxes; `s` names what it came from
//   doors     [{name, level, hinge: [x, y, z], width, height, closed_yaw_deg, swing_deg, state: "open" | "ajar" | "closed", link?}]
//   markers   [{name, kind: Spawn | Entrance | Exit | Interact, level, position: [x, y, z]}]
//   links     [{door, at: [x, y, z], arrive: [x, y, z], face: [fx, fz]}]     `at` is where you press F; `arrive` and `face` are where you stand, and the way you look, after coming IN by it
//   zones     [{kind: water | safe | restricted | trigger | hazard, name, min, max}]
//   spots     [{kind, name, position: [x, y, z]}]               where the page puts something: a locker, a shop, a dealer, a puzzle, loot, a monster, ...

export const MARKER_KINDS = ["Spawn", "Entrance", "Exit", "Interact"];
export const ZONE_KINDS = ["water", "safe", "restricted", "trigger", "hazard"];
export const DOOR_STATES = ["open", "ajar", "closed"];
export const WALKER_R = 0.28;                                    // the walker's radius, as the page and the Blender layout check use it
export const MAX_EXTENT = 60;                                    // one indoor scene should not be much larger than a store floor (about 52 m by 50 m)

const isNum = v => typeof v === "number" && Number.isFinite(v);
const isVec = (v, n) => Array.isArray(v) && v.length === n && v.every(isNum);
const isName = v => typeof v === "string" && v.length > 0;
const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);
const fmt = p => `(${p.map(v => +v.toFixed(2)).join(", ")})`;

// is a walker standing at p = [x, y, z] inside a collider? (between knee and head height, so a floor or a step under the feet does not count)
export function blocked(colliders, p, r = WALKER_R) {
  const [x, y, z] = p;
  return colliders.find(c => c.min[1] < y + 1.5 && c.max[1] > y + 0.5 && x > c.min[0] - r && x < c.max[0] + r && z > c.min[2] - r && z < c.max[2] + r) || null;
}
// is there a collider's top under p's feet? (within 6 cm)
export const onFloor = (colliders, p) => colliders.some(c => Math.abs(c.max[1] - p[1]) <= 0.06 && p[0] >= c.min[0] && p[0] <= c.max[0] && p[2] >= c.min[2] && p[2] <= c.max[2]);

// {errors, warnings} for one layout file. `manifest` (the world manifest's document) adds the comparison with its links.
export function checkWorldDoc(doc, {manifest = null} = {}) {
  const errors = [], warnings = [], err = m => errors.push(m), warn = m => warnings.push(m);
  if (!isObj(doc)) return {errors: ["the file is not an object"], warnings};
  if (!isName(doc.scene)) err("scene: needs a scene id");
  for (const k of ["colliders", "doors", "cameras", "markers"]) if (!Array.isArray(doc[k])) err(`${k}: must be a list (it may be empty)`);
  for (const k of ["links", "zones", "spots"]) if (doc[k] !== undefined && !Array.isArray(doc[k])) err(`${k}: must be a list when it is there`);
  if (errors.length) return {errors, warnings};
  const blenderFirst = ["links", "zones", "spots"].some(k => doc[k] !== undefined);             // the older files (from the store's Blender file, or made by code) carry none of these
  const links = doc.links || [], zones = doc.zones || [], spots = doc.spots || [];

  const box = (at, c) => { const ok = isVec(c.min, 3) && isVec(c.max, 3); if (!ok) err(`${at}: min and max must be three numbers each`); else if (c.min.some((v, i) => v >= c.max[i])) err(`${at}: min must be below max on every axis`); return ok; };
  const good = [];                                                                                // the colliders the position checks can use
  doc.colliders.forEach((c, i) => { const at = `collider ${i}${isObj(c) && isName(c.s) ? ` (${c.s})` : ""}`; if (!isObj(c) || !isName(c.s)) return err(`${at}: needs a name in s`); if (box(at, c) && c.min.every((v, j) => v < c.max[j])) good.push(c); });

  const unique = (list, key, what, report) => { const seen = new Set(); for (const o of list) { if (!isObj(o) || !isName(o[key])) continue; if (seen.has(o[key])) report(`${what} ${o[key]}: the name is used twice`); seen.add(o[key]); } };
  doc.doors.forEach((d, i) => {
    const at = `door ${isObj(d) && isName(d.name) ? d.name : i}`;
    if (!isObj(d) || !isName(d.name)) return err(`${at}: needs a name`);
    if (!isVec(d.hinge, 3)) err(`${at}: hinge must be three numbers`);
    for (const k of ["width", "height"]) if (!(isNum(d[k]) && d[k] > 0)) err(`${at}: ${k} must be a positive number`);
    for (const k of ["closed_yaw_deg", "swing_deg"]) if (!isNum(d[k])) err(`${at}: ${k} must be a number`);
    if (!DOOR_STATES.includes(d.state)) err(`${at}: state must be one of ${DOOR_STATES.join(", ")}`);
    if (d.link !== undefined && !isObj(d.link)) err(`${at}: link must be an object`);
  });
  unique(doc.doors, "name", "door", err);
  doc.markers.forEach((m, i) => {
    const at = `marker ${isObj(m) && isName(m.name) ? m.name : i}`;
    if (!isObj(m) || !isName(m.name)) return err(`${at}: needs a name`);
    if (!MARKER_KINDS.includes(m.kind)) err(`${at}: kind must be one of ${MARKER_KINDS.join(", ")}`);
    if (!isVec(m.position, 3)) err(`${at}: position must be three numbers`);
  });
  unique(doc.markers, "name", "marker", blenderFirst ? err : warn);
  doc.cameras.forEach((c, i) => { if (!isObj(c) || !isName(c.id) || !isVec(c.position, 3)) err(`camera ${isObj(c) && isName(c.id) ? c.id : i}: needs an id and a position of three numbers`); });

  // where a walker must be able to stand: clear of the colliders, with a floor under the feet
  const stand = (at, p, report = err) => {
    const b = blocked(good, p); if (b) report(`${at} ${fmt(p)}: inside the collider ${b.s}`);
    else if (!onFloor(good, p)) report(`${at} ${fmt(p)}: no floor under it (no collider's top within 6 cm of its height)`);
  };
  links.forEach((l, i) => {
    const at = `link ${isObj(l) && isName(l.door) ? l.door : i}`;
    if (!isObj(l) || !isName(l.door)) return err(`${at}: needs a door id`);
    if (!isVec(l.at, 3)) err(`${at}: at must be three numbers (where you press F)`); else stand(`${at}: at`, l.at);
    if (!isVec(l.arrive, 3)) err(`${at}: arrive must be three numbers (a Link_ needs its Arrive_)`); else stand(`${at}: arrive`, l.arrive);
    if (!isVec(l.face, 2)) err(`${at}: face must be two numbers [fx, fz]`); else if (Math.abs(Math.hypot(...l.face) - 1) > 0.01) err(`${at}: face must have length 1`);
  });
  unique(links, "door", "link", err);
  zones.forEach((z, i) => {
    const at = `zone ${isObj(z) && isName(z.name) ? z.name : i}`;
    if (!isObj(z) || !isName(z.name)) return err(`${at}: needs a name`);
    if (!ZONE_KINDS.includes(z.kind)) err(`${at}: kind must be one of ${ZONE_KINDS.join(", ")}`);
    box(at, z);
  });
  unique(zones, "name", "zone", err);
  spots.forEach((s, i) => {
    const at = `spot ${isObj(s) && isName(s.name) ? s.name : i}`;
    if (!isObj(s) || !isName(s.name)) return err(`${at}: needs a name`);
    if (!isName(s.kind)) err(`${at}: needs a kind`);
    if (!isVec(s.position, 3)) err(`${at}: position must be three numbers`); else stand(at, s.position);
  });
  unique(spots, "name", "spot", err);
  if (blenderFirst) {
    for (const m of doc.markers) if (isObj(m) && m.kind === "Spawn" && isVec(m.position, 3)) stand(`marker ${m.name}`, m.position);
    if (!links.length && !doc.markers.some(m => isObj(m) && (m.kind === "Spawn" || m.kind === "Entrance"))) err("no way in: a Blender-first scene needs a link, or a Spawn or Entrance marker");
  }

  const solid = good.filter(c => !/^(Ground|Edge)/.test(c.s));                                   // the extent of what is built, without the ground slab and the invisible edge walls (the older outdoor scenes are larger by design, so only a Blender-first file is warned)
  if (blenderFirst && solid.length) for (const [axis, i] of [["x", 0], ["z", 2]]) {
    const size = Math.max(...solid.map(c => c.max[i])) - Math.min(...solid.map(c => c.min[i]));
    if (size > MAX_EXTENT) warn(`the scene is ${size.toFixed(0)} m along ${axis}: over ${MAX_EXTENT} m, consider splitting it (one scene is loaded at a time)`);
  }

  if (manifest) {
    const sceneOf = id => { for (const a of manifest.areas || []) for (const s of a.scenes || []) if (s.id === id) return {area: a.id, scene: s}; return null; };
    const here = sceneOf(doc.scene), near = (a, b) => Array.isArray(a) && Array.isArray(b) && a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) <= 0.05);
    if (!here) warn(`scene ${doc.scene} is not in the world manifest yet: a new scene to add`);
    if (blenderFirst) {
      // a manifest link that names its own F spot (`from.at`: a door the file has no link for, as hotel floor 3's apartment door) is not looked for in the file
      const out = (manifest.links || []).filter(l => l.from && l.from.scene === doc.scene && l.from.door), into = (manifest.links || []).filter(l => l.to && l.to.scene === doc.scene && l.to.arrive);
      for (const l of out) if (!Array.isArray(l.from.at) && !links.some(k => k.door === l.from.door)) err(`the manifest's link ${l.id} leaves by the door ${l.from.door}, which the file has no link for`);
      for (const k of links) if (isObj(k) && isName(k.door) && !out.some(l => l.from.door === k.door)) warn(`link ${k.door}: the manifest has no link from this door yet: a new link to add`);
      for (const l of into) if (!links.some(k => near(k.arrive, l.to.arrive) && near(k.face, l.to.face))) warn(`the manifest's link ${l.id} arrives at ${fmt(l.to.arrive)}, which is no arrive point of the file`);
    }
  }
  return {errors, warnings};
}

// The manifest stanzas a Blender-first file's links call for, as text to paste into shared/farway.manifest.js and fill in. `area` is the scene's area id.
export function linkStanzas(doc, area = "AREA") {
  const q = v => JSON.stringify(v).replace(/,/g, ", "), out = [];
  for (const l of doc.links || []) {
    out.push(`// leaving ${doc.scene} by ${l.door} (F at ${fmt(l.at)}): fill in where it leads`);
    out.push(`plan("${area}.${doc.scene}.${l.door}", {area: "${area}", scene: "${doc.scene}", door: "${l.door}"}, {area: "?", scene: "?", arrive: [?, ?, ?], face: [?, ?]}, "doors"),`);
    out.push(`// arriving in ${doc.scene} by ${l.door}: the \`to\` of the link that comes in here`);
    out.push(`//   to: {area: "${area}", scene: "${doc.scene}", arrive: ${q(l.arrive)}, face: ${q(l.face)}}`);
  }
  return out.join("\n");
}
