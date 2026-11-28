// Right Door, Wrong Exit in its Blender rooms (games/rdwe/blender.js, the graph in games/rdwe/blender_rooms.js), solo: through the L4 gate into the
// dining room, which is now world/rdwe_dining.glb with its baked light and world/rdwe_dining.json's colliders; the walker stands on the floor, is
// stopped by a wall and climbs the green stairs; the door at the top takes it to the hallway, a side door of the hallway to the hall of doors and
// back, each time at the far side's arrival point; a shut door does not open; the dining room's front door (`house`) ends the game and the player is
// back on L4. Then the grocery's entrance into the finale, and the finale's `win` door out. Every delivered room is checked for its files.
// Usage: node tools/rdwe_blender_test.mjs     (needs Playwright + Chromium, and internet for three.js from unpkg; run from the repo root)
import {createRequire} from "node:module";
import {readFileSync, existsSync} from "node:fs";
import {createServer} from "../server/server.js";
import {ROOMS, SPINE, MISSING} from "../games/rdwe/blender_rooms.js";
const {chromium} = createRequire(import.meta.url)("playwright");
let failed = 0;
const check = (name, ok, extra = "") => { console.log((ok ? "PASS " : "FAIL ") + name + (extra ? "  " + extra : "")); if (!ok) failed++; };

// ---- the data, without a browser: every room has its files, every link lands on a link of the room it names, and the story runs dining..grocery
{
  const bad = [];
  for (const [id, r] of Object.entries(ROOMS)) {
    for (const f of [`world/${r.scene}.glb`, `world/${r.scene}.json`]) if (!existsSync(f)) bad.push(`${id}: no ${f}`);
    const doc = JSON.parse(readFileSync(`world/${r.scene}.json`, "utf8"));
    if (doc.links.length !== Object.keys(r.links).length) bad.push(`${id}: ${doc.links.length} links in its json, ${Object.keys(r.links).length} in the graph`);
    for (const [door, e] of Object.entries(r.links)) if (e.to && !(ROOMS[e.to.room] && ROOMS[e.to.room].links[e.to.door])) bad.push(`${id}.${door} -> ${e.to.room}.${e.to.door}`);
  }
  check(`the graph: ${Object.keys(ROOMS).length} rooms, each with its glb and json, every link landing on a link`, Object.keys(ROOMS).length === 43 && bad.length === 0, bad.join("; "));
  check("the seven rooms the game had are all Blender rooms, and the story joins them", ["dining", "hallway", "teal", "teal2", "flooded", "trampoline", "grocery"].every(id => ROOMS[id])
    && Object.entries(SPINE).every(([id, d]) => d === null ? id === "grocery" : !!ROOMS[id].links[d].to));
  check("the dining room's front door and the finale's win door leave the game", ROOMS.dining.links.house.out === "leave" && ROOMS.finale.links.win.out === "leave");
  check("the six god rooms have no json yet and are left out", MISSING.length === 6 && MISSING.every(s => /^rdwe_god_/.test(s)) && !Object.keys(ROOMS).some(id => /god/.test(id)), MISSING.join(","));
}

const srv = await createServer({port: 0, countdownMs: 60000});
const browser = await chromium.launch({args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]});
const errors = [];
const wait = (page, fn, arg, ms = 90000) => page.waitForFunction(fn, arg, {timeout: ms, polling: 100}).then(() => true, () => false);
const W = "./games/rdwe/walk.js";
async function enterGate(page) {
  await page.evaluate(async () => { const g = window.__game; if (g.S.id !== "L4") await g.loadScene("L4"); const dr = g.doors.find(d => d.d.name === "DoorLeaf_Gate_RDW"); g.teleport([dr.cx, g.S.floor, dr.cz]); g.openDoor(dr, true); });
  if (!await wait(page, () => window.__game.S.id === "T" && !window.__game.loading)) return false;
  await page.evaluate(() => { const g = window.__game, dr = g.doors.find(d => d.link && d.link.game); g.openDoor(dr, true); });
  return wait(page, () => document.getElementById("gamemount").style.display === "block");
}
// (polled with evaluate: waitForFunction takes the promise an async predicate returns as truthy)
async function inRoom(page, id, ms = 120000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) {
    if (await page.evaluate(async ([W, id]) => { const c = (await import(W)).debug.current; return !!c && c.built.meta.id === id && c.state === "walk"; }, [W, id])) return true;
    await new Promise(r => setTimeout(r, 150));
  }
  return false;
}
// where the walker is: feet, eye, and the room
const where = page => page.evaluate(async W => { const c = (await import(W)).debug.current; if (!c) return null; const p = c.controls.position(); return {id: c.built.meta.id, x: p.x, z: p.z, feet: c.controls.feet(), yaw: c.controls.getLook().yaw}; }, W);
const near = (w, p, d = 0.6) => !!w && Math.hypot(w.x - p[0], w.z - p[2]) < d && Math.abs(w.feet - p[1]) < 0.3;
// stand on a link's mark (on its floor), settle, press use; it should begin the exit through that door
async function useLink(page, door) {
  return page.evaluate(async ([W, door]) => {
    const w = await import(W), c = w.debug.current, e = c.built.room.links[door], eye = c.controls.position().y - c.controls.feet();
    c.controls.setPosition(e.at[0], e.at[1] + 0.05 + eye, e.at[2]); c.sim(1 / 60, 20);
    const label = c.target, prompt = document.getElementById("prompt").textContent; c.use(); c.sim(1 / 60, 2);
    return {label, prompt, state: c.state, after: document.getElementById("prompt").style.display};
  }, [W, door]);
}
try {
  const page = await (await browser.newContext({viewport: {width: 900, height: 700}})).newPage();
  page.on("pageerror", e => errors.push(e.message)); if (process.env.RDWE_DEBUG) page.on("console", m => console.log("[console]", m.text().slice(0, 200)));
  await page.goto(`http://localhost:${srv.port}/`); await page.click("#l-solo");
  await page.waitForFunction(() => window.__game && !document.getElementById("load"), null, {timeout: 240000});
  check("the L4 gate takes us into the game", await enterGate(page));
  check("the game opens in the dining room", await inRoom(page, "dining"));
  const room = await page.evaluate(async W => {
    const c = (await import(W)).debug.current, b = c.built; let meshes = 0, baked = 0;
    b.group.traverse(o => { if (o.isMesh) { meshes++; if (o.material && o.material.lightMap) baked++; } });
    const doc = await (await fetch("world/rdwe_dining.json")).json();
    const lights = []; c.scene.traverse(o => { if (o.isLight) lights.push(o.type); });
    return {blender: !!b.blender, scene: b.sceneId, meshes, baked, lightmaps: b.debug.bake.textures.length, boxes: b.world.length, cols: doc.colliders.length, doors: doc.doors.length,
      leaves: [...b.doors.values()].filter(d => d.leaf).length, lights, env: !!c.scene.environment};
  }, W);
  check("it is the Blender room: the glb's meshes, drawn with their baked light", room.blender && room.scene === "rdwe_dining" && room.meshes >= 20 && room.baked >= 15 && room.lightmaps >= 2, JSON.stringify(room));
  check("its colliders are the json's, plus one per door leaf, and every leaf is in the model", room.boxes === room.cols + room.doors && room.leaves === room.doors, JSON.stringify(room));
  check("no lights are added: the light is all baked", room.lights.length === 0 && !room.env, JSON.stringify(room.lights));
  // the walker arrives at the spawn and stands on the floor
  await page.evaluate(async W => (await import(W)).debug.current.sim(1 / 60, 60), W);
  const w0 = await where(page);
  check("the walker starts at the dining room's spawn, on the floor", near(w0, ROOMS.dining.spawn), JSON.stringify(w0));
  // the code room's lamp beat, kept: at 0.87 of every 28 s the green lamp clicks off (the room's second bake) for 3 s
  const lamp = await page.evaluate(async W => {
    const c = (await import(W)).debug.current, b = c.built.debug, L = b.lamp;
    c.setLoop(false);                                          // the simulation only: the frame loop would move the clock between the steps
    const ph = (b.elapsed % L.period) / L.period, toOn = ((1 - ph) % 1) * L.period + 0.5;           // to just after the start of the next cycle (the lamp on)
    c.sim(1 / 30, Math.round(toOn * 30)); const t0 = b.lightSet;
    c.sim(1 / 30, Math.round((L.offAt * L.period + L.off / 2 - 0.5) * 30)); const t1 = b.lightSet;         // to the middle of the lamp-off beat
    c.sim(1 / 30, Math.round(L.off * 30)); const t2 = b.lightSet;
    c.setLoop(true);
    return [t0, t1, t2];
  }, W);
  check("the dining room's lamp clicks off and on again (its night bake)", lamp.join() === "day,night,day", lamp.join());
  // a wall stops it: walk west into the west wall (x = -8) from x = -6, at z = 8
  const wall = await page.evaluate(async W => {
    const c = (await import(W)).debug.current, eye = c.controls.position().y - c.controls.feet();
    c.controls.setPosition(-6, eye, 8); c.controls.setLook(Math.PI / 2, 0); c.controls.setKeys({forward: true}); c.sim(1 / 60, 240); c.controls.setKeys({});
    const p = c.controls.position(); return {x: p.x, z: p.z};
  }, W);
  check("a wall stops the walker", wall.x > -8.0 && wall.x < -7.4, JSON.stringify(wall));
  // the green stairs: from the foot, walk north up twelve steps to the landing (3 m up)
  const stairs = await page.evaluate(async W => {
    const c = (await import(W)).debug.current, eye = c.controls.position().y - c.controls.feet();
    c.controls.setPosition(-0.5, eye, -9.4); c.controls.setLook(0, 0); c.controls.setKeys({forward: true}); c.sim(1 / 60, 420); c.controls.setKeys({}); c.sim(1 / 60, 30);
    const p = c.controls.position(); return {z: p.z, feet: c.controls.feet()};
  }, W);
  check("the walker climbs the stairs to the landing", Math.abs(stairs.feet - 3.0) < 0.1 && stairs.z < -14.2, JSON.stringify(stairs));
  // the door at the top: dining.stairs -> hallway.dining
  const u1 = await useLink(page, "stairs");
  check("at the top of the stairs, use goes through the door", u1.state === "exit" && /DOOR/.test(u1.label || ""), JSON.stringify(u1));
  check("... and the page's prompt line said so, and is cleared once the walker goes through", u1.prompt === "Press E to open the door" && u1.after === "none", JSON.stringify(u1));
  check("link 1: the stairs door leads into the hallway", await inRoom(page, "hallway"));
  const w1 = await where(page);
  check("... at the hallway's arrival point for that door", near(w1, ROOMS.hallway.links.dining.arrive), JSON.stringify(w1));
  check("... and the door behind is open (a two-way link)", await page.evaluate(async W => { const d = (await import(W)).debug.current.built.doors.get("DoorLeaf_dining"); return !!d && d.p === 1 && d.box.off; }, W));
  // a side door: hallway.door_c -> door_hall.hallway, and back
  const u2 = await useLink(page, "door_c");
  check("link 2: the hallway's third door leads into the hall of doors", u2.state === "exit" && await inRoom(page, "door_hall"), JSON.stringify(u2));
  check("... at its arrival point", near(await where(page), ROOMS.door_hall.links.hallway.arrive), JSON.stringify(await where(page)));
  const shut = await page.evaluate(async W => {        // a door that never opens has no link; walking into its leaf is a wall
    const c = (await import(W)).debug.current, d = c.built.doors.get("DoorLeaf_wrong_1"); return !!d && !d.box.off && d.d.opens === "never" && !c.built.room.links.wrong_1;
  }, W);
  check("the hall's other doors never open", shut);
  const u3 = await useLink(page, "hallway");
  check("link 3: and back the same way into the hallway, at the third door", u3.state === "exit" && await inRoom(page, "hallway") && near(await where(page), ROOMS.hallway.links.door_c.arrive), JSON.stringify(await where(page)));
  // back down to the dining room, whose front door ends the game
  await useLink(page, "dining");
  check("link 4: the hallway's first door leads back down to the dining room, at the top of the stairs", await inRoom(page, "dining") && near(await where(page), ROOMS.dining.links.stairs.arrive), JSON.stringify(await where(page)));
  const out = await useLink(page, "house");
  check("the dining room's front door is a way out", out.state === "exit" && out.label === "LEAVE", JSON.stringify(out));
  const back = await wait(page, () => window.__game.S.id === "L4" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000);
  const p4 = await page.evaluate(() => window.__game.P.p.toArray());
  check("... and the player is back on L4 at the gate", back && Math.hypot(p4[0] + 121.2, p4[2] - 63.6) < 2.5, JSON.stringify(p4));
  check("... and the walk says the game was left by the house door", await page.evaluate(async W => { const w = await import(W); return w.next() === null && w.leftBy() === "house"; }, W));
  // again: the trampoline park's reserved door is shut; the grocery's entrance opens on the finale, and the finale's win door ends the game
  check("into the game again", await enterGate(page) && await inRoom(page, "dining"));
  await page.evaluate(async W => (await import(W)).debug.current.jump("trampoline", "vent"), W);
  check("the trampoline park (coming out of the vent)", await inRoom(page, "trampoline") && near(await where(page), ROOMS.trampoline.links.vent.arrive), JSON.stringify(await where(page)));
  const gods = await useLink(page, "gods");
  check("its reserved door to the god rooms does not open", gods.state === "walk" && gods.label === "IT DOES NOT OPEN", JSON.stringify(gods));
  await page.evaluate(async W => (await import(W)).debug.current.jump("grocery", "glow"), W);
  check("the grocery", await inRoom(page, "grocery"));
  const ent = await useLink(page, "entrance");
  check("the grocery's entrance leads into the finale", ent.state === "exit" && await inRoom(page, "finale") && near(await where(page), ROOMS.finale.links.grocery.arrive), JSON.stringify(await where(page)));
  const fin = await page.evaluate(async W => { const c = (await import(W)).debug.current; let meshes = 0; c.built.group.traverse(o => { if (o.isMesh) meshes++; }); return {meshes, boxes: c.built.world.length, win: !!c.built.doors.get("DoorLeaf_win")}; }, W);
  check("the finale is loaded, with its win door", fin.meshes > 20 && fin.boxes > 60 && fin.win, JSON.stringify(fin));
  const win = await useLink(page, "win");
  check("the finale's win door is a way out", win.state === "exit" && win.label === "LEAVE", JSON.stringify(win));
  check("... and the player is back on L4", await wait(page, () => window.__game.S.id === "L4" && !window.__game.loading && document.getElementById("gamemount").style.display === "none", null, 150000)
    && await page.evaluate(async W => (await import(W)).leftBy() === "win", W));
  // every other room loads and stands the walker on a floor at each of its arrival points
  const ids = Object.keys(ROOMS);
  const res = await page.evaluate(async ([W, ids]) => {
    const w = await import(W), mount = document.getElementById("gamemount"); mount.style.display = "block";
    const el = t => document.createElement(t || "div"), joy = el(); joy.appendChild(Object.assign(el(), {className: "knob"}));
    const els = {mount, fade: el(), objective: el(), hint: el(), joystick: joy, readout: el(), tally: el(), use: el("button")};
    const out = {};
    for (const id of ids) {
      const done = w.start(id, els, {sound: false});
      while (!w.debug.current || w.debug.current.built.meta.id !== id) await new Promise(r => setTimeout(r, 50));
      const c = w.debug.current, bad = [];
      for (const [door, e] of Object.entries(c.built.room.links)) {
        const eye = c.controls.position().y - c.controls.feet();
        c.controls.setPosition(e.arrive[0], e.arrive[1] + 0.3 + eye, e.arrive[2]); c.sim(1 / 60, 40);
        const f = c.controls.feet(), p = c.controls.position();
        if (Math.abs(f - e.arrive[1]) > 0.35 || Math.hypot(p.x - e.arrive[0], p.z - e.arrive[2]) > 0.05) bad.push(`${door}: feet ${f.toFixed(2)} vs ${e.arrive[1]}`);
      }
      out[id] = bad;
      w.cancel(); await done;
    }
    mount.style.display = "none";
    return out;
  }, [W, ids]);
  const badRooms = Object.entries(res).filter(([, b]) => b.length);
  check(`every room (${ids.length}) loads, and each arrival point stands the walker on a floor`, Object.keys(res).length === ids.length && badRooms.length === 0, JSON.stringify(badRooms));
  check("no page errors", errors.length === 0, errors.join(" | "));
} catch (e) { console.log("ERROR", e.message); failed++; }
await browser.close(); await srv.close(); console.log(failed ? `${failed} FAILED` : "ALL PASSED"); process.exit(failed ? 1 : 0);
