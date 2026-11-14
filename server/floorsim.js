// A floor of a room, simulated on the server: its monsters (the shared rules in shared/monsters.js), its doors, and everything that used to be one player's job as the "host":
// hitting what a monster touches, deciding what a ray-gun shot does, swarming a thrown beacon, running to a noise, opening doors, hunting at the finale, and telling the floor
// where the monsters are. Players still say where they are (their `s` messages: x, y, z, flags); the server stores that on the player as `st`.
import {worldFromDoc, stepDoors, buildNav} from "../shared/world.js";
import {MonsterSim, spawnPlan, resolveShot, swarmApart, stunNear} from "../shared/monsters.js";
import {HIT_DMG} from "../shared/health.js";
import {LURE_S, reverse as reverseLure} from "../shared/beacon.js";
import {STUN_S} from "../shared/cloak.js";
import {ALARM_MS} from "../shared/finish.js";
import {wavePlan, startWave, killed} from "../shared/gbi.js";
import {killShot, SHOT_NOISE_S as BOLT_NOISE_S} from "../shared/crossbow.js";
import {placeTrap, springs, FLASH_THROW_M, FLASH_R, FLASH_STUN_S, WIRE_NOISE_R} from "../shared/consumables.js";

export const TICK_S = 0.05, SNAP_EVERY = 2, DOORS_EVERY = 10, ALERT_R = 40, THROW_SPEED = 4;
const nums = (v, n) => Array.isArray(v) && v.length === n && v.every(x => typeof x === "number" && Number.isFinite(x)) ? v : null;

export class Floor {
  // room: the server's room object ({players: Map, power, alarmAt}); io: {to(player, msg), toFloor(msg, exceptId)}; docs: {doc(scene) -> world json}; monCfg: world/monsters.json
  // chamber: REGISTRY.chamber(scene) for a Going back in chamber (null for an Original floor). A chamber has no monsters until its wave starts, and is kept while the room lives.
  constructor({scene, room, io, doc, monCfg, chamber = null, rnd = Math.random, onHit = () => {}, flags = p => ({dead: !!p.st.dead, imm: !!p.st.imm, cloak: !!p.st.cloak})}) {
    this.scene = scene; this.room = room; this.io = io; this.t = 0; this.rnd = rnd; this.onHit = onHit; this.flags = flags;
    this.chamber = chamber; this.keep = !!chamber; this.wave = null; this.monCfg = monCfg;
    this.W = worldFromDoc(doc, scene, chamber ? {floor: chamber.floorY, art: chamber.floor} : {powerOn: room.power.on});
    this.env = {W: this.W, now: () => this.t, rnd, openDoor: dr => this.openDoor(dr)};
    this.monsters = spawnPlan(this.W, monCfg, scene).map(p => new MonsterSim(p.cfg, scene, p.x, p.z, this.env));
    this.lures = []; this.ticks = 0; this.hunt = 0; this.beaconSeq = 0;
    this.traps = []; this.trapSeq = 0;                                // Going back in: the land mines and tripwires set in this chamber and not yet sprung
  }
  players() { return [...this.room.players.values()].filter(p => p.scene === this.scene); }
  // ---- Going back in: the chamber's wave (shared/gbi.js). It starts once, when the first player steps in, away from where they stand; each monster keeps a number (`wid`) for
  // the life of the room, so a kill can name it. Returns true if this call started it.
  enterChamber(p) {
    if (!this.chamber || this.wave || !p.st) return false;
    this.monsters = wavePlan(this.W, this.monCfg, this.chamber, [[p.st.x, p.st.z]]).map((s, i) => Object.assign(new MonsterSim(s.cfg, this.scene, s.x, s.z, this.env), {wid: i}));
    this.wave = {...startWave(this.chamber, this.t), monsters: this.monsters.length};
    return true;
  }
  // what a player in the chamber is told about its wave: the count, and each living monster as [wid, x, z] in the order the snapshots use
  waveMsg(of, fresh = false) {
    const w = this.wave; if (!w) return null;
    return {t: "wave", scene: this.scene, no: w.no, of, monsters: w.monsters, kills: w.kills, cleared: w.cleared, kind: this.chamber.wave.kind, l: this.monsters.map(m => [m.wid, +m.pos.x.toFixed(2), +m.pos.z.toFixed(2)]),
      traps: this.traps.map(t => this.trapView(t)), ...(fresh ? {fresh: 1} : {})};
  }
  exited(p) { return !!(this.room.run && this.room.run.exits.some(e => e.id === p.id)); }
  // who the monsters can see and hear: living, not newly lifted (immune), still in the building; a shot counts as running noise for half a second
  targets() {
    return this.players().filter(p => p.st && !this.exited(p)).map(p => ({p, f: this.flags(p)})).filter(({f}) => !f.dead && !f.imm).map(({p, f}) => {
      const s = p.st, shot = (p.shotT || 0) > 0;
      return {id: p.id, x: s.x, y: s.y, z: s.z, crouch: !!s.crouch && !shot, moving: !!s.moving || shot, run: !!s.run || shot, carry: !!s.carry, cloak: f.cloak};
    });
  }
  doorBusy(dr) {
    const inside = (x, y, z) => Math.abs(y - dr.cy) < 1.8 && Math.hypot(x - dr.cx, z - dr.cz) < 1.1;
    return this.players().some(p => p.st && !this.flags(p).dead && inside(p.st.x, p.st.y, p.st.z)) || this.monsters.some(m => inside(m.pos.x, m.fy, m.pos.z));
  }
  openDoor(dr) {                                                  // monsters open doors too (they never shut them, and never use the stair doors)
    if (dr.target !== 0 || dr.link) return;
    dr.target = 1; this.io.toFloor({t: "door", scene: this.scene, name: dr.d.name, open: 1});
  }
  // a player asks to open or shut a door: only a door they stand near, never a stair door; a shut one is refused while someone stands in the doorway
  playerDoor(p, name, open) {
    const dr = this.W.doors.find(d => d.d.name === name); if (!dr || dr.link || !p.st) return false;
    if (Math.hypot(p.st.x - dr.cx, p.st.z - dr.cz) > 4 || Math.abs(p.st.y - dr.cy) > 2.5) return false;
    const want = open === 0 ? 0 : 1; if (dr.target === want) return false;
    if (want === 0 && this.doorBusy(dr)) return false;
    dr.target = want; this.io.toFloor({t: "door", scene: this.scene, name, open: want}, p.id); return true;
  }
  // a shot: the ray starts at the shooter's eye (it must be near where they are) and banishes the monster it hits. `spend()` is called once the shot is known to be genuine
  // (it takes the round); returns null when the shot is refused, else {r: what it banished or null}.
  shot(p, o, d, spend = () => true) {
    o = nums(o, 3); d = nums(d, 3); if (!o || !d || !p.st) return null;
    if (Math.hypot(o[0] - p.st.x, o[2] - p.st.z) > 3 || Math.abs(o[1] - p.st.y - 1.5) > 1.2) return null;
    const L = Math.hypot(...d); if (!(L > 0.5 && L < 1.5)) return null; d = d.map(v => v / L);
    if (!spend()) return null;
    p.shotT = 0.5;
    const r = resolveShot(this.W, this.monsters, this.players().filter(q => q.st && !this.flags(q).dead).map(q => ({x: q.st.x, y: q.st.y, z: q.st.z})), o, d, this.rnd);
    if (r) this.io.toFloor({t: "zap", scene: this.scene, i: r.i, from: r.from, to: r.to});
    return {r};
  }
  // a monster of the wave is dead for good (a bolt, a trap): gone from the floor and its snapshots, counted toward the wave, and everyone in the chamber is told which
  kill(m, by = 0) {
    const i = this.monsters.indexOf(m); if (i < 0) return false;
    this.monsters.splice(i, 1); if (this.wave) this.wave = killed(this.wave);
    this.io.toFloor({t: "kill", scene: this.scene, id: m.wid, by, x: +m.pos.x.toFixed(2), z: +m.pos.z.toFixed(2), kills: this.wave ? this.wave.kills : 0, cleared: !!(this.wave && this.wave.cleared)});
    return true;
  }
  // a crossbow bolt (Going back in): checked like a ray shot; it kills the monster it hits, whatever its state. `spend()` takes the bolt once the shot is known to be genuine.
  // Returns null when refused, else {m: the monster killed or null, e: where the bolt stopped}.
  bolt(p, o, d, spend = () => true) {
    o = nums(o, 3); d = nums(d, 3); if (!this.chamber || !o || !d || !p.st) return null;
    if (Math.hypot(o[0] - p.st.x, o[2] - p.st.z) > 3 || Math.abs(o[1] - p.st.y - 1.5) > 1.2) return null;
    const L = Math.hypot(...d); if (!(L > 0.5 && L < 1.5)) return null; d = d.map(v => v / L);
    if (!spend()) return null;
    p.shotT = BOLT_NOISE_S;                                          // half the ray's noise
    const m = killShot(this.W, this.monsters, o, d), t = m ? Math.hypot(m.pos.x - o[0], m.pos.z - o[2]) : 25;
    if (m) this.kill(m, p.id);
    return {m, e: [o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t]};
  }
  // ---- the Q and E consumables (shared/consumables.js). The caller has taken one from the player's kit.
  // may a flash-vial thrown by p land at (x, z)? Within the throw of where the server has them (a little slack: the page shortens the throw at a wall).
  flashOk(p, x, z) { return !!this.chamber && !!p.st && Number.isFinite(x) && Number.isFinite(z) && Math.hypot(x - p.st.x, z - p.st.z) <= FLASH_THROW_M + 1; }
  // the vial bursts at (x, z): every monster within FLASH_R is stunned; the chamber sees the flash
  flash(p, x, z) {
    const n = stunNear(this.monsters, x, this.W.floor, z, FLASH_STUN_S, FLASH_R).length;
    this.io.toFloor({t: "flash", scene: this.scene, from: p.id, x: +x.toFixed(2), z: +z.toFixed(2), n, secs: FLASH_STUN_S});
  }
  trapView(t) { return {id: t.id, kind: t.kind, by: t.by, x: t.x, z: t.z, arm: +Math.max(0, t.armAt - this.t).toFixed(2)}; }          // arm: seconds until it is armed
  // a land mine or a tripwire set down where the server has the player; everyone in the chamber sees it
  setTrap(p, kind) {
    if (!this.chamber || !p.st) return null;
    const t = {...placeTrap(kind, +p.st.x.toFixed(2), +p.st.z.toFixed(2), this.t), id: ++this.trapSeq, by: p.id};
    this.traps.push(t); this.io.toFloor({t: "trap", scene: this.scene, ...this.trapView(t)}); return t;
  }
  // armed traps go off when a monster is on them: it (a mine) or everything in the blast (a tripwire) dies, and a tripwire's blast is loud
  stepTraps() {
    for (const t of this.traps) {
      const r = springs(t, this.t, this.monsters); if (!r) continue;
      t.done = true; this.io.toFloor({t: "sprung", scene: this.scene, id: t.id, kind: t.kind, x: t.x, z: t.z});
      for (const m of r.kills) this.kill(m, t.by);
      if (r.loud) this.alertNear(t.x, t.z, WIRE_NOISE_R);
    }
    if (this.traps.some(t => t.done)) this.traps = this.traps.filter(t => !t.done);
  }
  // a thrown AFK Beacon: it rolls from the thrower to (x, z) at 4 m/s, then runs for LURE_S seconds
  beacon(p, x, z, spend = () => true) {
    if (!p.st || !Number.isFinite(x) || !Number.isFinite(z) || Math.abs(x) > 500 || Math.abs(z) > 500 || !spend()) return false;
    const roll = Math.min(5, Math.hypot(x - p.st.x, z - p.st.z) / THROW_SPEED), land = this.t + roll;
    this.lures.push({id: ++this.beaconSeq, x, z, land, until: land + LURE_S});
    this.io.toFloor({t: "beacon", from: p.id, scene: this.scene, x, z}, p.id); return true;
  }
  // the cloak's short circuit: every monster within STUN_R of the player is stunned for STUN_S seconds (it neither moves nor hits); the floor sees the flash
  cloakBlast(p) {
    if (!p.st) return [];
    const idx = stunNear(this.monsters, p.st.x, p.st.y, p.st.z, STUN_S);
    this.io.toFloor({t: "stun", scene: this.scene, from: p.id, i: idx, secs: STUN_S, x: p.st.x, z: p.st.z}); return idx;
  }
  // a beacon's secondary: reverse the frequency of the nearest running beacon within 30 m of the player (once per beacon)
  reverseBeacon(p) {
    if (!p.st) return false;
    let best = -1, bd = 30;
    this.lures.forEach((b, k) => { const d = Math.hypot(b.x - p.st.x, b.z - p.st.z); if (this.t >= b.land && this.t < b.until && !b.reversed && d < bd) { bd = d; best = k; } });
    if (best < 0) return false;
    const b = this.lures[best] = reverseLure(this.lures[best], this.t);
    this.io.toFloor({t: "reverse", scene: this.scene, from: p.id, x: b.x, z: b.z, secs: b.repelUntil - this.t}); return true;
  }
  alertNear(x, z, r = ALERT_R) { for (const m of this.monsters) if (Math.hypot(m.pos.x - x, m.pos.z - z) < r) m.alert(x, z); }
  powerOn() { if (this.W.shutter && !this.W.shutter.off) { this.W.shutter.off = true; this.W.nav = buildNav(this.W, this.W.floor); } }
  step(dt = TICK_S) {
    this.t += dt; this.ticks++;
    stepDoors(this.W, dt, dr => this.doorBusy(dr));
    if (this.scene === "L4" && this.room.alarmAt && Date.now() - this.room.alarmAt < ALARM_MS && (this.hunt -= dt) <= 0) { this.hunt = 2; for (const m of this.monsters) m.alert(0, 24.5); }          // the alarm: every monster heads for the doors
    for (const p of this.players()) if (p.shotT > 0) p.shotT -= dt;
    const targets = this.targets(), live = this.lures.filter(b => this.t >= b.land && this.t < b.until);
    this.lures = this.lures.filter(b => this.t < b.until + 1);
    for (const m of this.monsters) for (const id of m.update(dt, targets, live).caught) this.onHit(id, HIT_DMG, m);
    swarmApart(this.monsters, dt);
    if (this.traps.length) this.stepTraps();
    if (this.ticks % SNAP_EVERY === 0) {
      const msg = {t: "m", scene: this.scene, l: this.monsters.map(m => m.snapshot())};
      if ((this.ticks / SNAP_EVERY) % DOORS_EVERY === 1) msg.d = this.W.doors.filter(d => !d.link && d.target === 1).map(d => d.d.name);          // late joiners learn which doors are open
      this.io.toFloor(msg);
    }
  }
}
