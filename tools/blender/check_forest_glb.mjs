// The forest's GLB check (docs/BLENDER.md, "8. forest"): do the instanced trees in world/forest.glb stand exactly on the 260 trees of shared/forest.js,
// whose trunks are the colliders? Reads the GLB without three (the EXT_mesh_gpu_instancing accessors) and, given --three <three package folder>, loads it
// with three's GLTFLoader too (node cannot decode images, so they are left out of the copy three parses) and reads the InstancedMeshes' matrices.
// Usage: node tools/blender/check_forest_glb.mjs [world/forest.glb] [--three <node_modules/three>]
import fs from "node:fs";
import path from "node:path";
import {fileURLToPath, pathToFileURL} from "node:url";
import {forestTrees, FOREST} from "../../shared/forest.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const argv = process.argv.slice(2), threeAt = argv.includes("--three") ? argv[argv.indexOf("--three") + 1] : null;
const file = argv.find((a, i) => !a.startsWith("--") && argv[i - 1] !== "--three") || path.join(root, "world/forest.glb");
const buf = fs.readFileSync(file), jl = buf.readUInt32LE(12), J = JSON.parse(buf.subarray(20, 20 + jl).toString());
const bin = buf.subarray(28 + jl, 28 + jl + buf.readUInt32LE(20 + jl));
let bad = 0;
const ok = (c, m) => { console.log((c ? "PASS " : "FAIL ") + m); if (!c) bad++; };
const read = a => {
  const acc = J.accessors[a], bv = J.bufferViews[acc.bufferView], n = {SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4}[acc.type];
  assert(acc.componentType === 5126, "float accessor");
  const f = new Float32Array(bin.buffer, bin.byteOffset + (bv.byteOffset || 0) + (acc.byteOffset || 0), acc.count * n);
  return Array.from({length: acc.count}, (_, i) => Array.from(f.subarray(i * n, i * n + n)));
};
function assert(c, m) { if (!c) throw new Error(m); }
const trees = forestTrees(), [hx, hz] = FOREST.half, z0 = FOREST.cz - hz, z1 = FOREST.cz + hz;
ok(trees.length === 260 && JSON.stringify(trees) === JSON.stringify(JSON.parse(fs.readFileSync(path.join(root, "blender/layout/forest.json"))).trees ?? trees),
   `shared/forest.js gives ${trees.length} trees (the layout file's, if it is there)`);
ok((J.extensionsUsed || []).includes("EXT_mesh_gpu_instancing") && !(J.extensionsRequired || []).includes("EXT_mesh_gpu_instancing"),
   "EXT_mesh_gpu_instancing used (not required: a loader without it still shows one of each)");

// every instance: [holder name, translation, rotation, scale, the trunk's footprint and the crown's lowest point in the mesh]
const inst = [];
for (const n of J.nodes) {
  const ext = n.extensions && n.extensions.EXT_mesh_gpu_instancing; if (!ext) continue;
  const T = read(ext.attributes.TRANSLATION), R = read(ext.attributes.ROTATION), S = read(ext.attributes.SCALE), me = J.meshes[n.mesh];
  let foot = 0, crownMin = Infinity;
  if (/^Trees_/.test(n.name)) {
    const bark = me.primitives.find(p => /^Bark_/.test(J.materials[p.material].name)), crown = me.primitives.find(p => /^Crown_/.test(J.materials[p.material].name));
    for (const [x, y, z] of read(bark.attributes.POSITION)) if (y < 2.2 / 1.12) foot = Math.max(foot, Math.hypot(x, z));   // the trunk below the crowns
    for (const [, y] of read(crown.attributes.POSITION)) crownMin = Math.min(crownMin, y);
    ok(n.mesh !== undefined && !n.translation && !n.rotation && !n.scale, `${n.name}: one mesh (${me.primitives.map(p => J.materials[p.material].name).join(" + ")}), ${T.length} instances, identity holder; ` +
       `trunk base radius in the mesh ${foot.toFixed(3)} m, crown from ${crownMin.toFixed(2)} m`);
  } else ok(true, `${n.name}: ${T.length} instances (passable small things)`);
  T.forEach((t, i) => inst.push({name: n.name, t, r: R[i], s: S[i], foot, crownMin}));
}
const tr = inst.filter(i => /^Trees_/.test(i.name));
const inside = tr.filter(i => i.t[0] > -hx && i.t[0] < hx && i.t[2] > z0 && i.t[2] < z1);
ok(inside.length === 260, `${inside.length} tree instances stand in the playable ground (x ${-hx} .. ${hx}, z ${z0} .. ${z1}); ${tr.length - inside.length} stand past the edge walls`);
let worstPos = 0, worstR = 0, worstOut = 0, lowCrown = Infinity, upright = true, matched = 0;
for (const [x, z, r] of trees) {
  const m = inside.find(i => Math.abs(i.t[0] - x) < 0.005 && Math.abs(i.t[2] - z) < 0.005);
  if (!m) continue;
  matched++;
  worstPos = Math.max(worstPos, Math.hypot(m.t[0] - x, m.t[2] - z), Math.abs(m.t[1]));
  const base = (m.foot / 1.08) * m.s[0];                                      // the mesh's footprint holds the 8 % root flare
  worstR = Math.max(worstR, Math.abs(base - r)); worstOut = Math.max(worstOut, m.foot * m.s[0] - r);
  lowCrown = Math.min(lowCrown, m.crownMin * m.s[1]);
  upright = upright && Math.abs(m.r[0]) < 1e-5 && Math.abs(m.r[2]) < 1e-5 && Math.abs(m.s[0] - m.s[2]) < 1e-6;
}
ok(matched === 260, `${matched} of 260 trees have an instance at their [x, z] (within 5 mm)`);
ok(worstPos < 0.001, `the worst instance is ${(worstPos * 1000).toFixed(2)} mm from its tree (and stands at y 0)`);
ok(worstR < 0.01, `each trunk's base radius (the mesh's widest ring below the crowns / 1.08, times the instance's scale) is the layout's r (worst ${(worstR * 1000).toFixed(1)} mm off)`);
ok(worstOut <= 0.05, `no trunk reaches past its collider by more than 5 cm, root flare included (worst ${(worstOut * 100).toFixed(1)} cm)`);
ok(upright, "every tree only turns about the vertical, and its trunk is round (x scale = z scale)");
ok(lowCrown > 2.2, `every crown starts above 2.2 m (lowest ${lowCrown.toFixed(2)} m)`);

if (threeAt) {
  const THREE = await import(pathToFileURL(path.join(threeAt, "build/three.module.js")).href);
  const {GLTFLoader} = await import(pathToFileURL(path.join(threeAt, "examples/jsm/loaders/GLTFLoader.js")).href);
  const J2 = JSON.parse(JSON.stringify(J));                                  // the same file without its images (node cannot decode them)
  delete J2.images; delete J2.textures; delete J2.samplers;
  for (const m of J2.materials) { if (m.pbrMetallicRoughness) delete m.pbrMetallicRoughness.baseColorTexture; delete m.normalTexture; delete m.emissiveTexture; delete m.occlusionTexture; }
  for (const k of ["extensionsUsed", "extensionsRequired"]) if (J2[k]) J2[k] = J2[k].filter(e => e !== "EXT_texture_webp");
  let js = Buffer.from(JSON.stringify(J2)); js = Buffer.concat([js, Buffer.alloc((4 - js.length % 4) % 4, 0x20)]);
  const head = Buffer.alloc(20); head.write("glTF", 0); head.writeUInt32LE(2, 4); head.writeUInt32LE(12 + 8 + js.length + 8 + bin.length, 8); head.writeUInt32LE(js.length, 12); head.write("JSON", 16);
  const bh = Buffer.alloc(8); bh.writeUInt32LE(bin.length, 0); bh.write("BIN\0", 4);
  const glb = Buffer.concat([head, js, bh, bin]);
  const gltf = await new Promise((res, rej) => new GLTFLoader().parse(glb.buffer.slice(glb.byteOffset, glb.byteOffset + glb.length), "", res, rej));
  const im = []; gltf.scene.updateMatrixWorld(true); gltf.scene.traverse(o => { if (o.isInstancedMesh) im.push(o); });
  const treeIM = im.filter(o => /^Trees_/.test(o.parent && o.parent.name) || /^Trees_/.test(o.name)), m4 = new THREE.Matrix4(), p = new THREE.Vector3();
  const pos = [];
  for (const o of treeIM.filter((o, i, a) => a.findIndex(q => q.parent === o.parent) === i)) for (let i = 0; i < o.count; i++) { o.getMatrixAt(i, m4); p.setFromMatrixPosition(m4.premultiply(o.matrixWorld)); pos.push([p.x, p.y, p.z]); }
  let hit = 0;
  for (const [x, z] of trees) if (pos.some(q => Math.abs(q[0] - x) < 0.001 && Math.abs(q[2] - z) < 0.001 && Math.abs(q[1]) < 0.001)) hit++;
  const uv1 = im.filter(o => o.geometry.attributes.uv1).length, withAo = im.filter(o => o.material.userData && o.material.userData.aomap).length;
  ok(hit === 260, `three r${THREE.REVISION}: ${im.length} InstancedMeshes (${treeIM.length} of trees, ${pos.length} tree instances); ${hit} of 260 trees found at their [x, 0, z] (1 mm)`);
  ok(uv1 === withAo && withAo === treeIM.length, `three: the ${withAo} tree InstancedMeshes carry userData.aomap and a uv1 (the page's applyLightmaps finds them: isMesh ${im.every(o => o.isMesh)})`);
}
console.log(bad ? `FAIL: ${bad} check(s) failed` : "RESULT PASS");
process.exit(bad ? 1 : 0);
