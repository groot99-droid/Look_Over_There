import test from "node:test";
import assert from "node:assert/strict";
import {inCone} from "./cone.js";
import {indexBoxes} from "./world.js";

const W = {floor: 0, boxes: [], grid: new Map(), doors: [], nav: null};
const mon = (x, z, o = {}) => ({pos: {x, z}, fy: 0, cfg: {height: 2}, ...o});
const eye = [0, 1.6, 0], facing = [0, -1];
test("a cone takes its reach and width as arguments: the same monsters are in a long narrow one and out of a short wide one", () => {
  const a = mon(0, -8), b = mon(-3, -3);                       // b is about 45 degrees off the axis
  assert.deepEqual(inCone(W, [a, b], eye, facing, 10, 20), [a]);
  assert.deepEqual(inCone(W, [a, b], eye, facing, 5, 100), [b]);
  assert.deepEqual(inCone(W, [a, b], eye, facing, 10, 100), [a, b]);
});
test("a cone ignores other floors, what is behind you and what a wall hides", () => {
  assert.deepEqual(inCone(W, [{...mon(0, -3), fy: 5}, mon(0, 3)], eye, facing, 10, 90), []);
  const walled = {...W, boxes: [{n: [-2, 0, -3.6], x: [2, 3, -3.0]}]}; indexBoxes(walled);
  assert.deepEqual(inCone(walled, [mon(0, -5)], eye, facing, 10, 90), []);
});
