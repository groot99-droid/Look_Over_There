"""The store's outside model after the owner's ruling of 2026-11-27 ("The parking lot was supposed to be part of the overworld and that house
with balloons was supposed to go since it's been replaced"), in plain Python (no Blender, no Draco decoding):

    python tools/split_exterior.py            rewrites world/Exterior.glb, world/L4.json and world/gbi_L4_4.json (running it again changes nothing)
    python tools/split_exterior.py --dry      says what it would drop, writes nothing

world/Exterior.glb keeps only what the Original's L4 and Going back in's gbi_L4_4 still need from it: the Intern's street and gate, the city round
it, its road (Road_ITN) and the sky box (Sky_LOT_Exterior, which index.html's applySky lights). The lot moves to its own scene
(world/parking_lot.glb, built by tools/blender/build_overworld_lot.py), which those two scenes draw too. Dropped:
  - the lot (ROOM_LOT_Exterior and everything under it, but the sky box, which is lifted to the top with the same place in the world);
  - the Right Door, Wrong Exit house and everything of it: RDW_House_* (walls, roof, trim, floor, balloons, flowers, swing, fence, clouds, sun,
    the "wrong exit"), its furniture (the top-level Set_* nodes), the road to it (Road_RDW);
  - the house's gate: Gate_RDW_wall, Gate_RDW_step, DoorLeaf_Gate_RDW, Entrance_RDW_House_1;
  - the traffic cones west of the city (Extra_one.* with x < 60): the lot's are the lot scene's now, the house's go with it.
Every mesh, material, texture, image, sampler, accessor and buffer view nothing uses any more is dropped and the binary chunk is rebuilt from the
buffer views that stay, byte for byte (Draco-compressed primitives are copied as they are). The scene's extras lose `sl_group` (an add-on's
script list with a user folder in it) and the sites' `origin` (a repository owner's name); nothing on the page reads either.

world/L4.json and world/gbi_L4_4.json (the store's floor and its Going back in chamber, which draw the lot too) lose the gate's stairwell
(Gate_RDW, 19 boxes) and the house's two props (Extra_Props_LOT west of x -100); the holes the stairwell left in the ground and the grass are
filled; the south hedge is cut where the lot's art cuts it (the road's gap, x -34 to -26, and the stile's, x 29 to 31). Their doors and markers
are left as they are: DoorLeaf_Gate_RDW and the marker Entrance_RDW_House_1 go when the coordinator drops the gate from the manifest (and from
shared/manifest.test.js, which names it).
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GLB = ROOT / "world/Exterior.glb"
LAYOUTS = [ROOT / "world/L4.json", ROOT / "world/gbi_L4_4.json"]
DROP_TOP = ("RDW_House_", "Gate_RDW_", "DoorLeaf_Gate_RDW", "Entrance_RDW_House_1", "Road_RDW", "Set_")
LOT_ROOT, SKY = "ROOM_LOT_Exterior", "Sky_LOT_Exterior"
HEDGE_S = ([-63.0, 9.6, 98.0], [63.0, 12.2, 99.5])
HEDGE_GAPS = [(-34.0, -26.0), (29.0, 31.0)]               # tools/blender/build_overworld_greybox.py: LOT_ROAD_GAP, LOT_STILE_GAP
GATE_HOLE = (-122.6, -119.8, 57.44, 62.6)                  # where the gate's stairwell went down through the ground and the grass


def read_glb(path):
    b = path.read_bytes()
    assert b[:4] == b"glTF" and struct.unpack_from("<I", b, 4)[0] == 2
    n = struct.unpack_from("<I", b, 12)[0]
    doc = json.loads(b[20:20 + n].decode("utf-8"))
    off = 20 + n
    bn = struct.unpack_from("<I", b, off)[0]
    assert b[off + 4:off + 8] == b"BIN\x00"
    return doc, b[off + 8:off + 8 + bn]


def write_glb(path, doc, binary):
    js = json.dumps(doc, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    js += b" " * (-len(js) % 4)
    binary += b"\x00" * (-len(binary) % 4)
    out = b"glTF" + struct.pack("<II", 2, 12 + 8 + len(js) + 8 + len(binary))
    out += struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(binary)) + b"BIN\x00" + binary
    path.write_bytes(out)


def walk_indices(o, key_map, path=()):
    """Every integer index field in a glTF object tree: yields (container, key, kind)."""
    if isinstance(o, dict):
        for k, v in list(o.items()):
            kind = key_map(path, k)
            if kind and isinstance(v, int):
                yield o, k, kind
            elif isinstance(v, (dict, list)):
                yield from walk_indices(v, key_map, path + (k,))
    elif isinstance(o, list):
        for v in o:
            yield from walk_indices(v, key_map, path)


def split_glb(doc, binary, dry=False):
    nodes = doc["nodes"]
    names = [n.get("name", "") for n in nodes]
    scene = doc["scenes"][doc.get("scene", 0)]
    roots = list(scene["nodes"])
    dropped = []
    keep_roots = []
    for r in roots:
        nm = names[r]
        if nm == LOT_ROOT:
            lot = nodes[r]
            assert not lot.get("rotation") and not lot.get("scale"), "the lot's root has only a translation"
            t = lot.get("translation", [0.0, 0.0, 0.0])
            for c in lot.get("children", []):
                if names[c] == SKY:
                    sky = nodes[c]
                    st = sky.get("translation", [0.0, 0.0, 0.0])
                    sky["translation"] = [t[i] + st[i] for i in range(3)]
                    keep_roots.append(c)
            dropped.append(f"{nm} (the lot: {len(lot.get('children', [])) - 1} nodes; {SKY} kept)")
        elif nm.startswith(DROP_TOP) or (nm.startswith("Extra_one") and nodes[r].get("translation", [0.0])[0] < 60.0):
            dropped.append(nm)
        else:
            keep_roots.append(r)
    if not dropped:
        return None, []
    # the nodes that stay: the kept roots and their children
    keep_nodes, todo = [], list(keep_roots)
    while todo:
        i = todo.pop()
        if i not in keep_nodes:
            keep_nodes.append(i)
            todo += nodes[i].get("children", [])
    keep_nodes.sort()
    nmap = {o: k for k, o in enumerate(keep_nodes)}
    # what they use
    meshes = sorted({nodes[i]["mesh"] for i in keep_nodes if "mesh" in nodes[i]})
    mats, accs, bvs = set(), set(), set()
    for m in meshes:
        for p in doc["meshes"][m]["primitives"]:
            accs |= set(p["attributes"].values())
            if "indices" in p:
                accs.add(p["indices"])
            for t in p.get("targets", []):
                accs |= set(t.values())
            if "material" in p:
                mats.add(p["material"])
            dr = p.get("extensions", {}).get("KHR_draco_mesh_compression")
            if dr:
                bvs.add(dr["bufferView"])
    tex = set()
    for m in mats:
        for o, k, kind in walk_indices(doc["materials"][m], lambda path, k: "texture" if k == "index" and path and path[-1].endswith("Texture") else None):
            tex.add(o[k])
    imgs = {doc["textures"][t]["source"] for t in tex if "source" in doc["textures"][t]}
    for t in tex:
        for ext in doc["textures"][t].get("extensions", {}).values():
            if "source" in ext:
                imgs.add(ext["source"])
    samps = {doc["textures"][t]["sampler"] for t in tex if "sampler" in doc["textures"][t]}
    for a in accs:
        if "bufferView" in doc["accessors"][a]:
            bvs.add(doc["accessors"][a]["bufferView"])
        sp = doc["accessors"][a].get("sparse")
        if sp:
            bvs |= {sp["indices"]["bufferView"], sp["values"]["bufferView"]}
    for i in imgs:
        if "bufferView" in doc["images"][i]:
            bvs.add(doc["images"][i]["bufferView"])
    maps = {}
    for kind, used in (("meshes", meshes), ("materials", mats), ("textures", tex), ("images", imgs), ("samplers", samps), ("accessors", accs),
                       ("bufferViews", bvs)):
        used = sorted(used)
        maps[kind] = {o: k for k, o in enumerate(used)}
        doc[kind] = [doc[kind][o] for o in used]
    # rebuild the binary chunk from the buffer views that stay, each on a 4-byte boundary (an accessor's offset inside its view is unchanged)
    out = bytearray()
    for v in doc["bufferViews"]:
        out += b"\x00" * (-len(out) % 4)
        s = v.get("byteOffset", 0)
        chunk = binary[s:s + v["byteLength"]]
        v["byteOffset"] = len(out)
        out += chunk
    doc["buffers"] = [{"byteLength": len(out)}]
    # remap every reference
    doc["nodes"] = [nodes[i] for i in keep_nodes]
    for n in doc["nodes"]:
        if "children" in n:
            n["children"] = [nmap[c] for c in n["children"]]
        if "mesh" in n:
            n["mesh"] = maps["meshes"][n["mesh"]]
    scene["nodes"] = [nmap[r] for r in keep_roots]
    for me in doc["meshes"]:
        for p in me["primitives"]:
            p["attributes"] = {k: maps["accessors"][v] for k, v in p["attributes"].items()}
            if "indices" in p:
                p["indices"] = maps["accessors"][p["indices"]]
            if "material" in p:
                p["material"] = maps["materials"][p["material"]]
            dr = p.get("extensions", {}).get("KHR_draco_mesh_compression")
            if dr:
                dr["bufferView"] = maps["bufferViews"][dr["bufferView"]]
    for a in doc["accessors"]:
        if "bufferView" in a:
            a["bufferView"] = maps["bufferViews"][a["bufferView"]]
        sp = a.get("sparse")
        if sp:
            for part in ("indices", "values"):
                sp[part]["bufferView"] = maps["bufferViews"][sp[part]["bufferView"]]
    for m in doc["materials"]:
        for o, k, kind in walk_indices(m, lambda path, k: "texture" if k == "index" and path and path[-1].endswith("Texture") else None):
            o[k] = maps["textures"][o[k]]
    for t in doc["textures"]:
        if "source" in t:
            t["source"] = maps["images"][t["source"]]
        if "sampler" in t:
            t["sampler"] = maps["samplers"][t["sampler"]]
        for ext in t.get("extensions", {}).values():
            if "source" in ext:
                ext["source"] = maps["images"][ext["source"]]
    for im in doc["images"]:
        if "bufferView" in im:
            im["bufferView"] = maps["bufferViews"][im["bufferView"]]
    for bv in doc["bufferViews"]:
        bv["buffer"] = 0
    # the extensions still in use
    text = json.dumps({k: doc[k] for k in ("materials", "meshes", "textures", "nodes")})
    doc["extensionsUsed"] = [e for e in doc.get("extensionsUsed", []) if f'"{e}"' in text]
    if "extensionsRequired" in doc:
        doc["extensionsRequired"] = [e for e in doc["extensionsRequired"] if e in doc["extensionsUsed"]]
    return bytes(out), dropped


def scrub_extras(doc):
    """The scene's extras: no add-on script list with a user folder, no repository owner's name."""
    ex = doc["scenes"][doc.get("scene", 0)].get("extras", {})
    notes = []
    if "sl_group" in ex:
        del ex["sl_group"]
        notes.append("sl_group")
    if isinstance(ex.get("bk_sites"), str):
        sites = json.loads(ex["bk_sites"])
        if any("origin" in s for s in sites):
            for s in sites:
                s.pop("origin", None)
            ex["bk_sites"] = json.dumps(sites)
            notes.append("bk_sites[].origin")
    return notes


def split_layout(doc):
    """Drop the gate's stairwell and the house's props, fill the holes, cut the south hedge. Returns what changed."""
    notes = []
    cols = doc["colliders"]
    gate = [c for c in cols if c["s"] == "Gate_RDW"]
    house = [c for c in cols if c["s"] == "Extra_Props_LOT" and c["max"][0] < -100.0]
    if gate or house:
        cols[:] = [c for c in cols if c not in gate and c not in house]
        notes.append(f"dropped {len(gate)} Gate_RDW and {len(house)} Extra_Props_LOT boxes")
    x0, x1, z0, z1 = GATE_HOLE
    for s, y0 in (("Ground_LOT_Exterior", 8.6), ("Ground_LOT_Exterior_grass", 9.0)):
        fill = {"s": s, "min": [x0, y0, z0], "max": [x1, 9.6, z1]}
        if fill not in cols:
            cols.append(fill)
            notes.append(f"filled the stairwell's hole in {s}")
    for i, c in enumerate(cols):
        if c["s"] == "Hedges_LOT_Exterior" and c["min"] == HEDGE_S[0] and c["max"] == HEDGE_S[1]:
            cuts = [HEDGE_S[0][0]] + [v for g in HEDGE_GAPS for v in g] + [HEDGE_S[1][0]]
            parts = [{"s": c["s"], "min": [cuts[k], HEDGE_S[0][1], HEDGE_S[0][2]], "max": [cuts[k + 1], HEDGE_S[1][1], HEDGE_S[1][2]]}
                     for k in range(0, len(cuts), 2)]
            cols[i:i + 1] = parts
            notes.append(f"cut the south hedge into {len(parts)} (the road's gap and the stile's)")
            break
    return notes


def main(argv):
    dry = "--dry" in argv
    doc, binary = read_glb(GLB)
    before = len(binary)
    out, dropped = split_glb(doc, binary, dry)
    notes = scrub_extras(doc)
    if out is None and not notes:
        print("world/Exterior.glb: already split, nothing to drop")
    else:
        print(f"world/Exterior.glb: dropped {len(dropped)} top-level nodes: {', '.join(dropped)}")
        print(f"  scene extras dropped: {', '.join(notes) or 'none'}; binary {before} -> {len(out if out is not None else binary)} bytes; "
              f"{len(doc['nodes'])} nodes, {len(doc['meshes'])} meshes, {len(doc['materials'])} materials, {len(doc['images'])} images")
        if not dry:
            write_glb(GLB, doc, out if out is not None else binary)
            print(f"  wrote {GLB.relative_to(ROOT)} ({GLB.stat().st_size} bytes)")
    for f in LAYOUTS:
        d = json.loads(f.read_text())
        n = split_layout(d)
        print(f"{f.relative_to(ROOT)}: " + ("; ".join(n) if n else "already split"))
        if n and not dry:
            f.write_text(json.dumps(d, separators=(",", ":")))


if __name__ == "__main__":
    main(sys.argv[1:])
