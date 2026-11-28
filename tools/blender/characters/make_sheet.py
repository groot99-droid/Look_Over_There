"""Turn the renders from render_stills.py into the review JPEGs and sheets (plain Python with Pillow, no Blender).

  python tools/blender/characters/make_sheet.py <render_dir> [owner_png]

Writes docs/renders/characters/<name>.jpg (display pose and a clip frame side by side), the contact sheet
docs/renders/characters/contact_sheet.jpg (each at most 400 KB, no metadata) and, if asked, a labelled overview
PNG for a phone screen.
"""
import io
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DOCS = os.path.join(REPO, "docs", "renders", "characters")
LIMIT = 400 * 1024
NAMES = {"trex": "T. rex skeleton", "stalker": "The stalker", "mawcrawler": "Mawcrawler"}
CLIP = {"trex": "roar", "stalker": "freeze", "mawcrawler": "lunge"}


def label(name):
    if name in NAMES:
        return NAMES[name]
    return " ".join(w.capitalize() for w in name.replace("warrior_", "").split("_"))


def font(size, bold=False):
    for f in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(f, size)
        except OSError:
            pass
    return ImageFont.load_default()


def save_jpeg(im, path):
    """Largest quality that fits the limit. Pillow writes no comment or EXIF unless asked."""
    im = im.convert("RGB")
    for q in range(92, 40, -4):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() <= LIMIT:
            break
    else:
        raise RuntimeError(f"{path} does not fit in {LIMIT} bytes")
    open(path, "wb").write(buf.getvalue())
    return buf.tell(), q


def main():
    rdir = sys.argv[1]
    owner = sys.argv[2] if len(sys.argv) > 2 else None
    names = sorted({f.rsplit("_", 1)[0] for f in os.listdir(rdir) if f.endswith("_rest.png")})
    order = [n for n in ("trex", "stalker", "mawcrawler") if n in names] + [n for n in names if n.startswith("warrior_")]
    os.makedirs(DOCS, exist_ok=True)
    tiles = {}
    for n in order:
        a = Image.open(os.path.join(rdir, n + "_rest.png")).convert("RGB")
        b = Image.open(os.path.join(rdir, n + "_pose.png")).convert("RGB")
        im = Image.new("RGB", (a.width + b.width, a.height + 44), (12, 12, 14))
        im.paste(a, (0, 44))
        im.paste(b, (a.width, 44))
        d = ImageDraw.Draw(im)
        d.text((14, 8), f"{n}: display pose | {CLIP.get(n, 'attack')}", fill=(235, 235, 235), font=font(26, True))
        size, q = save_jpeg(im, os.path.join(DOCS, n + ".jpg"))
        print(n, size, "q", q)
        tiles[n] = a
    # contact sheet: every character in its display pose, 4 across
    tw, th = 300, 380
    cols = 4
    rows = (len(order) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 40)), (12, 12, 14))
    d = ImageDraw.Draw(sheet)
    for k, n in enumerate(order):
        t = tiles[n].copy()
        t.thumbnail((tw, th))
        x, y = (k % cols) * tw, (k // cols) * (th + 40)
        sheet.paste(t, (x + (tw - t.width) // 2, y + (th - t.height) // 2))
        d.text((x + 8, y + th + 8), label(n), fill=(235, 235, 235), font=font(20))
    print("contact_sheet", save_jpeg(sheet, os.path.join(DOCS, "contact_sheet.jpg")))
    if owner:
        W = 1200
        big = font(46, True)
        mid = font(34, True)
        small = font(28)
        rowsimg = []
        head = Image.new("RGB", (W, 120), (12, 12, 14))
        ImageDraw.Draw(head).text((30, 30), "Night at the museum + the City's monsters", fill=(255, 255, 255), font=big)
        rowsimg.append(head)

        def panel(n, w, h, title, sub):
            p = Image.new("RGB", (w, h + 110), (20, 20, 24))
            im = Image.open(os.path.join(rdir, n + "_pose.png")).convert("RGB")
            im.thumbnail((w - 10, h))
            p.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
            dd = ImageDraw.Draw(p)
            dd.text((16, h + 10), title, fill=(255, 255, 255), font=mid)
            dd.text((16, h + 58), sub, fill=(200, 200, 200), font=small)
            return p

        r1 = Image.new("RGB", (W, 0 + 560 + 110), (12, 12, 14))
        r1.paste(panel("trex", W, 560, "T. rex skeleton", "museum night mode: comes alive, roars"), (0, 0))
        rowsimg.append(r1)
        r2 = Image.new("RGB", (W, 520 + 110), (12, 12, 14))
        r2.paste(panel("stalker", W // 2 - 5, 520, "The stalker", "City streets 00:00-06:00"), (0, 0))
        r2.paste(panel("mawcrawler", W // 2 - 5, 520, "Mawcrawler", "random spawning mob"), (W // 2 + 5, 0))
        rowsimg.append(r2)
        cap = Image.new("RGB", (W, 80), (12, 12, 14))
        ImageDraw.Draw(cap).text((30, 20), "The museum's warriors (each one its own rigged model)", fill=(255, 255, 255), font=mid)
        rowsimg.append(cap)
        war = [n for n in order if n.startswith("warrior_")]
        for i in range(0, len(war), 4):
            r = Image.new("RGB", (W, 440 + 100), (12, 12, 14))
            for j, n in enumerate(war[i:i + 4]):
                im = Image.open(os.path.join(rdir, n + "_rest.png")).convert("RGB")
                im.thumbnail((W // 4 - 10, 430))
                x = j * (W // 4)
                r.paste(im, (x + (W // 4 - im.width) // 2, 5))
                words = label(n).split(" ")
                dd = ImageDraw.Draw(r)
                dd.text((x + 12, 445), " ".join(words[:-1]) or words[0], fill=(255, 255, 255), font=font(30, True))
                dd.text((x + 12, 485), words[-1] if len(words) > 1 else "", fill=(210, 210, 210), font=font(30))
            rowsimg.append(r)
        H = sum(r.height for r in rowsimg)
        out = Image.new("RGB", (W, H), (12, 12, 14))
        y = 0
        for r in rowsimg:
            out.paste(r, (0, y))
            y += r.height
        out.save(owner, optimize=True)
        print("owner", owner, out.size)


if __name__ == "__main__":
    main()
