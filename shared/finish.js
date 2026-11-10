// The end of a round: players walk out of the L4 store into the parking lot, and the lot is the lobby. The round is over when everyone still
// in the room is out; the order they left in is their place. Pure functions; nothing here mutates its input.
export const ALARM_MS = 60000;
export const newRun = startedAt => ({startedAt, exits: [], ended: false});
// Returns {run, entry} or null (no run, already over, already out).
export function exitPlayer(run, id, now, name = "Player") {
  if (!run || run.ended || run.exits.some(e => e.id === id)) return null;
  const entry = {id, name: String(name).slice(0, 16), place: run.exits.length + 1, ms: Math.max(0, Math.round(now - run.startedAt))};
  return {run: {...run, exits: [...run.exits, entry]}, entry};
}
// True when the round is not already over and every id in `active` has left (and there is at least one).
export const done = (run, active) => !!run && !run.ended && active.length > 0 && active.every(id => run.exits.some(e => e.id === id));
export const finish = run => ({...run, ended: true});
export const results = run => run.exits.map(e => ({...e}));
export const fmtTime = ms => `${Math.floor(ms / 60000)}:${String(Math.floor(ms / 1000) % 60).padStart(2, "0")}`;

// ---- the score and the run record (RND-21, RND-27)
// PLACEHOLDER numbers: the owner has not confirmed them. They live here and nowhere else, so changing the formula means changing this one object.
export const SCORE = {base: 1000, perRevive: 150, perDeath: 100, perStepMs: 5000, perStep: 1};
// 1000, plus 150 per revive, minus 100 per death, minus 1 per 5 s of round time, never below 0
export const score = ({deaths = 0, revives = 0, ms = 0}) =>
  Math.max(0, SCORE.base + SCORE.perRevive * revives - SCORE.perDeath * deaths - SCORE.perStep * Math.floor(Math.max(0, ms) / SCORE.perStepMs));
// One finished round as plain data. `players` are {char, place, ms, downs, deaths, revives, shots} (extra fields, names above all, are dropped on purpose:
// the log carries no player names). `floors` are [{scene, ms}] in the order the room first used them.
export function runRecord({roomCode, mode, startedAt, endedAt, floors = [], players = []}) {
  const int = v => Math.max(0, Math.round(Number(v) || 0));
  return {
    roomCode: String(roomCode), mode: String(mode), startedAt, endedAt,
    floors: floors.map(f => ({scene: String(f.scene), ms: int(f.ms)})),
    players: players.map(p => ({char: p.char, place: p.place, ms: int(p.ms), downs: int(p.downs), deaths: int(p.deaths), revives: int(p.revives), shots: int(p.shots),
      score: score({deaths: int(p.deaths), revives: int(p.revives), ms: int(p.ms)})})).sort((a, b) => a.place - b.place),
  };
}
