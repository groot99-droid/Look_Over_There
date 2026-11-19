import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {newLaser, beam, dot, idle, addCharge, lost, dps, dmgMul, dotHears, RANGE_M, DPS_MIN, DPS_MAX, RAMP_S, LOSE_S, DRAIN_PER_S, DOT_DRAIN_PER_S, HEAT_S, LOCK_S, SWAP_S, MAX_SPARES, PACK_CHARGE, DOT_R} from "./laser.js";
import {indexBoxes} from "./world.js";

const monCfg = JSON.parse(readFileSync(new URL("../world/monsters.json", import.meta.url)));
const cfgOf = n => monCfg.monsters.find(m => m.name === n);
const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};
const A = {id: "a"}, B = {id: "b"};
// hold the beam on `target` for secs, in 0.05 s steps; returns the state and the damage dealt
function hold(l, target, secs) { let dmg = 0; for (let t = 0; t < secs - 1e-9; t += 0.05) { const r = beam(l, 0.05, target); if (!r.ok) return {l, dmg, why: r.why}; l = r.laser; dmg += r.dmg; } return {l, dmg}; }

test("the damage climbs from 15 to 60 a second over 2 s on one target: 75 in the first 2 s, so a creature (100) dies at about 2.4 s", () => {
  assert.equal(dps(0), DPS_MIN); assert.equal(dps(RAMP_S), DPS_MAX); assert.equal(dps(9), DPS_MAX); assert.equal(dps(1), 37.5); assert.equal(RANGE_M, 30);
  const two = hold(newLaser(), A, 2); assert.ok(Math.abs(two.dmg - 75) < 1, "75 in 2 s: " + two.dmg);
  let l = newLaser(), dmg = 0, t = 0; while (dmg < 100) { const r = beam(l, 0.05, A); l = r.laser; dmg += r.dmg; t += 0.05; } assert.ok(Math.abs(t - 2.42) < 0.08, "a creature at " + t);
});
test("leaving the target for more than 0.3 s starts the climb again; a shorter slip does not; another monster starts it at once", () => {
  let l = hold(newLaser(), A, 1.5).l; assert.ok(Math.abs(l.onT - 1.5) < 1e-6);
  l = hold(l, null, 0.2).l; assert.ok(l.onT > 1.4, "a 0.2 s slip keeps the climb"); l = beam(l, 0.05, A).laser; assert.ok(l.onT > 1.5);
  l = hold(l, null, LOSE_S + 0.1).l; assert.equal(l.onT, 0, "0.4 s off the target resets it");
  l = hold(newLaser(), A, 1.5).l; const r = beam(l, 0.05, B); assert.ok(r.dmg < 1, "the second monster starts at 15 a second: " + r.dmg); assert.equal(r.laser.target, B);
  l = idle(hold(newLaser(), A, 1.5).l, 0.5); assert.equal(l.onT, 0, "letting go of the trigger for 0.5 s resets it too");
});
test("the beam uses 8% of the battery a second (12.5 s a pack) and the dot 0.5%; an empty battery with no spare does nothing", () => {
  assert.equal(DRAIN_PER_S, 0.08); assert.equal(DOT_DRAIN_PER_S, 0.005);
  let l = {...newLaser(), spares: 0}; l = hold(l, null, 1).l; assert.ok(Math.abs(l.charge - 0.92) < 1e-6);
  let d = dot({...newLaser(), spares: 0}, 2); assert.ok(d.ok); assert.ok(Math.abs(d.laser.charge - 0.99) < 1e-9);
  assert.deepEqual(beam({...newLaser(), charge: 0, spares: 0}, 0.05, A), {ok: false, why: "empty"}); assert.deepEqual(dot({...newLaser(), charge: 0, spares: 0}, 0.05), {ok: false, why: "empty"});
});
test("after 5 s of beam it overheats and locks for 3 s; resting cools it, so two 3 s bursts with a rest between do not", () => {
  assert.equal(HEAT_S, 5); assert.equal(LOCK_S, 3);
  let r = hold(newLaser(), A, 5.2); assert.equal(r.why, "overheated"); let l = r.l; assert.ok(l.lock > 2.7 && l.lock <= LOCK_S);
  assert.deepEqual(dot(l, 0.05), {ok: false, why: "overheated"}, "the dot is locked too");
  l = idle(l, LOCK_S); assert.equal(l.lock, 0); assert.ok(beam(l, 0.05, A).ok);
  l = hold(newLaser(), A, 3).l; l = idle(l, 3); l = hold(l, A, 3); assert.equal(l.why, undefined, "3 s on, 3 s off, 3 s on: no overheat");
});
test("you start with a full pack and one spare; a flat pack swaps to a spare by itself in 2 s; two spares at most; a pack pickup adds 25%; a death takes it all", () => {
  let l = newLaser(); assert.equal(l.charge, 1); assert.equal(l.spares, 1); assert.equal(MAX_SPARES, 2); assert.equal(SWAP_S, 2); assert.equal(PACK_CHARGE, 0.25);
  l = {...l, charge: 0.01}; l = beam(l, 0.2, A).laser; assert.equal(l.charge, 0); assert.ok(l.swapT > 0, "it starts swapping");
  assert.deepEqual(beam(l, 0.05, A), {ok: false, why: "swapping"});
  l = idle(l, SWAP_S); assert.equal(l.charge, 1); assert.equal(l.spares, 0); assert.equal(l.swapT, 0);
  assert.ok(Math.abs(addCharge({...newLaser(), charge: 0.5}, PACK_CHARGE).charge - 0.75) < 1e-9); assert.equal(addCharge(newLaser(), PACK_CHARGE).charge, 1, "a full pack stays at 100%");
  const d = lost(); assert.equal(d.charge, 0); assert.equal(d.spares, 0);
});
test("the pale traveler takes 1.25 times the laser's damage; the others take it as it is", () => {
  assert.equal(dmgMul(cfgOf("pale_traveler")), 1.25); for (const k of ["creature", "clawed", "sinew"]) assert.equal(dmgMul(cfgOf(k)), 1);
});
test("the dot draws a monster that is patrolling or searching, within 12 m of it and with a clear line to it; never one that is chasing", () => {
  assert.equal(DOT_R, 12);
  const mon = (x, z, state = "patrol") => ({pos: {x, z}, fy: 0, cfg: {height: 2}, state});
  const a = mon(5, 0), b = mon(0, 11, "search"), far = mon(13, 0), hunting = mon(3, 0, "chase"), up = {...mon(1, 1), fy: 5};
  assert.deepEqual(dotHears(W, [a, b, far, hunting, up], [0, 0.2, 0]), [a, b]);
  const walled = {...W, boxes: [{n: [2, 0, -3], x: [2.6, 3, 3]}]}; indexBoxes(walled);
  assert.deepEqual(dotHears(walled, [mon(5, 0)], [0, 0.2, 0]), [], "a wall between it and the dot");
});
