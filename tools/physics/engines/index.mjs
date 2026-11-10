export const load = async name => (await (name === "rapier" ? import("./rapier.mjs") : import("./cannon.mjs"))).create();
