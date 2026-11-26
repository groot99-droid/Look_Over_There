// Writes the tiny model and pictures tools/art_test.mjs loads in place of a real Blender build: five upright quads, one per material the page treats specially
// (docs/BLENDER.md, R1): a baked one with a day and a night light set, an AO-only one, and the three the clock toggles. Run it again only if the fixture should change.
// Usage: node tools/fixtures/make_art_fixture.mjs
import fs from "node:fs";
import zlib from "node:zlib";
const dir = new URL("./", import.meta.url);
function png(w, h, rgb) {                                         // a flat-colour RGB picture
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({length: w}, () => rgb).flat())]), raw = Buffer.concat(Array.from({length: h}, () => row));
  const chunk = (type, data) => { const len = Buffer.alloc(4); len.writeUInt32BE(data.length); const body = Buffer.concat([Buffer.from(type), data]), crc = Buffer.alloc(4); crc.writeUInt32BE(zlib.crc32(body) >>> 0); return Buffer.concat([len, body, crc]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}
for (const [name, w, h, rgb] of [["lm_day", 4, 4, [230, 220, 200]], ["lm_night", 4, 4, [40, 50, 90]], ["ao", 4, 4, [128, 128, 128]], ["sky_day", 8, 4, [150, 190, 240]], ["sky_night", 8, 4, [10, 12, 30]]])
  fs.writeFileSync(new URL(`${name}.png`, dir), png(w, h, rgb));

const MATS = [
  {name: "Wall_Baked", pbrMetallicRoughness: {baseColorFactor: [0.8, 0.8, 0.8, 1]}, extras: {lightmap: "fixtures/lm_day.png", lightmap_intensity: 2, lightmap_night: "fixtures/lm_night.png", lightmap_night_intensity: 1.5}},
  {name: "Ground_AO", pbrMetallicRoughness: {baseColorFactor: [0.5, 0.6, 0.5, 1]}, extras: {aomap: "fixtures/ao.png", aomap_intensity: 0.8}},
  {name: "Lamp_Emit", emissiveFactor: [1, 0.8, 0.5], extensions: {KHR_materials_emissive_strength: {emissiveStrength: 5}}},
  {name: "Window_Lit", emissiveFactor: [1, 0.9, 0.6], extensions: {KHR_materials_emissive_strength: {emissiveStrength: 3}}},
  {name: "Emergency_Emit", emissiveFactor: [1, 0.2, 0.2], extensions: {KHR_materials_emissive_strength: {emissiveStrength: 4}}},
];
const f32 = a => Buffer.from(new Float32Array(a).buffer), parts = [], views = [], accessors = [];
const add = (buf, acc, target) => { const off = parts.reduce((n, b) => n + b.length, 0); parts.push(buf); views.push({buffer: 0, byteOffset: off, byteLength: buf.length, target}); accessors.push({bufferView: views.length - 1, ...acc}); return accessors.length - 1; };
const idx = add(Buffer.from(new Uint16Array([0, 1, 2, 0, 2, 3]).buffer), {componentType: 5123, count: 6, type: "SCALAR"}, 34963);
const nor = add(f32([0, 0, 1, 0, 0, 1, 0, 0, 1, 0, 0, 1]), {componentType: 5126, count: 4, type: "VEC3"}, 34962);
const uv = add(f32([0, 1, 1, 1, 1, 0, 0, 0]), {componentType: 5126, count: 4, type: "VEC2"}, 34962);
const meshes = [], nodes = [];
MATS.forEach((m, i) => {                                           // a 1 m quad, 3 m up (over the heads of whatever the scene keeps), facing south
  const x = i * 1.2 - 2.4, pos = add(f32([x, 3, -1, x + 1, 3, -1, x + 1, 4, -1, x, 4, -1]), {componentType: 5126, count: 4, type: "VEC3", min: [x, 3, -1], max: [x + 1, 4, -1]}, 34962);
  meshes.push({name: m.name, primitives: [{attributes: {POSITION: pos, NORMAL: nor, TEXCOORD_0: uv, TEXCOORD_1: uv}, indices: idx, material: i}]}); nodes.push({name: m.name, mesh: i});
});
const bin = Buffer.concat(parts), gltf = {asset: {version: "2.0", generator: "make_art_fixture.mjs"}, extensionsUsed: ["KHR_materials_emissive_strength"], scene: 0, scenes: [{nodes: nodes.map((_, i) => i)}], nodes, meshes, materials: MATS,
  accessors, bufferViews: views, buffers: [{byteLength: bin.length}]};
const pad = (b, fill) => Buffer.concat([b, Buffer.alloc((4 - b.length % 4) % 4, fill)]), json = pad(Buffer.from(JSON.stringify(gltf)), 0x20), body = pad(bin, 0);
const head = Buffer.alloc(12); head.writeUInt32LE(0x46546C67, 0); head.writeUInt32LE(2, 4); head.writeUInt32LE(12 + 8 + json.length + 8 + body.length, 8);
const ch = (b, type) => { const h = Buffer.alloc(8); h.writeUInt32LE(b.length, 0); h.writeUInt32LE(type, 4); return Buffer.concat([h, b]); };
fs.writeFileSync(new URL("art_room.glb", dir), Buffer.concat([head, ch(json, 0x4E4F534A), ch(body, 0x004E4942)]));
console.log("wrote art_room.glb and five pictures");
