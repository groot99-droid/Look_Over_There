// Rapier adapter (WASM, @dimforge/rapier3d-compat: the .wasm is inlined as base64 in the JS, so one file loads it).
import RAPIER from "@dimforge/rapier3d-compat";
export const NAME = "rapier";
export async function create({gravity = -9.81, sleep = true} = {}) {
  await RAPIER.init({});
  const world = new RAPIER.World({x: 0, y: gravity, z: 0});
  const body = (p, dyn, extra) => { const d = (dyn ? RAPIER.RigidBodyDesc.dynamic() : RAPIER.RigidBodyDesc.fixed()).setTranslation(p[0], p[1], p[2]).setCanSleep(sleep); if (extra) extra(d); return world.createRigidBody(d); };
  const cm = {friction: 0.4, restitution: 0.6};
  const col = (cd, rb, mass) => { cd.setFriction(cm.friction).setRestitution(cm.restitution); if (mass) cd.setMass(mass); return world.createCollider(cd, rb); };
  return {
    name: NAME, world, RAPIER,
    addStaticBox(b) { const h = [0, 1, 2].map(i => (b.x[i] - b.n[i]) / 2), rb = body([0, 1, 2].map(i => (b.x[i] + b.n[i]) / 2), false); col(RAPIER.ColliderDesc.cuboid(h[0], h[1], h[2]), rb); return rb; },
    addBall(p, r, mass = 0.4) { const rb = body(p, true, d => d.setLinearDamping(0.01).setAngularDamping(0.05)); col(RAPIER.ColliderDesc.ball(r), rb, mass); return rb; },
    addBox(p, half, mass = 1) { const rb = body(p, true, d => d.setLinearDamping(0.01).setAngularDamping(0.05)); col(RAPIER.ColliderDesc.cuboid(half[0], half[1], half[2]), rb, mass); return rb; },
    addSwing({pivot, length, seat = [0.3, 0.04, 0.15], mass = 3, angle = 0}) {
      const anchor = body(pivot, false);
      const pos = [pivot[0] + Math.sin(angle) * length, pivot[1] - Math.cos(angle) * length, pivot[2]];
      const rb = body(pos, true, d => d.setAngularDamping(0).setLinearDamping(0));
      const cd = RAPIER.ColliderDesc.cuboid(seat[0], seat[1], seat[2]).setFriction(0.4).setMass(mass).setCollisionGroups(0x0002_0001);   // member of group 2, hits group 1 only
      world.createCollider(cd, rb);
      rb.setRotation({x: 0, y: 0, z: Math.sin(angle / 2), w: Math.cos(angle / 2)}, true);
      // revolute joint about z: anchor at the pivot, the seat's own anchor `length` above its centre
      world.createImpulseJoint(RAPIER.JointData.revolute({x: 0, y: 0, z: 0}, {x: 0, y: length, z: 0}, {x: 0, y: 0, z: 1}), anchor, rb, true);
      return rb;
    },
    pos: b => { const t = b.translation(); return [t.x, t.y, t.z]; },
    vel: b => { const v = b.linvel(); return [v.x, v.y, v.z]; },
    rot: b => { const q = b.rotation(); return [q.x, q.y, q.z, q.w]; },
    asleep: b => b.isSleeping(),
    impulse(b, v) { b.applyImpulse({x: v[0], y: v[1], z: v[2]}, true); },
    step(dt) { world.timestep = dt; world.step(); },
    free() { world.free(); },
  };
}
