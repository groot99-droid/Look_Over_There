"""The last step of a teal-wing / institution room (tools/blender/build_rdwe_rooms2.py), in plain Python (numpy, Pillow): grades the bake's raw
irradiance into the lightmap WebPs, turns the exported GLB's textures to WebP (tools/webp_glb.py) and writes each baked material's intensities.

    python tools/blender/rdwe_rooms2_pack.py <scene> [--target 0.9] [--shoulder 1.15] [--cap Material=0.9,...]

The page draws a baked material unlit, with no tone mapping: shown = texture x base colour x texel x intensity / pi. A texel is written with a
shoulder: texel = G L / (C + G L) and intensity = pi C, so the page shows texture x C G L / (C + G L): about texture x G L where the light is
ordinary, rolling off toward texture x C under a lamp, never clipping. G is set so that the median texel of the shell's page in the room's
reference set is `target` (the room's `grade` in bake.json: one G for every set, so a darker set stays darker, or one per set). A cap lowers one
material's intensity. Reads work/<scene>/bake.json, raw_<n>.npy and <scene>_raw.glb; writes world/lightmaps/<scene>_<n>.webp, world/<scene>.glb
and work/<scene>/grade.json.
"""
import json
import math
import struct
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def srgb_encode(x):
    x = np.clip(x, 0, 1)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def glb_read(p):
    b = p.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    return j, rest


def glb_write(p, j, rest):
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * ((4 - len(js) % 4) % 4)
    total = 12 + 8 + len(js) + len(rest)
    p.write_bytes(struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(js), 0x4E4F534A) + js + rest)


def main(argv):
    sid = argv[0]
    w = ROOT / "work" / sid
    bake = json.loads((w / "bake.json").read_text())
    grade = bake.get("grade", {})

    def opt(n, d, cast=float):
        return cast(argv[argv.index(n) + 1]) if n in argv else d
    target = opt("--target", grade.get("target", 0.9))
    C = opt("--shoulder", grade.get("shoulder", 1.15))
    caps = dict(grade.get("caps", {}))
    if "--cap" in argv:
        for kv in argv[argv.index("--cap") + 1].split(","):
            k, v = kv.split("=")
            caps[k] = float(v)
    ref_set = grade.get("ref_set", bake["sets"][0])
    mode = grade.get("mode", "shared")
    maps = {int(k): v for k, v in bake["maps"].items()}
    raw = {i: np.load(w / f"raw_{i}.npy").astype(np.float32) for i in maps}

    def g_of(st):
        idx = [i for i, m in maps.items() if m["set"] == st and "struct" in m["groups"]]
        L = raw[idx[0]].max(axis=2)
        sel = L > 1e-6
        p50 = float(np.percentile(L[sel], 50)) if sel.any() else 1.0
        return target / max(p50, 1e-6), p50
    Gs = {}
    if mode == "shared":
        g, p50 = g_of(ref_set)
        Gs = {s: g for s in bake["sets"]}
    else:
        Gs = {s: g_of(s)[0] for s in bake["sets"]}
    Gs.update(grade.get("set_gain", {}) and {s: Gs[s] * f for s, f in grade.get("set_gain", {}).items()})
    out = ROOT / "world/lightmaps"
    out.mkdir(parents=True, exist_ok=True)
    rep = {}
    for i, m in sorted(maps.items()):
        L = raw[i]
        G = Gs[m["set"]]
        tex = G * L / (C + G * L)
        im = Image.fromarray((srgb_encode(tex) * 255 + 0.5).astype(np.uint8)[::-1], "RGB")
        dst = out / f"{sid}_{i}.webp"
        im.save(dst, "WEBP", quality=90, method=6)
        pk = L.max(axis=2)
        sel = pk > 1e-6
        rep[i] = {"set": m["set"], "G": round(G, 4), "C": C, "irradiance_p50_p90_p99": [round(float(v), 4) for v in np.percentile(pk[sel], [50, 90, 99])],
                  "webp_kb": round(dst.stat().st_size / 1e3)}
        print(f"{dst.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {dst.stat().st_size / 1e3:.0f} KB  set {m['set']}  G {G:.3f}")
    glb = ROOT / f"world/{sid}.glb"
    subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(w / f"{sid}_raw.glb"), str(glb), "90"], check=True)
    j, rest = glb_read(glb)
    nm = 0
    for mt in j.get("materials", []):
        ex = mt.get("extras", {})
        for k in list(ex):
            if k.endswith("_intensity") and k[:-len("_intensity")] in ex:
                ex[k] = round(math.pi * C * caps.get(mt["name"], 1.0), 4)
                nm += 1
    for nd in j.get("nodes", []):
        if nd.get("name", "").endswith("_x"):
            nd["name"] = nd["name"][:-2]
    glb_write(glb, j, rest)
    (w / "grade.json").write_text(json.dumps({"target": target, "shoulder": C, "caps": caps, "G": Gs, "mode": mode, "maps": rep}, indent=1))
    print(f"{glb.relative_to(ROOT)}  {glb.stat().st_size / 1e6:.2f} MB; {nm} intensities written (pi x {C} x cap)")


if __name__ == "__main__":
    main(sys.argv[1:])
