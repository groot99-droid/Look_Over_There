// The Going back in loadout and its locker (GBI-7): which gear you carry and which is in the locker. No graphics here.
// Rule from docs/WORLD.md ("Death in Going back in"): after a death the locker returns your weapons and gear for free; it does NOT return ammo, consumables or perks
// (the page zeroes those; this file only moves gear). Gear in v1: the ray, the cloak and the hunting crossbow (GEAR, which a room runs), and in solo play the pneumatic bolt driver too (SOLO_GEAR, docs/ITEMS.md). A beacon is counted as charges, so it is lost like ammo.
export const GEAR = ["gun", "cloak", "crossbow"];                         // what a room runs (the server owns these: session 16)
export const SOLO_GEAR = [...GEAR, "driver"];                            // solo Going back in: the arsenal weapons the server does not run yet come after (docs/ITEMS.md)
export const newLoadout = (carry = null, gear = GEAR) => { const c = carry || gear; return {carry: [...c], stash: gear.filter(g => !c.includes(g))}; };
export const carries = (l, g) => l.carry.includes(g);
const has = (l, g) => SOLO_GEAR.includes(g) && (l.carry.includes(g) || l.stash.includes(g));
// at the locker: pick a piece of gear up, or leave it there (ammo stays on you either way). Returns the new loadout; the same one if it is not possible.
export const take = (l, g) => l.stash.includes(g) ? {carry: [...l.carry, g], stash: l.stash.filter(x => x !== g)} : l;
export const leave = (l, g) => l.carry.includes(g) ? {carry: l.carry.filter(x => x !== g), stash: [...l.stash, g]} : l;
// a death: everything you carried is in the locker (nothing is lost), and you carry nothing until you walk to a locker and take it back
export const died = l => ({carry: [], stash: SOLO_GEAR.filter(g => has(l, g))});
