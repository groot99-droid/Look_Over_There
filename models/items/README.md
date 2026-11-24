# models/items/

The owner's Meshy AI models for the arsenal, the consumables, the dealer items, the grocery food and two extras (24 files). **Eleven are loaded by the game so far**: the land mine and the nail-bomb tripwire (as the floor traps, scaled to 0.46 m and 0.45 m) and the nine held weapons of Going back in: the hunting crossbow (0.42 m), pneumatic bolt driver (0.4 m), stun baton (0.5 m), moth jelly dart (0.5 m), propane flamethrower (0.55 m), frequency horn (0.38 m), almond water rocket launcher (0.7 m), laser pointer dissector (0.3 m) and hydraulic rebar shear (0.55 m). The baton's front is +X in its file; the other eight point along -X. The rebar shear's model is one piece, so its jaws do not open in the hand (the cut shows in its kick). The other 13 are not loaded, and wiring each one in is separate work. The rules for them are in `docs/ITEMS.md`.

## How they were prepared

Each file is the raw Meshy export with one change: its single 2048 x 2048 colour texture was re-saved from PNG to WebP at quality 95 (`python3 tools/webp_glb.py in.glb out.glb 95`). The mesh is untouched (the tool checks the geometry bytes are identical), the texture keeps its resolution, and nothing was decimated, resized or Draco-compressed. The owner chose this over the heavier slimming the ray gun got, which had visibly hurt it. 102 MB of raw exports became 30 MB.

- Format: glTF 2.0 binary, one mesh, one material, colour map only (no normal or roughness map), `EXT_texture_webp` required. three.js 0.160 (the game's version) loads it with the plain `GLTFLoader`; no Draco decoder is needed.
- About 15k triangles each (4k for the apple slices, 10k to 12k for a few).
- Every model is normalised to 1 unit on its longest side and centred on the origin, so each needs a scale when it is placed or held. The facing differs per model: check it when wiring.
- Accepted by the owner as they are: the bread has no bag or label, the soup can's label text is garbled, and the Old Brew bottle and the zip bags are opaque.
- Load a model when its item first appears, not at startup: the 24 together are 30 MB.

## What each file is

| Kind | File | Item | Meshy's name for it | Triangles | Size |
|---|---|---|---|---|---|
| Weapon | `pneumatic_bolt_driver.glb` | Pneumatic bolt driver | Rustborn_Raycaster | 15,009 | 1.30 MB |
| Weapon | `hunting_crossbow.glb` | Hunting crossbow | Rustbound_Recurve | 15,388 | 1.35 MB |
| Weapon | `propane_flamethrower.glb` | Propane flamethrower | Rustborn_Flamethrower | 14,811 | 1.26 MB |
| Weapon | `stun_baton_capacitor.glb` | Stun-baton capacitor | Rustbound_Contraption | 14,631 | 1.29 MB |
| Weapon | `almond_water_rocket_launcher.glb` | Almond water aerosol rocket launcher | Scrapyard_Blaster | 14,709 | 1.38 MB |
| Weapon | `laser_pointer_dissector.glb` | Optical laser pointer dissector | Scraplight_Blaster | 15,317 | 1.34 MB |
| Weapon | `hydraulic_rebar_shear.glb` | Hydraulic rebar shear | Rustborn_Rebar_Cannon | 14,555 | 1.29 MB |
| Weapon | `frequency_horn.glb` | Sound-amplified frequency horn | Junkyard_Sonic_Blaster | 14,616 | 1.27 MB |
| Weapon | `moth_jelly_dart.glb` | Moth jelly dart | Moth_Jelly_Blaster | 15,630 | 1.31 MB |
| Weapon | `gravity_gauntlet.glb` | Spring-loaded gravity gauntlet | Violet_Arc_Gauntlet | 15,365 | 1.32 MB |
| Consumable | `almond_water_land_mine.glb` | Almond water land mine | Scrapyard_Contraption | 14,990 | 1.42 MB |
| Consumable | `nail_bomb_tripwire.glb` | Compressed-air nail-bomb tripwire | Rustfang_Apparatus | 15,496 | 1.38 MB |
| Consumable | `incendiary_flash_vial.glb` | Phosphor-core incendiary flash-vial | Rustbound_Ember_Lantern | 12,111 | 1.25 MB |
| Dealer item | `green_leaf.glb` | Green plant ("Green Leaf") | Green_Leaf_Pack | 15,926 | 1.72 MB |
| Dealer item | `trippy_paper.glb` | Paper tab ("Trippy Paper") | Psychedelic_Sticker_Pack | 16,142 | 1.99 MB |
| Dealer item | `munchy_mushies.glb` | Mushrooms ("Munchy Mushies") | Munchy_Mushies | 9,737 | 1.14 MB |
| Dealer item | `sugar_rush.glb` | White powder ("Sugar Rush") | Sugar_Rush_Ice_Pack | 16,458 | 1.16 MB |
| Dealer item | `old_brew.glb` | Alcohol ("Old Brew") | Old_Brew_Bottle | 15,249 | 1.10 MB |
| Food | `apple_slices.glb` | Apples | Industrial_Apple_Slices | 4,179 | 0.82 MB |
| Food | `bread.glb` | Bread | Industrial_Bread | 15,749 | 0.98 MB |
| Food | `soup_can.glb` | Canned soup | Industrial_Soup_Can | 15,486 | 1.12 MB |
| Food | `ready_meal.glb` | Ready meal | Industrial_Ready_Meal | 16,046 | 0.95 MB |
| Extra | `med_kit.glb` | Med kit (no rule yet) | Apocalypse_Med_Kit | 14,751 | 1.43 MB |
| Extra | `spicy_brew.glb` | Spicy Brew (rule from the owner: Old Brew's wobble, but faster and hungrier, no blackout) | Spicy_Brew_Bottle | 16,436 | 1.49 MB |

A reference image exists for a plain spring gauntlet with no violet glow; it has no model. The raw exports and the reference images are kept by the owner outside the repository.
