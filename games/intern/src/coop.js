// Look Over There host only: the other players of a party room who are in this stage of the game.
// Nothing here changes the game: figures have no collision, make no sound and are seen only.
//
// The building is laid out as each player walks it, so two players' world frames differ. A spot is
// therefore given in the frame of the room it is in ({room: the room's base key, x, y, z, yaw}), and a
// figure is drawn only while a room with that key is live here, carried into the world by its matrix.
//
// To the page (the frame's parent), about 15 times a second while the candidate walks:
//   {type: 'intern-state', stage: 'S3', room: 'S3_C', x, y, z, yaw, moving}
// From the page, whenever it likes:
//   {type: 'intern-peers', peers: [{id, room, x, y, z, yaw, color}]}

import * as THREE from '../vendor/three/three.module.js';
import { SCALE } from './walk/controls.js';

const SEND_HZ = 15;
const HEIGHT = 1.72 / SCALE;   // the candidate's own shadow body is 1.72 m (stage.js); the walker is shrunk by SCALE

function figure(color) {
  const g = new THREE.Group();
  const mat = new THREE.MeshLambertMaterial({ color });
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.2, 0.9, 4, 10), mat);
  body.position.y = 0.65;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.16, 12, 10), mat);
  head.position.y = 1.5;
  g.add(body, head);
  g.scale.setScalar(HEIGHT / 1.66);
  g.userData.mat = mat;
  return g;
}

const yawOf = (m) => Math.atan2(m.elements[8], m.elements[10]); // a room is only ever turned about Y

export function initCoop({ stage, state, manifest }) {
  const embedded = window.parent !== window;
  const world = stage.world, player = stage.player;
  const figs = new Map(); // id -> {group, room, local: Vector3, yaw, fresh}
  let peers = [];
  let sentAt = 0, last = null, self = null;
  const _v = new THREE.Vector3();

  function here() {
    const f = player.feet();
    const inst = world.locate(f) || world.current();
    if (!inst) return null;
    _v.set(f[0], f[1], f[2]).applyMatrix4(inst.inv);
    return { room: inst.base, x: _v.x, y: _v.y, z: _v.z, yaw: THREE.MathUtils.degToRad(player.yawDeg()) - yawOf(inst.matrix) };
  }

  function drop(id) {
    const f = figs.get(id);
    if (!f) return;
    stage.scene.remove(f.group);
    f.group.traverse((o) => { if (o.geometry) o.geometry.dispose(); });
    f.group.userData.mat.dispose();
    figs.delete(id);
  }

  function draw(dt) {
    const seen = new Set();
    const live = world.instances();
    for (const p of peers) {
      if (!p || typeof p.room !== 'string' || ![p.x, p.y, p.z].every(Number.isFinite)) continue;
      seen.add(p.id);
      let f = figs.get(p.id);
      if (!f) {
        f = { group: figure(p.color || '#8a8f98'), room: null, local: new THREE.Vector3(), yaw: 0 };
        f.group.visible = false;
        stage.scene.add(f.group);
        figs.set(p.id, f);
      }
      const jump = f.room !== p.room || Math.hypot(f.local.x - p.x, f.local.z - p.z) > 4;
      const k = jump ? 1 : Math.min(1, dt * 10);
      f.room = p.room;
      f.local.set(f.local.x + (p.x - f.local.x) * k, f.local.y + (p.y - f.local.y) * k, f.local.z + (p.z - f.local.z) * k);
      const yaw = Number.isFinite(p.yaw) ? p.yaw : 0;
      f.yaw = jump ? yaw : f.yaw + Math.atan2(Math.sin(yaw - f.yaw), Math.cos(yaw - f.yaw)) * k;
      const inst = live.find((i) => i.base === p.room && i.group.visible);
      f.group.visible = !!inst;
      if (inst) {
        f.group.position.copy(f.local).applyMatrix4(inst.matrix);
        f.group.rotation.y = f.yaw + yawOf(inst.matrix);
      }
    }
    for (const id of [...figs.keys()]) if (!seen.has(id)) drop(id);
  }

  function send(now) {
    if (!embedded || !stage.isPlayerActive() || now - sentAt < 1000 / SEND_HZ) return;
    const h = here();
    if (!h) return;
    sentAt = now;
    const moving = !!last && last.room === h.room && Math.hypot(h.x - last.x, h.z - last.z) > 0.002;
    last = h; self = h;
    window.parent.postMessage({ type: 'intern-state', stage: manifest.spineOrder[state.sceneIndex], ...h, moving }, '*');
  }

  if (embedded) addEventListener('message', (e) => {
    if (e.source !== window.parent || !e.data || e.data.type !== 'intern-peers' || !Array.isArray(e.data.peers)) return;
    peers = e.data.peers.slice(0, 16);
  });
  stage.onFrame((dt) => { send(performance.now()); draw(dt); });

  return {
    // test hooks: how many figures are shown, where they are (in their room's frame), and the spot last sent
    count: () => [...figs.values()].filter((f) => f.group.visible).length,
    positions: () => [...figs.values()].filter((f) => f.group.visible).map((f) => ({ room: f.room, x: f.local.x, y: f.local.y, z: f.local.z })),
    self: () => self,
    here
  };
}
