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

test("rest (slice 12): starts at 90, drains 5 an hour awake, a full bar lasts 20 waking hours", async () => {
  const {REST, newNeeds, drain} = await import("./needs.js");
  const n = newNeeds(); assert.equal(n.rest, 90);
  assert.ok(Math.abs(drain(n, 2).rest - 80) < 1e-9);
  assert.ok(Math.abs(drain({...n, rest: 100}, 20).rest) < 1e-9);
  assert.equal(drain(n, 1000).rest, 0, "never below 0");
  assert.equal(REST.perHour * 20, REST.max);
  assert.equal(drain({hunger: 50}, 1).rest, undefined, "a record without rest is left without it");
});
test("rest: sleep refills it, 12 an hour, so a night from 20:00 to 06:00 fills it", async () => {
  const {REST, rest} = await import("./needs.js");
  assert.equal(rest({rest: 0}, 10).rest, REST.max);
  assert.equal(rest({rest: 20}, 3).rest, 56);
  assert.equal(rest({rest: 95}, 5).rest, 100);
  assert.equal(rest({rest: 40}, -2).rest, 40);
});
test("rest: warnings at 30 (tired) and 10 (exhausted), out at 0; passing out or fainting leaves you at least at 60", async () => {
  const {REST, restCrossed, passOut, faint, tired} = await import("./needs.js");
  assert.equal(restCrossed(31, 29), "tired"); assert.equal(restCrossed(11, 9), "exhausted"); assert.equal(restCrossed(1, 0), "out");
  assert.equal(restCrossed(29, 28), null); assert.equal(restCrossed(50, 60), null); assert.equal(restCrossed(0, 0), null);
  assert.equal(passOut({rest: 0, cart: ["meal"], hasCart: true}).rest, REST.wakeAt);
  assert.deepEqual(passOut({rest: 80, cart: ["meal"], hasCart: true}), {rest: 80, cart: [], hasCart: false});
  assert.equal(faint({hunger: 0, rest: 5, cart: [], hasCart: false}).rest, REST.wakeAt);
  assert.ok(tired({rest: 30}) && !tired({rest: 31}) && !tired({}));
});

test("stealing (slice 19): unseen you keep what you carried out; seen, you are fined $5 plus its price, never more than you have, and it goes back", async () => {
  const {steal, caught, fineFor, THEFT, newNeeds} = await import("./needs.js");
  const n = {...newNeeds(), money: 20, pantry: {apple: 1}, cart: ["apple", "meal"], hasCart: true};
  const s = steal(n);
  assert.deepEqual(s.pantry, {apple: 2, meal: 1}); assert.deepEqual(s.cart, []); assert.equal(s.hasCart, false); assert.equal(s.money, 20);
  assert.equal(fineFor(n), THEFT.fineBase + 1 + 6);
  const c = caught(n); assert.equal(c.fine, 12); assert.equal(c.n.money, 8); assert.deepEqual(c.n.pantry, {apple: 1}); assert.deepEqual(c.n.cart, []);
  const poor = caught({...n, money: 3}); assert.equal(poor.fine, 3); assert.equal(poor.n.money, 0);
});
