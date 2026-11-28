// The meadow's GLB check (docs/BLENDER.md, "9. meadow"): do the instanced trees in world/meadow.glb stand exactly on the 120 trees of shared/forest.js,
// whose trunks are the colliders, and the instanced flowers exactly on its 420 flowers, each in its own colour? Reads the GLB's EXT_mesh_gpu_instancing
// accessors directly (no three), so it checks the packed file the page loads, after tools/webp_glb.py.
// Usage: node tools/blender/check_meadow_glb.mjs [world/meadow.glb]
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath} from "node:url";
import {meadowTrees, meadowFlowers, MEADOW} from "../../shared/forest.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const file = process.argv.slice(2).find(a => !a.startsWith("--")) || path.join(root, "world/meadow.glb");
const buf = fs.readFileSync(file), jl = buf.readUInt32LE(12), J = JSON.parse(buf.subarray(20, 20 + jl).toString());
const bin = buf.subarray(28 + jl, 28 + jl + buf.readUInt32LE(20 + jl));
let bad = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) bad++; };
function assert(c, m) { if (!c) throw new Error(m); }
const read = a => {
  const acc = J.accessors[a], bv = J.bufferViews[acc.bufferView], n = {SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4}[acc.type];
  assert(acc.componentType === 5126, "float accessor");
  const f = new Float32Array(bin.buffer.slice(bin.byteOffset + (bv.byteOffset || 0) + (acc.byteOffset || 0), bin.byteOffset + (bv.byteOffset || 0) + (acc.byteOffset || 0) + acc.count * n * 4));
  return Array.from({length: acc.count}, (_, i) => Array.from(f.subarray(i * n, i * n + n)));
};
const trees = meadowTrees(), flowers = meadowFlowers(), [hx, hz] = MEADOW.half, z0 = MEADOW.cz - hz, z1 = MEADOW.cz + hz;
const lay = (() => { try { return JSON.parse(fs.readFileSync(path.join(root, "blender/layout/meadow.json"))); } catch { return null; } })();
ok(trees.length === 120 && flowers.length === 420 && (!lay || (JSON.stringify(lay.trees) === JSON.stringify(trees) && JSON.stringify(lay.flowers) === JSON.stringify(flowers))),
   `shared/forest.js gives ${trees.length} trees and ${flowers.length} flowers` + (lay ? " (the same as blender/layout/meadow.json's)" : ""));
ok((J.extensionsUsed || []).includes("EXT_mesh_gpu_instancing") && !(J.extensionsRequired || []).includes("EXT_mesh_gpu_instancing"),
   "EXT_mesh_gpu_instancing used (not required: a loader without it still shows one of each)");
ok((J.extensionsRequired || []).includes("EXT_texture_webp") && (J.images || []).every(i => i.mimeType === "image/webp"), `${(J.images || []).length} images, all WebP (EXT_texture_webp)`);

const inst = [];
for (const n of J.nodes) {
  const ext = n.extensions && n.extensions.EXT_mesh_gpu_instancing; if (!ext) continue;
  const T = read(ext.attributes.TRANSLATION), R = read(ext.attributes.ROTATION), S = read(ext.attributes.SCALE), me = J.meshes[n.mesh];
  let foot = 0, crownMin = Infinity, top = 0;
  if (/^Trees_/.test(n.name)) {
    const bark = me.primitives.find(p => /^Bark_/.test(J.materials[p.material].name)), crown = me.primitives.find(p => /^Crown_/.test(J.materials[p.material].name));
    for (const [x, y, z] of read(bark.attributes.POSITION)) if (y < 2.2 / 1.12) foot = Math.max(foot, Math.hypot(x, z));
    for (const [, y] of read(crown.attributes.POSITION)) crownMin = Math.min(crownMin, y);
    ok(!n.translation && !n.rotation && !n.scale, `${n.name}: one mesh (${me.primitives.map(p => J.materials[p.material].name).join(" + ")}), ${T.length} instances, identity holder; ` +
       `trunk base radius in the mesh ${foot.toFixed(3)} m, crown from ${crownMin.toFixed(2)} m`);
  } else {
    for (const p of me.primitives) for (const [, y] of read(p.attributes.POSITION)) top = Math.max(top, y);
    ok(!n.translation && !n.rotation && !n.scale, `${n.name}: ${T.length} instances, identity holder, ${top.toFixed(2)} m tall in the mesh (passable small things)`);
  }
  T.forEach((t, i) => inst.push({name: n.name, t, r: R[i], s: S[i], foot, crownMin, top}));
}

// the trees
const tr = inst.filter(i => /^Trees_/.test(i.name));
const inside = tr.filter(i => i.t[0] > -hx && i.t[0] < hx && i.t[2] > z0 && i.t[2] < z1);
ok(inside.length === 120, `${inside.length} tree instances stand in the playable ground (x ${-hx} .. ${hx}, z ${z0} .. ${z1}); ${tr.length - inside.length} stand past the edge walls`);
let worstPos = 0, worstR = 0, worstOut = 0, lowCrown = Infinity, upright = true, matched = 0;
for (const [x, z, r] of trees) {
  const m = inside.filter(i => Math.abs(i.t[0] - x) < 0.005 && Math.abs(i.t[2] - z) < 0.005);
  if (m.length !== 1) continue;
  matched++;
  const [q] = m;
  worstPos = Math.max(worstPos, Math.hypot(q.t[0] - x, q.t[2] - z), Math.abs(q.t[1]));
  worstR = Math.max(worstR, Math.abs((q.foot / 1.08) * q.s[0] - r)); worstOut = Math.max(worstOut, q.foot * q.s[0] - r);
  lowCrown = Math.min(lowCrown, q.crownMin * q.s[1]);
  upright = upright && Math.abs(q.r[0]) < 1e-5 && Math.abs(q.r[2]) < 1e-5 && Math.abs(q.s[0] - q.s[2]) < 1e-6;
}
ok(matched === 120, `${matched} of 120 trees have exactly one instance at their [x, z] (within 5 mm)`);
ok(worstPos < 0.001, `the worst tree instance is ${(worstPos * 1000).toFixed(2)} mm from its tree (and stands at y 0)`);
ok(worstR < 0.01, `each trunk's base radius (the mesh's widest ring below the crowns / 1.08, times the instance's scale) is the layout's r (worst ${(worstR * 1000).toFixed(1)} mm off)`);
ok(worstOut <= 0.05, `no trunk reaches past its collider by more than 5 cm, root flare included (worst ${(worstOut * 100).toFixed(1)} cm)`);
ok(upright, "every tree only turns about the vertical, and its trunk is round (x scale = z scale)");
ok(lowCrown > 2.2, `every crown starts above 2.2 m (lowest ${lowCrown.toFixed(2)} m)`);
const far = tr.filter(i => !inside.includes(i));
ok(far.every(i => i.t[0] <= -hx - 1.5 || i.t[0] >= hx + 1.5 || i.t[2] <= z0 - 1.5 || i.t[2] >= z1 + 1.5), `the ${far.length} trees past the edge walls all stand at least 1.5 m outside them (out of reach)`);

// the flowers
const fl = inst.filter(i => /^Flowers_/.test(i.name));
ok(fl.length === 420, `${fl.length} flower instances (${[0, 1, 2, 3, 4].map(c => fl.filter(i => i.name === `Flowers_${c}`).length).join(", ")} in Flowers_0 .. Flowers_4)`);
let fm = 0, wrong = 0, fworst = 0, ftall = 0;
const used = new Set();
for (const [x, z, c] of flowers) {
  const m = fl.filter(i => Math.abs(i.t[0] - x) < 0.005 && Math.abs(i.t[2] - z) < 0.005);
  if (m.length !== 1) continue;
  const [q] = m;
  if (q.name !== `Flowers_${c}`) { wrong++; continue; }
  fm++; used.add(q);
  fworst = Math.max(fworst, Math.hypot(q.t[0] - x, q.t[2] - z), Math.abs(q.t[1]));
  ftall = Math.max(ftall, q.top * q.s[1]);
}
ok(fm === 420 && wrong === 0 && used.size === 420, `${fm} of 420 flowers have exactly one instance at their [x, z] (within 5 mm), in the node of their colour (${wrong} in another colour's)`);
ok(fworst < 0.001, `the worst flower instance is ${(fworst * 1000).toFixed(2)} mm from its spot (and stands at y 0)`);
ok(ftall < 0.9, `the flowers stand at most ${ftall.toFixed(2)} m tall: small and passable (not solid: no collider, as the layout has none)`);

// what must not be in the file
const names = [...J.nodes.map(n => n.name || ""), ...J.meshes.map(m => m.name || ""), ...J.materials.map(m => m.name || "")];
ok(!names.some(n => /standin|shed|house|cottage|pagedrawn|Mesh_0|geometry_0/i.test(n)), "no node, mesh or material of the owner's shed or house, and no stand-in (the page draws them)");
const mats = J.materials.filter(m => m.extras && m.extras.aomap);
ok(mats.length >= 7 && !J.materials.some(m => m.extras && m.extras.lightmap), `${mats.length} materials carry aomap (${mats.map(m => `${m.name} ${m.extras.aomap} x${m.extras.aomap_intensity}`).join("; ")}); none carries lightmap`);
console.log(bad ? `FAIL: ${bad} check(s) failed` : "RESULT PASS");
process.exit(bad ? 1 : 0);
