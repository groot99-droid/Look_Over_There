import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {newHorn, tick, blast, call, recharge, addSpare, lost, blastTargets, knockEnd, knockDist, within, BLASTS, BLAST_RANGE_M, BLAST_ARC_DEG, KNOCK_M, STUN_S, COOL_S, CALL_R, BLAST_NOISE_R, SWAP_S} from "./horn.js";
import {indexBoxes} from "./world.js";

const monCfg = JSON.parse(readFileSync(new URL("../world/monsters.json", import.meta.url)));
const cfgOf = n => monCfg.monsters.find(m => m.name === n);
const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};
const mon = (x, z, o = {}) => ({pos: {x, z}, fy: 0, cfg: {height: 2}, ...o});
const eye = [0, 1.6, 0], facing = [0, -1];

test("a blast uses one of six battery charges and starts its 4 s cooldown; nothing blasts while cooling or flat", () => {
  assert.equal(BLASTS, 6); let h = newHorn(); assert.equal(h.charge, 6);
  const r = blast(h); assert.ok(r.ok); h = r.horn; assert.equal(h.charge, 5); assert.equal(h.coolB, COOL_S);
  assert.deepEqual(blast(h), {ok: false, why: "cooling"});
  h = tick(h, COOL_S); assert.ok(blast(h).ok);
  assert.deepEqual(blast({...newHorn(), charge: 0}), {ok: false, why: "empty"});
});
test("the call is free, has its own 4 s cooldown, and works with a flat battery", () => {
  let h = {...newHorn(), charge: 0}; const r = call(h); assert.ok(r.ok); h = r.horn; assert.equal(h.charge, 0); assert.equal(h.coolC, COOL_S);
  assert.deepEqual(call(h), {ok: false, why: "cooling"});
  const b = blast(newHorn()).horn; assert.ok(call(b).ok, "a blast does not stop the call"); assert.ok(blast(call(newHorn()).horn).ok, "and a call does not stop a blast");
});
test("a locker recharge is free and fills the battery; a death empties it and takes the spare", () => {
  const h = {...newHorn(), charge: 1, spare: 1}; assert.equal(recharge(h).charge, BLASTS); assert.equal(recharge(h).spare, 1, "the spare is kept");
  const l = lost(); assert.equal(l.charge, 0); assert.equal(l.spare, 0);
});
test("a flat battery with a spare swaps by itself in 3 s (no blasting meanwhile); with no spare it stays flat", () => {
  assert.equal(SWAP_S, 3);
  let h = {...newHorn(), charge: 1, spare: 0}; h = blast(h).horn; h = tick(h, 10); assert.equal(h.charge, 0); assert.equal(h.swapT, 0, "no spare: nothing to swap");
  h = addSpare({...newHorn(), charge: 1}); assert.equal(h.spare, 1); assert.equal(addSpare(h).spare, 1, "one spare at most");
  h = blast(h).horn; h = tick(h, COOL_S); assert.equal(h.charge, 0); assert.ok(h.swapT > 0 && h.swapT <= SWAP_S, "it started swapping: " + h.swapT);
  assert.deepEqual(blast(h), {ok: false, why: "swapping"});
  h = tick(h, SWAP_S); assert.equal(h.charge, BLASTS); assert.equal(h.spare, 0); assert.equal(h.swapT, 0);
});
test("the blast's cone: 10 m and 60 degrees, every monster in it, none behind, to the side, too far or behind a wall", () => {
  assert.equal(BLAST_RANGE_M, 10); assert.equal(BLAST_ARC_DEG, 60); assert.equal(STUN_S, 2);
  const a = mon(0, -3), b = mon(0, -9.9), far = mon(0, -10.5), side = mon(-5, -3), back = mon(0, 3);
  assert.deepEqual(blastTargets(W, [a, b, far, side, back], eye, facing), [a, b]);
  const walled = {...W, boxes: [{n: [-2, 0, -4.6], x: [2, 3, -4.0]}]}; indexBoxes(walled);
  assert.deepEqual(blastTargets(walled, [mon(0, -2), mon(0, -8)], eye, facing).map(m => m.pos.z), [-2]);
});
test("a monster is knocked back 6 m straight away from the horn (3 m for the clawed) and stops before a wall; nothing is damaged", () => {
  assert.equal(KNOCK_M, 6); assert.equal(knockDist(cfgOf("creature")), 6); assert.equal(knockDist(cfgOf("sinew")), 6); assert.equal(knockDist(cfgOf("pale_traveler")), 6); assert.equal(knockDist(cfgOf("clawed")), 3);
  const m = mon(0, -4); const [x, z] = knockEnd(W, m, [0, 0], 6); assert.ok(Math.abs(x) < 1e-9 && Math.abs(z + 10) < 0.01, `to z -10: ${x}, ${z}`);
  const side = mon(3, -4); const [sx, sz] = knockEnd(W, side, [0, 0], 5); assert.ok(Math.abs(Math.hypot(sx - 3, sz + 4) - 5) < 0.01, "5 m along the line from the horn through it");
  assert.ok(sx > 3 && sz < -4, "away from the horn");
  const walled = {...W, boxes: [{n: [-2, 0, -8.1], x: [2, 3, -7.5]}]}; indexBoxes(walled);
  const [, wz] = knockEnd(walled, mon(0, -4), [0, 0], 6); assert.ok(wz < -4 && wz > -7.5, `it stops short of the wall at -7.5: ${wz}`);
  const nav = new Uint8Array(4096); const edge = {...W, nav};                  // no walkable cells at all: it cannot be moved
  assert.deepEqual(knockEnd(edge, mon(0, -4), [0, 0], 6), [0, -4]);
});
test("the call and the blast are heard by every monster within 25 m and 40 m of the player", () => {
  assert.equal(CALL_R, 25); assert.equal(BLAST_NOISE_R, 40);
  const a = mon(34, 5), b = mon(10, -21), c = {...mon(11, 6), fy: 5}, d = mon(10, 30.5);          // from the player at (10, 0, 5): 24 m, 26 m, another floor, 25.5 m
  assert.deepEqual(within([a, b, c, d], 10, 0, 5, CALL_R), [a], "x, y, z in that order"); assert.deepEqual(within([a, b, d], 10, 0, 5, BLAST_NOISE_R), [a, b, d]);
});
