import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {newBaton, tick, swing, discharge, swingTarget, dischargeTargets, stunFor, CAPS, REACH_M, ARC_DEG, SWING_DMG, SWING_STUN_S, COOL_S, RECHARGE_S, BURST_R, BURST_DMG, BURST_STUN_S, DEAD_S, HIT_NOISE_S, BURST_NOISE_R} from "./baton.js";
import {SHOT_NOISE_S as BOW_NOISE_S} from "./crossbow.js";
import {indexBoxes} from "./world.js";

const monCfg = JSON.parse(readFileSync(new URL("../world/monsters.json", import.meta.url)));
const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};       // open ground: every ray is clear
const mon = (x, z, cfg = {height: 2}) => ({pos: {x, z}, fy: 0, cfg});
const eye = [0, 1.6, 0], facing = [0, -1];                                      // at the origin, looking down -z

test("a swing that hits uses a capacitor and starts the cooldown; a whiff costs nothing but the cooldown; no capacitors, no swing", () => {
  let b = newBaton(); assert.equal(b.caps, CAPS);
  let r = swing(b, true); assert.ok(r.ok); b = r.baton; assert.equal(b.caps, CAPS - 1); assert.equal(b.cool, COOL_S);
  assert.deepEqual(swing(b, true), {ok: false, why: "cooling"});
  b = tick(b, COOL_S); r = swing(b, false); assert.ok(r.ok); assert.equal(r.baton.caps, CAPS - 1, "a whiff is free");
  assert.deepEqual(swing({...newBaton(), caps: 0}, true), {ok: false, why: "empty"});
});
test("an empty capacitor recharges in RECHARGE_S, one at a time, and the bank stops at full", () => {
  let b = {...newBaton(), caps: 0};
  b = tick(b, RECHARGE_S - 0.01); assert.equal(b.caps, 0); b = tick(b, 0.02); assert.equal(b.caps, 1);
  b = tick(b, RECHARGE_S * 5); assert.equal(b.caps, CAPS); assert.equal(b.charge, 0);
});
test("three hits cannot kill a 100 health monster (25 each); the fourth would, which needs a capacitor it does not have yet", () => {
  assert.equal(SWING_DMG, 25); assert.ok(CAPS * SWING_DMG < 100, "alone it cannot kill a creature at once");
});
test("the discharge needs all three capacitors and leaves the baton dead for DEAD_S (no charging while dead)", () => {
  let b = newBaton();
  b = swing(b, true).baton; b = tick(b, COOL_S);
  assert.deepEqual(discharge(b), {ok: false, why: "charging"}, "only two capacitors");
  b = tick(b, RECHARGE_S); assert.equal(b.caps, CAPS);
  const r = discharge(b); assert.ok(r.ok); b = r.baton; assert.equal(b.caps, 0); assert.equal(b.dead, DEAD_S);
  assert.deepEqual(swing(tick(b, 1), true), {ok: false, why: "dead"});
  b = tick(b, DEAD_S - 0.5); assert.equal(b.caps, 0, "still dead and not charging"); b = tick(b, 0.5); assert.equal(b.dead, 0);
  b = tick(b, RECHARGE_S); assert.equal(b.caps, 1, "charging starts again after it wakes");
});
test("the stun is as long as the swing says, 1.5 times on the sinew (it is wet), and nothing else changes", () => {
  const cfg = n => monCfg.monsters.find(m => m.name === n);
  assert.equal(stunFor(cfg("creature"), SWING_STUN_S), 4); assert.equal(stunFor(cfg("clawed"), SWING_STUN_S), 4); assert.equal(stunFor(cfg("pale_traveler"), SWING_STUN_S), 4);
  assert.equal(stunFor(cfg("sinew"), SWING_STUN_S), 6); assert.equal(stunFor(cfg("sinew"), BURST_STUN_S), 4.5);
});
test("a swing hits the nearest monster within reach and inside the arc, and nothing behind, to the side, too far or behind a wall", () => {
  const near = mon(0, -1.5), far = mon(0, -1.7);
  assert.equal(swingTarget(W, [far, near], eye, facing), near);
  assert.equal(swingTarget(W, [mon(0, -REACH_M - 0.2)], eye, facing), null, "past the reach");
  assert.equal(swingTarget(W, [mon(0, 1.2)], eye, facing), null, "behind you");
  const a = ARC_DEG / 2 * Math.PI / 180;
  assert.ok(swingTarget(W, [mon(-Math.sin(a * 0.9) * 1.5, -Math.cos(a * 0.9) * 1.5)], eye, facing), "just inside the arc");
  assert.equal(swingTarget(W, [mon(-Math.sin(a * 1.3) * 1.5, -Math.cos(a * 1.3) * 1.5)], eye, facing), null, "just outside the arc");
  assert.equal(swingTarget(W, [{...mon(0, -1.2), fy: 5}], eye, facing), null, "another floor");
  const walled = {...W, boxes: [{n: [-1, 0, -0.9], x: [1, 3, -0.7]}]}; indexBoxes(walled);
  assert.equal(swingTarget(walled, [mon(0, -1.5)], eye, facing), null, "a wall between");
});
test("the discharge reaches every monster within BURST_R on the player's floor", () => {
  const a = mon(3, 0), b = mon(0, -BURST_R + 0.1), far = mon(5, 0), up = {...mon(1, 1), fy: 5};
  assert.deepEqual(dischargeTargets([a, b, far, up], 0, 0, 0), [a, b]);
  assert.equal(BURST_DMG, 15); assert.equal(BURST_STUN_S, 3);
});
test("a hit is a puff as quiet as the crossbow's; the discharge is a bang heard by monsters within 15 m", () => {
  assert.equal(HIT_NOISE_S, BOW_NOISE_S); assert.equal(BURST_NOISE_R, 15);
});
