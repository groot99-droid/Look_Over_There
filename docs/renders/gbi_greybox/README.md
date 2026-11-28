# Going back in greybox (docs/BLENDER_AREAS.md, section 6: 15 chambers and 5 safe houses)

Plain boxes, to scale, for the 15 new chambers of Going back in and the five safe houses: no dressing, no bake. Each chamber fills the store's footprint (x -26.3 to 26.3, z -22.35 to 27.35) at its floor's height (B1 -3, L1 0, L2 3.2, L3 6.4, L4 9.6). The two chambers that exist, `gbi_L4_4` and `gbi_L3_1`, are left as they are, and so are the store's floors. This is for review: no scene or link has been added to the manifest, and the greybox GLBs are in `glb/` here, not in `world/`.

- Built by `tools/blender/build_gbi_greybox.py` (the method of the Overworld's and the hotel's greybox builds). The Blender run on the rented GPU writes `world/<chamber>.json` through `tools/blender/export_scene.py`, the GLB and an eye-height still; the plans, the floor panels and the owner's sheet are drawn from the same model by `tools/blender/gbi_greybox_sheets.py`.
- `python tools/blender/build_gbi_greybox.py --check .` runs the gates on the exported files (see `CHECKS.txt`): every link has its other side; each chamber has exactly one arrival and one way on, and the run is one chain from `gbi_L4_1` to the Overworld; every spot is there; every monster is at least 16 m from the arrival; every collider is inside the footprint and its storey; no two solids overlap; links, spots and doors are clear, corridors at least 1.6 m; a walker can reach the way on and every spot from the arrival; every hazard has its part, its two travel ends and its zone; the hazards' parts are their own nodes in the GLBs; and the Blender export is exactly what the model says.
- `CHECKS.txt`: the gates, `node tools/worlddoc.mjs check` on every file (0 errors; the warnings say a scene or a link is new to the manifest), `node --test shared/*.test.js`, and the privacy grep.
- `owner_gbi_greybox.png`: one tall sheet for a phone, a panel per floor. `<floor>_panel.png`: the floor's four chambers in the run's order (1 top left, 2 top right, 3 bottom left, 4 bottom right), the existing one drawn from its own layout file. `<chamber>_plan.png`: one chamber, larger, with every spot, the hazards' travel and labels. `<chamber>_still.jpg`: eye height (1.55 m), greybox lights only.

## The run

`L4_1 > L4_2 > L4_3 > L4_4 (existing) > stairs > L3_1 (existing) > L3_2 > L3_3 > L3_4 > stairs > L2_1 > L2_2 > L2_3 > L2_4 > stairs > L1_1 > L1_2 > L1_3 > L1_4 > stairs > B1_1 > B1_2 > B1_3 > B1_4 > out to the Overworld`

Connectors, all from the kit (`blender/kit/README.md`): 3 elevator pairs, 6 painted-sky halls (one of them the way out), 3 plain doors between chambers, 3 stair doors down to the next floor's real stairwell and 3 stair doors arriving from the existing floor's own stairs down, and 4 vent ducts built shut.

## Chambers

| Chamber | Layout | Arrives by | Leaves by | Hazards | Spots | Colliders, doors |
|---|---|---|---|---|---|---|
| `gbi_L4_1` | Showroom floor: the run's first chamber: a lit showroom, a lava band to cross on display islands | spawn: the run's start | elevator to `gbi_L4_2` (`lift_to_L4_2`) | floor is lava (`Hazard_lava_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 54, 4 |
| `gbi_L4_2` | Room sets: furniture showroom: mock rooms down both sides, a chainsaw slot in the aisle, the floor's safe house | elevator from `gbi_L4_1` (`lift_from_L4_1`) | painted-sky hall to `gbi_L4_3` (`exit_to_L4_3`) | moving chainsaw blades (`Hazard_blade_1`, `Hazard_blade_2`) | locker x1, loot x3, puzzle x1, object x3, monster x3; **safe house** | 66, 3 |
| `gbi_L4_3` | Stockroom: the racking behind the showroom: tall aisles, a cross aisle where the walls close | painted-sky hall from `gbi_L4_2` (`from_L4_2`) | painted-sky hall to `gbi_L4_4` (`exit_to_L4_4`) | crushing walls (`Hazard_crush_1`, `Hazard_crush_2`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 31, 3 |
| `gbi_L3_2` | White gallery: one bright plaster hall, free-standing walls and plinths, the floor's safe house | stair door from `gbi_L3_1` (`stair_from_L3_1`) | door to `gbi_L3_3` (`to_L3_3`) | moving chainsaw blades (`Hazard_blade_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3; **safe house** | 46, 3 |
| `gbi_L3_3` | Colonnade: white columns either side of a long hall you must walk the length of, where the walls close | door from `gbi_L3_2` (`from_L3_2`) | elevator to `gbi_L3_4` (`lift_to_L3_4`) | crushing walls (`Hazard_crush_1`, `Hazard_crush_2`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 54, 2 |
| `gbi_L3_4` | White maze: plaster walls that fold the room into one long path; lava chases you down a leg; the stairs down | elevator from `gbi_L3_3` (`lift_from_L3_3`) | stair door to `gbi_L2_1` (`stair_down`) | floor is lava (`Hazard_lava_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 46, 3 |
| `gbi_L2_2` | Door grid: a grid of small rooms, a door on every side; gas drifts down the middle row; the floor's safe house | stair door from `gbi_L2_1` (`stair_from_L2_1`) | painted-sky hall to `gbi_L2_3` (`exit_to_L2_3`) | toxic gas (`Hazard_gas_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3; **safe house** | 124, 29 |
| `gbi_L2_3` | Long loop: rings inside rings; the way on is only reached by walking the loops; blades in two legs | painted-sky hall from `gbi_L2_2` (`from_L2_2`) | door to `gbi_L2_4` (`to_L2_4`) | moving chainsaw blades (`Hazard_blade_1`, `Hazard_blade_2`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 32, 4 |
| `gbi_L2_4` | Split halls: three long halls side by side, cross passages between them; the walls close in the middle hall; the stairs down | door from `gbi_L2_3` (`from_L2_3`) | stair door to `gbi_L1_1` (`stair_down`) | crushing walls (`Hazard_crush_1`, `Hazard_crush_2`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 36, 5 |
| `gbi_L1_2` | Cubicle farm: an open office of low cubicles, private offices along the north wall, gas down an aisle; the floor's safe house | stair door from `gbi_L1_1` (`stair_from_L1_1`) | elevator to `gbi_L1_3` (`lift_to_L1_3`) | toxic gas (`Hazard_gas_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3; **safe house** | 157, 6 |
| `gbi_L1_3` | Corridor offices: two corridors cross in the middle, offices in every quarter, the walls close in the north leg | elevator from `gbi_L1_2` (`lift_from_L1_2`) | painted-sky hall to `gbi_L1_4` (`exit_to_L1_4`) | crushing walls (`Hazard_crush_1`, `Hazard_crush_2`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 69, 10 |
| `gbi_L1_4` | Conference ring: a ring corridor round the conference room, offices outside it, a blade in the west leg; the stairs down | painted-sky hall from `gbi_L1_3` (`from_L1_3`) | stair door to `gbi_B1_1` (`stair_down`) | moving chainsaw blades (`Hazard_blade_1`), toxic gas (`Hazard_gas_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 49, 8 |
| `gbi_B1_2` | Lido: a white-tiled pool hall under columns; the tide rises in the pool; the floor's safe house | door from `gbi_B1_1` (`from_B1_1`) | door to `gbi_B1_3` (`to_B1_3`) | high tides (`Hazard_tide_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3; **safe house** | 52, 2 |
| `gbi_B1_3` | Baths: bath cells off a tiled corridor; the tide in the west bath, gas down the corridor | door from `gbi_B1_2` (`from_B1_2`) | painted-sky hall to `gbi_B1_4` (`exit_to_B1_4`) | high tides (`Hazard_tide_1`), toxic gas (`Hazard_gas_1`) | locker x1, loot x3, puzzle x1, object x3, monster x3 | 35, 8 |
| `gbi_B1_4` | The drain: wave 20, the run's end: a walkway round a flooding basin, a blade along the last dash, the EXIT hall out | painted-sky hall from `gbi_B1_3` (`from_B1_3`) | painted-sky hall to the Overworld (`exit_to_overworld`) | high tides (`Hazard_tide_1`), moving chainsaw blades (`Hazard_blade_1`, `Hazard_blade_2`) | locker x1, loot x3, puzzle x1, object x3, monster x4 | 39, 3 |

Each **safe house** is the kit's room (`world/kit/safe_house.json`) placed in the chamber with the suffix of its floor: `Spot_shop_1_<F>`, `Spot_stash_1_<F>`, `Spot_save_1_<F>`, `Spot_craft_1_<F>`, `Spot_respawn_1_<F>`, `Spot_locker_1_<F>` (each with `of: safe_house`) and `Zone_safe_safe_house_<F>`.

## Links that leave this set (the coordinator's side)

The arrive points on the existing floors are the store's own (the points its stair doors arrive at today); each was checked to be clear and on a floor in that floor's file.

| Chamber and door | Connector | Other side | Proposal |
|---|---|---|---|
| `gbi_L4_1` (Marker_Arrival, Spawn) | none | the options screen | the run starts here: the manifest's `startChamber` moves from `gbi_L4_4` to `gbi_L4_1` |
| `gbi_L4_3`.`exit_to_L4_4` | painted-sky hall | `gbi_L4_4` | new in `gbi_L4_4`: arrive just inside the store's sealed glass doors, (0, 9.6, 25.6) facing (0, -1) |
| `gbi_L3_2`.`stair_from_L3_1` | stair door | `gbi_L3_1` | `gbi_L3_1`'s own stair door down, `DoorLeaf_Stair_L2_L3_down` (unlinked today), leads here; back: arrive in `gbi_L3_1` at (-16.478, 6.4, -15.078) facing (0, -1) |
| `gbi_L3_4`.`stair_down` | stair door | `gbi_L2_1` | arrive in L2's real stairwell, (-16.478, 6.4, -14.278) facing (0, 1); back: `gbi_L2_1`'s `DoorLeaf_Stair_L2_L3_up` |
| `gbi_L2_2`.`stair_from_L2_1` | stair door | `gbi_L2_1` | `gbi_L2_1`'s `DoorLeaf_Stair_L1_L2_down` leads here; back: arrive at (-0.007, 3.2, 10.508) facing (0, 1) |
| `gbi_L2_4`.`stair_down` | stair door | `gbi_L1_1` | arrive in L1's real stairwell, (-0.007, 3.2, 9.708) facing (0, -1); back: `gbi_L1_1`'s `DoorLeaf_Stair_L1_L2_up` |
| `gbi_L1_2`.`stair_from_L1_1` | stair door | `gbi_L1_1` | `gbi_L1_1`'s `DoorLeaf_Stair_B1_L1_down` leads here; back: arrive at (0.009, 0.0, -0.799) facing (0, 1) |
| `gbi_L1_4`.`stair_down` | stair door | `gbi_B1_1` | arrive in B1's real stairwell, (0.009, 0.0, -1.599) facing (0, -1); back: `gbi_B1_1`'s `DoorLeaf_Stair_B1_L1_up` |
| `gbi_B1_2`.`from_B1_1` | door | `gbi_B1_1` | B1 has no second door: `gbi_B1_1` needs a new one (open question 3) |
| `gbi_B1_4`.`exit_to_overworld` | painted-sky hall | the Overworld | the run's end: out to the results screen and the lot, as the Original's walk-out |

`gbi_L2_1`, `gbi_L1_1` and `gbi_B1_1` have no file yet; they are the store's L2, L1 and B1, to make as `tools/make_chambers.mjs` made `gbi_L3_1`.

## Names the page and the coordinator read

- **Links**: `Link_<door>` / `Arrive_<door>` as in the table; the kit's names carry its suffix (`lift_to_L4_2`, `exit_to_L4_3`, `stair_down`). Every chamber also has `Marker_Arrival` (`Spawn` on `gbi_L4_1`, `Entrance` elsewhere, with the door it belongs to).
- **Hazards**: the moving part is `Hazard_<kind>_<n>` (kinds `crush`, `lava`, `tide`, `gas`, `blade`), one object with its origin at the start of its travel and the properties `hazard`, `kind_of`, `motion` (`close`, `advance`, `rise`, `drift`, `fill`, `track`), `period_s`, `what`, `travel_a`, `travel_b`, `zone` (and `y_from`/`y_to` for a rising tide). It has no collider: the page moves it and deals the damage. The two ends of its travel are the spots `Spot_hazard_<kind>_<n>_a` and `_b` (kind `hazard` in the layout file, same properties plus `end`), on the floor at the part's origin at each end; the area is `Zone_hazard_<kind>_<n>`. A pair of crushing walls are two hazards with `pair` naming each other.
- **Spots**: `Spot_locker_1` (the Lost and Found), `Spot_loot_<n>`, `Spot_puzzle_1` (`what`: the floor's own puzzle), `Spot_object_<n>` (the missing objects), `Spot_monster_<n>` (`wave`: 1 to 20, top down), `Spot_vent_<n>` (`state: shut`, `to`). The kit's `Spot_call_1_<sfx>` and `Spot_panel_1_<sfx>` come with each elevator.
- **Doors**: the chamber doors inside a chamber are `DoorLeaf_<wall>_<where>`, 0.94 m by 2.16 m, `kind: chamber door`, `barricade: yes`, with mixed states (closed, open, ajar), so they can be shut, trapped or barricaded. Vent grilles are `DoorLeaf_vent_<n>`, 0.8 m square, `locked`.
- **Water**: the pools are `Zone_water_<name>` (0.3 m deep, walkable), with an art-only surface (`decor_*_Water`).

## Materials (for the reskin)

Every box uses a role material, named after the store's own per-floor set so the dressing pass can take the store's materials by name and Secret Operations can swap them: `M_D_floor_<F>`, `M_D_wall_<F>`, `M_D_ceil_<F>` (floor, walls, ceiling), `M_GBI_furn_<F>` (furniture, racks, desks), `M_D_trim` (low partitions, half walls, islands, blade slots), `M_D_door`, `M_Water`, `M_GBI_kit` (the kit's pieces, which the page draws from `world/kit/<piece>.glb`), `M_GBI_vent`, and `M_GBI_hazard_<kind>`. Each art box also carries its role as the property `mat_role`. A chamber's whole look is those few materials.

## Rulings (my calls; the owner can change any of them)

1. **Safe houses** are inside chamber 2 of each floor (`gbi_L4_2`, `gbi_L3_2`, `gbi_L2_2`, `gbi_L1_2`, `gbi_B1_2`): the kit's room against an outer wall, door facing the chamber, after the floor's first wave. Not separate scenes, so there is no extra load and no extra link.
2. **The existing floor's own stairs down** are its chamber 1's way on (into chamber 2's stair door), because in Going back in the next floor is reached from chamber 4's new stair door, which arrives in that floor's real stairwell, as the brief says.
3. **The run's start is `gbi_L4_1`** (a Spawn marker by its south wall), and **the run's end is an EXIT painted-sky hall in `gbi_B1_4`** out to the Overworld: "every hall between worlds".
4. **Connectors**: elevators, painted-sky halls and plain doors between chambers on a floor; stair doors only where the floor changes. Each piece stands inside the footprint against an outer wall (the sky hall and the stair door's hallway are 10.4 m deep), so nothing leaves the store's footprint. The elevator gets a shaft round its car (side stubs, a header to the ceiling) so it cannot be walked behind.
5. **Kit placement** uses the pieces' own layout files (`world/kit/<piece>.json`) with `kit_place.py`'s transform and suffix rule (so `--preview`, `--check` and Blender agree); the sky hall's `entry` link and the stair door's `hall_far` link are left out (you walk through the entry; the hallway's far door is shut), and so are the kit's own markers.
6. **Vents are built shut** (4 of them) and are not links: each chamber keeps exactly one way on until crawling exists; `Spot_vent_<n>` says where each would lead.
7. **Ceilings**: B1 3.0 m, L1 2.8 m, L2 3.0 m, L3 3.2 m, L4 4.5 m (the store's showroom height). The sky hall (3.25 m) and the stair door's landing run into the ceiling slab of a lower room; on dressing that is hidden or the room raised.
8. **Hazards**, 25 in all, at least one per chamber, every kind used (crushing walls x8, blades x8, gas x4, tides x3, lava x2): lava where there is room to cross on islands (L4_1, L3_4), tides in the pools (B1), gas in offices, doors and baths, crushing walls in narrow aisles and halls, blades along floor slots. Hazards never block the only way on for good: each cycles (`period_s`).
9. **The monsters** stand at the far end from the arrival: the nearest is 26.7 m away (at least 16 m was asked). `gbi_B1_4`, wave 20, has four.
10. **Looks**: three layouts per floor in that floor's spirit: L4 showroom floor, room sets, stockroom; L3 gallery, colonnade, maze; L2 door grid, loop, split halls; L1 cubicles, corridor offices, conference ring; B1 lido, baths, drain.

## Open questions for the owner

1. Should a safe house be its own small scene off the chamber, rather than a room inside chamber 2?
2. Is a stair door the right way from an existing floor into its chamber 2 (it reuses that floor's real stairs down), or would you rather the existing floors kept their stairs as decoration and got a new door?
3. B1 has no second door: what should take you from `gbi_B1_1` (the store's B1) to `gbi_B1_2`? Proposal: a painted-sky hall on B1's north wall. A pool dive would also fit, once swimming exists.
4. Where should `gbi_L4_3`'s sky hall arrive in `gbi_L4_4`? Proposal: just inside the store's sealed glass doors.
5. Should the vents become a second way between chambers once crawling exists (a shortcut that skips a hazard), or stay a hiding place?
6. The end of the run: out through an EXIT hall to the Overworld's results screen, or a last room first?
7. Ceiling heights: L4's chambers are 4.5 m like the store's showroom; should they be lower, like the other floors?

## For the coordinator

- `world/gbi_L4_4.json` (and `world/L4.json`, which it is made from) has a collider `Site_ITN_City` (x 17.39 to 34.74, z 4.89 to 29.18, y 9.6 to 84.6) from the Exterior's city backdrop that reaches into the store's east bays. It is not from this greybox, and nothing here changes it; worth a look, since it may block the east of the store in that chamber.
