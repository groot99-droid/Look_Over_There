import test from "node:test";
import assert from "node:assert/strict";
import {newShear, tick, hold, release, resetHold, addCuts, addSpare, lost, worn, spooled, blocked, helpless, cutTarget, CUTS, DMG, DMG_WORN, SPOOL_S, READY_S, COOL_S, RESET_S, REACH_M, MAX_SPARES, SWAP_S, PACK_CUTS, WALK_K} from "./shear.js";

const MON = {kind: "monster", helpless: false}, STUNNED = {kind: "monster", helpless: true}, CAGE = {kind: "barricade"};
const spool = s => hold(s, SPOOL_S);
// one whole cut: wait out the cooldown, spool, release on `target`
const cut = (s, target) => release(spool(tick(s, COOL_S)), target);
const wearOut = () => { let s = newShear(); for (let i = 0; i < CUTS; i++) s = cut(s, MON).shear; return s; };

test("the motor spools for 1 s, holds ready for 3 s, then winds down; letting go early cuts nothing and spends nothing", () => {
  let s = hold(newShear(), 0.6); assert.ok(!spooled(s));
  const early = release(s, MON); assert.deepEqual([early.ok, early.why, early.shear.cuts, early.shear.spool], [false, "early", CUTS, 0]);
  s = hold(hold(newShear(), 0.6), 0.5); assert.ok(spooled(s));
  s = hold(s, READY_S - 0.1); assert.ok(spooled(s), "still ready just inside 3 s"); s = hold(s, 0.2); assert.ok(!spooled(s), "held too long: it has to spool again");
  assert.equal(SPOOL_S, 1); assert.equal(READY_S, 3); assert.equal(REACH_M, 2); assert.equal(WALK_K, 0.8);
});
test("a fresh spring has four cuts and each kills anything (200); after a cut it cools for 1.5 s", () => {
  assert.equal(CUTS, 4); assert.equal(DMG, 200);
  let s = newShear(); const r = release(spool(s), MON); assert.ok(r.ok); assert.equal(r.dmg, 200); assert.equal(r.wornCut, false); s = r.shear; assert.equal(s.cuts, 3); assert.equal(s.cool, COOL_S);
  assert.equal(blocked(s), "cooling"); assert.ok(!spooled(hold(s, 2)), "it will not spool while cooling"); assert.ok(spooled(spool(tick(s, COOL_S))));
  for (let i = 0; i < 3; i++) { const x = cut(s, MON); assert.equal(x.dmg, 200); s = x.shear; }
  assert.equal(s.cuts, 0); assert.ok(worn(s)); assert.equal(s.needReset, false, "the fourth fresh cut needs no reset");
});
test("a cut on empty air still uses a fresh cut; a cut opens a barricade and uses one too", () => {
  const a = release(spool(newShear()), null); assert.ok(a.ok); assert.equal(a.dmg, 0); assert.equal(a.opened, false); assert.equal(a.shear.cuts, CUTS - 1);
  const b = release(spool(newShear()), CAGE); assert.equal(b.opened, true); assert.equal(b.shear.cuts, CUTS - 1);
});
test("a worn spring: 100 to a monster moving freely, a kill (200) on a helpless one, a barricade still opens, and nothing is spent", () => {
  assert.equal(DMG_WORN, 100);
  const s = wearOut(); assert.ok(worn(s));
  const free = cut(s, MON); assert.equal(free.dmg, 100); assert.equal(free.wornCut, true); assert.equal(free.shear.cuts, 0);
  assert.equal(cut(s, STUNNED).dmg, 200); assert.equal(cut(s, CAGE).opened, true); assert.equal(cut(s, null).dmg, 0);
});
test("after every worn cut the jaw must be reset by hand: 3 s of holding, and letting go starts over", () => {
  assert.equal(RESET_S, 3);
  let s = cut(wearOut(), MON).shear; assert.equal(s.needReset, true); s = tick(s, COOL_S);
  assert.equal(blocked(s), "reset"); assert.ok(!spooled(hold(s, 5)), "it will not spool until it is reset");
  s = resetHold(s, 2.9, true); assert.equal(s.needReset, true); s = resetHold(s, 0.05, false); assert.equal(s.reset, 0, "let go: start over");
  s = resetHold(s, 2.9, true); assert.equal(s.needReset, true); s = resetHold(s, 0.2, true); assert.equal(s.needReset, false);
  assert.ok(spooled(spool(s))); const again = release(spool(s), MON); assert.equal(again.shear.needReset, true, "and the next worn cut needs it again");
  assert.equal(resetHold(newShear(), 5, true).reset, 0, "a fresh shear has nothing to reset");
});
test("fluid: a pack gives 2 cuts and a fresh spring (no reset owed); never more than 4; two spares at most", () => {
  assert.equal(PACK_CUTS, 2); assert.equal(MAX_SPARES, 2);
  let s = cut(wearOut(), MON).shear; assert.equal(s.needReset, true);
  s = addCuts(s, PACK_CUTS); assert.equal(s.cuts, 2); assert.equal(s.needReset, false); assert.ok(!worn(s)); assert.equal(cut(s, MON).dmg, 200);
  assert.equal(addCuts(newShear(), PACK_CUTS).cuts, CUTS); assert.equal(addSpare(addSpare(addSpare(newShear()))).spares, MAX_SPARES);
});
test("with a spare, the last fresh cut starts a 2 s swap by itself and the spring is fresh again; a death takes the cuts and the spares", () => {
  assert.equal(SWAP_S, 2);
  let s = addSpare(newShear()); for (let i = 0; i < CUTS; i++) s = cut(s, MON).shear;
  assert.equal(s.cuts, 0); assert.ok(s.swapT > 0); assert.equal(blocked(s), "swapping"); assert.ok(!spooled(hold(s, 2)));
  s = tick(s, SWAP_S); assert.equal(s.cuts, CUTS); assert.equal(s.spares, 0); assert.ok(!worn(s));
  const d = lost(); assert.equal(d.cuts, 0); assert.equal(d.spares, 0); assert.ok(worn(d)); assert.equal(d.needReset, false, "you come back worn, but the first cut is yours");
});
test("helpless: stunned, slowed or held; a free monster is not", () => {
  const m = o => ({stunT: 0, slowMul: () => 1, ...o});
  assert.equal(helpless(m()), false); assert.equal(helpless(m({stunT: 0.4})), true); assert.equal(helpless(m({slowMul: () => 0.5})), true); assert.equal(helpless(m({held: true})), true);
});
test("the cut bites the nearest monster within 2 m and 15 degrees either side, or a shut barricade in reach; nothing behind, far or already open", () => {
  const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null}, eye = [0, 1.6, 0], f = [0, -1];
  const mon = (x, z, o = {}) => ({pos: {x, z}, fy: 0, cfg: {height: 2}, stunT: 0, slowMul: () => 1, ...o});
  const a = mon(0, -1.5), far = mon(0, -2.3), side = mon(-1, -1.2), stunned = mon(0, -1.2, {stunT: 1});
  assert.equal(cutTarget(W, [far, a], [], eye, f).m, a); assert.equal(cutTarget(W, [far, side], [], eye, f), null);
  assert.deepEqual([cutTarget(W, [a, stunned], [], eye, f).m, cutTarget(W, [a, stunned], [], eye, f).helpless], [stunned, true]);
  const cage = {id: "cage", x: 0.6, z: -1.4, y: 0, open: false};
  assert.equal(cutTarget(W, [], [cage], eye, f).b, cage, "a barricade is big: 23 degrees off still bites");
  assert.equal(cutTarget(W, [], [{...cage, open: true}], eye, f), null); assert.equal(cutTarget(W, [], [{...cage, z: 1.4}], eye, f), null, "behind you");
  assert.equal(cutTarget(W, [a], [{...cage, x: 0, z: -1.0}], eye, f).kind, "barricade", "the nearer of the two");
});
