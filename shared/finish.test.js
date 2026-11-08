import test from "node:test";
import assert from "node:assert/strict";
import {newRun, exitPlayer, done, finish, results, fmtTime, SCORE, score, runRecord} from "./finish.js";

test("places go in the order players leave, with their time", () => {
  let run = newRun(1000);
  const a = exitPlayer(run, 7, 61000, "Ann"); run = a.run;
  assert.deepEqual(a.entry, {id: 7, name: "Ann", place: 1, ms: 60000});
  const b = exitPlayer(run, 3, 95000, "Bo"); run = b.run;
  assert.equal(b.entry.place, 2); assert.deepEqual(results(run).map(r => r.id), [7, 3]);
});
test("leaving twice changes nothing; no run or an ended run refuses", () => {
  const run = exitPlayer(newRun(0), 1, 10, "A").run;
  assert.equal(exitPlayer(run, 1, 20, "A"), null);
  assert.equal(exitPlayer(null, 1, 20), null);
  assert.equal(exitPlayer(finish(run), 2, 20), null);
});
test("the round is done when everyone still present is out, once", () => {
  let run = newRun(0);
  assert.equal(done(run, [1, 2]), false);
  run = exitPlayer(run, 1, 5).run; assert.equal(done(run, [1, 2]), false);
  assert.equal(done(run, [1]), true, "the one who is left behind has left the room");
  assert.equal(done(run, []), false);
  run = exitPlayer(run, 2, 9).run; assert.equal(done(run, [1, 2]), true);
  assert.equal(done(finish(run), [1, 2]), false, "already announced");
});
test("input is never mutated and times format as m:ss", () => {
  const run = newRun(0), frozen = JSON.stringify(run);
  exitPlayer(run, 1, 5); assert.equal(JSON.stringify(run), frozen);
  assert.equal(fmtTime(0), "0:00"); assert.equal(fmtTime(65400), "1:05"); assert.equal(fmtTime(3725000), "62:05");
});

test("score: 1000, +150 per revive, -100 per death, -1 per 5 s, never below 0 (RND-27 placeholder)", () => {
  assert.deepEqual(SCORE, {base: 1000, perRevive: 150, perDeath: 100, perStepMs: 5000, perStep: 1});
  assert.equal(score({}), 1000);
  assert.equal(score({deaths: 2, revives: 3, ms: 600000}), 1000 + 450 - 200 - 120, "10 minutes is 120 steps of 5 s");
  assert.equal(score({ms: 4999}), 1000, "a step counts only when it is whole"); assert.equal(score({ms: 5000}), 999);
  assert.equal(score({deaths: 50}), 0, "never below 0");
});
test("run record: the fields in RND-21, ordered by place, scored, and without names", () => {
  const rec = runRecord({roomCode: "ABC", mode: "original", startedAt: 1000, endedAt: 901000, floors: [{scene: "B1", ms: 300000.4}, {scene: "L1", ms: 600000}],
    players: [{id: 9, name: "Bob", char: 1, place: 2, ms: 800000, downs: 4, deaths: 3, revives: 0, shots: 7, hits: 2},
              {id: 8, name: "Ann", char: 0, place: 1, ms: 700000, downs: 5, deaths: 1, revives: 3, shots: 12}]});
  assert.deepEqual(rec, {roomCode: "ABC", mode: "original", startedAt: 1000, endedAt: 901000,
    floors: [{scene: "B1", ms: 300000}, {scene: "L1", ms: 600000}],
    players: [{char: 0, place: 1, ms: 700000, downs: 5, deaths: 1, revives: 3, shots: 12, score: 1000 + 450 - 100 - 140},
              {char: 1, place: 2, ms: 800000, downs: 4, deaths: 3, revives: 0, shots: 7, score: 1000 - 300 - 160}]});
  assert.ok(!/Ann|Bob|name|"id"/.test(JSON.stringify(rec)), "no player names or ids");
});
test("run record: missing or bad numbers become 0 and the input is not changed", () => {
  const input = {roomCode: "X", mode: "original", startedAt: 0, endedAt: 5, players: [{char: 2, place: 1, ms: -5, downs: "x"}]}, frozen = JSON.stringify(input);
  const rec = runRecord(input); assert.deepEqual(rec.players[0], {char: 2, place: 1, ms: 0, downs: 0, deaths: 0, revives: 0, shots: 0, score: 1000}); assert.deepEqual(rec.floors, []);
  assert.equal(JSON.stringify(input), frozen);
});
