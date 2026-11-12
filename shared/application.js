// The job application quiz (City slice 3). One engine for every job: a quiz is rounds, each round has items to drag and bins to drop them in. Answer a graded round wrong and you are
// rejected; answer them all right and you are accepted. A round with `graded: false` only records what you said (the intrusive questions come that way). One application at a time.
// Pure rules here and in tests; index.html draws the overlay and keeps the state. Only the Intern has a quiz so far: the other four jobs are "not hiring yet".

// A round: {id, title, prompt, items: [{id, label}], bins: [{id, label}], answer: {itemId: binId}, graded}. The Intern's rounds follow docs/WORLD.md: sort tasks, match a form to a day, then something more intrusive.
export const QUIZZES = {
  intern: {
    job: "The Intern", address: "666 HALLAM ROW", flag: "job_intern",
    rounds: [
      {id: "tasks", title: "1 of 3: SORT THE TASKS", prompt: "Interns fetch, file and watch. Interns do not decide. Drag each task to where it belongs.", graded: true,
        items: [{id: "coffee", label: "Fetch the coffee"}, {id: "boxes", label: "Label the file boxes"}, {id: "monitor", label: "Watch the lobby monitor"}, {id: "doors", label: "Open the locked doors"}, {id: "reports", label: "Approve the incident reports"}],
        bins: [{id: "mine", label: "An intern's task"}, {id: "notmine", label: "Not an intern's task"}],
        answer: {coffee: "mine", boxes: "mine", monitor: "mine", doors: "notmine", reports: "notmine"}},
      {id: "forms", title: "2 of 3: MATCH THE FORM TO THE DAY", prompt: "Visitor badges are issued on Mondays. Supplies are ordered in the middle of the week. Incidents are reported at the end of it.", graded: true,
        items: [{id: "badge", label: "Visitor badge"}, {id: "supply", label: "Supply order"}, {id: "incident", label: "Incident report"}],
        bins: [{id: "mon", label: "Monday"}, {id: "wed", label: "Wednesday"}, {id: "fri", label: "Friday"}],
        answer: {badge: "mon", supply: "wed", incident: "fri"}},
      {id: "notice", title: "3 of 3: A FEW QUESTIONS FOR OUR RECORDS", prompt: "There are no wrong answers. Who would notice if you were gone?", graded: false,
        items: [{id: "neighbour", label: "A neighbour"}, {id: "friend", label: "A friend"}, {id: "landlord", label: "Your landlord"}, {id: "family", label: "Your family"}],
        bins: [{id: "yes", label: "Would notice"}, {id: "no", label: "Would not notice"}]},
    ],
  },
};
export const hasQuiz = job => Object.prototype.hasOwnProperty.call(QUIZZES, job);

// Grade a finished quiz. `answers` is {roundId: {itemId: binId}}. Every item of every round must be placed. Returns {complete, pass, wrong: ["roundId.itemId", ...]}:
// pass needs every graded round right; an ungraded round only has to be complete. A bin or item that is not in the round counts as wrong (or missing), never as a pass.
export function grade(quiz, answers) {
  const wrong = []; let complete = true;
  for (const r of quiz.rounds) {
    const a = (answers && answers[r.id]) || {}, bins = new Set(r.bins.map(b => b.id));
    for (const it of r.items) {
      const put = a[it.id];
      if (put === undefined) { complete = false; continue; }
      if (!bins.has(put)) { wrong.push(`${r.id}.${it.id}`); continue; }
      if (r.graded && r.answer[it.id] !== put) wrong.push(`${r.id}.${it.id}`);
    }
  }
  return {complete, pass: complete && wrong.length === 0, wrong};
}

// The state of applications: {active: jobId | null, rejectedOn: {jobId: day}, accepted: {jobId: true}}. All of these return a new state and never mutate.
export const newApplications = () => ({active: null, rejectedOn: {}, accepted: {}});
export function canApply(state, job, day) {
  if (!hasQuiz(job)) return {ok: false, reason: "not hiring yet"};
  if (state.accepted[job]) return {ok: false, reason: "already accepted"};
  if (state.active) return {ok: false, reason: "one application at a time"};
  if (state.rejectedOn[job] !== undefined && state.rejectedOn[job] >= day) return {ok: false, reason: "rejected: you may apply again tomorrow"};
  return {ok: true, reason: ""};
}
export const begin = (state, job, day) => canApply(state, job, day).ok ? {...state, active: job} : state;
export const abandon = state => ({...state, active: null});                                          // closing the quiz half way counts as nothing
export function finish(state, job, result, day) {
  if (state.active !== job) return state;
  return result.pass ? {...state, active: null, accepted: {...state.accepted, [job]: true}} : {...state, active: null, rejectedOn: {...state.rejectedOn, [job]: day}};
}
// what the Mail page says about your applications (the computer shows these under the empty-inbox line)
export function mailLines(state, day) {
  const out = [];
  for (const job of Object.keys(QUIZZES)) {
    const q = QUIZZES[job];
    if (state.accepted[job]) out.push(`ACCEPTED: ${q.job}, ${q.address}.`, "Report to the front door any time the store is open. We have noted your answers.", "");
    else if (state.rejectedOn[job] !== undefined) out.push(`REJECTED: ${q.job}, ${q.address}.`, state.rejectedOn[job] >= day ? "Thank you for your interest. You may apply again tomorrow." : "Thank you for your interest. You may apply again.", "");
  }
  return out;
}
