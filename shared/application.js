// The job application quiz (City slice 3). One engine for every job: a quiz is rounds, each round has items to drag and bins to drop them in. Answer a graded round wrong and you are
// rejected; answer them all right and you are accepted. A round with `graded: false` only records what you said (the intrusive questions come that way). One application at a time.
// Pure rules here and in tests; index.html draws the overlay and keeps the state. Every Hallam Row job has a quiz (slice 6 added the other four); only the Intern has a job game, the others' shifts are stubs.

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
  // slice 6: the other four jobs on Hallam Row. Their job games are not built, so a shift there is a stub (shared/pay.js STUB_SHIFTS); the application is real.
  trash: {
    job: "Trash truck worker", address: "41 HALLAM ROW", flag: "job_trash",
    rounds: [
      {id: "sort", title: "1 of 3: SORT THE LOAD", prompt: "Glass and paper are recycled. Food goes to compost. Everything else goes to the landfill.", graded: true,
        items: [{id: "bottle", label: "A glass bottle"}, {id: "paper", label: "Yesterday's newspaper"}, {id: "peel", label: "A banana peel"}, {id: "mirror", label: "A broken mirror"}, {id: "bag", label: "An empty crisp bag"}],
        bins: [{id: "recycle", label: "Recycling"}, {id: "compost", label: "Compost"}, {id: "landfill", label: "Landfill"}],
        answer: {bottle: "recycle", paper: "recycle", peel: "compost", mirror: "landfill", bag: "landfill"}},
      {id: "route", title: "2 of 3: THE ROUTE", prompt: "Hallam Row is collected on Mondays. The depot is cleaned on Wednesdays. The truck is serviced on Fridays.", graded: true,
        items: [{id: "row", label: "Collect Hallam Row"}, {id: "depot", label: "Clean the depot"}, {id: "truck", label: "Service the truck"}],
        bins: [{id: "mon", label: "Monday"}, {id: "wed", label: "Wednesday"}, {id: "fri", label: "Friday"}],
        answer: {row: "mon", depot: "wed", truck: "fri"}},
      {id: "found", title: "3 of 3: WHAT YOU FIND", prompt: "There are no wrong answers. Sometimes the bins hold things. What do you do with them?", graded: false,
        items: [{id: "wallet", label: "A wallet"}, {id: "key", label: "A door key"}, {id: "photo", label: "A photograph of you"}],
        bins: [{id: "hand", label: "Hand it in"}, {id: "keep", label: "Keep it"}]},
    ],
  },
  museum: {
    job: "Museum night guard", address: "108 HALLAM ROW", flag: "job_museum",
    rounds: [
      {id: "rooms", title: "1 of 3: WHERE THINGS BELONG", prompt: "Anything older than paper is in the ancient hall. Pictures hang in the gallery.", graded: true,
        items: [{id: "spear", label: "A bronze spearhead"}, {id: "tablet", label: "A clay tablet"}, {id: "portrait", label: "An oil portrait"}, {id: "sketch", label: "A charcoal sketch"}],
        bins: [{id: "ancient", label: "Ancient hall"}, {id: "gallery", label: "Gallery"}],
        answer: {spear: "ancient", tablet: "ancient", portrait: "gallery", sketch: "gallery"}},
      {id: "rules", title: "2 of 3: IF SOMETHING MOVES", prompt: "Guards write everything in the log and keep the lights on. Guards never touch the exhibits, and never look away from one that has moved.", graded: true,
        items: [{id: "log", label: "Write it in the log"}, {id: "lights", label: "Turn the lights on"}, {id: "touch", label: "Touch it"}, {id: "away", label: "Look away"}],
        bins: [{id: "do", label: "Do"}, {id: "dont", label: "Do not"}],
        answer: {log: "do", lights: "do", touch: "dont", away: "dont"}},
      {id: "watch", title: "3 of 3: A FEW QUESTIONS FOR OUR RECORDS", prompt: "There are no wrong answers. Which of these have watched you?", graded: false,
        items: [{id: "statue", label: "A statue"}, {id: "painting", label: "A painting"}, {id: "window", label: "A lit window"}, {id: "nobody", label: "Nobody"}],
        bins: [{id: "yes", label: "Has watched me"}, {id: "no", label: "Has not"}]},
    ],
  },
  lab: {
    job: "Laboratory worker", address: "214 HALLAM ROW", flag: "job_lab",
    rounds: [
      {id: "caps", title: "1 of 3: SORT THE SAMPLES", prompt: "Red caps are biological. Yellow caps are chemical. Blue caps are unknown: they go to the sealed room.", graded: true,
        items: [{id: "red", label: "A vial with a red cap"}, {id: "yellow", label: "A vial with a yellow cap"}, {id: "blue", label: "A vial with a blue cap"}, {id: "red2", label: "A jar with a red cap"}],
        bins: [{id: "bio", label: "Biological"}, {id: "chem", label: "Chemical"}, {id: "sealed", label: "Sealed room"}],
        answer: {red: "bio", yellow: "chem", blue: "sealed", red2: "bio"}},
      {id: "clearance", title: "2 of 3: WHICH DOOR", prompt: "Level 1 opens the front lab. Level 2 opens the cold room. Level 3 opens the sublevel.", graded: true,
        items: [{id: "l1", label: "Level 1 badge"}, {id: "l2", label: "Level 2 badge"}, {id: "l3", label: "Level 3 badge"}],
        bins: [{id: "front", label: "Front lab"}, {id: "cold", label: "Cold room"}, {id: "sub", label: "Sublevel"}],
        answer: {l1: "front", l2: "cold", l3: "sub"}},
      {id: "left", title: "3 of 3: A FEW QUESTIONS FOR OUR RECORDS", prompt: "There are no wrong answers. Have you ever been somewhere you could not leave?", graded: false,
        items: [{id: "store", label: "A store at night"}, {id: "hotel", label: "A hotel corridor"}, {id: "dream", label: "A dream"}, {id: "here", label: "Here"}],
        bins: [{id: "yes", label: "Yes"}, {id: "no", label: "No"}]},
    ],
  },
  factory: {
    job: "Factory floor worker", address: "330 HALLAM ROW", flag: "job_factory",
    rounds: [
      {id: "parts", title: "1 of 3: SORT THE PARTS", prompt: "Bolts go in the grey bin. Springs go in the blue bin. Anything still warm goes back to the line.", graded: true,
        items: [{id: "hex", label: "A hex bolt"}, {id: "coil", label: "A coil spring"}, {id: "warm", label: "A part that is still warm"}, {id: "carriage", label: "A carriage bolt"}, {id: "leaf", label: "A leaf spring"}],
        bins: [{id: "grey", label: "Grey bin"}, {id: "blue", label: "Blue bin"}, {id: "line", label: "Back to the line"}],
        answer: {hex: "grey", coil: "blue", warm: "line", carriage: "grey", leaf: "blue"}},
      {id: "start", title: "2 of 3: STARTING A SHIFT", prompt: "Clock in first. Then wash your hands, then put on your gloves. Only then start the line.", graded: true,
        items: [{id: "clock", label: "Clock in"}, {id: "wash", label: "Wash your hands"}, {id: "gloves", label: "Put on your gloves"}, {id: "line", label: "Start the line"}],
        bins: [{id: "1", label: "First"}, {id: "2", label: "Second"}, {id: "3", label: "Third"}, {id: "4", label: "Fourth"}],
        answer: {clock: "1", wash: "2", gloves: "3", line: "4"}},
      {id: "still", title: "3 of 3: A FEW QUESTIONS FOR OUR RECORDS", prompt: "There are no wrong answers. How long could you stand still at the line?", graded: false,
        items: [{id: "minute", label: "A minute"}, {id: "hour", label: "An hour"}, {id: "shift", label: "A whole shift"}, {id: "forever", label: "Forever"}],
        bins: [{id: "yes", label: "I could"}, {id: "no", label: "I could not"}]},
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
