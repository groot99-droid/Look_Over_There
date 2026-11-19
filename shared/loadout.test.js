import test from "node:test";
import assert from "node:assert/strict";
import {GEAR, SOLO_GEAR, ARSENAL, MAX_ARSENAL, newLoadout, carries, take, leave, died, canTake, arsenalCarried} from "./loadout.js";

test("a new loadout carries everything by default; the locker holds what you leave", () => {
  const l = newLoadout(); assert.deepEqual(l, {carry: GEAR, stash: []});
  const m = leave(l, "crossbow"); assert.ok(!carries(m, "crossbow")); assert.deepEqual(m.stash, ["crossbow"]);
  assert.deepEqual(take(m, "crossbow"), l, "taking it back");
  assert.equal(take(l, "gun"), l, "not in the locker: nothing changes"); assert.equal(leave(m, "gun").carry.includes("gun"), false);
  assert.equal(leave(l, "nope"), l);
});
test("after a death the locker holds all the gear and you carry none, whatever you had", () => {
  for (const carry of [GEAR, ["gun"], []]) {
    const d = died(newLoadout(carry)); assert.deepEqual(d.carry, []); assert.deepEqual([...d.stash].sort(), [...GEAR].sort());
  }
  const back = GEAR.reduce(take, died(newLoadout())); assert.deepEqual(back.carry.sort(), [...GEAR].sort(), "all of it comes back for free");
});
test("the bolt driver is solo gear: a room's loadout (GEAR) has no driver, a solo one carries it, and a death puts it in the locker", () => {
  assert.ok(!GEAR.includes("driver")); assert.deepEqual(SOLO_GEAR, [...GEAR, "driver", "baton", "dart", "flame", "horn", "rocket", "laser"]);
  assert.ok(!carries(newLoadout(), "driver"));
  const l = newLoadout(["gun", "cloak", "crossbow", "driver"], SOLO_GEAR); assert.ok(carries(l, "driver")); assert.deepEqual(l.stash, ["baton", "dart", "flame", "horn", "rocket", "laser"]);
  const m = leave(l, "driver"); assert.deepEqual(m.stash, ["baton", "dart", "flame", "horn", "rocket", "laser", "driver"]); assert.ok(carries(take(m, "driver"), "driver"));
  assert.deepEqual(died(l), {carry: [], stash: SOLO_GEAR}); assert.deepEqual(died(newLoadout()), {carry: [], stash: GEAR});
});
test("you carry at most MAX_ARSENAL (2) of the arsenal weapons: the locker refuses a third until you leave one", () => {
  assert.equal(MAX_ARSENAL, 2); assert.deepEqual(ARSENAL, ["crossbow", "driver", "baton", "dart", "flame", "horn", "rocket", "laser"]);
  const l = newLoadout(["gun", "cloak", "crossbow", "driver"], SOLO_GEAR); assert.deepEqual(l.stash, ["baton", "dart", "flame", "horn", "rocket", "laser"]); assert.deepEqual(arsenalCarried(l), ["crossbow", "driver"]);
  assert.equal(canTake(l, "baton"), false); assert.equal(take(l, "baton"), l, "refused: the same loadout back");
  const m = leave(l, "crossbow"); assert.equal(canTake(m, "baton"), true);
  const n = take(m, "baton"); assert.deepEqual(arsenalCarried(n), ["driver", "baton"], "the order you took them in is the order of the weapon slots");
  assert.equal(canTake(n, "crossbow"), false);
  assert.equal(canTake(l, "gun"), false, "not in the locker"); assert.equal(canTake(leave(l, "gun"), "gun"), true, "the ray and the cloak are not capped");
  assert.deepEqual(died(n), {carry: [], stash: SOLO_GEAR}); assert.equal(arsenalCarried(died(n)).length, 0, "after a death you may take any two back");
});
