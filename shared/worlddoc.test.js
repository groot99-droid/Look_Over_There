import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import {checkWorldDoc, linkStanzas, blocked, onFloor} from "./worlddoc.js";
import {FARWAY} from "./farway.manifest.js";

// a small Blender-first room: a floor 10 m by 8 m, four walls, a counter, one door out, a zone and two spots
const room = () => ({
  scene: "test_room",
  colliders: [
    {s: "COL_Floor", min: [-5, -0.2, -4], max: [5, 0, 4]},
    {s: "COL_Wall_N", min: [-5, 0, -4.2], max: [5, 3, -4]}, {s: "COL_Wall_S", min: [-5, 0, 4], max: [5, 3, 4.2]},
    {s: "COL_Wall_W", min: [-5.2, 0, -4], max: [-5, 3, 4]}, {s: "COL_Wall_E", min: [5, 0, -4], max: [5.2, 3, 4]},
    {s: "COL_Counter", min: [-4, 0, -3.5], max: [-1, 1, -2.5]},
  ],
  doors: [{name: "DoorLeaf_Front", level: "test_room", hinge: [-0.47, 0, 4], width: 0.94, height: 2.16, closed_yaw_deg: 0, swing_deg: 95, state: "closed"}],
  cameras: [], markers: [{name: "Spawn_door", kind: "Spawn", level: "test_room", position: [0, 0, 3]}],
  links: [{door: "front_door", at: [0, 0, 3.4], arrive: [0, 0, 3], face: [0, -1]}],
  zones: [{kind: "safe", name: "Zone_safe_room", min: [-5, 0, -4], max: [5, 3, 4]}],
  spots: [{kind: "locker", name: "Spot_locker_1", position: [4.5, 0, 0]}, {kind: "shop", name: "Spot_shop_1", position: [-2.5, 0, -2]}],
});
const errs = (doc, opts) => checkWorldDoc(doc, opts).errors;
const has = (list, re) => list.some(m => re.test(m));

test("every layout file in world/ passes, with or without the manifest", () => {
  const files = fs.readdirSync(new URL("../world/", import.meta.url)).filter(f => f.endsWith(".json") && f !== "monsters.json");
  assert.ok(files.length >= 17, "the world files are found");
  for (const f of files) {
    const doc = JSON.parse(fs.readFileSync(new URL(`../world/${f}`, import.meta.url), "utf8"));
    assert.deepEqual(errs(doc), [], f); assert.deepEqual(errs(doc, {manifest: FARWAY}), [], `${f} against the manifest`);
  }
});

test("a well-made Blender-first room passes", () => {
  const r = checkWorldDoc(room()); assert.deepEqual(r.errors, []); assert.deepEqual(r.warnings, []);
});

test("the shape is checked: lists, boxes, doors, markers, links, zones and spots", () => {
  assert.ok(has(errs(null), /not an object/));
  { const d = room(); delete d.cameras; assert.ok(has(errs(d), /cameras: must be a list/)); }
  { const d = room(); d.spots = {}; assert.ok(has(errs(d), /spots: must be a list/)); }
  { const d = room(); d.colliders[1].min = [5, 0, -4.2]; assert.ok(has(errs(d), /COL_Wall_N.*min must be below max/)); }
  { const d = room(); d.colliders[0].max = [5, 0]; assert.ok(has(errs(d), /three numbers each/)); }
  { const d = room(); delete d.colliders[2].s; assert.ok(has(errs(d), /needs a name in s/)); }
  { const d = room(); d.doors[0].state = "wide"; d.doors[0].width = 0; assert.ok(has(errs(d), /state must be one of/)); assert.ok(has(errs(d), /width must be a positive number/)); }
  { const d = room(); d.markers[0].kind = "Start"; assert.ok(has(errs(d), /kind must be one of Spawn/)); }
  { const d = room(); d.links[0].face = [0, -2]; assert.ok(has(errs(d), /face must have length 1/)); }
  { const d = room(); delete d.links[0].arrive; assert.ok(has(errs(d), /a Link_ needs its Arrive_/)); }
  { const d = room(); d.zones[0].kind = "lava"; assert.ok(has(errs(d), /zone Zone_safe_room: kind must be one of/)); }
  { const d = room(); delete d.spots[0].kind; assert.ok(has(errs(d), /Spot_locker_1: needs a kind/)); }
});

test("names are used once", () => {
  { const d = room(); d.doors.push({...d.doors[0]}); assert.ok(has(errs(d), /door DoorLeaf_Front: the name is used twice/)); }
  { const d = room(); d.links.push({...d.links[0]}); assert.ok(has(errs(d), /link front_door: the name is used twice/)); }
  { const d = room(); d.spots.push({...d.spots[0]}); assert.ok(has(errs(d), /spot Spot_locker_1: the name is used twice/)); }
});

test("a walker must be able to stand at every link, spot and spawn: clear of the colliders, with a floor under the feet", () => {
  const d0 = room();
  assert.equal(blocked(d0.colliders, [0, 0, 3]), null); assert.equal(blocked(d0.colliders, [-2.5, 0, -3]).s, "COL_Counter"); assert.equal(blocked(d0.colliders, [4.9, 0, 0]).s, "COL_Wall_E", "within the walker's radius of a wall");
  assert.equal(onFloor(d0.colliders, [0, 0, 0]), true); assert.equal(onFloor(d0.colliders, [0, 1, 0]), false); assert.equal(onFloor(d0.colliders, [-2.5, 1, -3]), true, "standing on the counter");
  { const d = room(); d.links[0].arrive = [-2.5, 0, -3]; assert.ok(has(errs(d), /link front_door: arrive .* inside the collider COL_Counter/)); }
  { const d = room(); d.links[0].at = [0, 0, 9]; assert.ok(has(errs(d), /link front_door: at .* no floor under it/)); }
  { const d = room(); d.spots[1].position = [-2.5, 0.4, -3]; assert.ok(has(errs(d), /spot Spot_shop_1 .* inside the collider/)); }
  { const d = room(); d.markers[0].position = [0, 2, 3]; assert.ok(has(errs(d), /marker Spawn_door .* no floor under it/)); }
  { const d = room(); d.links = []; d.markers = []; assert.ok(has(errs(d), /no way in/)); }
});

test("an older file is not held to the Blender-first rules", () => {
  const d = room(); delete d.links; delete d.zones; delete d.spots; d.markers = [{name: "Exit_down", kind: "Exit", level: "x", position: [0, -2.75, 0]}, {name: "Exit_down", kind: "Exit", level: "x", position: [0, -2.75, 1]}];
  const r = checkWorldDoc(d); assert.deepEqual(r.errors, []); assert.ok(has(r.warnings, /marker Exit_down: the name is used twice/));
});

test("a Blender-first scene much larger than a store floor is warned about, not refused", () => {
  const d = room(); d.colliders.push({s: "COL_Far", min: [70, 0, 0], max: [71, 3, 1]});
  const r = checkWorldDoc(d); assert.deepEqual(r.errors, []); assert.ok(has(r.warnings, /75 m along x|76 m along x/));
});

test("against the manifest: its links from the scene need a link in the file, and the file's new doors are named", () => {
  const manifest = {areas: [{id: "hotel", scenes: [{id: "test_room"}, {id: "hall"}]}], links: [
    {id: "hotel.test_room>hall", from: {area: "hotel", scene: "test_room", door: "front_door"}, to: {area: "hotel", scene: "hall", arrive: [0, 0, 0], face: [0, 1]}},
    {id: "hotel.hall>test_room", from: {area: "hotel", scene: "hall", door: "room_door"}, to: {area: "hotel", scene: "test_room", arrive: [0, 0, 3], face: [0, -1]}},
  ]};
  assert.deepEqual(checkWorldDoc(room(), {manifest}), {errors: [], warnings: []});
  { const d = room(); d.links[0].door = "side_door"; const r = checkWorldDoc(d, {manifest});
    assert.ok(has(r.errors, /hotel.test_room>hall leaves by the door front_door, which the file has no link for/)); assert.ok(has(r.warnings, /link side_door: the manifest has no link from this door yet/)); }
  { const d = room(); d.links[0].arrive = [1, 0, 3]; assert.ok(has(checkWorldDoc(d, {manifest}).warnings, /hotel.hall>test_room arrives at \(0, 0, 3\), which is no arrive point of the file/)); }
  { const d = room(); d.scene = "new_room"; assert.ok(has(checkWorldDoc(d, {manifest}).warnings, /scene new_room is not in the world manifest yet/)); }
});

test("linkStanzas writes what to paste into the manifest", () => {
  const t = linkStanzas(room(), "hotel");
  assert.match(t, /plan\("hotel.test_room.front_door", \{area: "hotel", scene: "test_room", door: "front_door"\}/); assert.match(t, /arrive: \[0, 0, 3\], face: \[0, -1\]/);
  assert.equal(linkStanzas({scene: "x"}), "");
});
