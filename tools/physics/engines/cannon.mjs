// cannon-es adapter. Same small API as engines/rapier.mjs so the bench, the test and the page run either engine.
// Boxes are given the way the game stores them: {n:[x,y,z] min, x:[x,y,z] max} (axis-aligned).
import * as C from "cannon-es";
export const NAME = "cannon-es";
export async function create({gravity = -9.81, sleep = true} = {}) {
  const world = new C.World({gravity: new C.Vec3(0, gravity, 0)});
  world.allowSleep = sleep;
  world.broadphase = new C.SAPBroadphase(world);      // sweep and prune: much cheaper than the default naive pairs with many static boxes
  const mat = new C.Material("m");
  world.addContactMaterial(new C.ContactMaterial(mat, mat, {friction: 0.4, restitution: 0.6}));
  const mk = (shape, p, mass) => { const b = new C.Body({mass, material: mat, shape, position: new C.Vec3(p[0], p[1], p[2])}); if (mass) { b.sleepSpeedLimit = 0.15; b.sleepTimeLimit = 0.5; b.linearDamping = 0.01; b.angularDamping = 0.05; } world.addBody(b); return b; };
  return {
    name: NAME, world,
    addStaticBox(b) { const h = [0, 1, 2].map(i => (b.x[i] - b.n[i]) / 2); return mk(new C.Box(new C.Vec3(h[0], h[1], h[2])), [0, 1, 2].map(i => (b.x[i] + b.n[i]) / 2), 0); },
    addBall(p, r, mass = 0.4) { return mk(new C.Sphere(r), p, mass); },
    addBox(p, half, mass = 1) { return mk(new C.Box(new C.Vec3(half[0], half[1], half[2])), p, mass); },
    // a seat hung from a fixed pivot by a hinge about the z axis (the swing swings in the x-y plane)
    addSwing({pivot, length, seat = [0.3, 0.04, 0.15], mass = 3, angle = 0}) {
      const anchor = mk(new C.Sphere(0.01), pivot, 0); anchor.collisionResponse = false;
      const pos = [pivot[0] + Math.sin(angle) * length, pivot[1] - Math.cos(angle) * length, pivot[2]];
      const body = mk(new C.Box(new C.Vec3(seat[0], seat[1], seat[2])), pos, mass); body.angularDamping = 0.0; body.linearDamping = 0.0;
      body.collisionFilterGroup = 2; body.collisionFilterMask = 1;  // the seat does not hit the anchor
      anchor.collisionFilterGroup = 4; anchor.collisionFilterMask = 0;
      // seat's local frame: pivot sits `length` above the seat centre; hinge axis z. The seat is a point mass at its centre for the period check (box is thin).
      world.addConstraint(new C.HingeConstraint(anchor, body, {pivotA: new C.Vec3(0, 0, 0), axisA: new C.Vec3(0, 0, 1), pivotB: new C.Vec3(0, length, 0), axisB: new C.Vec3(0, 0, 1)}));
      body.quaternion.setFromAxisAngle(new C.Vec3(0, 0, 1), angle);
      return body;
    },
    pos: b => [b.position.x, b.position.y, b.position.z],
    vel: b => [b.velocity.x, b.velocity.y, b.velocity.z],
    rot: b => { const q = b.quaternion; return [q.x, q.y, q.z, q.w]; },
    asleep: b => b.sleepState === C.Body.SLEEPING,
    impulse(b, v) { b.wakeUp(); b.velocity.x += v[0] / b.mass; b.velocity.y += v[1] / b.mass; b.velocity.z += v[2] / b.mass; },
    step(dt) { world.step(dt); },      // one fixed step; the caller owns the accumulator
    free() {},
  };
}
