import test from "node:test";
import assert from "node:assert/strict";
import {newKit, setE, useSlot, addPack, lost, placeTrap, springs, slotKind, MAX, START, MINE_ARM_S, WIRE_ARM_S, MINE_R, WIRE_R, WIRE_BLAST_R} from "./consumables.js";

const mon = (x, z) => ({pos: {x, z}});
test("Q is the flash-vial, E is the mine until the locker changes it, and each use costs one", () => {
  let k = newKit(); assert.deepEqual([slotKind(k, 0), slotKind(k, 1), slotKind(k, 2)], ["flash", "mine", null]);
  const q = useSlot(k, 0); assert.ok(q.ok); assert.equal(q.kind, "flash"); assert.equal(q.kit.n.flash, START.flash - 1); assert.equal(k.n.flash, START.flash, "the input is not changed");
  k = setE(k, "wire"); assert.equal(useSlot(k, 1).kind, "wire"); assert.equal(setE(k, "flash").e, "wire", "flash is not an E item");
  assert.deepEqual(useSlot(k, 2), {ok: false, why: "no slot"});
});
test("an empty slot does nothing", () => {
  let k = newKit(); for (let i = 0; i < START.mine; i++) k = useSlot(k, 1).kit;
  assert.deepEqual(useSlot(k, 1), {ok: false, why: "empty", kind: "mine"});
});
test("a pack adds one flash-vial and one of the E item, capped; a death takes them all", () => {
  let k = addPack(newKit()); assert.equal(k.n.flash, START.flash + 1); assert.equal(k.n.mine, START.mine + 1);
  for (let i = 0; i < 5; i++) k = addPack(k); assert.equal(k.n.flash, MAX.flash); assert.equal(k.n.mine, MAX.mine); assert.equal(k.n.wire, START.wire, "the item not in the slot is untouched");
  const l = lost(k); assert.deepEqual(l.n, {flash: 0, mine: 0, wire: 0}); assert.equal(l.e, k.e);
});
test("a mine arms after its delay and kills only the monster that steps on it", () => {
  const t = placeTrap("mine", 0, 0, 10), a = mon(0.5, 0), b = mon(0.9, 0), far = mon(5, 0);
  assert.equal(springs(t, 10 + MINE_ARM_S - 0.1, [a]), null, "not armed yet");
  const r = springs(t, 10 + MINE_ARM_S, [far, b, a]); assert.deepEqual(r.kills, [a]); assert.equal(r.loud, false);
  assert.equal(springs(t, 20, [far, mon(MINE_R + 0.1, 0)]), null, "just out of reach");
  assert.equal(springs({...t, done: true}, 20, [a]), null, "spent");
});
test("a tripwire arms fast, kills everything in its blast, and is loud", () => {
  const t = placeTrap("wire", 0, 0, 0), trip = mon(WIRE_R - 0.1, 0), blast = mon(0, WIRE_BLAST_R - 0.1), safe = mon(0, WIRE_BLAST_R + 1);
  assert.equal(springs(t, WIRE_ARM_S - 0.1, [trip]), null);
  const r = springs(t, WIRE_ARM_S, [trip, blast, safe]); assert.deepEqual(r.kills, [trip, blast]); assert.equal(r.loud, true);
  assert.equal(springs(t, 5, [mon(WIRE_R + 0.5, 0)]), null, "inside the blast but outside the trip: nothing sets it off");
});
