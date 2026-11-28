"""The Blender rooms of Right Door, Wrong Exit as the game walks them: writes games/rdwe/blender_rooms.js from the room graph in
tools/blender/build_rdwe_greybox.py (PAIRS, SELF, OUTSIDE, the scene titles) and each delivered room's world/rdwe_<room>.json (its links:
where you leave by a door, where you land coming in by it, and the facing). Pure Python, no Blender: run it again after a room is
re-exported or the graph changes, and commit both files.

    python3 tools/blender/rdwe_links.py            writes games/rdwe/blender_rooms.js
    python3 tools/blender/rdwe_links.py --check    exits 1 if the file on disk is not what this would write

A room is delivered when both world/rdwe_<scene>.glb and world/rdwe_<scene>.json exist. A room's id in the game is its scene id without
`rdwe_` (rdwe_dining -> dining), so the seven rooms the game had keep their ids (the coop places `rdwe:<room>`, shared/farway.manifest.js).
A link from (A, door a) arrives in B at B's own link for door b: its `arrive` and `face`. A one-way pair's second side is an arrival door
that does not open back. A link that leaves the set (OUTSIDE) either ends the game (the way in, the finale's ending: the page takes the
player back where they came from, as when the game's last room was reached before) or is shut (a planned or reserved room that is not here).
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
import build_rdwe_greybox as G  # noqa: E402  (imports without Blender)

OUT = ROOT / "games" / "rdwe" / "blender_rooms.js"
ORDER = ["dining", "hallway", "teal", "teal2", "flooded", "trampoline", "grocery"]     # the story: the seven rooms in the order the game played them
LEAVE = {("rdwe_dining", "house"), ("rdwe_finale", "win")}                            # the OUTSIDE links that end the game


def short(scene):
    return scene[len("rdwe_"):] if scene.startswith("rdwe_") else scene


def r3(v):
    return [round(float(x), 3) for x in v]


def model():
    world = ROOT / "world"
    docs = {}
    for js in sorted(world.glob("rdwe_*.json")):
        scene = js.stem
        if (world / f"{scene}.glb").exists():
            docs[scene] = json.loads(js.read_text())
    missing = sorted(p.stem for p in world.glob("rdwe_*.glb") if p.stem not in docs)
    titles = {sid: G.SCENES[sid]().title for sid in G.SCENES}
    bad = []
    side_to = {}                                   # (scene, door) -> {room, door, kind} | {out, note}
    for (a, b, kind, _note) in G.PAIRS:
        if a[0] in docs and b[0] in docs:
            side_to[a] = {"room": short(b[0]), "door": b[1], "kind": kind}
            if kind != "one_way":
                side_to[b] = {"room": short(a[0]), "door": a[1], "kind": kind}
    for side in G.SELF:
        if side[0] in docs:
            side_to[side] = {"room": short(side[0]), "door": side[1], "kind": "self"}
    for side, (conn, lid, where) in G.OUTSIDE.items():
        if side[0] in docs:
            side_to[side] = {"out": "leave" if side in LEAVE else "shut", "note": lid.split(":")[0] + ": " + where}
    rooms = {}
    for scene, doc in docs.items():
        leaves = {d["name"]: d for d in doc.get("doors", [])}
        spawn = next((m["position"] for m in doc.get("markers", []) if m.get("kind") == "Spawn"), None)
        links = {}
        for l in doc.get("links", []):
            door = l["door"]
            leaf = f"DoorLeaf_{door}" if f"DoorLeaf_{door}" in leaves else None
            e = {"at": r3(l["at"]), "arrive": r3(l["arrive"]), "face": r3(l["face"]), "leaf": leaf}
            to = side_to.get((scene, door))
            if to is None:
                # the second side of a one-way pair (or a pair whose other room is not delivered yet): an arrival only
                other = [p for p in G.PAIRS if p[1] == (scene, door)]
                if other and other[0][2] == "one_way":
                    e["arrival"] = True
                elif other or [p for p in G.PAIRS if p[0] == (scene, door)]:
                    e["shut"] = "its other room is not delivered"
                else:
                    bad.append(f"{scene}.{door}: no side in PAIRS, SELF or OUTSIDE")
                    e["shut"] = "not in the room graph"
            elif "out" in to:
                e["out"] = to["out"]
                e["note"] = to["note"]
            else:
                e["to"] = {"room": to["room"], "door": to["door"]}
                e["kind"] = to["kind"]
            if leaf:
                d = leaves[leaf]
                for k in ("opens_when", "shows", "seen_from"):
                    if k in d:
                        e["when"] = f"{k.replace('_', ' ')} {d[k]}"
            links[door] = e
        rooms[short(scene)] = {"scene": scene, "title": titles.get(scene, short(scene)), "spawn": r3(spawn) if spawn else None, "links": links}
    # every link's destination exists, as a link of the room it names
    for rid, r in rooms.items():
        for door, e in r["links"].items():
            to = e.get("to")
            if to and (to["room"] not in rooms or to["door"] not in rooms[to["room"]]["links"]):
                bad.append(f"{rid}.{door} -> {to['room']}.{to['door']}: no such link")
    # the story: the link from each of the seven rooms to the next (the last one ends the game, as before)
    spine = {}
    for i, rid in enumerate(ORDER):
        nxt = ORDER[i + 1] if i + 1 < len(ORDER) else None
        hit = [d for d, e in rooms.get(rid, {}).get("links", {}).items() if nxt and e.get("to", {}).get("room") == nxt]
        spine[rid] = hit[0] if hit else None
        if nxt and not hit:
            bad.append(f"the story: no link from {rid} to {nxt}")
    return rooms, spine, missing, bad


def render(rooms, spine, missing):
    lines = [
        "// GENERATED by tools/blender/rdwe_links.py from tools/blender/build_rdwe_greybox.py (PAIRS, SELF, OUTSIDE) and world/rdwe_<room>.json. Do not edit:",
        "// change the graph or re-export the room, then run `python3 tools/blender/rdwe_links.py` and commit both.",
        "//",
        "// ROOMS[id] = {scene, title, spawn, links}: id is the scene without `rdwe_`. links[door] = {at, arrive, face, leaf, ...} where",
        "//   to: {room, door}, kind   leaving by this door lands at ROOMS[room].links[door].arrive, facing its face (game x, z)",
        "//   arrival: true            the second side of a one-way pair: you come in by it, it does not open back",
        "//   out: 'leave' | 'shut'    leaves the set: 'leave' ends the game (the page takes the player back), 'shut' is a room not built here (note says which)",
        "//   when                     the door's condition in the model (opens_when, shows, seen_from): not implemented, the door opens",
        "// SPINE[id] = the door the story takes from each of the seven rooms the game had (null: the game ends there, as before).",
        "// MISSING = rooms delivered as a .glb with no .json yet: not walkable.",
        "export const ROOMS = {",
    ]
    for rid in sorted(rooms):
        lines.append(f"  {rid}: {json.dumps(rooms[rid], separators=(', ', ': '))},")
    lines.append("};")
    lines.append(f"export const SPINE = {json.dumps(spine, separators=(', ', ': '))};")
    lines.append(f"export const MISSING = {json.dumps(missing, separators=(', ', ': '))};")
    return "\n".join(lines) + "\n"


def main():
    rooms, spine, missing, bad = model()
    for b in bad:
        print("BAD", b)
    text = render(rooms, spine, missing)
    if "--check" in sys.argv:
        same = OUT.exists() and OUT.read_text() == text
        print(f"{OUT.relative_to(ROOT)}: {'up to date' if same else 'STALE: run python3 tools/blender/rdwe_links.py'}")
        sys.exit(0 if same and not bad else 1)
    OUT.write_text(text)
    nlinks = sum(len(r["links"]) for r in rooms.values())
    print(f"wrote {OUT.relative_to(ROOT)}: {len(rooms)} rooms, {nlinks} links; not walkable yet (no json): {', '.join(missing) or 'none'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
