# models/world/

The owner's Meshy models for buildings and large set pieces of the world, waiting for the scenes they belong in. Nothing here is loaded by the game yet.

| File | What | Goes in | Size |
|---|---|---|---|
| `shed.glb` | The shed: a two-storey scrap-wood shack on brick footings, a porch with steps, a white tree mark beside the door (Meshy: "Stylized post-apocalyptic") | The meadow of the dreamcore forest, with the Dreamcore house (`docs/WORLD.md`, "Dreamcore forest and house"; the manifest's `dreamcore_forest` area, still planned, and its `forest.shed>addon` link) | 9,890 triangles, 4.5 MB |

## How they were prepared

As for `models/items/`: every texture re-saved as WebP at quality 95 with `python3 tools/webp_glb.py in.glb out.glb 95`; the mesh is untouched (the tool checks the geometry bytes) and nothing was resized. The shed's export has four 2048 px maps (base colour, normal, metallic-roughness and a near-black emissive map), three JPEG and one PNG: 14.8 MB became 4.5 MB.

The model is normalised to about 1.9 units on each side, centred, with Y up. It needs a scale and a facing when it is placed.
