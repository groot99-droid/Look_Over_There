"""The connector kit's last step, in plain Python (needs Pillow): what tools/blender/build_kit.py leaves in its work folder becomes the kit's files.

    python tools/blender/kit_pack.py [--work work/kit] [--quality 90] [piece ...]

For each piece: <work>/kit_<piece>_0.png -> world/lightmaps/kit_<piece>_0.webp (8-bit, q90), and <work>/kit_<piece>_raw.glb -> world/kit/<piece>.glb
(its textures re-encoded as WebP by tools/webp_glb.py, which asserts the geometry bytes are unchanged). Then each baked material's
`lightmap_intensity` is multiplied by the piece's GAIN and capped where CAPS says (the same thing B1 did for its small props:
docs/renders/B1/caps.json on its branch), so the page's displayed brightness lands in the brief's band without a new bake.
The factors are listed in blender/kit/README.md with the brightness table they give.
"""
import json
import struct
import subprocess
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
PIECES = ["elevator", "stair_door", "safe_house", "sky_hall"]
GAIN = {"elevator": 1.0, "stair_door": 1.0, "safe_house": 1.0, "sky_hall": 1.0}
CAPS = {             # piece -> {material: factor}: a small bright material's own factor next to a lamp, on top of the GAIN
    "elevator": {"Car_Rust": 0.5, "Brass": 0.22, "Button_Grey": 0.55},            # the cab's ceiling round the bulb, the cage, the panel
    "stair_door": {"Fixture_Housing": 0.55, "Door_Handle": 0.75},                 # the light panel's housing round the tube
    "safe_house": {"SH_Paper": 0.2, "SH_Pad": 0.68},                              # the ledger under the green lamp, the pad round its ring
}


def read_glb(p):
    b = p.read_bytes()
    n = struct.unpack("<I", b[12:16])[0]
    j = json.loads(b[20:20 + n])
    rest = b[20 + n:]
    return j, rest


def write_glb(p, j, rest):
    js = json.dumps(j, separators=(",", ":")).encode()
    while len(js) % 4:
        js += b" "
    body = struct.pack("<I", len(js)) + b"JSON" + js + rest
    p.write_bytes(b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body)


def main(argv):
    work = Path(argv[argv.index("--work") + 1]) if "--work" in argv else ROOT / "work/kit"
    q = int(argv[argv.index("--quality") + 1]) if "--quality" in argv else 90
    todo = [a for a in argv if a in PIECES] or PIECES
    (ROOT / "world/lightmaps").mkdir(parents=True, exist_ok=True)
    (ROOT / "world/kit").mkdir(parents=True, exist_ok=True)
    for piece in todo:
        png = work / f"kit_{piece}_0.png"
        raw = work / f"kit_{piece}_raw.glb"
        assert png.exists() and raw.exists(), f"{piece}: run build_kit.py first ({png.name}, {raw.name})"
        im = Image.open(png).convert("RGB")
        assert max(im.size) <= 2048
        dst = ROOT / f"world/lightmaps/kit_{piece}_0.webp"
        im.save(dst, "WEBP", quality=q, method=6)
        glb = ROOT / f"world/kit/{piece}.glb"
        subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(raw), str(glb), str(q)], check=True, stdout=subprocess.DEVNULL)
        j, rest = read_glb(glb)
        changed = []
        for m in j.get("materials", []):
            ex = m.get("extras") or {}
            if "lightmap_intensity" in ex:
                k = GAIN[piece] * CAPS.get(piece, {}).get(m["name"], 1.0)
                ex["lightmap_intensity"] = round(ex["lightmap_intensity"] * k, 4)
                changed.append((m["name"], k))
            for key in list(ex):
                if key not in ("lightmap", "lightmap_intensity"):
                    del ex[key]
        for sc in j.get("scenes", []):
            sc.pop("extras", None)
        write_glb(glb, j, rest)
        print(f"{piece}: {dst.relative_to(ROOT)} {im.size[0]}x{im.size[1]} {dst.stat().st_size / 1e3:.0f} KB; {glb.relative_to(ROOT)} "
              f"{glb.stat().st_size / 1e6:.2f} MB; gain {GAIN[piece]}, caps {CAPS.get(piece, {})}")


if __name__ == "__main__":
    main(sys.argv[1:])
