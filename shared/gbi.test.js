import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {wavePlan, startWave} from "./gbi.js";
import {REGISTRY} from "./registry.js";
import {worldFromDoc} from "./world.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const monCfg = JSON.parse(fs.readFileSync(path.join(ROOT, "world/monsters.json"), "utf8"));
// the shared world over a chamber's file, as the page builds it (colliders and doors, no models in node); the chamber reuses a floor's model, so it takes that floor's `art`
const worldOf = id => { const ch = REGISTRY.chamber(id); return worldFromDoc(JSON.parse(fs.readFileSync(path.join(ROOT, `world/${id}.json`), "utf8")), id, {floor: ch.floorY, art: ch.floor}); };

test("the wave plan places as many monsters as the manifest says, every one of the chamber's kind", () => {
  for (const id of REGISTRY.chambers) {
    const ch = REGISTRY.chamber(id), W = worldOf(id);
    const plan = wavePlan(W, monCfg, ch);
    assert.equal(plan.length, ch.wave.monsters, id);
    assert.ok(plan.every(p => p.cfg.name === ch.wave.kind && Number.isFinite(p.x) && Number.isFinite(p.z)), id);
  }
});
test("the plan keeps away from the player and is the same every time", () => {
  const ch = REGISTRY.chamber("gbi_L3_1"), W = worldOf("gbi_L3_1");
  const a = wavePlan(W, monCfg, ch, [[0, 0]]), b = wavePlan(W, monCfg, ch, [[0, 0]]);
  assert.deepEqual(a.map(p => [p.x, p.z]), b.map(p => [p.x, p.z]));
  assert.ok(a.every(p => Math.hypot(p.x, p.z) >= 16));
});
test("an unknown monster kind is an error, not an empty wave", () => {
  assert.throws(() => wavePlan({nav: new Uint8Array(0)}, monCfg, {id: "x", wave: {kind: "nope", monsters: 1}}), /no monster kind nope/);
});
test("a wave starts with the chamber's number and size", () => {
  assert.deepEqual(startWave(REGISTRY.chamber("gbi_L4_4"), 12), {chamber: "gbi_L4_4", no: 4, monsters: 3, t0: 12});
});
test("the sealed L4 chamber puts no wave in the parking lot", () => {
  const ch = REGISTRY.chamber("gbi_L4_4"), W = worldOf("gbi_L4_4");
  assert.ok(wavePlan(W, monCfg, ch).every(p => p.z <= 27.6));
});
