// The Q and E consumable slots of Going back in (GBI-8): three single-use items from the master arsenal, each with its own rule. No graphics here.
//   Q (support):  the phosphor-core flash-vial: thrown up to FLASH_THROW_M ahead, it stuns every monster within FLASH_R of where it lands for FLASH_STUN_S. It kills nothing.
//   E (combat / objective): one of two traps, chosen at the locker.
//     almond water land mine: set down where you stand, armed after MINE_ARM_S; a monster within MINE_R of it sets it off and dies. One monster.
//     nail-bomb tripwire: armed after WIRE_ARM_S; a monster within WIRE_R sets it off, and every monster within WIRE_BLAST_R dies. The blast is loud (monsters within WIRE_NOISE_R go and look).
// Counts are capped (MAX) and start at START; each ammo pack adds one flash-vial and one of the E item. They are not returned after a death (docs/WORLD.md): `lost`.
export const KINDS = ["flash", "mine", "wire"];
export const SLOT_OF = {flash: 0, mine: 1, wire: 1};
export const MAX = {flash: 3, mine: 3, wire: 2}, START = {flash: 2, mine: 2, wire: 1};
export const FLASH_THROW_M = 6, FLASH_R = 6, FLASH_STUN_S = 6;
export const MINE_ARM_S = 1.5, MINE_R = 1.2, WIRE_ARM_S = 0.5, WIRE_R = 2.0, WIRE_BLAST_R = 3.0, WIRE_NOISE_R = 25;
export const newKit = () => ({n: {...START}, e: "mine"});
const cap = (n, k) => Math.max(0, Math.min(MAX[k], n));
export const slotKind = (kit, slot) => slot === 0 ? "flash" : slot === 1 ? kit.e : null;
// choose what the E slot holds (the locker): "mine" or "wire". The counts stay as they are.
export const setE = (kit, kind) => SLOT_OF[kind] === 1 ? {...kit, e: kind} : kit;
// what pressing a slot does to the kit: {ok: true, kind, kit} (one used), or {ok: false, why: "empty" | "no slot"}
export function useSlot(kit, slot) {
  const kind = slotKind(kit, slot); if (!kind) return {ok: false, why: "no slot"};
  if (kit.n[kind] <= 0) return {ok: false, why: "empty", kind};
  return {ok: true, kind, kit: {...kit, n: {...kit.n, [kind]: kit.n[kind] - 1}}};
}
export const addPack = kit => ({...kit, n: {...kit.n, flash: cap(kit.n.flash + 1, "flash"), [kit.e]: cap(kit.n[kit.e] + 1, kit.e)}});
export const lost = kit => ({...kit, n: {flash: 0, mine: 0, wire: 0}});
// a trap set down at x, z at time `now` (seconds)
export const placeTrap = (kind, x, z, now) => ({kind, x, z, armAt: now + (kind === "mine" ? MINE_ARM_S : WIRE_ARM_S), done: false});
// does the trap go off at `now`? monsters: [{pos: {x, z}}]. Returns null, or {kills: [monster], loud} (the trap is then spent: the caller sets done)
export function springs(trap, now, monsters) {
  if (trap.done || now < trap.armAt) return null;
  const d = m => Math.hypot(m.pos.x - trap.x, m.pos.z - trap.z);
  if (trap.kind === "mine") { const m = monsters.filter(m => d(m) <= MINE_R).sort((a, b) => d(a) - d(b))[0]; return m ? {kills: [m], loud: false} : null; }
  if (trap.kind === "wire") return monsters.some(m => d(m) <= WIRE_R) ? {kills: monsters.filter(m => d(m) <= WIRE_BLAST_R), loud: true} : null;
  return null;
}
// where a flash-vial thrown from (x, z) toward unit (dx, dz) lands: `reach` metres ahead (the page shortens it to the nearest wall)
export const flashLanding = (x, z, dx, dz, reach = FLASH_THROW_M) => [x + dx * reach, z + dz * reach];
