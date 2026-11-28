# Secret Operations greybox (docs/BLENDER_AREAS.md, section 8: Secret Operations, Project Never Land)

Plain grey boxes, to scale, for the unique scenes of Secret Operations: the three entries, the three keycard checkpoints, two corridor sections and two lab sections (open-ended, more than one route each), the breaker room, the control room with its cell, and the Registrar's hall, the boss arena. There are no reference photos, so each scene is built from docs/WORLD.md's description. The reskinned Going back in chambers that the base also uses are not here: they are the Going back in greybox's. This is for review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.

- Built by `tools/blender/build_secretops_greybox.py` (the method of the Overworld's greybox build: one model in plain Python, a Blender run that writes `world/<scene>.json` through `tools/blender/export_scene.py`, the GLB, the plan and the still). The labels and these sheets come from `tools/blender/secretops_greybox_sheets.py`.
- `python tools/blender/build_secretops_greybox.py --check .` runs the gates on the exported files: every link has its other side and every scene is reached from each entry; no two colliders overlap; corridors and aisles are at least 1.6 m wide and clear, doorways 1 m, ceilings 2.8 to 3.2 m (the dock and the arena are tall on purpose), steps 0.27 m at most; every link, arrival and spot stands on floor a walker can reach, all on one piece; the open-ended sections have at least three links and a loop; the required objects are there; the arena's floor panels tile the field exactly; every restricted scene has cameras and every camera a breaker; agents spawn away from where you arrive, and every scene with agents has cover and ammo. `--against <preview dir>` also compares the Blender export with the model's preview, to the millimetre.
- `CHECKS.txt`: those gates, `node tools/worlddoc.mjs check` on every file (0 errors; the warnings say a scene or a link is new to the manifest), `node --test shared/*.test.js` and the privacy grep.
- `overview.png`: how the scenes join each other and the rest of Farway, with the keycard each door asks for. For each scene, `<scene>_plan.jpg` (top-down, scale bar, labels, doors, links, keycards, cameras and their sweep, agents and their beats, cover, ammo, loot, breakers) and `<scene>_still.jpg` (eye height, 1.55 m).

## Scenes

| Scene | Size | Links (door: where it goes) | Colliders, doors, cameras, spots | Mood |
|---|---|---|---|---|
| `service_entry` | 40.4 m by 16.4 m: a freight lift, a dock hall 4 m high, a pool room and a guard office | `freight_lift`: grocery back_of_house; `pool_dive`: the Intern (S8_H); `checkpoint_1`: checkpoint_1 | 50 colliders, 2 doors, 4 cameras; spots: agent x1, ammo x2, filed x1, loot x1, patrol x4 | back of house, cold strip lights |
| `hidden_entry` | 19.4 m by 19.4 m: a closet, a dog-leg maintenance passage and a storeroom; no cameras | `repeating_room`: rdwe repeating_room; `corridors_a`: corridors_a | 28 colliders, 2 doors, 0 cameras; spots: ammo x1, loot x2 | dusty, forgotten, unwatched |
| `b2_entry` | 34.4 m by 14.4 m: an airlock, a staff locker room, a sterile corridor and a scan room | `laboratory`: lab laboratory (the B2 door); `checkpoint_1`: checkpoint_1 | 36 colliders, 3 doors, 3 cameras; spots: agent x1, ammo x1, filed x1, locker x1, loot x1, patrol x4 | clinical, humming |
| `checkpoint_1` | 24.4 m by 22.4 m: an outer hall the two keyed entries open into, two scanner lanes, a guard booth with a window, an inner hall and the tier-1 door | `service_entry`: service_entry; `b2_entry`: b2_entry; `corridors_a`: corridors_a (card 1) | 36 colliders, 4 doors, 4 cameras; spots: agent x2, ammo x2, filed x1, loot x1, patrol x4, reader x1 | security, flat white light |
| `corridors_a` | 41.2 m by 29.2 m: a ring of 2.4 m corridors round two blocks, a spine through the middle with an atrium, corner bays, an office and a store | `checkpoint_1`: checkpoint_1; `hidden_entry`: hidden_entry; `breaker_room`: breaker_room; `labs_a_west`: labs_a; `labs_a_east`: labs_a; `checkpoint_2`: checkpoint_2 | 100 colliders, 8 doors, 6 cameras; spots: agent x3, ammo x2, filed x1, loot x1, patrol x4 | institutional, endless doors |
| `labs_a` | 32.4 m by 21.2 m: a south hall, two labs with benches and fume hoods, a spine with windows into both, a north hall and the tier-2 door to Labs B | `corridors_a_west`: corridors_a; `corridors_a_east`: corridors_a; `labs_b`: labs_b (card 2) | 66 colliders, 3 doors, 4 cameras; spots: agent x2, ammo x2, filed x1, loot x2, patrol x2, reader x1 | clinical, too clean |
| `breaker_room` | 28.2 m by 16.4 m: a plant room with three breaker panels (circuits A, B and C), two transformers and two ways in | `corridors_a`: corridors_a; `corridors_b`: corridors_b (card 2) | 25 colliders, 2 doors, 1 cameras; spots: agent x1, ammo x1, breaker x3, filed x1, loot x1, reader x1 | loud, hot, orange |
| `checkpoint_2` | 30.4 m by 26.4 m: an antechamber, a screening hall with a chicane of barriers, a guard booth with a window and the tier-2 vestibule | `corridors_a`: corridors_a; `corridors_b`: corridors_b (card 2) | 41 colliders, 3 doors, 4 cameras; spots: agent x2, ammo x1, filed x1, loot x1, patrol x4, reader x1 | security, harder |
| `corridors_b` | 44.4 m by 21.2 m: two long corridors joined by three cross corridors, the middle one through a server closet | `checkpoint_2`: checkpoint_2; `labs_b_west`: labs_b; `labs_b_east`: labs_b; `breaker_room`: breaker_room (card 2); `checkpoint_3`: checkpoint_3 | 86 colliders, 5 doors, 5 cameras; spots: agent x3, ammo x2, filed x1, loot x1, patrol x4, reader x1 | institutional, the hum louder |
| `labs_b` | 36.4 m by 26.8 m: one big lab hall with glass test cubicles, a south hall, a specimen room and the tier-2 door back to Labs A | `corridors_b_west`: corridors_b; `corridors_b_east`: corridors_b; `labs_a`: labs_a (card 2) | 35 colliders, 4 doors, 4 cameras; spots: agent x3, ammo x2, filed x1, loot x2, patrol x2, reader x1 | clinical, something kept here |
| `checkpoint_3` | 30.4 m by 26.4 m: an approach, a decontamination tunnel between two doors, a vault with twin guard booths and the tier-3 door to the Registrar | `corridors_b`: corridors_b; `registrar_hall`: registrar_hall (card 3) | 49 colliders, 6 doors, 4 cameras; spots: agent x3, ammo x1, filed x1, loot x1, reader x1 | security, final, cold |
| `registrar_hall` | 47.4 m by 20.4 m, 7 m high: a long green server hall with a pink stripe on the walls, 48 racks in four rows over a field of 200 floor panels, fixed landings at both ends, the control room's front and the cell at the east end, 12 cameras round every wall | `checkpoint_3`: checkpoint_3; `control_room`: control_room | 317 colliders, 2 doors, 12 cameras; spots: agent x6, ammo x4, breaker x4, core x1, loot x1 | green, humming, watched |
| `control_room` | 20.4 m by 10.4 m: an antechamber from the arena, the control room with its single chair facing a wall of monitors, and the cell beside it, a puzzle room you solve to leave | `registrar_hall`: registrar_hall | 33 colliders, 2 doors, 3 cameras; spots: admin x1, agent x1, ammo x1, breaker x1, chair x1, filed x1, loot x1, puzzle x3 | dim, the monitors' glow, watched |

## The graph

Each pair is one link. Pressing F at one side's `Link_<door>` puts you at the other side's `Arrive_<door>`, facing its -Y axis. Every pair has both sides built (the gate checks it). The card is the keycard tier the door's reader asks for (its `keycard_tier` property and a `Spot_reader` beside it); 0 is none. A reader is on the side you come from going deeper; coming back the door opens from inside.

```
grocery freight lift --+
Intern pool dive ------+--> service_entry --+
lab B2 door -------------> b2_entry --------+--> checkpoint_1 =[1]=> corridors_a --+--> labs_a (2 doors) =[2]=> labs_b
RDWE repeating room ----> hidden_entry ----(no card)----------------------------+   |                         | (2 doors)
                                                          corridors_a --> breaker_room =[2]=> corridors_b <-+
                                                          corridors_a --> checkpoint_2 =[2]=> corridors_b
                                                                corridors_b --> checkpoint_3 =[3]=> registrar_hall --> control_room (+ cell)
```

| From | To | Connector | Card | Note |
|---|---|---|---|---|
| `service_entry.checkpoint_1` | `checkpoint_1.service_entry` | doors | - | the dock hall's south door into the outer hall |
| `b2_entry.checkpoint_1` | `checkpoint_1.b2_entry` | doors | - | the scan room's east door into the outer hall |
| `checkpoint_1.corridors_a` | `corridors_a.checkpoint_1` | doors | 1 | the tier-1 door, north out of the inner hall |
| `hidden_entry.corridors_a` | `corridors_a.hidden_entry` | doors | - | the storeroom's maintenance door: no card, so the hidden entry skips checkpoint 1 |
| `corridors_a.labs_a_west` | `labs_a.corridors_a_west` | doors | - | north corridor, west door |
| `corridors_a.labs_a_east` | `labs_a.corridors_a_east` | doors | - | north corridor, east door |
| `corridors_a.breaker_room` | `breaker_room.corridors_a` | doors | - | the west corridor's door |
| `corridors_a.checkpoint_2` | `checkpoint_2.corridors_a` | doors | - | the east corridor's north door |
| `checkpoint_2.corridors_b` | `corridors_b.checkpoint_2` | doors | 2 | the tier-2 door out of the vestibule |
| `labs_a.labs_b` | `labs_b.labs_a` | doors | 2 | a tier-2 door between the labs: the second way into Corridors B's side |
| `breaker_room.corridors_b` | `corridors_b.breaker_room` | doors | 2 | a tier-2 door: the breaker room joins the two corridor sections |
| `corridors_b.labs_b_west` | `labs_b.corridors_b_west` | doors | - | north corridor, west door |
| `corridors_b.labs_b_east` | `labs_b.corridors_b_east` | doors | - | north corridor, east door |
| `corridors_b.checkpoint_3` | `checkpoint_3.corridors_b` | doors | - | the east end of the ladder |
| `checkpoint_3.registrar_hall` | `registrar_hall.checkpoint_3` | doors | 3 | the tier-3 vault door into the arena's west landing |
| `registrar_hall.control_room` | `control_room.registrar_hall` | doors | - | the door under the control room's window |

Links that leave this area (the coordinator wires the other side; nothing here edits the manifest):

| Link | Connector | Ids | The other side |
|---|---|---|---|
| `service_entry.freight_lift` | service_corridor | reused: grocery.backhouse>secret_ops (planned, needs keycard_tier_1); new: secret_ops.service_entry>grocery for the ride back | grocery back_of_house (planned, not built): its freight lift. Into service_entry: arrive (0, 0, -8.2) facing (0, 1), in the car |
| `service_entry.pool_dive` | pool_dive | reused: intern.pool_dive>secret_ops (planned, one way) | the Intern's escape (intern S8_H, built as a game): you surface in the pool and climb out at (-12.2, 0, 2.3) facing (0, -1), along the pool. The F side (diving back) stays shut until swimming exists |
| `hidden_entry.repeating_room` | gate | reused: rdwe.repeating_room>secret_ops (planned); new: secret_ops.hidden_entry>rdwe back | rdwe repeating_room (planned, RDWE's phase B). Into hidden_entry: arrive (-1.6, 0, 0) facing (1, 0) |
| `b2_entry.laboratory` | doors | new: lab.laboratory>secret_ops (needs a keycard, see the open questions) and secret_ops.b2_entry>lab | laboratory (built): the sealed B2 door on its north wall (shared/lab.js LAB.b2, (0, -6); F within 1.6 m of (0, -5.4)); back in the lab you stand at (0, 0, -4.6) facing (0, 1). Into b2_entry: arrive (0, 0, -1.4) facing (0, -1) |

The manifest's `service_entry` and `hidden_entry` (the `secret_ops` stub) have no coordinates yet, so there was nothing to keep: the arrival points above are new, and the coordinator copies them into `grocery.backhouse>secret_ops`, `intern.pool_dive>secret_ops` and `rdwe.repeating_room>secret_ops` as their `to.arrive` and `to.face`.

## Rulings (my calls, the owner can change any)

- **Scenes.** 13 unique scenes: `service_entry`, `hidden_entry`, `b2_entry`, `checkpoint_1` to `checkpoint_3`, `corridors_a`, `corridors_b`, `labs_a`, `labs_b`, `breaker_room`, `control_room` and `registrar_hall`. With the reskinned chambers that is the "about 12 scenes plus the boss" of docs/WORLD.md.
- **Progression.** The three entries meet at checkpoint 1 (service entry and B2 entry) or skip it (the hidden entry). Tier 1 opens Corridors A; tier 2 opens Corridors B by three doors (checkpoint 2, Labs A to Labs B, the breaker room's back door); tier 3 opens the Registrar's hall. A reader is on the side you come from; coming back, doors open from inside.
- **The hidden entry** is "the one entrance with no clearance": its maintenance door into Corridors A has no reader, so it skips checkpoint 1. It is also the base's blind spot: no cameras, no agents, two stash spots.
- **The B2 entry** is a decontamination airlock and a staff locker room behind the lab's sealed door (the lab is at y 0, so the "B2" stairs are the link itself; the scene's floor is at y 0 like every other).
- **The pool dive** arrives at the top of the pool's steps; the pool is 1.6 m deep with six 0.267 m steps and a `Zone_water`. Diving back is a link whose F side stays shut until swimming exists, as the plan says for every swimming route.
- **Keycard 3** has no flag in the manifest yet (only `keycard_tier_1` and `keycard_tier_2`). The tier-3 door asks for 3 and a `Spot_loot` in Labs B's specimen room carries `keycard_tier: 3`, so the card can be found inside the base as well as bought.
- **Cameras and breakers.** Every restricted scene has cameras (54 in all), each `SecCam_<nn>` an empty exported to `cameras` in world/L1.json's format (pan, tilt, zoom, loop) plus its own rig object `SecCam_<nn>_rig` to sweep and smash. Each camera is on a circuit: the breaker room's three breakers cut A (entries, checkpoint 1, Corridors A, the breaker room), B (the labs) and C (checkpoints 2 and 3, Corridors B). The arena has its own four breakers R1 to R4, one a wall, for phase 1; the control room has R5.
- **export_scene.py** now writes `SecCam_<nn>` empties to `cameras` (its table promised it; no scene had any). The change is additive: a camera's custom properties go through as objects and lists. Other areas' exports are unchanged.
- **Agents** are `Spot_agent_<n>` (role spawn, guard or phase_1) and their beats `Spot_patrol_<route>_<k>` (walked in order, looped); the page draws the suit character. No spawn is within 12 m of an arrival going deeper or 6 m of one coming back.
- **Arrivals** stand 1.4 m inside their door. Coming in by a side door of a corridor you would face its far wall, so those arrivals look the longer way along the corridor instead (every arrival has at least 2 m clear ahead; the gate checks it).
- **Shooter readability.** Full cover (pillars, crates 1.4 m, racks, cabinets, tanks, glass cubicles) and half cover (barriers 1.1 m, benches 0.95 m, low crates) in every combat space; the long corridors of Corridors A and B get alcoves to step into, since the corridor lanes stay clear; glass windows and cubicles keep sightlines without being open ground. Ammo and loot in every scene.
- **The Registrar's hall** is 47 m by 20 m and 7 m high (a stated exception to the 3.2 m ceilings): a 40 m by 20 m field of 200 `FloorPanel_<x>_<z>` (2 m, checkered) over an 8 m pit with a `Zone_hazard`, fixed landings at both ends (you never arrive on a panel), four rows of 48 `Rack_<n>` with 3 m aisles and a 4 m central aisle, 12 cameras on the four walls, the pink stripe at 1.2 to 1.5 m round every wall, the control room's window and the cell's bars on the east wall. Each panel carries `panel_x`, `panel_z` and `under_rack` (1 where a rack stands on it), each rack `rack` and `hp`; the `Spot_core` at the centre has `keep_panels`.
- **Phase 3's sky.** The ceiling over the field is 50 `CeilingPanel_<x>_<z>` objects the page can open on a sky. **Phase 3 needs a second, glitched sky backdrop for the arena (R3); it is not made here.**
- **The control room** has one chair (`Chair_control`, the only chair; `Spot_chair_1` where you sit) facing a wall of monitors, an Admin console spot (`Spot_admin_1`, unlocked by beating the Registrar), and the cell beside it: 4 m by 4 m, its door locked (`locked`, `puzzle: cell`, opens from inside), a window from the control room, three `Spot_puzzle` parts (a vent grate, a loose tile, a code panel), a `Zone_trigger_cell` and a camera watching it. In the arena the control room and the cell are its east wall.
- **Phase 2 filing.** Each scene but the hidden entry and the arena has one `Spot_filed` (11 in all, one of them in the cell) for the page to no-clip players to.

## Open questions for the owner

1. **Keycard tier 3:** add a `keycard_tier_3` flag (the Market sells it, and Labs B drops one), or should the vault door take something else?
2. **The lab's B2 door:** should it need keycard tier 1, like the grocery's lift, or is holding the lab job enough? (The B2 entry leads to checkpoint 1 either way.)
3. **Filing into the cell:** one of the phase 2 filing spots is in the cell, so a filed player may have to solve it. Keep?
4. **The arena's height:** 7 m, so the racks, the cameras and the opening ceiling read as a hall. Keep it, or 3.2 m like the rest?
5. **The hidden entry:** no cameras and no agents, as the base's blind spot. Or should one camera be there to find?

## Not done here

- Dressing, light baking and review renders (step 2), the manifest wiring and the page (the coordinator's).
- The reskinned chambers (the Going back in greybox's), the glitched phase 3 sky (R3), the agents' model and behaviour.
- Swimming (the pool dive back) and crawling: built for, shut.

## Gate output

See `CHECKS.txt`.
