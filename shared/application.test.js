import test from "node:test";
import assert from "node:assert/strict";
import {QUIZZES, hasQuiz, grade, newApplications, canApply, begin, abandon, finish, mailLines} from "./application.js";

const Q = QUIZZES.intern;
const right = () => ({tasks: Q.rounds[0].answer, forms: Q.rounds[1].answer, notice: {neighbour: "yes", friend: "no", landlord: "yes", family: "no"}});

test("every round is well formed: each graded answer names a real item and a real bin", () => {
  assert.equal(Q.flag, "job_intern");
  for (const r of Q.rounds) {
    assert.ok(r.items.length >= 3 && r.bins.length >= 2);
    if (r.graded) { assert.deepEqual(Object.keys(r.answer).sort(), r.items.map(i => i.id).sort()); for (const b of Object.values(r.answer)) assert.ok(r.bins.some(x => x.id === b)); }
  }
  assert.equal(Q.rounds.filter(r => !r.graded).length, 1, "one intrusive round that has no wrong answer");
});
test("all graded rounds right is a pass; the ungraded round takes any answer", () => {
  const g = grade(Q, right()); assert.deepEqual(g, {complete: true, pass: true, wrong: []});
  const other = right(); other.notice = {neighbour: "no", friend: "no", landlord: "no", family: "no"};
  assert.equal(grade(Q, other).pass, true, "nobody would notice: still accepted");
});
test("one wrong placement in a graded round is a rejection and says which", () => {
  const a = right(); a.tasks = {...a.tasks, doors: "mine"};
  const g = grade(Q, a); assert.equal(g.pass, false); assert.equal(g.complete, true); assert.deepEqual(g.wrong, ["tasks.doors"]);
  const b = right(); b.forms = {badge: "fri", supply: "wed", incident: "mon"};
  assert.deepEqual(grade(Q, b).wrong, ["forms.badge", "forms.incident"]);
});
test("an unfinished quiz is not complete and never passes", () => {
  const a = right(); delete a.notice.family; assert.deepEqual([grade(Q, a).complete, grade(Q, a).pass], [false, false]);
  assert.equal(grade(Q, {}).pass, false); assert.equal(grade(Q, undefined).complete, false);
  const bad = right(); bad.tasks = {...bad.tasks, coffee: "no_such_bin"}; assert.equal(grade(Q, bad).pass, false, "a bin that is not in the round is wrong");
});
test("one application at a time, only jobs with a quiz, and a rejection waits until tomorrow", () => {
  let s = newApplications();
  assert.equal(canApply(s, "intern", 1).ok, true); assert.match(canApply(s, "w41", 1).reason, /not hiring/); assert.equal(hasQuiz("w41"), false);
  s = begin(s, "intern", 1); assert.equal(s.active, "intern"); assert.match(canApply(s, "intern", 1).reason, /one application/);
  assert.equal(begin(s, "intern", 1), s, "starting a second one changes nothing");
  s = finish(s, "intern", {pass: false}, 1); assert.equal(s.active, null);
  assert.match(canApply(s, "intern", 1).reason, /tomorrow/); assert.equal(canApply(s, "intern", 2).ok, true, "the next game day it is open again");
  s = finish(begin(s, "intern", 2), "intern", {pass: true}, 2); assert.equal(s.accepted.intern, true); assert.match(canApply(s, "intern", 3).reason, /already accepted/);
});
test("closing the quiz half way counts as nothing, and finishing something you did not start does nothing", () => {
  let s = begin(newApplications(), "intern", 1); s = abandon(s); assert.equal(s.active, null); assert.deepEqual(s.rejectedOn, {}); assert.equal(canApply(s, "intern", 1).ok, true);
  const t = newApplications(); assert.equal(finish(t, "intern", {pass: true}, 1), t);
});
test("the mail says accepted or rejected, and by when you may try again", () => {
  assert.deepEqual(mailLines(newApplications(), 1), []);
  const rej = finish(begin(newApplications(), "intern", 1), "intern", {pass: false}, 1);
  assert.match(mailLines(rej, 1).join("\n"), /REJECTED.*666 HALLAM ROW[\s\S]*again tomorrow/); assert.match(mailLines(rej, 2).join("\n"), /may apply again\./);
  const acc = finish(begin(newApplications(), "intern", 1), "intern", {pass: true}, 1);
  assert.match(mailLines(acc, 1).join("\n"), /ACCEPTED: The Intern/);
});
