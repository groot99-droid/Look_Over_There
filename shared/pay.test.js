import test from "node:test";
import assert from "node:assert/strict";
import {PAY, shiftPay} from "./pay.js";

test("the ending sets the base pay", () => {
  for (const [ending, base] of Object.entries(PAY.base)) assert.equal(shiftPay({ending, conformance: 0, friction: 0}).pay, base);
  assert.ok(PAY.base.ASSIMILATION > PAY.base.RETAINED && PAY.base.RETAINED > PAY.base.PENDING && PAY.base.PENDING > PAY.base.EXPULSION, "the company pays most for assimilation");
});
test("compliance adds, friction docks, and the pay stays between $0 and $30", () => {
  const r = shiftPay({ending: "ASSIMILATION", conformance: 6, dissonance: 1, friction: 1.6});
  assert.equal(r.pay, 20 + 6 - 2); assert.deepEqual(r.lines, ["Shift: ASSIMILATION", "Base: $20", "Compliance bonus: +$6", "Friction: -$2", "Paid: $24"]);
  assert.equal(shiftPay({ending: "EXPULSION", conformance: -6, friction: 8}).pay, 0, "never below 0");
  assert.equal(shiftPay({ending: "ASSIMILATION", conformance: 8, friction: 0}).pay, 28);
  assert.ok(shiftPay({ending: "ASSIMILATION", conformance: 99, friction: -5}).pay <= PAY.max, "out-of-range numbers are clamped");
  assert.equal(shiftPay({ending: "PENDING", conformance: -3, friction: 0}).pay, 8, "negative conformance takes nothing off");
});
test("quitting early pays nothing", () => {
  const r = shiftPay({ending: "PENDING", conformance: 4, friction: 0, early: true});
  assert.equal(r.pay, 0); assert.match(r.lines.join(" "), /left early/);
});
test("a missing or malformed result is a PENDING shift: the base, no bonus, no docking", () => {
  for (const bad of [undefined, null, "x", {}, {ending: "PROMOTED"}, {ending: "ASSIMILATION", conformance: "lots", friction: NaN}]) {
    const r = shiftPay(bad), want = bad && bad.ending === "ASSIMILATION" ? 20 : 8;
    assert.equal(r.pay, want, JSON.stringify(bad));
  }
  assert.equal(shiftPay({ending: "PENDING", early: "yes"}).pay, 8, "only a real true counts as quitting");
});
