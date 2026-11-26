// The other players of a party room, drawn inside Right Door, Wrong Exit (session 11). Presence only: a plain figure for each, at the position and heading the room's
// server relays. They have no collision and no effect on the walk. The page gives `peers()` (who is in this room of the game, with the latest position the server
// told us) and this moves a figure toward each, so a position that arrives 15 times a second looks like walking.
import * as THREE from 'three';

const body = new THREE.CapsuleGeometry(0.22, 0.9, 4, 10), head = new THREE.SphereGeometry(0.17, 12, 8);

// scene: the room's THREE scene; height: the walker's eye height in this game's units (it shrinks with the walker's scale, so a player is the same size to everyone)
export function createPeerFigures(scene, height) {
  const figs = new Map();       // id -> {group, mat, target: [x, y, z, yaw]}
  const k = height / 1.62;      // the figure is modelled for a 1.62 m eye
  function make(p) {
    const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(p.color || '#cccccc') });
    const g = new THREE.Group();
    const b = new THREE.Mesh(body, mat); b.position.y = 0.67; g.add(b);
    const h = new THREE.Mesh(head, mat); h.position.y = 1.42; g.add(h);
    g.scale.setScalar(k);
    g.position.set(p.x, p.y - height, p.z); g.rotation.y = p.yaw || 0;
    scene.add(g);
    return { group: g, mat, at: [p.x, p.y, p.z, p.yaw || 0] };
  }
  return {
    // call every frame with the page's current list and the frame's dt (seconds)
    update(list, dt) {
      const seen = new Set();
      for (const p of list) {
        seen.add(p.id);
        let f = figs.get(p.id); if (!f) { f = make(p); figs.set(p.id, f); }
        const a = Math.min(1, dt * 12);             // ease toward the latest position
        f.at[0] += (p.x - f.at[0]) * a; f.at[1] += (p.y - f.at[1]) * a; f.at[2] += (p.z - f.at[2]) * a;
        let dy = (p.yaw || 0) - f.at[3]; dy = Math.atan2(Math.sin(dy), Math.cos(dy)); f.at[3] += dy * a;
        f.group.position.set(f.at[0], f.at[1] - height, f.at[2]); f.group.rotation.y = f.at[3];
      }
      for (const [id, f] of figs) if (!seen.has(id)) { scene.remove(f.group); f.mat.dispose(); figs.delete(id); }
    },
    count: () => figs.size,
    positions: () => [...figs.values()].map(f => f.at.slice(0, 3)),
    dispose() { for (const f of figs.values()) { scene.remove(f.group); f.mat.dispose(); } figs.clear(); },
  };
}
