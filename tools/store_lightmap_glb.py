"""Writes a store floor's bake (tools/blender/bake_store.py) into its GLB, touching nothing else.

  python tools/store_lightmap_glb.py B1 <work folder> [--exposure 1.0] [--base <glb>]

- Each baked primitive gets TEXCOORD_1 (the lightmap UV, unsigned short normalized) as a new accessor on a new buffer view at the end of the
  binary chunk. The Draco data, every existing buffer view, accessor, node, skin, animation and camera stay byte for byte as they were
  (asserted below), so the geometry, UV0, the doors and the cameras do not change. three's GLTFLoader reads an attribute that is not in the
  Draco block as a plain accessor.
- Each baked material gets `lightmap` and `lightmap_intensity` in its extras (docs/BLENDER.md, R1). The intensity is pi x the map's white
  point x the exposure: the page shows texture x base colour x texel x intensity / pi. `--caps` lowers it for named materials (small,
  near-white or saturated props that would clip at the room's exposure) by a factor each.
- The maps go to world/lightmaps/<scene>_<n>.webp (8-bit WebP q90, no metadata).
- Scene extras that hold a machine's absolute user path (an add-on's script list, `sl_group`) are dropped; nothing on the page reads them.
"""
import argparse
import json
import math
import re
import struct
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def read_glb(b):
    assert b[:4] == b"glTF"
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    off = 20 + n
    bn = struct.unpack("<I", b[off:off + 4])[0]
    return j, bytearray(b[off + 8:off + 8 + bn])


def write_glb(j, BIN):
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    BIN = bytes(BIN) + b"\0" * (-len(BIN) % 4)
    total = 12 + 8 + len(js) + 8 + len(BIN)
    return b"glTF" + struct.pack("<II", 2, total) + struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(BIN)) + b"BIN\0" + BIN


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("scene"); ap.add_argument("work")
    ap.add_argument("--exposure", type=float, default=1.0)
    ap.add_argument("--caps", default=None, help="json {factor: {material: f}}: those materials' intensity x f (small bright props capped so they do not clip)")
    ap.add_argument("--base", default=None, help="the GLB to add to (default world/<scene>.glb); it must have no TEXCOORD_1 yet")
    a = ap.parse_args()
    work = Path(a.work)
    base = Path(a.base) if a.base else ROOT / "world" / f"{a.scene}.glb"
    raw = base.read_bytes()
    j0, BIN0 = read_glb(raw)
    j, BIN = json.loads(json.dumps(j0)), bytearray(BIN0)
    rep = json.loads((work / f"{a.scene}_bake.json").read_text())
    uv = (work / f"{a.scene}_uv1.bin").read_bytes()
    for m in j["meshes"]:
        for p in m["primitives"]:
            if "TEXCOORD_1" in p["attributes"]:
                sys.exit(f"{base} already has TEXCOORD_1: start from the shipped GLB (--base)")
    n_bv0, n_acc0 = len(j["bufferViews"]), len(j["accessors"])
    added = 0
    for r in rep["prims"]:
        p = j["meshes"][r["mesh"]]["primitives"][r["prim"]]
        cnt = j["accessors"][p["attributes"]["POSITION"]]["count"]
        assert cnt == r["count"], (r, cnt)
        v = np.frombuffer(uv, np.float32, count=r["count"] * 2, offset=r["offset"]).reshape(-1, 2)
        assert v.min() >= -1e-4 and v.max() <= 1 + 1e-4, ("lightmap UV outside 0..1", r)
        q = np.round(np.clip(v, 0, 1) * 65535).astype("<u2")
        BIN += b"\0" * (-len(BIN) % 4)
        j["bufferViews"].append({"buffer": 0, "byteOffset": len(BIN), "byteLength": q.nbytes, "target": 34962})
        BIN += q.tobytes()
        j["accessors"].append({"bufferView": len(j["bufferViews"]) - 1, "componentType": 5123, "normalized": True, "count": len(q), "type": "VEC2",
                               "min": (q.min(axis=0) / 65535).tolist(), "max": (q.max(axis=0) / 65535).tolist()})
        p["attributes"]["TEXCOORD_1"] = len(j["accessors"]) - 1
        added += 1
    j["buffers"][0]["byteLength"] = len(BIN) + (-len(BIN) % 4)
    out_dir = ROOT / "world" / "lightmaps"; out_dir.mkdir(parents=True, exist_ok=True)
    caps = json.loads(Path(a.caps).read_text())["factor"] if a.caps else {}
    pages = {}
    for n, pg in rep["pages"].items():
        url = f"world/lightmaps/{a.scene}_{n}.webp"
        im = Image.open(work / f"{a.scene}_{n}.png").convert("RGB")
        im.save(ROOT / url, "WEBP", quality=90, method=6)
        pages[int(n)] = (url, round(math.pi * pg["scale"] * a.exposure, 4))
    for name, mr in rep["materials"].items():
        m = j["materials"][mr["index"]]
        assert m["name"] == name
        url, k = pages[mr["page"]]
        if name in caps:
            assert 0 < caps[name] <= 1, (name, caps[name])
            k = round(k * caps[name], 4)
        m["extras"] = {**m.get("extras", {}), "lightmap": url, "lightmap_intensity": k}
    # scrub: an add-on of the machine that exported the store wrote its script list, with absolute paths of the user folder, into the scene's
    # extras (sl_group). The page reads none of it; drop any scene extra that holds such a path, so the public file carries none.
    priv = re.compile(r"[A-Za-z]:[\\/]+Users[\\/]|/home/[^/]+/|/Users/[^/]+/")
    scrubbed = []
    for sc in j["scenes"]:
        ex = sc.get("extras", {})
        for k in list(ex):
            if priv.search(json.dumps(ex[k])):
                del ex[k]; scrubbed.append(k)
    assert not priv.search(json.dumps(j)), "a machine path is still in the GLB"
    # nothing else that was there has changed
    assert BIN[:len(BIN0)] == BIN0, "the existing binary data changed"
    assert j["bufferViews"][:n_bv0] == j0["bufferViews"] and j["accessors"][:n_acc0] == j0["accessors"]
    for k in j0:
        if k not in ("bufferViews", "accessors", "buffers", "materials", "meshes", "scenes"):
            assert j[k] == j0[k], k
    for s0, s1 in zip(j0["scenes"], j["scenes"]):
        e0 = {k: v for k, v in s0.get("extras", {}).items() if k not in scrubbed}
        assert {k: v for k, v in s0.items() if k != "extras"} == {k: v for k, v in s1.items() if k != "extras"} and e0 == s1.get("extras", {})
    for m0, m1 in zip(j0["meshes"], j["meshes"]):
        for p0, p1 in zip(m0["primitives"], m1["primitives"]):
            a1 = dict(p1["attributes"]); a1.pop("TEXCOORD_1", None)
            assert a1 == p0["attributes"] and {k: v for k, v in p1.items() if k != "attributes"} == {k: v for k, v in p0.items() if k != "attributes"}
    for m0, m1 in zip(j0["materials"], j["materials"]):
        assert {k: v for k, v in m0.items() if k != "extras"} == {k: v for k, v in m1.items() if k != "extras"}
    dst = ROOT / "world" / f"{a.scene}.glb"
    dst.write_bytes(write_glb(j, BIN))
    print(f"{dst.name}: {len(raw)} -> {dst.stat().st_size} bytes (+{(dst.stat().st_size / len(raw) - 1) * 100:.1f} %), TEXCOORD_1 on {added} primitives, "
          f"{len(rep['materials'])} materials baked ({len(caps)} capped), scene extras scrubbed: {scrubbed}, {len(pages)} maps: " + ", ".join(f"{u} x{k}" for u, k in pages.values()))


if __name__ == "__main__":
    main()
