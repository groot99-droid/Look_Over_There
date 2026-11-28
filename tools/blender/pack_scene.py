"""The last step of a Blender scene build, in plain Python (needs Pillow): the bake's lightmap PNGs become WebP, the exported GLB's textures become WebP.

    python tools/blender/pack_scene.py <scene> [--work <dir>] [--quality 90]

Reads <work>/<scene>_<n>.png and <work>/<scene>_raw.glb (what `build_<scene>.py --stage bake` and `--stage export` leave in the work folder,
the system temp folder's farway_<scene> by default) and writes world/lightmaps/<scene>_<n>.webp (8-bit, q90, each at most 2048 x 2048)
and world/<scene>.glb (through tools/webp_glb.py, which asserts that the geometry bytes are unchanged).
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def main(argv):
    scene = argv[0]
    work = Path(argv[argv.index("--work") + 1]) if "--work" in argv else Path(os.environ.get("TEMP", tempfile.gettempdir())) / f"farway_{scene}"
    q = int(argv[argv.index("--quality") + 1]) if "--quality" in argv else 90
    out = ROOT / "world/lightmaps"
    out.mkdir(parents=True, exist_ok=True)
    pngs = sorted(work.glob(f"{scene}_[0-9]*.png"))
    assert pngs, f"no lightmap PNGs {scene}_<n>.png in {work}"
    assert len(pngs) <= 4, "at most four lightmaps per scene (docs/BLENDER.md R1)"
    for png in pngs:
        im = Image.open(png).convert("RGB")
        assert max(im.size) <= 2048, f"{png.name} is {im.size}: at most 2048 x 2048"
        dst = out / (png.stem + ".webp")
        im.save(dst, "WEBP", quality=q, method=6)
        print(f"{dst.relative_to(ROOT)}  {im.size[0]}x{im.size[1]}  {dst.stat().st_size / 1e3:.0f} KB")
    raw = work / f"{scene}_raw.glb"
    glb = ROOT / f"world/{scene}.glb"
    b = raw.read_bytes()
    if b'"images"' in b[20:20 + int.from_bytes(b[12:16], "little")]:
        subprocess.run([sys.executable, str(ROOT / "tools/webp_glb.py"), str(raw), str(glb), str(q)], check=True)
    else:                                                              # flat colours only (the table and chairs): nothing to convert
        glb.write_bytes(b)
    print(f"{glb.relative_to(ROOT)}  {glb.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main(sys.argv[1:])
