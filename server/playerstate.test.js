import test from "node:test";
import assert from "node:assert/strict";
import {newPS, newStats, gaveRevive, shotHit, onFloor, statsOf, hit, tick, lift, gotLocker, gotPack, gotBeacon, shoot, throwBeacon, toggleCloak, shortCircuit, view, changed, isDown, isImmune, canTakePack, canTakeBeacon, DOWNED_S, IMMUNE_S, THROW_GAP_S} from "./playerstate.js";

test("three hits down a player; the grace second and the gap protect; being down or immune takes no more", () => {
  const ps = newPS(); assert.ok(hit(ps, 35, 10)); assert.equal(view(ps).hp, 65); assert.ok(!hit(ps, 35, 10.5), "grace");
  assert.ok(hit(ps, 35, 11.2)); assert.ok(hit(ps, 35, 12.5)); assert.ok(isDown(ps)); assert.ok(!hit(ps, 35, 20), "already down");
  const imm = newPS(); imm.immUntil = 50; assert.ok(isImmune(imm, 49) && !hit(imm, 35, 49), "immune"); assert.ok(hit(imm, 35, 51));
});
test("regeneration after 10 s; a downed player gets up alone after DOWNED_S (20 s) with 100 HP and a few seconds of safety", () => {
  const ps = newPS(); hit(ps, 35, 0); tick(ps, 1, 5); assert.equal(view(ps).hp, 65); tick(ps, 1, 11); assert.equal(view(ps).hp, 66);
  const d = newPS(); hit(d, 50, 0); hit(d, 50, 2); assert.ok(isDown(d), "two hits of 50");
  assert.equal(tick(d, 1, 2 + DOWNED_S - 1), null); assert.equal(tick(d, 1, 2 + DOWNED_S), "respawn"); assert.equal(view(d).hp, 100); assert.ok(isImmune(d, 2 + DOWNED_S + IMMUNE_S - 0.1));
});
test("a teammate lifts a downed player to 50 HP; an upright one cannot be lifted", () => {
  const ps = newPS(); assert.ok(!lift(ps, 5)); hit(ps, 50, 0); hit(ps, 50, 2); hit(ps, 50, 4); assert.ok(lift(ps, 10)); assert.equal(view(ps).hp, 50); assert.ok(isImmune(ps, 12));
});
test("the locker gives the gun with 3 rounds and a cloak; packs add 3 to a cap of 9; shots cost a round and need their gap; no rounds, no shot", () => {
  const ps = newPS(); assert.ok(!shoot(ps, 1), "no gun"); gotLocker(ps); assert.deepEqual([ps.gun, ps.rounds, !!ps.cloak], [true, 3, true]);
  assert.ok(shoot(ps, 1)); assert.ok(!shoot(ps, 1.2), "the gap"); assert.ok(shoot(ps, 1.7)); assert.equal(ps.rounds, 1);
  gotPack(ps); gotPack(ps); gotPack(ps); gotPack(ps); assert.equal(ps.rounds, 9); assert.ok(!canTakePack(ps));
  const empty = newPS(); gotLocker(empty); empty.rounds = 0; assert.ok(!shoot(empty, 5), "out of rounds");
});
test("beacons: two at most, a throw needs one and a second between throws", () => {
  const ps = newPS(); assert.ok(!throwBeacon(ps, 1)); gotBeacon(ps); gotBeacon(ps); gotBeacon(ps); assert.equal(ps.beacons, 2); assert.ok(!canTakeBeacon(ps));
  assert.ok(throwBeacon(ps, 10)); assert.ok(!throwBeacon(ps, 10 + THROW_GAP_S - 0.1), "too soon"); assert.ok(throwBeacon(ps, 10 + THROW_GAP_S)); assert.equal(ps.beacons, 0);
});
test("the cloak: needs the locker, toggles, drains on the server's clock and switches itself off when flat; going down switches it off", () => {
  const ps = newPS(); assert.ok(!toggleCloak(ps)); gotLocker(ps); assert.ok(toggleCloak(ps)); assert.equal(view(ps).cloak.on, true);
  for (let t = 0; t < 16; t += 0.5) tick(ps, 0.5, 100 + t); assert.equal(view(ps).cloak.on, false); assert.equal(view(ps).cloak.b, 0);
  assert.ok(!toggleCloak(ps), "too flat to switch on");
  const d = newPS(); gotLocker(d); toggleCloak(d); hit(d, 50, 0); hit(d, 50, 2); hit(d, 50, 4); assert.equal(view(d).cloak.on, false);
});
test("changed() says so once per change", () => {
  const ps = newPS(); assert.ok(changed(ps)); assert.ok(!changed(ps)); gotLocker(ps); assert.ok(changed(ps)); assert.ok(!changed(ps));
});

test("short circuit: needs a working cloak and a living player; kills the cloak for 5 minutes and shows in the view", () => {
  const ps = newPS(); assert.ok(!shortCircuit(ps), "no cloak yet"); gotLocker(ps); assert.ok(toggleCloak(ps) && ps.cloak.on);
  assert.ok(shortCircuit(ps)); assert.deepEqual([ps.cloak.on, ps.cloak.b, view(ps).cloak.x], [false, 0, 300]); assert.ok(!shortCircuit(ps), "already dead"); assert.ok(!toggleCloak(ps), "cannot be switched on");
  tick(ps, 100, 0); assert.equal(view(ps).cloak.x, 200, "the broken seconds count down on the server's clock");
  const d = newPS(); gotLocker(d); hit(d, 50, 0); hit(d, 50, 2); assert.ok(isDown(d) && !shortCircuit(d), "a downed player cannot");
});

test("counters: a down is counted; a down nobody lifted becomes a death, a lifted one does not", () => {
  const ps = newPS(); assert.deepEqual(ps.stats, newStats());
  hit(ps, 50, 0); hit(ps, 50, 2); assert.ok(isDown(ps));
  assert.equal(ps.stats.downs, 1); assert.equal(ps.stats.deaths, 0, "not a death yet");
  assert.equal(tick(ps, 1, DOWNED_S + 2), "respawn"); assert.equal(ps.stats.deaths, 1, "the time ran out");
  const b = newPS(); hit(b, 50, 0); hit(b, 50, 2); lift(b, 10);
  assert.equal(tick(b, 1, 10 + DOWNED_S + 5), null); assert.deepEqual([b.stats.downs, b.stats.deaths], [1, 0], "lifted: a down, not a death");
  hit(b, 50, 100); hit(b, 50, 102); assert.equal(b.stats.downs, 2, "a second down counts again");
});
test("counters: only hits that landed count as downs; a hit on someone down or immune adds nothing", () => {
  const ps = newPS(); hit(ps, 35, 0); assert.equal(ps.stats.downs, 0);
  hit(ps, 35, 0.5); hit(ps, 35, 1.5); hit(ps, 35, 3); assert.equal(ps.stats.downs, 1); hit(ps, 35, 9); assert.equal(ps.stats.downs, 1, "already down");
});
test("counters: shots, beacons, revives given, hits", () => {
  const ps = newPS(); gotLocker(ps); gotBeacon(ps);
  assert.ok(shoot(ps, 10)); assert.ok(!shoot(ps, 10.01), "too fast: refused shots do not count"); assert.ok(shoot(ps, 12)); assert.equal(ps.stats.shots, 2);
  shotHit(ps); assert.equal(ps.stats.hits, 1);
  assert.ok(throwBeacon(ps, 20)); assert.ok(!throwBeacon(ps, 20.1)); assert.equal(ps.stats.beacons, 1);
  const empty = newPS(); assert.ok(!shoot(empty, 5)); assert.ok(!throwBeacon(empty, 5)); assert.equal(empty.stats.shots + empty.stats.beacons, 0, "no gun, no beacon: nothing counted");
  gaveRevive(ps); gaveRevive(ps); assert.equal(ps.stats.revives, 2);
});
test("counters: time on each floor adds up per scene, and a snapshot does not change afterwards", () => {
  const ps = newPS(); onFloor(ps, "B1", 0.5); onFloor(ps, "B1", 0.25); onFloor(ps, "L1", 1); onFloor(ps, null, 5);
  assert.deepEqual(ps.stats.floorMs, {B1: 750, L1: 1000});
  const snap = statsOf(ps); onFloor(ps, "B1", 1); assert.equal(snap.floorMs.B1, 750); assert.equal(ps.stats.floorMs.B1, 1750);
});

// ---- Going back in in a room (session 16): the loadout, the crossbow and the consumables are kept here
import {newGbiPS, gbiGear, gbiSetE, gbiSlot, gbiUse, shootBow, gbiDied} from "./playerstate.js";
import {GUN_ROUNDS} from "../shared/loot.js";
import {START_BOLTS, PACK_BOLTS, RELOAD_S} from "../shared/crossbow.js";
import {START as KIT_START} from "../shared/consumables.js";
test("Going back in: you start with all your gear; the loadout decides the ray and the cloak; the Original's state has none of it", () => {
  const ps = newGbiPS(), v = view(ps);
  assert.deepEqual(v.carry, ["gun", "cloak", "crossbow"]); assert.equal(v.bolts, START_BOLTS); assert.deepEqual(v.kit, {n: KIT_START, e: "mine"}); assert.equal(v.rounds, GUN_ROUNDS); assert.ok(v.gun && v.cloak);
  assert.ok(gbiGear(ps, "leave", "gun")); assert.equal(ps.gun, false); assert.ok(!shoot(ps, 10), "the ray is in the locker"); assert.equal(ps.rounds, GUN_ROUNDS, "its rounds stay on you");
  assert.ok(!gbiGear(ps, "leave", "gun"), "already there"); assert.ok(!gbiGear(ps, "take", "sword")); assert.ok(!gbiGear(ps, "grab", "gun"));
  assert.ok(gbiGear(ps, "leave", "cloak")); assert.equal(ps.cloak, null); assert.ok(gbiGear(ps, "take", "cloak")); assert.ok(ps.cloak);
  assert.ok(gbiGear(ps, "take", "gun")); assert.ok(shoot(ps, 10));
  const o = newPS(); assert.equal(view(o).carry, undefined); assert.equal(view(o).kit, undefined); assert.ok(!gbiGear(o, "take", "gun")); assert.ok(!shootBow(o)); assert.equal(gbiUse(o, 0), null); assert.ok(!gbiSetE(o, "wire"));
  gotPack(o); assert.equal(o.gbi, undefined, "an Original pack is rounds only");
});
test("Going back in: a bolt costs one and the bow must reload; consumables are counted; a death puts the gear in the locker and takes the ammunition", () => {
  const ps = newGbiPS();
  assert.ok(shootBow(ps)); assert.equal(ps.gbi.bow.bolts, START_BOLTS - 1); assert.ok(!shootBow(ps), "reloading"); assert.equal(ps.stats.shots, 1);
  tick(ps, RELOAD_S, 5); assert.ok(shootBow(ps)); gbiGear(ps, "leave", "crossbow"); tick(ps, RELOAD_S, 8); assert.ok(!shootBow(ps), "not in hand");
  gotPack(ps); assert.equal(ps.gbi.bow.bolts, START_BOLTS - 2, "no bolts for a crossbow left in the locker"); assert.equal(ps.gbi.kit.n.flash, Math.min(3, KIT_START.flash + 1));
  gbiGear(ps, "take", "crossbow"); gotPack(ps); assert.equal(ps.gbi.bow.bolts, START_BOLTS - 2 + PACK_BOLTS);
  assert.equal(gbiSlot(ps, 1), "mine"); assert.equal(gbiSlot(ps, 2), null); assert.ok(gbiSetE(ps, "wire")); assert.ok(!gbiSetE(ps, "wire")); assert.ok(!gbiSetE(ps, "flash")); assert.equal(gbiUse(ps, 1), "wire"); assert.equal(gbiUse(ps, 1), null, "one tripwire to start with");
  assert.equal(gbiUse(ps, 0), "flash");
  hit(ps, 100, 20); assert.ok(isDown(ps)); assert.ok(!gbiGear(ps, "leave", "gun")); assert.equal(gbiUse(ps, 0), null); assert.ok(!shootBow(ps));
  assert.equal(tick(ps, 0.05, 20 + DOWNED_S), "respawn"); gbiDied(ps);
  const v = view(ps); assert.deepEqual(v.carry, []); assert.equal(v.gun, false); assert.equal(v.cloak, null); assert.equal(v.rounds, 0); assert.equal(v.bolts, 0); assert.deepEqual(v.kit.n, {flash: 0, mine: 0, wire: 0}); assert.equal(v.kit.e, "wire", "the E slot's choice is kept");
  for (const g of ["gun", "cloak", "crossbow"]) assert.ok(gbiGear(ps, "take", g)); assert.ok(ps.gun && ps.cloak); assert.equal(ps.rounds, 0);
});
