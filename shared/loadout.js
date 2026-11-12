// The Going back in loadout and its locker (GBI-7): which gear you carry and which is in the locker. No graphics here.
// Rule from docs/WORLD.md ("Death in Going back in"): after a death the locker returns your weapons and gear for free; it does NOT return ammo, consumables or perks
// (the page zeroes those; this file only moves gear). Gear in v1: the ray, the cloak and the hunting crossbow. A beacon is counted as charges, so it is lost like ammo.
export const GEAR = ["gun", "cloak", "crossbow"];
export const newLoadout = (carry = GEAR) => ({carry: [...carry], stash: GEAR.filter(g => !carry.includes(g))});
export const carries = (l, g) => l.carry.includes(g);
const has = (l, g) => GEAR.includes(g) && (l.carry.includes(g) || l.stash.includes(g));
// at the locker: pick a piece of gear up, or leave it there (ammo stays on you either way). Returns the new loadout; the same one if it is not possible.
export const take = (l, g) => l.stash.includes(g) ? {carry: [...l.carry, g], stash: l.stash.filter(x => x !== g)} : l;
export const leave = (l, g) => l.carry.includes(g) ? {carry: l.carry.filter(x => x !== g), stash: [...l.stash, g]} : l;
// a death: everything you carried is in the locker (nothing is lost), and you carry nothing until you walk to a locker and take it back
export const died = l => ({carry: [], stash: GEAR.filter(g => has(l, g))});
