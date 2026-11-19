# Re-encode a GLB's PNG and JPEG textures as WebP (EXT_texture_webp), leaving every other byte of geometry as it was.
# usage: python3 tools/webp_glb.py in.glb out.glb [quality]   (needs Pillow; used for models/items/, see its README)
import sys, json, struct, io, hashlib
from PIL import Image
src, dst, q = sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 95
b = open(src, "rb").read()
assert b[:4] == b"glTF" and struct.unpack("<I", b[4:8])[0] == 2
jlen = struct.unpack("<I", b[12:16])[0]; assert b[16:20] == b"JSON"; j = json.loads(b[20:20+jlen])
blen = struct.unpack("<I", b[20+jlen:24+jlen])[0]; assert b[24+jlen:28+jlen] == b"BIN\x00"; binc = b[28+jlen:28+jlen+blen]
assert len(j["buffers"]) == 1 and "uri" not in j["buffers"][0]
views = j["bufferViews"]; data = [binc[v.get("byteOffset", 0): v.get("byteOffset", 0) + v["byteLength"]] for v in views]
geo_before = hashlib.sha256(b"".join(d for i, d in enumerate(data) if i not in {im["bufferView"] for im in j["images"]})).hexdigest()
sizes = []
for im in j["images"]:
    i = im["bufferView"]; img = Image.open(io.BytesIO(data[i])); assert im.get("mimeType") in ("image/png", "image/jpeg"), im
    o = io.BytesIO(); img.save(o, "WEBP", quality=q, method=6); sizes.append((img.size, len(data[i]), o.tell())); data[i] = o.getvalue(); im["mimeType"] = "image/webp"
for t in j["textures"]:
    if "source" in t: t.setdefault("extensions", {})["EXT_texture_webp"] = {"source": t.pop("source")}
for k in ("extensionsUsed", "extensionsRequired"):
    j[k] = sorted(set(j.get(k, [])) | {"EXT_texture_webp"})
out = bytearray()
for v, d in zip(views, data):
    while len(out) % 4: out.append(0)
    v["byteOffset"] = len(out); v["byteLength"] = len(d); out += d
while len(out) % 4: out.append(0)
j["buffers"][0]["byteLength"] = len(out)
geo_after = hashlib.sha256(b"".join(bytes(out[v["byteOffset"]: v["byteOffset"] + v["byteLength"]]) for i, v in enumerate(views) if i not in {im["bufferView"] for im in j["images"]})).hexdigest()
assert geo_before == geo_after, "geometry bytes changed"
js = json.dumps(j, separators=(",", ":")).encode(); js += b" " * (-len(js) % 4)
glb = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(out)) + struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(out)) + b"BIN\x00" + bytes(out)
open(dst, "wb").write(glb)
print(f"{dst.split('/')[-1]:34s} {len(b)/1e6:4.1f} -> {len(glb)/1e6:4.2f} MB  {len(sizes)} texture(s), {sizes[0][0][0]}px, {sum(s[1] for s in sizes)/1e6:.1f} -> {sum(s[2] for s in sizes)/1e6:.2f} MB  geometry identical")
