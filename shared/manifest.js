// The world manifest: which areas, scenes, links and modes exist, and what each one needs. Pure functions only (no data, no I/O), so the game page, the
// server and the tools can all use them. The data is in shared/farway.manifest.js; shared/registry.js builds it once at load.
//
// A manifest is {manifestVersion: 1, flags, connectors, modes, areas, links}.
//   area  {id, name, status: "built" | "planned" | "reserved", soloOnly?, coop?, rooms?: [id], spine?: [id], scenes?: [scene], ...}
//   scene {id, floorY?, files?, backdrop?: {day, night?} (equirect pictures of what lies past the scene), multiplayer?, presence?, puzzle?: "fuses" | "switches" | "keypad", powerSource?, loot?: {lockers, packs}, chamber?: {floor, index, wave: {monsters, kind}, stairsDown?, next?}}
//   link  {id, from: {area, scene?, door?}, to: {area, scene?, room?, door?, arrive?, face?}, connector, status, requires?: [flag], soloOnly?, returnTo?, note?}
//   mode  {status, area, floors, players: {min, max}, finish?: {scene, ...}, chambersPerFloor?, waves?, startChamber?}
// `multiplayer` is a floor the server runs (monsters, puzzles, health). `presence: true` is a page scene a room's players can be in together: the server only relays who is
// there and where, and runs no rules. A built link without `soloOnly` is one a room can follow, so both its ends must be one or the other.
// A scene id is unique across the whole manifest (the server's messages name a scene by its bare id).
// An addon is the same shape ({areas, links, flags?, connectors?, modes?}) and is added with mergeAddon.

export const STATUSES = ["built", "planned", "reserved"];
export const PUZZLES = ["fuses", "switches", "keypad"];
const isObj = v => !!v && typeof v === "object" && !Array.isArray(v);
const isId = v => typeof v === "string" && /^[A-Za-z][A-Za-z0-9_]*$/.test(v);
const isLinkId = v => typeof v === "string" && /^[A-Za-z0-9_.>-]+$/.test(v);
const isFile = v => typeof v === "string" && v.length > 0 && !v.startsWith("/") && !v.split("/").includes("..");
const isCount = v => Number.isInteger(v) && v >= 0;
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
// the rooms of a game (Right Door, Wrong Exit) or the stages of its spine (the Intern): what a `coop` game makes a place of
const placeIds = a => { const l = Array.isArray(a.rooms) ? a.rooms : Array.isArray(a.spine) ? a.spine : []; return l.length && l.every(isId) ? l : []; };

// Everything wrong with a manifest, as {errors, warnings} (arrays of strings). With worldDocs ({sceneId: parsed world/<id>.json}) it also checks that the
// door links in those files and the built links here are the same set. Never throws and never mutates its input.
export function checkManifest(doc, {worldDocs = null} = {}) {
  const errors = [], warnings = [], err = m => errors.push(m);
  if (!isObj(doc)) return {errors: ["the manifest is not an object"], warnings};
  if (doc.manifestVersion !== 1) err(`manifestVersion must be 1 (got ${JSON.stringify(doc.manifestVersion)})`);
  if (!Array.isArray(doc.areas)) { err("areas must be an array"); return {errors, warnings}; }
  const flags = new Set(Array.isArray(doc.flags) ? doc.flags : []), connectors = new Set(Array.isArray(doc.connectors) ? doc.connectors : []);
  const areas = new Map(), sceneArea = new Map(), scenesOf = new Map(), chambers = [], roomScenes = new Set(), coopRooms = new Map();

  for (const a of doc.areas) {
    if (!isObj(a) || !isId(a.id)) { err(`an area needs an id of letters, digits and underscores (got ${JSON.stringify(a && a.id)})`); continue; }
    if (areas.has(a.id)) { err(`duplicate area id ${a.id}`); continue; }
    areas.set(a.id, a);
    if (!STATUSES.includes(a.status)) err(`area ${a.id}: status must be one of ${STATUSES.join(", ")}`);
    if (a.coop !== undefined) {                                                                  // a game a room's players can be in together: a place for each room or stage (session 11)
      if (a.coop !== true) err(`area ${a.id}: coop must be true (or left out)`);
      else if (a.status !== "built") err(`area ${a.id}: only a built area can be coop`);
      else if (!placeIds(a).length) err(`area ${a.id}: coop needs rooms or spine (a list of ids)`);
      else coopRooms.set(a.id, new Set(placeIds(a)));
    }
    if (a.scenes === undefined) continue;
    if (!Array.isArray(a.scenes)) { err(`area ${a.id}: scenes must be an array`); continue; }
    const ids = new Set(); scenesOf.set(a.id, ids);
    for (const s of a.scenes) {
      if (!isObj(s) || !isId(s.id)) { err(`area ${a.id}: a scene needs an id (got ${JSON.stringify(s && s.id)})`); continue; }
      if (sceneArea.has(s.id)) { err(`duplicate scene id ${s.id} (in ${sceneArea.get(s.id)} and ${a.id})`); continue; }
      sceneArea.set(s.id, a.id); ids.add(s.id);
      const at = `scene ${s.id}`;
      if (s.puzzle !== undefined && !PUZZLES.includes(s.puzzle)) err(`${at}: puzzle must be one of ${PUZZLES.join(", ")}`);
      if (s.loot !== undefined && !(isObj(s.loot) && isCount(s.loot.lockers) && isCount(s.loot.packs))) err(`${at}: loot needs whole-number lockers and packs`);
      if (s.files !== undefined && !(Array.isArray(s.files) && s.files.every(isFile))) err(`${at}: files must be relative paths without ..`);
      if (s.backdrop !== undefined && !(isObj(s.backdrop) && isFile(s.backdrop.day) && (s.backdrop.night === undefined || isFile(s.backdrop.night)) && Object.keys(s.backdrop).every(k => k === "day" || k === "night"))) err(`${at}: backdrop needs a day picture (a relative path without ..) and may have a night one`);
      if (s.backdrop !== undefined && s.files === undefined) err(`${at}: a backdrop needs a scene the page loads (files)`);
      if (s.chamber !== undefined) {                                                                 // Going back in: a chamber is a scene with a wave (checked against the modes below)
        const c = s.chamber;
        if (!(isObj(c) && isId(c.floor) && Number.isInteger(c.index) && c.index >= 1 && isObj(c.wave) && isCount(c.wave.monsters) && c.wave.monsters >= 1 && isId(c.wave.kind))) err(`${at}: chamber needs a floor, an index from 1, and a wave with monsters and kind`);
        else if (c.stairsDown !== undefined && typeof c.stairsDown !== "string") err(`${at}: chamber.stairsDown must be a door name`);
        chambers.push(s);
      }
      if (s.presence !== undefined && s.presence !== true) err(`${at}: presence must be true (or left out)`);
      if (s.presence && s.multiplayer) err(`${at}: a scene is multiplayer (the server runs it) or presence, not both`);
      if (a.status === "built") {
        if (s.files !== undefined && s.files.length === 0) err(`${at}: a built scene needs at least one file`);
        if (s.multiplayer && typeof s.floorY !== "number") err(`${at}: a multiplayer scene needs a floorY`);
        if (s.presence && typeof s.floorY !== "number") err(`${at}: a presence scene needs a floorY`);
        if (s.presence && s.files === undefined) err(`${at}: a presence scene needs files (it is a scene the page loads)`);
        if (s.multiplayer || s.presence === true) roomScenes.add(s.id);
      } else if (s.multiplayer || s.presence) err(`${at}: only a built scene can be multiplayer or presence`);
    }
  }

  const linkIds = new Set();
  for (const l of Array.isArray(doc.links) ? doc.links : []) {
    if (!isObj(l) || !isLinkId(l.id)) { err(`a link needs an id (got ${JSON.stringify(l && l.id)})`); continue; }
    if (linkIds.has(l.id)) { err(`duplicate link id ${l.id}`); continue; }
    linkIds.add(l.id);
    const at = `link ${l.id}`;
    if (!STATUSES.includes(l.status)) err(`${at}: status must be one of ${STATUSES.join(", ")}`);
    if (!connectors.has(l.connector)) err(`${at}: unknown connector ${JSON.stringify(l.connector)}`);
    for (const need of l.requires === undefined ? [] : Array.isArray(l.requires) ? l.requires : [null]) if (!flags.has(need)) err(`${at}: requires an undeclared flag ${JSON.stringify(need)}`);
    for (const end of ["from", "to"]) {
      const e = l[end];
      if (!isObj(e) || !areas.has(e.area)) { err(`${at}: ${end}.area ${JSON.stringify(e && e.area)} is not an area`); continue; }
      if (e.scene !== undefined && scenesOf.has(e.area) && !scenesOf.get(e.area).has(e.scene)) err(`${at}: ${end}.scene ${e.scene} is not a scene of ${e.area}`);
      if (l.status === "built" && areas.get(e.area).status !== "built") err(`${at}: a built link cannot touch the ${areas.get(e.area).status} area ${e.area}`);
      const game = end === "to" && e.scene === undefined && coopRooms.has(e.area);                // a link into a coop game: a room can follow it to the game's rooms
      if (l.status === "built" && game && e.room !== undefined && !coopRooms.get(e.area).has(e.room)) err(`${at}: to.room ${e.room} is not a room of ${e.area}`);
      if (l.status === "built" && !l.soloOnly && !roomScenes.has(e.scene) && !game) err(`${at}: a room could follow this link into ${e.scene || e.area}, which is neither multiplayer nor presence: mark the link soloOnly`);
    }
    if (l.returnTo !== undefined && !(isObj(l.returnTo) && areas.has(l.returnTo.area) && (l.returnTo.scene === undefined || sceneArea.get(l.returnTo.scene) === l.returnTo.area))) err(`${at}: returnTo is not a place`);
  }
  for (const id of coopRooms.keys()) if (!(doc.links || []).some(l => l && l.status === "built" && !l.soloOnly && l.to && l.to.area === id)) err(`area ${id} is coop but no built gate leads into it that a room can follow (its gate says soloOnly)`);

  for (const [name, m] of Object.entries(isObj(doc.modes) ? doc.modes : {})) {
    const at = `mode ${name}`;
    if (!isObj(m) || !STATUSES.includes(m.status)) { err(`${at}: needs a status`); continue; }
    const ids = scenesOf.get(m.area);
    if (!areas.has(m.area)) { err(`${at}: area ${m.area} does not exist`); continue; }
    if (!Array.isArray(m.floors) || !m.floors.length) err(`${at}: needs floors`);
    else for (const f of m.floors) if (m.status === "built" && !(ids && ids.has(f))) err(`${at}: floor ${f} is not a scene of ${m.area}`);
    if (m.players !== undefined && !(isObj(m.players) && Number.isInteger(m.players.min) && Number.isInteger(m.players.max) && m.players.min >= 1 && m.players.min <= m.players.max)) err(`${at}: players needs 1 <= min <= max`);
    if (m.finish !== undefined && Array.isArray(m.floors) && !m.floors.includes(m.finish.scene)) err(`${at}: finish.scene must be one of its floors`);
  }

  const gbi = (doc.modes || {}).going_back_in;                                                       // chambers: each one sits on a floor of the mode, its `next` is another chamber, and the start is one
  const chamberIds = new Set(chambers.map(c => c.id));
  const chamberAt = new Map();                                                                         // one chamber per place in the run: a floor and an index name it
  for (const c of chambers) {
    const at = `scene ${c.id}`, ch = c.chamber;
    if (!isObj(ch) || !gbi) continue;
    if (!gbi.floors.includes(ch.floor)) err(`${at}: chamber floor ${ch.floor} is not a floor of going_back_in`);
    if (gbi.chambersPerFloor !== undefined && ch.index > gbi.chambersPerFloor) err(`${at}: chamber index ${ch.index} is past chambersPerFloor ${gbi.chambersPerFloor}`);
    { const k = `${ch.floor} ${ch.index}`; if (chamberAt.has(k)) err(`${at}: chamber ${ch.index} of ${ch.floor} is already ${chamberAt.get(k)}`); else chamberAt.set(k, c.id); }
    if (ch.next !== undefined && !chamberIds.has(ch.next)) err(`${at}: chamber.next ${ch.next} is not a chamber`);
    if (ch.next !== undefined && ch.stairsDown === undefined) err(`${at}: chamber.next needs chamber.stairsDown`);
  }
  if (gbi && gbi.startChamber !== undefined && !chamberIds.has(gbi.startChamber)) err(`mode going_back_in: startChamber ${gbi.startChamber} is not a chamber`);
  if (gbi && gbi.status === "built" && !chambers.length) err("mode going_back_in: built without any chamber");

  if (worldDocs) compareWorldDocs(doc, worldDocs, err, m => warnings.push(m));
  return {errors, warnings};
}
export const validateManifest = (doc, opts) => checkManifest(doc, opts).errors;

const DOOR_BACKED = ["stair_door", "gate"];
// The door links stored in world/<scene>.json and the built links here must be the same set, with the same arrival points.
function compareWorldDocs(doc, worldDocs, err, warn) {
  const built = (doc.links || []).filter(l => l && l.status === "built");
  for (const [scene, wdoc] of Object.entries(worldDocs)) {
    const doors = new Map((wdoc.doors || []).filter(d => d.link).map(d => [d.name, d.link]));
    const mine = built.filter(l => l.from && l.from.scene === scene && DOOR_BACKED.includes(l.connector));          // other connectors (walking out of the store) are not doors in the file
    for (const [name, jl] of doors) {
      const l = mine.find(x => x.from.door === name);
      if (!l) { err(`world/${scene}.json: door ${name} has a link that the manifest does not list`); continue; }
      if (jl.game) {
        if (l.to.area !== jl.game || l.to.room !== jl.room || !same(l.to.arrive, jl.arrive) || !same(l.to.face, jl.face)) err(`${l.id}: differs from the game link in world/${scene}.json`);
        const coop = (doc.areas.find(a => a.id === l.to.area) || {}).coop === true;
        if (!l.soloOnly && !coop) err(`${l.id}: a game gate must say soloOnly unless its game is coop`);
        if (jl.scene === undefined) warn(`${l.id}: world/${scene}.json has no return scene, so after the game the page falls back to the passage scene (manifest says ${l.returnTo ? l.returnTo.scene : "nothing"})`);
        else if (!l.returnTo || l.returnTo.scene !== jl.scene) err(`${l.id}: returnTo differs from world/${scene}.json`);
      } else if (l.to.scene !== jl.scene || l.to.door !== jl.door || !same(l.to.arrive, jl.arrive) || !same(l.to.face, jl.face)) err(`${l.id}: differs from the stair link in world/${scene}.json`);
    }
    for (const l of mine) if (!doors.has(l.from.door)) err(`${l.id}: world/${scene}.json has no door ${l.from.door} with a link`);
  }
}

// Evaluates a link's `requires` against the flags a player holds (a Set, an array or an object of true values).
export function requirementsMet(link, flags) {
  const has = flags instanceof Set ? f => flags.has(f) : Array.isArray(flags) ? f => flags.includes(f) : flags ? f => !!flags[f] : () => false;
  const missing = (link && link.requires ? link.requires : []).filter(f => !has(f));
  return {ok: missing.length === 0, missing};
}

function deepFreeze(o) { if (o && typeof o === "object" && !Object.isFrozen(o)) { Object.freeze(o); for (const v of Object.values(o)) deepFreeze(v); } return o; }

// The lookups the rest of the code needs, derived once from a valid manifest. Throws (listing every problem) on an invalid one. The result is frozen.
export function buildRegistry(doc) {
  const {errors} = checkManifest(doc);
  if (errors.length) throw new Error("invalid world manifest:\n  " + errors.join("\n  "));
  const builtScenes = doc.areas.filter(a => a.status === "built").flatMap(a => (a.scenes || []).map(s => ({...s, area: a.id})));
  const floors = {}, pageScenes = {}, loot = {}, presence = {}, gamePlaces = {}, gameOf = new Map();
  for (const a of doc.areas) if (a.status === "built" && a.coop === true) { gameOf.set(a.id, placeIds(a).map(r => `${a.id}:${r}`)); for (const r of placeIds(a)) gamePlaces[`${a.id}:${r}`] = {area: a.id, room: r}; }
  for (const s of builtScenes) {
    if (s.multiplayer) floors[s.id] = s.floorY;
    if (s.presence) presence[s.id] = s.floorY;
    if (s.files) pageScenes[s.id] = {glbs: s.files.filter(f => f.endsWith(".glb")), floor: s.floorY, ...(s.backdrop ? {backdrop: s.backdrop} : {})};
    if (s.loot) loot[s.id] = {lockers: s.loot.lockers, packs: s.loot.packs};
  }
  const links = doc.links || [], modeGbi = (doc.modes || {}).going_back_in, chamberScenes = new Map(builtScenes.filter(s => s.chamber).map(s => [s.id, s]));
  // a chamber with its place in the run: wave number = (position of its floor in the mode) x chambersPerFloor + index, 1-based (20 waves = 5 floors x 4 chambers)
  const chamber = id => {
    const s = chamberScenes.get(id); if (!s || !modeGbi) return null;
    const no = modeGbi.floors.indexOf(s.chamber.floor) * (modeGbi.chambersPerFloor || 4) + s.chamber.index;
    return {id, floorY: s.floorY, ...s.chamber, wave: {...s.chamber.wave, no}};
  };
  // Which scenes a player in a room of `mode` may be in, given the flags they hold: the mode's floors, and whatever the built links a room can follow (no soloOnly) lead
  // to from there, each link's `requires` met. A room starts in the mode's own scenes: its `floors`, or for Going back in (whose `floors` name storeys, not scenes) its first chamber. {ok, missing}: `missing` names the flags of the shut links on the way, for a message. The page's own doors check each
  // link as you use it; this is for the server (may this player be in that scene?) and for "go to a friend", which skips the doors.
  const canReach = (scene, flags, mode = "original") => {
    const m = (doc.modes || {})[mode], seen = new Set(!m ? [] : m.startChamber ? [m.startChamber] : Array.isArray(m.floors) ? m.floors : []), todo = [...seen], missing = new Set();
    while (todo.length) {
      const from = todo.pop();
      for (const l of links) {
        if (l.status !== "built" || l.soloOnly || l.from.scene !== from) continue;
        if (!l.to.scene && gameOf.has(l.to.area)) {                                                   // a gate into a coop game: all of that game's places (they have no links out)
          const r = requirementsMet(l, flags);
          if (r.ok) gameOf.get(l.to.area).forEach(p => seen.add(p)); else r.missing.forEach(f => missing.add(f));
          continue;
        }
        if (!l.to.scene || seen.has(l.to.scene)) continue;
        const r = requirementsMet(l, flags);
        if (r.ok) { seen.add(l.to.scene); todo.push(l.to.scene); } else r.missing.forEach(f => missing.add(f));
      }
    }
    return seen.has(scene) ? {ok: true, missing: []} : {ok: false, missing: [...missing]};
  };
  return deepFreeze({
    presence, gamePlaces, canReach,
    chamber, chambers: [...chamberScenes.keys()],
    manifest: structuredClone(doc),
    floors, pageScenes, loot,
    powerSources: builtScenes.filter(s => s.powerSource).map(s => s.id),
    scenesWith: puzzle => Object.freeze(builtScenes.filter(s => s.puzzle === puzzle).map(s => s.id)),
    modes: structuredClone(doc.modes || {}),
    maxPlayers: mode => ((doc.modes || {})[mode] || {}).players?.max,
    links: structuredClone(links),
    linkFrom: (scene, door) => links.find(l => l.status === "built" && l.from.scene === scene && l.from.door === door),
    linksFrom: scene => links.filter(l => l.from.scene === scene),
    area: id => doc.areas.find(a => a.id === id),
  });
}

// A new manifest with an addon's areas and links added. An addon may add areas, links, flags, connectors and modes; it may not reuse an existing
// area, scene, link or mode id, and every link it brings must touch one of its own areas. Throws on any problem; the base is never changed.
export function mergeAddon(base, addon) {
  const problems = [];
  if (!isObj(addon) || !Array.isArray(addon.areas) || !addon.areas.length) throw new Error("an addon needs at least one area");
  const own = new Set(addon.areas.map(a => a && a.id));
  for (const a of addon.areas) if ((base.areas || []).some(b => b.id === a.id)) problems.push(`area ${a.id} already exists`);
  for (const k of Object.keys(addon.modes || {})) if ((base.modes || {})[k]) problems.push(`mode ${k} already exists`);
  for (const l of addon.links || []) if (!own.has(l.from && l.from.area) && !own.has(l.to && l.to.area)) problems.push(`link ${l.id} touches none of the addon's own areas`);
  if (problems.length) throw new Error("addon refused:\n  " + problems.join("\n  "));
  const merged = {
    ...structuredClone(base),
    flags: [...new Set([...(base.flags || []), ...(addon.flags || [])])],
    connectors: [...new Set([...(base.connectors || []), ...(addon.connectors || [])])],
    modes: {...structuredClone(base.modes || {}), ...structuredClone(addon.modes || {})},
    areas: [...structuredClone(base.areas), ...structuredClone(addon.areas)],
    links: [...structuredClone(base.links || []), ...structuredClone(addon.links || [])],
  };
  const {errors} = checkManifest(merged);
  if (errors.length) throw new Error("addon refused:\n  " + errors.join("\n  "));
  return merged;
}
