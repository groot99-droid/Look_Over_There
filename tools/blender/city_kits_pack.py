"""The City's kits, last step, in plain Python (needs Pillow): what tools/blender/build_city_kits.py leaves in its work folder becomes the kits' files.

    python tools/blender/city_kits_pack.py [--work work/city_kits] [--quality 90] [piece ...]

For each piece: <work>/<piece>/kit_<piece>_<n>.png -> world/lightmaps/kit_<piece>_<n>.webp (8-bit, q90, linear AO: the page loads it with NoColorSpace),
and <work>/<piece>/kit_<piece>_raw.glb -> world/kit/<piece>.glb (its textures re-encoded as WebP by tools/webp_glb.py, which asserts that the
geometry bytes are unchanged). The materials keep `aomap` and `aomap_intensity` in their extras and nothing else; the scene's extras are dropped.
"""
import json
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PIECES = ["street_segment", "bus_stop", "depot_yard"]


def read_glb(p):
    b = p.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    return json.loads(b[20:20 + n]), b[20 + n:]


def write_glb(p, j, rest):
    js = json.dumps(j, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    body = struct.pack("<I", len(js)) + b"JSON" + js + rest
    p.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)


def main(argv):
    work = Path(argv[argv.index("--work") + 1]) if "--work" in argv else ROOT / "work/city_kits"
    q = int(argv[argv.index("--quality") + 1]) if "--quality" in argv else 90
    todo = [a for a in argv if a in PIECES] or PIECES
    (ROOT / "world/lightmaps").mkdir(parents=True, exist_ok=True)
    (ROOT / "world/kit").mkdir(parents=True, exist_ok=True)
    for piece in todo:
        wd = work / piece
        pngs = sorted(wd.glob(f"kit_{piece}_[0-9].png"))
        raw = wd / f"kit_{piece}_raw.glb"
        assert pngs and raw.exists(), f"{piece}: run build_city_kits.py --stage bake,export first"
        assert len(pngs) <= 4, "at most four AO maps a piece"
        for png in pngs:
            im = Image.open(png).convert("RGB")
            assert max(im.size) <= 2048
            dst = ROOT / f"world/lightmaps/{png.stem}.webp"
            im.save(dst, "WEBP", quality=q, method=6)
            print(f"{dst.relative_to(ROOT).as_posix()}  {im.size[0]}x{im.size[1]}  {dst.stat().st_size / 1e3:.0f} KB")
        glb = ROOT / f"world/kit/{piece}.glb"
        subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(raw), str(glb), str(q)], check=True, stdout=subprocess.DEVNULL)
        j, rest = read_glb(glb)
        for m in j.get("materials", []):
            ex = m.get("extras") or {}
            for key in list(ex):
                if key not in ("aomap", "aomap_intensity"):
                    del ex[key]
        for sc in j.get("scenes", []):
            sc.pop("extras", None)
        write_glb(glb, j, rest)
        print(f"{glb.relative_to(ROOT).as_posix()}  {glb.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1:])
