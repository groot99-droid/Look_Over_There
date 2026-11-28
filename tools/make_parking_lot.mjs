// Superseded (2026-11-27): world/parking_lot.json is now the Overworld lot's own layout, written from Blender by
// tools/blender/build_overworld_lot.py through tools/blender/export_scene.py (the model is build_overworld_greybox.py's `parking_lot()`).
// It used to be made here from world/L4.json, with the Right Door, Wrong Exit gate and the Intern's city in it; running that now would undo
// the lot scene, so this script only says where the layout comes from. See docs/renders/parking_lot/README.md.
console.error("world/parking_lot.json is built in Blender now: blender -b --factory-startup --python tools/blender/build_overworld_lot.py -- --stage art");
process.exit(1);
