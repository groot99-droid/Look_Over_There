"""The last step of the Morpheus room (plain Python with Pillow, no Blender): the lightmap PNGs to world/lightmaps/*.webp (q90), and the
exported GLB to world/rdwe_god_morpheus.glb with every texture as WebP (EXT_texture_webp), the geometry bytes left exactly as they were.

    python tools/blender/pack_rdwe_morpheus.py [--furniture-q 75] [--q 85]

Why not tools/webp_glb.py alone: the reduced copies in blender/models/rdwe_morpheus/ already carry WebP textures, which the exporter passes
through and webp_glb.py refuses. Here each furniture or prop texture is re-encoded from the copies stage's own baked JPEG (q90, in the work
folder) rather than from the WebP (no second lossy pass), at --furniture-q; the room's generated PNG textures at --q.
"""
import glob
import hashlib
import io
import json
import os
import struct
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
SCENE = "rdwe_god_morpheus"
WORK = ROOT / f"blender/work/farway_{SCENE}"
args = sys.argv[1:]


def arg(name, default):
    return type(default)(args[args.index(name) + 1]) if name in args else default


FQ, Q = arg("--furniture-q", 75), arg("--q", 85)

for p in sorted(glob.glob(str(WORK / f"{SCENE}_[0-9].png"))):
    out = ROOT / "world/lightmaps" / (Path(p).stem + ".webp")
    Image.open(p).convert("RGB").save(out, "WEBP", quality=90, method=6)
    print(out.relative_to(ROOT), out.stat().st_size)

src = WORK / f"{SCENE}_raw.glb"
b = src.read_bytes()
assert b[:4] == b"glTF"
jlen = struct.unpack("<I", b[12:16])[0]
j = json.loads(b[20:20 + jlen])
blen = struct.unpack("<I", b[20 + jlen:24 + jlen])[0]
binc = b[28 + jlen:28 + jlen + blen]
views = j["bufferViews"]
data = [binc[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]] for v in views]
img_views = {im["bufferView"] for im in j["images"]}
geo_before = hashlib.sha256(b"".join(d for i, d in enumerate(data) if i not in img_views)).hexdigest()
for im in j["images"]:
    i = im["bufferView"]
    jpg = WORK / f"{im.get('name', '')}.jpg"
    if jpg.exists():
        img, q, how = Image.open(jpg), FQ, "from the baked JPEG"
    else:
        img, q, how = Image.open(io.BytesIO(data[i])), Q, "from the export"
    o = io.BytesIO()
    img.convert("RGB").save(o, "WEBP", quality=q, method=6)
    print(f"  {im.get('name')}: {img.size[0]}px {how}, q{q}: {len(data[i])} -> {o.tell()}")
    data[i] = o.getvalue()
    im["mimeType"] = "image/webp"
for t in j["textures"]:
    if "source" in t:
        t.setdefault("extensions", {})["EXT_texture_webp"] = {"source": t.pop("source")}
for k in ("extensionsUsed", "extensionsRequired"):
    j[k] = sorted(set(j.get(k, [])) | {"EXT_texture_webp"})
blob, off = bytearray(), 0
for v, d in zip(views, data):
    while len(blob) % 4:
        blob += b"\0"
    v["byteOffset"] = len(blob)
    v["byteLength"] = len(d)
    blob += d
while len(blob) % 4:
    blob += b"\0"
j["buffers"][0]["byteLength"] = len(blob)
geo_after = hashlib.sha256(b"".join(bytes(d) for i, d in enumerate(data) if i not in img_views)).hexdigest()
assert geo_after == geo_before, "geometry changed"
js = json.dumps(j, separators=(",", ":")).encode()
js += b" " * (-len(js) % 4)
out = ROOT / f"world/{SCENE}.glb"
total = 12 + 8 + len(js) + 8 + len(blob)
with open(out, "wb") as f:
    f.write(b"glTF" + struct.pack("<II", 2, total))
    f.write(struct.pack("<I", len(js)) + b"JSON" + js)
    f.write(struct.pack("<I", len(blob)) + b"BIN\0" + bytes(blob))
print(f"{out.relative_to(ROOT)}: {len(b) / 1e6:.2f} -> {total / 1e6:.2f} MB, geometry identical")
