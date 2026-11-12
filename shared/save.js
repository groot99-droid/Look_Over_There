// Saving the City (slice 7): "A bed saves and skips the night" (docs/WORLD.md). The bed writes this record to the browser; the page reads it back at start.
// Pure: makeSave builds the record from the live state, readSave checks a stored one and returns a clean state or null. It never trusts what it reads: a missing,
// corrupt or older-version save is ignored (you start fresh, as before saving existed), every number is clamped, and unknown foods or jobs are dropped.
import {FOODS, HUNGER, REST, newNeeds} from "./needs.js";
import {QUIZZES, newApplications} from "./application.js";

export const SAVE_KEY = "city_save";
export const SAVE_VERSION = 1;
// New Game (slice 9) removes these: the save and every job's flag. `original_complete` is the Original's, not the City's, and stays.
export const NEW_GAME_KEYS = [SAVE_KEY, ...Object.values(QUIZZES).map(q => q.flag)];
const FOOD_IDS = new Set(FOODS.map(f => f.id)), JOB_IDS = new Set(Object.keys(QUIZZES));
const int = (v, lo, hi) => { const n = Number(v); return Number.isFinite(n) ? Math.min(hi, Math.max(lo, Math.round(n))) : null; };
const isObj = v => v !== null && typeof v === "object" && !Array.isArray(v);

// what the bed writes: the clock, the needs (not the cart: you are at home), and the applications
export function makeSave({t, needs, apps}) {
  return {
    v: SAVE_VERSION, t,
    needs: {hunger: needs.hunger, rest: needs.rest, money: needs.money, pantry: {...needs.pantry}, lastPay: needs.lastPay ?? null, lastNote: needs.lastNote || ""},
    apps: {rejectedOn: {...apps.rejectedOn}, accepted: {...apps.accepted}},
  };
}

// a stored save (text, as localStorage holds it) -> {t, needs, apps} ready to use, or null if there is none worth trusting
export function readSave(text) {
  let s; try { s = JSON.parse(text); } catch (e) { return null; }
  if (!isObj(s) || s.v !== SAVE_VERSION) return null;
  const t = Number(s.t); if (!Number.isFinite(t) || t < 0) return null;
  const n = isObj(s.needs) ? s.needs : {}, a = isObj(s.apps) ? s.apps : {};
  const needs = newNeeds();
  const h = Number(n.hunger); needs.hunger = Number.isFinite(h) ? Math.min(HUNGER.max, Math.max(0, h)) : needs.hunger;
  const r = Number(n.rest); needs.rest = n.rest !== undefined && n.rest !== null && Number.isFinite(r) ? Math.min(REST.max, Math.max(0, r)) : needs.rest;     // slice 12: a save from before rest existed starts rested
  needs.money = int(n.money, 0, 1e6) ?? needs.money;
  if (isObj(n.pantry)) for (const [id, c] of Object.entries(n.pantry)) if (FOOD_IDS.has(id)) { const k = int(c, 0, 999); if (k) needs.pantry[id] = k; }
  needs.lastPay = n.lastPay === null || n.lastPay === undefined ? null : int(n.lastPay, 0, 1e6);
  needs.lastNote = typeof n.lastNote === "string" ? n.lastNote.slice(0, 40) : "";
  const apps = newApplications();
  if (isObj(a.rejectedOn)) for (const [job, d] of Object.entries(a.rejectedOn)) if (JOB_IDS.has(job)) { const k = int(d, 0, 1e6); if (k >= 1) apps.rejectedOn[job] = k; }      // days start at 1: anything else is dropped, not clamped
  if (isObj(a.accepted)) for (const [job, v] of Object.entries(a.accepted)) if (JOB_IDS.has(job) && v === true) apps.accepted[job] = true;
  return {t, needs, apps};
}
