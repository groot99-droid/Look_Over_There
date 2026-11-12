// The City's needs (slice 4): hunger, money, the grocery cart and the pantry at home. Pure rules, shared by index.html and the tests; nothing here touches the page.
// Hunger runs 0..100 and only drains while the City's clock runs (so it waits outside the City, during a shift and while you read the computer). At 0 you faint and wake at home.
// Defaults for the owner to change: the numbers below. There is no save yet, so a reload starts again at these values.
export const HUNGER = {max: 100, start: 80, perHour: 100 / 36, sleepFactor: 0.5, sleepFloor: 5, warn: 30, starve: 10, wakeAt: 25, full: 95};
// rest (slice 12): "Needs: hunger and sleep" (docs/WORLD.md). 0..100, drains while you are awake in the City (a full bar lasts 20 waking hours), refills while you sleep
// (12 an hour: a night from 20:00 to 06:00 fills it). Warnings at 30 (tired) and 10 (exhausted); at 0 you pass out and wake at home at 06:00. Tired by day, the bed lets you nap.
export const REST = {max: 100, start: 90, perHour: 5, perSleepHour: 12, warn: 30, exhausted: 10, wakeAt: 60, napHours: 3};
export const MONEY = {start: 20};                 // a shift's pay is in shared/pay.js: it scales with how the shift went
export const CARRY = {hands: 2, cart: 8};
export const FOODS = [
  {id: "apple", label: "Apples", price: 1, fill: 12},
  {id: "bread", label: "Bread", price: 2, fill: 25},
  {id: "soup", label: "Canned soup", price: 3, fill: 35},
  {id: "meal", label: "Ready meal", price: 6, fill: 60},
];
const food = id => FOODS.find(f => f.id === id);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
export const newNeeds = () => ({hunger: HUNGER.start, rest: REST.start, money: MONEY.start, pantry: {}, cart: [], hasCart: false, lastPay: null, lastNote: ""});

// hunger after `hours` game hours awake; and after `hours` asleep (half the rate, and sleep never takes you below 5: you wake hungry, not fainted)
// awake: both needs drain (rest only if the record has it: older callers and saves without it keep working)
export const drain = (n, hours) => ({...n, hunger: clamp(n.hunger - Math.max(0, hours) * HUNGER.perHour, 0, HUNGER.max), ...(n.rest === undefined ? {} : {rest: clamp(n.rest - Math.max(0, hours) * REST.perHour, 0, REST.max)})});
export const sleepDrain = (n, hours) => ({...n, hunger: Math.max(Math.min(n.hunger, HUNGER.sleepFloor), n.hunger - Math.max(0, hours) * HUNGER.perHour * HUNGER.sleepFactor)});
// which warning a change of hunger crosses, if any: "hungry" (30), "starving" (10), "faint" (0)
export function crossed(before, after) {
  if (after <= 0 && before > 0) return "faint";
  if (after <= HUNGER.starve && before > HUNGER.starve) return "starving";
  if (after <= HUNGER.warn && before > HUNGER.warn) return "hungry";
  return null;
}
export const faint = n => ({...n, hunger: HUNGER.wakeAt, cart: [], hasCart: false, ...(n.rest === undefined ? {} : {rest: Math.max(n.rest, REST.wakeAt)})});
// slice 12: sleeping `hours` refills rest; which rest warning a change crosses; passing out (from exhaustion, or knocked out) leaves you at least partly rested
export const rest = (n, hours) => ({...n, rest: clamp((n.rest ?? REST.start) + Math.max(0, hours) * REST.perSleepHour, 0, REST.max)});
export function restCrossed(before, after) {
  if (after <= 0 && before > 0) return "out";
  if (after <= REST.exhausted && before > REST.exhausted) return "exhausted";
  if (after <= REST.warn && before > REST.warn) return "tired";
  return null;
}
export const passOut = n => ({...n, rest: Math.max(n.rest ?? 0, REST.wakeAt), cart: [], hasCart: false});
export const tired = n => (n.rest ?? REST.max) <= REST.warn;

// the grocery: take a cart, put items in it (2 in your hands without one, 8 with), pay at the checkout, and what you paid for goes to the pantry at home
export const capacity = n => n.hasCart ? CARRY.cart : CARRY.hands;
export const takeCart = n => n.hasCart ? {n, ok: false, reason: "You already have a cart."} : {n: {...n, hasCart: true}, ok: true, reason: ""};
export function addToCart(n, id) {
  if (!food(id)) return {n, ok: false, reason: "That is not for sale."};
  if (n.cart.length >= capacity(n)) return {n, ok: false, reason: n.hasCart ? "Your cart is full." : "Your hands are full. Take a cart at the entrance."};
  return {n: {...n, cart: [...n.cart, id]}, ok: true, reason: ""};
}
export const cartTotal = n => n.cart.reduce((s, id) => s + food(id).price, 0);
export function checkout(n) {
  if (!n.cart.length) return {n, ok: false, paid: 0, reason: "Your cart is empty."};
  const total = cartTotal(n);
  if (total > n.money) return {n, ok: false, paid: 0, reason: `That comes to $${total}. You have $${n.money}.`};
  const pantry = {...n.pantry}; for (const id of n.cart) pantry[id] = (pantry[id] || 0) + 1;
  return {n: {...n, money: n.money - total, pantry, cart: [], hasCart: false}, ok: true, paid: total, reason: ""};
}
export const putBack = n => ({...n, cart: [], hasCart: false});          // leaving with what you did not pay for: it goes back on the shelves (no stealing in v0)

// the fridge at home: one item each time, the most filling one you have; not when you are already full
export function eat(n) {
  if (n.hunger >= HUNGER.full) return {n, ok: false, ate: null, reason: "You are not hungry."};
  const have = FOODS.filter(f => (n.pantry[f.id] || 0) > 0).sort((a, b) => b.fill - a.fill);
  if (!have.length) return {n, ok: false, ate: null, reason: "The fridge is empty. The grocery is on Hallam Row."};
  const f = have[0], pantry = {...n.pantry, [f.id]: n.pantry[f.id] - 1};
  return {n: {...n, hunger: clamp(n.hunger + f.fill, 0, HUNGER.max), pantry}, ok: true, ate: f.id, reason: ""};
}
export const pay = (n, amount, note = "") => ({...n, money: n.money + amount, lastPay: amount, lastNote: note});        // note: what the pay was for (the shift's ending)
export const pantryLines = n => FOODS.filter(f => n.pantry[f.id]).map(f => `${f.label}: ${n.pantry[f.id]}`);
