"""Writes shared/farway.scenes.js: the Blender areas' scenes and links for the world manifest (shared/farway.manifest.js imports it).

    python3 tools/blender/wire_scenes.py          # write it
    python3 tools/blender/wire_scenes.py --check  # exit 1 if the file on disk is not what this would write

Plain Python, no Blender. It reads, for each Blender area (docs/BLENDER_AREAS.md):
  - the greybox builder's SCENES (which scenes the area has, and each one's floor level) and PAIRS (which door meets which), from
    tools/blender/build_<area>_greybox.py;
  - world/<scene>.json, for each door's `arrive` and `face` (export_scene.py writes them: where you stand when you come in by that door).
A pair ((A, a), (B, b), connector) is two links, A's door a to B (arriving at B's link b) and back, or one for a one_way connector. The joins onto the
scenes that are not Blender-first (the street, the mall's entrance, the grocery's main floor, the laboratory, hotel floor 3's apartment door) are
in JOINS below, with their F spot on the older side (`from.at`), from each builder's OUTSIDE notes.

Every new scene is a presence scene (a room's players see each other there). A link that touches a scene that is not one (the mall's entrance,
the grocery's main floor, the laboratory) is soloOnly, as the manifest requires.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / "shared/farway.scenes.js"

# builder module -> manifest area id
AREAS = [("hotel", "hotel"), ("grocery", "grocery"), ("mall", "mall"), ("overworld", "overworld"), ("secretops", "secret_ops")]
# scenes the manifest itself lists, by hand (their files and links are written there): links to and from them are still made here
HAND_SCENES = {"parking_lot"}
# scenes a builder has that are not scenes of the game (the hotel's room layouts load behind doors, world/rooms/)
NOT_SCENES = {"motel_a", "motel_b", "green_room", "clue_room", "empty_room",
              "table_and_chairs", "bus_station"}          # the Overworld's two sets on the lot (#121): drawn in the parking lot, not scenes you go to
# a scene with no GLB of its own draws a kit piece placed at its origin (the mall's sky halls: #112)
KIT_GLB = {f"sky_hall_{k:02d}": "world/kit/sky_hall.glb" for k in range(1, 5)}
# the connector a pair names -> the manifest's connector (the manifest's list is extended with the new kinds)
CONNECTOR = {"door": "doors"}
# pairs that stay planned: under water, until swimming exists (the hotel's pools)
PLANNED = {"pool_route": "Under water: shut until swimming exists."}
# scenes that are not presence scenes (links touching them are soloOnly)
SOLO_SCENES = {"entrance", "main_floor", "laboratory", "galleries"}

# Blender scenes with no greybox builder: (area, scene, floorY, presence)
EXTRA_SCENES = [("museum", "galleries_wing", 0.0, False)]          # #81: the museum's side wing, off the hall's two doorways (a guard's shift is solo)

# the joins onto the older scenes: (id, from, to, connector, extra). `from.at` is the F spot on a scene whose world file has no links.
JOINS = [
    # the hotel: the apartment tower's door opens the lobby (the owner, 2026-11-28: "Lobby only"); the lobby's front doors lead back out
    ("city.tower>hotel_lobby", {"area": "city", "scene": "street", "door": "tower"}, ("hotel", "lobby", "street"), "doors", {}),
    ("hotel.lobby.street", {"area": "hotel", "scene": "lobby", "door": "street"}, {"area": "city", "scene": "street", "arrive": [-6.2, 0.0, -19.0], "face": [1.0, 0.0]}, "doors", {}),
    # your apartment is room 301 on hotel floor 3 (its door's room_layout is "apartment"); the apartment's door leads back to that corridor
    ("hotel.floor_3.room_301>apartment", {"area": "hotel", "scene": "floor_3", "door": "room_301", "at": [-16.0, 0.0, -0.6]},
     {"area": "city", "scene": "apartment", "arrive": [1.5, 0.0, 1.4], "face": [0.0, -1.0]}, "doors", {"note": "Your apartment: room 301."}),
    ("city.apartment>floor_3", {"area": "city", "scene": "apartment", "door": "front_door"},
     {"area": "hotel", "scene": "floor_3", "arrive": [-16.0, 0.0, -0.2], "face": [0.0, 1.0]}, "doors", {}),
    # the Overworld's road (#115): its north end walks into the forest, and the forest's signpost back walks to the road's forest end
    ("overworld.road.forest", ("overworld", "road", "forest"), {"area": "dreamcore_forest", "scene": "forest", "arrive": [0.0, 0.0, 6.0], "face": [0.0, -1.0]}, "walk", {}),
    ("forest.road>lot", {"area": "dreamcore_forest", "scene": "forest", "door": "road_back"}, ("overworld", "road", "forest"), "walk",
     {"note": "The forest's signpost back: the Overworld's road, at its forest end (the lot is at its other end)."}),
    # the mall: three wings and the food court open off the entrance (#110's README: entrance's side of each)
    ("mall.entrance.wing_books", {"area": "mall", "scene": "entrance", "door": "wing_books", "at": [0.0, 0.0, -11.3]}, ("mall", "wing_books", "entrance"), "doors", {}),
    ("mall.entrance.wing_cinema", {"area": "mall", "scene": "entrance", "door": "wing_cinema", "at": [-15.3, 0.0, -1.0]}, ("mall", "wing_cinema", "entrance"), "doors", {}),
    ("mall.entrance.wing_entertainment", {"area": "mall", "scene": "entrance", "door": "wing_entertainment", "at": [15.3, 0.0, -1.0]}, ("mall", "wing_entertainment", "entrance"), "doors", {}),
    ("mall.entrance.food_court", {"area": "mall", "scene": "entrance", "door": "food_court", "at": [4.0, 0.0, -11.3]}, ("mall", "food_court", "entrance"), "doors", {}),
    ("mall.wing_books.entrance", ("mall", "wing_books", "entrance"), {"area": "mall", "scene": "entrance", "arrive": [0.0, 0.0, -10.6], "face": [0.0, 1.0]}, "doors", {}),
    ("mall.wing_cinema.entrance", ("mall", "wing_cinema", "entrance"), {"area": "mall", "scene": "entrance", "arrive": [-14.6, 0.0, -1.0], "face": [1.0, 0.0]}, "doors", {}),
    ("mall.wing_entertainment.entrance", ("mall", "wing_entertainment", "entrance"), {"area": "mall", "scene": "entrance", "arrive": [14.6, 0.0, -1.0], "face": [-1.0, 0.0]}, "doors", {}),
    ("mall.food_court.entrance", ("mall", "food_court", "entrance"), {"area": "mall", "scene": "entrance", "arrive": [4.0, 0.0, -10.6], "face": [0.0, 1.0]}, "doors", {}),
    # the museum's side wing (#81): the hall's doorways at z -10, the natural-history hall to the west and the history gallery to the east
    ("museum.galleries.wing_w", {"area": "museum", "scene": "galleries", "door": "wing_w", "at": [-5.4, 0.0, -10.0]}, ("museum", "galleries_wing", "hall_w"), "doors", {}),
    ("museum.galleries.wing_e", {"area": "museum", "scene": "galleries", "door": "wing_e", "at": [5.4, 0.0, -10.0]}, ("museum", "galleries_wing", "hall_e"), "doors", {}),
    ("museum.galleries_wing.hall_w", ("museum", "galleries_wing", "hall_w"), {"area": "museum", "scene": "galleries", "arrive": [-5.2, 0.0, -10.0], "face": [1.0, 0.0]}, "doors", {}),
    ("museum.galleries_wing.hall_e", ("museum", "galleries_wing", "hall_e"), {"area": "museum", "scene": "galleries", "arrive": [5.2, 0.0, -10.0], "face": [-1.0, 0.0]}, "doors", {}),
    # the grocery: the aisles through the north wall's gap, the back of house through the staff doors (#108)
    ("grocery.main_floor.aisles", {"area": "grocery", "scene": "main_floor", "door": "aisles", "at": [0.0, 0.0, -8.3]}, ("grocery", "aisles", "main_floor"), "doors", {}),
    ("grocery.main_floor.back_of_house", {"area": "grocery", "scene": "main_floor", "door": "back_of_house", "at": [11.4, 0.0, -5.5]}, ("grocery", "back_of_house", "main_floor"), "doors", {}),
    ("grocery.aisles.main_floor", ("grocery", "aisles", "main_floor"), {"area": "grocery", "scene": "main_floor", "arrive": [0.0, 0.0, -7.8], "face": [0.0, 1.0]}, "doors", {}),
    ("grocery.back_of_house.main_floor", ("grocery", "back_of_house", "main_floor"), {"area": "grocery", "scene": "main_floor", "arrive": [10.7, 0.0, -5.5], "face": [-1.0, 0.0]}, "doors", {}),
    # Secret Operations: open for now (the owner, 2026-11-28: "Open for now"; a keycard can be added later): the grocery's freight lift and the lab's B2 door
    ("grocery.back_of_house.secret_ops", ("grocery", "back_of_house", "secret_ops"), ("secret_ops", "service_entry", "freight_lift"), "service_corridor", {}),
    ("secret_ops.service_entry.freight_lift", ("secret_ops", "service_entry", "freight_lift"), ("grocery", "back_of_house", "secret_ops"), "service_corridor", {}),
    ("lab.laboratory.b2", {"area": "lab", "scene": "laboratory", "door": "b2", "at": [0.0, 0.0, -5.4]}, ("secret_ops", "b2_entry", "laboratory"), "doors", {}),
    ("secret_ops.b2_entry.laboratory", ("secret_ops", "b2_entry", "laboratory"), {"area": "lab", "scene": "laboratory", "arrive": [0.0, 0.0, -4.6], "face": [0.0, 1.0]}, "doors", {}),
]


def builder(name):
    return __import__(f"build_{name}_greybox")


def world(scene):
    p = ROOT / f"world/{scene}.json"
    return json.loads(p.read_text()) if p.exists() else None


def link_of(scene, door):
    w = world(scene)
    for l in (w or {}).get("links", []):
        if l["door"] == door:
            return l
    return None


def num(v):
    return round(float(v), 3) + 0.0


def collect():
    scenes, links, area_of, problems = {}, [], {}, []
    for mod, area in AREAS:
        b = builder(mod)
        out = []
        for sid in b.SCENES:
            if sid in NOT_SCENES:
                continue
            area_of[sid] = area
            if sid in HAND_SCENES or world(sid) is None:
                if world(sid) is None:
                    problems.append(f"{area}: {sid} has no world/{sid}.json")
                continue
            S = b.SCENES[sid]()
            files = [f for f in (f"world/{sid}.glb",) if (ROOT / f).exists()] or ([KIT_GLB[sid]] if sid in KIT_GLB else [])
            if not files:
                problems.append(f"{area}: {sid} has no GLB")
            out.append({"id": sid, "floorY": num(S.levels[0]), "files": files + [f"world/{sid}.json"], "presence": True})
        scenes[area] = out
        for p in b.PAIRS:
            (a, da), (bb, db), conn, note = p[0], p[1], p[2], (p[3] if len(p) > 3 and isinstance(p[3], str) else "")
            ends = [(a, da, bb, db)] + ([] if conn == "one_way" else [(bb, db, a, da)])
            for s0, d0, s1, d1 in ends:
                if s0 in NOT_SCENES or s1 in NOT_SCENES:
                    continue
                arr = link_of(s1, d1)
                if link_of(s0, d0) is None or arr is None:
                    problems.append(f"{area}: pair {s0}.{d0} > {s1}.{d1}: a side has no link in its world file")
                    continue
                l = {"id": f"{area}.{s0}.{d0}", "status": "planned" if conn in PLANNED else "built", "connector": CONNECTOR.get(conn, conn),
                     "from": {"area": area, "scene": s0, "door": d0}, "to": {"area": area, "scene": s1, "arrive": [num(v) for v in arr["arrive"]], "face": [num(v) for v in arr["face"]]}}
                if conn in PLANNED:
                    l["note"] = PLANNED[conn]
                elif note:
                    l["note"] = note
                links.append(l)
    for area, sid, fy, pres in EXTRA_SCENES:
        scenes.setdefault(area, []).append({"id": sid, "floorY": fy, "files": [f"world/{sid}.glb", f"world/{sid}.json"], **({"presence": True} if pres else {})})
        if not pres:
            SOLO_SCENES.add(sid)
    for lid, fr, to, conn, extra in JOINS:
        if isinstance(fr, tuple):
            fr = {"area": fr[0], "scene": fr[1], "door": fr[2]}
        if isinstance(to, tuple):
            arr = link_of(to[1], to[2])
            if arr is None:
                problems.append(f"join {lid}: {to[1]} has no link {to[2]}")
                continue
            to = {"area": to[0], "scene": to[1], "arrive": [num(v) for v in arr["arrive"]], "face": [num(v) for v in arr["face"]]}
        if fr.get("scene") and world(fr["scene"]) and not fr.get("at") and link_of(fr["scene"], fr["door"]) is None and fr["scene"] not in ("street", "apartment", "forest", "meadow"):
            problems.append(f"join {lid}: {fr['scene']} has no link {fr['door']}")
        l = {"id": lid, "status": "built", "connector": conn, "from": fr, "to": to, **extra}
        links.append(l)
    for l in links:
        if l["from"].get("scene") in SOLO_SCENES or l["to"].get("scene") in SOLO_SCENES:
            l["soloOnly"] = True
    ids = [l["id"] for l in links]
    for d in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"duplicate link id {d}")
    return scenes, links, problems


def render(scenes, links):
    j = lambda v: json.dumps(v, separators=(", ", ": ")).replace('"area": ', "area: ").replace('"scene": ', "scene: ").replace('"door": ', "door: ") \
        .replace('"arrive": ', "arrive: ").replace('"face": ', "face: ").replace('"at": ', "at: ").replace('"id": ', "id: ").replace('"status": ', "status: ") \
        .replace('"connector": ', "connector: ").replace('"from": ', "from: ").replace('"to": ', "to: ").replace('"note": ', "note: ").replace('"soloOnly": ', "soloOnly: ") \
        .replace('"floorY": ', "floorY: ").replace('"files": ', "files: ").replace('"presence": ', "presence: ")
    lines = ["// Made by tools/blender/wire_scenes.py from the Blender areas' greybox builders (their SCENES and PAIRS) and world/<scene>.json. Do not edit:",
             "// change the builder or JOINS in that script and run it (`--check` tells whether this file is current). shared/farway.manifest.js uses it.", "",
             "export const BLENDER_SCENES = {"]
    for area, ss in scenes.items():
        lines.append(f"  {area}: [")
        lines += [f"    {j(s)}," for s in ss]
        lines.append("  ],")
    lines += ["};", "", "export const BLENDER_LINKS = ["]
    lines += [f"  {j(l)}," for l in links]
    lines += ["];", ""]
    return "\n".join(lines)


def main(argv):
    scenes, links, problems = collect()
    for p in problems:
        print("note: " + p)
    text = render(scenes, links)
    if "--check" in argv:
        ok = OUT.exists() and OUT.read_text() == text
        print("farway.scenes.js is current" if ok else "farway.scenes.js is out of date: run tools/blender/wire_scenes.py")
        return 0 if ok else 1
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)}: {sum(len(v) for v in scenes.values())} scenes, {len(links)} links ({sum(l['status'] == 'built' for l in links)} built)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
