import test from "node:test";
import assert from "node:assert/strict";
import {QUIZZES, hasQuiz, grade, newApplications, canApply, begin, abandon, finish, mailLines} from "./application.js";

const Q = QUIZZES.intern;
const right = () => ({tasks: Q.rounds[0].answer, forms: Q.rounds[1].answer, notice: {neighbour: "yes", friend: "no", landlord: "yes", family: "no"}});

test("every round of every quiz is well formed: each graded answer names a real item and a real bin", () => {
  assert.equal(Q.flag, "job_intern");
  for (const q of Object.values(QUIZZES)) for (const r of q.rounds) {
    assert.ok(r.items.length >= 3 && r.bins.length >= 2);
    if (r.graded) { assert.deepEqual(Object.keys(r.answer).sort(), r.items.map(i => i.id).sort()); for (const b of Object.values(r.answer)) assert.ok(r.bins.some(x => x.id === b)); }
  }
  for (const q of Object.values(QUIZZES)) assert.equal(q.rounds.filter(r => !r.graded).length, 1, q.job + ": one intrusive round that has no wrong answer");
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

test("the other four jobs (slice 6): each has its own flag, and right answers pass while one wrong one fails", () => {
  assert.deepEqual(Object.keys(QUIZZES), ["intern", "trash", "museum", "lab", "factory"]);
  assert.deepEqual(Object.values(QUIZZES).map(q => q.flag), ["job_intern", "job_trash", "job_museum", "job_lab", "job_factory"]);
  for (const [job, q] of Object.entries(QUIZZES)) {
    const right = Object.fromEntries(q.rounds.map(r => [r.id, r.graded ? r.answer : Object.fromEntries(r.items.map(it => [it.id, r.bins[0].id]))]));
    assert.equal(grade(q, right).pass, true, job + " right");
    const g = q.rounds.find(r => r.graded), it = g.items[0], other = g.bins.find(b => b.id !== g.answer[it.id]).id;
    const wrong = {...right, [g.id]: {...g.answer, [it.id]: other}};
    assert.deepEqual(grade(q, wrong).wrong, [`${g.id}.${it.id}`], job + " wrong");
  }
});
test("one application at a time holds across jobs, and you can hold more than one job", () => {
  let s = begin(newApplications(), "trash", 1);
  assert.match(canApply(s, "lab", 1).reason, /one application/);
  s = finish(s, "trash", {pass: true}, 1); s = finish(begin(s, "lab", 1), "lab", {pass: true}, 1);
  assert.deepEqual(s.accepted, {trash: true, lab: true});
});
