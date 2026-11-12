import test from "node:test";
import assert from "node:assert/strict";
import {SAVE_VERSION, makeSave, readSave} from "./save.js";
import {newNeeds} from "./needs.js";
import {newApplications} from "./application.js";

const live = () => ({t: 1234.5, needs: {...newNeeds(), hunger: 41.25, money: 33, pantry: {soup: 2, bread: 1}, cart: ["meal"], hasCart: true, lastPay: 24, lastNote: "ASSIMILATION"},
  apps: {...newApplications(), rejectedOn: {lab: 3}, accepted: {intern: true, trash: true}, active: "museum"}});

test("a save round-trips: the clock, hunger, money, the fridge, the last pay and the applications", () => {
  const r = readSave(JSON.stringify(makeSave(live())));
  assert.equal(r.t, 1234.5); assert.equal(r.needs.hunger, 41.25); assert.equal(r.needs.money, 33);
  assert.deepEqual(r.needs.pantry, {soup: 2, bread: 1}); assert.equal(r.needs.lastPay, 24); assert.equal(r.needs.lastNote, "ASSIMILATION");
  assert.deepEqual(r.apps.rejectedOn, {lab: 3}); assert.deepEqual(r.apps.accepted, {intern: true, trash: true});
});
test("what is not saved: the cart, and an application in progress", () => {
  const r = readSave(JSON.stringify(makeSave(live())));
  assert.deepEqual(r.needs.cart, []); assert.equal(r.needs.hasCart, false); assert.equal(r.apps.active, null);
});
test("no save, a corrupt one, or another version: ignored", () => {
  for (const bad of [null, "", "{", "[]", "42", JSON.stringify({v: SAVE_VERSION + 1, t: 5}), JSON.stringify({v: SAVE_VERSION, t: -1}), JSON.stringify({v: SAVE_VERSION, t: "soon"}), JSON.stringify({t: 5})]) assert.equal(readSave(bad), null, String(bad));
});
test("a tampered save is cleaned: numbers clamped, unknown foods and jobs dropped, defaults where a field is wrong", () => {
  const r = readSave(JSON.stringify({v: SAVE_VERSION, t: 10, needs: {hunger: 500, money: -7, pantry: {soup: 2.6, caviar: 9, bread: -1}, lastPay: "lots", lastNote: "x".repeat(99)},
    apps: {rejectedOn: {lab: 0, nowhere: 2, trash: 4}, accepted: {intern: "yes", factory: true, ceo: true}}}));
  assert.equal(r.needs.hunger, 100); assert.equal(r.needs.money, 0); assert.deepEqual(r.needs.pantry, {soup: 3});
  assert.equal(r.needs.lastPay, null); assert.equal(r.needs.lastNote.length, 40);
  assert.deepEqual(r.apps.rejectedOn, {trash: 4}); assert.deepEqual(r.apps.accepted, {factory: true});
  const thin = readSave(JSON.stringify({v: SAVE_VERSION, t: 0}));
  assert.equal(thin.needs.hunger, 80); assert.equal(thin.needs.money, 20); assert.deepEqual(thin.apps.accepted, {});
});

test("New Game forgets the save and every job flag, and keeps the Original's", async () => {
  const {NEW_GAME_KEYS, SAVE_KEY} = await import("./save.js");
  const {QUIZZES} = await import("./application.js");
  assert.ok(NEW_GAME_KEYS.includes(SAVE_KEY));
  for (const q of Object.values(QUIZZES)) assert.ok(NEW_GAME_KEYS.includes(q.flag), q.flag);
  assert.equal(NEW_GAME_KEYS.length, 1 + Object.keys(QUIZZES).length);
  assert.ok(!NEW_GAME_KEYS.includes("original_complete"));
});

test("rest is saved and read back, clamped; a save from before rest existed starts rested (slice 12)", async () => {
  const {REST} = await import("./needs.js");
  const s = makeSave({t: 10, needs: {...newNeeds(), rest: 37.5}, apps: newApplications()});
  assert.equal(s.needs.rest, 37.5);
  assert.equal(readSave(JSON.stringify(s)).needs.rest, 37.5);
  assert.equal(readSave(JSON.stringify({...s, needs: {...s.needs, rest: 400}})).needs.rest, REST.max);
  assert.equal(readSave(JSON.stringify({...s, needs: {...s.needs, rest: "x"}})).needs.rest, REST.start);
  const old = JSON.parse(JSON.stringify(s)); delete old.needs.rest;
  assert.equal(readSave(JSON.stringify(old)).needs.rest, REST.start);
});

test("what you have spotted and reported is saved; a tampered or old save is cleaned (slice 15)", async () => {
  const s = makeSave({t: 5, needs: newNeeds(), apps: newApplications(), seen: {spotted: {sign: true, peds: true}, reported: {sign: true}}});
  assert.deepEqual(readSave(JSON.stringify(s)).seen, {spotted: {sign: true, peds: true}, reported: {sign: true}});
  const bad = readSave(JSON.stringify({...s, seen: {spotted: {lamp: true, peds: "yes"}, reported: {window: true, bus: true}}}));
  assert.deepEqual(bad.seen, {spotted: {window: true}, reported: {window: true}}, "unreal ids dropped, non-true dropped, a reported one counts as spotted");
  const old = JSON.parse(JSON.stringify(s)); delete old.seen;
  assert.deepEqual(readSave(JSON.stringify(old)).seen, {spotted: {}, reported: {}});
  assert.deepEqual(makeSave({t: 1, needs: newNeeds(), apps: newApplications()}).seen, {spotted: {}, reported: {}});
});
