// Pay for a shift at a job (City slice 5): it scales with how the shift went, as docs/WORLD.md says ("Pay scales with performance").
// For the Intern the game reports its result when it ends (games/intern/src/main.js posts it with "intern-ending"): the ending, conformance (-8..+8),
// dissonance (0..7), friction from the mini-games (0..8) and whether you quit early. The company pays for compliance and docks for friction.
// Pure: the page passes the posted result in, and this never trusts it (every field is checked and clamped). Defaults for the owner to change: the table below.
export const PAY = {
  base: {ASSIMILATION: 20, RETAINED: 14, PENDING: 8, EXPULSION: 4},   // by ending
  perConformance: 1,       // + per point of conformance above 0
  perFriction: 1,          // - per point of friction (rounded)
  quit: 0,                 // quitting early (the game's bail) pays nothing
  max: 30,
};
const num = (v, lo, hi) => { const n = Number(v); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : 0; };

// What the shift pays and why. `result` is the game's {ending, conformance, dissonance, friction, early}; anything missing or malformed counts as a
// PENDING shift with no bonus and no docking, so an older game that only says it ended still pays the PENDING base.
export function shiftPay(result) {
  const r = result && typeof result === "object" ? result : {};
  const ending = Object.prototype.hasOwnProperty.call(PAY.base, r.ending) ? r.ending : "PENDING";
  if (r.early === true) return {pay: PAY.quit, ending, lines: [`Shift: ${ending}`, "You left early. No pay."]};
  const conf = Math.round(num(r.conformance, -8, 8)), fric = Math.round(num(r.friction, 0, 8));
  const base = PAY.base[ending], bonus = Math.max(0, conf) * PAY.perConformance, dock = fric * PAY.perFriction;
  const pay = Math.min(PAY.max, Math.max(0, base + bonus - dock));
  const lines = [`Shift: ${ending}`, `Base: $${base}`];
  if (bonus) lines.push(`Compliance bonus: +$${bonus}`);
  if (dock) lines.push(`Friction: -$${dock}`);
  lines.push(`Paid: $${pay}`);
  return {pay, ending, lines};
}
