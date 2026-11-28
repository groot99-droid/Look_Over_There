import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {checkManifest, validateManifest, buildRegistry, mergeAddon, requirementsMet} from "./manifest.js";
import {FARWAY} from "./farway.manifest.js";
import {REGISTRY} from "./registry.js";
import {BUS_STREET} from "./city.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const clone = o => structuredClone(o);
const worldDocs = () => Object.fromEntries(REGISTRY.modes.original.floors.map(id => [id, JSON.parse(fs.readFileSync(path.join(ROOT, `world/${id}.json`), "utf8"))]));
const bad = (mutate, expect) => { const d = clone(FARWAY); mutate(d); const e = validateManifest(d); assert.ok(e.some(m => expect.test(m)), `wanted ${expect}, got ${JSON.stringify(e)}`); };

// ---- the values that used to be written out by hand in six files. If one of these changes, a rule of the game changed: say so on purpose.
test("the registry gives the same floors, scenes, puzzles, loot and room size the code used to hard-code", () => {
  assert.deepEqual(REGISTRY.floors, {B1: -3.0, L1: 0, L2: 3.2, L3: 6.4, L4: 9.6, gbi_L4_4: 9.6, gbi_L3_1: 6.4});          // session 16: the two chambers are scenes a room's server runs
  assert.deepEqual(Object.keys(REGISTRY.floors), ["B1", "L1", "L2", "L3", "L4", "gbi_L4_4", "gbi_L3_1"]);
  assert.deepEqual(Object.keys(REGISTRY.pageScenes).slice(0, 5), ["B1", "L1", "L2", "L3", "L4"], "order matters: the page seeds spots by scene index");
  assert.deepEqual(REGISTRY.pageScenes, {
    B1: {glbs: ["world/B1.glb"], floor: -3.0}, L1: {glbs: ["world/L1.glb"], floor: 0}, L2: {glbs: ["world/L2.glb"], floor: 3.2},
    L3: {glbs: ["world/L3.glb"], floor: 6.4}, L4: {glbs: ["world/L4.glb", "world/Exterior.glb"], floor: 9.6},
    parking_lot: {glbs: ["world/L4.glb", "world/Exterior.glb"], floor: 9.6},          // the Overworld (session 6): a page scene, not a room's floor (see `floors` above)
    gbi_L4_4: {glbs: ["world/L4.glb", "world/Exterior.glb"], floor: 9.6}, gbi_L3_1: {glbs: ["world/L3.glb"], floor: 6.4},          // Going back in chambers (session 8): page scenes too
    street: {glbs: ["world/street.glb"], floor: 0}, apartment: {glbs: ["world/apartment.glb"], floor: 0}, main_floor: {glbs: ["world/main_floor.glb"], floor: 0}, entrance: {glbs: ["world/entrance.glb"], floor: 0}, galleries: {glbs: ["world/galleries.glb"], floor: 0}, factory_floor: {glbs: ["world/factory_floor.glb"], floor: 0}, laboratory: {glbs: ["world/laboratory.glb"], floor: 0}, forest: {glbs: ["world/forest.glb"], floor: 0}, meadow: {glbs: ["world/meadow.glb"], floor: 0},                                                       // the City (session 9): Hallam Row, blockout geometry built in index.html
  });
  assert.deepEqual(REGISTRY.scenesWith("fuses"), ["B1"]);
  assert.deepEqual(REGISTRY.scenesWith("switches"), ["L1"]);
  assert.deepEqual(REGISTRY.scenesWith("keypad"), ["L2"]);
  assert.deepEqual(REGISTRY.powerSources, ["L3", "L4"]);
  assert.deepEqual(REGISTRY.loot, {B1: {lockers: 8, packs: 6}, L1: {lockers: 0, packs: 3}, L2: {lockers: 0, packs: 3}, L3: {lockers: 0, packs: 4}, L4: {lockers: 0, packs: 3}, gbi_L4_4: {lockers: 0, packs: 3}, gbi_L3_1: {lockers: 0, packs: 3}});          // the chambers (session 8) carry ammo packs
  assert.equal(REGISTRY.maxPlayers("original"), 10);
});

test("the shipped manifest has no errors and no warnings (both gates name their return scene in world/L4.json)", () => {
  const {errors, warnings} = checkManifest(FARWAY, {worldDocs: worldDocs()});
  assert.deepEqual(errors, []);
  assert.deepEqual(warnings, []);
});

test("every door link in world/*.json is in the manifest, with the same arrival, and the other way round", () => {
  const docs = worldDocs(), built = REGISTRY.links.filter(l => l.status === "built" && ["stair_door", "gate"].includes(l.connector) && l.from.area === "lot");          // walking out of the store is not a door in the file
  let n = 0;
  for (const [scene, doc] of Object.entries(docs)) for (const d of doc.doors) if (d.link) { n++; assert.ok(REGISTRY.linkFrom(scene, d.name), `${scene}/${d.name}`); }
  assert.equal(built.length, n, "same count");
  assert.equal(n, 10);
  const gdocs = Object.fromEntries(["gbi_L4_4", "gbi_L3_1"].map(id => [id, JSON.parse(fs.readFileSync(path.join(ROOT, `world/${id}.json`), "utf8"))]));          // the chambers' files: one link, from gbi_L4_4 down
  assert.deepEqual(checkManifest(FARWAY, {worldDocs: gdocs}).errors, []);
  assert.equal(Object.values(gdocs).flatMap(d => d.doors).filter(d => d.link).length, REGISTRY.links.filter(l => l.status === "built" && l.from.area === "gbi").length);
});

test("a drifted door link is caught", () => {
  const docs = worldDocs(), d = docs.B1.doors.find(x => x.link); d.link = {...d.link, arrive: [9, 9, 9]};
  assert.ok(checkManifest(FARWAY, {worldDocs: docs}).errors.some(m => /differs from the stair link/.test(m)));
  const docs2 = worldDocs(); docs2.L1.doors.find(x => x.link).link = undefined;
  assert.ok(checkManifest(FARWAY, {worldDocs: docs2}).errors.some(m => /has no door .* with a link/.test(m)));
  const docs3 = worldDocs(); docs3.L3.doors.push({name: "NewDoor", link: {scene: "L2", door: "x", arrive: [0, 0, 0], face: [0, 1]}});
  assert.ok(checkManifest(FARWAY, {worldDocs: docs3}).errors.some(m => /does not list/.test(m)));
});

test("the two game gates say where to return to; Right Door, Wrong Exit is coop (a room can enter it, session 11) and the Intern is solo only", () => {
  for (const door of ["DoorLeaf_Gate_RDW", "DoorLeaf_Gate_ITN"]) {
    const l = REGISTRY.linkFrom("L4", door);
    assert.equal(l.connector, "gate", door);
    assert.deepEqual(l.returnTo, {area: "lot", scene: "L4"});
  }
  assert.equal(REGISTRY.linkFrom("L4", "DoorLeaf_Gate_RDW").soloOnly, false);
  assert.equal(REGISTRY.linkFrom("L4", "DoorLeaf_Gate_ITN").soloOnly, true);
});

// ---- the validator
test("each kind of mistake is reported", () => {
  bad(d => { d.manifestVersion = 2; }, /manifestVersion/);
  bad(d => { d.areas.push({...d.areas[0]}); }, /duplicate area id lot/);
  bad(d => { d.areas.find(a => a.id === "hotel").scenes.push({id: "B1"}); }, /duplicate scene id B1/);          // the hotel is still planned (the mall was built in slice 13)
  bad(d => { d.areas[0].scenes[0].puzzle = "lasers"; }, /puzzle must be one of/);
  bad(d => { d.areas[0].scenes[0].files = []; }, /at least one file/);
  bad(d => { d.areas[0].scenes[0].files = ["../secret"]; }, /relative paths/);
  bad(d => { delete d.areas[0].scenes[0].floorY; }, /needs a floorY/);
  bad(d => { d.areas[0].scenes[0].loot = {lockers: -1, packs: 3}; }, /loot needs/);
  bad(d => { d.areas.find(a => a.id === "hotel").scenes[0].multiplayer = true; }, /only a built scene can be multiplayer/);
  bad(d => { d.links[0].to.area = "nowhere"; }, /not an area/);
  bad(d => { d.links[0].to.scene = "L9"; }, /not a scene of lot/);
  bad(d => { d.links[0].connector = "teleport"; }, /unknown connector/);
  bad(d => { d.links[0].requires = ["no_such_flag"]; }, /undeclared flag/);
  bad(d => { d.links[1].id = d.links[0].id; }, /duplicate link id/);
  bad(d => { d.links[0].to.area = "hotel"; delete d.links[0].to.scene; }, /built link cannot touch the planned area/);
  bad(d => { d.links[0].returnTo = {area: "lot", scene: "nope"}; }, /returnTo is not a place/);
  bad(d => { d.modes.original.floors.push("L9"); }, /floor L9 is not a scene/);
  bad(d => { d.modes.original.players = {min: 5, max: 2}; }, /players needs/);
  bad(d => { d.modes.original.finish.scene = "L9"; }, /finish\.scene/);
  assert.deepEqual(validateManifest(null), ["the manifest is not an object"]);
});

test("validation never changes its input", () => {
  const d = clone(FARWAY), frozen = JSON.stringify(d);
  checkManifest(d, {worldDocs: worldDocs()}); buildRegistry(d); assert.equal(JSON.stringify(d), frozen);
});

test("an invalid manifest cannot become a registry, and the error lists every problem", () => {
  const d = clone(FARWAY); d.links[0].connector = "x"; d.links[1].connector = "y";
  assert.throws(() => buildRegistry(d), err => /unknown connector "x"/.test(err.message) && /unknown connector "y"/.test(err.message));
});

test("the registry is frozen, so nothing can edit the floors at run time", () => {
  assert.throws(() => { REGISTRY.floors.B1 = 1; }, TypeError);
  assert.throws(() => { REGISTRY.scenesWith("fuses").push("L9"); }, TypeError);
  assert.throws(() => { REGISTRY.modes.original.players.max = 99; }, TypeError);
  assert.equal(REGISTRY.floors.B1, -3.0);
});

test("a planned scene never reaches the page or the server", () => {
  for (const id of ["lobby", "playground", "bus_station"]) { assert.equal(REGISTRY.floors[id], undefined); assert.equal(REGISTRY.pageScenes[id], undefined); }
  assert.equal(REGISTRY.linkFrom("L4", "front_doors").id, "lot.L4.front_doors>overworld", "the built link is found by its door name");
  assert.equal(REGISTRY.linkFrom("lot", "overworld.bus>city"), undefined);
  assert.ok(REGISTRY.links.some(l => l.id === "city.street>jobs" && l.status === "planned"), "planned links are listed");
});
test("the Overworld's parking lot is on the page but never a floor the server runs", () => {
  assert.equal(REGISTRY.floors.parking_lot, undefined, "the server runs nothing there (a room can be in it: see the presence tests)");
  assert.deepEqual(REGISTRY.pageScenes.parking_lot, {glbs: ["world/L4.glb", "world/Exterior.glb"], floor: 9.6});
  const l = REGISTRY.links.find(x => x.id === "lot.L4.front_doors>overworld");
  assert.deepEqual([l.status, l.requires], ["built", ["original_complete"]]);
  assert.deepEqual(requirementsMet(l, []), {ok: false, missing: ["original_complete"]}, "shut until the Original has been finished");
  assert.equal(requirementsMet(l, ["original_complete"]).ok, true);
  const doc = JSON.parse(fs.readFileSync(path.join(ROOT, "world/parking_lot.json"), "utf8"));
  assert.deepEqual(l.to.arrive, doc.markers.find(m => m.kind === "Spawn").position, "the link arrives at the table, which is the scene's spawn marker");
  assert.ok(doc.colliders.some(c => c.s === "Block_store_doors"), "the store cannot be entered from the lot");
});

// ---- requirements
test("a link's requirements are met only when every flag is held", () => {
  const l = REGISTRY.links.find(x => x.id === "grocery.backhouse>secret_ops");
  assert.deepEqual(requirementsMet(l, []), {ok: false, missing: ["keycard_tier_1"]});
  assert.equal(requirementsMet(l, new Set(["keycard_tier_1"])).ok, true);
  assert.equal(requirementsMet(l, {keycard_tier_1: true}).ok, true);
  assert.equal(requirementsMet(l, {keycard_tier_1: false}).ok, false);
  assert.equal(requirementsMet(l, undefined).ok, false);
  assert.equal(requirementsMet({id: "free"}, []).ok, true);
  assert.deepEqual(requirementsMet(REGISTRY.links.find(x => x.id === "lot.L4.front_doors>overworld"), ["x"]).missing, ["original_complete"]);
});

// ---- addons
const addon = () => ({
  flags: ["shed_key"], connectors: ["rope"],
  areas: [{id: "shed_addon", name: "The shed", status: "built", scenes: [{id: "shed_inside", floorY: 0, files: ["addons/shed/shed.glb"], multiplayer: true, puzzle: "keypad", loot: {lockers: 0, packs: 1}}]}],
  links: [{id: "shed.in", status: "built", connector: "rope", requires: ["shed_key"], from: {area: "lot", scene: "L3", door: "x"}, to: {area: "shed_addon", scene: "shed_inside"}}],
  modes: {shed: {status: "built", area: "shed_addon", floors: ["shed_inside"], players: {min: 1, max: 4}}},
});
test("an addon adds scenes, links and a mode without touching the base", () => {
  const base = clone(FARWAY), frozen = JSON.stringify(base);
  const m = mergeAddon(base, addon());
  assert.equal(JSON.stringify(base), frozen, "the base is unchanged");
  const r = buildRegistry(m);
  assert.deepEqual(Object.keys(r.floors), ["B1", "L1", "L2", "L3", "L4", "gbi_L4_4", "gbi_L3_1", "shed_inside"]);
  assert.deepEqual(r.scenesWith("keypad"), ["L2", "shed_inside"]);
  assert.equal(r.maxPlayers("shed"), 4);
  assert.deepEqual(r.pageScenes.shed_inside, {glbs: ["addons/shed/shed.glb"], floor: 0});
});
test("an addon cannot reuse ids, redefine a base mode, or add a link between base areas", () => {
  const a = addon(); a.areas[0].id = "lot";
  assert.throws(() => mergeAddon(FARWAY, a), /area lot already exists/);
  const b = addon(); b.areas[0].scenes[0].id = "L1";
  assert.throws(() => mergeAddon(FARWAY, b), /duplicate scene id L1/);
  const c = addon(); c.modes = {original: c.modes.shed};
  assert.throws(() => mergeAddon(FARWAY, c), /mode original already exists/);
  const d = addon(); d.links[0].from = {area: "lot", scene: "L1"}; d.links[0].to = {area: "lot", scene: "L2"};
  assert.throws(() => mergeAddon(FARWAY, d), /touches none of the addon's own areas/);
  const e = addon(); e.links[0].requires = ["undeclared"];
  assert.throws(() => mergeAddon(FARWAY, e), /undeclared flag/);
  assert.throws(() => mergeAddon(FARWAY, {}), /at least one area/);
});

// ---- Going back in chambers (session 8)
test("the chambers: wave numbers follow the run (4th chamber of L4 is wave 4, 1st of L3 is wave 5), and the start is a built chamber", () => {
  const c = REGISTRY.chamber("gbi_L4_4"), n = REGISTRY.chamber("gbi_L3_1");
  assert.equal(c.wave.no, 4); assert.equal(n.wave.no, 5); assert.equal(c.next, "gbi_L3_1"); assert.equal(c.stairsDown, "DoorLeaf_Stair_L3_L4_down");
  assert.equal(REGISTRY.modes.going_back_in.startChamber, "gbi_L4_4");
  assert.equal(REGISTRY.chamber("L3"), null, "an Original floor is not a chamber");
  assert.equal(REGISTRY.modes.going_back_in.status, "built", "session 16: a room can run the mode");
  for (const id of REGISTRY.chambers) assert.equal(REGISTRY.floors[id], REGISTRY.chamber(id).floorY, "every chamber is a scene the server runs, at its floor's height");
  assert.ok(!REGISTRY.linkFrom("gbi_L4_4", "DoorLeaf_Stair_L3_L4_down").soloOnly, "the stairs down are open to a room");
});
test("a bad chamber is caught", () => {
  bad(d => { d.modes.going_back_in.startChamber = "L3"; }, /startChamber L3 is not a chamber/);
  bad(d => { d.areas.find(a => a.id === "gbi").scenes[0].chamber.floor = "L9"; }, /not a floor of going_back_in/);
  bad(d => { d.areas.find(a => a.id === "gbi").scenes[0].chamber.index = 5; }, /past chambersPerFloor/);
  // a backdrop: equirect pictures of what lies past a scene the page loads; a day one, and maybe a night one
  { const d = clone(FARWAY), st = d.areas.find(a => a.id === "city").scenes.find(x => x.id === "street"); st.backdrop = {day: "world/backdrops/street_day.webp", night: "world/backdrops/street_night.webp"};
    assert.deepEqual(validateManifest(d), []); assert.deepEqual(buildRegistry(d).pageScenes.street.backdrop, st.backdrop); assert.equal(buildRegistry(clone(FARWAY)).pageScenes.street.backdrop, undefined); }
  bad(d => { d.areas.find(a => a.id === "city").scenes[0].backdrop = {night: "world/x.webp"}; }, /backdrop needs a day picture/);
  bad(d => { d.areas.find(a => a.id === "city").scenes[0].backdrop = {day: "../x.webp"}; }, /backdrop needs a day picture/);
  bad(d => { d.areas.find(a => a.id === "city").scenes[0].backdrop = {day: "world/x.webp", dusk: "world/y.webp"}; }, /backdrop needs a day picture/);
  bad(d => { d.areas.find(a => a.id === "city").scenes.find(x => x.id === "bus_stop").backdrop = {day: "world/x.webp"}; }, /a backdrop needs a scene the page loads/);
  bad(d => { const sc = d.areas.find(a => a.id === "gbi").scenes; sc[1].chamber.floor = sc[0].chamber.floor; sc[1].chamber.index = sc[0].chamber.index; }, /chamber 4 of L4 is already gbi_L4_4/);   // one chamber per floor and index
  bad(d => { d.areas.find(a => a.id === "gbi").scenes[0].chamber.next = "nope"; }, /is not a chamber/);
  bad(d => { delete d.areas.find(a => a.id === "gbi").scenes[0].chamber.wave; }, /chamber needs a floor/);
});
test("the City's street is on the page, never a floor the server runs, and the bus links join it to the lot", () => {
  assert.equal(REGISTRY.floors.street, undefined);
  assert.deepEqual(REGISTRY.pageScenes.street, {glbs: ["world/street.glb"], floor: 0});
  const there = REGISTRY.linkFrom("parking_lot", "bus_stop"), back = REGISTRY.linkFrom("street", "bus_stop");
  assert.ok(there && there.status === "built" && !there.soloOnly && !back.soloOnly && there.to.scene === "street" && back && back.to.scene === "parking_lot");
  assert.deepEqual(there.to.arrive, BUS_STREET.arrive, "the arrival is the street's spawn point"); assert.deepEqual(there.to.face, BUS_STREET.face);
});

// ---- presence (session 17): page scenes a room's players can be in together. The server relays who is there and where, and runs nothing.
test("presence scenes: the parking lot is one, the floors and the chambers are not, and the field is checked", () => {
  assert.deepEqual(REGISTRY.presence, {parking_lot: 9.6, street: 0, apartment: 0, forest: 0, meadow: 0}, "the lot, the street, the apartment, the forest and the meadow are places a room can be in, each at its floor height");
  for (const id of ["B1", "L4", "gbi_L4_4", "main_floor", "playground"]) assert.equal(REGISTRY.presence[id], undefined, id);
  assert.equal(REGISTRY.floors.parking_lot, undefined, "the server still runs nothing there");
  bad(d => { d.areas.find(a => a.id === "overworld").scenes[0].presence = "yes"; }, /parking_lot: presence must be true/);
  bad(d => { d.areas.find(a => a.id === "lot").scenes[0].presence = true; }, /B1: a scene is multiplayer \(the server runs it\) or presence, not both/);
  bad(d => { delete d.areas.find(a => a.id === "overworld").scenes[0].floorY; }, /parking_lot: a presence scene needs a floorY/);
  bad(d => { d.areas.find(a => a.id === "overworld").scenes[1].presence = true; }, /table_and_chairs: a presence scene needs files/);
});
test("a built link a room can follow joins scenes a room can be in; every other link says soloOnly", () => {
  const out = REGISTRY.links.find(l => l.id === "lot.L4.front_doors>overworld");
  assert.deepEqual([out.soloOnly, out.requires], [undefined, ["original_complete"]], "a room can walk out, and the flag is still needed");
  for (const l of REGISTRY.links.filter(l => l.status === "built" && !l.soloOnly)) for (const e of [l.from, l.to])
    assert.ok(REGISTRY.floors[e.scene] !== undefined || REGISTRY.presence[e.scene] !== undefined || (e.scene === undefined && Object.values(REGISTRY.gamePlaces).some(g => g.area === e.area)), `${l.id}: ${e.scene || e.area}`);          // or the gate into a coop game: its places
  bad(d => { delete d.links.find(l => l.id === "city.street>grocery").soloOnly; }, /city\.street>grocery: a room could follow this link into main_floor/);
  bad(d => { delete d.links.find(l => l.connector === "gate" && l.to.area === "intern").soloOnly; }, /a room could follow this link into intern/);          // the Intern is not coop: its gate must stay solo only
});
test("canReach: which scenes a room's player may be in, by the flags they hold", () => {
  assert.deepEqual(REGISTRY.canReach("L2", []), {ok: true, missing: []}, "the mode's floors are always open");
  assert.deepEqual(REGISTRY.canReach("parking_lot", []), {ok: false, missing: ["original_complete"]});
  assert.deepEqual(REGISTRY.canReach("parking_lot", ["original_complete"]), {ok: true, missing: []});
  assert.equal(REGISTRY.canReach("parking_lot", new Set(["job_intern"])).ok, false);
  assert.equal(REGISTRY.canReach("main_floor", ["original_complete", "job_intern"]).ok, false, "the grocery's links are solo only");
  for (const id of ["street", "apartment"]) { assert.equal(REGISTRY.canReach(id, ["original_complete"]).ok, true, id); assert.deepEqual(REGISTRY.canReach(id, []).missing, ["original_complete"], "the City is past the lot, so it needs the lot's flag"); }
  for (const id of ["main_floor", "entrance", "galleries", "factory_floor", "laboratory", "gbi_L4_4"]) assert.equal(REGISTRY.canReach(id, REGISTRY.manifest.flags).ok, false, `${id} stays solo only`);
  assert.equal(REGISTRY.canReach("nowhere", ["original_complete"]).ok, false);
  assert.equal(REGISTRY.canReach("L2", [], "no_such_mode").ok, false);
  // a Going back in room's scenes are its chambers (its `floors` name storeys): you can be in either chamber, never in the Original's floors or the lot, flags or not
  for (const id of REGISTRY.chambers) assert.deepEqual(REGISTRY.canReach(id, [], "going_back_in"), {ok: true, missing: []}, id);
  for (const id of ["L4", "B1", "parking_lot", "street", "apartment"]) assert.equal(REGISTRY.canReach(id, REGISTRY.manifest.flags, "going_back_in").ok, false, `${id} is not a scene of a going_back_in room`);
});

// ---- co-op inside the games (session 11, slice 2): a game area marked `coop` has a place for each of its rooms or stages, and a room can follow its gate into it.
// The shipped manifest has Right Door, Wrong Exit coop (slice 3) and the Intern solo only until it can show other players (slice 4), so these use a copy with co-op switched on for either.
const withCoop = (games = ["rdwe", "intern"]) => {
  const d = clone(FARWAY);
  for (const a of d.areas) if (games.includes(a.id)) a.coop = true;
  for (const l of d.links) if (l.connector === "gate" && l.status === "built" && games.includes(l.to.area)) delete l.soloOnly;
  return d;
};
test("shipped: Right Door, Wrong Exit has game places a room reaches through its gate; the Intern has none", () => {
  assert.deepEqual(Object.keys(REGISTRY.gamePlaces), ["dining", "hallway", "teal", "teal2", "flooded", "trampoline", "grocery"].map(r => `rdwe:${r}`));
  assert.equal(REGISTRY.canReach("rdwe:dining", []).ok, true, "no flag is needed for the gate");
  assert.equal(REGISTRY.canReach("intern:S0", REGISTRY.manifest.flags).ok, false);
  assert.deepEqual(checkManifest(FARWAY, {worldDocs: worldDocs()}).warnings, []);
});
test("a coop game has a place per room (Right Door, Wrong Exit) or stage (the Intern), named area:room", () => {
  assert.deepEqual(validateManifest(withCoop()), []);
  const r = buildRegistry(withCoop());
  assert.deepEqual(Object.keys(r.gamePlaces).filter(p => p.startsWith("rdwe:")), ["dining", "hallway", "teal", "teal2", "flooded", "trampoline", "grocery"].map(x => `rdwe:${x}`));
  assert.deepEqual(Object.keys(r.gamePlaces).filter(p => p.startsWith("intern:")), ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"].map(x => `intern:${x}`));
  assert.deepEqual(r.gamePlaces["rdwe:teal"], {area: "rdwe", room: "teal"});
});
test("a room reaches a game's places through its gate, and only that game's", () => {
  const rdwe = buildRegistry(withCoop(["rdwe"]));
  assert.deepEqual(rdwe.canReach("rdwe:teal", [], "original"), {ok: true, missing: []}, "from the gate, any room of the game");
  assert.equal(rdwe.canReach("intern:S3", [], "original").ok, false, "the Intern is still solo only here");
  assert.equal(rdwe.canReach("rdwe:nowhere", [], "original").ok, false);
  const both = buildRegistry(withCoop());
  assert.equal(both.canReach("intern:S3", [], "original").ok, true);
  assert.equal(both.canReach("rdwe:dining", [], "going_back_in").ok, false, "a Going back in room has no gate to the games");
  assert.equal(both.canReach("L4", [], "original").ok, true, "and the way back is still there");
});
test("coop is checked: it needs a built game with rooms or stages, and its gate must then not say soloOnly", () => {
  bad(d => { d.areas.find(a => a.id === "rdwe").coop = "yes"; }, /coop must be true/);
  bad(d => { delete d.areas.find(a => a.id === "rdwe").rooms; }, /coop needs rooms or spine/);
  bad(d => { d.areas.find(a => a.id === "hotel").coop = true; }, /only a built area can be coop/);          // the hotel is still planned (the dreamcore forest, the first example here, is built now)
  bad(d => { d.areas.find(a => a.id === "intern").coop = true; }, /soloOnly/);          // coop game, but its gate still says soloOnly: say which one
  const d = withCoop(["rdwe"]); const gate = d.links.find(l => l.to.area === "rdwe" && l.connector === "gate" && l.status === "built");
  gate.to.room = "nowhere"; assert.ok(validateManifest(d).some(m => /nowhere/.test(m)), "a gate into a room the game does not have");
  const solo = clone(FARWAY); solo.links.find(l => l.to.area === "intern" && l.connector === "gate" && l.status === "built").soloOnly = false;
  assert.ok(validateManifest(solo).some(m => /neither multiplayer nor presence|soloOnly/.test(m)), "a gate a room can follow into a game that is not coop");
});
