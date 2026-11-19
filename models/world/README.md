# models/world/

The owner's Meshy models for buildings and large set pieces of the world. Both are in the game: the dreamcore meadow (`shared/forest.js`, `meadowProps` in `index.html`) stands them on the ground at their heights and turns them to face the path.

| File | What | Goes in | Size |
|---|---|---|---|
| `shed.glb` | The shed: a two-storey scrap-wood shack on brick footings, a porch with steps, a white tree mark beside the door (Meshy: "Stylized post-apocalyptic"). Its front is +Z in the file | The meadow, west of the path, front turned to face it, 6.2 m tall (`MEADOW.shed`). Locked: the `forest.shed>addon` link is still planned | 9,890 triangles, 4.5 MB |
| `cottage.glb` | The Dreamcore house from outside: a small stone cottage with a slate roof, a chimney and a porch with lit windows (Meshy: "Moonlit Cabin"). Its front door is +X in the file | The end of the meadow's path, door facing down it, 7.5 m tall (`MEADOW.house`). Its door is Right Door, Wrong Exit (`forest.house>rdwe`, solo only) | 18,254 triangles, 1.3 MB |

## How they were prepared

As for `models/items/`: every texture re-saved as WebP at quality 95 with `python3 tools/webp_glb.py in.glb out.glb 95`; the mesh is untouched (the tool checks the geometry bytes) and nothing was resized. The shed's export has four 2048 px maps (base colour, normal, metallic-roughness and a near-black emissive map), three JPEG and one PNG: 14.8 MB became 4.5 MB.

The cottage's export had one 2048 px map (2.7 MB of PNG became 0.56 MB). Both are normalised Meshy exports (about 1.9 and 0.95 units tall), centred, Y up; the page scales them to their heights.
