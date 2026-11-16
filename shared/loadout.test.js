import test from "node:test";
import assert from "node:assert/strict";
import {GEAR, newLoadout, carries, take, leave, died} from "./loadout.js";

test("a new loadout carries everything by default; the locker holds what you leave", () => {
  const l = newLoadout(); assert.deepEqual(l, {carry: GEAR, stash: []});
  const m = leave(l, "crossbow"); assert.ok(!carries(m, "crossbow")); assert.deepEqual(m.stash, ["crossbow"]);
  const back = take(m, "crossbow"); assert.deepEqual([...back.carry].sort(), [...GEAR].sort(), "taking it back (it goes to the end of the carried list)"); assert.deepEqual(back.stash, []);
  assert.equal(take(l, "gun"), l, "not in the locker: nothing changes"); assert.equal(leave(m, "gun").carry.includes("gun"), false);
  assert.equal(leave(l, "nope"), l);
});
test("after a death the locker holds all the gear and you carry none, whatever you had", () => {
  for (const carry of [GEAR, ["gun"], []]) {
    const d = died(newLoadout(carry)); assert.deepEqual(d.carry, []); assert.deepEqual([...d.stash].sort(), [...GEAR].sort());
  }
  const back = GEAR.reduce(take, died(newLoadout())); assert.deepEqual(back.carry.sort(), [...GEAR].sort(), "all of it comes back for free");
});
test("the bolt driver is part of the gear: carried at the start, left and taken like the others", () => {
  assert.ok(GEAR.includes("driver")); assert.ok(carries(newLoadout(), "driver"));
  const m = leave(newLoadout(), "driver"); assert.deepEqual(m.stash, ["driver"]); assert.ok(carries(take(m, "driver"), "driver"));
});
