// The hunting crossbow (GBI-8): the first lethal weapon of Going back in. No graphics here. Its own ammo rule, unlike the ray's rounds:
// bolts, one per shot, at most MAX_BOLTS carried, PACK_BOLTS from each ammo pack you pick up while you carry it, and a slow reload (RELOAD_S) between shots.
// A bolt that hits a monster kills it (the monster is gone for good); the ray only banishes. A shot makes half the noise of the ray's.
import {rayMonster} from "./monsters.js";
export const MAX_BOLTS = 6, START_BOLTS = 4, PACK_BOLTS = 2, RELOAD_S = 1.8, SHOT_NOISE_S = 0.25;
export const newBow = (bolts = 0) => ({bolts: Math.max(0, Math.min(MAX_BOLTS, bolts)), cool: 0});
export const addBolts = (bow, n) => ({...bow, bolts: Math.max(0, Math.min(MAX_BOLTS, bow.bolts + n))});
export const tick = (bow, dt) => bow.cool > 0 ? {...bow, cool: Math.max(0, bow.cool - dt)} : bow;
// what a shot does to the bow: {ok: true, bow} (one bolt used, reloading), or {ok: false, why: "reloading" | "empty"}
export function shoot(bow) {
  if (bow.cool > 0) return {ok: false, why: "reloading"};
  if (bow.bolts <= 0) return {ok: false, why: "empty"};
  return {ok: true, bow: {bolts: bow.bolts - 1, cool: RELOAD_S}};
}
// the monster a bolt from o along d (unit) kills: the nearest one on o's floor the ray hits, whatever its state (a banished or glitching one included), or null
export const killShot = (W, monsters, o, d) => { const hit = rayMonster(W, monsters, o, d); return hit ? hit.m : null; };
