# Characters: the museum's night exhibits, the stalker and the Mawcrawler

All five source models are **the owner's own Meshy work** (generated on 2026-11-24). They are kept as
they came: no decimation and no remeshing (`docs/BLENDER.md` rule 5). Every triangle count below matches
the source. The only edit is the one the owner asked for, which was to cut the two warrior friezes into
their figures. Neither frieze has a shared base or ground plate, so no geometry was deleted. No hole was
made, and nothing had to be filled.

| Where | What |
|---|---|
| `blender/characters/source/*.glb` | The five Meshy sources, unchanged. Not in the repo (git-ignored, 41 MB): the owner keeps them. To rebuild, put the five files here under these names: `warriors_through_the_ages.glb`, `warriors_across_empires.glb`, `tyrant_bones.glb`, `moonclaw_stalker.glb`, `the_mawcrawler.glb` |
| `tools/blender/characters/build_trex.py` | The T. rex: new theropod rig, weights, clips → `models/characters/trex.glb` |
| `tools/blender/characters/build_warriors.py` | Splits both friezes into 8 figures, rigs each one and adds clips → `models/characters/warrior_*.glb` |
| `tools/blender/characters/build_creatures.py` | The stalker and the Mawcrawler: keeps the Meshy rigs, names the bones and adds clips |
| `tools/blender/characters/common.py` | Shared helpers: import, armature, weights, the mesh cut, keyframed clips (NLA tracks), the stretch gate, WebP export, scrub |
| `tools/blender/characters/skinweights.py` | Weight solving in plain numpy: the cut between a held weapon and the body, harmonic weights between anchors, the stretch and crack measures, the relax, and the warriors' `Humanoid` fit with its size search |
| `tools/blender/characters/warrior_clips.py`, `creature_clips.py` | The clips as pose functions (no Blender needed), and the same poses as bone matrices for the stretch measure |
| `tools/blender/characters/render_stills.py` | Imports each exported GLB again and renders its display pose and one clip frame (Cycles, CPU) |
| `tools/blender/characters/make_sheet.py` | Builds the JPEG stills and `contact_sheet.jpg` (Pillow, at most 400 KB each, no metadata) |
| `docs/renders/characters/<name>.jpg` | One still per character: the display pose on the left and a clip frame on the right |

To rebuild, run each step through the one-Blender-at-a-time wrapper. Blender 5.2 runs on the CPU.

```
blender -b --factory-startup -P tools/blender/characters/build_trex.py
blender -b --factory-startup -P tools/blender/characters/build_creatures.py
blender -b --factory-startup -P tools/blender/characters/build_warriors.py
blender -b --factory-startup -P tools/blender/characters/render_stills.py -- <render_dir>
python tools/blender/characters/make_sheet.py <render_dir>
```

## Conventions (all files)

- **Axes:** glTF, y up. Each character faces **+Z**. Its own left is +X, and its bones use the suffixes
  `.L` for +X and `.R` for −X.
- **Origin:** on the floor, between or under the feet. The rest pose is the display pose, the pose the model
  was made in.
- **One `SkinnedMesh` per file** with one skeleton and named `AnimationClip`s. Clips run in place: they have
  no root motion, so code moves the character. The exceptions are the Mawcrawler's `lunge` and `spawn`, which
  move its root bone and return it to the start.
- **Textures:** the Meshy maps keep their full resolution and are re-encoded as WebP (`EXT_texture_webp`, q90),
  as `models/ammo_pack.glb` and the other models the page already loads are. There is no Draco.
- **Frame rate:** keys are sampled on every frame at 24 fps. Looping clips end on their first pose.

## The files

All of them load in three.js (checked with `GLTFLoader` and `AnimationMixer` in node; the API used is the
r160 API). Each has one skin, its clips, a WebP base colour map, and bounds as listed. Bounds are in metres in
the file, as min → max (x, y, z).

| File | What it is | Tris (= source) | Bones | Size | Bounds | Clips (seconds; L = loops) |
|---|---|---|---|---|---|---|
| `trex.glb` | T. rex skeleton, museum exhibit ("Tyrant Bones") | 10,940 | 27 (26 deform) | 1.46 MB | (−1.63, 0, −6.02) → (1.63, 3.74, 6.02): 12.0 m long, 3.74 m tall | idle 3.0 L, walk 1.67 L, roar 3.0, return_to_pose 1.5 |
| `stalker.glb` | The City's stalker ("Moonclaw Stalker") | 6,165 | 65 | 3.09 MB | (−0.51, 0, −0.64) → (0.51, 1.70, 0.64) | idle 2.5 L, walk 1.33 L, stalk 2.67 L, freeze 1.0 (held pose) |
| `mawcrawler.glb` | The Mawcrawler, a random spawning mob | 5,482 | 44 | 2.77 MB | (−1.46, 0, −1.15) → (1.46, 1.70, 1.15) | idle 2.0 L, crawl 1.33 L, lunge 1.25, spawn 2.0 |
| `warrior_egyptian_pharaoh.glb` | Pharaoh in a nemes headdress, with a khopesh | 4,540 | 18 (17) | 0.88 MB | 0.43 m tall | idle 2.0 L, march 1.0 L, attack 0.92, freeze 0.25 |
| `warrior_viking_raider.glb` | Viking with a helmet, a bearded axe and a round shield | 5,045 | 18 (17) | 0.91 MB | 0.44 m tall | as above |
| `warrior_qin_terracotta.glb` | Qin terracotta soldier with a ji halberd | 5,839 | 18 (17) | 0.94 MB | 0.45 m tall | as above |
| `warrior_british_redcoat.glb` | 18th-century redcoat with a tricorne and a musket | 5,802 | 18 (17) | 0.95 MB | 0.46 m tall | as above |
| `warrior_medieval_knight.glb` | Late-medieval knight in plate, with a sallet and a sword | 4,636 | 18 (17) | 0.87 MB | 0.51 m tall | as above |
| `warrior_japanese_samurai.glb` | Samurai in armour, with a kabuto and a katana | 5,273 | 18 (17) | 0.90 MB | 0.49 m tall | as above |
| `warrior_mongol_archer.glb` | Mongol horse archer with a spear, a bow and a quiver | 6,058 | 18 (17) | 0.94 MB | 0.54 m tall | as above |
| `warrior_roman_legionary.glb` | Roman legionary with a galea, a gladius and a scutum | 4,753 | 18 (17) | 0.87 MB | 0.50 m tall | as above |

The four warriors from "Warriors Through the Ages" add up to 21,226 triangles and the four from "Warriors
Across Empires" to 20,720. Both totals equal their frieze, so the split lost nothing.

### How each one was rigged

- **T. rex.** Meshy's rig did not fit a theropod. It had no jaw and a single arm on the midline, one chain
  ran along the belly ribs, and both legs were pushed to one side. It was replaced by a new rig with these
  bones:
  - `root`, which does not deform;
  - `pelvis`, `spine1`, `spine2` and `chest`;
  - `neck1` to `neck3`, `head` and `jaw`;
  - `tail1` to `tail9`;
  - `thigh`, `shin` and `foot` on each side;
  - `arm.L` and `arm.R`.

  The skull, spine and tail form one piece of the mesh. The lower jaw is cut from the skull along the gap
  between the teeth: the faces that bridged the gap now belong to one side or the other and their vertices are
  doubled in place (no face added, removed or moved), so the teeth no longer string out when the mouth opens.
  That piece is weighted **harmonically**: anchored at the core of each axial bone (the jaw to `jaw`), and
  blended smoothly by length in between, so no short edge takes a whole change of weight. Every separate bone of
  the mesh moves rigidly with its own bone: each leg segment and each arm is matched by position, and each rib
  follows the spine.

  The model is **scaled in the file** (2.2×) to real size, so code should not scale it. The rest pose is
  the mounted display pose. `return_to_pose` starts from a mid-stride pose, with the head turned and the jaw
  open, and eases into that display pose, so it can follow `walk` or `roar` when the lights come back.
- **Stalker and Mawcrawler.** Both Meshy rigs fit their bodies.
  - The stalker's rig is a hunched biped: spine, neck, head, three small chains in the mouth (`mouth_a` to
    `mouth_c`), long arms with four claws per hand (`claw1_1.L` and so on), and digitigrade legs (`thigh`,
    `shin`, `foot`, `toe`).
  - The Mawcrawler's rig has `body`, `neck`, `maw`, `jaw_upper`, `jaw_lower`, `tail`, and six legs:
    `leg_front1.L` to `leg_front5.L`, then `leg_mid*` and `leg_rear*` with six bones each.

  Their bones and Meshy's weights are kept; only the bone names changed (renaming a bone renames its vertex
  group). The stalker's weights were fixed where its clips stretched them: Meshy gave the toes part of the
  long claws that hang beside the feet (and the claws part of the toes), which tore the claw into a spike
  whenever a leg moved. Now an arm never takes a leg's weight or the other arm's, and a leg never an arm's; then
  the weights are smoothed around every edge a clip still stretched past 1.8×. The stalker's arms, stride and
  claws play at 0.8 of their first size so every frame passes the gate; its `freeze` curls the claws in (a
  spread tore the webbing between them). The Mawcrawler's weights pass as they are; its `spawn` folds the legs
  less tightly than before (that fold stretched them up to 3×). The stalker's rest pose is a stride, so `walk`
  and `stalk` bring the legs under the hips.
- **Warriors.** Each frieze was cut into loose parts. Seams were welded for the count, so a figure is not cut
  along its UV seams. Parts of 1,000 triangles or more seeded the figures, and every smaller part joined the
  figure it touches. No base or ground plate existed, so nothing was deleted.

  Each figure got a small humanoid rig: `root`, `hips`, `spine`, `chest`, `neck`, `head`, and on each side
  `thigh`, `shin`, `foot`, `upperarm`, `forearm` and `hand`. The rig was placed from measurements of the
  figure, with the legs and the depth of each joint read from the mesh.

  The figures are sculpted in one piece: hands rest on thighs and belts, a fist sits on the breastplate, the
  legs are joined under coats, robes and skirts, the Viking's axe lies on his shoulder against the helmet and his
  shield is fused to his body, and the redcoat's musket is sculpted onto his coat. Blender's automatic (heat)
  weights tore them wherever those parts moved apart. The weights are now built in `skinweights.Humanoid`:
  - **limbs.** Each point gets a limb from the heat weights (a leg never across the midline). An arm keeps only
    what lies within 6 % of the figure's height of its own bones: the heat weights also gave the arms the coat
    tail, the belt or the skirt panel a hand rests on, which then tore away with every swing.
  - **held parts.** Every separate weapon within 3 cm of a hand is held rigidly by that hand, the distance
    measured along its edges as well as at its vertices (a long shaft such as the ji or the Mongol spear has
    vertices only at its ends). A held part must look like a weapon: long and thin (a sword, a bow, a spear, the
    musket's lower half) or large (the scutum); a flat skirt panel hanging by the hand stays with the body. Two
    weapons are sculpted onto the body, so they are selected by shape in `build_warriors.py` and held the same
    way: the Viking's bearded axe (a capsule round the haft and a box round the head) and the redcoat's slung
    musket (two capsules, stock and barrel). The Viking's round shield, which is turned and curves back at the
    rim, is held as a disc (centre, normal, radius, depth), so the whole rim goes with it.
  - **the only cut.** A held weapon or shield is cut from the body it touches (its faces keep their vertices,
    which are doubled in place; no face is added, removed or moved), so it can leave the body. Nothing else is
    cut: the first fix also cut every limb from the limbs it rests on, and the clips then opened cracks up to
    3 cm wide in coats, robes and skirts. The legs under a robe and a hand on a hip now stay joined and blend.
  - **harmonic weights.** Points in the core of each bone are anchored to it (never two anchors of different
    bones side by side, and never two anchors of bones that are not jointed within 2 % of the figure's height
    of each other, such as the inner thighs under a robe), and everything in between is harmonic over the mesh,
    weighted by edge length, so the weights blend across each joint over centimetres, never within one short
    edge. Of the anchor settings tried, those that keep at least 85 % of the motion and stretch least win; the
    weights are then smoothed around every edge a clip still stretches past 1.8x.

  The clips move the figures like toys coming alive: the whole figure rocks from foot to foot in `march` and
  leans back, then into the blow in `attack` (a turn of the root bone, which bends nothing), the legs step, the
  body twists from the spine and the weapon arm swings. Each clip has a ladder of sizes
  (`warrior_clips.LADDERS`). For each figure every clip plays at the largest size at which, after the weights are
  smoothed for it, no edge stretches past 2x and no cut opens a crack (see the gates below). The table under the
  gates lists the sizes each figure got.

  The soles of all eight figures were already open in the source (86 to 162 open edges at the feet of each).
  They were left open, because filling them would change the triangle counts. They cannot be seen while a
  figure stands.

  The main weapon hand is `hand.R`, except for the samurai and the knight (`hand.L`). `attack` is a lunge:
  the figure leans back and winds up, then strikes forward from the spine, the legs brace and the weapon arm
  swings (for the figures whose arm size is 0 the weapon moves with the body only).
  `freeze` holds the display pose for 0.25 s, which makes a crossfade into it snap the figure back to how it
  stood in the case.

### The gates

Every build plays every clip, frame by frame, through the armature and measures each triangle edge: its
length over its rest length, or the inverse when it shrinks (the same measure as the node check). **No edge
may pass 2x** in any frame of any clip, or the build stops (edges under 1 mm at rest, 2.2 mm on the T. rex and
0.3 mm on the warriors, are not measured). The warriors' weight solve also measures every cut: the two copies
of a doubled vertex, where neither is held by a hand, may not move more than 1.2 % of the figure's height apart
(a crack, which the edge measure cannot see). Since only held weapons are cut now, no warrior has such a cut
and every crack is 0 mm. When a clip cannot pass at full size, it plays at a smaller size from its ladder. The
sizes and worst edges each warrior got:

| Figure | idle (sway) | march (stride) | attack (legs, arm, body) | Worst edge: idle / march / attack | Cracks |
|---|---|---|---|---|---|
| `warrior_egyptian_pharaoh` | 1.0 | 1.0 | 1.0, 1.0, 1.0 | 1.08 / 1.56 / 1.49 | 0 mm |
| `warrior_viking_raider` | 1.0 | 0.85 | 0.4, 0.0, 0.6 | 1.33 / 1.94 / 1.66 | 0 mm |
| `warrior_qin_terracotta` | 1.0 | 0.35 | 0.55, 0.55, 0.7 | 1.45 / 1.83 / 1.86 | 0 mm |
| `warrior_british_redcoat` | 1.0 | 1.0 | 1.0, 1.0, 1.0 | 1.12 / 1.65 / 1.67 | 0 mm |
| `warrior_medieval_knight` | 1.0 | 0.85 | 0.4, 0.0, 0.6 | 1.08 / 1.79 / 1.78 | 0 mm |
| `warrior_japanese_samurai` | 1.0 | 0.25 | 0.25, 0.0, 0.5 | 1.14 / 1.93 / 1.76 | 0 mm |
| `warrior_mongol_archer` | 1.0 | 0.45 | 0.15, 0.0, 0.4 | 1.24 / 1.79 / 1.78 | 0 mm |
| `warrior_roman_legionary` | 1.0 | 1.0 | 0.85, 0.85, 0.9 | 1.24 / 1.25 / 1.77 | 0 mm |

A size of 1 is the full move; an arm size of 0 keeps the weapon arm against the body, so the weapon moves with the body's lean and twist. The edge measures are from the Blender build; the node check, which samples every frame of every clip, agrees: no edge over 2x in any of the 11 files.

## What the coordinator needs to wire

Nothing is wired yet: `index.html`, `shared/`, the manifest and the tests are untouched. The page's own
pattern applies (`SkeletonUtils.clone`, `AnimationMixer`, `frustumCulled = false` on skinned meshes, as in the
`Monster` class in `index.html`).

1. **Museum night mode (108 Hallam Row, `galleries`, the shift from 20:00 to 23:00).** Today six code-made
   statues stand on 0.6 m plinths at `MUSEUM.homes`. Suggested wiring:
   - **T. rex.** Place it at real size down the middle of the hall, for example at (0, 0, −8) facing +Z
     toward the door. It is 12 m long and 3.3 m wide, so it fits between the plinth rows at x = ±4.4. While
     unwatched it plays `idle`, then `walk` (code moves it, at about 1.5 to 2 m/s for this cycle) and `roar`
     when it is close. When the player looks back, it plays `return_to_pose` and holds its last frame. It is
     not solid today; give it a box collider if it should block the player.
   - **Warriors.** The models are toy-sized dioramas, about 0.45 m tall and as made. Either stand them on
     the plinths as they are, as miniatures, or scale them in code, for example 3.5× for life size, if they
     replace the six statues. There are eight warriors and six homes, so pick six or add two plinths. Use the
     same watched or unwatched rule as the statues:
     - unwatched and moving: `march`, turned toward the player;
     - next to the player: `attack`;
     - watched: crossfade to `freeze` and hold it;
     - set back by F: snap to the plinth and play `freeze`.

     The plaques would read with the names in the table.
2. **The stalker (`street`, 00:00 to 06:00).** Replace the box figure from `stalkerMesh()` with
   `models/characters/stalker.glb`. Keep it out of `monsters`, as now, so that nothing touches it.
   - It is 1.7 m tall in the file. Today's figure is 2.3 m tall, so scale it by 1.35 in code if the height
     should stay.
   - While the player looks at it, crossfade to `freeze` and hold it. When unseen and following, play
     `stalk`. When moving fast, play `walk`. When standing, play `idle`.
   - It faces +Z. The box figure faced −Z (its eyes are at z −0.16), so drop the `+ Math.PI` from the yaw in
     `stalkerTick`.
3. **The Mawcrawler (a new monster kind).** Load `models/characters/mawcrawler.glb` as a mob that spawns at
   random. When it spawns, play `spawn` once at the spawn point; the clip rises 1.75 m out of the floor and
   ends standing. Then switch to the `crawl` and `idle` loops. `lunge` is its attack: the clip moves it
   about 0.65 m forward and back again, and the bite lands at about 0.8 s.
   - The `Monster` class in `index.html` finds `idle`, and `crawl` through its walk regex. Set
     `anim: {attack: "lunge", run: "crawl"}` in its config.
   - Check `yawOffset`: the class defaults to π, but this file faces +Z, so it probably wants 0.
   - Its rules (where it spawns, how often, its speed, and whether it can be killed) are not in
     `docs/ITEMS.md` yet. They are the coordinator's or the owner's call.
4. All the files are optional to the page: keep the code-made figures as the fallback when a load fails, as
   for the other models.
