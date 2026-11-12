// The trash truck worker's shift (session 9, slice 11): "The job is on the street, along a route" (docs/WORLD.md). The first job game after the Intern, and blockout like the rest.
// You start at the depot (41 Hallam Row) and the route is Hallam Row itself: eight bins stand at the kerb, F at a bin empties it, and F back at the depot's door clocks you out.
// The shift has the stub's hours (4 game hours, 150 real seconds) and start window (08:00 to 16:00). Pay is by performance, like the Intern's: $2 a bin, and $4 more for all
// eight if you clock out before time is up. Running out of time, or leaving the street (the bus, a door), ends the shift and pays for the bins emptied, without the bonus.
import {DAY_S} from "./city.js";
import {STUB_SHIFTS} from "./pay.js";

// [x, z] at the kerb (x +-5.4), on both sides, clear of doors, lamp posts, the bus stop and the pedestrians (slice 8)
export const BINS = [[-5.4, -8], [5.4, -26], [-5.4, -30], [-5.4, -48], [5.4, -50], [-5.4, -76], [5.4, -84], [5.4, -112]];
export const BIN_REACH = 1.8;
export const TRASH = {perBin: 2, allBonus: 4, hours: STUB_SHIFTS.trash.hours, depot: "w41"};
export const routeEnds = t0 => t0 + TRASH.hours / 24 * DAY_S;            // the City time the shift is over

// the nearest bin you have not emptied within reach of (px, pz), or -1. `got` is the list of emptied bins' indexes.
export function nearBin(px, pz, got = []) {
  let best = -1, bd = BIN_REACH;
  BINS.forEach(([x, z], i) => { if (got.includes(i)) return; const d = Math.hypot(x - px, z - pz); if (d < bd) { bd = d; best = i; } });
  return best;
}
// how it ends: `done` = you clocked out at the depot before time; anything else (time, left) pays the bins only
export function trashPay(got, how) {
  const n = Math.max(0, Math.min(BINS.length, Math.floor(got) || 0)), all = n === BINS.length && how === "done";
  const pay = n * TRASH.perBin + (all ? TRASH.allBonus : 0);
  const lines = [`Bins emptied: ${n} of ${BINS.length}`, `$${TRASH.perBin} a bin: $${n * TRASH.perBin}`];
  if (all) lines.push(`Whole route, clocked out on time: +$${TRASH.allBonus}`);
  else if (how === "time") lines.push("Time ran out before you clocked out.");
  else if (how === "left") lines.push("You left the route.");
  lines.push(`Paid: $${pay}`);
  return {pay, n, lines, note: `Trash route ${n}/${BINS.length}`};
}
