// The world manifest for Farway: the one place that says which scenes, floors, puzzles, links and modes exist. Edit this file to add a scene or a link; the
// loader (shared/manifest.js) checks it when the game or the server starts, and `node tools/manifest.mjs check` also checks it against world/*.json.
// Status: "built" is in the game now; "planned" is designed but not built; "reserved" holds a place for an addon. Only built things reach the game.
// See docs/MANIFEST.md.

// the stair doors between floors: copied from the "link" in world/<scene>.json (tools/manifest.mjs check fails if they drift)
const stair = (scene, door, to, toDoor, arrive, face) => ({
  id: `lot.${scene}.${door}`, status: "built", connector: "stair_door",
  from: {area: "lot", scene, door}, to: {area: "lot", scene: to, door: toDoor, arrive, face},
});
// a door that opens one of the two games. A room can enter Right Door, Wrong Exit (coop, session 11); the Intern is still solo only.
const gate = (door, game, to, returnScene, soloOnly = true) => ({
  id: `lot.L4.${door}`, status: "built", connector: "gate", soloOnly,
  from: {area: "lot", scene: "L4", door}, to: {area: game, ...to}, returnTo: {area: "lot", scene: returnScene},
});
import {BLENDER_SCENES, BLENDER_LINKS} from "./farway.scenes.js";      // the Blender areas' scenes and links, made by tools/blender/wire_scenes.py

const plan = (id, from, to, connector, extra = {}) => ({id, status: "planned", connector, from, to, ...extra});
const stub = (id, name, status, scenes) => ({id, name, status, scenes: scenes.map(s => ({id: s}))});

export const FARWAY = {
  manifestVersion: 1,
  world: "Farway",
  flags: ["original_complete", "job_intern", "job_trash", "job_museum", "job_lab", "job_factory", "keycard_tier_1", "keycard_tier_2", "admin_access"],
  connectors: ["stair_door", "gate", "doors", "walk", "elevator", "stairs", "bus", "pool_dive", "pool_route", "service_corridor", "one_way", "escalator", "freight_lift", "mirror", "service", "sky_hall"],

  // a mode is a way to play a round; `players.max` is the room size the server enforces
  modes: {
    original: {
      status: "built", area: "lot", floors: ["B1", "L1", "L2", "L3", "L4"], startScene: "B1", players: {min: 1, max: 10},
      finish: {scene: "L4", trigger: "parking_lot", alarmMs: 60000}, results: ["place", "time", "bestOnBrowser"],
    },
    going_back_in: {
      // built (session 16): a room runs it on the server, starting everyone in `startChamber`; its scenes are the chambers of the `gbi` area, not `floors` (those say which storeys the run
      // goes down). Solo play still enters it from the Overworld's options screen (session 8). No finish yet: the run has no end until all 20 chambers exist.
      status: "built", area: "lot", floors: ["L4", "L3", "L2", "L1", "B1"], players: {min: 1, max: 10}, chambersPerFloor: 4, waves: 20, startChamber: "gbi_L4_4",
    },
  },

  areas: [
    {
      id: "lot", name: "Look Over There", status: "built", tone: "backrooms",
      scenes: [
        {id: "B1", floorY: -3.0, files: ["world/B1.glb", "world/B1.json"], multiplayer: true, puzzle: "fuses", loot: {lockers: 8, packs: 6}},
        {id: "L1", floorY: 0, files: ["world/L1.glb", "world/L1.json"], multiplayer: true, puzzle: "switches", loot: {lockers: 0, packs: 3}},
        {id: "L2", floorY: 3.2, files: ["world/L2.glb", "world/L2.json"], multiplayer: true, puzzle: "keypad", loot: {lockers: 0, packs: 3}},
        {id: "L3", floorY: 6.4, files: ["world/L3.glb", "world/L3.json"], multiplayer: true, powerSource: true, loot: {lockers: 0, packs: 4}},
        {id: "L4", floorY: 9.6, files: ["world/L4.glb", "world/parking_lot.glb", "world/city_skyline.glb", "world/Exterior.glb", "world/L4.json"], multiplayer: true, powerSource: true, loot: {lockers: 0, packs: 3}},
      ],
    },
    {id: "rdwe", name: "Right Door, Wrong Exit", status: "built", coop: true, tone: "dreamcore", rooms: ["dining", "hallway", "teal", "teal2", "flooded", "trampoline", "grocery"]},
    {id: "intern", name: "The Intern", status: "built", soloOnly: true, tone: "liminal", spine: ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8"]},
    {
      // v0 is one scene: the parking lot with the table and chairs as the spawn, the store doors, and one sky mode. The other scenes are designed, not built (they have no files).
      id: "overworld", name: "Overworld", status: "built", tone: "dreamcore",
      scenes: [
        // presence (session 17): a room's players can be in the lot together. The server relays who is there and where; it runs nothing.
        // #133: the lot is the Overworld's own scene: the store's art (L4.glb), the lot (parking_lot.glb) and the town on the horizon (city_skyline.glb), under the Overworld's sky
        {id: "parking_lot", floorY: 9.6, files: ["world/L4.glb", "world/parking_lot.glb", "world/city_skyline.glb", "world/parking_lot.json"], presence: true,
         backdrop: {day: "world/backdrops/overworld_clear_day.webp", night: "world/backdrops/overworld_night.webp"}},
        ...BLENDER_SCENES.overworld,          // the Blender Overworld (#115 to #122): the market, the playground, the courts and the track, the tree house, the road, the hills
      ],
    },
    {
      // Going back in, slice 1: two chambers made from existing floors (tools/make_chambers.mjs writes their world files). `chamber.floor` and `index` place it in the run (wave number =
      // floor position x chambersPerFloor + index); the 4th chamber of a floor has the stairs down, to the next floor's first. `multiplayer`: a going_back_in room's server runs them as floors (session 16).
      // Which chamber the existing floor is (docs/ROUND.md, GBI-1): on L4 it is the 4th (it has the real stairs down); on L3, L2, L1 and B1 it is the 1st (the stairs from the floor
      // above arrive in its real stairwell). So the 15 new chambers are L4's 1 to 3 and 2 to 4 of the other four floors; the 4th of L3, L2 and L1 gets a stair door of its own, and
      // B1's 4th is wave 20, the run's end, with no stairs.
      id: "gbi", name: "Going back in", status: "built", tone: "backrooms",
      scenes: [
        {id: "gbi_L4_4", floorY: 9.6, multiplayer: true, files: ["world/L4.glb", "world/parking_lot.glb", "world/city_skyline.glb", "world/Exterior.glb", "world/gbi_L4_4.json"], loot: {lockers: 0, packs: 3}, chamber: {floor: "L4", index: 4, wave: {monsters: 3, kind: "creature"}, stairsDown: "DoorLeaf_Stair_L3_L4_down", next: "gbi_L3_1"}},
        {id: "gbi_L3_1", floorY: 6.4, multiplayer: true, files: ["world/L3.glb", "world/gbi_L3_1.json"], loot: {lockers: 0, packs: 3}, chamber: {floor: "L3", index: 1, wave: {monsters: 3, kind: "creature"}}},
      ],
    },
    {
      // the dreamcore forest and meadow (shared/forest.js): the road from the parking lot, a path north through the trees, then the meadow with the shed and the house.
      // Both are presence scenes: a room's players see each other walk there. The house's door is Right Door, Wrong Exit (solo only); the shed is locked until its addon.
      id: "dreamcore_forest", name: "Dreamcore forest and meadow", status: "built", tone: "dreamcore",
      scenes: [{id: "forest", floorY: 0, files: ["world/forest.glb", "world/forest.json"], presence: true}, {id: "meadow", floorY: 0, files: ["world/meadow.glb", "world/meadow.json"], presence: true}],
    },
    {
      // v0 (session 9): Hallam Row as a blockout street, reached by the bus. Its layout and the day clock are in shared/city.js; world/street.json is made from it by tools/make_street.mjs.
      id: "city", name: "City", status: "built", tone: "liminal",
      // presence (session 17): a room's players see each other on the street and in the apartment. Nothing else is shared: each player's clock, needs, money, jobs and night are their own.
      scenes: [{id: "street", floorY: 0, files: ["world/street.glb", "world/street.json"], presence: true}, {id: "apartment", floorY: 0, files: ["world/apartment.glb", "world/apartment.json"], presence: true}, {id: "bus_stop"}],
    },
    // the hotel (the apartment tower, #93 to #107): the lobby behind the tower's door on Hallam Row, the atrium, three floors, the roof, the pools and the maze
    {id: "hotel", name: "Strange hotel (apartment tower)", status: "built", tone: "liminal", scenes: BLENDER_SCENES.hotel},
    {
      // slice 13 (session 9): the mall's atrium, a blockout behind the street's MALL door. Open to go in by day; at 20:00 it locks you in until dawn.
      id: "mall", name: "Liminal mall", status: "built", tone: "liminal",
      scenes: [{id: "entrance", floorY: 0, files: ["world/entrance.glb", "world/entrance.json"]}, ...BLENDER_SCENES.mall],          // #110 to #116: the wings and the rooms round the atrium
    },
    {
      // slice 4 (session 9): the grocery's main floor, a blockout behind the street's grocery door; open by day like the other stores. The back of house stays planned.
      id: "grocery", name: "Grocery", status: "built", tone: "liminal",
      scenes: [{id: "main_floor", floorY: 0, files: ["world/main_floor.glb", "world/main_floor.json"]}, ...BLENDER_SCENES.grocery],          // #108 to #111: the aisles, the second floor, the back of house, the basement
    },
    {
      // slice 14 (session 9): the museum night guard's shift, behind 108 Hallam Row. One gallery hall, blockout; you are only in it during your shift.
      id: "museum", name: "Museum (108 Hallam Row)", status: "built", tone: "liminal",
      scenes: [{id: "galleries", floorY: 0, files: ["world/galleries.glb", "world/galleries.json"]}],
    },
    {
      // slice 16 (session 9): the factory floor worker's shift, behind 330 Hallam Row. One hall with a conveyor belt, blockout; you are only in it during your shift.
      id: "factory", name: "Factory (330 Hallam Row)", status: "built", tone: "liminal",
      scenes: [{id: "factory_floor", floorY: 0, files: ["world/factory_floor.glb", "world/factory_floor.json"]}],
    },
    {
      // slice 17 (session 9): the laboratory worker's shift, behind 214 Hallam Row. One room of stations, blockout, with a sealed door marked B2 (Secret Operations is planned).
      id: "lab", name: "Laboratory (214 Hallam Row)", status: "built", tone: "liminal",
      scenes: [{id: "laboratory", floorY: 0, files: ["world/laboratory.glb", "world/laboratory.json"]}],
    },
    stub("jobs", "Hallam Row (street of jobs)", "planned", ["street_of_jobs"]),
    // #125 and #127: thirteen scenes. Open for now (the owner, 2026-11-28): the lab's B2 door and the grocery's freight lift need no keycard yet
    {id: "secret_ops", name: "Secret Operations (Project Never Land)", status: "built", tone: "liminal", scenes: BLENDER_SCENES.secret_ops},
    {id: "future_addon_shed", name: "Reserved for the shed", status: "reserved"},
    {id: "future_addon_treehouse", name: "Reserved for the tree house", status: "reserved"},
  ],

  links: [
    // ---- built: the stairs and the two game gates (arrive and face are what goLink hands to loadScene)
    stair("B1", "DoorLeaf_Stair_B1_L1_up", "L1", "DoorLeaf_Stair_B1_L1_down", [0.009, 0.0, -0.799], [0.0, 1.0]),
    stair("L1", "DoorLeaf_Stair_B1_L1_down", "B1", "DoorLeaf_Stair_B1_L1_up", [0.009, 0.0, -1.599], [0.0, -1.0]),
    stair("L1", "DoorLeaf_Stair_L1_L2_up", "L2", "DoorLeaf_Stair_L1_L2_down", [-0.007, 3.2, 10.508], [0.0, 1.0]),
    stair("L2", "DoorLeaf_Stair_L1_L2_down", "L1", "DoorLeaf_Stair_L1_L2_up", [-0.007, 3.2, 9.708], [0.0, -1.0]),
    stair("L2", "DoorLeaf_Stair_L2_L3_up", "L3", "DoorLeaf_Stair_L2_L3_down", [-16.478, 6.4, -15.078], [0.0, -1.0]),
    stair("L3", "DoorLeaf_Stair_L2_L3_down", "L2", "DoorLeaf_Stair_L2_L3_up", [-16.478, 6.4, -14.278], [0.0, 1.0]),
    stair("L3", "DoorLeaf_Stair_L3_L4_up", "L4", "DoorLeaf_Stair_L3_L4_down", [16.0, 9.6, 7.2], [0.0, -1.0]),
    stair("L4", "DoorLeaf_Stair_L3_L4_down", "L3", "DoorLeaf_Stair_L3_L4_up", [16.0, 9.6, 8.0], [0.0, 1.0]),
    gate("DoorLeaf_Gate_ITN", "intern", {arrive: [116.4, 9.6, 75.0], face: [1.0, 0.0]}, "L4"),

    // Going back in: the stairs down from the 4th chamber of L4 to the first chamber of L3. One way (the chamber's own `up` door has no link). Arrival is on L3's floor (6.4).
    {id: "gbi.gbi_L4_4.stairs_down", status: "built", connector: "stair_door",
     from: {area: "gbi", scene: "gbi_L4_4", door: "DoorLeaf_Stair_L3_L4_down"}, to: {area: "gbi", scene: "gbi_L3_1", door: "DoorLeaf_Stair_L3_L4_up", arrive: [16.0, 6.4, 8.0], face: [0.0, 1.0]}},

    // ---- planned: from the world bible. None of these reach the game until their area is built.
    // walking out of the store after the Original: the results screen offers it once the flag is held. Not a door in world/L4.json (the glass doors are open once the power is on).
    // A room can follow it too (session 17): the lot is a presence scene, and each player still needs the flag.
    {id: "lot.L4.front_doors>overworld", status: "built", connector: "doors", requires: ["original_complete"],
     from: {area: "lot", scene: "L4", door: "front_doors"}, to: {area: "overworld", scene: "parking_lot", arrive: [-8.0, 9.6, 43.6], face: [0.0, -1.0]},
     note: "You arrive at the table and chairs in the parking lot, facing the store."},
    plan("overworld.store_doors>lot", {area: "overworld", scene: "parking_lot", door: "store_doors"}, {area: "lot"}, "doors", {requires: ["original_complete"], note: "Options screen: Original or Going back in."}),
    // the bus: a stop in the parking lot (a shelter beside the lot's own bus stop post) takes you to Hallam Row, and the stop on the street brings you back. A room can ride it (session 17): both ends are presence scenes.
    {id: "overworld.bus>city", status: "built", connector: "bus", from: {area: "overworld", scene: "parking_lot", door: "bus_stop"}, to: {area: "city", scene: "street", arrive: [3.6, 0.0, 4.0], face: [0.0, -1.0]},
     note: "Just a ride. You arrive on the east sidewalk of Hallam Row, facing up the street."},
    {id: "city.bus>overworld", status: "built", connector: "bus", from: {area: "city", scene: "street", door: "bus_stop"}, to: {area: "overworld", scene: "parking_lot", arrive: [-41.0, 9.6, 43.0], face: [0.0, -1.0]},
     note: "The ride back. The City's clock pauses while you are away."},
    // slice 2 had the apartment tower's door open straight into your apartment. Since the hotel (2026-11-28, the owner: "Lobby only") it opens the hotel's lobby, and your apartment is
    // room 301 on floor 3: city.tower>hotel_lobby, hotel.lobby.street, hotel.floor_3.room_301>apartment and city.apartment>floor_3 are in farway.scenes.js. A room can use them all.
    // slice 3: once the Intern's application is accepted (the quiz in shared/application.js; the flag is kept in the browser), 666 Hallam Row's door starts your shift: the Intern game, solo only.
    // returnTo carries where you stand when you come back out. Open store hours still apply (the street's doors shut at 20:00).
    {id: "city.666>intern", status: "built", connector: "doors", soloOnly: true, requires: ["job_intern"], from: {area: "city", scene: "street", door: "w666"}, to: {area: "intern"},
     returnTo: {area: "city", scene: "street", arrive: [-6.2, 0.0, -127.0], face: [1.0, 0.0]}, note: "A shift at The Intern. Needs the accepted application."},
    // the road to the forest: the lot's signpost walks you onto the Overworld's road (#115), whose far end walks into the forest; the forest's signpost back walks you to the road's forest end.
    // Those three links are in farway.scenes.js (overworld.parking_lot.forest_road, overworld.road.forest, forest.road>lot).
    // the forest's path ends in a bright gap: walking through it is the way into the meadow, and walking back out of the meadow's south edge is the way back
    {id: "forest.gap>meadow", status: "built", connector: "walk", from: {area: "dreamcore_forest", scene: "forest", door: "gap"}, to: {area: "dreamcore_forest", scene: "meadow", arrive: [0.0, 0.0, 6.0], face: [0.0, -1.0]}},
    {id: "meadow.gap>forest", status: "built", connector: "walk", from: {area: "dreamcore_forest", scene: "meadow", door: "gap"}, to: {area: "dreamcore_forest", scene: "forest", arrive: [0.0, 0.0, -86.0], face: [0.0, 1.0]}},
    // the house's front door: Right Door, Wrong Exit. Since #133 it is the only way in (the balloon house and its gate on L4's lot are gone), and a room can follow it
    // (the owner, 2026-11-27: "the co-op entrance to RDWE is the meadow house as well"). You come back out on the path in front of the house.
    {id: "forest.house>rdwe", status: "built", connector: "doors", from: {area: "dreamcore_forest", scene: "meadow", door: "house_door"}, to: {area: "rdwe", room: "dining"},
     returnTo: {area: "dreamcore_forest", scene: "meadow", arrive: [0.0, 0.0, -57.5], face: [0.0, 1.0]}, note: "The house is much bigger inside."},
    plan("forest.shed>addon", {area: "dreamcore_forest", scene: "meadow", door: "shed"}, {area: "future_addon_shed"}, "gate", {note: "Leads to its own addon later. Also a puzzle."}),
    plan("overworld.treehouse>addon", {area: "overworld", scene: "tree_house", door: "addon"}, {area: "future_addon_treehouse"}, "gate", {note: "Leads to its own addon later. Also a puzzle."}),
    plan("hotel.sub_pools>lot.B1", {area: "hotel", scene: "sub_pool_11", door: "under_b1"}, {area: "lot", scene: "B1"}, "pool_route", {note: "Separate pools connected underwater, a long way with many levels between."}),
    // slice 13: the street's MALL door and back. In by day (08:00 to 20:00); at 20:00 the doors lock until 06:00 with you inside; solo only.
    {id: "city.street>mall", status: "built", connector: "doors", soloOnly: true, from: {area: "city", scene: "street", door: "mall"}, to: {area: "mall", scene: "entrance", arrive: [0.0, 0.0, 10.4], face: [0.0, -1.0]},
     note: "The mall can lock you in."},
    {id: "mall.entrance>street", status: "built", connector: "doors", soloOnly: true, from: {area: "mall", scene: "entrance", door: "front_door"}, to: {area: "city", scene: "street", arrive: [6.2, 0.0, -67.0], face: [-1.0, 0.0]}},
    // slice 4: the street's grocery door and back. Open 08:00 to 20:00 (at closing you are shown out); solo only.
    {id: "city.street>grocery", status: "built", connector: "doors", soloOnly: true, from: {area: "city", scene: "street", door: "grocery"}, to: {area: "grocery", scene: "main_floor", arrive: [0.0, 0.0, 7.4], face: [0.0, -1.0]},
     note: "Open by day, abandoned by night."},
    {id: "grocery.main_floor>street", status: "built", connector: "doors", soloOnly: true, from: {area: "grocery", scene: "main_floor", door: "front_door"}, to: {area: "city", scene: "street", arrive: [6.2, 0.0, -17.0], face: [-1.0, 0.0]}},
    plan("city.street>jobs", {area: "city", scene: "street"}, {area: "jobs", scene: "street_of_jobs"}, "doors"),
    // slice 14: 108's door starts the museum guard's shift (20:00 to 21:00, the page checks the hours) and the hall's door ends it, back by 108; solo only.
    {id: "city.e108>museum", status: "built", connector: "doors", soloOnly: true, requires: ["job_museum"], from: {area: "city", scene: "street", door: "e108"}, to: {area: "museum", scene: "galleries", arrive: [0.0, 0.0, 4.4], face: [0.0, -1.0]},
     note: "Everything comes alive at night."},
    // slice 16: 330's door starts the factory shift (08:00 to 16:00, the page checks the hours) and the hall's door ends it, back by 330; solo only.
    {id: "city.e330>factory", status: "built", connector: "doors", soloOnly: true, requires: ["job_factory"], from: {area: "city", scene: "street", door: "e330"}, to: {area: "factory", scene: "factory_floor", arrive: [0.0, 0.0, 5.4], face: [0.0, -1.0]}},
    {id: "factory.factory_floor>street", status: "built", connector: "doors", soloOnly: true, from: {area: "factory", scene: "factory_floor", door: "front_door"}, to: {area: "city", scene: "street", arrive: [6.2, 0.0, -95.0], face: [-1.0, 0.0]}},
    // slice 17: 214's door starts the lab shift (08:00 to 16:00, the page checks the hours) and the room's door ends it, back by 214; solo only.
    {id: "city.w214>lab", status: "built", connector: "doors", soloOnly: true, requires: ["job_lab"], from: {area: "city", scene: "street", door: "w214"}, to: {area: "lab", scene: "laboratory", arrive: [0.0, 0.0, 4.4], face: [0.0, -1.0]}},
    {id: "lab.laboratory>street", status: "built", connector: "doors", soloOnly: true, from: {area: "lab", scene: "laboratory", door: "front_door"}, to: {area: "city", scene: "street", arrive: [-6.2, 0.0, -95.0], face: [1.0, 0.0]}},
    {id: "museum.galleries>street", status: "built", connector: "doors", soloOnly: true, from: {area: "museum", scene: "galleries", door: "front_door"}, to: {area: "city", scene: "street", arrive: [6.2, 0.0, -41.0], face: [-1.0, 0.0]}},
    plan("rdwe.repeating_room>secret_ops", {area: "rdwe", room: "repeating_room"}, {area: "secret_ops", scene: "hidden_entry"}, "gate", {note: "The only entrance with no clearance. Hinted by a room that repeats or a door seen from one angle."}),
    plan("intern.pool_dive>secret_ops", {area: "intern", room: "S8_H"}, {area: "secret_ops", scene: "service_entry"}, "pool_dive", {note: "The Intern's escape."}),
    plan("rdwe.finale>grocery", {area: "rdwe", room: "grocery"}, {area: "grocery", scene: "main_floor"}, "doors", {note: "One ending, many exits."}),
    ...BLENDER_LINKS,
  ],
};
