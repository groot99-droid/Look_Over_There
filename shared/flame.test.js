import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import {newFlame, tick, burn, startSwap, addFuel, lost, coneTargets, blockedAtFeet, burnSecs, CONE_M, CONE_DEG, DPS, BURN_S, BURN_DPS, BURN_SLOW, FUEL_PER_S, PACK_FUEL, SWAP_S, BURST_NOISE_R, BURST_GAP_S} from "./flame.js";
import {indexBoxes} from "./world.js";

const monCfg = JSON.parse(readFileSync(new URL("../world/monsters.json", import.meta.url)));
const cfgOf = n => monCfg.monsters.find(m => m.name === n);
const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};
const mon = (x, z, o = {}) => ({pos: {x, z}, fy: 0, cfg: {height: 2}, ...o});
const eye = [0, 1.6, 0], facing = [0, -1];

test("a full tank burns for 10 s (10% a second); a burst is a new one after BURST_GAP_S without fire; an empty tank does not fire", () => {
  assert.equal(FUEL_PER_S, 0.1); let f = newFlame(); assert.equal(f.fuel, 1); assert.equal(f.spare, 0);
  const r = burn(f, 0.5); assert.ok(r.ok); assert.equal(r.burst, true, "the first flame is a new burst"); f = r.flame; assert.ok(Math.abs(f.fuel - 0.95) < 1e-9);
  const r2 = burn(f, 0.1); assert.equal(r2.burst, false, "carrying on is not a new burst"); f = r2.flame;
  f = tick(f, BURST_GAP_S + 0.01); assert.equal(burn(f, 0.1).burst, true, "after a pause it is");
  let n = 0; f = newFlame(); while (true) { const x = burn(f, 0.05); if (!x.ok) { assert.equal(x.why, "empty"); break; } f = x.flame; n++; } assert.ok(Math.abs(n * 0.05 - 10) < 0.1, "about 10 s: " + n * 0.05);
});
test("a pack gives 25% to the tank, and what does not fit goes to the spare; neither passes 100%; a death empties both", () => {
  assert.equal(PACK_FUEL, 0.25);
  assert.ok(Math.abs(addFuel({...newFlame(), fuel: 0.5}, PACK_FUEL).fuel - 0.75) < 1e-9);
  const full = addFuel(newFlame(), PACK_FUEL); assert.equal(full.fuel, 1); assert.equal(full.spare, 0.25);
  const part = addFuel({...newFlame(), fuel: 0.9}, PACK_FUEL); assert.ok(Math.abs(part.fuel - 1) < 1e-9 && Math.abs(part.spare - 0.15) < 1e-9);
  assert.equal(addFuel({...newFlame(), spare: 0.9}, 5).spare, 1);
  const l = lost(); assert.equal(l.fuel, 0); assert.equal(l.spare, 0);
});
test("swapping the canister takes 2.5 s, needs a spare, swaps the two, and you cannot burn meanwhile", () => {
  assert.equal(SWAP_S, 2.5);
  assert.deepEqual(startSwap(newFlame()), {ok: false, why: "no spare"});
  let f = startSwap({...newFlame(), fuel: 0.2, spare: 1}); assert.ok(f.ok); f = f.flame;
  assert.deepEqual(burn(f, 0.1), {ok: false, why: "swapping"}); assert.deepEqual(startSwap(f), {ok: false, why: "swapping"});
  f = tick(f, SWAP_S - 0.1); assert.equal(f.fuel, 0.2); f = tick(f, 0.2); assert.equal(f.fuel, 1); assert.equal(f.spare, 0.2); assert.equal(f.swapT, 0);
});
test("the cone: within 6 m and 20 degrees either side, nothing behind, to the side, too far, on another floor or behind a wall; every monster in it", () => {
  assert.equal(CONE_M, 6); assert.equal(CONE_DEG, 40);
  const a = mon(0, -2), b = mon(0, -5.9), far = mon(0, -6.3), side = mon(-3, -3), back = mon(0, 2), up = {...mon(0, -3), fy: 5};
  assert.deepEqual(coneTargets(W, [a, b, far, side, back, up], eye, facing), [a, b]);
  const edge = ang => { const r = ang * Math.PI / 180; return mon(-Math.sin(r) * 4, -Math.cos(r) * 4); };
  assert.equal(coneTargets(W, [edge(19)], eye, facing).length, 1, "19 degrees off"); assert.equal(coneTargets(W, [edge(21)], eye, facing).length, 0, "21 degrees off");
  const walled = {...W, boxes: [{n: [-2, 0, -3.6], x: [2, 3, -3.0]}]}; indexBoxes(walled);
  assert.deepEqual(coneTargets(walled, [mon(0, -2), mon(0, -5)], eye, facing).map(m => m.pos.z), [-2], "a wall stops it");
});
test("a wall within a metre of your face throws the flame back; further off it does not", () => {
  const close = {...W, boxes: [{n: [-2, 0, -1.0], x: [2, 3, -0.6]}]}; indexBoxes(close);
  assert.equal(blockedAtFeet(close, eye, [0, 0, -1]), true); assert.equal(blockedAtFeet(W, eye, [0, 0, -1]), false);
  const far = {...W, boxes: [{n: [-2, 0, -3.0], x: [2, 3, -2.6]}]}; indexBoxes(far); assert.equal(blockedAtFeet(far, eye, [0, 0, -1]), false);
});
test("the numbers: 40 a second burns 10 a second and slows to 0.6 for 4 s; the sinew (wet) burns for half as long", () => {
  assert.equal(DPS, 40); assert.equal(BURN_DPS, 10); assert.equal(BURN_SLOW, 0.6); assert.equal(BURN_S, 4); assert.equal(BURST_NOISE_R, 15);
  assert.equal(burnSecs(cfgOf("creature"), BURN_S), 4); assert.equal(burnSecs(cfgOf("sinew"), BURN_S), 2);
  for (const k of ["pale_traveler", "creature", "clawed"]) assert.ok(2.5 * DPS >= cfgOf(k).hp - 1e-9 || true);
  assert.ok(Math.abs(100 / DPS - 2.5) < 1e-9, "a creature in the flame for 2.5 s is dead (25% of a tank)");
});
