import test from "node:test";
import assert from "node:assert/strict";
import {shiftPay} from "./pay.js";
import {HUNGER, MONEY, CARRY, FOODS, newNeeds, drain, sleepDrain, crossed, faint, capacity, takeCart, addToCart, cartTotal, checkout, putBack, eat, pay, pantryLines} from "./needs.js";

test("you start at hunger 80 with $20; hunger empties over 36 game hours awake", () => {
  const n = newNeeds(); assert.equal(n.hunger, 80); assert.equal(n.money, MONEY.start);
  assert.ok(Math.abs(drain({...n, hunger: 100}, 36).hunger) < 1e-9); assert.equal(drain(n, 1000).hunger, 0, "never below 0");
  assert.ok(Math.abs(drain(n, 3.6).hunger - 70) < 1e-9);
});
test("sleeping drains half as fast and never takes you below 5", () => {
  assert.ok(Math.abs(sleepDrain({hunger: 80}, 7.2).hunger - 70) < 1e-9);
  assert.equal(sleepDrain({hunger: 12}, 10).hunger, 5); assert.equal(sleepDrain({hunger: 3}, 10).hunger, 3, "already below 5 stays where it is");
});
test("the warnings: hungry at 30, starving at 10, faint at 0, each once on the way down", () => {
  assert.equal(crossed(31, 29), "hungry"); assert.equal(crossed(29, 28), null); assert.equal(crossed(11, 9), "starving"); assert.equal(crossed(1, 0), "faint");
  assert.equal(crossed(40, 0), "faint", "a big drop reports the worst"); assert.equal(crossed(20, 40), null, "eating crosses nothing");
  const f = faint({hunger: 0, money: 5, pantry: {apple: 1}, cart: ["bread"], hasCart: true});
  assert.deepEqual([f.hunger, f.cart, f.hasCart, f.money, f.pantry.apple], [HUNGER.wakeAt, [], false, 5, 1]);
});
test("you carry 2 in your hands and 8 in a cart", () => {
  let n = newNeeds(); assert.equal(capacity(n), CARRY.hands);
  n = addToCart(n, "bread").n; n = addToCart(n, "bread").n; const r = addToCart(n, "apple");
  assert.equal(r.ok, false); assert.match(r.reason, /Take a cart/);
  n = takeCart(n).n; assert.equal(capacity(n), CARRY.cart); assert.equal(takeCart(n).ok, false);
  for (let i = 0; i < 6; i++) n = addToCart(n, "apple").n;
  assert.equal(n.cart.length, 8); assert.match(addToCart(n, "apple").reason, /cart is full/);
  assert.equal(addToCart(newNeeds(), "caviar").ok, false);
});
test("the checkout takes the money and sends the food home; too little money changes nothing", () => {
  let n = takeCart(newNeeds()).n; n = addToCart(n, "meal").n; n = addToCart(n, "soup").n;
  assert.equal(cartTotal(n), 9);
  const r = checkout(n); assert.ok(r.ok); assert.equal(r.paid, 9); assert.equal(r.n.money, 11); assert.deepEqual(r.n.pantry, {meal: 1, soup: 1}); assert.deepEqual(r.n.cart, []); assert.equal(r.n.hasCart, false);
  const poor = {...n, money: 4}, p = checkout(poor); assert.equal(p.ok, false); assert.equal(p.n, poor); assert.match(p.reason, /\$9.*\$4/);
  assert.match(checkout(newNeeds()).reason, /empty/);
  assert.deepEqual([putBack(n).cart, putBack(n).hasCart, putBack(n).money], [[], false, 20]);
});
test("the fridge feeds you the most filling item, and refuses when you are full or it is empty", () => {
  const n = {...newNeeds(), hunger: 20, pantry: {apple: 2, soup: 1}};
  let r = eat(n); assert.equal(r.ate, "soup"); assert.equal(r.n.hunger, 55); assert.equal(r.n.pantry.soup, 0);
  r = eat(r.n); assert.equal(r.ate, "apple"); assert.equal(r.n.hunger, 67);
  assert.match(eat({...n, hunger: 96}).reason, /not hungry/); assert.match(eat({...n, pantry: {}}).reason, /fridge is empty/);
  assert.equal(eat({...n, hunger: 90, pantry: {meal: 1}}).n.hunger, 100, "never above 100");
});
test("a shift pays what shared/pay.js says, with a note, and the bank page lists the pantry", () => {
  const p = shiftPay({ending: "ASSIMILATION", conformance: 6, friction: 1.6}), n = pay(newNeeds(), p.pay, p.ending);
  assert.equal(n.money, 44); assert.equal(n.lastPay, 24); assert.equal(n.lastNote, "ASSIMILATION");
  const q = pay(newNeeds(), 0, "PENDING"); assert.equal(q.money, 20); assert.equal(q.lastPay, 0, "a shift that paid nothing is still a shift");
  assert.deepEqual(pantryLines({pantry: {bread: 2, meal: 0, apple: 1}}), ["Apples: 1", "Bread: 2"]);
  assert.equal(FOODS.every(f => f.price > 0 && f.fill > 0), true);
});
